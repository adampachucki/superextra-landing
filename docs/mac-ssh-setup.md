# Mac SSH Setup for Remote VM

## Context

We run Claude Code on a remote GCP AI Workstation (Belgium, `34.38.81.215`) via mosh + tmux. Each parallel Claude agent runs in its own tmux session. The Mac connects via mosh for low-latency typing; the phone (Moshi app) also uses mosh.

SSH with ControlMaster is configured for fast `scp` and non-interactive commands (e.g., listing/killing sessions). VS Code connects via SSH (not mosh). Cursor can use either SSH or mosh.

## Prerequisites

- macOS with mosh installed (`brew install mosh`)
- SSH key (`~/.ssh/id_ed25519`) authorized on the VM
- VS Code with `code` CLI installed (Cmd+Shift+P > "Shell Command: Install 'code' command in PATH")
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
CVM_HOST="superextra-vm"                    # SSH alias — inherits all SSH config optimizations
CVM_REPO="/home/adam/src/superextra-landing"  # full path — avoids ~ expansion issues over mosh
CVM_MOSH() { ... }                          # mosh wrapper with locale settings
```

**Commands:**

| Command       | What it does       | How it works                                                                                                            |
| ------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `cv`          | New Claude session | Creates tmux session with random name (petname), opens Claude Code via mosh                                             |
| `cv l`        | List & attach      | Shows tmux sessions, pick one to attach via mosh. Dumps last 2500 lines of session history (with colors) for scrollback |
| `cv k [name]` | Kill session       | Interactive picker if no name given. Uses SSH (not mosh)                                                                |
| `cv K`        | Kill all sessions  | Uses SSH                                                                                                                |
| `cv w [name]` | Worktree session   | Creates git worktree + tmux session for isolated work                                                                   |

**Mosh title:** `MOSH_TITLE_NOPREFIX=1` is set to prevent mosh from adding `[mosh]` prefix to terminal tab titles.

## `cv` command — VM side (`~/.bashrc`)

Same subcommands, runs locally using tmux directly (no mosh/SSH needed):

| Command       | What it does       | How it works                                                                                                                                     |
| ------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `cv`          | New Claude session | Creates tmux session with random name (petname), opens Claude Code                                                                               |
| `cv l`        | List & switch      | Shows sessions, pick one. Uses `tmux attach` outside tmux, `switch-client` inside tmux. Dumps 2500 lines of history with colors before attaching |
| `cv k [name]` | Kill session       | Interactive picker if no name                                                                                                                    |
| `cv K`        | Kill all           | Kills tmux server                                                                                                                                |
| `cv w [name]` | Worktree session   | Creates git worktree + tmux session                                                                                                              |

**Additional VM commands:**

- `bye` — kill the current tmux session
- `rename <name>` — rename the current tmux session

**Shell focus integration (`~/.bashrc`):** When inside tmux, the shell responds to terminal focus events to hide/show the cursor — complements the tmux focus hooks (see below).

## tmux config (`~/.tmux.conf` on VM)

```tmux
set -g mouse off              # native terminal scrolling (smooth in VS Code)
set -g escape-time 0          # no ESC delay
set -g status off             # no status bar (reduces scroll artifacts)
set -g set-titles on          # set terminal tab title
set -g set-titles-string "#S" # title = session name
set -g window-size latest
set -g focus-events on        # enable focus event detection

# Ctrl+B, m — toggle mouse on/off
bind m set -g mouse \; display "Mouse #{?mouse,ON,OFF}"

# Hide cursor when terminal tab loses focus, show when it regains focus
# Writes directly to the client TTY to bypass tmux's screen buffer
set-hook -g client-focus-out "run-shell -b 'printf \"\\033[?25l\" > #{client_tty}'"
set-hook -g client-focus-in "run-shell -b 'printf \"\\033[?25h\" > #{client_tty}'"

# Plugins
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'nhdaly/tmux-better-mouse-mode'
set -g @scroll-speed-num-lines-per-scroll "1"
```

**Key behaviors:**

- **Mouse off by default** — enables native smooth scrolling in VS Code and Cursor. Without this, tmux intercepts scroll events and scrolls line-by-line (jumpy).
- **Ctrl+B, m** — toggles mouse on for mobile (Moshi needs mouse on for swipe scrolling). Toggle off when back to VS Code.
- **Focus cursor** — cursor hides when terminal tab loses focus, shows when regained. Prevents confusion about which tab is active. Works via tmux hooks writing directly to the client TTY + shell-level focus event bindings.
- **No status bar** — reduces visual artifacts in VS Code's scrollback when tmux redraws.

## VS Code / Cursor

**Open VS Code to the VM:**

```bash
cvs    # alias for: code --remote ssh-remote+superextra-vm /home/adam/src/superextra-landing
```

**Keyboard shortcut `Cmd+Shift+M`** — opens a new terminal tab and runs `cv` to create/attach a Claude session. Works in both VS Code (SSH remote) and Cursor (local mosh). Always creates a new tab, never types into existing ones.

**Key VS Code/Cursor settings (`settings.json`):**

| Setting                                        | Value      | Why                                                                                                                         |
| ---------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------------------- |
| `terminal.integrated.gpuAcceleration`          | `"auto"`   | WebGL rendering — fastest terminal renderer                                                                                 |
| `terminal.integrated.shellIntegration.enabled` | `false`    | Prevents terminal relaunch warnings on reconnect                                                                            |
| `git.terminalAuthentication`                   | `false`    | Prevents Git from injecting GIT_ASKPASS into terminals (fixes orange tabs on reconnect). Source Control sidebar still works |
| `remote.SSH.useLocalServer`                    | `true`     | Keeps remote server alive through brief disconnects                                                                         |
| `remote.SSH.localServerDownload`               | `"always"` | Pre-downloads server binary for faster reconnects                                                                           |
| `remote.SSH.connectTimeout`                    | `60`       | Longer timeout for reconnects                                                                                               |
| `window.restoreWindows`                        | `"all"`    | Restores all windows (including remote) on restart                                                                          |
| `window.confirmBeforeClose`                    | `"always"` | Prevents accidental window close                                                                                            |

**Orange terminal tabs on reconnect:** Fixed by `git.terminalAuthentication: false` and `shellIntegration.enabled: false`. Claude Code and Copilot Chat extensions disabled on remote workspace (no per-extension setting to disable their terminal injection).

**Typing latency in VS Code terminal:** Higher than standalone terminals due to web-based renderer (xterm.js). The ~40ms network round-trip is the hard floor. Key mitigations are on the SSH/TCP side (see above). VS Code's built-in local echo (`localEchoEnabled`) was tested and rejected — causes cursor jumping and ghost characters with tmux/Claude Code.

For typing-heavy work (Claude Code sessions), use iTerm2/Ghostty with `cv` (mosh provides true local echo). Use VS Code for file browsing, editing, and quick terminal commands.

## How parallel agents work

Each `cv` (from Mac) opens a new mosh connection to a new tmux session. Each session runs its own Claude Code instance. They work in parallel, fully independent.

- Mac: each session is a separate terminal tab (iTerm2, Ghostty, etc.)
- Mobile (Moshi): each session is a separate mosh connection
- Both Mac and phone can connect to the same session simultaneously
- Switch between sessions: `cv l` from Mac or VM

## Screenshot to VM

`Cmd+Shift+1` takes a screenshot on the Mac, uploads to `/home/adam/screenshots/` on the VM via SCP, and copies the remote path to clipboard. Paste the path into Claude Code to share images.

Script: `~/.local/bin/screenshot-to-vm`

## Troubleshooting

| Problem                              | Fix                                                                                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **mosh exits immediately**           | Check UDP ports 60000-61000 in GCP firewall. Verify locale: `locale -a \| grep en_US.utf8`                                                |
| **ControlMaster socket stale**       | `rm ~/.ssh/sockets/*` and reconnect                                                                                                       |
| **Typing feels slow**                | Run `ping 34.38.81.215` — ~40ms is normal. Check `sysctl net.inet.tcp.delayed_ack` is 0. Verify `ObscureKeystrokeTiming no` in SSH config |
| **Scrolling jumpy in VS Code**       | `tmux show -g mouse` should be `off`. Toggle with Ctrl+B, m                                                                               |
| **Scrolling broken on mobile**       | Toggle mouse on: Ctrl+B, m                                                                                                                |
| **Orange terminal tabs**             | Check `git.terminalAuthentication` is `false`. Ensure Claude Code and Copilot Chat extensions disabled on remote                          |
| **Cursor visible in unfocused tabs** | Verify `focus-events on` in tmux.conf and focus hooks are present                                                                         |
| **`cv` opens wrong folder**          | Check `CVM_REPO` in `~/.zshrc` uses full path (`/home/adam/src/...`), not `~`                                                             |
