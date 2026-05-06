# Watchdog liveness — drop the `pipeline_wedged` rule

**Date:** 2026-05-06
**Owner:** Adam (PM); execution: Claude
**Status:** Plan — not yet implemented
**Reviewed by:** codex (independent), 2026-05-06

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

## Root cause

Two liveness fields tracking the same thing — "is the worker alive?" —
with different update cadences. `lastHeartbeat` is the actual liveness
signal (forced tick every 30 s by a dedicated task). `lastEventAt` was
sold as a second-tier signal ("worker is alive _and_ making progress")
but it only updates when Gemini emits an event, and Gemini's emission
cadence is bursty by design. The `pipeline_wedged` rule conflates "no
recent ADK event" with "wedged," which isn't true.

## Goal

Eliminate the false positive. Reduce surface area while we're in there.
No defensive hardening, no new fields, no migration.

## Explored solutions

### Option A — raise the `lastEventAt` threshold to 10 min

- Pros: smallest diff.
- Cons: treats the symptom. Same false positive returns the next time
  Gemini batches longer than the new threshold. Two liveness fields
  remain.

### Option B — heartbeat task also writes `lastEventAt` (collapse onto `lastEventAt`)

Heartbeat ticks both fields; `pipeline_wedged` becomes effectively dead
because `heartbeat_lost` (10 min) catches the same case `pipeline_wedged`
(5 min, now never stale during heartbeat ticks) was meant to catch.

- Pros: removes the false positive.
- Cons: agent-side write change, claim-shape change, semantic muddle
  (a heartbeat tick writing into a field called `lastEventAt`),
  in-flight migration risk, deployment ordering between Reasoning
  Engine and Cloud Functions.

### Option C — delete the `pipeline_wedged` rule, keep `lastHeartbeat` as sole running-liveness field (recommended)

The `lastEventAt` rule was the bug. Delete it. `lastHeartbeat` is
already the right signal — it's a forced 30 s tick that doesn't depend
on Gemini's emission cadence.

- Pros: smallest possible diff. Root-cause fix. No agent change. No
  claim-shape change. No migration — old and new in-flight sessions
  already use `lastHeartbeat`. No semantic muddle.
- Cons: loses "worker alive but main coroutine stuck on a tool" as a
  distinct error reason. Accepted: alive-but-no-events is no longer a
  watchdog failure mode.

### Option D — kill the watchdog entirely

Push timeouts into the agent.

- Pros: addresses hung tools at the source.
- Cons: doesn't help with crashed workers — `running` sessions whose
  process is gone would stay `running` forever. Watchdog still needed
  as a backstop. Strictly more code.

## Recommended approach — Option C

Delete the `pipeline_wedged` rule. `lastHeartbeat` becomes the sole
liveness field for `running` sessions. Threshold stays at 10 min — no
evidence to tighten it, and a fix is the wrong place to smuggle in
behavioural changes.

`lastEventAt` can stay on the doc as event metadata if it has
diagnostic value. It just stops driving liveness. Cleaning it out
entirely is a separate, optional follow-up.

### What changes

**Required (the actual fix):**

- `functions/watchdog.js` — ~22 LOC removed
  - Drop `LAST_EVENT_MAX_AGE_MS` constant.
  - Drop `eventThresholdMs` and `eventThreshold` derivations in
    `findStuckSessions`.
  - Drop the third query in the `Promise.all` (the `lastEventAt < `
    one). Three parallel queries become two.
  - Drop the `for (const doc of eventSnap.docs)` classifier block.
  - Trim the top-of-file comment from three thresholds to two.
- `functions/watchdog.test.js` — ~14 LOC removed
  - Drop the `pipeline_wedged` classification test (lines 170–183).
- `firestore.indexes.json` — ~7 LOC removed
  - Drop the `status + lastEventAt` composite index entry.

**Total: ~45 LOC removed, 0 added.**

Follow-up cleanup (separate PR, only if `lastEventAt` has no
diagnostic use): drop the field from the session init, the
`on_event_callback` bump, and the claim-transaction write. Out of
scope here.

### Migration

None. Old and new in-flight sessions already write `lastHeartbeat`
every 30 s. The watchdog change is backward-compatible by construction.

### Deployment

One push to `main`. CI deploys functions and indexes together. No
Reasoning Engine redeploy needed.

## Done when

- `npm run test` and `cd functions && npm test` green with the
  `pipeline_wedged` test removed.
- Cloud Functions deployed via the normal `main` push.
- Spot-check a recent long-grounded-search session in production:
  status reaches `complete`, no `pipeline_wedged` flip in the session
  history.

## Out of scope

- Per-tool timeouts inside the agent.
- Renaming `lastEventAt` to anything. Mechanical churn.
- Changing the `queued`/`handoff_start_timeout` rule. Unrelated.
- Tightening the heartbeat threshold from 10 min. No evidence.
- A `runningStartedAt` / `deadlineAt` max-runtime guard. Defensive
  hardening for a hypothetical case.

## Notes from review

The first draft of this plan recommended Option B (heartbeat writes
`lastEventAt`). Codex review surfaced that Option C is strictly leaner:
same end state (one running-liveness rule), but no agent change, no
migration, no semantic muddle. It also pushed back on a 5 min
threshold change that had no incident evidence behind it. Both
adopted.
