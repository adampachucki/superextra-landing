# GEAR probe — results

**Date:** 2026-04-26
**Plan:** [`docs/gear-probe-plan-2026-04-26.md`](./gear-probe-plan-2026-04-26.md)
**Execution log:** [`docs/gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md)
**Decision:** **MIGRATION APPROVED**

---

## Configuration recorded at top (per plan §1)

- **Pinned versions actually used:** `google-adk==1.28.0`, `google-cloud-firestore==2.22.0`, `google-cloud-aiplatform[agent_engines,adk]==1.147.0`. Auto-appended by the SDK: `cloudpickle==3.1.2`, `pydantic==2.12.5`. Python 3.12 in deployed runtime.
- **Project:** `superextra-site`. **Region:** `us-central1`. **Staging bucket:** `gs://superextra-site-agent-engine-staging` (created during probe).
- **Reasoning engine SA used by deployed runtime:** `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (note `-re` suffix). Granted `roles/datastore.user` for the probe.
- **Probe resources:**
  - Lifecycle: `projects/907466498524/locations/us-central1/reasoningEngines/329317476414259200`
  - Event-shape: `projects/907466498524/locations/us-central1/reasoningEngines/8725153081739706368`
  - Both should be deleted post-decision (not production traffic targets).
- **Deployed runtime config:** `min_instances`, `container_concurrency`, container size are NOT exposed in the `reasoningEngines.get()` response in this SDK version; appear to be Agent-Runtime-managed. Recorded as observed.

---

## Test 1 — Caller-disconnect survival (gate A): **PASS**

**Setup:** Lifecycle probe (`DeterministicSlowAgent`, 5 events × 60s = 5 min total run). Harness invoked `async_stream_query`. Observe-then-kill via `kill_after_first_event.sh` — wait for first event Firestore doc, then `kill -9` harness PID.

**Evidence:**

- `caller_killed_at` server timestamp: `2026-04-26 07:18:53.382 UTC`
- `after_run` server timestamp: `2026-04-26 07:22:52.227 UTC`
- **Gap: 238.8 seconds**

Final Firestore state for the killed run (path: `probe_runs/3614419488746766336/events`):

| count | kind                                                        |
| ----- | ----------------------------------------------------------- |
| 1     | before_run                                                  |
| 5     | event (one per agent yield, all post-kill except the first) |
| 1     | agent_event                                                 |
| 1     | after_run                                                   |

All 5 deterministic-agent events landed in Firestore. Events 2–5 (timestamps 07:19:51, 07:20:51, 07:21:51, 07:22:51) all landed AFTER `caller_killed_at` (07:18:53). Terminal `after_run` landed nearly 4 minutes after the harness was SIGKILLed.

**Conclusion:** Agent Runtime `streamQuery` invocations survive caller disconnect; the runtime drives the ADK agent to completion regardless of the calling client's connection state, and registered plugin callbacks fire end-to-end.

---

## Test 2 — Durable invocation primitive (gate B): **FAIL on Phase 2a — informative only**

**Phase 2a evidence:**

1. **REST `:streamQuery` response.** Status 200 SSE stream. No `Operation-Name` header, no `Location:` header, no `operation`/`name` LRO field in body. Just plain SSE chunks.
2. **`agent_engines` SDK surface on the deployed handle.** `dir(remote)` lists session methods, `stream_query`/`async_stream_query`, `streaming_agent_run_with_events`, `operation_schemas`, `wait`. **No** `start_invocation` / `get_operation` / `cancel_operation` / `*_long_running` methods. `async_api_client` exposes nothing extra.
3. **`projects.locations.operations.list` during a 5-min in-flight invocation.** Returned only deploy-LRO and session-creation-LRO entries. No invocation-level operation appeared.

**Conclusion:** No documented per-invocation LRO/background primitive for ADK chat turns on Agent Runtime as of 2026-04-26. The April 2026 release notes' "long-running operations up to 7 days" applies to lifecycle (deploy/session) operations, not chat-turn invocations.

**Why Test 2 failing does NOT block migration:** Test 1 already proved the underlying durability property the gate exists to verify. The only thing Test 2 would have additionally given us is a poll-by-operation watchdog design. Without it, the watchdog continues to poll Firestore liveness (`lastEventAt`/`lastHeartbeat` written by the FirestoreProgressPlugin), unchanged from today.

---

## Test 3 — Plugin callbacks fire on deployed runtime: **PASS**

**Lifecycle probe run** (5-event deterministic agent): produced 8 plugin docs covering all 4 callback kinds — `before_run` (1×), `event` from `on_event_callback` (5×), `agent_event` from `after_agent_callback` (1×), `after_run` (1×).

**Event-shape probe run** (real `LlmAgent` + `echo_tool`): produced 6 plugin docs with the full ADK event taxonomy:

| ADK event | content shape                                                         | plugin captured                                             |
| --------- | --------------------------------------------------------------------- | ----------------------------------------------------------- |
| 1         | `function_call(name=echo_tool, args={message:hello})`                 | `kind=event, event_author=probe_event_shape, is_final=True` |
| 2         | `function_response(name=echo_tool, response={echoed:hello, ok:true})` | `kind=event, event_author=probe_event_shape, is_final=True` |
| 3         | `text="done"`                                                         | `kind=event, event_author=probe_event_shape, is_final=True` |

**Conclusion:** ADK [#4464](https://github.com/google/adk-python/issues/4464) (plugin callbacks not invoked) does **NOT** reproduce under deployed Agent Runtime in `google-adk==1.28.0`. `on_event_callback` receives real ADK `Event` objects with full `content.parts` payloads — our existing `firestore_events.py:map_event` logic that extracts function-calls / function-responses / grounding metadata transfers without modification.

---

## Test 4 — Plugin metadata propagation via session state: **PASS**

**Setup:** `await remote.async_create_session(user_id="diag4", state={"runId": "r-iam2", "attempt": 3, "turnIdx": 0})`, then `async_stream_query`.

**Evidence:** All 8 plugin docs from the run carry exactly the values set at `create_session()` time:

```
runId="r-iam2", attempt=3, turnIdx=0, userId="diag4", sid="5061904556481314816"
```

`runId`/`attempt`/`turnIdx` were read from `invocation_context.session.state` inside callbacks. `userId` from `invocation_context.user_id`. `sid` from `invocation_context.session.id`. **No fallback to message-text encoding required.**

**Conclusion:** The production-intended FirestoreProgressPlugin design works end-to-end. Per-run metadata can be reliably propagated from the agentStream proxy to plugin callbacks via session state, exactly as our current `worker_main.py:1086` pattern does.

---

## Test 5 — Custom session ID acceptance: **PASS via REST; ADK SDK has a stale client-side guard**

Initial finding (incorrect): ADK's `async_create_session(session_id=...)` rejects with `User-provided Session id is not supported for VertexAISessionService`.

**Follow-up investigation (2026-04-26 afternoon):** the rejection is a stale client-side guard at `google-adk==1.28.0` `vertex_ai_session_service.py:121`:

```python
if session_id:
    raise ValueError('User-provided Session id is not supported for VertexAISessionService.')
```

The very next line of the same method calls the underlying API, **which does support user-provided IDs**. The guard was never removed when the platform feature shipped. Tracked as open bug [adk-python#987](https://github.com/google/adk-python/issues/987).

**Verified end-to-end via REST + ADK:**

```
POST https://us-central1-aiplatform.googleapis.com/v1beta1/{resource}/sessions?sessionId=se-custom001
body: {"userId": "rest-test", "sessionState": {"runId": "r-rest", "attempt": 1}}
→ 200 OK; session created at .../sessions/se-custom001
```

Both `v1` and `v1beta1` accepted the prefixed ID. Then ADK `async_stream_query(user_id="rest-test", session_id="se-custom001", message="go")` ran cleanly against the REST-created session; plugin wrote docs to `probe_runs/se-custom001/events/`; `runId="r-rest"` propagated from `sessionState` into `invocation_context.session.state` exactly as Test 4 demonstrated.

**Verdict:** Custom session IDs work end-to-end at the platform level. The release notes are correct; the ADK SDK is stale. Migration can use `se-{uuid}` IDs throughout by bypassing ADK's `create_session` and calling REST directly.

**Production-relevant takeaway (revised):** we CAN use our internal UUID-derived sid as the Agent Runtime session id (with `se-` prefix). The `adkSessionId` mapping plumbing in our session doc (`worker_main.py:1086-1093`) **can be deleted**, not preserved as I originally claimed. This is a code-reduction win the migration plan should claim.

---

## Test 6 — Duplicate dispatch behavior: concurrent runs both succeed

**Action:** Two `async_stream_query` calls 2 seconds apart on the same `(user_id, session_id)` pair.

**Result:** Both invocations completed successfully; each returned 5 events. Neither was rejected, neither serialized at the API layer.

**Implication:** Agent Runtime does **NOT** enforce single-active-invocation per session. **Idempotency must continue to live in our Firestore** (currentRunId / currentAttempt / takeover transaction). The migration does NOT simplify this part of `worker_main.py:293-364`. Reviewer's P1 ("Agent Runtime owns concurrency is too broad") confirmed empirically.

---

## Test 7 — Cold start + concurrency: directional only

**Latencies observed during probe runs:**

| Scenario                                       | First-event latency       | Note                                                  |
| ---------------------------------------------- | ------------------------- | ----------------------------------------------------- |
| First invocation ~3 min after deploy completed | ~2.2s (LLM agent)         | Includes ~1s of LLM thinking; cold-start overhead ≤1s |
| Back-to-back invocations within same minute    | sub-second to first event | Warm                                                  |
| 5-minute idle gap, then invoke                 | ~2s observed              | Limited samples                                       |

**Conclusion:** Directionally consistent with April 2026 release notes' "sub-second cold starts" claim, though not rigorously measured (didn't run a 15-min-idle baseline; decision was already determined by Test 1). Production-deployed agent should keep `min_instances=1` if user-configurable; if Agent Runtime auto-manages, accept the directional sub-second behaviour.

**Provisioning time observed:** measured three deploys consistently:

| Operation                                             | Time   |
| ----------------------------------------------------- | ------ |
| `agent_engines.create()` — lifecycle probe            | 202.7s |
| `agent_engines.create()` — event_shape probe          | 220.3s |
| `agent_engines.update()` — same code, existing engine | 214.4s |

All ~3.5 min. **Update is NOT materially faster than create.** The release notes' "less than 1 minute" claim is wrong as observed. Possible explanations: applies to a deploy mode we didn't exercise (Express mode? a different deployment surface?) or marketing optimism. CI/CD planning should assume ~4 min, not 1 min. Not migration-blocking.

---

## Decision

**MIGRATION APPROVED** per plan §8.

Gate satisfied: **(Test 1 PASS) ∨ (Test 2 PASS)** evaluates True via Test 1.
Required tests: **Test 3 PASS**, **Test 4 PASS**.

Primary reason: Agent Runtime `streamQuery` invocations are durable across caller disconnect (proven by 238.8s gap between caller kill and terminal plugin write). The production FirestoreProgressPlugin design works as specified — all callbacks fire, metadata propagates via session state, real ADK event taxonomy is preserved, no fallback mechanisms required.

---

## Findings that reshape the migration proposal

The migration plan rewrite must reflect these probe-derived facts (not assumptions):

1. **Custom session IDs work via REST, blocked only by an SDK guard.** Use REST `:createSession?sessionId=se-{uuid}` directly from `agentStream`, then ADK `async_stream_query(session_id="se-{uuid}", ...)` for the run. **`adkSessionId` mapping plumbing in our session doc can be DELETED, not preserved.** This is a code-reduction win the original proposal missed. Tracked upstream as [adk-python#987](https://github.com/google/adk-python/issues/987).
2. **No invocation-level LRO exists**, and the release-notes "7 days" phrasing was misleading. The actual durability mechanism is **per-request long timeout + caller-disconnect-survival**, both proven by Test 1 (run continued 238.8s past `kill -9`). Watchdog continues polling Firestore liveness fields written by the plugin (`lastEventAt`/`lastHeartbeat`), not `operations.get`. Same shape as today's watchdog.
3. **Concurrent invocations are not serialized** — `currentRunId`, `currentAttempt`, takeover transaction, fenced terminal writes all survive the migration.
4. **Reasoning Engine SA needs explicit grants** — `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (note `-re` suffix) must get `roles/datastore.user` and any other roles the FirestoreProgressPlugin (or other in-plugin clients) requires. **Add to deploy.yml.**
5. **ADK `App.name` must be a Python identifier** — no hyphens. Display name takes hyphens.
6. **Reserved env vars** — `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` are reserved by Agent Runtime; cannot be passed in `env_vars={}`.
7. **Module-path discipline** — relative imports inside the bundled `extra_packages` directory; align cwd at deploy time so cloudpickle records the same module names the deployed runtime sees.
8. **Provisioning time** ~3.5 min for both create and update — release notes' "<1 minute" wrong as observed. CI/CD planning: assume 4 min.
9. **Plugin-error semantics** — uncaught exceptions in `on_event_callback` HALT the run. Production FirestoreProgressPlugin must be defensively coded with try/except around external writes (matches today's `worker_main.py` defensive pattern around `_fenced_update`).

These findings + the existing reviewer P1/P2/P3 corrections (`agentCheck` is gone, six indexes not four, etc.) form the rewrite scope for the migration proposal.

### Doc-vs-reality table (for the committee — explains where I trusted release notes incorrectly)

| Release-notes claim                    | Reality                                                                                                                                                             | Mechanism of the gap                                                                                              |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Custom session IDs supported           | **TRUE at platform layer.** ADK SDK has stale client-side guard ([adk-python#987](https://github.com/google/adk-python/issues/987)). Bypass via direct REST.        | SDK code wasn't updated when platform feature shipped.                                                            |
| Sub-1-minute provisioning              | **FALSE.** Consistently ~3.5 min for create and update.                                                                                                             | Possibly a different deploy mode applies; or marketing optimism.                                                  |
| "Long-running operations up to 7 days" | **Misleading phrasing.** No invocation LRO API exists. But per-request timeout _is_ effectively long, and disconnect-survival _is_ real. Same practical durability. | Release notes implied a fire-and-forget API surface; mechanism is actually different but functionally equivalent. |

---

## Recommended migration scope (revised against probe findings)

Replaces §6 of the original proposal:

**Removed (~700–800 LOC, lower than the original ~1,000 estimate):**

- ADK `Runner` construction + lifecycle management in `worker_main.py`
- The event-iteration loop (`async for event in runner.run_async(...)`) — moves into `on_event_callback`
- The signal handler / FastAPI lifespan / structured-logging boilerplate that exists because we self-host
- Cloud Run service `superextra-worker` infra
- Cloud Tasks queue dispatch helper in `functions/index.js` (replaced by `streamQuery` invocation)

**Stays (revised down vs. original):**

- Takeover transaction + ownership fencing (Test 6 confirmed this stays)
- Heartbeat task — the plugin's `on_event_callback` writes `lastEventAt`, but for long silent LLM calls (60–90s) the watchdog still needs an active heartbeat. Either keep it as a separate asyncio task in the agentStream-proxy side, or accept looser watchdog thresholds based on `lastEventAt` only.
- `currentRunId` / `currentAttempt` / fenced terminal writes
- All chat-state UI machinery, capability URLs, watchdog
- Cloud Function `agentStream` (changes shape — calls REST `:createSession?sessionId=se-{uuid}` then `async_stream_query` instead of enqueueing — but stays as the public proxy)

**Additional deletion win from doc-vs-reality investigation:**

- The `adkSessionId` mapping plumbing on the session doc (read/write at `worker_main.py:1086-1093`) and the field on the Firestore session schema. Custom session IDs work end-to-end via REST; our `se-{sid}` ID becomes the Agent Runtime session ID directly.

**Net reduction realistic estimate:** ~700–800 LOC. Up slightly from the post-probe estimate now that `adkSessionId` plumbing is also droppable. Still less of a code-deletion win than the original proposal's ~1,000 figure, but real.

---

## Cleanup

- [ ] Delete probe Reasoning Engines (`329317476414259200`, `8725153081739706368`)
- [ ] Delete probe sessions
- [ ] Decide whether `agent/probe/` stays in repo as reference, gets archived, or gets deleted
- [ ] Revoke `roles/datastore.user` from `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com` if migration is not pursued; otherwise keep as the production runtime SA needs it
