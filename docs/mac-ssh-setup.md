# Mac SSH Setup for Remote VM

## Context

We run Claude Code on a remote GCP AI Workstation (Belgium, `34.38.81.215`) via mosh + tmux. Each parallel Claude agent runs in its own tmux session. The Mac connects via mosh for low-latency typing; the phone (Moshi app) also uses mosh.

SSH with ControlMaster is configured for fast `scp` and non-interactive commands (e.g., listing/killing sessions). VS Code connects via SSH (not mosh). Cursor can use either SSH or mosh.

Mutagen provides real-time bidirectional file sync between the VM and a local mirror folder, so code changes from Claude on the VM appear instantly in a local VS Code/Cursor window.

## Prerequisites

- macOS with mosh installed (`brew install mosh`)
- Mutagen installed (`brew install mutagen-io/mutagen/mutagen`)
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

## Mutagen file sync

Real-time bidirectional sync between VM and local mirror folder. Claude edits on the VM appear instantly in local VS Code/Cursor.

**Folders:**

| Folder                                  | Purpose                                     |
| --------------------------------------- | ------------------------------------------- |
| `~/src/superextra-landing`              | Your real local repo — fully yours, no sync |
| `~/src/superextra-landing-vm`           | Mutagen mirror — bidirectional sync with VM |
| VM: `/home/adam/src/superextra-landing` | The remote repo where Claude works          |

**Sync session:** `superextra-vm-sync`

- Mode: `two-way-safe` — changes sync both directions; conflicts are flagged, never overwritten
- Ignores: node_modules, .svelte-kit, build, dist, .turbo, .next, .vercel, .venv, **pycache**, \*.pyc, .firebase
- .git IS synced — so local mirror has full git history, diffs, branches visible in VS Code
- Daemon auto-starts on boot (registered with launchd via `mutagen daemon register`)

**Useful commands:**

| Command                                     | What it does                                          |
| ------------------------------------------- | ----------------------------------------------------- |
| `mutagen sync list`                         | Show sync status, conflicts, file counts              |
| `mutagen sync flush`                        | Force immediate sync (run after large git operations) |
| `mutagen sync pause superextra-vm-sync`     | Pause sync temporarily                                |
| `mutagen sync resume superextra-vm-sync`    | Resume sync                                           |
| `mutagen sync reset superextra-vm-sync`     | Reset sync state if stuck                             |
| `mutagen sync terminate superextra-vm-sync` | Remove sync session                                   |

**Conflict handling:**

When both sides change the same file simultaneously, Mutagen flags a conflict:

- No data is lost — both versions preserved
- A macOS notification appears (via `mutagen-conflict-watch` background service)
- Run `mutagen sync list` to see conflicting files
- Resolve by keeping one version (overwrite/delete the other)
- Sync resumes automatically after resolution

**Important:** Don't commit on both sides simultaneously. The .git directory syncs bidirectionally, so concurrent git operations can conflict. Commit from one side at a time.

**Conflict watcher:** Auto-starts via LaunchAgent at `~/Library/LaunchAgents/com.user.mutagen-conflict-watch.plist`. Checks every 10 seconds, shows macOS notification with sound on conflict.

## `cv` command — Mac side (`~/.zshrc`)

```bash
CVM_HOST="superextra-vm"                    # SSH alias — inherits all SSH config optimizations
CVM_REPO="/home/adam/src/superextra-landing"  # full path — avoids ~ expansion issues over mosh
CVM_MOSH() { ... }                          # mosh wrapper with locale settings + MOSH_TITLE_NOPREFIX
```

**Commands:**

| Command       | What it does       | How it works                                                                                                            |
| ------------- | ------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| `cv`          | New Claude session | Creates tmux session with random name (petname), opens Claude Code via mosh                                             |
| `cv l`        | List & attach      | Shows tmux sessions, pick one to attach via mosh. Dumps last 2500 lines of session history (with colors) for scrollback |
| `cv k [name]` | Kill session       | Interactive picker if no name given. Uses SSH (not mosh)                                                                |
| `cv K`        | Kill all sessions  | Uses SSH                                                                                                                |
| `cv w [name]` | Worktree session   | Creates git worktree + tmux session for isolated work                                                                   |

**Stale socket handling:** `cv` auto-checks SSH connectivity before connecting. If the connection is dead, it clears stale sockets so the next attempt makes a fresh connection.

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

**Shell focus integration (`~/.bashrc`):** When inside tmux, the shell responds to terminal focus events to hide/show the cursor.

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
set-hook -g client-focus-out "run-shell -b 'printf \"\\033[?25l\" > #{client_tty}'"
set-hook -g client-focus-in "run-shell -b 'printf \"\\033[?25h\" > #{client_tty}'"

# Plugins
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'nhdaly/tmux-better-mouse-mode'
set -g @scroll-speed-num-lines-per-scroll "1"
```

**Key behaviors:**

- **Mouse off by default** — enables native smooth scrolling in VS Code and Cursor
- **Ctrl+B, m** — toggles mouse on for mobile (Moshi needs mouse on for swipe scrolling)
- **Focus cursor** — cursor hides when terminal tab loses focus, shows when regained
- **No status bar** — reduces visual artifacts in VS Code's scrollback

## VS Code / Cursor

**Open VS Code to the VM (SSH remote):**

```bash
cvs    # alias for: code --remote ssh-remote+superextra-vm /home/adam/src/superextra-landing
```

**Open local mirror folder:** Open `~/src/superextra-landing-vm` in VS Code/Cursor to see Claude's changes synced in real-time via Mutagen.

**Keyboard shortcut `Cmd+Shift+M`** — opens a new terminal tab and runs `cv` to create/attach a Claude session. Works in both VS Code (SSH remote) and Cursor (local mosh). Always creates a new tab.

**Key VS Code/Cursor settings (`settings.json`):**

| Setting                                        | Value      | Why                                                                                                            |
| ---------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------- |
| `terminal.integrated.gpuAcceleration`          | `"auto"`   | WebGL rendering — fastest terminal renderer                                                                    |
| `terminal.integrated.shellIntegration.enabled` | `false`    | Prevents terminal relaunch warnings on reconnect                                                               |
| `git.terminalAuthentication`                   | `false`    | Prevents Git from injecting GIT_ASKPASS into terminals (fixes orange tabs). Source Control sidebar still works |
| `remote.SSH.useLocalServer`                    | `true`     | Keeps remote server alive through brief disconnects                                                            |
| `remote.SSH.localServerDownload`               | `"always"` | Pre-downloads server binary for faster reconnects                                                              |
| `remote.SSH.connectTimeout`                    | `60`       | Longer timeout for reconnects                                                                                  |
| `window.restoreWindows`                        | `"all"`    | Restores all windows (including remote) on restart                                                             |
| `window.confirmBeforeClose`                    | `"always"` | Prevents accidental window close                                                                               |

**Typing latency in VS Code terminal:** Higher than standalone terminals due to web-based renderer. The ~40ms network round-trip is the hard floor. Key mitigations are on the SSH/TCP side (see above). VS Code's built-in local echo was tested and rejected — causes cursor jumping with tmux/Claude Code.

For typing-heavy work (Claude Code sessions), use iTerm2/Ghostty with `cv` (mosh provides true local echo). Use VS Code for file browsing, editing, and quick terminal commands.

## How parallel agents work

Each `cv` (from Mac) opens a new mosh connection to a new tmux session. Each session runs its own Claude Code instance. They work in parallel, fully independent.

- Mac: each session is a separate terminal tab (iTerm2, Ghostty, etc.)
- Mobile (Moshi): each session is a separate mosh connection
- Both Mac and phone can connect to the same session simultaneously
- Local mirror (via Mutagen) shows all changes from all agents in real-time

## Screenshot to VM

`Cmd+Shift+1` takes a screenshot on the Mac, uploads to `/home/adam/screenshots/` on the VM via SCP, and copies the remote path to clipboard. Paste the path into Claude Code to share images.

Script: `~/.local/bin/screenshot-to-vm`

## Troubleshooting

| Problem                              | Fix                                                                                                                                       |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **mosh exits immediately**           | Check UDP ports 60000-61000 in GCP firewall. Verify locale: `locale -a \| grep en_US.utf8`                                                |
| **ControlMaster socket stale**       | `rm ~/.ssh/sockets/*` and reconnect (or just run `cv` — it auto-clears stale sockets)                                                     |
| **Typing feels slow**                | Run `ping 34.38.81.215` — ~40ms is normal. Check `sysctl net.inet.tcp.delayed_ack` is 0. Verify `ObscureKeystrokeTiming no` in SSH config |
| **Scrolling jumpy in VS Code**       | `tmux show -g mouse` should be `off`. Toggle with Ctrl+B, m                                                                               |
| **Scrolling broken on mobile**       | Toggle mouse on: Ctrl+B, m                                                                                                                |
| **Orange terminal tabs**             | Check `git.terminalAuthentication` is `false`. Ensure Claude Code and Copilot Chat extensions disabled on remote                          |
| **Cursor visible in unfocused tabs** | Verify `focus-events on` in tmux.conf and focus hooks are present                                                                         |
| **`cv` opens wrong folder**          | Check `CVM_REPO` in `~/.zshrc` uses full path (`/home/adam/src/...`), not `~`                                                             |
| **Mutagen not syncing**              | `mutagen sync list` — check status. `mutagen sync flush` to force. `mutagen daemon start` if daemon died                                  |
| **Mutagen conflict**                 | `mutagen sync list` shows conflicting files. Keep one version, delete/overwrite the other. Sync resumes automatically                     |
| **Mutagen stuck**                    | `mutagen sync reset superextra-vm-sync` to reset state                                                                                    |
