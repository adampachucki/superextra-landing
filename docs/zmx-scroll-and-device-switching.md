# zmx scroll and device-switching — historical postmortem

> **Archived 2026-05-07.** zmx is no longer in the live stack. The VM `~/.bashrc` `x` (and `c`) functions create plain tmux sessions running `claude` (or `codex`) directly. This document is preserved as the postmortem of the zmx-era scroll, resize, and multi-device debugging — the analysis that ultimately concluded zmx should be dropped. **For current setup, see [vm-setup.md](vm-setup.md).** The `~/.bashrc.bak-pre-zmx-drop-2026-05-07` backup retains the prior implementation if rollback is ever needed.

Context captured after an intensive debugging session on 2026-04-17. Read this before touching the scroll / resize / multi-device path again. The short version: most of what looks fixable at the zmx layer isn't, because Claude Code's Ink renderer stores conversation messages in `<Static>` that cannot be re-emitted. Any scrollback wipe permanently destroys session history.

## Stack architecture review (2026-05-06)

A round of testing decomposed the mobile flow `Moshi → mosh → tmux → zmx → claude` into its parts to see which layers are actually load-bearing. Findings:

**tmux is mandatory.** Moshi's session picker shows tmux sessions only — that's the discovery/switch UX on the phone. No tmux = no picker = no way to enumerate or jump between concurrent sessions from mobile. As of 2026-05-06 no iOS terminal app surfaces zmx sessions natively.

**Tailscale is convenience, not infrastructure.** Connecting the phone to the VM's public IP via mosh works identically to Tailscale-routed mosh — same survive-disconnect behavior, same UDP transport. GCP firewall already allows mosh UDP 60000–61000, ET 2022, and SSH 22 from `0.0.0.0/0`. Tailscale's value is DNS (`ai-workstation` resolves), key-free auth potential (`tailscale up --ssh`), and NAT traversal. None of those are required for the basic flow.

**zmx is not required for survive-disconnect.** ET on the Mac side and mosh on the phone side already keep client connections alive across network drops. The tmux session on the VM persists regardless. Eliminating zmx and running ET → tmux → claude (Mac) / mosh → tmux → claude (phone) was tested and works correctly through both desktop and mobile network outages.

**zmx's "native scroll" benefit is neutralized by the tmux requirement.** The historical case for zmx was that it's a raw PTY relay with no alternate screen, so terminal-native scroll worked on the Mac. But because tmux is now mandatory (mobile picker), and tmux owns the alternate screen by definition, native scroll on the Mac is unreachable regardless of whether zmx sits underneath tmux. Whatever scroll experience tmux provides is what you get.

**zmx would become valuable again only if** an iOS terminal app surfaced zmx sessions directly the way Moshi surfaces tmux. There is no such client as of 2026-05-06.

**`CLAUDE_CODE_NO_FLICKER=1` must stay set.** Disabling it (tested via `env -u CLAUDE_CODE_NO_FLICKER claude` in plain ET+tmux on 2026-05-06) introduced significant rendering artifacts in the tmux pane. The variable's existing always-on injection through `~/.zx-env` is the desired state for any tmux-based stack. Don't unset it. (The "comment in `~/.bashrc` is misleading" caveat below remains accurate — the value is still applied through `~/.zx-env`.)

**Implication for future simplification.** A clean, equivalent stack that drops zmx looks like:

```
Mac:    VS Code terminal → ET (34.38.81.215:2022) → tmux → claude
Mobile: Moshi → mosh → tmux → claude
(both attach to the same tmux server on the VM)
```

This eliminates the local Zig build, the upstream-fork branch, the resize-leader/scroll-bug surface area, and the zmx-vs-tmux sequencing dance documented in `~/zmx-tmux-scrolling.md`. The trade: no native scroll on the Mac (already true once tmux is in the path), and zmx's named-session command surface (`zmx attach NAME claude`) becomes `tmux new -As NAME 'claude'`.

Not a recommendation to migrate today — just a record that the architectural premise of the rest of this doc (zmx is load-bearing) has been re-examined and found to be weaker than it looked.

## Read-this-first (for future agents / future me)

- **Do not attempt to fix scroll / duplicate / stale-cells issues by broadcasting escape sequences from the zmx daemon.** Any `\x1b[3J` (clear scrollback) or `\x1b[2J` (clear visible) broadcast wipes Ink `<Static>` conversation content permanently — Static items are emitted once and never re-emitted, so wiping is irreversible data loss.
- **Root cause of the visible artifacts is upstream Claude Code / Ink**, not zmx. Specifically: Ink's `log-update` erases only its last-tracked row count on SIGWINCH; rows past that stay stale. Real fix is DECSET 2026 sync output + full-height tracking in Ink — both upstream.
- **Known good state as of 2026-04-18 (updated late-day)**: zmx is **v0.5.0 pure upstream** (no local patches). Binary at `/usr/local/bin/zmx`, 9086224 bytes. Previous local patch `c863651` (leader-on-resize) was removed because it caused resize storms without reliably delivering its promised "switch without typing" behavior. Rollback binary at `/usr/local/bin/zmx.bak-v0.4.2-20260418`. See §Known-good-state for full details.
- **Only one patch we tried was safe and worth re-applying**: Patch 1 (client-side `\x1b[3J` in the attach clear_seq). It fixes the 5× on-reattach duplication and has no trade-offs. The other four patches (2, B, C, D) are documented here specifically so nobody wastes time reinventing them.

## Stack recap

```
Mac (VS Code terminal)        Mobile (Moshi)
  ↓ ET (TCP 2022)                ↓ mosh (UDP)
VM (GCP)                       VM
  ↓ zmx attach NAME claude       ↓ tmux → zmx attach NAME
  shared zmx daemon → PTY → Claude
```

Both clients attach to the same zmx daemon. The daemon runs Claude in a single PTY. zmx broadcasts Claude's output bytes to every attached client; each client's terminal (VS Code xterm.js, or tmux pane) renders independently.

## Known issues

### 1. Scrollback duplicates on every re-attach

**Symptom:** re-opening a session shows N× copies of the session history stacked.
**Root cause:** zmx replays its stored scrollback + visible state to any new client on attach. The client's terminal already had content (from a previous attach), so the replay's text appends — each reconnect multiplies it.
**Fix:** Client emits `\x1b[3J` (plus `\x1b[2J\x1b[H`) before connecting the socket, so the replay lands on a clean canvas. Upstream clear_seq is only `\x1b[2J\x1b[H` — lacks `\x1b[3J`. A one-line local patch in `main.zig` adds the 3J. **As of 2026-04-18 this patch is NOT installed** (we reverted yesterday's experiments). Re-applying it is safe and has no trade-offs.

### 2. ~50–70 line "artifact from previous device" on Mac after switching

**Symptom:** top of Mac's visible area (or scrollback) shows Claude's render from the previous device's size — including the character typed to trigger the switch.
**Root cause:** Ink's `log-update` tracks its own "last-rendered height" and on SIGWINCH erases exactly that many rows before writing the new frame. Rows past that height retain stale bytes. Upstream Ink/Claude-Code bug.
**Tracked upstream:** [claude-code #6481](https://github.com/anthropics/claude-code/issues/6481), [#18493](https://github.com/anthropics/claude-code/issues/18493), [#9727](https://github.com/anthropics/claude-code/issues/9727), [#29937](https://github.com/anthropics/claude-code/issues/29937).
**No clean zmx-layer fix.** Any broadcast of `\x1b[2J` wipes Claude's `<Static>` conversation forever; `\x1b[3J` alone only clears scrollback which doesn't contain the stale visible cells.

### 3. Mobile tmux scrollback fills with duplicate session content

**Symptom:** mobile scrolling shows the same session content multiple times.
**Root cause:** every leader change (triggered on each keystroke via upstream `isUserInput` + local `c863651` leader-on-resize) resizes the PTY. Claude SIGWINCHes and emits a full TUI frame at the new size. That frame is broadcast to every client including mobile's tmux. Tmux pane is at mobile size; Claude's frame is at Mac size → misaligned bytes pile into tmux's scrollback.
**No clean fix** for the same reason as issue 2 — wiping tmux scrollback kills `<Static>`.

### 4. Leader-on-resize feedback loop — RESOLVED

**History:** local patch `c863651` auto-promoted any resizing client to leader. Combined with the upstream user-input detector, each keystroke from a non-leader bounced leader → requested the client's size → PTY resize → Claude SIGWINCH → full repaint broadcast. This was the main accelerant for issues 2 and 3.

**Resolved 2026-04-18:** patch removed. Leader now changes only on genuine user input (upstream `isUserInput` via libghostty parser). Expected behavior: when switching devices, press any key on the new device to hand over leadership. Issues 2 and 3 still exist whenever a real leader change triggers a PTY resize (can't be eliminated without upstream Claude-Code fixes), but the storm of per-keystroke resizes is gone.

### 5. Copy-mode trap on mobile

**Symptom:** typing suddenly stops reaching Claude; Enter does nothing; can't see keystrokes.
**Root cause:** `set -g mouse on` + `tmux-better-mouse-mode` plugin = wheel-up enters copy-mode. If scrollback is empty (common with wipes), the pane is in copy-mode with no visual cue, and all keys are consumed by tmux.
**Unstick:** press `q` or run `tmux send-keys -t <session> q`.
**Avoidance:** either remove `tmux-better-mouse-mode` or rebind `WheelUpPane` to not auto-enter copy-mode.

### 6. NO_FLICKER is misleadingly "commented out" but actively applied

`~/.bashrc` has `# export CLAUDE_CODE_NO_FLICKER=1` with a comment saying "Leave disabled." But the variable IS set for every new zmx session because:

- `~/.zx-env` exports it (the Mac-side ET wrapper — currently the `x` function in `~/.zshrc` — sources this over ET; historically named `CVM_ET()`)
- tmux server global env has it (persisted from when a tmux session was started with the variable in scope, survives bashrc changes)

Net effect: NO_FLICKER=1 is always injected into Claude. The bashrc comment was updated 2026-04-18 to reflect reality. If we ever actually want it off, we must unset in BOTH `~/.zx-env` AND `tmux set-environment -g -u CLAUDE_CODE_NO_FLICKER`, AND kill existing zmx daemons so their cached env goes away.

## Anatomy of a device switch

1. User types a character on Mac (already attached). Mac's zmx-client sends it to the daemon.
2. Daemon's `handleInput` sees the byte. Calls `util.isUserInput()` (libghostty parser). If true, promotes Mac's client to leader via `setLeader`.
3. `setLeader` sends a Resize IPC message _back_ to the new leader asking for its size.
4. Mac's client responds with its terminal dimensions.
5. Daemon's `handleResize` runs. With the local `c863651` patch, any _other_ client that sends a resize would also be auto-promoted — but in this flow Mac is already leader, so it just does `ioctl(TIOCSWINSZ)` with Mac's size.
6. PTY size changes. Claude (running in the PTY) receives SIGWINCH.
7. Ink's resize handler fires. Re-renders the whole React tree. `log-update` erases N rows (its last-known render height) and writes the new frame.
8. Claude's output bytes flow up the PTY → zmx daemon → broadcast to every attached client. Each client's terminal writes the bytes; rows past their own viewport scroll into their scrollback.
9. Mobile's tmux, being at a different size than Mac, receives the Mac-sized frame in its smaller pane → misalignment → scrollback grows.

## Patches attempted on 2026-04-17 (all reverted except Patch 1 also reverted)

- **Patch 1** — client-side clear_seq adds `\x1b[3J` before connect. Fixed issue 1. **Reverted on 2026-04-18 as part of "back to pre-scroll-session state."** Re-apply whenever.
- **Patch 2** — daemon broadcasts `\x1b[3J` to all clients on size-changing resize. Destroys `<Static>` conversation. Reverted.
- **Patch B** — IPC protocol extension adding `wraps_own_scrollback` flag so Patch 2 could skip tmux clients. Infrastructure was fine; depended on Patch 2's broken premise. Reverted.
- **Patch C** — deferred single-shot `\x1b[3J` 300ms after resize, quiescence-extended. Same "destroys Static" problem. Reverted.
- **Patch D** — pre-resize broadcast of `\x1b[2J\x1b[3J\x1b[H` to wipe visible too. Killed all scrollback on Mac; user could only scroll one row. Reverted.

Common thread: **you cannot safely wipe scrollback or visible area during a live session** without destroying conversation history that Claude cannot re-emit.

## What would actually fix this (upstream)

1. Claude Code adopts DECSET 2026 (synchronized output) around TUI re-renders — tracked in [claude-code #37283](https://github.com/anthropics/claude-code/issues/37283). Terminal buffers the update; no intermediate visible state; no scrollback growth from repaints.
2. Ink's `log-update` tracks full emitted height including anything that scrolled off, not just its last `writeFrame` height. Eliminates stale cells past tracked-height.
3. Claude Code treats conversation content as idempotent and re-emittable (not one-shot `<Static>`) so any wipe is recoverable.

Realistically (1) is the most tractable; it's the Anthropic team's call.

## Known good state (2026-04-18, late-day)

- zmx: **v0.5.0 pure upstream, no local patches**. Binary at `/usr/local/bin/zmx`, 9086224 bytes. Branch `main` at `origin/main`. No local branches.
- `~/.zx-env`: exports NO_FLICKER=1, DISABLE_NONESSENTIAL_TRAFFIC=1, DISABLE_TERMINAL_TITLE=1.
- tmux server env: all three set.
- Mac `~/.zshrc` ET wrapper (`x` function, formerly `CVM_ET()`): sources `~/.zx-env` over ET before running the command.

Lives with issues 2 and 3. Issue 1 (scrollback dup on re-attach) is present because Patch 1 isn't installed. Issue 4 (leader-on-resize resize storm) is **resolved** — the local patch that caused it was removed. Leader now only changes on actual user input (upstream `isUserInput`), which means you must type a key to hand leadership to a new device (no auto-switch). In practice this was already the observed behavior even with the patch installed.

## Related issues

- [claude-code #826](https://github.com/anthropics/claude-code/issues/826) — scroll reset during generation
- [claude-code #1413](https://github.com/anthropics/claude-code/issues/1413) — laggy scroll with history
- [claude-code #6481](https://github.com/anthropics/claude-code/issues/6481) — window resize shenanigans
- [claude-code #9727](https://github.com/anthropics/claude-code/issues/9727) — resize breaks UI rendering
- [claude-code #18493](https://github.com/anthropics/claude-code/issues/18493) — content loss when shrinking
- [claude-code #29937](https://github.com/anthropics/claude-code/issues/29937) — tmux rendering corruption
- [claude-code #37283](https://github.com/anthropics/claude-code/issues/37283) — missing DECSET 2026 sync output
- [EternalTerminal #178](https://github.com/MisterTea/EternalTerminal/issues/178) — heavy scroll freezes
- [xterm.js #1805](https://github.com/xtermjs/xterm.js/issues/1805) — excessive mouse-wheel scroll
