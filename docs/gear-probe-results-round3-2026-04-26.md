# GEAR migration probe — round 3 results

**Date:** 2026-04-26
**Plan:** [`gear-probe-plan-round3-2026-04-26.md`](./gear-probe-plan-round3-2026-04-26.md)
**Round 1 results:** [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md)
**Round 2 results:** [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md)
**Execution log:** [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md)
**Decision:** **MIGRATION APPROVED.** Both reviewer P0s resolved with timestamp-precise evidence. Write v3 plan incorporating R3 findings + reviewer P1/P2 corrections.

---

## Summary

| #    | Test                               | Variant               | Result             | Evidence                                                                                                                             |
| ---- | ---------------------------------- | --------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| R3.1 | Per-turn `sessionState` mutability | —                     | **PASS**           | `:appendEvent` with `actions.stateDelta` + RFC3339 timestamp; turn-2 plugin docs all carry `runId=r-2`, `turnIdx=1`                  |
| R3.2 | Cloud Function handoff (gate)      | explicit abort, run 1 | **PASS**           | Gap 240.6s between abort and `after_run`; full 8-doc shape                                                                           |
| R3.2 | Cloud Function handoff (gate)      | explicit abort, run 2 | **PASS**           | Gap 240.6s, identical to run 1 — repeatable                                                                                          |
| R3.2 | Cloud Function handoff (diag)      | leave-open            | informational PASS | Gap 240.4s — same behaviour as abort, but per Firebase docs this is undefined behaviour. Diagnostic only; gate is the abort variant. |

Both reviewer P0s now resolved:

- P0 #1 (per-turn metadata) — `:appendEvent` is the supported mechanism. Platform explicitly directs you there with the error message _"you can only update it by appending an event"_ on `sessions.patch` attempts.
- P0 #2 (CF clean handoff) — Agent Runtime continues for ≥240s after explicit `reader.cancel()` + `controller.abort()` + `res.status(202).send()`. Reproduced twice with identical timing.

---

## R3.1 — Per-turn `sessionState` mutability: **PASS**

### Mechanism (a) — REST `PATCH /sessions/{sid}?updateMask=sessionState`: NOT SUPPORTED

```
PATCH .../sessions/se-r31-{ts}?updateMask=sessionState
{"sessionState": {"runId": "r-2", "turnIdx": 1, "attempt": 1}}
→ 400 Bad Request
{
  "error": {
    "code": 400,
    "message": "Can't update the session state for session [...], you can only update it by appending an event.",
    "status": "INVALID_ARGUMENT"
  }
}
```

**Important platform-level finding:** the publicly documented `sessions.patch` does NOT update `sessionState`. The platform error message explicitly redirects you to `:appendEvent`. This is a deliberate design choice — state mutation goes through the event log, not direct field updates.

### Mechanism (b) — REST `:appendEvent` with `actions.stateDelta`: WORKS

Initial attempt failed because of timestamp format. Recording the failure for the migration runbook:

```
POST .../sessions/{sid}:appendEvent
{
  "author": "system",
  "invocationId": "r31-mutate-{ts}",
  "timestamp": 1777227316.81987,           ← Unix float — REJECTED
  "actions": {"stateDelta": {...}}
}
→ 400 Bad Request
"Invalid value at 'event.timestamp' (type.googleapis.com/google.protobuf.Timestamp), Field 'timestamp', Invalid data type for timestamp"
```

After fixing timestamp to RFC3339 string (`%Y-%m-%dT%H:%M:%S.%fZ`):

```
POST .../sessions/se-r31-{ts}:appendEvent
{
  "author": "system",
  "invocationId": "r31-mutate-{ts}",
  "timestamp": "2026-04-26T18:18:41.775335Z",
  "actions": {"stateDelta": {"runId": "r-2", "turnIdx": 1, "attempt": 1}}
}
→ 200 OK
{}
```

Then REST `:getSession` confirmed the new state:

```json
{ "runId": "r-2", "turnIdx": 1, "attempt": 1 }
```

Then `async_stream_query` (turn 2) was invoked. Plugin docs filtered by turn-2 `invocation_id`:

| Doc | kind        | runId | turnIdx | attempt |
| --- | ----------- | ----- | ------- | ------- |
| 1   | before_run  | r-2   | 1       | 1       |
| 2   | event       | r-2   | 1       | 1       |
| 3   | event       | r-2   | 1       | 1       |
| 4   | event       | r-2   | 1       | 1       |
| 5   | agent_event | r-2   | 1       | 1       |
| 6   | after_run   | r-2   | 1       | 1       |

**All six turn-2 docs carry the mutated state.** Per-turn metadata propagation works exactly as the migration design needs.

### Migration recipe

For every turn:

1. (First turn only) `POST .../sessions?sessionId=se-{sid}` with initial `sessionState`.
2. (Every turn) `POST .../sessions/{sid}:appendEvent` with `actions.stateDelta={runId, attempt, turnIdx}` carrying the new turn's metadata. Body is camelCase JSON with RFC3339 timestamp.
3. `POST .../reasoningEngines/{resource}:streamQuery?alt=sse` with `class_method: "async_stream_query"` and `input.session_id=se-{sid}`. The plugin will see the just-mutated state via `invocation_context.session.state`.

### Field-format gotchas captured for the migration runbook

- camelCase, not snake_case: `invocationId`, `stateDelta`, `sessionState`.
- Timestamp must be RFC3339 string, not Unix float.
- `sessionId` regex: `[a-z][a-z0-9-]*[a-z0-9]` — no underscores, no uppercase.
- `:appendEvent` returns `{}` on success — body is empty.

---

## R3.2 — Cloud Function handoff: **PASS** (gate variant)

### Setup

Two diagnostic Cloud Functions deployed to `superextra-site`:

- `probeHandoffAbort` — explicit `reader.cancel()` + `controller.abort()` before `res.send()`. **Gate variant.**
- `probeHandoffLeaveOpen` — same flow but skips abort/cancel. **Diagnostic only.**

Both:

- `onRequest({ cors: true, timeoutSeconds: 90 }, …)` — bumped from production's 30s because the lifecycle agent's first NDJSON event takes ~60s. Migration finding: production `agentStream` rewrite must do the same.
- `node@22`, Gen 2.
- Use `google-auth-library` (added as direct dep in `functions/package.json`).

### Gate variant evidence

**Run 1:**

- `cf_returned_at` server timestamp: `2026-04-26T18:24:19.664Z`
- CF response: 62.26s elapsed, status 202, body `{"handoff":"received_first_event","variant":"abort","first_line_len":353}`
- `after_run.ts`: `2026-04-26T18:28:20.293Z`
- **Gap: 240.6 seconds**
- Final docs: 1× before_run, 5× event, 1× agent_event, 1× after_run = 8 docs (full expected shape)

**Run 2 (cold repeatability):**

- `cf_returned_at`: `2026-04-26T18:30:59.424Z`
- `after_run.ts`: `2026-04-26T18:35:00.054Z`
- **Gap: 240.6 seconds** — identical to run 1
- Final docs: 8 (same shape)

### Verdict

Agent Runtime continues to drive the agent for ≥240 seconds AFTER the Cloud Function explicitly aborted the streamQuery and returned 202. The runtime treats explicit clean disconnect the same way it treats the round-1 Test-1 `kill -9`: the agent runs to completion regardless of caller state.

This is the supported clean-handoff pattern the migration design rests on. Production `agentStream` rewrite must use the same shape: read first NDJSON line as handoff proof, abort, return 202.

### Diagnostic variant (leave-open) finding

The leave-open variant ALSO completed cleanly with a 240.4s gap — essentially identical behaviour to the abort variant. **This does NOT promote the leave-open pattern to the gate.** Firebase's documented termination semantics still apply ("background work after `res.send()` may not progress, may resume on a future invocation, may reset connections"). Production must use the explicit-abort pattern; we should not lean on undocumented behaviour.

The fact that both variants produced identical timing in our test conditions is consistent with round-1 Test 1's finding that Agent Runtime's caller-disconnect-survival is robust across multiple disconnect modes (process kill, clean abort, leave-open). The migration design uses the safest shape regardless.

---

## Operational findings (incremental on top of R1/R2)

### R3.1

- **camelCase REST.** `:appendEvent` body uses `invocationId`, `stateDelta`, `sessionState`. snake_case (`invocation_id`, `state_delta`) gets rejected.
- **Timestamps are RFC3339 strings.** Not Unix floats. Use `%Y-%m-%dT%H:%M:%S.%fZ`.
- **`sessions.patch` is NOT for state.** Platform explicitly says use `:appendEvent`. Direct PATCH on `sessionState` is intentionally rejected.

### R3.2

- **Cloud Function timeout must be ≥90s** for the production-shape handoff (agents with slow first events). 30s is the OLD pattern (Cloud-Tasks-enqueue is sub-second); the new pattern needs to wait for handoff proof.
- **`google-auth-library` direct dep** in `functions/package.json` — was transitive via `@google-cloud/tasks`; declared explicitly during R3 setup and should stay.
- **ADC quota project** must be set for `firebase deploy` from the VM. Either edit `~/.config/gcloud/legacy_credentials/.../adc.json` to add `quota_project_id: superextra-site`, OR set `GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site` env var. Both worked in combination.

### Reviewer-flagged finding 6 verified

Removing function source from `functions/index.js` does NOT auto-delete deployed Gen 2 functions. Explicit cleanup commands required:

```bash
firebase functions:delete probeHandoffAbort --region us-central1 --project=superextra-site --force
firebase functions:delete probeHandoffLeaveOpen --region us-central1 --project=superextra-site --force
```

Then remove source from `index.js` and redeploy.

---

## Decision

**MIGRATION APPROVED.** All gates passed. Write v3 incorporating:

1. **Per-turn metadata propagation via `:appendEvent`** — replaces v2's "set state at createSession" assumption. Concrete REST recipe in §R3.1 above.
2. **Explicit-abort handoff in `agentStream`** — read first NDJSON line, `reader.cancel()` + `controller.abort()`, then `res.status(202).send()`. Cloud Function `timeoutSeconds: 90`.
3. **Reviewer P1/P2 corrections from v2 review** (all of them):
   - `transport: 'cloudrun'|'gear'` session-stickiness routing
   - Keep `adkSessionId` through 30-day rollback window
   - Plugin-owned heartbeat asyncio task
   - Write-class taxonomy for plugin defensive code
   - `google-cloud-secret-manager` in agent requirements
   - Recommendation-section narrative correction: heartbeat/takeover/fencing SURVIVE migration

---

## Migration plan revision scope (for v3)

These findings should land in `docs/gear-migration-proposal-2026-04-26-v3.md`:

- **§Code prerequisites** (new section, expanded from v2):
  - Lazy-init Gemini subclass (from R2.4)
  - Secret Manager runtime fetch (from R2.2)
  - **Per-turn `:appendEvent` metadata propagation (NEW from R3.1)**
  - **Cloud Function handoff with explicit `reader.cancel()` + `controller.abort()` + `timeoutSeconds: 90` (NEW from R3.2)**
  - NDJSON parser in agentStream (from R2.7)
  - FirestoreProgressPlugin with try/except + write-class taxonomy
- **§IAM matrix** — unchanged from v2.
- **§Migration cutover plan** — A/B with `transport` field, NOT in-place update.
- **§Operational gotchas** — adds R3 findings on camelCase REST, RFC3339 timestamps, sessionId regex, ADC quota_project_id, Gen-2 explicit function deletion.

---

## Cleanup TODOs

- [ ] `firebase functions:delete probeHandoffAbort probeHandoffLeaveOpen --region us-central1 --project=superextra-site --force`
- [ ] Remove `_runHandoff`, `probeHandoffAbort`, `probeHandoffLeaveOpen`, `GoogleAuth` import from `functions/index.js`
- [ ] Keep `google-auth-library` in `functions/package.json` — migration uses it
- [ ] Keep `agent/probe/probe_plugin.py` `invocation_id` addition — clean improvement
- [ ] R3 probe scripts stay in repo until migration completes
- [ ] R3 sessions (`se-r31-*`, `se-r32-*`) cleaned up alongside R1/R2 probe resource cleanup
