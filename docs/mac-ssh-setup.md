# Mac SSH Setup for Remote VM

## Context

We run Claude Code on a remote GCP AI Workstation (Belgium, `34.38.81.215`) via tmux. Previously we used mosh + Tailscale, but we're simplifying to plain SSH with ControlMaster for connection reuse, auto-reconnect, and iTerm2's native tmux integration (`tmux -CC`).

The phone (Moshi app) still uses mosh — that's handled in the app, not here.

## Prerequisites

- macOS with iTerm2 installed (https://iterm2.com/downloads.html — install if missing)
- SSH key already authorized on the VM (`ssh adam@34.38.81.215` works without password prompt)

## Step 1: SSH config

Edit `~/.ssh/config` on the Mac. If a `Host superextra-vm` block already exists, replace it. Otherwise add it:

```
Host superextra-vm
    HostName 34.38.81.215
    User adam
    ServerAliveInterval 15
    ServerAliveCountMax 3
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 4h
```

Then create the sockets directory:

```bash
mkdir -p ~/.ssh/sockets
```

**What this does:**

- `ServerAliveInterval 15` + `ServerAliveCountMax 3` — detects dead connections in ~45 seconds instead of hanging for minutes
- `ControlMaster auto` — first SSH connection becomes a master; all subsequent `ssh`, `scp`, `cv` commands piggyback on it instantly (no handshake)
- `ControlPath` — where the master socket file lives
- `ControlPersist 4h` — master connection stays open 4 hours after last use, so reconnects are instant even after closing the terminal

## Step 2: `cv` wrapper in `~/.zshrc`

Find the existing `cv` function in `~/.zshrc` and replace it with this version. If there's no existing `cv` function, add this:

```bash
# cv - connect to VM tmux session via iTerm2's native tmux integration
# Usage: cv [session-name]  (defaults to "main")
# Auto-reconnects on SSH disconnect. Ctrl+C to stop.
cv() {
  local session="${1:-main}"
  while true; do
    ssh -t superextra-vm "tmux -CC new -A -s $session"
    echo "Disconnected. Reconnecting in 2s... (Ctrl+C to stop)"
    sleep 2
  done
}
```

Then reload:

```bash
source ~/.zshrc
```

**What this does:**

- `tmux -CC` — iTerm2's control mode. Each tmux window becomes a native iTerm2 tab with native scrollback, clipboard, and split panes. tmux is still running on the VM but iTerm2 renders everything as if it were local.
- `new -A -s $session` — attaches to existing session or creates a new one
- The `while true` loop auto-reconnects if SSH drops (2 second pause between attempts)
- Works with the same tmux sessions the phone connects to — same session, different UI

## Step 3: Remove old mosh setup (if present)

If there's a `mosh` alias or mosh-based `cv` function in `~/.zshrc`, remove it. We no longer use mosh on the Mac.

Check for and remove:

- Any `alias` lines referencing `mosh`
- Any function that calls `mosh` to connect to the VM

Do NOT remove the screenshot-to-vm setup (Cmd+Shift+7) — that stays.

## Step 4: Test

Open **iTerm2** (not Terminal.app — `tmux -CC` only works in iTerm2) and run:

```bash
cv main
```

You should see iTerm2 open native tabs for each tmux window. Verify:

1. Scrollback works (scroll up with trackpad)
2. Cmd+C / Cmd+V work for copy-paste
3. New tmux windows appear as new iTerm2 tabs
4. Disconnect by closing the tab — then run `cv main` again, session should reattach with everything intact

## Step 5: Test ControlMaster

With `cv` running in one tab, open another iTerm2 tab and run:

```bash
ssh superextra-vm echo "instant connection"
```

It should connect instantly (no SSH handshake delay). This also makes the screenshot-to-vm SCP uploads faster.

## Daily use

- `cv main` — connect to main session from Mac (native iTerm2 tabs)
- `cv research` — connect to a different session
- Phone (Moshi app) — connects to the same session via mosh + regular tmux
- Both can be connected simultaneously — same session, different views
- If SSH drops on Mac, it auto-reconnects in 2 seconds

## Troubleshooting

- **"tmux -CC" shows raw escape codes instead of native tabs**: You're not in iTerm2. This feature is iTerm2-only. Open iTerm2 and try again.
- **SSH hangs instead of reconnecting**: Check that `ServerAliveInterval` is in your SSH config. Run `ssh -v superextra-vm` to debug.
- **ControlMaster socket stale**: `rm ~/.ssh/sockets/*` and reconnect.
- **Phone and Mac fighting over tmux window**: Both clients share the active window by default. This is normal — switching windows on one device switches on the other.
