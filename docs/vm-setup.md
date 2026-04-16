# Remote VM Setup

## What

A GCP VM (g2-standard-4, Belgium) running Claude Code, accessible from any device. Claude runs in persistent zmx sessions on the VM — start a session from your Mac, pick it up from your phone.

## Why

- **Always-on sessions** — Claude keeps working after you close the laptop
- **Multi-device** — same session from Mac (VS Code terminal) and phone (Moshi app)
- **Native scroll on Mac** — zmx doesn't use alternate screen, so VS Code terminal scrolls natively
- **Parallel work** — multiple Claude sessions on different tasks simultaneously
- **Fast reconnect** — ET auto-reconnects after sleep/wake, mosh survives roaming

## Architecture

```
Mac (VS Code terminal)                       Mobile (Moshi app)
  ↓ ET (TCP, port 2022)                        ↓ mosh (UDP)
GCP VM (34.38.81.215)                        GCP VM
  ↓                                            ↓
zmx session ← native scroll                 tmux session (scroll wrapper)
  ↓                                            ↓ zmx attach
Claude Code                                  same zmx session → Claude Code
```

**zmx** owns the process. **tmux** is a thin scroll wrapper only used on mobile (mosh breaks native scroll). Both devices connect to the same zmx session.

### Why not just tmux?

tmux uses the alternate screen buffer, which causes VS Code's xterm.js to convert scroll wheel events to arrow key sequences. This is hardcoded in xterm.js — no setting can fix it. zmx is a raw pty relay that doesn't use alternate screen, so native scroll works.

### Why ET over SSH/mosh?

- **vs SSH**: ET auto-reconnects after laptop sleep (1-5s). SSH connections die.
- **vs mosh**: ET is a raw byte pipe — native scroll works. Mosh runs a terminal emulator that re-renders, breaking native scroll.
- **Trade-off**: ET has no local echo (unlike mosh), so typing has ~130ms round-trip latency. VS Code GPU rendering and Claude Code no-flicker mode mitigate this.

## Session commands

Two sister command sets. Same interface, different transport layer.

### `zx` — Mac/desktop (native scroll via ET)

Defined in Mac `~/.zshrc`. Use from VS Code terminal or any Mac terminal.

| Command            | Action                                                    |
| ------------------ | --------------------------------------------------------- |
| `zx` / `zx <name>` | Create session running Claude (+ tmux wrapper for mobile) |
| `zxl`              | List sessions, pick to join                               |
| `zxj <name>`       | Join session by name                                      |
| `zxk <name>`       | Kill session (both zmx + tmux)                            |
| `zxK`              | Kill all sessions                                         |

**Keyboard shortcut:** Cmd+Shift+X in VS Code opens a terminal and runs `zx`.

### `tx` — Mobile (tmux scroll via mosh)

Defined in VM `~/.bashrc`. Use after mosh-ing in from Moshi.

| Command            | Action                                           |
| ------------------ | ------------------------------------------------ |
| `tx` / `tx <name>` | Create session (tmux wrapping zmx)               |
| `txl`              | List sessions, pick to join                      |
| `txj <name>`       | Join session by name (auto-creates tmux wrapper) |
| `txk <name>`       | Kill session (both zmx + tmux)                   |
| `txK`              | Kill all sessions                                |

### `zx` on the VM

Also defined in VM `~/.bashrc`. Use when connected via SSH or ET directly (not through mosh). Attaches to zmx without tmux — native scroll.

### Cross-device workflow

1. Create from Mac: `zx my-task` → creates zmx session + detached tmux wrapper
2. Join from phone: `txj my-task` → attaches via tmux to same zmx session
3. Or vice versa — create from phone with `tx`, join from Mac with `zxj`
4. Both devices can be connected simultaneously (zmx leader policy: last typist controls resize)

### Session lifecycle

When Claude exits (`/exit`, Ctrl+C, or crash), zmx session dies, tmux wrapper dies. No orphans.

## Connection details

### ET (EternalTerminal)

- **Server**: systemd service `et.service`, port 2022, config at `/etc/et.cfg`
- **Client**: `brew install MisterTea/et/et` on Mac
- **GCP firewall**: rule `allow-et` (TCP 2022)
- **Telemetry**: disabled in `/etc/et.cfg`
- **Restart policy**: drop-in at `/etc/systemd/system/et.service.d/override.conf` sets `Restart=always`, `RestartSec=1s` so the service comes back within ~1 s on any exit.

### sshd keepalives

- **VM** `/etc/ssh/sshd_config.d/keepalive.conf`: `ClientAliveInterval 60`, `ClientAliveCountMax 3`, `TCPKeepAlive no`. Effective interval is 120 s (the vendor `50-cloudimg-settings.conf` drop-in sets 120 first and sshd is first-match-wins) — so dead peers are reaped in ~6 min.
- **Mac** `~/.ssh/config` for `superextra-vm`: `ServerAliveInterval 15`, `ServerAliveCountMax 10`, `TCPKeepAlive no`. ControlMaster is torn down after ~150 s of unanswered keepalives — loose enough to survive laptop sleep / wifi hiccups, tight enough to not hang for hours.

### mosh

- **Server**: installed on VM, auto-spawns `mosh-server` processes
- **Client**: Moshi app on iPhone
- **GCP firewall**: rule `allow-mosh` (UDP 60000-61000)

### SSH

Used for non-interactive commands (listing/killing sessions).

`~/.ssh/config` on Mac:

```
Host superextra-vm
    HostName 34.38.81.215
    User adam
    AddressFamily inet
    ServerAliveInterval 15
    ServerAliveCountMax 10
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

Key optimizations: `ObscureKeystrokeTiming no` (disables 20ms delay), `Ciphers aes128-gcm` (hardware AES), `ControlMaster` (connection reuse).

## Performance tuning

### VM TCP (`/etc/sysctl.conf`)

- `net.ipv4.tcp_congestion_control=bbr` — better latency than cubic
- `net.ipv4.tcp_autocorking=0` — sends keystrokes immediately
- `net.ipv4.tcp_slow_start_after_idle=0` — keeps connection warm
- `net.ipv4.tcp_mtu_probing=1` — survives PMTU blackholes without stalling
- BBR + Fair Queue qdisc: persistent via `net.core.default_qdisc=fq` in `/etc/sysctl.conf` (applied at sysctl-load time; no separate systemd unit)

### macOS TCP

- `sudo sysctl -w net.inet.tcp.delayed_ack=0` — immediate ACKs (persistent via LaunchDaemon)
- `sudo sysctl -w net.inet.tcp.mssdflt=1448` — proper Ethernet MSS

### VS Code terminal

| Setting                                        | Value   | Why                                                           |
| ---------------------------------------------- | ------- | ------------------------------------------------------------- |
| `terminal.integrated.gpuAcceleration`          | `on`    | WebGL rendering, fastest on Retina                            |
| `terminal.integrated.smoothScrolling`          | `false` | No animation delay                                            |
| `terminal.integrated.localEchoEnabled`         | `off`   | Tested and rejected — causes visual artifacts with Claude TUI |
| `terminal.integrated.defaultProfile.osx`       | `zsh`   | Required for `zx` commands                                    |
| `terminal.integrated.shellIntegration.enabled` | `false` | Prevents relaunch warnings                                    |

### Claude Code

Environment variables in VM `~/.bashrc`:

- `CLAUDE_CODE_NO_FLICKER=1` — double-buffered rendering, less data per frame
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` — no telemetry traffic competing with keystrokes

## zmx

Session manager that replaced tmux for the Mac path. Raw pty relay — doesn't use alternate screen, so native scroll works in VS Code.

- **Binary**: `/usr/local/bin/zmx` (root-owned, installed via `sudo install`)
- **Source**: `~/src/zmx` — upstream `github.com/neurosnap/zmx` (no GitHub fork)
- **Build requires**: Zig 0.15.2 (installed at `/opt/zig/`)
- **Logs**: `/run/user/1001/zmx/logs/`
- **Leader policy**: upstream uses `util.isUserInput()` (libghostty ANSI parser) to promote on deliberate user input — typing, arrow keys, etc. — and intentionally excludes focus / mouse events to avoid leader-thrashing. Plus a local patch (see below) that also promotes on _resize_, so switching devices without typing still resizes the pty to match the new window.

### Local fork state

- `main` tracks `origin/main` clean.
- `local-leader-fixes` = `main` + one commit: `local: promote to leader on resize`. Before rebase on new upstream, we also had an "extra leader triggers" patch (focus-in / ESC / space); it was dropped because upstream's `util.isUserInput()` covers the same ground better — and deliberately excludes focus events. Do not re-introduce.
- Belt-and-braces backup of the patch: `~/zmx-local-leader-patch.diff`.

### Update procedure

No `zmx-update` command exists — build manually:

```bash
cd ~/src/zmx
git checkout main && git pull --ff-only
git checkout local-leader-fixes && git rebase main   # resolve conflicts if upstream touched the resize block
zig build -Doptimize=ReleaseSafe
sudo cp /usr/local/bin/zmx /usr/local/bin/zmx.bak-$(date +%Y%m%d)
sudo install -m 755 -o root -g root zig-out/bin/zmx /usr/local/bin/zmx
```

Replacing the binary does **not** kill running zmx daemons — only new `zmx attach` invocations pick up the new binary. Safe mid-session.

### Rollback

```bash
sudo cp /usr/local/bin/zmx.bak-v042-patched /usr/local/bin/zmx
# or any other timestamped backup under /usr/local/bin/zmx.bak-*
```

## tmux config (`~/.tmux.conf` on VM)

Only used as mobile scroll wrapper. Minimal config:

```tmux
set -g set-titles on
set -g set-titles-string #S
set -g mouse on              # needed for scroll through mosh
set -g escape-time 0
set -g window-size latest
set -g status off
set -g focus-events on

set-hook -g client-focus-out run-shell -b printf \"\\033[?25l\" > #{client_tty}
set-hook -g client-focus-in run-shell -b printf \"\\033[?25h\" > #{client_tty}

set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",*256col*:RGB,*256col*:Tc"
set -g history-limit 50000
```

## VS Code

**Keyboard shortcuts:**

| Shortcut    | Action                                   |
| ----------- | ---------------------------------------- |
| Cmd+Shift+X | New terminal + `zx` (create zmx session) |
| Cmd+Shift+B | Claude BR terminal profile               |
| Cmd+Shift+R | Rename terminal tab                      |

## Mutagen file sync

Real-time bidirectional sync between VM and local mirror folder. Claude edits on the VM appear instantly in local VS Code.

| Folder                                  | Purpose                                     |
| --------------------------------------- | ------------------------------------------- |
| `~/src/superextra-landing`              | Your real local repo — no sync              |
| `~/src/superextra-landing-vm`           | Mutagen mirror — bidirectional sync with VM |
| VM: `/home/adam/src/superextra-landing` | The remote repo where Claude works          |

Session: `superextra-vm-sync`, mode `two-way-safe`. .git IS synced. Daemon auto-starts on boot.

| Command                                 | Action                         |
| --------------------------------------- | ------------------------------ |
| `mutagen sync list`                     | Show sync status and conflicts |
| `mutagen sync flush`                    | Force immediate sync           |
| `mutagen sync reset superextra-vm-sync` | Reset if stuck                 |

Conflict watcher: LaunchAgent at `~/Library/LaunchAgents/com.user.mutagen-conflict-watch.plist`. Shows macOS notification on conflict.

## Screenshots

Cmd+Shift+7 on Mac captures screenshot, uploads via SCP to `/home/adam/screenshots/` on VM, copies path to clipboard. Paste into Claude Code to share images. See `docs/screenshot-to-vm-setup.md`.

## VM details

|           |                                                     |
| --------- | --------------------------------------------------- |
| Host      | `adam@34.38.81.215` (static IP)                     |
| Machine   | GCP g2-standard-4, Belgium                          |
| OS        | Ubuntu 24.04                                        |
| Repo      | `~/src/superextra-landing`                          |
| Node      | 22 (via nvm)                                        |
| Python    | 3.12 (agent venv at `agent/.venv/`)                 |
| Env files | `.env`, `agent/.env` — gitignored, created manually |

### What's installed

- Node 22, Python 3.12, Docker, mosh, tmux, gcloud CLI
- EternalTerminal 6.2.10 (systemd service)
- zmx (built from source, Zig 0.15.2)
- Tailscale (installed, running on VM only — backup access path)
- MCP servers: GitHub (npx), Svelte, Miro, Apify

### Config files on VM

- `~/.bashrc` — `zx`, `tx` functions, performance env vars
- `~/.tmux.conf` — mouse on, status off (mobile wrapper only)
- `/etc/et.cfg` — ET server config
- `~/.claude.json` — MCP server config
- `~/src/superextra-landing/.env` — app env vars
- `~/src/superextra-landing/agent/.env` — agent env vars

## GCP firewall rules

| Rule                | Protocol | Ports       | Purpose         |
| ------------------- | -------- | ----------- | --------------- |
| `default-allow-ssh` | TCP      | 22          | SSH             |
| `allow-et`          | TCP      | 2022        | EternalTerminal |
| `allow-mosh`        | UDP      | 60000-61000 | mosh            |
| `allow-dev-server`  | TCP      | 5199        | Dev server      |

## Troubleshooting

| Problem                         | Fix                                                                                                                                                                                                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ET disconnected after sleep** | Usually auto-reconnects in 1-5s. If not, run `zxl` to rejoin — zmx session is still alive                                                                                                                                                                                                         |
| **mosh exits immediately**      | Check UDP ports 60000-61000 in GCP firewall. Verify locale: `locale -a \| grep en_US.utf8`                                                                                                                                                                                                        |
| **Stale SSH sockets**           | `rm ~/.ssh/sockets/*` (or just run `zx` — auto-clears)                                                                                                                                                                                                                                            |
| **Typing feels slow**           | ~65ms ping is normal. Check `CLAUDE_CODE_NO_FLICKER=1` is set. ET has no local echo — this is the hard floor                                                                                                                                                                                      |
| **zmx needs rebuilding**        | See `## zmx → Update procedure`. Requires Zig 0.15.2 at `/opt/zig/`                                                                                                                                                                                                                               |
| **zmx session lost**            | If zmx crashes, the Claude session dies (SIGHUP). Git-committed work is safe. Restart with `zx`                                                                                                                                                                                                   |
| **Mobile shows Mouse OFF**      | Stale tmux config. Kill tmux session (`txk <name>`), rejoin (`txj <name>`)                                                                                                                                                                                                                        |
| **VS Code SSH can't connect**   | Try `ssh superextra-vm` first. If VS Code updated, `rm -rf ~/.vscode-server/` on VM and reconnect                                                                                                                                                                                                 |
| **Claude not authenticated**    | Run `claude auth login` on VM                                                                                                                                                                                                                                                                     |
| **Mutagen not syncing**         | `mutagen sync list` for status. `mutagen sync flush` to force. `mutagen daemon start` if daemon died                                                                                                                                                                                              |
| **skhd not intercepting keys**  | macOS Accessibility won't list ad-hoc signed binaries. Wrap in .app: `/Applications/skhd.app/Contents/MacOS/skhd` (copy from brew cellar, add Info.plist with bundle ID `com.koekeishiya.skhd`). Update LaunchAgent to point to .app binary. Then add skhd.app in System Settings → Accessibility |
