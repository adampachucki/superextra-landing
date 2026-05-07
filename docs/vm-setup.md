# Remote VM Setup

GCP VM running Claude Code (and Codex) in persistent **tmux** sessions, accessible from any device. Commands like `x` (claude) and `c` (codex) start or attach to named sessions; both clients — Mac (over EternalTerminal) and iPhone (over mosh) — see the same tmux server and share state.

The previous version of this stack used **zmx** as a raw-PTY relay between clients and the AI process. zmx was removed on 2026-05-07 after a testing round showed every benefit it offered was either (a) already provided by other layers or (b) unreachable in practice. See [Decision history](#decision-history) for the full account.

---

## TL;DR

```
Mac (VS Code / Cursor)              iPhone (Moshi)
   │                                    │
   │ ET (TCP, port 2022)                │ mosh (UDP 60000–61000)
   ▼                                    ▼
        ──────────── GCP VM ────────────
                       │
                       ▼
                  tmux server
                   │       │
                   ▼       ▼
                claude   codex
              (one session per task)
```

| Command           | What it does                                               |
| ----------------- | ---------------------------------------------------------- |
| `x` / `x NAME`    | Create or attach to a tmux session running `claude`        |
| `c` / `c NAME`    | Create or attach to a tmux session running `codex` (Azure) |
| `x l` / `xl`      | List sessions, prompt for one to join                      |
| `x j NAME` / `xj` | Join (or create+attach) `NAME`                             |
| `x k NAME` / `xk` | Kill session `NAME` (tmux + any leftover zmx daemon)       |
| `x K` / `xK`      | Wipe all sessions on the VM (`tmux kill-server`)           |
| `c l/j/k/K`       | Same surface for codex sessions                            |

Sessions persist across all client disconnects. A session is destroyed only by `tmux kill-session -t NAME` (or `x k NAME`), the inner `claude`/`codex` process exiting, `tmux kill-server` (or `x K`), or VM reboot.

---

## Architecture

### Mac path

```
VS Code/Cursor terminal
  │ runs `et adam@…:2022` (via the `x` zshrc function)
  ▼
EternalTerminal (auto-reconnect TCP, persistent server-side bash)
  │
  ▼
bash on VM (sources ~/.bashrc, which loads ~/.secrets and ~/.zx-env)
  │ runs `_x_session NAME claude` from the `x` function
  ▼
tmux server on VM (creates session if missing, attaches client)
  │
  ▼
Pane process: `claude` (Claude Code TUI)
```

### Mobile path

```
Moshi app (iPhone)
  │ mosh UDP to 34.38.81.215
  ▼
mosh-server on VM (auto-spawned per connection)
  │ runs the user's login shell, which sources ~/.bashrc
  ▼
bash on VM (Moshi picker enumerates tmux sessions)
  │ tap a session → runs tmux attach -t NAME
  ▼
Same tmux server / same session as the Mac
```

The phone and the Mac connect to **the same tmux server**. Two clients on one session is supported by tmux natively (mirrored views, keystrokes from either client reach the pane). With `window-size latest` set in `~/.tmux.conf`, the most-recently-active client's terminal size wins, so switching from Mac to iPhone (or vice versa) triggers a one-time reflow on the other client.

---

## Why this setup

This section is the load-bearing one. Each component is here for a specific reason; equally importantly, several plausible-looking layers (zmx, Tailscale, plain SSH on Mac) have been tried and removed.

### tmux as the session layer

Mandatory. Two reasons:

1. **Survive client disconnect.** The tmux server holds the PTY and the inner process (claude/codex) regardless of whether any client is currently attached. Closing your laptop, killing Wi-Fi, putting the phone in airplane mode — none of these touch the session. The next attach picks up exactly where you left off.
2. **Moshi's session picker enumerates tmux sessions.** When you open the Moshi app on the phone, the picker connects via mosh, runs `tmux list-sessions`, and shows you that list. There is **no iOS terminal app that surfaces alternative session managers (like zmx) natively**. So tmux being in the path on mobile is non-negotiable; if you want a clickable list of running sessions on your phone, you need tmux.

### EternalTerminal on the Mac

Chosen over plain SSH and over mosh, both deliberately:

- **vs plain SSH:** ET keeps the bash PTY alive on the VM and silently reconnects after a network drop (laptop sleep, Wi-Fi flip, ISP hiccup). SSH dies on disconnect; you'd have to reattach manually each time.
- **vs mosh on the Mac:** mosh's "main feature" is a client-side terminal emulator with local echo and predictive typing — designed for high-latency cellular links. On a desktop with a stable connection, those features actively cause artifacts (especially with TUIs like claude). And mosh runs over UDP 60000–61000, requiring more open ports than ET's single TCP port.

ET has **no local echo** — typing has full round-trip latency (~30 ms intercontinental, fine in practice with Claude's no-flicker mode and GPU rendering).

### mosh on the iPhone

Chosen over SSH-only iOS clients:

- The phone is on cellular and roams between networks. mosh's UDP + IP roaming is exactly what you want here.
- The session-state-on-disconnect-and-resume behavior is built in.
- Local echo means typing feels instant despite RTT.

We tested SSH-only iOS clients (the third-party "Termux" on the App Store, etc.). They work for ad-hoc connects but die on every network blip. mosh + Moshi is the right shape for a phone.

### Tailscale isn't load-bearing

The VM has a public IPv4 (34.38.81.215). GCP firewall already allows ET (2022), SSH (22), and mosh (60000–61000) from `0.0.0.0/0`. Both Mac and phone can reach the VM directly without a VPN.

Tailscale **is** installed on the VM (and the phone has a Tailscale client). Its role is:

- DNS convenience (`ai-workstation` resolves to a tailnet IP without DNS plumbing)
- Backup access path if GCP firewall or public IPv4 ever break
- NAT traversal if the VM ever loses its public address

But the day-to-day flow doesn't require it. Verified 2026-05-07 by running the full mobile flow with Tailscale off — no functional difference.

### Why we removed zmx

Worth its own section, since this is the biggest recent simplification.

**What zmx was.** A raw-PTY relay session manager (`github.com/neurosnap/zmx`, written in Zig). Originally adopted because it solved one specific problem: native terminal scroll on the Mac. tmux's normal mode runs in the alternate-screen buffer, which prevents VS Code's xterm.js from scrolling its own scrollback (mouse wheel sends arrow keys to the alt-screen buffer instead of moving xterm.js's scrollback view). zmx, being a raw-PTY relay with no alternate screen, sidesteps this — output flows into xterm.js's real scrollback, mouse wheel and Cmd+F search work natively.

**Why that broke.** The mobile path needs tmux (Moshi picker requirement, see above). When tmux co-attaches to the same session as the Mac, it captures every byte the inner process emits into its own scrollback. From that moment on, every client sharing that session — including the Mac — is constrained by tmux's behavior even though tmux isn't in the Mac path. Worse, `CLAUDE_CODE_NO_FLICKER=1` (which keeps tmux scrollback clean by wrapping each TUI redraw in DECSET 2026 sync output) had to stay set for the mobile path, and tested unsetting on 2026-05-06 produced significant artifacts. So the Mac wasn't actually getting "native scroll" anyway — it was getting tmux-shaped scroll experience routed through zmx.

**The cost-benefit calculus that didn't work.** zmx was bringing:

- Build dependency (Zig 0.15.2, manual `zig build`)
- Local fork tracking (no GitHub fork, just a local branch that needed rebasing)
- A multi-month saga of resize-leader patches (`c863651` and friends), all eventually reverted upstream as resize storms vs no-op
- An entire ~95-line `~/.bashrc` shape with mode auto-detection (`zmx` vs `tmux`), background-tmux-wrapper races to make Moshi's picker see zmx sessions, and a creation-order pollution bug analyzed in `zmx-scroll-and-device-switching.md`

zmx's _only_ differentiator (native Mac scroll) wasn't reaching the user. Everything else it did — multi-client attach, named sessions, persistence across client disconnect — tmux already does, with a much smaller footprint and zero local maintenance.

**The migration.** 2026-05-07: replaced the entire `x` / `c` complex with a small `_x_session` helper that runs `tmux new-session -As NAME 'claude'` (or `codex`). Net deletion: ~100 LOC from `~/.bashrc`. zmx binary still present at `/usr/local/bin/zmx` so legacy zmx-wrapped sessions can drain naturally; will be removed once `zmx ls --short` shows zero sessions.

**When zmx would become valuable again:** if and only if an iOS terminal app starts surfacing zmx sessions natively the way Moshi surfaces tmux. There's no such client as of 2026-05-07.

### Why `CLAUDE_CODE_NO_FLICKER=1`

Always on. Without it, every SIGWINCH-triggered repaint Claude emits gets captured into tmux's scrollback, producing 2× doubling on every reconnect. With it, Claude wraps each TUI frame in DECSET 2026 (synchronized output), tmux treats the frame as atomic, and scrollback stays clean.

Tested unsetting on 2026-05-06: artifacts return immediately. Don't unset.

The same mechanism explains the other two `CLAUDE_CODE_*` env vars, which are quality-of-life flags (terminal title injection off, anonymous telemetry off).

---

## Commands

All defined in VM `~/.bashrc`. Mac side has a parallel `x` zshrc function that opens an ET shell to the VM and invokes the VM-side `x`.

### `x` and `c` — create / attach

| Invocation     | Behavior                                                                                 |
| -------------- | ---------------------------------------------------------------------------------------- |
| `x`            | New tmux session with a random pet-name (e.g. `fast-ant`), running `claude`              |
| `x NAME`       | If `NAME` exists, attach. Else create with `claude`.                                     |
| `c` / `c NAME` | Same as `x` but spawns `codex`. The VM's `~/.codex/config.toml` configures Azure Foundry |
| `x -z NAME`    | `-z` and `-t` are accepted as no-ops for muscle memory (legacy zmx/tmux mode flags)      |
| `x -t NAME`    | Same — no-op                                                                             |

When attached from inside an existing tmux client (e.g., Moshi's picker), `x NAME` switches to the named session via `tmux switch-client`. Otherwise it does `tmux attach`.

### `x l` / `xl` — list and join

Prints the tmux session list, prompts for a name to attach. Just typing a name attaches; typing a non-existent name _creates_ it (with claude). Ctrl+C / empty input cancels.

### `x j NAME` / `xj NAME` — join by name

Same as `x NAME` (the `j` is just for muscle memory). With no argument, falls through to `x l`.

### `x k NAME` / `xk NAME` — kill one session

```bash
tmux kill-session -t "=NAME"
zmx kill "NAME"   # only if zmx binary still on PATH
```

The defensive `zmx kill` cleans up legacy session daemons that may be lurking. Once zmx is uninstalled (Phase 4 below), this becomes a no-op via the `command -v zmx` guard.

### `x K` / `xK` — kill everything

```bash
zmx ls --short | xargs zmx kill   # only if zmx still installed
tmux kill-server
```

This wipes the entire tmux workspace on the VM. There is no whitelist. This VM's tmux usage is exclusively Claude/Codex sessions, so this is acceptable; if you ever start using tmux for unrelated work on the VM, you'd want to add a tagging mechanism. (Considered and rejected in the migration design — see `zmx-scroll-and-device-switching.md` Stack architecture review.)

### Mac-side aliases

Same names exist in `~/.zshrc` on the Mac. Behavior by subcommand:

- `x NAME` / `x j NAME` / `x` / `c NAME` etc. — open an ET shell to the VM and invoke the VM-side function, which lands inside the tmux session.
- `x l` / `c l` — SSH to the VM, run `tmux list-sessions -F '#{session_name}'`, prompt locally for a name, then recurse into `x j NAME`.
- `x k NAME` / `x K` (and `c k NAME` / `c K`) — SSH to the VM and delegate to the VM-side `x k` / `x K` via `bash -ic`. This shares the VM-side's `command -v zmx` guard so legacy zmx-daemon cleanup still happens transparently for as long as zmx is installed.
- `x iap [up|down|status]` — Mac-only, manages the IPv6-only fallback (see [IPv6-only network fallback](#ipv6-only-network-fallback) below).

### Keyboard shortcuts (VS Code / Cursor)

| Shortcut    | Action                                                                 |
| ----------- | ---------------------------------------------------------------------- |
| Cmd+Shift+X | New terminal → `x` on VM (Claude session)                              |
| Cmd+Shift+A | New terminal → `codex-az` locally (Mac-side codex against Azure)       |
| Cmd+Shift+B | New terminal → Claude BR profile (`claude-br` → Bedrock-routed Claude) |
| Cmd+Shift+R | Rename terminal tab                                                    |

Defined in `~/Library/Application Support/{Code,Cursor}/User/keybindings.json`. Two files structurally identical; mirror changes between them.

---

## Configuration files

### `~/.bashrc` (VM) — `x` / `c` definitions

Lives at lines ~130–185 of a 187-line file. Self-contained block. Excerpted:

```bash
[ -r ~/.zx-env ] && . ~/.zx-env
CVM_REPO="$HOME/src/superextra-landing"

_x_session() {
  local name="$1" cmd="$2"
  if ! tmux has-session -t "=$name" 2>/dev/null; then
    tmux new-session -d -s "$name" -c "$CVM_REPO" \
      -e CLAUDE_CODE_NO_FLICKER=1 \
      -e CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1 \
      -e CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      -e AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY" \
      "$cmd"
  fi
  if [ -n "$TMUX" ]; then tmux switch-client -t "=$name"
  else tmux attach -t "=$name"; fi
}

_xc() { … dispatcher: l/j/k/K/default … }

x() { _xc claude "$@"; }
c() { _xc codex  "$@"; }

xl() { x l; }   # (and xj, xk, xK, cl, cj, ck, cK similarly)
```

The `-e KEY=VALUE` flags inject env vars into the new tmux session because tmux's `update-environment` only auto-propagates a small set (DISPLAY, SSH\_\*, etc.). Anything else has to be passed explicitly.

The `-e AZURE_OPENAI_API_KEY="$AZURE_OPENAI_API_KEY"` line expands the variable from the calling bash's env (sourced from `~/.secrets`). It only matters when _creating_ a new session; attaching to an existing one doesn't re-pass it.

### `~/.zx-env` (VM) — Claude Code env vars

```bash
export CLAUDE_CODE_NO_FLICKER=1
export CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
```

Single source of truth for these three. Sourced by `~/.bashrc` so every interactive shell on the VM has them. Re-injected via `tmux new-session -e` because tmux server env can be stale and the pane process doesn't go through bash.

### `~/.secrets` (VM, mode 0600) — API keys

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=…
export AZURE_OPENAI_API_KEY=…
```

Sourced by `~/.bashrc` (line ~127). Mode 0600 keeps it readable only to the user. Not in git.

To add a new secret that needs to reach a tmux session, you have to do **both**:

1. Add `export FOO=…` to `~/.secrets`.
2. Add `-e FOO="$FOO"` to the `_x_session` tmux call in `~/.bashrc`.

Just step 1 isn't enough — your bash will have it but tmux panes won't.

### `~/.codex/config.toml` (VM) — Codex provider

```toml
model = "gpt-5.5"
model_provider = "azure"
model_reasoning_effort = "xhigh"

[model_providers.azure]
name = "Azure OpenAI"
base_url = "https://….cognitiveservices.azure.com/openai/v1"
env_key = "AZURE_OPENAI_API_KEY"
wire_api = "responses"
```

Note this puts Azure at the **top level** as the only provider. Plain `codex` on the VM uses Azure. (On the Mac, where multiple profiles exist, you'd need `codex --profile azure` — that's what the Mac's `codex-az` shell function wraps.)

Auth: codex looks up `AZURE_OPENAI_API_KEY` in its env (per the `env_key` line). That env var must be in the pane's env — see `_x_session` `-e` line.

### `~/.tmux.conf` (VM)

```tmux
set -g set-titles on
set -g set-titles-string "#S"
set -g mouse on
set -g escape-time 0
set -g window-size latest
set -g status off
set -g focus-events on

# Hide cursor on focus loss / show on focus gain
set-hook -g client-focus-out "run-shell -b 'printf \"\\033[?25l\" > #{client_tty}'"
set-hook -g client-focus-in  "run-shell -b 'printf \"\\033[?25h\" > #{client_tty}'"

set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",*256col*:RGB,*256col*:Tc"
set -g history-limit 50000

# Plugins (tpm)
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'nhdaly/tmux-better-mouse-mode'
set -g @scroll-speed-num-lines-per-scroll "1"
run '~/.tmux/plugins/tpm/tpm'
```

Notes:

- `mouse on` is required for scroll over mosh to work at all. **Don't** turn it off, even if you read advice that says it makes copy-paste fragile — selection works fine in Moshi.
- `window-size latest` sizes to the most recently active client. With Mac+iPhone both attached, the most recent typist's window size wins.
- `status off` hides the green tmux status bar at the bottom — pure space saving for iOS.

### `/etc/et.cfg` (VM) — EternalTerminal server

Standard ET server config. Listens on 2022, telemetry off.

Restart policy: a drop-in at `/etc/systemd/system/et.service.d/override.conf` sets `Restart=always`, `RestartSec=1s` so the service comes back within ~1 s on any exit.

### `/etc/ssh/sshd_config.d/keepalive.conf` (VM)

```
ClientAliveInterval 60
ClientAliveCountMax 3
TCPKeepAlive no
```

Effective interval is 120 s (vendor `50-cloudimg-settings.conf` drop-in sets 120 first; sshd is first-match-wins). Dead peers are reaped in ~6 min.

---

## Authentication

Different commands have very different auth models. Worth being explicit because the difference caused real debugging time during the 2026-05-07 migration.

| Command  | Auth provider   | Auth storage                         | How it reaches a tmux pane                                 |
| -------- | --------------- | ------------------------------------ | ---------------------------------------------------------- |
| `claude` | Anthropic OAuth | `~/.claude/.credentials.json` (0600) | Pane process reads file from disk on startup. No env var.  |
| `codex`  | Azure API key   | `~/.secrets` `AZURE_OPENAI_API_KEY`  | Must be in pane env. Propagated via `tmux new-session -e`. |

**To re-authenticate claude:** `claude auth login` from any shell on the VM. It writes a fresh OAuth token to the credentials file. Existing sessions keep working with the old token until it expires; new sessions pick up the new one.

**To rotate the codex Azure key:** edit `~/.secrets`, source it, restart any open codex sessions. The bashrc `-e` injection will pull the new value on next session create.

---

## Connection details

### ET (EternalTerminal)

- Server: systemd `et.service`, port 2022. Logs: `journalctl -u et.service`.
- Client: `brew install MisterTea/et/et` on Mac.
- Used for the Mac's day-to-day session. The `x` / `c` zshrc functions invoke `et` as their transport.

### mosh

- Server: `mosh-server` auto-spawned per connection from Moshi.
- Client: Moshi app on iPhone.
- Used for the phone's day-to-day session. The Moshi app embeds a tmux session picker that connects via mosh to the VM, runs `tmux ls`, and shows you the session list.

### SSH (background uses)

Direct SSH is used for non-interactive commands from the Mac (config pulls, file scp, the `vp` proxy when needed). Mac's `~/.ssh/config` for the host:

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

### GCP firewall rules

| Rule                | Protocol | Ports       | Purpose         |
| ------------------- | -------- | ----------- | --------------- |
| `default-allow-ssh` | TCP      | 22          | SSH             |
| `allow-et`          | TCP      | 2022        | EternalTerminal |
| `allow-mosh`        | UDP      | 60000–61000 | mosh            |
| `allow-dev-server`  | TCP      | 5199        | Dev server      |

All four allow `0.0.0.0/0` source. No VPN required for any client connection.

---

## IPv6-only network fallback

The VM's public IP `34.38.81.215` is IPv4-only. Some networks (notably some EU mobile/home ISPs) put the Mac on IPv6-only with no v4 default route — direct ET/SSH to the VM fails with "no route to host".

**Mechanism**: when v4 is unreachable, the Mac side adds `34.38.81.215` as a `/32` alias on `lo0` and binds a single `gcloud compute start-iap-tunnel` to that exact IP:port. The kernel routes traffic to the VM IP via lo0 → local gcloud listener → IAP → VM. Existing ET clients in already-open VS Code terminals reconnect transparently because their destination address didn't change.

**SSH bootstrap (for ET's spawned `ssh adam@34.38.81.215`)**: a `Match host superextra-vm,34.38.81.215 exec "ifconfig lo0 | grep 34.38.81.215"` block in `~/.ssh/config` activates only when the alias is present and overrides with `ProxyCommand gcloud compute start-iap-tunnel ai-workstation %p --listen-on-stdin --zone=europe-west1-b --quiet`. No long-lived SSH tunnel needed.

This is entirely a Mac-side concern; the VM has no equivalent infrastructure.

### Mac-side IAP commands

- `x` / `xl` / `xj` etc. — same session API as in v4-direct mode; `_x_route` auto-engages IAP fallback when needed.
- `x iap status` / `x iap up` / `x iap down` — manage the lo0 alias + tunnel manually. `up` prompts for admin auth (TouchID-capable via osascript when there's no TTY). State files: `/tmp/x-iap.{pid,log}`.
- `vp up` / `vp down` — opens/closes a SOCKS5 (`localhost:1080`) and HTTP CONNECT (`localhost:1081`) proxy through the VM, for tools that need to reach IPv4-only services from an IPv6-only network. The HTTP CONNECT side runs a stdlib Python proxy at `~/bin/codex-connect-proxy.py` on the VM.
- `codex-az` — local Mac codex command; auto-engages `HTTPS_PROXY=http://localhost:1081` when on IPv6-only.

### Auto-transition (launchd watcher)

`~/bin/x-netchange.sh`, registered as a user agent at `~/Library/LaunchAgents/co.pachucki.x-netchange.plist`, fires on macOS `com.apple.system.config.network_change` notifications. On each fire:

- Acts only when `v4_default` route presence flips, OR when a state mismatch is detected (alias present while v4 default route is also present — likely an orphan from a failed `iap_up`).
- On `iap → v4_direct` transition: tears down `vp` (SOCKS+HTTP CONNECT) before dropping the SSH ControlMaster, so `ssh -O cancel` can reach it. Then bounces the `superextra-vm-sync` mutagen session.
- On `iap_up` failure (e.g. gcloud auth blip, cold-start timeout): rolls back the half-set alias rather than stranding traffic at a dead lo0 socket.

`/etc/sudoers.d/x-iap-lo0` whitelists `ifconfig lo0 alias 34.38.81.215/32` and `ifconfig lo0 -alias 34.38.81.215` NOPASSWD so the watcher can flip routing without prompting.

---

## VS Code / Cursor

### Terminal profiles

Both editors, in `settings.json` under `terminal.integrated.profiles.osx`:

- `zsh` (default) — regular shell, sources `~/.zshrc` which defines `x`
- `Claude` — runs `claude; exec zsh`
- `Claude BR` — runs `claude-br; exec zsh` (Bedrock-routed Claude)
- `Codex Azure` — runs `codex-az; exec zsh` (used by Cmd+Shift+A)

### Terminal performance settings

| Setting                                        | Value   | Why                                                               |
| ---------------------------------------------- | ------- | ----------------------------------------------------------------- |
| `terminal.integrated.gpuAcceleration`          | `on`    | WebGL rendering, fastest on Retina                                |
| `terminal.integrated.smoothScrolling`          | `false` | No animation delay                                                |
| `terminal.integrated.localEchoEnabled`         | `off`   | Tested and rejected — causes visual artifacts with the Claude TUI |
| `terminal.integrated.shellIntegration.enabled` | `false` | Prevents relaunch warnings                                        |

If terminal scrolling ever feels too fast, the tuning knob is `terminal.integrated.mouseWheelScrollSensitivity` (default 1.0; lower = slower). It's global — applies to every terminal.

---

## Performance tuning

### VM TCP (`/etc/sysctl.conf`)

- `net.ipv4.tcp_congestion_control=bbr` — better latency than cubic
- `net.ipv4.tcp_autocorking=0` — sends keystrokes immediately
- `net.ipv4.tcp_slow_start_after_idle=0` — keeps connection warm
- `net.ipv4.tcp_mtu_probing=1` — survives PMTU blackholes without stalling
- `net.core.default_qdisc=fq` — Fair Queue for BBR

### macOS TCP

- `sudo sysctl -w net.inet.tcp.delayed_ack=0` — immediate ACKs (persistent via LaunchDaemon)
- `sudo sysctl -w net.inet.tcp.mssdflt=1448` — proper Ethernet MSS

---

## Mutagen file sync

Bidirectional sync between VM and a local mirror folder. Claude/Codex edits on the VM appear instantly in local VS Code.

| Folder                                  | Purpose                                     |
| --------------------------------------- | ------------------------------------------- |
| `~/src/superextra-landing`              | Real local repo — no sync                   |
| `~/src/superextra-landing-vm`           | Mutagen mirror — bidirectional sync with VM |
| VM: `/home/adam/src/superextra-landing` | The remote repo where Claude works          |

Session: `superextra-vm-sync`, mode `two-way-safe`. `.git` IS synced. Daemon auto-starts on boot.

| Command                                 | Action                         |
| --------------------------------------- | ------------------------------ |
| `mutagen sync list`                     | Show sync status and conflicts |
| `mutagen sync flush`                    | Force immediate sync           |
| `mutagen sync reset superextra-vm-sync` | Reset if stuck                 |

Mutagen daemon LaunchAgent: `~/Library/LaunchAgents/io.mutagen.mutagen.plist` (auto-started on login).

---

## Screenshots

Cmd+Shift+1 on Mac captures a screenshot, uploads via SCP to `/home/adam/screenshots/` on VM, copies the path to clipboard. Paste into Claude Code to share images. Implementation: `~/.local/bin/screenshot-to-vm` (Mac), bound by skhd at `~/.config/skhd/skhdrc`.

---

## VM details

|           |                                                     |
| --------- | --------------------------------------------------- |
| Host      | `adam@34.38.81.215` (static IP)                     |
| Tailnet   | `ai-workstation` / `100.101.35.72`                  |
| Machine   | GCP g2-standard-4, Belgium (europe-west1-b)         |
| OS        | Ubuntu 24.04                                        |
| Repo      | `~/src/superextra-landing`                          |
| Node      | 22 (via nvm at `~/.nvm/versions/node/v22.22.2/`)    |
| Python    | 3.12 (agent venv at `agent/.venv/`)                 |
| Env files | `.env`, `agent/.env` — gitignored, created manually |

### What's installed

- Node 22, Python 3.12, Docker, **mosh**, **tmux 3.4**, gcloud CLI
- **EternalTerminal** 6.2.10 (systemd service)
- **Claude Code** at `~/.nvm/versions/node/v22.22.2/bin/claude`
- **Codex CLI** at `~/.nvm/versions/node/v22.22.2/bin/codex`
- **Tailscale** (running on VM only — backup access path)
- **MCP servers**: GitHub (npx), Svelte, Miro, Apify
- **zmx** (still on disk at `/usr/local/bin/zmx` for legacy session drainage; will be removed when no zmx daemons remain)

### Config files on VM (the canonical list)

| Path                                    | Purpose                                             |
| --------------------------------------- | --------------------------------------------------- |
| `~/.bashrc`                             | `x` / `c` definitions, sources `.zx-env`/`.secrets` |
| `~/.zx-env`                             | `CLAUDE_CODE_*` env vars                            |
| `~/.secrets`                            | API keys (mode 0600)                                |
| `~/.tmux.conf`                          | tmux config                                         |
| `~/.codex/config.toml`                  | Codex provider config (Azure)                       |
| `~/.claude/.credentials.json`           | Claude OAuth token (mode 0600)                      |
| `~/.claude.json`                        | MCP server config                                   |
| `/etc/et.cfg`                           | ET server config                                    |
| `/etc/ssh/sshd_config.d/keepalive.conf` | sshd keepalives                                     |
| `~/src/superextra-landing/.env`         | App env vars                                        |
| `~/src/superextra-landing/agent/.env`   | Agent env vars                                      |

---

## Operations

### Adding a new env var that needs to reach claude/codex

Two-step:

1. Add it to `~/.zx-env` (if it's a Claude config knob) or `~/.secrets` (if it's a credential). Both are sourced by `~/.bashrc`.
2. Add a `-e VAR="$VAR"` line inside `_x_session` in `~/.bashrc` so tmux passes it into new panes.

If you skip step 2, your bash will see the var but `claude`/`codex` running in the tmux pane won't.

### Cleaning up stale sessions

```bash
tmux ls                      # see what's there
x k SESSION-NAME             # kill one
x K                          # nuke all sessions on the VM
```

### Inspecting a session non-destructively

```bash
tmux capture-pane -p -t '=NAME' | tail -50      # last 50 lines of pane content
tmux list-sessions -F '#{session_name} cwd=#{pane_current_path} cmd=#{pane_current_command}'
```

### Updating Claude Code or Codex CLI

Both are nvm-installed npm packages.

```bash
# On VM, in any interactive bash:
npm install -g @anthropic-ai/claude-code   # claude
npm install -g @openai/codex                # codex
```

Existing sessions keep running the old binary; new sessions get the new one.

### Removing zmx entirely (Phase 4 of the migration)

When `zmx ls --short` returns empty (all legacy sessions drained):

```bash
sudo rm /usr/local/bin/zmx /usr/local/bin/zmx.bak-*
rm -rf ~/src/zmx
```

The `command -v zmx` guards in `_x_session` and the kill paths will then no-op, and the `zmx`-related code becomes dormant. Rollback: copy back any retained backup binary.

---

## Troubleshooting

| Problem                                                                  | Fix                                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ET disconnected after sleep**                                          | Usually auto-reconnects in 1–5 s. If not, run `xl` to rejoin — tmux session is still alive.                                                                                                                                                                      |
| **mosh exits immediately**                                               | Check UDP ports 60000–61000 in GCP firewall. Verify locale: `locale -a                                                                                                                                                                                           | grep en_US.utf8`.                                                                                                                                                               |
| **Stale SSH sockets**                                                    | `rm ~/.ssh/sockets/*` (or just run `x` — auto-clears).                                                                                                                                                                                                           |
| **Typing feels slow**                                                    | ~65 ms ping is normal. ET has no local echo — that's the hard floor. Verify `CLAUDE_CODE_NO_FLICKER=1` is set on the live process: `tr '\\0' '\\n' < /proc/<pid>/environ                                                                                         | grep FLICKER`.                                                                                                                                                                  |
| **Claude not authenticated**                                             | Run `claude auth login` on the VM. New token → all new sessions pick it up.                                                                                                                                                                                      |
| **Codex says "Error loading configuration: config profile X not found"** | The VM's `~/.codex/config.toml` puts Azure at the top level, not under `[profiles.azure]`. Plain `codex` is correct on the VM. If you typed `codex --profile azure` directly, drop the flag. (Mac codex uses the flag because Mac config has multiple profiles.) |
| **Codex starts but immediately fails to authenticate**                   | `AZURE_OPENAI_API_KEY` not in pane env. Run `echo "$AZURE_OPENAI_API_KEY"                                                                                                                                                                                        | wc -c`in the offending pane — if zero/empty, the bashrc`-e`injection didn't fire (maybe session was created before the key was in`~/.secrets`). Recreate: `x k NAME && c NAME`. |
| **Mobile shows Mouse OFF**                                               | Stale tmux config. Kill the affected session (`xk NAME`), rejoin (`xj NAME`).                                                                                                                                                                                    |
| **Mac shows stale content from other device after switching**            | Known Ink/SIGWINCH bug; full analysis in [zmx-scroll-and-device-switching.md](zmx-scroll-and-device-switching.md). No clean fix at our layer — conversation content lives in Ink `<Static>` and cannot be safely wiped.                                          |
| **Mobile tmux shows duplicate session content mid-session**              | Cross-device size mismatch triggers Claude repaints at Mac size into mobile-sized tmux panes. Same upstream root cause as above.                                                                                                                                 |
| **VS Code / Cursor SSH can't connect**                                   | Try `ssh superextra-vm` first. If editor was just updated, `rm -rf ~/.vscode-server/` on VM and reconnect.                                                                                                                                                       |
| **Mutagen not syncing**                                                  | `mutagen sync list` for status. `mutagen sync flush` to force. `mutagen daemon start` if daemon died.                                                                                                                                                            |
| **Old `zx` / `tx` / `cv` commands not found**                            | All renamed to `x` / `c` long ago. `zx foo` → `x foo`, `zxl` → `xl`, `txj` → `xj`, `cv-codex` → `c`. Mode flags `-z` / `-t` are still accepted as no-ops.                                                                                                        |
| **`x K` killed sessions I wanted to keep**                               | `x K` runs `tmux kill-server` — it's intentionally a wipe. There is no whitelist. Kill specific sessions with `x k NAME` instead.                                                                                                                                |

---

## Decision history

A condensed log of stack changes and rationale, newest first. Read this when you're considering a structural change — chances are it's been tried.

### 2026-05-07 — Mac zshrc: stop enumerating sessions via zmx

- Mac-side `x l` / `x k` (no-arg) / `x K` (and the `c` siblings) were still calling `ssh ... "zmx list --short"` to enumerate sessions. Post-VM-zmx-drop, that returned empty — so list/kill-picker/kill-all silently no-op'd.
- Replaced with `tmux list-sessions -F '#{session_name}'` for listing and `bash -ic 'x k …' / 'x K'` delegation for kills (delegates to VM-side, which already has the proper `command -v zmx` guard).
- Extracted the picker logic into `_x_pick_remote` shared by `x` and `c`. Net `~/.zshrc` LOC: 304 → 283.

### 2026-05-07 — Drop zmx; unify `x` and `c` over a shared helper

- Removed: `zmx attach …` from session creation; `_x_detect_mode`, `_x_ensure_tmux`, `_x_pick`, `_x_attach`; mode-detection logic; background-tmux-wrapper-spawn race.
- Added: `_x_session NAME CMD` helper; `_xc CMD ARGS…` dispatcher; thin wrappers `x() { _xc claude "$@"; }` and `c() { _xc codex "$@"; }`.
- Net `~/.bashrc` LOC: 287 → 186 (–101).
- **Why**: tmux is mandatory anyway (Moshi picker), zmx's "native scroll" benefit was unreachable in practice, the ongoing Zig-build / fork-tracking / resize-leader-patch saga was paying for nothing. See "Why we removed zmx" above.
- **Migration**: surgical bashrc edit; current zmx-wrapped sessions kept running until naturally drained. zmx binary still on disk for legacy-session cleanup.

### 2026-05-07 — Add `AZURE_OPENAI_API_KEY` propagation

- Added one `-e` line in `_x_session`. Without it, `codex` panes had no API key and crashed silently.
- **Why**: tmux's `update-environment` only auto-propagates DISPLAY, SSH*\*, etc. Custom env vars from `~/.secrets` need explicit `-e` injection — same pattern already used for `CLAUDE_CODE*\*`.
- **Implication**: this is the canonical pattern for any future env var that needs to reach a tmux pane. See "Adding a new env var" in Operations.

### 2026-04-29 — Add `vp` proxy, `x-netchange.sh` watcher

- Added the SOCKS5 / HTTP CONNECT proxy through the VM (for codex's Azure access from IPv6-only Mac networks) and the launchd watcher for automatic v4↔v6 transitions.
- **Why**: Mac on IPv6-only nets needed a way to reach Azure cognitive services even when also reaching the VM via IAP. SOCKS5 didn't suffice for codex 0.125's reqwest (which honors `HTTPS_PROXY=http://...` but not `socks5h://`).

### 2026-04-22 — Unify `zx` and `tx` into a single `x` function

- Removed: `zx`, `zxl`, `zxj`, `zxk`, `zxK` and their `tx*` siblings.
- Added: single `x` function with auto-mode-detection (`zmx` from ET, `tmux` from mosh-server) and `-z` / `-t` overrides.
- Same surgery applied to codex side: `cv-codex` and family → `c`.
- **Why**: two parallel command families with identical surface but different inner mechanics caused mode confusion. Single command, mode auto-detected from parent process, removed the foot-gun.
- **2026-05-07 update**: with zmx gone, mode auto-detection is moot. The auto-detect helpers were deleted. The `-z` / `-t` flags survive as accepted no-ops to preserve muscle memory.

### 2026-04-18 — Drop the local `c863651` resize-leader patch from zmx

- Removed: local-only patch that auto-promoted any resizing client to leader.
- **Why**: caused per-keystroke resize storms (each keystroke triggered leader change → PTY resize → Claude SIGWINCH → full repaint broadcast → mobile tmux scrollback pollution) without reliably delivering the "switch device by typing" outcome it was meant to enable. Pure upstream zmx had cleaner behavior.
- **2026-05-07 follow-up**: zmx itself is now gone, making this entire codepath irrelevant.

### Older history

See [zmx-scroll-and-device-switching.md](zmx-scroll-and-device-switching.md) for the detailed postmortem of the zmx-era scroll/resize/multi-device debugging session (2026-04-17). It's preserved as historical context for why the architecture review concluded zmx had to go.
