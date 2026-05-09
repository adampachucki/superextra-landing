# Remote VM Setup

GCP VM running Claude Code and Codex in persistent **tmux** sessions, accessible from Mac and iPhone over **mosh + Tailscale**. Commands `x` (claude) and `c` (codex) start or attach to named sessions; both clients see the same tmux server and share state.

---

## TL;DR

```
Mac (VS Code / Cursor)              iPhone (Moshi)
   │                                    │
   │ mosh over Tailscale                │ mosh over Tailscale
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

| Command           | What it does                                                      |
| ----------------- | ----------------------------------------------------------------- |
| `x` / `x NAME`    | Create or attach to a tmux session running `claude`               |
| `c` / `c NAME`    | Create or attach to a tmux session running `codex` (Azure)        |
| `x l` / `xl`      | List sessions, prompt for one to join                             |
| `x j NAME` / `xj` | Join (or create+attach) `NAME`                                    |
| `x k NAME` / `xk` | Kill session `NAME`                                               |
| `x K` / `xK`      | Wipe all sessions on the VM (`tmux kill-server`)                  |
| `c l/j/k/K`       | Same surface for codex sessions                                   |
| `xn`              | Rename a session's tmux window (the bold label in Moshi's picker) |

Sessions persist across all client disconnects. Destroyed only by `tmux kill-session -t NAME` (`x k NAME`), the inner `claude`/`codex` exiting, `tmux kill-server` (`x K`), or VM reboot.

---

## Architecture

### Mac path

```
VS Code / Cursor terminal
  │ runs `mosh adam@ai-workstation` (via the `x` zshrc function)
  ▼
mosh-server on VM (auto-spawned per connection over UDP via Tailscale)
  │ runs the user's login shell, which sources ~/.bashrc
  ▼
bash on VM
  │ runs `_x_session NAME claude` from the VM-side `x` function
  ▼
tmux server on VM (creates session if missing, attaches client)
  │
  ▼
Pane process: `claude` (Claude Code TUI)
```

### Mobile path

```
Moshi app (iPhone)
  │ mosh over Tailscale to ai-workstation
  ▼
mosh-server on VM (same as above, identical path)
  │
  ▼
bash → tmux server → claude / codex
```

The phone and the Mac connect to **the same tmux server**. Two clients on one session is supported by tmux natively (mirrored views, keystrokes from either client reach the pane). With `window-size latest` set in `~/.tmux.conf`, the most-recently-active client's terminal size wins, so switching from Mac to iPhone (or vice versa) triggers a one-time reflow on the other client.

---

## Why this setup

This section is the load-bearing one. Each component is here for a specific reason.

### tmux as the session layer

Mandatory:

1. **Survive client disconnect.** The tmux server holds the PTY and the inner process (claude/codex) regardless of whether any client is currently attached. Closing your laptop, killing Wi-Fi, putting the phone in airplane mode — none of these touch the session. The next attach picks up exactly where you left off.
2. **Moshi's session picker enumerates tmux sessions.** When you open the Moshi app on the phone, the picker connects via mosh, runs `tmux list-sessions`, and shows you that list.

### mosh on both clients

Chosen as the single transport for both Mac and iPhone:

- **mosh's UDP + IP roaming** survives network changes mid-session (Wi-Fi flip, cellular handoff, laptop sleep/wake).
- **Local echo** keeps typing responsive over high-latency / lossy links.
- **One mental model on both clients** — same diagnostics, same connection profile.

Why not ET (EternalTerminal) on the Mac as before? Until 2026-05-09 we did. ET was strictly TCP-stable on stable home networks, but kept us on a public IP path (TCP 2022 ingress) and required a complex IAP fallback for v6-only networks. Switching the Mac to mosh-over-Tailscale collapsed both into one transport and let us close all public terminal ingress.

### Tailscale as the transport layer

The VM is reached exclusively over Tailscale. Public IPv4 ingress is closed for SSH / mosh / dev-server (only ICMP + intra-VPC + UDP 41641 for Tailscale's WireGuard remain). This is both the transport mechanism and the security boundary.

Tailnet traffic between Mac/iPhone and the VM is encapsulated:

- **Direct path (preferred):** WireGuard over UDP 41641. Tailscale's coordination server brokers NAT punch-through; both ends learn each other's public IPs and open a direct tunnel. Verified working with ~29 ms RTT to the GCP VM in europe-west1.
- **Relay fallback:** DERP relay over outbound TCP 443. No firewall rule needed (HTTPS egress is implicitly allowed). Slower but always works.

The `allow-tailscale-direct` GCP firewall rule allows UDP 41641 inbound for direct WG. Without it, Tailscale silently falls back to DERP — works but slower.

### Why `CLAUDE_CODE_NO_FLICKER=1`

Always on. Without it, every SIGWINCH-triggered repaint Claude emits gets captured into tmux's scrollback, producing 2× doubling on every reconnect. With it, Claude wraps each TUI frame in DECSET 2026 (synchronized output), tmux treats the frame as atomic, and scrollback stays clean. Tested unsetting on 2026-05-06: artifacts return immediately. Don't unset.

The two other `CLAUDE_CODE_*` env vars are quality-of-life flags (terminal title injection off, anonymous telemetry off).

---

## Commands

All defined in VM `~/.bashrc`. Mac side has parallel `x` / `c` zshrc functions that open a mosh session to the VM.

### `x` and `c` — create / attach

| Invocation  | Behavior                                                                                               |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| `x`         | New tmux session named `claude` (or `claude-2`, `claude-3`, … on collision), running `claude`          |
| `x NAME`    | If `NAME` exists, attach. Else create with `claude`.                                                   |
| `c`         | Same default-naming pattern as `x` but with base `codex` (`codex`, `codex-2`, …) and runs `codex`      |
| `c NAME`    | Like `x NAME` but for codex. VM's `~/.codex/config.toml` configures Azure Foundry as the only provider |
| `x -z NAME` | `-z` and `-t` accepted as no-ops for muscle memory (legacy zmx/tmux mode flags)                        |

When attached from inside an existing tmux client (Moshi's picker), `x NAME` switches to the named session via `tmux switch-client`. Otherwise it does `tmux attach`.

### `x l` / `xl` — list and join

Prints the tmux session list, prompts for a name to attach. Just typing a name attaches; typing a non-existent name _creates_ it (with claude). Ctrl+C / empty input cancels.

### `x j NAME` / `xj NAME` — join by name

Same as `x NAME` (the `j` is just for muscle memory). With no argument, falls through to `x l`.

### `x k NAME` / `xk NAME` — kill one session

```bash
tmux kill-session -t "=NAME"
```

### `x K` / `xK` — kill everything

```bash
tmux kill-server
```

Wipes the entire tmux workspace on the VM. There is no whitelist — this VM's tmux usage is exclusively Claude/Codex sessions, so this is acceptable.

### `xn` — rename window (Moshi-picker bold label)

```bash
xn SESSION NEW_LABEL    # rename window in SESSION to NEW_LABEL
xn                       # interactive: pick a session, prompt for new name
```

Window rename is sticky (auto-disables `automatic-rename`). Session name unchanged so `x j SESSION` keeps working.

### Mac-side aliases

Same names exist in `~/.zshrc`. Behavior:

- `x NAME` / `x j NAME` / `x` / `c NAME` etc. — open a mosh session to the VM and invoke the VM-side function.
- `x l` / `c l` — SSH to the VM (via tailnet), run `tmux list-sessions`, print numbered list locally, prompt for line number, resolve to session name, recurse into `x j NAME`.
- `x k NAME` / `x K` (and `c k NAME` / `c K`) — SSH to the VM and delegate to the VM-side `x k` / `x K` via `bash -ic`.

### Keyboard shortcuts (VS Code / Cursor)

Symmetric "local vs VM" layout — each VM shortcut sits one key to the left of its local equivalent:

| Local (Mac)                               | VM                                           |
| ----------------------------------------- | -------------------------------------------- |
| Cmd+Shift+**C** — `claude` (subscription) | Cmd+Shift+**X** — `x` on VM (claude session) |
| Cmd+Shift+**S** — `codex-az` (Azure)      | Cmd+Shift+**A** — `c` on VM (codex session)  |

Other terminal-related bindings:

| Shortcut    | Action                                                                                                       |
| ----------- | ------------------------------------------------------------------------------------------------------------ |
| Cmd+Shift+B | New terminal → Claude BR profile (`claude-br` → Bedrock-routed Claude)                                       |
| Cmd+Shift+M | Inside a tmux pane: send `Ctrl+B $` (rename current session). VS Code tab + Moshi picker update immediately. |
| Cmd+Alt+R   | Same as Cmd+Shift+M — kept for backwards-compat muscle memory.                                               |
| Cmd+Shift+R | VS Code-local tab rename. Use this for non-tmux tabs (local Claude via Cmd+Shift+C, etc.).                   |

The renaming chain that makes Cmd+Shift+M work end-to-end:

1. `Ctrl+B $` opens tmux's session-rename prompt (overridden in `~/.tmux.conf` to start empty — no backspacing required).
2. tmux updates `#S`. With `set-titles on` + `set-titles-string "#S"`, tmux re-emits the title-set escape `\033]0;NEWNAME\007`.
3. VS Code's xterm.js reads the escape and updates its tab title (combined with `terminal.integrated.tabs.title: "${sequence}"` and `tabs.description: ""`).
4. Moshi polls tmux state and shows `NEWNAME` in its picker.

After session rename, `x j OLDNAME` no longer works — use `x j NEWNAME` or `xl`.

---

## Names you see in each UI

### tmux fields

- `#S` — **session name**. Set explicitly by `x` / `c` at create time, mutable via `Ctrl+B $` (Cmd+Shift+M / Alt+R). This is the **identity** that everything user-facing tracks.
- `#W` — **window name**. Auto-tracked by tmux's `automatic-rename` to whatever process is running in the pane. **Not displayed in any UI you use** — purely internal.

### VS Code / Cursor terminal tab

- **Bold (white)** — `terminal.integrated.tabs.title: "${sequence}"`. `${sequence}` is the OSC title-set escape from the running program. Since `~/.tmux.conf` has `set-titles-string "#S"`, this resolves to the **live session name**.
- **Gray (description)** — `terminal.integrated.tabs.description: ""`. Intentionally empty.
- **Cmd+Shift+R**: VS Code-only inline tab rename. Sets a _manual override_ that blocks future title-escape updates. Useful for non-tmux tabs (local Claude / codex) only.

### Moshi connect-time picker

One label per row, **live**: the current `#S`. Each picker open queries tmux fresh; renames are reflected immediately on next open.

### Moshi active-session panel/header

Two labels per card:

- **Bold (white)** — live `#S`. Refreshes whenever tmux state changes. Updates on `Ctrl+B $`.
- **Smaller (green)** — **Moshi-internal card label**, frozen at the moment you tapped a session in the picker. Doesn't track tmux state changes. Refreshes only on detach+reattach.

So: white = live session name everywhere it appears. Green is a Moshi card-level snapshot you can't control from your config.

---

## Configuration files

### `~/.bashrc` (VM) — `x` / `c` definitions

Self-contained block around lines 130–185 of a 187-line file. Excerpt:

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

_x_default_name() {
  local base="$1" name="$base" n=2
  while tmux has-session -t "=$name" 2>/dev/null; do
    name="${base}-${n}"; n=$((n+1))
  done
  echo "$name"
}

_xc() { … dispatcher: l/j/k/K/default; default uses _x_default_name "$cmd" … }

x() { _xc claude "$@"; }
c() { _xc codex "$@"; }
```

The `-e KEY=VALUE` flags inject env vars into the new tmux session because tmux's `update-environment` only auto-propagates a small set (DISPLAY, SSH\_\*, etc.). Anything else has to be passed explicitly.

### `~/.zshrc` (Mac) — `x` / `c` wrappers

After the 2026-05-09 ET → mosh migration, this is much simpler:

```zsh
VM_HOST=ai-workstation
VM_REPO=/home/adam/src/superextra-landing
CVM_MOSH() { mosh adam@$VM_HOST -- bash -ic "$1"; }

# `x`/`c` dispatch lists/picks via SSH (tailnet), kills via SSH+bash -ic delegation,
# attach goes through `mosh adam@ai-workstation -- bash -ic 'x NAME'`.
```

`xn` (window rename), `rn` (local terminal title), `codex-az`, `gemini-vx`, the `claude-*` aliases all preserved.

### `~/.zx-env` (VM) — Claude Code env vars

```bash
export CLAUDE_CODE_NO_FLICKER=1
export CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
```

Sourced by `~/.bashrc`. Re-injected via `tmux new-session -e` because tmux server env can be stale and the pane process doesn't go through bash.

### `~/.secrets` (VM, mode 0600) — API keys

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=…
export AZURE_OPENAI_API_KEY=…
```

Sourced by `~/.bashrc`. Mode 0600 keeps it readable only to the user.

To add a new secret that needs to reach a tmux session, you have to do **both**:

1. Add `export FOO=…` to `~/.secrets`.
2. Add `-e FOO="$FOO"` to the `_x_session` tmux call in `~/.bashrc`.

### `~/.codex/config.toml` (VM)

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

Azure at the top level as the only provider. Plain `codex` on the VM uses Azure. (On the Mac, `codex-az` wraps `codex --profile azure` because the Mac's config has multiple profiles.)

### `~/.tmux.conf` (VM)

```tmux
set -g set-titles on
set -g set-titles-string "#S"
set -g mouse on
set -g escape-time 0
set -g window-size latest
set -g status off
set -g visual-activity off
set -g visual-bell off
set -g visual-silence off
set -g set-clipboard on

# Override default $ session-rename binding to start with empty prompt.
bind '$' command-prompt -p 'Name:' 'rename-session -- "%%"'

# Plugins
set -g @plugin 'tmux-plugins/tpm'
set -g @plugin 'nhdaly/tmux-better-mouse-mode'
set -g @scroll-speed-num-lines-per-scroll "1"
run '~/.tmux/plugins/tpm/tpm'

# Hide cursor when terminal tab loses focus, show on regain
set -g focus-events on
set-hook -g client-focus-out "run-shell -b 'printf \"\\033[?25l\" > #{client_tty}'"
set-hook -g client-focus-in  "run-shell -b 'printf \"\\033[?25h\" > #{client_tty}'"

set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",*256col*:RGB,*256col*:Tc"
set -g history-limit 100000
```

### Mac `~/.ssh/config` (post-migration)

Single Host block for the VM (tailnet only; public-IP block deleted):

```
Host ai-workstation ai-workstation.tailcb8df5.ts.net 100.101.35.72
    User adam
    HostKeyAlias 34.38.81.215
    ServerAliveInterval 15
    ServerAliveCountMax 10
    TCPKeepAlive no
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 4h
    ObscureKeystrokeTiming no
    IdentitiesOnly yes
    IdentityFile ~/.ssh/id_ed25519
    CheckHostIP no
```

`HostKeyAlias 34.38.81.215` reuses the trusted host-key entry from before the tailnet switch (same VM, same host key). `ObscureKeystrokeTiming no` disables OpenSSH's 20 ms keystroke-timing obfuscation that adds typing latency.

### `/etc/ssh/sshd_config.d/keepalive.conf` (VM)

```
ClientAliveInterval 60
ClientAliveCountMax 3
TCPKeepAlive no
```

Effective interval is 120 s (vendor `50-cloudimg-settings.conf` drop-in sets 120 first; sshd is first-match-wins). Dead peers are reaped in ~6 min.

### `/etc/ssh/sshd_config.d/no-root.conf` (VM)

```
PermitRootLogin no
```

Disables root login entirely. User-level access via `adam` is the only path.

---

## Authentication

| Command  | Auth provider   | Auth storage                         | How it reaches a tmux pane                                 |
| -------- | --------------- | ------------------------------------ | ---------------------------------------------------------- |
| `claude` | Anthropic OAuth | `~/.claude/.credentials.json` (0600) | Pane process reads file from disk on startup. No env var.  |
| `codex`  | Azure API key   | `~/.secrets` `AZURE_OPENAI_API_KEY`  | Must be in pane env. Propagated via `tmux new-session -e`. |

**Re-authenticate claude:** `claude auth login` from any shell on the VM. Writes a fresh OAuth token to the credentials file. Existing sessions keep working with the old token until it expires; new sessions pick up the new one.

**Rotate codex Azure key:** edit `~/.secrets`, source it, restart any open codex sessions. The bashrc `-e` injection will pull the new value on next session create.

---

## Connection details

### mosh

- Server: `mosh-server` auto-spawned per connection (Mac and iPhone alike).
- Mac client: `brew install mosh` → `mosh adam@ai-workstation`. Wired into `x` / `c` zshrc functions via `CVM_MOSH`.
- iPhone client: Moshi app. Picker connects via mosh, runs `tmux ls`, shows session list.
- Title-prefix `[mosh] ` is suppressed via `MOSH_TITLE_NOPREFIX=1` in `/etc/environment` on the VM.

### Tailscale

- Both Mac and iPhone are tailnet members. VM's tailnet IP: `100.101.35.72` (`ai-workstation`).
- All Mac→VM and iPhone→VM traffic (mosh, ssh, occasional dev-server) flows over the tailnet.
- Direct WireGuard P2P typical: ~29 ms RTT Mac↔VM. Falls back to DERP relay if direct fails.

### SSH

Direct SSH used only for non-interactive Mac→VM commands (config pulls, scp, `xk` / `xK` delegation via `bash -ic`). Goes via tailnet. Key auth, no passwords.

### GCP firewall rules (post-migration)

| Rule                     | Protocol | Ports | Purpose                        |
| ------------------------ | -------- | ----- | ------------------------------ |
| `allow-tailscale-direct` | UDP      | 41641 | Tailscale direct WireGuard P2P |
| `default-allow-icmp`     | ICMP     | —     | ping                           |
| `default-allow-internal` | All      | —     | intra-VPC (10.128.0.0/9)       |

Public ingress for SSH, mosh, ET, and dev-server is deliberately closed. All terminal traffic flows over Tailscale.

---

## VS Code / Cursor

### Terminal profiles

Both editors, in `settings.json` under `terminal.integrated.profiles.osx`:

- `zsh` (default) — regular shell
- `Claude` — runs `claude; exec zsh` (local Claude subscription)
- `Claude BR` — runs `claude-br; exec zsh` (Bedrock-routed Claude)
- `Codex Azure` — runs `codex-az; exec zsh` (used by Cmd+Shift+S)

### Terminal performance settings

| Setting                                        | Value   | Why                                                           |
| ---------------------------------------------- | ------- | ------------------------------------------------------------- |
| `terminal.integrated.gpuAcceleration`          | `on`    | WebGL rendering, fastest on Retina                            |
| `terminal.integrated.smoothScrolling`          | `false` | No animation delay                                            |
| `terminal.integrated.localEchoEnabled`         | `off`   | Tested and rejected — causes visual artifacts with Claude TUI |
| `terminal.integrated.shellIntegration.enabled` | `false` | Prevents relaunch warnings                                    |

---

## Performance tuning

### VM TCP (`/etc/sysctl.conf`)

- `net.ipv4.tcp_congestion_control=bbr`
- `net.ipv4.tcp_autocorking=0`
- `net.ipv4.tcp_slow_start_after_idle=0`
- `net.ipv4.tcp_mtu_probing=1`
- `net.core.default_qdisc=fq`

### macOS TCP

- `sudo sysctl -w net.inet.tcp.delayed_ack=0` (persistent via LaunchDaemon)
- `sudo sysctl -w net.inet.tcp.mssdflt=1448`

---

## Mutagen file sync

| Folder                                  | Purpose                                     |
| --------------------------------------- | ------------------------------------------- |
| `~/src/superextra-landing`              | Real local repo — no sync                   |
| `~/src/superextra-landing-vm`           | Mutagen mirror — bidirectional sync with VM |
| VM: `/home/adam/src/superextra-landing` | The remote repo where Claude works          |

Session: `superextra-vm-sync`, mode `two-way-safe`. `.git` synced. Daemon auto-starts on boot.

| Command                                 | Action                         |
| --------------------------------------- | ------------------------------ |
| `mutagen sync list`                     | Show sync status and conflicts |
| `mutagen sync flush`                    | Force immediate sync           |
| `mutagen sync reset superextra-vm-sync` | Reset if stuck                 |

Mutagen daemon LaunchAgent: `~/Library/LaunchAgents/io.mutagen.mutagen.plist`.

---

## Screenshots

Cmd+Shift+1 on Mac captures a screenshot, uploads via SCP to `/home/adam/screenshots/` on VM, copies the path to clipboard. Implementation: `~/.local/bin/screenshot-to-vm` (Mac), bound by skhd at `~/.config/skhd/skhdrc`.

---

## Push notifications (`moshi-hook`)

`moshi-hook` is a small Go daemon that bridges Claude Code / Codex hook events into Moshi's iOS app. Forwards `approval_required`, `task_complete`, `session_started`, `tool_running`, `tool_finished` events to Moshi over WebSocket → iOS Live Activity / push.

Installed on the VM (where claude/codex actually run). Optionally also on the Mac for local Claude/Codex tabs.

### VM install

```bash
curl -fsSL https://getmoshi.app/install.sh | sh
moshi-hook pair --token <token from Moshi → Settings → Agent Hooks>
moshi-hook install
```

`install` adds Moshi-owned hook entries to `~/.claude/settings.json`, `~/.codex/hooks.json`, and other supported agents. User-owned hooks are preserved.

### Persistent daemon (systemd user service)

```ini
# ~/.config/systemd/user/moshi-hook.service
[Unit]
Description=moshi-hook daemon
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=%h/.local/bin/moshi-hook serve
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
```

```bash
sudo loginctl enable-linger adam
systemctl --user daemon-reload
systemctl --user enable --now moshi-hook
```

### Mac install (optional)

```bash
brew tap rjyo/moshi
brew install moshi-hook
moshi-hook pair --token <fresh-token>
moshi-hook install
brew services start moshi-hook
```

### Diagnostics

```bash
moshi-hook status
moshi-hook logs -f
systemctl --user status moshi-hook
```

---

## VM details

|           |                                                       |
| --------- | ----------------------------------------------------- |
| Host      | `adam@ai-workstation` (tailnet) / `100.101.35.72`     |
| Public IP | `34.38.81.215` (firewalled — terminal ingress closed) |
| Machine   | GCP g2-standard-4, Belgium (europe-west1-b)           |
| OS        | Ubuntu 24.04                                          |
| Repo      | `~/src/superextra-landing`                            |
| Node      | 22 (via nvm at `~/.nvm/versions/node/v22.22.2/`)      |
| Python    | 3.12 (agent venv at `agent/.venv/`)                   |

### What's installed

- Node 22, Python 3.12, Docker, **mosh**, **tmux 3.4**, gcloud CLI
- **Claude Code** at `~/.nvm/versions/node/v22.22.2/bin/claude`
- **Codex CLI** at `~/.nvm/versions/node/v22.22.2/bin/codex`
- **Tailscale** (the transport layer; daemon always on)
- **MCP servers**: GitHub (npx), Svelte, Miro, Apify
- **moshi-hook** at `~/.local/bin/moshi-hook` (Go daemon; see [Push notifications](#push-notifications-moshi-hook))

### Config files on VM

| Path                                        | Purpose                                                            |
| ------------------------------------------- | ------------------------------------------------------------------ |
| `~/.bashrc`                                 | `x` / `c` definitions, sources `.zx-env`/`.secrets`                |
| `~/.zx-env`                                 | `CLAUDE_CODE_*` env vars                                           |
| `~/.secrets`                                | API keys (mode 0600)                                               |
| `~/.tmux.conf`                              | tmux config                                                        |
| `~/.codex/config.toml`                      | Codex provider config (Azure)                                      |
| `~/.codex/hooks.json`                       | Codex hooks (managed by `moshi-hook install`)                      |
| `~/.claude/.credentials.json`               | Claude OAuth token (mode 0600)                                     |
| `~/.claude/settings.json`                   | Claude config; `hooks.Stop` populated by `moshi-hook install`      |
| `~/.claude.json`                            | MCP server config                                                  |
| `~/.config/systemd/user/moshi-hook.service` | systemd user unit running `moshi-hook serve`                       |
| `~/.local/state/moshi/hook.log`             | moshi-hook daemon logs                                             |
| `/etc/environment`                          | `MOSH_TITLE_NOPREFIX=1` (suppresses mosh's `[mosh] ` title prefix) |
| `/etc/ssh/sshd_config.d/keepalive.conf`     | sshd keepalives                                                    |
| `/etc/ssh/sshd_config.d/no-root.conf`       | `PermitRootLogin no`                                               |
| `~/src/superextra-landing/.env`             | App env vars                                                       |
| `~/src/superextra-landing/agent/.env`       | Agent env vars                                                     |

---

## Operations

### Adding a new env var that needs to reach claude/codex

Two-step:

1. Add `export FOO=…` to `~/.zx-env` (Claude config) or `~/.secrets` (credential).
2. Add `-e FOO="$FOO"` to the `_x_session` tmux call in `~/.bashrc`.

### Cleaning up stale sessions

```bash
tmux ls                      # see what's there
x k SESSION-NAME             # kill one
x K                          # nuke all sessions
```

### Inspecting a session non-destructively

```bash
tmux capture-pane -p -t '=NAME' | tail -50
tmux list-sessions -F '#{session_name} cwd=#{pane_current_path} cmd=#{pane_current_command}'
```

### Updating Claude Code or Codex CLI

```bash
npm install -g @anthropic-ai/claude-code   # claude
npm install -g @openai/codex                # codex
```

Existing sessions keep running the old binary; new sessions get the new one.

---

## Recovery

If Tailscale breaks and the VM is unreachable:

1. **GCP serial console** (always available):
   ```bash
   gcloud compute connect-to-serial-port adam@ai-workstation
   ```
2. From the serial console, re-open public SSH temporarily:
   ```bash
   gcloud compute firewall-rules create default-allow-ssh \
     --direction=INGRESS --action=ALLOW --rules=tcp:22 \
     --source-ranges=0.0.0.0/0 --priority=65534
   ```
3. SSH in directly via `34.38.81.215`, debug Tailscale, then re-delete the public SSH rule when done.

---

## Troubleshooting

| Problem                                                       | Fix                                                                                                                                                         |
| ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **mosh disconnect after sleep**                               | Usually auto-reconnects in 1–5 s. If not, run `xl` to rejoin — tmux session is still alive.                                                                 |
| **mosh exits immediately**                                    | Check Tailscale is up on Mac (`tailscale status`). Verify locale: `locale -a \| grep en_US.utf8` on VM.                                                     |
| **Claude not authenticated**                                  | Run `claude auth login` on the VM. New token → all new sessions pick it up.                                                                                 |
| **Codex says "config profile X not found"**                   | The VM's `~/.codex/config.toml` puts Azure at the top level, not under `[profiles.azure]`. Plain `codex` is correct. Don't use `codex --profile azure`.     |
| **Codex starts but immediately fails to authenticate**        | `AZURE_OPENAI_API_KEY` not in pane env. Run `echo "$AZURE_OPENAI_API_KEY" \| wc -c` in the offending pane — if zero, the bashrc `-e` injection didn't fire. |
| **Tab in VS Code shows `[mosh] NAME`**                        | `MOSH_TITLE_NOPREFIX=1` not set or not picked up. Add to `/etc/environment` on VM, reconnect mosh.                                                          |
| **Mac shows stale content from other device after switching** | Known Ink/SIGWINCH bug; full analysis archived in `zmx-scroll-and-device-switching.md`. No clean fix at our layer.                                          |
| **Mobile tmux shows duplicate session content mid-session**   | Cross-device size mismatch triggers Claude repaints at Mac size into mobile-sized tmux panes. Same upstream root cause.                                     |
| **VS Code / Cursor SSH can't connect**                        | Try `ssh ai-workstation` from a terminal first. If editor was just updated, `rm -rf ~/.vscode-server/` on VM and reconnect.                                 |
| **Mutagen not syncing**                                       | `mutagen sync list` for status. `mutagen sync flush` to force. `mutagen daemon start` if daemon died.                                                       |
| **Old `zx`/`tx`/`cv` commands not found**                     | All renamed to `x` / `c`. `-z`/`-t` flags accepted as no-ops.                                                                                               |
| **`x K` killed sessions I wanted to keep**                    | `x K` runs `tmux kill-server` — intentional wipe. Kill specific sessions with `x k NAME` instead.                                                           |

---

## Decision history

A condensed log of stack changes and rationale, newest first.

### 2026-05-09 — Drop ET, mosh-only over Tailscale, close public ingress

Replaced ET (Mac transport) with mosh, replaced public-IP routing with Tailscale on both clients. Result: single transport, single network plane, zero public terminal exposure.

This reverses the 2026-05-06 finding that "Tailscale isn't load-bearing." With ET removed, Tailscale becomes the carrier for both Mac and iPhone (no IPv6-only fallback needed — Tailscale handles connectivity via WireGuard direct or DERP relay regardless of v6 vs v4 on the local network).

Changes:

- Mac: `brew uninstall et`. ~/.zshrc trimmed 305 → 130 lines (drop CVM_ET, IAP/lo0 helpers, vp proxy, x iap subcommand). ~/.ssh/config trimmed 52 → 19 lines (drop superextra-vm Host block + Match ProxyCommand).
- VM: ET package purged + binaries gone + service unit gone. fail2ban purged (vestigial without public SSH). `~/bin/codex-connect-proxy.py` removed.
- GCP firewall: added `allow-tailscale-direct` (UDP 41641); deleted `allow-et`, `allow-mosh`, `default-allow-ssh`, `allow-dev-server`.

Recovery: GCP serial console + temporary public SSH rule re-creation if Tailscale ever fails.

### 2026-05-08 — SSH hardening: `PermitRootLogin no`, install fail2ban

[Subsequently fail2ban was removed on 2026-05-09 — see entry above. `PermitRootLogin no` retained as defensive depth.]

Audit triggered by "is the VM safe without Tailscale?" question. SSH was already key-only (`PasswordAuthentication no`, `KbdInteractiveAuthentication no`), but root login was allowed via key (`PermitRootLogin without-password`).

### 2026-05-08 — Add `moshi-hook` for iOS push notifications

Installed `moshi-hook` v0.1.8 on the VM as a systemd user service. Bridges Claude/Codex hook events into Moshi's iOS app. Phone gets pings on `task_complete` / `approval_required` / etc.

### 2026-05-08 — Drop pet names; collapse session/window into one identity

Replaced random pet-name auto-naming (`fast-ant`, `cool-bee`, …) with command-based defaults (`claude`, `claude-2`, …). Pet names were never typed by the user (addressing happens through pickers); their only role was zero-typing fallback. Replacing with `claude`/`codex` keeps the convenience while making the auto-name semantically meaningful.

### 2026-05-07 — Drop zmx; unify `x` and `c` over a shared helper

Removed: `zmx attach …` from session creation; mode-detection logic; background-tmux-wrapper-spawn race. Net `~/.bashrc` LOC: 287 → 186 (–101). Why: tmux is mandatory anyway (Moshi picker), zmx's "native scroll" benefit was unreachable in practice, the ongoing Zig-build / fork-tracking / resize-leader-patch saga was paying for nothing.

### 2026-04-22 — Unify `zx` and `tx` into a single `x` function

Removed: parallel `zx`/`tx` command families. Single `x` function with auto-mode-detection (later removed in 2026-05-07).

---

See [zmx-scroll-and-device-switching.md](zmx-scroll-and-device-switching.md) for the detailed postmortem of the zmx-era debugging session (archived 2026-05-07).
