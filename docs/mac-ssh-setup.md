# Mac SSH Setup for Remote VM

## Context

We run Claude Code on a remote GCP AI Workstation (Belgium, `34.38.81.215`) via mosh + tmux. Each parallel Claude agent runs in its own tmux session. The Mac connects via mosh for low-latency typing; the phone (Moshi app) also uses mosh.

SSH with ControlMaster is configured for fast `scp` and non-interactive commands (e.g., listing/killing sessions). VS Code connects via SSH (not mosh).

## Prerequisites

- macOS with mosh installed (`brew install mosh`)
- SSH key (`~/.ssh/id_ed25519`) authorized on the VM
- Any terminal app (iTerm2, Ghostty, Terminal.app all work)

## SSH config

`~/.ssh/config` on the Mac:

```
Host superextra-vm
    HostName 34.38.81.215
    User adam
    AddressFamily inet
    ServerAliveInterval 15
    ServerAliveCountMax 6000
    TCPKeepAlive no
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 4h
    Ciphers aes128-gcm@openssh.com,chacha20-poly1305@openssh.com
    ObscureKeystrokeTiming no
    KexAlgorithms curve25519-sha256,curve25519-sha256@libssh.org
    HostKeyAlgorithms ssh-ed25519,ssh-ed25519-cert-v01@openssh.com
    PreferredAuthentications publickey
    IdentitiesOnly yes
    IdentityFile ~/.ssh/id_ed25519
    CheckHostIP no
    RekeyLimit 1G 1h
```

Create the sockets directory: `mkdir -p ~/.ssh/sockets`

**Key optimizations (noticeable effect):**

- `ObscureKeystrokeTiming no` — **biggest win.** Disables OpenSSH 10's 20ms keystroke quantization delay
- `Ciphers aes128-gcm` — uses hardware AES acceleration instead of software chacha20
- `ControlMaster auto` + `ControlPersist 4h` — connection reuse, no repeated handshakes
- `ServerAliveInterval 15` + `ServerAliveCountMax 6000` — detects dead connections in ~45s, keeps alive ~25 hours

**Additional tuning (marginal but harmless):**

- `AddressFamily inet` — skips IPv6 attempt on connect
- `KexAlgorithms` + `HostKeyAlgorithms` — pins fastest algorithms, skips negotiation
- `PreferredAuthentications publickey` + `IdentitiesOnly yes` — skips trying other auth methods
- `CheckHostIP no` — skips extra DNS lookup
- `RekeyLimit 1G 1h` — prevents unexpected rekey latency spikes

## VM server-side config

**sshd (`/etc/ssh/sshd_config`):**

- `ClientAliveInterval 60` + `ClientAliveCountMax 6000`
- `TCPKeepAlive no`

**TCP tuning (`/etc/sysctl.conf`) — applied to reduce latency:**

Key changes (noticeable effect):

- `net.ipv4.tcp_congestion_control=bbr` — Google's congestion control, better latency than cubic
- `net.ipv4.tcp_autocorking=0` — sends small packets (keystrokes) immediately instead of batching
- `net.ipv4.tcp_slow_start_after_idle=0` — keeps connection warm after typing pauses

Additional tuning (marginal but harmless):

- `net.ipv4.tcp_low_latency=1` — prioritizes latency over throughput
- `net.ipv4.tcp_notsent_lowat=131072` — caps kernel send buffer at 128KB, reduces output bufferbloat
- `net.ipv4.tcp_thin_linear_timeouts=1` — faster retransmit for thin streams (SSH)
- `net.ipv4.tcp_no_metrics_save=1` — prevents cached metrics from suboptimal connections

**Packet scheduling:**

BBR works best with Fair Queue qdisc (persistent via systemd service `fq-qdisc.service`):

```bash
tc qdisc replace dev ens4 root fq
```

## macOS TCP optimization

**Delayed ACK (noticeable effect):**

```bash
sudo sysctl -w net.inet.tcp.delayed_ack=0
```

Made persistent via LaunchDaemon at `/Library/LaunchDaemons/com.user.tcp-delayed-ack.plist`.
Sends TCP ACKs immediately instead of waiting up to 40ms to batch them.

**MSS default (marginal but correct):**

```bash
sudo sysctl -w net.inet.tcp.mssdflt=1448
```

Fixes macOS default of 512 bytes to proper Ethernet value. Add to LaunchDaemon to persist.

Verify settings: `sysctl net.inet.tcp.delayed_ack` (should be 0), `sysctl net.inet.tcp.mssdflt` (should be 1448).

## `cv` command — Mac side (`~/.zshrc`)

```bash
CVM_HOST="adam@34.38.81.215"
CVM_REPO="~/src/superextra-landing"
CVM_MOSH() { LC_CTYPE=en_US.UTF-8 mosh --server="LANG=en_US.UTF-8 LC_CTYPE=en_US.UTF-8 mosh-server" "$@"; }

cv          — new session (random name via petname), opens claude via mosh
cv l        — list sessions, pick one to attach via mosh
cv k [name] — kill a session (interactive picker if no name)
cv K        — kill all sessions
cv w [name] — new worktree session
```

## `cv` command — VM side (`~/.bashrc`)

Same subcommands, runs locally using tmux directly:

```bash
cv          — new session (random name via petname), opens claude
cv l        — list sessions, pick one (uses tmux attach outside tmux, switch-client inside tmux)
cv k [name] — kill a session (interactive picker if no name)
cv K        — kill all sessions
cv w [name] — new worktree session
```

`cv l` dumps the last 2500 lines of session history (with colors) before attaching, so you can scroll back through previous output with native terminal scrolling.

Also available on VM: `bye` (kill current session), `rename <name>` (rename current session).

## tmux config (`~/.tmux.conf` on VM)

```
set -g mouse off           # native terminal scrolling (smooth in VS Code)
bind m set -g mouse \; display "Mouse #{?mouse,ON,OFF}"  # Ctrl+B, m to toggle
set -g status off          # no status bar (reduces scroll artifacts)
set -g escape-time 0       # no ESC delay
```

**Mouse toggle:** Default is off for smooth scrolling in VS Code. Toggle on with Ctrl+B, m when using mobile (Moshi needs mouse on for swipe scrolling).

## VS Code

Open VS Code to the VM from Mac terminal:

```bash
cvs    # alias for: code --remote ssh-remote+superextra-vm /home/adam/src/superextra-landing
```

Key VS Code settings (`settings.json`):

- `terminal.integrated.gpuAcceleration: "auto"` — WebGL rendering, fastest terminal renderer
- `remote.SSH.useLocalServer: true` — keeps remote server alive through brief disconnects
- `remote.SSH.localServerDownload: "always"` — pre-downloads server binary
- `remote.SSH.connectTimeout: 60` — longer timeout for reconnects
- `window.restoreWindows: "all"` — restores all windows (including remote) on restart

### VS Code terminal typing latency

VS Code's terminal has higher typing latency than standalone terminals because it uses a web-based renderer (xterm.js in Electron). The hard floor is the network round-trip (~40ms to Belgium). Key optimizations are on the SSH/TCP side (see above).

**Not recommended:** VS Code's built-in local echo (`localEchoEnabled`) causes cursor jumping and ghost characters with tmux/Claude Code. Disabled.

For typing-heavy work (Claude Code sessions), use iTerm2/Ghostty with `cv` (mosh provides true local echo). Use VS Code for file browsing, editing, and quick terminal commands.

## How parallel agents work

Each `cv` (from Mac) opens a new mosh connection to a new tmux session. Each session runs its own Claude Code instance. They work in parallel, fully independent.

- Mac: each session is a separate terminal tab (iTerm2, Ghostty, etc.)
- Mobile (Moshi): each session is a separate mosh connection
- Both Mac and phone can connect to the same session simultaneously

## Screenshot to VM

`Cmd+Shift+1` takes a screenshot on the Mac, uploads to `/home/adam/screenshots/` on the VM via SCP, and copies the remote path to clipboard. Paste the path into Claude Code to share images.

Script: `~/.local/bin/screenshot-to-vm`

## Troubleshooting

- **mosh exits immediately**: Check UDP ports 60000-61000 in GCP firewall. Verify locale: `locale -a | grep en_US.utf8`.
- **ControlMaster socket stale**: `rm ~/.ssh/sockets/*` and reconnect.
- **Typing feels slow**: Run `ping 34.38.81.215` to check if it's network (~40ms is normal) or config. Verify `sysctl net.inet.tcp.delayed_ack` is 0. Check `ObscureKeystrokeTiming no` is in SSH config.
- **Scrolling jumpy in VS Code**: Check `tmux show -g mouse` — should be `off`. Toggle with Ctrl+B, m.
- **Scrolling broken on mobile**: Toggle mouse on with Ctrl+B, m.
