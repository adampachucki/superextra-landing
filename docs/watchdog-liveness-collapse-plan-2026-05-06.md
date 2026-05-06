# Watchdog liveness — collapse `lastHeartbeat` + `lastEventAt` into one signal

**Date:** 2026-05-06
**Owner:** Adam (PM); execution: Claude
**Status:** Plan — not yet implemented

## Problem

The watchdog (`functions/watchdog.js`) flips a `running` session to
`status='error'` with `error='pipeline_wedged'` when `lastEventAt` on the
session doc is more than 5 minutes stale. The intent stated in the file
comment is:

> running, lastEventAt > 5 min → pipeline_wedged. Heartbeat fresh but no
> ADK events — specialist stuck on a hung tool call, etc.

That intent breaks for legitimate Gemini grounded-search calls.

### Concrete incident — session `0160ac51-2c02-458e-aa7d-fbecba2e79c7`

Timeline (UTC, 2026-05-04):

- `19:27:31` — session created, run `0163fa85…` claimed
- `19:31:08` — last `lastEventAt` bump
- `19:36:35` — last `lastHeartbeat` tick (worker alive)
- `19:37:02` — **watchdog flipped status → error** (`pipeline_wedged`,
  `lastEventAgeMs ≈ 353 374`)
- `19:38:46` — a single Gemini event landed and exploded into 49
  `Searching the web` timeline rows in one burst, all sharing
  `event_id = 04bf882a…` and indices 0–48

Diagnosis. The research lead made a `google_search`-grounded Gemini call
that ran ~7.5 minutes inside Gemini and returned 49
`web_search_queries` in one response. ADK only fires `on_event` when
Gemini emits an event, so `firestore_progress.on_event_callback`
(`agent/superextra_agent/firestore_progress.py:494-553`) — the only path
that bumps `lastEventAt` — never ran during the call. The 30 s
heartbeat task kept `lastHeartbeat` fresh, so the worker was clearly
alive; the `pipeline_wedged` rule fired anyway because it watches
`lastEventAt` only.

This is not a one-off. As we lean harder on grounded research, more
turns will sit inside long inline Gemini calls, so this false positive
will get more common.

## Goal

Eliminate the false positive without losing the watchdog's real job —
catching abandoned `running` sessions whose worker is gone — and reduce
the surface area of the liveness machinery while we are in there.

## Explored solutions

### Option A — keep two fields, raise the `lastEventAt` threshold

Change `LAST_EVENT_MAX_AGE_MS` from 5 min to ~10 min so a 7-minute
Gemini call no longer trips it.

- Pros: smallest diff. Preserves the "stuck tool, alive heartbeat"
  signal as a distinct error reason.
- Cons: arbitrary number; still fragile as Gemini does more inline
  work per call. Doesn't address the underlying redundancy of two
  liveness fields tracking essentially the same thing.

### Option B — heartbeat also bumps `lastEventAt` (keep both rules)

Have the 30 s heartbeat task write `lastEventAt` alongside
`lastHeartbeat`.

- Pros: removes the false positive immediately. Heartbeat already proves
  liveness; this just makes `lastEventAt` reflect that.
- Cons: leaves dead code behind. The `pipeline_wedged` rule would only
  fire when the heartbeat task itself dies, but `heartbeat_lost` (10
  min) catches that case too. Two rules, one underlying signal — pure
  redundancy.

### Option C — collapse to one liveness field, one watchdog rule (recommended)

Have the heartbeat write a single `lastActivityAt` (or keep the name
`lastEventAt`); ADK event handling also writes the same field; delete
`lastHeartbeat` and the second watchdog rule.

- Pros: one mental model — "is this session still alive?" — answered by
  one field with one threshold. Removes ~60–80 LOC across the
  watchdog, the progress plugin, the agentStream init, and tests.
  Eliminates the false positive by construction.
- Cons: loses the ability to distinguish "container died" from "main
  coroutine wedged on a tool" in the error reason. In practice both
  outcomes are the same to the user (run is dead, retry); diagnostic
  value lives in Cloud Trace, not the field name.

### Option D — kill the watchdog entirely, rely on per-tool timeouts

Push timeout enforcement into the agent process itself.

- Pros: addresses hung tools at the source.
- Cons: doesn't help with crashed workers — `running` sessions whose
  process is gone would stay `running` forever. Watchdog is still
  needed as a backstop. Strictly more code, not less.

## Recommended approach — Option C

Collapse `lastHeartbeat` and `lastEventAt` into a single field. Keep
the heartbeat task (it provides the liveness ticks). Keep one watchdog
rule with one threshold. Pick **5 minutes** as the threshold, since the
heartbeat now keeps the field fresh and any staleness > 5 min really
does mean the worker is gone.

Field name: keep `lastEventAt` to minimise churn (Firestore doc shape,
indexes, frontend, tests all reference it). Treat the heartbeat tick
as just another "event."

### What changes

- `functions/watchdog.js`
  - Drop the `heartbeat` query from `findStuckSessions`. Three
    parallel queries become two (`queued` + `running by lastEventAt`).
  - Drop the `heartbeat_lost` classifier branch.
  - Drop `HEARTBEAT_MAX_AGE_MS`.
  - Trim the top-of-file comment block from three thresholds to two
    (queued, running).
  - Net: ~25–30 LOC removed.
- `agent/superextra_agent/firestore_progress.py`
  - Heartbeat task writes `lastEventAt` instead of `lastHeartbeat`
    (single field write, same fenced-update path).
  - Remove `lastHeartbeat` from the claim transaction (`_fenced_txn`
    around line 88–95).
  - Remove `lastHeartbeat` references in `fenced_session_update`
    callsites and helper docstrings.
  - Net: ~5–10 LOC removed.
- `functions/index.js`
  - Drop `lastHeartbeat: null` from the initial session shape (around
    line 228).
  - Net: 1 LOC.
- `functions/watchdog.test.js`
  - Drop the `heartbeat_lost` test case and any mock plans keyed off
    `lastHeartbeat`.
  - Drop precedence-test branches that depend on heartbeat ordering.
  - Net: ~30–40 LOC removed.
- `agent/tests/`
  - Update any progress-plugin tests that assert `lastHeartbeat` is
    written. Replace with assertions on `lastEventAt`.
- `docs/deployment-gotchas.md` and watchdog plan refs
  - Update any prose that refers to two liveness signals.

Estimated total: ~60–80 LOC net deletion plus prose cleanup.

### Migration

Sessions in flight at deploy time were written under the old shape:
`lastHeartbeat` ticking, `lastEventAt` potentially stale. The new
watchdog will only look at `lastEventAt`, so an in-flight session that
hasn't had a real ADK event in > 5 min could be flipped immediately on
the first run after deploy.

Two ways to handle this safely; pick one:

1. **Drain.** Deploy at a low-traffic moment; accept that any in-flight
   session > 5 min since last event gets flipped. Realistic blast
   radius is small — most turns finish well under that.
2. **Transitional read.** Have the new watchdog rule read
   `Math.max(lastEventAt, lastHeartbeat)` for one deploy cycle, then a
   follow-up PR drops the `lastHeartbeat` read once no in-flight
   sessions written under the old shape can exist. More code in the
   short term; zero risk of flipping legit in-flight runs.

Recommended: option 1 (drain). The watchdog already wraps every flip
in a transaction that re-checks status and runId, so a worker that
completes between query and flip is not clobbered. The worst case is
a single user seeing a spurious error and hitting retry.

### Threshold check

With heartbeat ticking `lastEventAt` every 30 s, a healthy session's
`lastEventAt` is at most ~30 s stale. A 5 min threshold gives 10
heartbeat windows of grace before flipping — more than enough to
absorb transient Firestore write retries without flipping a healthy
session.

## Done when

- `npm run test` (Vitest) and `cd functions && npm test` both green
  with `lastHeartbeat` removed.
- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` green with the
  heartbeat task writing `lastEventAt`.
- Manual e2e: kick off a session that does a long grounded-search
  call (similar to the incident); confirm it completes without being
  flipped to `pipeline_wedged`.
- Reasoning Engine redeployed (`redeploy_engine.py --yes`) so the
  agent-side write change takes effect.
- Cloud Functions deployed via the normal `main` push.
- A follow-up scan of recent sessions in Firestore shows no
  `error='heartbeat_lost'` or `error='pipeline_wedged'` for sessions
  that were demonstrably making progress.

## Out of scope

- Per-tool timeouts inside the agent. Worth doing later as a defence
  in depth (catches hung tools without waiting for the watchdog), but
  not required to fix this incident and would expand the diff
  significantly.
- Renaming `lastEventAt` to `lastActivityAt`. Mechanical churn with
  no behavioural payoff.
- Changing the `queued` rule or the `handoff_start_timeout` reason.
  Those are unaffected.
