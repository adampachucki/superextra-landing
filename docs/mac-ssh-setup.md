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
    ServerAliveInterval 15
    ServerAliveCountMax 6000
    TCPKeepAlive no
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 4h
```

Create the sockets directory: `mkdir -p ~/.ssh/sockets`

**What this does:**

- `ServerAliveInterval 15` + `ServerAliveCountMax 6000` — detects dead connections in ~45s, keeps alive for ~25 hours
- `ControlMaster auto` — first SSH connection becomes a master; subsequent `ssh`, `scp` commands piggyback instantly (no handshake)
- `ControlPersist 4h` — master stays open 4 hours after last use

VM side (`/etc/ssh/sshd_config`) has `ClientAliveInterval 60` + `ClientAliveCountMax 6000`.

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

Also available on VM: `bye` (kill current session), `rename <name>` (rename current session).

## VS Code

Open VS Code to the VM from Mac terminal:

```bash
cvs    # alias for: code --remote ssh-remote+superextra-vm /home/adam/src/superextra-landing
```

Key VS Code settings (`settings.json`):

- `remote.SSH.useLocalServer: true` — keeps remote server alive through brief disconnects
- `remote.SSH.localServerDownload: "always"` — pre-downloads server binary
- `remote.SSH.connectTimeout: 60` — longer timeout for reconnects
- `window.restoreWindows: "all"` — restores all windows (including remote) on restart

**Note:** VS Code's integrated terminal is noticeably slower than standalone terminals for typing. Use iTerm2/Ghostty with `cv` for Claude Code sessions. Use VS Code for file browsing, editing, and quick commands. Mosh local echo does not work in VS Code's terminal.

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
