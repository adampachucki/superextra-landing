# Remote VM Setup

## What

A GCP VM (g2-standard-4, Belgium) running Claude Code, accessible from any device. Claude runs in persistent zmx sessions on the VM — start a session from your Mac, pick it up from your phone. One command (`x`) drives everything, auto-detecting whether to attach via zmx-direct (Mac over ET) or tmux-wrapped (mobile over mosh).

## Why

- **Always-on sessions** — Claude keeps working after you close the laptop
- **Multi-device** — same session from Mac (VS Code / Cursor terminal) and phone (Moshi app)
- **Smooth Mac scroll** — `CLAUDE_CODE_NO_FLICKER=1` + DECSET 2026 sync output keeps VS Code / Cursor terminal scrollback clean (not strictly "native", but close; see [Scroll](#scroll) below)
- **Parallel work** — multiple Claude sessions on different tasks simultaneously
- **Fast reconnect** — ET auto-reconnects after sleep/wake, mosh survives roaming

## Architecture

```
Mac (VS Code / Cursor terminal)              Mobile (Moshi app)
  ↓ ET (TCP, port 2022)                        ↓ mosh (UDP)
GCP VM (34.38.81.215)                        GCP VM
  ↓                                            ↓
zmx session ← smooth scroll via xterm.js    tmux session (scroll wrapper)
  ↓                                            ↓ zmx attach
Claude Code                                  same zmx session → Claude Code
```

**zmx** owns the process. **tmux** is a thin scroll wrapper only used on mobile (mosh breaks xterm.js-level scrollback). Both devices connect to the same zmx session.

### Scroll

- **Mac**: ET forwards raw bytes, zmx is a raw pty relay (doesn't use alternate screen), so VS Code / Cursor's xterm.js scrollback works. Claude Code runs with `CLAUDE_CODE_NO_FLICKER=1`, which wraps each TUI frame in DECSET 2026 sync output so redraws don't pollute scrollback.
- **Mobile**: tmux mouse mode scrolls tmux's own history (not xterm.js's). `NO_FLICKER` still matters — without it, every SIGWINCH-triggered repaint Claude emits gets captured into tmux scrollback (producing 2× doubling on every reconnect); with it, frames are atomic and scrollback stays clean.

### Why not just tmux on Mac?

tmux uses the alternate screen buffer, which causes VS Code / Cursor's xterm.js to convert scroll wheel events into arrow key sequences. This is hardcoded in xterm.js — no setting can fix it. zmx avoids this by never entering alternate screen.

### Why ET over SSH/mosh on Mac?

- **vs SSH**: ET auto-reconnects after laptop sleep (1-5 s). SSH connections die.
- **vs mosh**: ET is a raw byte pipe — scrollback works in xterm.js. Mosh runs a terminal emulator that re-renders, breaking xterm.js-level scrollback.
- **Trade-off**: ET has no local echo (unlike mosh), so typing has ~130 ms round-trip latency. GPU rendering in the terminal + Claude Code's no-flicker mode mitigate the visual impact.

## Session commands

One command: `x`. Mode auto-detected from context; override with `-z` / `-t` if needed.

### Mode detection

| Invoked from                                  | Detected mode | Attach behavior         |
| --------------------------------------------- | ------------- | ----------------------- |
| Inside an existing tmux session (`$TMUX` set) | `tmux`        | `tmux switch-client`    |
| Under `mosh-server` (mobile via Moshi)        | `tmux`        | `tmux attach` (creates) |
| ET / SSH / local console                      | `zmx`         | `zmx attach` direct     |

Detection is `ps -o comm= -p $PPID` — checks if the parent process is `mosh-server`; if `$TMUX` is already set, always uses tmux mode.

### Commands

Defined in Mac `~/.zshrc` and VM `~/.bashrc`. Both sides share the same interface; Mac's `x` runs locally for list/kill housekeeping (via SSH) and tunnels through ET for attach/create.

| Command       | Action                                                      |
| ------------- | ----------------------------------------------------------- |
| `x`           | Create session with a random name, attach in the right mode |
| `x <name>`    | Create or attach to `<name>`                                |
| `x j <name>`  | Join `<name>` (auto-creates tmux wrapper if missing)        |
| `x l` / `xl`  | List sessions, pick one to join                             |
| `x k <name>`  | Kill session (both zmx + tmux)                              |
| `xk`          | List + pick to kill                                         |
| `xK`          | Kill all sessions                                           |
| `x -z <name>` | Force zmx-direct mode (override auto-detect)                |
| `x -t <name>` | Force tmux-wrapped mode (override auto-detect)              |

**Keyboard shortcut:** Cmd+Shift+X in VS Code / Cursor opens a terminal and runs `x`.

### Moshi picker visibility

When you run `x <name>` on Mac (zmx-direct mode), the command also spawns a detached tmux wrapper on the VM in the background (~0.3–3 s after zmx session creation). This makes the session appear in Moshi's picker without needing to first do a mobile "join" step. On mobile, `x` in tmux mode creates the wrapper synchronously as part of attach.

### Cross-device workflow

1. Create from Mac: `x my-task` → zmx session + detached tmux wrapper on VM
2. Open Moshi on phone → picker shows `my-task` → tap to attach via tmux
3. Or from mobile first: `x my-task` → same topology, attach via tmux
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

Used for non-interactive commands (listing/killing sessions from Mac).

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

Key optimizations: `ObscureKeystrokeTiming no` (disables 20 ms delay), `Ciphers aes128-gcm` (hardware AES), `ControlMaster` (connection reuse).

## IPv6-only network fallback

The VM's public IP `34.38.81.215` is IPv4-only. Some networks (notably some EU mobile/home ISPs) put the Mac on IPv6-only with no v4 default route — direct ET/SSH to the VM fails with "no route to host".

**The mechanism**: when v4 is unreachable, add `34.38.81.215` as a `/32` alias on `lo0` and bind a single `gcloud compute start-iap-tunnel` to that exact `IP:port`. The kernel routes traffic to the VM IP via lo0 → local gcloud listener → IAP → VM. Existing ET clients in already-open VS Code terminals reconnect transparently because their destination address didn't change.

**SSH bootstrap (for ET's spawned `ssh adam@34.38.81.215`)**: a `Match host superextra-vm,34.38.81.215 exec "ifconfig lo0 | grep 34.38.81.215"` block in `~/.ssh/config` activates only when the alias is present and overrides with `ProxyCommand gcloud compute start-iap-tunnel ai-workstation %p --listen-on-stdin --zone=europe-west1-b --quiet`. No long-lived SSH tunnel needed.

### Mac commands

- `x` / `xl` / `xj` / `xk` / `xK` — same session API as in v4-direct mode; `_x_route` auto-engages IAP fallback when needed.
- `x iap status` / `x iap up` / `x iap down` — manage the lo0 alias + tunnel manually. `up` prompts for admin auth (TouchID-capable via osascript when there's no TTY). State files: `/tmp/x-iap.{pid,log}`.
- `vp up` — opens a SOCKS5 (`localhost:1080`) and HTTP CONNECT (`localhost:1081`) proxy through the VM, for tools that need to reach IPv4-only services like Azure cognitive services from an IPv6-only network. The HTTP CONNECT side runs a stdlib Python proxy at `~/bin/codex-connect-proxy.py` on the VM.
- `codex-az` — auto-engages `HTTPS_PROXY=http://localhost:1081` when on IPv6-only (codex's reqwest honors HTTPS_PROXY for HTTP CONNECT but ignores SOCKS).

### Auto-transition (launchd watcher)

`~/bin/x-netchange.sh`, registered as a user agent at `~/Library/LaunchAgents/co.pachucki.x-netchange.plist`, fires on macOS `com.apple.system.config.network_change` notifications. On each fire:

- Acts only when `v4_default` route presence flips, OR when a state mismatch is detected (alias present while v4 default route is also present — likely an orphan from a failed `iap_up`).
- On `iap → v4_direct` transition: tears down `vp` (SOCKS+HTTP CONNECT) before dropping the SSH ControlMaster, so `ssh -O cancel` can reach it. Then bounces the `superextra-vm-sync` mutagen session.
- On `iap_up` failure (e.g. gcloud auth blip, cold-start timeout): rolls back the half-set alias rather than stranding traffic at a dead lo0 socket.

`/etc/sudoers.d/x-iap-lo0` whitelists `ifconfig lo0 alias 34.38.81.215/32` and `ifconfig lo0 -alias 34.38.81.215` NOPASSWD so the watcher can flip routing without prompting.

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

### VS Code / Cursor terminal

Both editors should mirror this config. The full set lives in `~/Library/Application Support/{Code,Cursor}/User/settings.json`.

| Setting                                        | Value   | Why                                                           |
| ---------------------------------------------- | ------- | ------------------------------------------------------------- |
| `terminal.integrated.gpuAcceleration`          | `on`    | WebGL rendering, fastest on Retina                            |
| `terminal.integrated.smoothScrolling`          | `false` | No animation delay                                            |
| `terminal.integrated.localEchoEnabled`         | `off`   | Tested and rejected — causes visual artifacts with Claude TUI |
| `terminal.integrated.defaultProfile.osx`       | `zsh`   | Required for `x` commands                                     |
| `terminal.integrated.shellIntegration.enabled` | `false` | Prevents relaunch warnings                                    |

If terminal scrolling ever feels too fast in x sessions specifically, the tuning knob is `terminal.integrated.mouseWheelScrollSensitivity` (default 1.0; lower = slower). Note that it's global — applies to every terminal, not just x sessions.

### Claude Code env

Single source of truth at `~/.zx-env` on the VM:

```bash
export CLAUDE_CODE_NO_FLICKER=1
export CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
```

Propagation paths (must all stay in sync — all read the same file):

- **VM `~/.bashrc`** sources `~/.zx-env` at the top → every interactive shell on the VM (SSH, ET, local console, tmux panes opened by hand) has the vars.
- **Mac `~/.zshrc` `CVM_ET()`** sources `~/.zx-env` over ET before running the command → ET's non-interactive shell gets the vars (bashrc doesn't fire in non-interactive mode).
- **`x()` tmux mode** passes the vars as `tmux new-session -e KEY=VALUE` → new tmux sessions get them even if the tmux server env is stale.

## zmx

Session manager that replaced tmux for the Mac path. Raw pty relay — doesn't use alternate screen.

- **Binary**: `/usr/local/bin/zmx` (root-owned, installed via `sudo install`)
- **Source**: `~/src/zmx` — upstream `github.com/neurosnap/zmx` (no GitHub fork)
- **Build requires**: Zig 0.15.2 (installed at `/opt/zig/`)
- **Logs**: `/run/user/1001/zmx/logs/`
- **Leader policy**: upstream uses `util.isUserInput()` (libghostty ANSI parser) to promote on deliberate user input — typing, arrow keys, etc. — and intentionally excludes focus / mouse events to avoid leader-thrashing. **As of 2026-04-18 we run pure upstream — no local patches.** The previous local `promote-on-resize` patch was removed because it caused resize storms that degraded the multi-client experience without reliably delivering the "switch device without typing" outcome it was meant to enable.
- **Known issues with scroll / device-switching artifacts**: see [zmx-scroll-and-device-switching.md](zmx-scroll-and-device-switching.md). Read before investigating the scroll / resize path.

### Source state

- `main` tracks `origin/main`. **No local branches, no local patches.** Just keep it fast-forwarded.
- Previous local branch `local-leader-fixes` and its standalone patch diff were removed on 2026-04-18 (see docs/zmx-scroll-and-device-switching.md for history).

### Update procedure

```bash
cd ~/src/zmx
git checkout main && git pull --ff-only
zig build -Doptimize=ReleaseSafe
sudo cp /usr/local/bin/zmx /usr/local/bin/zmx.bak-$(date +%Y%m%d)
sudo install -m 755 -o root -g root zig-out/bin/zmx /usr/local/bin/zmx
```

Replacing the binary does **not** kill running zmx daemons — only new `zmx attach` invocations pick up the new binary. Safe mid-session.

### Rollback

```bash
sudo cp /usr/local/bin/zmx.bak-v0.4.2-20260418 /usr/local/bin/zmx
# or any other timestamped backup under /usr/local/bin/zmx.bak-*
```

## tmux config (`~/.tmux.conf` on VM)

Only used as the mobile scroll wrapper. Minimal config:

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

**Note on env propagation:** this config doesn't list Claude Code env vars in `update-environment`; we don't rely on tmux server env being fresh. The `x` function's tmux mode injects `CLAUDE_CODE_*` directly via `tmux new-session -e`. A historical tmux-server-env drift caused Claude spawned via `tx` on mobile to miss `NO_FLICKER` and produce doubling scrollback; the `-e` injection is the fix.

## VS Code and Cursor

### Keyboard shortcuts (both editors)

| Shortcut    | Action                                  |
| ----------- | --------------------------------------- |
| Cmd+Shift+X | New terminal + `x` (create zmx session) |
| Cmd+Shift+B | Claude BR terminal profile              |
| Cmd+Shift+R | Rename terminal tab                     |

Keybindings live in `~/Library/Application Support/{Code,Cursor}/User/keybindings.json`. The two files are structurally identical — same keys and commands — so changes need mirroring between them.

### Terminal profiles

Both editors have these profiles in `settings.json` under `terminal.integrated.profiles.osx`:

- `zsh` (default) — regular shell, sources `~/.zshrc` which defines `x`
- `Claude` — runs `claude; exec zsh`
- `Claude BR` — runs `claude-br; exec zsh` (Bedrock-routed Claude)

VS Code has an additional `bash` profile; Cursor doesn't. Add it if you need it.

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

- `~/.bashrc` — sources `~/.zx-env`, defines `x` function and helpers (`_x_detect_mode`, `_x_ensure_tmux`, `_x_attach`, `_x_pick`) + `xl/xj/xk/xK` aliases
- `~/.zx-env` — Claude Code env vars (single source of truth)
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

| Problem                                                       | Fix                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ET disconnected after sleep**                               | Usually auto-reconnects in 1-5 s. If not, run `xl` to rejoin — zmx session is still alive                                                                                                                                                                                                         |
| **mosh exits immediately**                                    | Check UDP ports 60000-61000 in GCP firewall. Verify locale: `locale -a \| grep en_US.utf8`                                                                                                                                                                                                        |
| **Stale SSH sockets**                                         | `rm ~/.ssh/sockets/*` (or just run `x` — auto-clears)                                                                                                                                                                                                                                             |
| **Typing feels slow**                                         | ~65 ms ping is normal. Check `CLAUDE_CODE_NO_FLICKER=1` is set on the live process: `tr '\\0' '\\n' < /proc/<pid>/environ \| grep FLICKER`. ET has no local echo — this is the hard floor                                                                                                         |
| **zmx needs rebuilding**                                      | See `## zmx → Update procedure`. Requires Zig 0.15.2 at `/opt/zig/`                                                                                                                                                                                                                               |
| **zmx session lost**                                          | If zmx crashes, the Claude session dies (SIGHUP). Git-committed work is safe. Restart with `x`                                                                                                                                                                                                    |
| **Mobile shows Mouse OFF**                                    | Stale tmux config. Kill tmux session (`xk <name>`), rejoin (`xj <name>`)                                                                                                                                                                                                                          |
| **Mobile scrollback doubles on every reopen**                 | Historical — root cause was `CLAUDE_CODE_NO_FLICKER` missing from Claude's env for tx-created sessions (tmux server env had drifted stale). Fixed by sourcing `~/.zx-env` from `~/.bashrc` + injecting via `tmux new-session -e`. Existing polluted sessions stay polluted until recreated        |
| **VS Code / Cursor SSH can't connect**                        | Try `ssh superextra-vm` first. If editor updated, `rm -rf ~/.vscode-server/` on VM and reconnect                                                                                                                                                                                                  |
| **Claude not authenticated**                                  | Run `claude auth login` on VM                                                                                                                                                                                                                                                                     |
| **Mutagen not syncing**                                       | `mutagen sync list` for status. `mutagen sync flush` to force. `mutagen daemon start` if daemon died                                                                                                                                                                                              |
| **Mac shows stale content from other device after switching** | Known Ink/SIGWINCH bug; see [zmx-scroll-and-device-switching.md](zmx-scroll-and-device-switching.md) §2. No clean zmx-layer fix — conversation content lives in Ink `<Static>` and cannot be safely wiped                                                                                         |
| **Mobile tmux shows duplicate session content mid-session**   | Separate issue from the reopen-doubling bug above. Cross-device size mismatch triggers Claude repaints at Mac size into mobile-sized tmux panes. See [zmx-scroll-and-device-switching.md](zmx-scroll-and-device-switching.md) §3. No clean fix — upstream Claude Code / Ink                       |
| **New `zx`/`tx` session commands not found**                  | Those were renamed on 2026-04-22 — everything is `x` now. `zx foo` → `x foo`, `zxl` → `xl`, `txj` → `xj`, etc. Mode auto-detects from parent process                                                                                                                                              |
| **Cursor terminal scrolls too fast in x sessions**            | Add `terminal.integrated.mouseWheelScrollSensitivity: 0.5` (or lower) to Cursor settings. Applies globally to all terminals. Setting `smoothScrolling: false` alone is usually enough                                                                                                             |
| **skhd not intercepting keys**                                | macOS Accessibility won't list ad-hoc signed binaries. Wrap in .app: `/Applications/skhd.app/Contents/MacOS/skhd` (copy from brew cellar, add Info.plist with bundle ID `com.koekeishiya.skhd`). Update LaunchAgent to point to .app binary. Then add skhd.app in System Settings → Accessibility |
