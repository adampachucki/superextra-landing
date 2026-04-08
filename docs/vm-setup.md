# Remote VM Setup

## What

A GCP VM (g2-standard-4, Belgium) running Claude Code, accessible from any device via direct SSH (static IP). Claude runs in persistent tmux sessions on the VM — start a session from your Mac, pick it up from your phone, continue on your iPad.

## Why

- **Always-on sessions** — Claude keeps working after you close the laptop
- **Multi-device** — same session from Mac (Cursor terminal, CLI), phone (Termius), iPad
- **Parallel work** — multiple Claude sessions on different tasks simultaneously
- **Fast connection** — direct SSH with static IP (~50-70ms from Poland)
- **Isolated worktrees** — parallel sessions on separate branches without conflicts

## Architecture

```
Your device
  ↓ ssh (direct, static IP)
GCP VM (34.38.81.215)
  ↓
tmux session
  ↓
Claude Code → edits ~/src/superextra-landing
```

Cursor Remote SSH connects separately for IDE features (file browsing, syntax highlighting, go-to-definition) on the same files Claude edits.

## The `cv` command

One function, defined in Mac `~/.zshrc` and VM `~/.bashrc`. Manages all Claude sessions.

| Command          | Action                                                              |
| ---------------- | ------------------------------------------------------------------- |
| `cv feature-x`   | New session named `feature-x` with Claude                           |
| `cv`             | New session with auto-generated name                                |
| `cv w feature-x` | New session in isolated git worktree (own branch, own node_modules) |
| `cv l`           | List sessions — pick one by number to attach                        |
| `cv a feature-x` | Attach to existing session by name                                  |
| `cv k feature-x` | Kill session by name                                                |
| `cv k`           | List sessions — pick one by number to kill                          |
| `cv K`           | Kill all sessions                                                   |

Sessions persist across disconnects. Close terminal, switch Wi-Fi, sleep laptop — `cv a` picks up where you left off.

### Session lifecycle

When you run `cv feature-x`, tmux starts a session that runs `claude` as its sole command. When Claude exits (via `/exit`, Ctrl+C, or crash), the tmux session closes automatically — no orphan shells left behind. This is intentional: Claude Code doesn't support resuming a crashed session, so a fallback shell would just be an empty prompt in the repo directory with nothing useful to do.

Two helpers for managing the current session from inside it:

| Command         | Action                          |
| --------------- | ------------------------------- |
| `bye`           | Kill the current tmux session   |
| `rename <name>` | Rename the current tmux session |

### Terminal tab titles

tmux sets the terminal tab title to the session name. Cursor needs this setting to pick it up:

```json
"terminal.integrated.tabs.title": "${sequence}",
"terminal.integrated.tabs.description": "${process}"
```

Mac Terminal.app and Termius pick up titles automatically.

## Worktrees (`cv w`)

For parallel sessions that need isolation. `cv w feature-x`:

1. Creates git worktree at `~/src/superextra-landing-worktrees/feature-x/`
2. Creates branch `feature-x`
3. Symlinks `.env` and `agent/.env` from main checkout
4. Runs `npm install` (~30-60 sec)
5. Starts Claude in the worktree

Use `cv` (no worktree) for single sessions — instant startup. Use `cv w` when running multiple sessions that might conflict.

## Connection stack

| Layer       | Tool              | Purpose                                                              |
| ----------- | ----------------- | -------------------------------------------------------------------- |
| Network     | Direct IP         | Static IP `34.38.81.215`, no VPN needed                              |
| Transport   | mosh              | Resilient UDP connection, survives sleep/roaming, instant local echo |
| Persistence | tmux              | Sessions survive disconnects                                         |
| IDE         | Cursor Remote SSH | Full editor features on remote files                                 |
| Dev server  | Port forwarding   | Cursor auto-forwards port 5199 to localhost                          |

### Why mosh over SSH

SSH is used for one-shot commands (`cv k`, `cv K`). Interactive sessions use mosh for:

- Instant local echo (typing feels responsive despite latency)
- Survives Wi-Fi → cellular switches
- Survives laptop sleep without reconnecting

### VS Code Remote SSH

Connects VS Code to the VM for file browsing, syntax highlighting, go-to-definition:

1. `Cmd+Shift+P` → "Remote-SSH: Connect to Host" → `superextra-vm`
2. Open `/home/adam/src/superextra-landing`
3. Run `cv feature-x` in VS Code's integrated terminal
4. Claude's file changes appear in the editor in real-time
5. `npm run dev` in another terminal tab — auto-forwarded to `localhost:5199`

SSH config (`~/.ssh/config`):

```
Host superextra-vm
    HostName 34.38.81.215
    User adam
    ForwardAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 720
    TCPKeepAlive no
```

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
- MCP servers: GitHub (Docker), Svelte, Miro, Apify (all HTTP-based except GitHub)
- No browser-dependent MCPs (Chrome DevTools, Pencil, Playwright)

### Config files on VM

- `~/.bashrc` — contains `cv` function
- `~/.tmux.conf` — `set-titles on`, `set-titles-string "#S"`
- `~/.claude.json` — MCP server config
- `~/src/superextra-landing/.env` — app env vars
- `~/src/superextra-landing/agent/.env` — agent env vars
- `~/src/superextra-landing/scripts/worktree-setup.sh` — worktree initialization script

## Deploying from VM

Push to `main` → GitHub Actions → Firebase Hosting. Same as local development. Claude on the VM has full git access via SSH key (`~/.ssh/id_ed25519`, added to GitHub as `GCP AI Workstation`).

## Troubleshooting

**VS Code SSH can't connect** — Try `ssh superextra-vm` first to verify SSH works. If VS Code updated recently, the remote server may need reinstalling — SSH in manually and `rm -rf ~/.vscode-server/`, then reconnect.

**Claude not authenticated on VM** — Run `claude auth login` on the VM and follow the browser flow.

**sudo not working** — `adam` must be in the sudo group. Fix via: `gcloud compute ssh ai-workstation --zone=europe-west1-b -- "sudo usermod -aG sudo adam"`

**Worktree env files missing** — The setup script symlinks them, but if you create worktrees manually, copy or symlink `.env` and `agent/.env` from the main checkout.

**tmux session name conflict** — `cv feature-x` fails if a session named `feature-x` already exists. Use `cv a feature-x` to attach, or `cv k feature-x` to kill it first.

## Why not Tailscale

Evaluated April 2026. Previously used (Tailscale IP `100.101.35.72`), removed in `57c7416` due to ~300ms latency from DERP relay fallback. Re-evaluated whether it could improve VS Code SSH reliability after sleep/wake. Decision: **don't use it.**

- **Mosh doesn't need it** — already handles roaming and sleep natively via UDP
- **Won't fix VS Code sleep/wake** — SSH TCP sessions inside the WireGuard tunnel still time out during extended sleep (15+ min). VS Code shows "Cannot reconnect" regardless of transport
- **macOS sleep/wake bugs** — Tailscale fails to reconnect after sleep >15 min ([#1134](https://github.com/tailscale/tailscale/issues/1134)), can break all internet on wake ([#17736](https://github.com/tailscale/tailscale/issues/17736), [#17937](https://github.com/tailscale/tailscale/issues/17937))
- **The 300ms was fixable** — caused by DERP relay, not WireGuard. Opening UDP 41641 in GCP firewall gives direct P2P (~1-3ms overhead). But no benefit over current setup even with direct connections
