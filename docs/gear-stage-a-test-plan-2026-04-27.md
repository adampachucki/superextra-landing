# GEAR migration — Stage A test plan

**Date:** 2026-04-27
**Branch:** `gear-migration` (15 commits ahead of main)
**Staging Reasoning Engine:** `projects/907466498524/locations/us-central1/reasoningEngines/1179666575196684288`
**Allowlisted UIDs:** `feadLLD5IuUrJNeQTPPu9QIg3wg1` (prod), `UqQvmOsaBifkwzzLBugbnYj8kUt2` (dev origin)
**`GEAR_DEFAULT`:** `'cloudrun'` at the time these smokes were defined; **flipped to `'gear'` (Stage B) after Smoke 1–4 + 6a passed.** Smoke 5 (non-allowlisted control) is consequently STALE — there is no "default-cloudrun" cohort to test against any more. See Smoke 5 note below.

**Companion docs:**

- [`gear-migration-implementation-plan-2026-04-26.md`](./gear-migration-implementation-plan-2026-04-26.md) (v3.10) — full implementation plan
- [`gear-migration-execution-log-2026-04-27.md`](./gear-migration-execution-log-2026-04-27.md) — execution status + decisions
- [`gear-post-review-fixes-plan-2026-04-27.md`](./gear-post-review-fixes-plan-2026-04-27.md) — post-review fixes (already shipped)
- [`gear-probe-results-round3-2026-04-26.md`](./gear-probe-results-round3-2026-04-26.md) — R3.2 verified 240s post-disconnect run continuation at the platform layer (Smoke 4 verifies this end-to-end)

---

## Three phases

1. **Phase 0** — Pre-flight CI sweep (5 min)
2. **Phase 1** — Live smoke matrix, gating (~45 min wall-clock)
3. **Phase 2** — Soak observation (week 1)
4. **Phase 3** — Pre-PR-to-main residuals (closes v3.9 P2 gap)

Stage A is "open" once Phase 1 is fully green; the soak runs through Phase 2; PR-to-main happens after Phase 3.

---

## Phase 0 — Pre-flight CI sweep

Already green at commit `dec05e4`. Only allowlist content has changed since (commits `cac5587` → `5636357` → `9718cf8`); a re-run is paranoia, but cheap and worth it before any live traffic.

```bash
npm run lint
npm run check
npm run test                                          # 59 pass
cd functions && npm test                              # 70 pass
npm run test:rules                                    # 22 pass
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v   # 226 pass
```

If any suite fails, stop and investigate before live testing.

---

## Phase 1 — Live smoke matrix (gating)

Six smokes. Numbers 1, 3, 5, 6a can fire in parallel if multiple browsers are available; #2 depends on #1; #4 should run after at least one of #1 or #3 has passed (so a baseline gear-success exists before stressing the disconnect path).

| #   | Name                                  | Origin / UID                                                    | What it proves                                                                                                               | Pass criteria                                                                                                                                                                 |
| --- | ------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Prod canary first-turn**            | `agent.superextra.ai/chat`, prod UID `feadLLD5...`              | End-to-end gear path works                                                                                                   | Session `transport='gear'`; reaches `status='complete'`; reply + sources + title rendered; agentStream logs show no `WARNING`/`ERROR` for this session                        |
| 2   | **Prod canary follow-up**             | Same session as #1                                              | `:appendEvent` stateDelta propagation; per-turn metadata in plugin                                                           | `turns/0002/events/...` populated; second terminal write succeeds; reply renders                                                                                              |
| 3   | **Dev canary first-turn**             | `http://34.38.81.215:5199/agent`, dev UID `UqQvmOsa...`         | Origin/auth-scoped session storage under gear (anon UIDs are per-origin; dev origin stores in different IndexedDB than prod) | Same as #1 from the dev origin                                                                                                                                                |
| 4   | **Disconnect survival**               | Either canary, fresh session                                    | The architectural bet — R3.2's 240s post-disconnect proof end-to-end with prod agent code                                    | Start session, wait for first progress event, close tab. Wait 10 min. Reopen `?sid={sid}`. Confirm `status='complete'`, all events visible, no `error` field, reply rendered. |
| 5   | **Non-allowlisted control**           | Incognito + anon auth (different UID)                           | Stage A is contained; allowlist-miss honored                                                                                 | Session `transport='cloudrun'`; routes through existing Cloud Run worker; completes normally                                                                                  |
| 6a  | **Legacy session sticky on cloudrun** | A non-allowlisted user's existing pre-`transport`-field session | v3.9 P1 fix in the wild — legacy sessions don't re-route to gear                                                             | Follow-up turn on an old session stays `transport=undefined`/`'cloudrun'`; routes through worker                                                                              |
| 6b  | New allowlisted session uses gear     | (covered by #1 and #3 — no separate run)                        | —                                                                                                                            | —                                                                                                                                                                             |

### Smoke 1 + 3 recipe (canary first-turn)

1. Open the relevant origin in a fresh browser tab.
2. Sign in (anon flow is fine; the UIDs above are anon-origin-scoped).
3. Submit a deep query. Suggested: _"What's the menu like at Bistro Le Lucet in Brussels?"_ — produces a multi-specialist run with grounding sources.
4. Within ~1s, confirm chat panel renders (Phase 6 optimistic UX).
5. Open Firestore console (or `gcloud firestore documents ...`) on `sessions/{sid}` — confirm `transport: 'gear'`.
6. Watch progress events stream over 7–15 min.
7. On completion, confirm:
   - Reply populated, no truncation
   - Sources panel populated
   - Title generated
   - Session `status: 'complete'`
8. Cloud Logging filter: `resource.type="cloud_function" resource.labels.function_name="agentStream" jsonPayload.sessionId="{sid}"` — confirm only `INFO` lines, no `WARNING`/`ERROR`.

### Smoke 2 recipe (follow-up)

On the just-completed Smoke 1 session:

1. Send a follow-up query, e.g. _"What about vegetarian options there?"_
2. Confirm the chat panel updates immediately (existing session, no optimistic flow needed).
3. In Firestore: `sessions/{sid}/turns/0002` should appear with `status: 'running'`, then events stream into `turns/0002/events/...`.
4. Confirm `session.state` (visible via `:getSession` REST call or Reasoning Engine logs) shows `runId` and `turnIdx=2` — proves `:appendEvent` stateDelta worked.
5. Final state: `turns/0002.status: 'complete'` with reply + sources.

### Smoke 4 recipe (disconnect survival) — load-bearing

The R3.2 probe verified the platform survives caller disconnect for ≥240s. This smoke proves the same end-to-end with the production agent + plugin + Firestore writes.

1. Sign in as an allowlisted UID (prod or dev).
2. Submit a deep query. Capture the `sid` from the URL after Phase 6 optimistic flip.
3. Wait for first progress event in the timeline (~30–60s).
4. **Close the browser tab.**
5. Wait 10 min (production agent runs are 7–15 min; 10 min hits the typical completion window).
6. Open `https://agent.superextra.ai/chat?sid={sid}` (or dev equivalent).
7. Confirm:
   - Reply present, complete (no `[truncated]` or empty)
   - All timeline events visible from the run
   - Session `status: 'complete'`
   - No `error` field on session or any turn doc
8. Spot-check a few timeline event timestamps — they should span the disconnected window (i.e., events were written by the plugin while the tab was closed).

If this fails, the migration's value proposition is not realized; debug before continuing.

### Smoke 5 recipe (non-allowlisted control) — STALE under Stage B

> **Stage B note (2026-04-27):** `GEAR_DEFAULT='gear'` shipped, so non-allowlisted UIDs now route to `'gear'` by default — there is no "control" cohort to verify containment against any more. This smoke was meaningful only while `GEAR_DEFAULT='cloudrun'` and is preserved here as historical record. To re-run it under Stage B, temporarily flip `GEAR_DEFAULT` back to `'cloudrun'` (which is what the rollback drill exercises).

1. Open an incognito browser window. Anon-auth produces a different UID than the allowlist.
2. Submit a query.
3. In Firestore: confirm `sessions/{sid}.transport: 'cloudrun'`.
4. Verify Cloud Run worker (`superextra-worker`) receives traffic via Cloud Tasks.
5. Confirm normal completion (`status: 'complete'`, reply + sources rendered).

This proved containment under Stage A: only allowlisted UIDs hit GEAR; everyone else stayed on the legacy worker.

### Smoke 6a recipe (legacy session sticky)

The hardest scenario to set up but the most important for the v3.9 P1 fix.

1. Find a session in Firestore created BEFORE 2026-04-27 (or before commit `9038932` which introduced the `transport` field). Look for sessions where the `transport` key is missing entirely (not just `'cloudrun'` — _missing_).
2. Sign in as that session's owner (must NOT be in `GEAR_ALLOWLIST` — otherwise the allowlist-hit path overrides the legacy preservation logic).
3. Send a follow-up turn on that session.
4. Confirm:
   - Session doc still has no `transport` field after the follow-up txn (`t.update` doesn't add one)
   - The follow-up routes to Cloud Run worker, not gear
   - Final `status: 'complete'`

If this routes to gear, the v3.9 P1 fix has regressed and the agentStream txn capture logic needs review.

---

## Capturing results

Append a one-line entry per smoke to `docs/gear-migration-execution-log-2026-04-27.md` under a new "Stage A canary results" section:

```
SmokeN (Name): sid=<sid> uid=<uid> transport=<gear|cloudrun> status=<complete|error> events=<count> elapsed=<min> notes=<freeform>
```

Example:

```
Smoke1 (Prod canary first-turn): sid=abc123 uid=feadLLD5... transport=gear status=complete events=14 elapsed=9.2 notes=clean run, no warnings
```

If any smoke fails: capture the failure mode, the Cloud Logging timestamp range, and the affected `sid`. Do NOT proceed to the next smoke until the failure is understood.

---

## Phase 2 — Soak observation (week 1)

Stage A is "open" once Phase 1 is green. The soak then runs for ~1 week with the allowlist unchanged.

### Daily watch items

- **Cloud Logging warnings on agentStream:**

  ```
  resource.type="cloud_function"
  resource.labels.function_name="agentStream"
  severity>=WARNING
  ```

  Expected: zero. Anything that appears here is a candidate for investigation.

- **Stuck running sessions:** Firestore query for `transport='gear' AND status='running' AND <now - lastEventAt> > 20 minutes`. The watchdog (every 2 min) should flip these to `status='error'` with reason `pipeline_wedged` after 5 min of stale `lastEventAt`. If anything sits past 20 min, the watchdog isn't firing or the lastEventAt updates aren't happening — both are bugs.

- **Reasoning Engine cost:** check GCP billing at midweek. Worker traffic for allowlisted UIDs has dropped to near-zero (Cloud Run scales down); Reasoning Engine compute should appear as a new line item. Sanity-check magnitude per-turn against the old worker — order-of-magnitude difference warrants a pause and cost analysis.

- **Subjective agent quality:** answer quality on real queries. The migration is supposed to be invisible to users; if answers feel different (shorter, less grounded, missing sources, weird formatting), something's drifted in the deployment. Compare against pre-migration sessions on the same topic if needed.

### Rollback triggers

Roll back IMMEDIATELY (drop UIDs from `GEAR_ALLOWLIST`, redeploy) if:

- Any allowlisted-UID session reaches `status='error'` with no clear user-facing cause
- Cloud Logging shows >2 distinct error types from agentStream's gear branch
- Cost per turn is >2× the cloudrun baseline
- Watchdog catches a stuck `running` session that wasn't already errored by the plugin

Roll back DEFENSIVELY (drop UIDs, observe, then decide) if:

- Subjective quality regresses
- Latency-to-first-event is consistently >2× the cloudrun baseline (~60s vs 30s is fine; 120s+ is not)

Rollback steps (sub-minute):

```bash
# Edit functions/index.js — remove UIDs from GEAR_ALLOWLIST (or comment out)
# Then:
firebase deploy --only functions:agentStream --project=superextra-site
```

Existing allowlisted sessions stay sticky (per-session `transport='gear'` continues to route through gear), so an in-progress run is never rerouted; only NEW sessions get the allowlist-disabled treatment.

---

## Phase 3 — Pre-PR-to-main residuals

Before opening the PR (only after Phase 2 is clean):

1. **Re-run Phase 0 CI sweep.** Test counts unchanged from `dec05e4`.
2. **v3.9 P2 Chrome MCP smoke** (closes the residual gap flagged in the post-review):
   - Dev server `http://localhost:5199/agent` (cloudrun path is fine; the v3.9 P2 catch is transport-independent)
   - Sign in, click into a chat input
   - In Chrome DevTools MCP: `emulate({offline: true})` to force offline
   - Submit a query
   - Confirm: chat state rolls back to `'idle'`, `activeSid` clears, no orphan session selected
   - Capture screenshot to `docs/gear-phase6-p2-smoke-2026-04-27.png`
   - Restore: `emulate({offline: false})`
3. **Append PR description** with:
   - Branch commit count (15 + post-review + Stage A allowlist commits)
   - Phase 1 smoke results table (the 6-row table with sids and outcomes)
   - Phase 2 soak duration + any rollback events
   - Phase 3 v3.9 P2 screenshot reference
   - Link to this test plan

> **Historical (2026-04-27):** the original sequencing here said Stage B (`GEAR_DEFAULT='gear'`) would flip _after_ PR merge. In practice Stage B shipped the same day as Stage A (commit `f4ff1bf`), before PR #10 was opened, because all Stage A smokes ran clean and Adam waived the soak window. PR merge to main now happens with Stage B already live; the only step still gated on the rollback window is Phase 9 cutover (worker decommission + field migration + `agent/probe/` archival).

---

## Estimated wall-clock for Phase 1

If parallelizable (multiple browsers, multiple sessions concurrent):

- Smokes 1, 3, 5, 6a fire concurrently, ~15 min each
- Smoke 2 sequential after 1 completes, ~10 min
- Smoke 4 includes a 10-min disconnect wait, ~15 min total
- **Total: ~40–50 min**

If fully serial:

- 6 smokes × ~10–15 min each = ~70–90 min

---

## Out of scope for Stage A

Documented for clarity; revisit at Phase 9 cleanup or a future iteration:

- **Forced gear handoff failure path** (deliberately broken `GEAR_REASONING_ENGINE_RESOURCE` to verify `gearHandoffCleanup` cleanup) — covered well by `gear-handoff.test.js` unit tests; provoking a real 502 in production logs creates noise that needs explanation later. Skip.
- **Watchdog manual trigger** — assumed working; observable through Phase 2 if any stuck sessions appear.
- **End-to-end gear path under high concurrency** — Stage A is single-user (allowlisted operator); concurrency surface is exercised at Stage B default flip, not here.
- **Memory Bank integration** — explicitly deferred per the implementation plan.

---

## Retrospective (2026-04-28)

One process scar from this plan worth recording:

**Any "X is contained" smoke must verify the contained X actually works end-to-end (`status='complete'`), not just that routing landed (`status='running'`).**

Smoke 5 ("non-allowlisted control") asserted only that a non-allowlisted submission landed at `transport='cloudrun'` and reached `status='running'` on the legacy worker. It did NOT wait for `status='complete'`. Result: when the global plugin registration in `agent/superextra_agent/agent.py` started shorting the worker pipeline (the `runId`-missing halt-content path), the regression sat undetected for hours. Smoke 5 passed; cloudrun was actually broken.

Going forward, any "containment" smoke gets the same finish criteria as the happy path: terminal state with the expected reply shape. The cost (a few extra minutes per smoke) is small relative to discovering a silently-broken rollback path mid-incident.
