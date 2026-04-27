# GEAR migration probe — round 3 plan

**Date:** 2026-04-26
**Plan:** verify two P0 mechanics flagged by reviewer of v2 proposal before approving migration
**Round 1 results:** [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md)
**Round 2 results:** [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md)
**v2 proposal:** [`gear-migration-proposal-2026-04-26-v2.md`](./gear-migration-proposal-2026-04-26-v2.md)

## Context

The reviewer of v2 flagged two unverified P0 mechanics. Both have been independently confirmed against Google's documentation as genuine gaps.

1. **Per-turn `sessionState` mutability for follow-up turns.** The round-2 [R2.3](./gear-probe-results-round2-2026-04-26.md) probe proved create-time `sessionState` persists _unchanged_ across two `stream_query` invocations on the same session. In production, `runId`/`turnIdx`/`attempt` change every turn — without a verified mutation mechanism, every follow-up turn's plugin callbacks would carry the _first_ turn's metadata, mis-attributing all events. The publicly documented `sessions.patch` primarily targets `displayName`; `sessionState` mutability is a known pain point on Google's developer forum.

2. **Cloud Function handoff with `streamQuery`.** v2 says `agentStream` "fires off the streamQuery and returns 202" — i.e., Agent Runtime continues server-side after the Cloud Function terminates. Firebase docs are explicit: _"Any code run after graceful termination cannot access the CPU and will not make any progress... background activity may resume on a future invocation interfering with the new request."_ Round-1 [Test 1](./gear-probe-results-2026-04-26.md) verified the platform survives external `kill -9` of a Python process holding the TCP connection — that is NOT the same failure mode as a Firebase Cloud Function returning from its handler.

R3 closes both gaps with one targeted experiment each. ~2–3 hours total. Outcome determines whether v2 is safe to implement, needs amendments, or has to fall back to a thin-worker hybrid.

## Decision contract

**Important framing:** R3.2's gate is the **explicit-abort variant**, not a leave-open fetch. A leave-open fetch would only prove that _sometimes_ dangling background activity survives Cloud Function termination, which Firebase docs explicitly warn against ("background activity may resume on a later invocation interfering with the new request; network access after termination often resets"). The migration design must rest on a _supported_ clean handoff — `reader.cancel()` + `AbortController.abort()` before `res.status(202).send()`, then verify Agent Runtime continues. The leave-open behaviour is captured separately as a diagnostic, but it is not the gate.

| R3.1 | R3.2 (explicit-abort)        | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ---- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PASS | PASS                         | Approve migration. Write v3 incorporating R3-confirmed mechanics + reviewer P1/P2 corrections.                                                                                                                                                                                                                                                                                                                                                               |
| PASS | FAIL (clean abort kills run) | Direct CF→Agent-Runtime handoff is not a supported pattern. Re-architect cutover path: Cloud Tasks → thin worker holds streamQuery, plugin still writes Firestore. The hybrid the user originally rejected becomes the only safe path; re-evaluate cost-benefit in light of empirical evidence. (The leave-open diagnostic, if it happens to "pass," does NOT save this row — undefined behaviour is not a foundation for production.)                       |
| FAIL | PASS                         | **Migration not approved.** R3.1 fail means our `session.state` metadata propagation mechanism doesn't work for follow-up turns. Candidate workarounds (message-text encoding, keyed Firestore lookup by `invocation_id`, etc.) are _unverified designs_. Hold migration; design a replacement and probe it (call it R4) before re-approving. Message-text encoding in particular is unattractive because it pollutes the prompt path the LLM actually sees. |
| FAIL | FAIL                         | Migration not safely implementable in current platform shape. Stay on existing runtime; document the two blockers and the platform-feature requests they imply. Re-evaluate when Google ships either feature.                                                                                                                                                                                                                                                |

Reviewer P1/P2 fixes (session-stickiness routing via `transport: 'cloudrun' \| 'gear'` field, `adkSessionId` deletion sequencing, plugin-owned heartbeat asyncio task, write-class taxonomy, dependency adds, recommendation-section narrative correction) fold into v3 regardless of R3 outcome.

## R3.1 — per-turn `sessionState` mutability

**Probe agent:** reuse the existing `kitchen` probe (resource `projects/907466498524/locations/us-central1/reasoningEngines/3851695334971408384`). The `ProbePlugin` already reads `runId`/`attempt`/`turnIdx` from `invocation_context.session.state` and writes them to Firestore on every callback — exactly the production-intended mechanism we need to verify mutates correctly.

**Doc-isolation prerequisite:** the existing plugin writes per-callback docs to `probe_runs/{sid}/events/` with auto-IDs and no `invocation_id` field. The fresh-sid-per-run pattern (`se-r31-{ts}`) isolates R3.1 docs from prior R1/R2 runs, but does NOT isolate turn 1 from turn 2 within R3.1. Two changes to fix this:

1. **Update `agent/probe/probe_plugin.py`** to record `getattr(invocation_context, 'invocation_id', None)` in every doc (`before_run`, `event`, `agent_event`, `after_run`). 5-line change.
2. **Redeploy the kitchen probe** (`agent_engines.update(...)`, ~3.5 min) so the deployed plugin emits `invocation_id`-tagged docs.
3. **Belt-and-suspenders timestamp filtering**: the harness writes wall-clock marker docs to `probe_runs/{sid}/markers/turn1_started_at` and `…/turn2_started_at` with `firestore.SERVER_TIMESTAMP` immediately before each `async_stream_query`. Filter docs strictly by `ts >= turn2_started_at`.

**Test sequence:**

1. Create a fresh session via REST `:createSession?sessionId=se-r31-{timestamp}` with `sessionState={runId: 'r-1', turnIdx: 0, attempt: 1}`.
2. Write `markers/turn1_started_at`. Run `async_stream_query` (turn 1) on the kitchen probe with message `'fetch:https://example.com/'`. Capture the `invocation_id` from the first event in the response stream. Verify all plugin docs from this `invocation_id` carry `runId='r-1'`, `turnIdx=0`, `attempt=1`. Read final state via REST `:getSession`.
3. **Try state-mutation mechanisms in this order, stopping at the first one that propagates correctly. Use SDK-derived JSON shapes — do NOT hand-shape (REST is camelCase: `sessionState`, `stateDelta`, `invocationId`, `timestamp`):**
   - **(a)** REST `PATCH .../sessions/se-r31-...?updateMask=sessionState` with body `{"sessionState": {"runId": "r-2", "turnIdx": 1, "attempt": 1}}`. Capture full HTTP request + response (status, headers, body) verbatim.
   - **(b)** REST `:appendEvent` on the session — use the SDK's `Session`/`SessionEvent` model classes (e.g., `from google.cloud.aiplatform_v1beta1.types import SessionEvent`) to construct the request body, so the JSON shape is canonical. Body should carry `actions.stateDelta` (camelCase) with the new metadata. Capture full request + response.
   - **(c)** SDK `remote.async_update_session(...)` if exposed (`dir(remote)` to discover; if absent, skip).
   - **(d)** If none above, REST `:createEvent` or any other endpoint discovered via the v1beta1 reasoning-engine spec.
4. After whichever mechanism succeeded (HTTP-layer success), re-read state via REST `:getSession` to confirm the platform-side state actually changed to the new values.
5. Write `markers/turn2_started_at`. Run `async_stream_query` (turn 2) on the same session. Capture turn 2's `invocation_id`. Filter Firestore docs by `invocation_id == turn2_invocation_id` (primary) AND `ts >= turn2_started_at` (sanity check). Verify plugin docs from turn 2 carry `runId='r-2'`, `turnIdx=1` — the _new_ values.

**Pass criterion:** Step 5 plugin docs (filtered to turn 2's invocation_id) show `runId='r-2'` AND `turnIdx=1`. Both required — plugin sees the per-turn-mutated state.

**Fail criterion:** Step 5 plugin docs still show `runId='r-1'` (turn-1 state persisted into turn 2 callbacks), OR step 3 found no mechanism that mutated state at the HTTP layer (all four attempts returned errors), OR step 4's `:getSession` re-read still shows turn-1 state.

**Inconclusive:** Step 3 mechanism succeeded at HTTP layer (200 OK) but step 4's `:getSession` shows state didn't actually mutate. Try the next mechanism in the list before declaring fail.

**Document:** the exact REST request body that worked (or all four bodies if all failed) plus exact response bodies. This becomes the migration plan's "how to update per-turn metadata" recipe — or, if all four fail, the input to R4's design.

## R3.2 — Cloud Function handoff with streamQuery

**Probe agent:** the lifecycle probe (5-min `DeterministicSlowAgent`, resource `projects/907466498524/locations/us-central1/reasoningEngines/329317476414259200`). It produces 5 events spaced 60s apart and a clean terminal `after_run` — long enough that the CF returns within seconds of the first event, leaving ~4 minutes of post-CF-termination runtime to verify continuation.

**Two CF variants** — same agent, same upstream, different disconnect semantics:

**Variant A (gate variant — explicit clean abort):** `probeHandoffAbort` Cloud Function in `functions/index.js`:

1. Match production constraints: `onRequest({ cors: true, timeoutSeconds: 30 }, …)`. Same shape as `agentStream`.
2. Accepts POST with body `{sessionId: string}` (the lifecycle-probe sid for this run, pre-created by the test harness).
3. Construct an `AbortController`. Authenticates via `google-auth-library`.
4. Initiates `fetch('https://us-central1-aiplatform.googleapis.com/v1/{lifecycle-resource}:streamQuery?alt=sse', { signal: controller.signal, … })` with NDJSON body `{class_method: 'async_stream_query', input: {user_id: 'r32-abort', session_id: <body.sessionId>, message: 'go'}}`.
5. Reads bytes from the response stream until the first complete `\n`-terminated JSON line is parsed (proof of handoff).
6. Records the handoff timestamp via `Date.now()` and writes a marker doc to Firestore at `probe_runs/{sid}/markers/cf_returned_at` with `{variant: 'abort', ts: SERVER_TIMESTAMP, wall: Date.now()}`.
7. **`reader.cancel().catch(() => {})` — explicit reader teardown.**
8. **`controller.abort()` — explicit fetch abort propagating client-side cancellation to Agent Runtime.**
9. Returns `res.status(202).json({handoff: 'received_first_event_then_aborted', variant: 'abort'})`. No background work after this point — the fetch is provably cancelled before `res.send()`.

**Variant B (diagnostic — leave-open):** `probeHandoffLeaveOpen` Cloud Function. Same as Variant A but skips steps 7–8 (no `reader.cancel()`, no `controller.abort()`). Returns 202 with the fetch still pending. **This variant is informative-only — used to characterize platform behaviour, NOT as a migration gate.** Firebase docs explicitly describe this pattern as unsupported.

**Setup:**

1. Add `google-auth-library` as a direct dependency of `functions/package.json` (currently transitive through `@google-cloud/tasks`; that dependency might be removed during migration so we declare it explicitly).
2. Add both functions to `functions/index.js` (~80 LOC total). Both use `timeoutSeconds: 30` to match production.
3. Deploy: `firebase deploy --only functions:probeHandoffAbort,functions:probeHandoffLeaveOpen --project=superextra-site` (no other functions touched).

**Test sequence (run for each variant):**

1. From `agent/probe/run_r32.py`:
   - Create session `se-r32-{variant}-{ts}` via REST `:createSession?sessionId=…` on the lifecycle probe.
   - POST to the deployed `probeHandoffAbort` (or `probeHandoffLeaveOpen`) URL with `{sessionId: 'se-r32-{variant}-{ts}'}`.
   - Capture the CF's response body and wall-clock timestamp it returned.
2. Watch Firestore for `probe_runs/se-r32-{variant}-{ts}/events/`:
   - Expect: 1× `before_run`, 5× `event` (one per `DeterministicSlowAgent` step), 1× `agent_event`, 1× `after_run` — same 8-doc shape as round-1 Test 1.
   - Pull the `cf_returned_at` marker.
   - Pull the `after_run` doc's server timestamp.

**Pass criteria (gate variant — `probeHandoffAbort`):**

- All 8 plugin docs land within 10 minutes of `cf_returned_at`.
- `after_run.ts > cf_returned_at + 60s` — proves Agent Runtime kept executing for ≥60s after the CF _explicitly cancelled_ the request and returned. This is the genuinely-supported handoff property the migration requires.

**Fail criteria (gate variant):** `after_run` never lands within 10 min, OR fewer than 5 `event` docs land (stream truncated mid-run after explicit abort).

**Diagnostic interpretation (leave-open variant):** record the same evidence (gap, doc count) but treat it as platform-behaviour data, NOT as a gate signal. Useful for understanding what happens in the undefined-behaviour territory Firebase warns about.

**Inconclusive (gate variant):** All docs land but timestamp gap <60s. Re-run with a longer-running probe.

**Repeat:** run gate variant twice from cold to rule out warm-instance caching effects. Both must pass.

**Document:** exact CF response timings; whether either variant exhibits Firebase's documented "background activity may resume on subsequent invocation" failure mode (check Cloud Logs for the leave-open variant on subsequent traffic).

## Probe artifacts to write

All under `agent/probe/` and `functions/` — incremental additions to existing R1/R2 scaffolding:

| File                          | Purpose                                                     | Notes                                                                                                                                |
| ----------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `agent/probe/probe_plugin.py` | Add `invocation_id` to every doc                            | 5-line change for R3.1 doc isolation; requires kitchen redeploy (~3.5 min).                                                          |
| `agent/probe/run_r31.py`      | R3.1 test runner                                            | Standalone script following the pattern of `run_round2.py`. Captures `invocation_id` from response stream and Firestore marker docs. |
| `agent/probe/run_r32.py`      | R3.2 test runner                                            | Creates session, invokes deployed CF (both variants), watches Firestore.                                                             |
| `functions/index.js`          | Add `probeHandoffAbort` + `probeHandoffLeaveOpen` functions | Temporary diagnostics. ~80 LOC total. Removed during cleanup via explicit `firebase functions:delete`.                               |
| `functions/package.json`      | Add `google-auth-library` as direct dependency              | Currently only transitive via `@google-cloud/tasks`; declare explicitly for the migration's longer-term use too.                     |

No new Reasoning Engine deployments needed — existing `kitchen` and `lifecycle` resources already have the right plugin and agent shape.

**Existing utilities to reuse:**

- `ProbePlugin` (`agent/probe/probe_plugin.py`) — already reads metadata from `session.state` and writes per-callback Firestore docs. No changes.
- `kitchen_sink.py` agent (`agent/probe/kitchen_sink.py`) — already has `fetch_external_url` tool; suitable for R3.1's turn invocations.
- `agent.py` → `lifecycle_root` (`agent/probe/agent.py`) — `DeterministicSlowAgent` already deployed; suitable for R3.2.
- `google-auth-library` already proven working in `functions/probe-stream-query.js` — same pattern in `probeHandoff`.
- `firestore.Client` patterns from `run_round2.py` for state polling.

## Verification

Each test produces a deterministic exit code from its harness and machine-verifiable evidence in Firestore. End-to-end verification:

```bash
# R3.1
cd /home/adam/src/superextra-landing/agent
export GOOGLE_APPLICATION_CREDENTIALS=/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json
export GOOGLE_CLOUD_PROJECT=superextra-site
PYTHONPATH=. .venv/bin/python -m probe.run_r31
# Exit 0 = PASS (turn-2 plugin docs show updated runId/turnIdx)
# Exit 1 = FAIL (turn-2 docs still show original values)
# Exit 2 = INCONCLUSIVE (mutation succeeded at HTTP but state read shows no change)

# R3.2 — first deploy the diagnostic CF
cd /home/adam/src/superextra-landing/functions
firebase deploy --only functions:probeHandoff --project=superextra-site
# Then run the test harness
cd /home/adam/src/superextra-landing/agent
PYTHONPATH=. .venv/bin/python -m probe.run_r32
# Exit 0 = PASS (after_run lands >60s after cf_returned_at)
# Exit 1 = FAIL (no after_run within 10 min of cf_returned_at)
# Exit 2 = INCONCLUSIVE (gap <60s, re-run with longer agent)
```

Cross-check Firestore directly:

```python
from google.cloud import firestore
fs = firestore.Client(project='superextra-site')
sid = 'se-r31-...'  # or se-r32-...
docs = list(fs.collection('probe_runs').document(sid).collection('events').stream())
for d in docs:
    print(d.to_dict())
```

## Logging

All findings appended to [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md) under a new top-level `# Round 3 — verifying P0 mechanics before v3` section. Same append-only format as rounds 1 and 2. Every action, blocker, and finding lands there as it happens. After R3 completes, summary report at `docs/gear-probe-results-round3-2026-04-26.md` (or `-2026-04-27` if execution slips into next day).

## Time and risk estimate

**Time:** 2–3 hours end-to-end:

- 30 min — write `run_r31.py`, run R3.1 with up to 4 mechanism attempts
- 30 min — add `probeHandoff` to `functions/index.js`, deploy to Firebase
- 30 min — write `run_r32.py`, create session, run twice from cold
- 30 min — analyze findings, write log entries
- 30 min — buffer for unexpected (CF deploy hiccups, IAM, etc.)

**Risk:** very low. R3.1 is read-mutate-read against an existing probe — no production code touched. R3.2 deploys ONE additional Firebase function alongside production with no traffic routing changes (existing `agentStream` is untouched). Both probes use existing Reasoning Engines; no new Agent Runtime deploys (so no 3.5-min provisioning waits).

**Failure modes for the probe itself:**

- CF deploy fails because of unrelated `functions/` issues (e.g., dependency mismatch). Fix the unrelated issue or temporarily set `engines.node` if needed.
- IAM permissions for the CF's runtime SA missing `aiplatform.user`. The default Firebase Functions SA may need a grant for calling `:streamQuery`. Document any grants needed.

## What R3 does NOT cover

For honesty about scope:

- **Workaround testing.** If R3.1 fails, R3 does NOT test message-text encoding or invocation-id Firestore lookup as alternatives. Those fall to v3 design.
- **Thin-worker fallback path.** If R3.2 fails, R3 does NOT prototype the Cloud Tasks → thin worker design. Falls to v3 redesign with revised cost-benefit.
- **Multi-user concurrency.** Tests use single sessions; cross-session interactions during high concurrency stay in scope for migration cutover phase, not R3.
- **Pricing impact.** Same as round 1/2 — out of scope.

## Cleanup

After R3 completes (regardless of outcome):

- [ ] **Delete deployed functions explicitly** — removing source from `functions/index.js` does NOT automatically delete the deployed function in Gen 2:
  ```bash
  firebase functions:delete probeHandoffAbort --region us-central1 --project=superextra-site --force
  firebase functions:delete probeHandoffLeaveOpen --region us-central1 --project=superextra-site --force
  ```
  Then remove the function definitions from `functions/index.js` and redeploy.
- [ ] R3 probe scripts (`run_r31.py`, `run_r32.py`) stay in repo as reference until migration completes; archive after.
- [ ] `probe_plugin.py` `invocation_id` change can stay — adding metadata to plugin docs is genuinely useful and doesn't conflict with anything. Do NOT roll back.
- [ ] No new Reasoning Engines deployed → no Agent Runtime cleanup needed (kitchen update was in-place).
- [ ] R3 test sessions (`se-r31-*`, `se-r32-*`) remain in their parent Reasoning Engines; will be deleted along with parent during the existing round-1/round-2 cleanup TODO.
- [ ] Optional: revert the `google-auth-library` direct-dependency add if migration is not approved. If approved, keep it — the migration's `agentStream` rewrite uses it.

## Critical files

- **Read** [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md) §R2.3 — confirms the create-time-state-persists-unchanged baseline R3.1 builds on
- **Read** [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md) — R1/R2 execution lessons (especially the IAM hunt and module-path discipline)
- **Reuse** [`agent/probe/probe_plugin.py`](../agent/probe/probe_plugin.py) — existing `ProbePlugin` reads `session.state` exactly as production FirestoreProgressPlugin will
- **Reuse** [`functions/probe-stream-query.js`](../functions/probe-stream-query.js) — proven Node `:streamQuery` recipe, copy-paste pattern for `probeHandoff`
- **Modify** [`functions/index.js`](../functions/index.js) — add `probeHandoff` (temporary, ~50 LOC, removed in cleanup)
- **Existing resources** in [`agent/probe/deployed_resources.json`](../agent/probe/deployed_resources.json) — `kitchen` and `lifecycle` are sufficient

## References

- [Vertex AI sessions.patch REST reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.reasoningEngines.sessions/patch) — primary candidate for R3.1 mechanism (a)
- [Vertex AI Sessions API overview](https://docs.cloud.google.com/agent-builder/agent-engine/sessions/manage-sessions-api) — `:appendEvent` and related endpoints for R3.1 mechanism (b)
- [How to update state once session is created in Agent Engine](https://discuss.google.dev/t/how-to-update-state-once-session-is-created-in-agent-engine/320488) — Google Developer forum thread confirming `sessionState` post-create mutability is an open question
- [Firebase Cloud Functions termination semantics](https://firebase.google.com/docs/functions/terminate-functions) — official guidance that background work after `res.send()` is unsupported
- [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md) — round-1 Test 1 evidence shape (238.8s gap) that R3.2 reuses
