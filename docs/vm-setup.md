# Remote VM Setup

## What

A GCP VM (g2-standard-4, Belgium) running Claude Code, accessible from any device via Tailscale. Claude runs in persistent tmux sessions on the VM — start a session from your Mac, pick it up from your phone, continue on your iPad.

## Why

- **Always-on sessions** — Claude keeps working after you close the laptop
- **Multi-device** — same session from Mac (Cursor terminal, CLI), phone (Termius), iPad
- **Parallel work** — multiple Claude sessions on different tasks simultaneously
- **Fast connection** — mosh transport for snappy typing over Berlin → Belgium latency
- **Isolated worktrees** — parallel sessions on separate branches without conflicts

## Architecture

```
Your device
  ↓ mosh (interactive) / ssh (commands)
GCP VM (100.101.35.72 via Tailscale)
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
| Network     | Tailscale         | Private mesh VPN, no port forwarding needed                          |
| Transport   | mosh              | Resilient UDP connection, survives sleep/roaming, instant local echo |
| Persistence | tmux              | Sessions survive disconnects                                         |
| IDE         | Cursor Remote SSH | Full editor features on remote files                                 |
| Dev server  | Port forwarding   | Cursor auto-forwards port 5199 to localhost                          |

### Why mosh over SSH

SSH is used for one-shot commands (`cv k`, `cv K`). Interactive sessions use mosh for:

- Instant local echo (typing feels responsive despite latency)
- Survives Wi-Fi → cellular switches
- Survives laptop sleep without reconnecting

### Cursor Remote SSH

Connects Cursor IDE to the VM for file browsing, syntax highlighting, go-to-definition:

1. `Cmd+Shift+P` → "Remote-SSH: Connect to Host" → `superextra-vm`
2. Open `/home/adam/src/superextra-landing`
3. Run `cv feature-x` in Cursor's integrated terminal
4. Claude's file changes appear in the editor in real-time
5. `npm run dev` in another terminal tab — auto-forwarded to `localhost:5199`

SSH config (`~/.ssh/config`):

```
Host superextra-vm
    HostName 100.101.35.72
    User adam
    ForwardAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

## VM details

|           |                                                     |
| --------- | --------------------------------------------------- |
| Host      | `adam@100.101.35.72` (Tailscale)                    |
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

**mosh locale error** — Mac sends invalid `LC_CTYPE=UTF-8`. The `cv` function handles this by setting `LC_CTYPE=en_US.UTF-8` explicitly. If you see this error outside `cv`, run: `LC_CTYPE=en_US.UTF-8 mosh adam@100.101.35.72`

**Cursor SSH can't connect** — Check Tailscale is running. Try `ssh superextra-vm` first to verify SSH works. If Cursor updated recently, the remote server may need reinstalling — SSH in manually and `rm -rf ~/.cursor-server/`, then reconnect.

**Claude not authenticated on VM** — Run `claude auth login` on the VM and follow the browser flow.

**sudo not working** — `adam` must be in the sudo group. Fix via: `gcloud compute ssh ai-workstation --zone=europe-west1-b -- "sudo usermod -aG sudo adam"`

**Worktree env files missing** — The setup script symlinks them, but if you create worktrees manually, copy or symlink `.env` and `agent/.env` from the main checkout.

**tmux session name conflict** — `cv feature-x` fails if a session named `feature-x` already exists. Use `cv a feature-x` to attach, or `cv k feature-x` to kill it first.
