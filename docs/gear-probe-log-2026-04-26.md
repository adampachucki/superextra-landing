# GEAR probe — execution log

**Started:** 2026-04-26
**Plan:** [`docs/gear-probe-plan-2026-04-26.md`](./gear-probe-plan-2026-04-26.md)
**Operator:** Claude (Opus 4.7) under Adam's session

Append-only log. Every action, blocker, finding, and learning lands here as it happens. Final decision contract is in the plan §8; the result report (`docs/gear-probe-results-2026-04-26.md`) is built from this log when the probe completes.

---

## 2026-04-26 — Environment + scaffolding

### Pre-flight findings

**Environment confirmed:**

- gcloud project = `superextra-site`, account = `adam@finebite.co`, ADC token works.
- venv at `agent/.venv`, Python 3.12.3.
- Installed: `google-adk==1.28.0` ✓ (matches plan), `google-cloud-firestore==2.22.0` ✓, `google-cloud-aiplatform==1.147.0` (plan said 1.144.0; minor drift — newer is fine, recorded).
- `from vertexai import agent_engines` imports cleanly. Module exposes `AdkApp`, `create`, `delete`, `get`, `update`, plus `Queryable`/`StreamQueryable`/`AsyncQueryable`/`AsyncStreamQueryable` protocol classes.

**ADK plugin signatures verified empirically against installed 1.28.0:**

| Callback                                         | Signature                                                        | Notes                                                                                                                   |
| ------------------------------------------------ | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `before_run_callback`                            | `(*, invocation_context: InvocationContext)`                     | ✓ matches `chat_logger.py:113`                                                                                          |
| `after_run_callback`                             | `(*, invocation_context: InvocationContext)`                     | ✓ matches `chat_logger.py:134`                                                                                          |
| `on_event_callback`                              | `(*, invocation_context: InvocationContext, event: Event)`       | **Present in 1.28.0** — reviewer was right; we can gate on it directly. No need to fall back to `after_agent_callback`. |
| `before_agent_callback` / `after_agent_callback` | `(*, agent: BaseAgent, callback_context: CallbackContext)`       | Supplementary.                                                                                                          |
| `before_tool_callback` / `after_tool_callback`   | `(*, tool: BaseTool, tool_args, tool_context: ToolContext, ...)` | Useful for Test 3b real-tool path.                                                                                      |

This validates the probe plugin design from §2.2 of the plan exactly.

**No probe code yet — scaffolding next.**

---

## 2026-04-26 — Probe scaffolding

**Files written under `agent/probe/`:**

- `agent.py` — `DeterministicSlowAgent(BaseAgent)` (5 events × 60s) + `LlmAgent(probe_event_shape)` with `echo_tool`. Two `App` factories.
- `probe_plugin.py` — `ProbePlugin` registering `before_run_callback`, `on_event_callback`, `after_run_callback`, `after_agent_callback`. All write to Firestore `probe_runs/{sid}/events/`.
- `deploy.py` — idempotent `agent_engines.create()` with `--redeploy` flag; records resource names in `deployed_resources.json`.
- `run_probe.py` — harness: creates session with `state={runId, attempt, turnIdx}`, fires `async_stream_query`, writes per-event marker files to `/tmp/probe_markers/{sid}.event.N`.
- `watch_firestore.py` — verifier; computes timestamp gap between `caller_killed_at` marker and `after_run` doc.
- `kill_after_first_event.sh` — observe-then-kill wrapper.
- `requirements.txt` — pinned: `google-adk==1.28.0`, `google-cloud-firestore==2.22.0`, `google-cloud-aiplatform[agent_engines,adk]==1.147.0`.

**Blocker hit and resolved during scaffolding:**

1. **ADK `App` rejects hyphenated names.** `superextra-probe-lifecycle` → `ValidationError: must be a valid identifier consisting of letters, digits, and underscores`. Renamed to `superextra_probe_lifecycle` and `superextra_probe_event_shape`. Display names (Agent Runtime resource label) keep hyphens — that's a different field.

2. **No Agent Engine staging bucket existed.** Created `gs://superextra-site-agent-engine-staging` in `us-central1`. Set `PROBE_STAGING_BUCKET` env var in `deploy.py` defaults to this.

**Local smoke (no deploy):** `make_lifecycle_app()` and `make_event_shape_app()` construct cleanly, plugins register. Ready to deploy.

---

## 2026-04-26 — Deploy blockers (worked through)

Three deploy attempts before success:

1. **`PermissionDenied: ACCESS_TOKEN_SCOPE_INSUFFICIENT`** — VM's GCE metadata SA doesn't have `cloud-platform` scope. Fixed by `export GOOGLE_APPLICATION_CREDENTIALS=/home/adam/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json`. **Add to migration runbook.**
2. **`agent_engine has none of the following callable methods`** — passing `App` to `agent_engines.create()` directly fails. Must wrap in `agent_engines.AdkApp(app=our_app)`. The `AdkApp` wrapper is what exposes `query`/`stream_query`/`async_stream_query` etc.
3. **`Environment variable name 'GOOGLE_CLOUD_PROJECT' is reserved`** — Agent Runtime sets `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` automatically. Cannot pass them in `env_vars={}`. Removed from deploy.
4. **`FileNotFoundError: ./agent/probe`** — `extra_packages` paths resolve relative to cwd (which was `agent/`), not repo root. Fixed by changing to `./probe`.
5. **First successful deploy then "failed to start"** — runtime started but couldn't run. Root cause: cloudpickle module-path mismatch. Local code imported as `agent.probe.X`; remote bundle is at `probe.X`. Fixed by running deploy from `agent/` cwd with `PYTHONPATH=.` and importing `from probe.agent import ...`. Also switched intra-package imports inside `probe/` to relative form (`from .probe_plugin import ProbePlugin`).

**Successful deploy time:** 202.7s (~3.4 minutes). **[CORRECTED LATER — see "Provisioning time" in the Doc-vs-reality section: 3.4 min is NOT consistent with the release notes' "<1 min" claim. The original framing here was wrong. Treat the realistic number as ~3.5 min for both `create()` and `update()`.]**

**Resource:** `projects/907466498524/locations/us-central1/reasoningEngines/329317476414259200`

---

## 2026-04-26 — IAM hunt for the deployed runtime SA

First post-deploy invocation showed: agent runs, returns events, but plugin writes nothing to Firestore.

**Initial misdiagnosis:** suspected ADK [#4464](https://github.com/google/adk-python/issues/4464) (plugin callbacks not firing under deployed runtime). False alarm.

**Actual cause:** the deployed Agent Runtime runs as `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (note the `-re` suffix for "reasoning engine") with role `roles/aiplatform.reasoningEngineServiceAgent`. **This SA has no Firestore access by default.** Plugin's `firestore.Client()` was failing inside `_write()`, our try/except was swallowing it.

**Confirmed by:** redeploying the plugin without try/except. After grant, `stream_query` ran cleanly; before grant, it returned 1 event then errored out (Firestore exception propagated through plugin → runner halt).

**Fix:** `gcloud projects add-iam-policy-binding superextra-site --member="serviceAccount:service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com" --role="roles/datastore.user"`. **Add to migration runbook.**

---

## 2026-04-26 — Test 3 + Test 4 results: PASS

After IAM grant propagated (~60s), invoked the lifecycle probe with `state={"runId": "r-iam2", "attempt": 3, "turnIdx": 0}` at `create_session()` time.

**Result:** 5 events received from `stream_query`, **8 Firestore docs written by the deployed plugin**:

| #   | kind        | runId  | attempt | turnIdx | userId | Notes                                                           |
| --- | ----------- | ------ | ------- | ------- | ------ | --------------------------------------------------------------- |
| 1   | before_run  | r-iam2 | 3       | 0       | diag4  |                                                                 |
| 2-6 | event ×5    | r-iam2 | 3       | 0       | diag4  | event_author=probe_lifecycle, is_final=True, distinct event_ids |
| 7   | agent_event | r-iam2 | 3       | 0       | diag4  | from after_agent_callback, agent=probe_lifecycle                |
| 8   | after_run   | r-iam2 | 3       | 0       | diag4  |                                                                 |

**Test 3 (plugin callbacks fire on deployed runtime): PASS.** All four callback kinds observed firing: `before_run_callback`, `on_event_callback` (5×), `after_agent_callback`, `after_run_callback`. ADK [#4464](https://github.com/google/adk-python/issues/4464) does NOT reproduce under Agent Runtime in google-adk 1.28.0.

**Test 4 (metadata propagation via session state): PASS.** `runId="r-iam2"`, `attempt=3`, `turnIdx=0`, `userId="diag4"` propagated correctly through `invocation_context.session.state` and `invocation_context.user_id` to every plugin callback. **No fallback mechanism needed.** This validates the production-intended FirestoreProgressPlugin design.

**Sub-finding:** every event from `DeterministicSlowAgent` shows `is_final=True`. ADK's `is_final_response()` returns True when there are no pending tool calls — our deterministic agent yields plain content events with no follow-up needed, so each is "final" by ADK's definition. Production code (specialists with tool calls) will distinguish meaningfully.

---

## 2026-04-26 — Test 5 result: FAIL (contra release notes) — [SUPERSEDED below]

> **[SUPERSEDED]** This section's verdict was reversed by the doc-vs-reality investigation. The platform DOES support custom session IDs via REST; only the ADK Python SDK (`VertexAiSessionService`) has a stale client-side guard rejecting them. See "Custom session IDs — bug is at ADK SDK layer, NOT platform" below for the corrected finding. The "Implication for migration" list in this section is wrong — we do NOT need an `adkSessionId` mapping; we can use `se-{uuid}` end-to-end via direct REST `:createSession`. Keeping this section verbatim for the audit trail of how the wrong conclusion was reached the first time.

Empirical finding from the very first invocation attempt.

**Action:** `await remote.async_create_session(user_id="probe_user", session_id="se-baseline001", state={...})`

**Result:** `FailedPrecondition: 400 Reasoning Engine Execution failed. ... "User-provided Session id is not supported for VertexAISessionService."`

**Verdict (initial, INCORRECT):** The April 2026 release notes claim "When creating a Session, you can specify your own session ID" does **NOT** apply to ADK agents using `VertexAiSessionService` (the only session service available on Agent Runtime today). Sessions get auto-generated numeric IDs (e.g., `5061904556481314816`).

**Implication for migration (INCORRECT — see SUPERSEDED note above):**

- Accepting auto-generated IDs from `create_session()`
- Storing the mapping `(our_session_id → adk_session_id)` in our own Firestore session doc
- Our existing `worker_main.py:175` already does this via the `adkSessionId` field on the session doc — pattern carries forward.

This is **not a migration blocker** — we already use the auto-generated-id pattern in production. But the docs are wrong; flag this for any future migration decision.

---

## 2026-04-26 — Test 1 result: PASS (load-bearing)

**Setup:** Lifecycle probe (DeterministicSlowAgent: 5 events × 60s sleep = 5 min total). Harness invoked `async_stream_query`. Observe-then-kill via `kill_after_first_event.sh` — wait for first event marker, then `kill -9` harness.

**Timeline (server timestamps):**

- T+0s: harness starts
- T+~60s: first event lands in Firestore (`event #1` plus `before_run`)
- **T+62s: harness SIGKILLed; `caller_killed_at` marker written at 07:18:53.382Z**
- T+120s: event #2 lands (post-kill)
- T+180s: event #3 lands (post-kill)
- T+240s: event #4 lands (post-kill)
- T+300s: event #5 lands (post-kill)
- T+~301s: `after_run` lands at 07:22:52.227Z

**Computed gap between kill and terminal write: 238.8 seconds.**

Final Firestore state for the killed run: `{before_run: 1, event: 5, agent_event: 1, after_run: 1}` — every event the agent would have produced fired through the plugin and landed in Firestore. The terminal `after_run` doc landed nearly 4 minutes after the harness was killed.

**VERDICT: Agent Runtime `streamQuery` runs survive caller disconnect.** The runtime keeps executing the ADK agent to completion regardless of the calling client's connection state. Plugin callbacks fire end-to-end.

This is the load-bearing finding that satisfies **gate A** of the binary decision contract.

---

## 2026-04-26 — Test 2 result: FAIL (no LRO for chat-turn invocations)

Phase 2a — discovery. Inspected three sources for a durable invocation primitive:

1. **REST `:streamQuery` response headers.** No `Operation-Name` header, no `Location:` header pointing to a poll endpoint, no `operation`/`name` field in the body matching `projects/.../operations/...`. Standard SSE response.
2. **`agent_engines` SDK surface.** `dir(remote)` reveals: `api_client`, `async_*` session methods, `stream_query`, `async_stream_query`, `streaming_agent_run_with_events`, `operation_schemas`, `wait`, `to_dict`, etc. **None** of `start_invocation`, `get_operation`, `cancel_operation`, `*_long_running` exist. `async_api_client` has no extra methods.
3. **`projects.locations.operations.list`** during an in-flight 5-min invocation. Returned exclusively `CreateReasoningEngineOperationMetadata` (deploy LRO) and `CreateSessionOperationMetadata` (session LRO). **No invocation-level operation appeared.**

**Verdict:** Phase 2a fails. No documented LRO/operation/background primitive exists for chat-turn invocations on Agent Runtime as of 2026-04-26. Phase 2b not run (nothing to invoke through).

**Why this is informative-only, not migration-blocking:** Test 1 already proved durability via caller-disconnect survival, which satisfies the gate's underlying question. The Test 2 result tells us watchdog design — we **must continue polling Firestore liveness** (`lastEventAt`/`lastHeartbeat` written by the plugin), not `operations.get`. Same shape as today's watchdog.

---

## 2026-04-26 — Test 6 result: concurrent invocations both succeed

Two `async_stream_query` calls 2s apart on the same `(user_id, session_id)`. Both ran to completion, each returned 5 events. Neither was rejected, neither was serialized at the API layer.

**Verdict:** Agent Runtime does NOT enforce single-active-invocation per session. **Idempotency must continue to live in our Firestore** (currentRunId / currentAttempt / takeover transaction). The migration does NOT simplify this part of `worker_main.py` — those invariants survive.

This is the expected outcome the reviewer flagged in P1. Recording it explicitly so the migration plan can keep the right amount of lifecycle protection.

---

## 2026-04-26 — Test 3 deeper: real LLM+tool event taxonomy

Event-shape probe (`LlmAgent` + `echo_tool`) baseline run. 3 events in 2.8s wall:

| event | author            | content shape                                                         |
| ----- | ----------------- | --------------------------------------------------------------------- |
| 1     | probe_event_shape | `function_call(name=echo_tool, args={message:hello})`                 |
| 2     | probe_event_shape | `function_response(name=echo_tool, response={echoed:hello, ok:true})` |
| 3     | probe_event_shape | `text="done"`                                                         |

Plugin produced 6 docs: `before_run`, 3× `event` (one per ADK event including the function_call and function_response shapes), `agent_event` (after_agent_callback for `probe_event_shape`), `after_run`.

**Production implication:** the FirestoreProgressPlugin's `on_event_callback` will receive ADK Events with the same shape we currently iterate in `worker_main.py:1115`. Our existing `firestore_events.py:map_event` logic that handles `function_call` / `function_response` / `grounding_metadata` extraction transfers without modification.

---

## 2026-04-26 — Test 5 deferred verification — [SUPERSEDED below]

> **[SUPERSEDED]** This section's takeaway is wrong. Custom session IDs DO work via direct REST. See the Doc-vs-reality section below.

Already known from Test 3's first attempt: VertexAiSessionService rejects user-provided session IDs with `User-provided Session id is not supported for VertexAISessionService`. Did not separately verify that auto-generated IDs starting with digits are accepted (the test plan asked us to compare prefixed `se-{uuid}` vs raw UUID); since user-provided IDs are rejected entirely, the comparison is moot. The auto-generated IDs Agent Runtime returns are **all-digit numeric strings** (e.g., `5061904556481314816`) — neither letter-prefixed nor UUID-shaped.

**Production-relevant takeaway (INCORRECT — see SUPERSEDED note above):** we cannot map our internal sid (UUID v4) to the ADK session_id 1:1. Must store `adkSessionId` separately on our session doc — the pattern already exists at `worker_main.py:1086-1093`.

**Corrected takeaway:** call REST `:createSession?sessionId=se-{uuid}` directly from `agentStream` (bypassing ADK's stale guard), then ADK `async_stream_query(session_id="se-{uuid}", ...)` works against it. We can use `se-{uuid}` end-to-end and delete the `adkSessionId` plumbing.

---

## 2026-04-26 — Test 7 cold start (informative; light-touch measurement)

**Deployed config observed:** the `spec` returned by `reasoningEngines.get(...)` does **not** expose `min_instances`, `container_concurrency`, or container size. These appear to be managed by Agent Runtime internally, not user-configurable through the standard `agent_engines.create()` flow at this SDK version. Recording as observed.

**Latencies actually seen during the probe:**

| Scenario                                                      | First-event latency       | Notes                                                                                 |
| ------------------------------------------------------------- | ------------------------- | ------------------------------------------------------------------------------------- |
| First invocation after deploy (warm-ish, ~3 min after deploy) | ~2.2s                     | LLM-only path; the agent itself takes ~1s of LLM thinking, so cold-start overhead ≤1s |
| Sequential invocations during the same minute                 | sub-second to first event | Warm container, agent's own latency dominates                                         |
| 5-minute idle gap, then invoke                                | ~2s observed              | Limited samples                                                                       |

**Directional read:** consistent with the April 2026 release notes claim of sub-second cold starts. Did not run a rigorous 15-min-idle test — would be a wasted experiment given decision is already determined by Test 1. Production should `min_instances=1` if available; if Agent Runtime auto-manages, accept the directional sub-second behaviour.

---

## 2026-04-26 — Probe complete; decision evidence in place

Total wall time for execution: ~80 minutes including iterating through 3 deploy blockers + 1 IAM hunt + 5 deployed-runtime invocations.

**Gate evaluation per §8 of the plan:**

| Test                             | Required for migration? | Result                              | Notes                                                                              |
| -------------------------------- | ----------------------- | ----------------------------------- | ---------------------------------------------------------------------------------- |
| 1 — caller-disconnect survival   | Gate A (T1 OR T2)       | **PASS**                            | 238.8s gap between kill and `after_run`                                            |
| 2 — durable invocation primitive | Gate B (T1 OR T2)       | FAIL on Phase 2a                    | Informative; T1 satisfies the gate                                                 |
| 3 — plugin callbacks fire        | Required                | **PASS**                            | All callbacks observed, including `on_event_callback` with real ADK Event payloads |
| 4 — metadata via session.state   | Required                | **PASS**                            | runId/attempt/turnIdx/userId/sid all propagate                                     |
| 5 — custom session IDs           | Informative             | FAIL contra release notes           | User-provided IDs rejected; same pattern as today (auto-generated `adkSessionId`)  |
| 6 — duplicate dispatch           | Informative             | FAIL (concurrent runs both proceed) | Idempotency stays in Firestore                                                     |
| 7 — cold start                   | Informative             | OK directionally                    | ~2s observed first-event including agent latency                                   |

**Decision: MIGRATION APPROVED** per the plan's binary gate (T1 ∨ T2 = pass, T3 = pass, T4 = pass).

Findings that will reshape the migration plan vs. the original proposal:

1. ~~Custom session IDs are NOT supported — keep `adkSessionId` mapping on session doc.~~ **[CORRECTED in Doc-vs-reality investigation below: custom session IDs DO work via direct REST. The ADK SDK has a stale guard. We can use `se-{uuid}` end-to-end and delete the `adkSessionId` plumbing.]**
2. No invocation-level LRO exists — watchdog continues polling Firestore liveness, NOT `operations.get`.
3. Concurrent invocations on the same session both succeed — currentRunId/currentAttempt/takeover transaction must be preserved.
4. Reasoning Engine SA is `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` — must be granted `roles/datastore.user` (and any other GCP services we call from inside plugins).
5. ADK App's `App.name` must be a valid Python identifier (no hyphens). Display name takes hyphens.
6. Plugin module path mismatch is a real footgun: cloudpickle records the module name where the class is defined; the deployed runtime imports from `extra_packages` root. Use relative imports inside the bundled package and align cwd at deploy time.
7. Reserved env vars: `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` cannot be passed in `env_vars`.
8. Provisioning time observed: ~3.5 min (well under the older "10 min" docs claim, but not under the release notes' "<1 min" — that claim is wrong as observed).

**Next:** write `docs/gear-probe-results-2026-04-26.md` from this log; rewrite `docs/gear-migration-proposal-2026-04-25.md` to incorporate findings, fix the stale-against-main P2 errors, and replace unverified fire-and-forget claims with the verified caller-disconnect-survival mechanism.

---

## 2026-04-26 — Doc-vs-reality investigation (follow-up after probe)

User flagged: contradictions with documentation are strange; investigate why before treating as platform truths. Result: **two of the three contradictions are SDK-layer artifacts, not platform-layer truths.** The third has a different mechanism than I assumed but the practical outcome matches.

### Custom session IDs — bug is at ADK SDK layer, NOT platform

**Reproduced via direct REST, bypassing ADK:**

```
POST https://us-central1-aiplatform.googleapis.com/v1beta1/{resource}/sessions?sessionId=se-custom001
body: {"userId": "rest-test", "sessionState": {"runId": "r-rest", "attempt": 1}}
→ 200 OK, session created with name=.../sessions/se-custom001
```

Both `v1` and `v1beta1` accepted the prefixed UUID. **Platform supports custom IDs exactly as the release notes promised.**

**Confirmed streaming end-to-end against the custom-ID session:** ADK's `async_stream_query(user_id="rest-test", session_id="se-custom001", message="go")` worked. Plugin wrote docs to `probe_runs/se-custom001/events/`; `runId="r-rest"` propagated from `sessionState` set at REST-create time.

**Located the SDK rejection:** `google-adk==1.28.0` `vertex_ai_session_service.py:121`:

```python
async def create_session(self, *, app_name, user_id, state=None, session_id=None, ...):
    ...
    if session_id:
        raise ValueError('User-provided Session id is not supported for VertexAISessionService.')
    ...
    api_response = await api_client.agent_engines.sessions.create(...)
```

The very next line of code calls the underlying API, which **does** support user-provided IDs. The guard is stale — likely written before the platform feature shipped, never removed. Tracked as [adk-python#987](https://github.com/google/adk-python/issues/987), still open.

**Practical implication for our migration (this changes the plan):**

- We CAN use our own `se-{uuid}` IDs end-to-end.
- We DO NOT need to keep `adkSessionId` mapping in the session doc (`worker_main.py:1086-1093` plumbing can be deleted).
- Two paths to the working pattern:
  1. Bypass ADK `create_session`. Call REST `:createSession?sessionId=se-{uuid}` directly from `agentStream`. Then ADK `async_stream_query(session_id="se-{uuid}", ...)` works against it.
  2. Or wait for adk-python#987 to land and use ADK natively. Path 1 is independent of upstream.

This is a **simplification gain** I missed in the original probe writeup. Our internal sid → ADK session_id mapping disappears.

### Provisioning time — release notes wrong, but consistently so

Tested both `agent_engines.create()` and `agent_engines.update()`:

- Create #1 (lifecycle): 202.7s
- Create #2 (event_shape): 220.3s
- Update on existing engine (same code): 214.4s

All ~3.5 min. The release notes' "less than 1 minute" claim is **wrong as observed**. Update isn't faster than create. Possible explanations:

- Different region performance
- "Express mode" or "lightweight" deploy path we didn't use
- Marketing optimism

Not investigated further because not migration-blocking. CI/CD planning should assume ~4 min, not 1 min.

### 7-day LRO — different mechanism than I assumed; practical outcome matches

Re-read the release-notes phrasing: _"Agent Runtime now supports long-running operations (up to 7 days)."_

I had read this as "fire-and-forget LRO API for chat-turn invocations." That's wrong — confirmed by inspecting:

- v1beta1 reasoning engine spec exposes class methods with these `api_mode` values: `async`, `stream`, `async_stream`. **No `long_running` or `background` mode exists.**
- `streaming_agent_run_with_events` exists as an alternate streaming method but its own docstring says "In general, you should use `async_stream_query` instead" — same durability model, just an alternate variant.
- `operations.list` filtered by reasoning engine returns only deploy/update LROs and session-creation LROs. No invocation LROs.

**Reinterpreted meaning of "7 days":** the per-request runtime timeout. I.e., Agent Runtime won't kill an in-flight `streamQuery` request for up to 7 days. That's consistent with what Test 1 observed — the runtime kept running our 5-min agent past caller disconnect with no internal timeout fired. Our 7-15 min pipeline fits comfortably under any 7-day ceiling.

So: the docs' "7-day LRO" phrasing is misleading (suggests an API surface that doesn't exist) but the **practical durability property is real** — Test 1 proved it directly. We don't need an LRO API; we have caller-disconnect-survival, which is functionally equivalent for our case.

### Summary of the doc-vs-reality investigation

| Release-notes claim                    | Reality                                                                                     | Why the gap                                                                                                           | Migration impact                                                                                                                         |
| -------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| "Custom session IDs supported"         | Platform: TRUE. ADK SDK: FALSE (stale guard at line 121 of `vertex_ai_session_service.py`). | adk-python#987 client-side check not removed when platform feature shipped.                                           | **Plus:** drop `adkSessionId` mapping plumbing. Use `se-{uuid}` end-to-end via REST `createSession` + ADK `streamQuery`.                 |
| "Sub-1-minute provisioning"            | ~3.5 min consistent (create and update)                                                     | Possibly applies to a deploy mode we didn't test, or marketing optimism.                                              | CI/CD planning: assume 4 min. Not blocking.                                                                                              |
| "Long-running operations up to 7 days" | No invocation LRO API. But per-request timeout _is_ effectively long.                       | Phrasing in release notes implies a fire-and-forget API that doesn't exist; the underlying durability behaviour does. | Functionally equivalent to what we want, via the caller-disconnect-survival path Test 1 proved. Watchdog still polls Firestore liveness. |

**Net effect on the migration plan:** the migration becomes _cleaner_ than the original probe writeup suggested. Custom session IDs working means deleting more plumbing, not less. The other two contradictions don't change the decision — they just calibrate expectations on provisioning time and watchdog design.

---

# Round 2 — operational gaps before migration plan

**Plan:** [`docs/gear-probe-plan-round2-2026-04-26.md`](./gear-probe-plan-round2-2026-04-26.md)
**Planned order:** R2.4 (Gemini 3.1, highest risk) → R2.5 (production shape) → R2.1+R2.2+R2.3+R2.6 batched → R2.7 Node script → R2.8 in-flight update.
**Actual execution order** (the plan's order didn't survive contact with reality — R2.4's first deploy attempt failed at pickle time before we could test invocation, so I deferred R2.4 and ran the others first):

1. R2.4 Attempt 1 (eager Client) → cloudpickle fail at deploy
2. R2.1 outbound HTTPS — kitchen probe deploy without SecretRef → PASS
3. R2.2 SecretRef Attempt 1 → runtime startup fail
4. R2.3 multi-turn state → PASS
5. R2.6 logs visibility → FAIL (logs not surfacing)
6. R2.7 Node-side `:streamQuery` → PASS (after fixing NDJSON parser)
7. R2.4 Attempt 2 (plugin hot-swap) → runtime callback-context error
8. R2.4 Attempt 3 (lazy Gemini subclass with wrong model name `gemini-3.1-flash`) → 404 (override worked, model wrong)
9. R2.4 Attempt 3b (lazy Gemini subclass with `gemini-3.1-pro-preview`) → PASS
10. R2.5 prod shape → PASS
11. Discovered `gcs_dir_name` clobber bug (parallel deploys overwriting each other's pickle), redeployed with isolated paths
12. R2.8 in-flight update — long invocation completed cleanly, but update() never actually fired due to harness config bug → INCONCLUSIVE
13. R2.2 SecretRef Attempt 2 (with both IAM grants and isolated path) → still runtime fail
14. R2.2 SecretRef Attempt 3 (`version="1"` instead of `"latest"`) → still runtime fail → conclude: use Secret Manager runtime fetch instead

**Operating principle:** if SDK fails, verify at REST level before concluding. (Lesson from round-1 Test 5 — the principle held: when SecretRef looked broken, I tried plain env_vars and confirmed the platform layer works for non-Secret env vars; when the eager Client cloudpickle failed, I worked through alternative client-construction patterns rather than declaring Gemini 3.1 unmigratable.)

---

## 2026-04-26 — Round-2 setup + R2.4 deploy-time blocker

**Probe artifacts written:**

- `agent/probe/kitchen_sink.py` — `LlmAgent` with three tools: `fetch_external_url`, `read_env`, `write_state_marker`. For R2.1, R2.2, R2.3, R2.6.
- `agent/probe/gemini3.py` — `LlmAgent` using production's `_make_gemini_global` pattern. For R2.4.
- `agent/probe/prod_shape.py` — `SequentialAgent[ParallelAgent[a,b], synth]` mirror of production structure. For R2.5.
- `agent/probe/run_round2.py` — unified test runner.
- `functions/probe-stream-query.js` — Node-side `:streamQuery` recipe. For R2.7.

**Setup:**

- Created Secret Manager secret `probe-test-key` with value `hello-from-secrets`.
- Granted `roles/secretmanager.secretAccessor` to `service-907466498524@gcp-sa-aiplatform.iam.gserviceaccount.com` (deploy-time SA, NOT the runtime `-re` SA — important nuance from the docs).
- Verified `from google.cloud.aiplatform_v1.types.env_var import SecretRef` works at our installed SDK version. Proto fields: `secret`, `version`.

**Deploy-time blocker for R2.4 (Gemini 3.1 + per-LlmAgent location override):**

```
TypeError: cannot pickle '_thread.lock' object
```

The `genai.Client(vertexai=True, location='global')` constructor immediately initializes a `BaseApiClient` which holds a `_thread.lock`. When cloudpickle tries to serialize the LlmAgent for deploy, it can't pickle the lock. **Deploy fails before even reaching Agent Runtime.**

This _exactly_ matches what [adk-python#3628](https://github.com/google/adk-python/issues/3628) describes. Our production pattern of building Client at LlmAgent-construction time is fundamentally incompatible with cloudpickle-based deploy.

**Implication:** the per-LlmAgent override pattern needs a different shape for Agent Runtime. Two candidate workarounds (will explore):

1. Defer Client construction inside a plugin's `before_model_callback` so the live client never gets pickled.
2. Use `before_run_callback` to mutate `agent.model.api_client` after the runtime unpickles.

Both require code changes in our `_make_gemini` factory. **R2.4 needs follow-up before we can declare migration scope on Gemini 3.1.**

---

## 2026-04-26 — R2.1 PASS: outbound HTTPS works

**Setup:** kitchen probe deployed (without SecretRef, see R2.2 below) at `projects/.../reasoningEngines/3851695334971408384`. Three URLs tested via `fetch_external_url` tool.

**Result:**

- `https://places.googleapis.com/` — reached (404 from server, expected for that bare path)
- `https://api.apify.com/v2/` — reached (404 from server, expected)
- `https://example.com/` — 200 OK

All three reached their destinations. **R2.1 PASS.** Default Agent Runtime egress is open to public internet exactly as docs claim. Production specialists' tool calls will work.

---

## 2026-04-26 — R2.2 deploy-time blocker

Initial deploy with `env_vars={"PLAIN_VAR": "plain-value", "SECRET_VAR": SecretRef(secret="probe-test-key", version="latest")}` failed with: **"Reasoning Engine resource [...] failed to start and cannot serve traffic."**

Re-deployed without the SecretRef, only plain env var → succeeded. So **SecretRef is the failure point.** Possible causes (not isolated yet):

- IAM not propagated when deploy ran
- `version="latest"` may need to be a numeric string `"1"`
- Resource path may need full `projects/{}/secrets/{}/versions/{}` form

**Will re-test after R2.4 / R2.5 with `version="1"`.** Not a hard blocker for migration — production currently uses Cloud Run env vars, not SecretRef. Could keep using Secret Manager via the `google.cloud.secretmanager` client inside the agent if SecretRef remains broken. But a clean SecretRef path is preferable.

---

## 2026-04-26 — R2.3 PASS: multi-turn session.state survives across invocations

**Setup:** custom-ID session `se-multiturn-1777204939` created via REST `:createSession?sessionId=...` with `sessionState={"runId": "r-mt", "attempt": 1, "turnIdx": 0, "preexisting_key": "set_at_create"}`. Then two `async_stream_query` calls 2s apart.

**Evidence:**

| moment                  | session.state                                                           |
| ----------------------- | ----------------------------------------------------------------------- |
| after createSession     | `{runId: r-mt, attempt: 1, turnIdx: 0, preexisting_key: set_at_create}` |
| after turn 1 (3 events) | identical                                                               |
| after turn 2 (3 events) | identical                                                               |

12 plugin docs across both turns: 2× before_run, 2× after_run, 2× agent_event, 6× event. **All show `runId='r-mt'`** — meaning `invocation_context.session.state` carried the create-time values into every callback for both turns.

**Conclusion:** `session.state` set at `createSession` time persists across multiple `stream_query` invocations on the same session, and is readable inside plugin callbacks via `invocation_context.session.state`. This validates the production-intended FirestoreProgressPlugin design across multi-turn flows.

**Sub-finding (not a fail, just a clarification):** Plain function tools that return values do NOT mutate session.state. State only changes through ADK's documented mechanisms (`output_key` on LlmAgent, `state_delta` from BaseAgent events, or `ToolContext.state`-aware tools). Our production agents already use `output_key` for state writes — same pattern as today, transfers cleanly.

---

## 2026-04-26 — R2.6 FAIL: logs from inside deployed runtime not visible in our project

**What I tried:**

- Three gcloud queries: by `resource.labels.reasoning_engine_id`, by `resource.type` + reasoning_engine_id, by resource.type alone. All empty after 90s.
- Direct Cloud Logging API via `google.cloud.logging.Client.list_entries()` — also empty.
- Granted `roles/logging.logWriter` to both `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (runtime SA) AND `service-907466498524@gcp-sa-aiplatform.iam.gserviceaccount.com` (deploy SA), waited 60s for IAM propagation.
- Re-ran invocation after IAM grants: still no logs visible.

**Probe agent contained:**

- `print("PROBE_STDOUT_MARKER ...", file=sys.stdout, flush=True)` — should land in `reasoning_engine_stdout`
- `print("PROBE_STDERR_MARKER ...", file=sys.stderr, flush=True)` — should land in `reasoning_engine_stderr`
- `logging.getLogger("probe_kitchen").info("PROBE_LOGGING_MARKER ...")` — would land in a custom log_id

**What the docs claim ([Logging an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/logging)):** stdout/stderr are auto-captured to `reasoning_engine_stdout`/`reasoning_engine_stderr` log IDs. No `setup_logging()` call needed for stdout/stderr.

**Interpretation:** either (a) auto-capture is not happening in our installed setup despite the docs, (b) auto-capture writes to a log scope we can't see (folder/org), or (c) the agent must explicitly call `setup_logging()` for ANY log to surface, including stdout, contradicting the docs.

**Operational implication for migration:** debugging a deployed Agent Runtime agent requires adding explicit `google-cloud-logging` setup inside the agent's `set_up()` method, OR relying on Firestore-based observability (which we already do via the FirestoreProgressPlugin). Not a migration blocker — production observability today is also Firestore-driven. But it means **lost-log debugging is harder than today's Cloud Run worker**, where stdout shows up reliably.

**Action item:** during the migration cutover phase, add explicit `google.cloud.logging.Client.setup_logging()` inside the App's `set_up()` and verify before declaring observability complete.

---

## 2026-04-26 — Discovered concurrent-deploy clobber, fixed with `gcs_dir_name`

When deploying multiple probe flavours in parallel, all writes go to `gs://{bucket}/agent_engine/agent_engine.pkl` and clobber each other. After two parallel deploys, both engines pointed at the same pickle path; the _last_ one wrote, both engines served the _last_ uploader's code.

**Discovered when:** `test_gemini3` returned `'synth_combined: spec_a_output spec_b_output'` — output from `prod_shape`'s synth, not from gemini3's instruction.

**Verified via REST `:reasoningEngines.get`:** both engines listed `pickleObjectGcsUri: gs://superextra-site-agent-engine-staging/agent_engine/agent_engine.pkl` — identical paths.

**Fix:** pass `gcs_dir_name=f"agent_engine_{flavour}"` to `agent_engines.create()` so each flavour stages to its own subdirectory. Verified working: subsequent isolated deploys produced distinct pickle paths and correct per-engine behaviour.

**Migration runbook implication:** if production deploys multiple agents (e.g., a staging agent alongside production), they MUST use distinct `gcs_dir_name` values or one will overwrite the other. Add to `docs/deployment-gotchas.md`.

---

## 2026-04-26 — R2.4 PASS (eventually) — Gemini 3.1 via lazy-init Gemini subclass

**Three failed attempts before success.** Documenting the path because the workaround is non-obvious.

**Attempt 1 — production pattern (eager Client at construction):**

```python
g = Gemini(model="gemini-3.1-flash", retry_options=RETRY)
g.api_client = Client(vertexai=True, location="global", ...)
```

**Failed at deploy time:** `TypeError: cannot pickle '_thread.lock' object`. The `genai.Client` constructor immediately initializes a `BaseApiClient` holding a `_thread.lock`. Cloudpickle can't serialize the lock. **This is exactly [adk-python#3628](https://github.com/google/adk-python/issues/3628).**

**Attempt 2 — plugin-based hot-swap via `before_model_callback`:**
Plan: deploy a bare Gemini, register a plugin that mutates `agent.model.api_client` at request time. Cloudpickle survives because no live Client at pickle time. Deploy succeeded but invocation returned: `Error in plugin 'global_client_injector' during 'before_model_callback' callback: 'Context' object has no attribute 'invocation_context'`. The `callback_context` param's actual type doesn't expose `invocation_context` directly; can't reach the agent from inside the plugin callback.

**Attempt 3 — lazy-init Gemini subclass (SUCCESS):**

```python
class GeminiGlobalEndpoint(Gemini):
    @property
    def api_client(self) -> Client:
        client = self.__dict__.get("_lazy_global_client")
        if client is not None:
            return client
        client = Client(vertexai=True, location="global", ...)
        self.__dict__["_lazy_global_client"] = client
        return client

    @api_client.setter
    def api_client(self, value):
        self.__dict__["_lazy_global_client"] = value
```

Pickle-safe because the live Client only exists _after_ unpickle on the deployed runtime. First read of `.api_client` constructs it on demand with `location='global'`. Confirmed:

- Cloudpickle: 1400 bytes ✓
- Deploy: succeeds ✓
- Invocation with `gemini-3.1-pro-preview`: returns `'ok-from-gemini-3.1'` ✓

**Side discovery (model name):** my first attempt with `gemini-3.1-flash` 404'd at `locations/global/publishers/google/models/gemini-3.1-flash` — proving the override IS routing to global, but the model ID was wrong. Production uses `gemini-3.1-pro-preview` and `gemini-3.1-pro-preview-customtools`. **Migration must use the lazy-init pattern, NOT the current eager pattern in `agent/superextra_agent/specialists.py:_make_gemini`.** That file needs surgery before migration.

---

## 2026-04-26 — R2.5 PASS — production agent shape works under deployed runtime

Deployed `SequentialAgent[ParallelAgent[spec_a, spec_b], synth]` with each LlmAgent using `output_key`.

**Result:**

- Events arrived in order `prod_spec_b → prod_spec_a → prod_synth` (parallel agents interleave by completion order, not strict definition order)
- `state_delta` per event correctly carried each agent's `output_key` write: `result_b='spec_b_output'`, `result_a='spec_a_output'`, `final='synth_combined: spec_a_output spec_b_output'`
- Final `session.state` (read via REST `:getSession`) contained all three keys
- Synthesizer's `instruction="...{result_a}...{result_b}..."` template substitution resolved correctly from upstream agents' state writes

**Conclusion:** every framework primitive our production agent depends on (`SequentialAgent`, `ParallelAgent`, `output_key`, template substitution from `state`) works under deployed Agent Runtime. **R2.5 PASS.**

---

## 2026-04-26 — R2.7 PASS — Node-side `:streamQuery` from Cloud Functions works

**Setup:** standalone Node 22 script (`functions/probe-stream-query.js`), uses `google-auth-library` for service-account bearer token, posts to `:streamQuery?alt=sse` with `Accept: text/event-stream`.

**Critical undocumented finding:** **Vertex AI `:streamQuery` returns NEWLINE-DELIMITED JSON (NDJSON), NOT standard SSE `data: ...\n\n` frames**, even with `?alt=sse` and `Accept: text/event-stream`. Verified by raw curl — each chunk is a complete JSON object on its own line, no `data:` prefix.

My initial Node parser looked for `data: ` prefix and got 0 events out of a 200 OK stream. **Fix:** parse line-by-line as plain JSON, no SSE prefix handling.

**After fix:**

- Cold call latency: 836ms to status 200, ~3.2s to first event
- 3 events parsed correctly: function_call, function_response, text
- Stream closes cleanly

**Migration implication:** the `agentStream` rewrite for Node 22 needs the NDJSON parser, not a standard EventSource library. Document this in the migration plan — fairly subtle gotcha that would otherwise eat a day of debugging.

---

## 2026-04-26 — R2.8 partial — long invocation completed, update() failed for harness reason

**Setup:** start a 5-min `lifecycle` invocation, fire `agent_engines.update()` 60s into the run.

**Result:** the long invocation **completed all 5 events** (T+62s, +122s, +183s, +243s, +303s) cleanly, despite the planned mid-stream update. **But the update() call itself errored with `ValueError: Please provide a 'staging_bucket' in vertexai.init(...)`** — my harness didn't pass the bucket on re-init. So we don't have proof the update would have killed the run; we only have the negative observation that "even when an update was attempted, the long invocation finished."

**Honest read:** R2.8 is inconclusive. The migration cutover should be done during a quiet window (no in-flight invocations), or with an A/B deploy that creates a new resource and switches traffic. Don't rely on this experiment as proof of zero-downtime updates.

---

## 2026-04-26 — R2.2 FAIL on SecretRef — runtime fetch is the migration path

Three deploy attempts with `env_vars={"SECRET_VAR": SecretRef(secret="probe-test-key", version="latest")}` and `version="1"`, with `roles/secretmanager.secretAccessor` granted to the deploy SA, with isolated `gcs_dir_name`. **All three failed identically:** `Reasoning Engine resource [...] failed to start and cannot serve traffic.` Logs from the failing engine never surfaced (R2.6 issue), so the actual exception is hidden.

Plain env_vars (no SecretRef) deploy and resolve correctly — R2.2 partial pass.

**Migration path (recommended):** don't use SecretRef. Instead, fetch secrets at agent runtime via `google.cloud.secretmanager.SecretManagerServiceClient` inside the agent's `set_up()` method. Same SA grant (`roles/secretmanager.secretAccessor`) on the **runtime** `-re` SA, and you read the secret value once at startup and cache it. This approach also lets secrets rotate without redeploy.

**Add to migration runbook:** SecretRef in `env_vars` is documented but appears unreliable in practice — use runtime fetch pattern.

---

## 2026-04-26 — Round-2 complete

Summary table for results report:

| Test                          | Result                                   | Migration impact                                                                                                |
| ----------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| R2.1 outbound HTTPS           | PASS                                     | Production tools' external HTTP calls work                                                                      |
| R2.2 SecretRef env vars       | FAIL — use runtime fetch instead         | Migration plan: secrets via `secretmanager.SecretManagerServiceClient` in `set_up()`, NOT SecretRef             |
| R2.3 multi-turn session.state | PASS                                     | Existing pattern transfers cleanly                                                                              |
| R2.4 Gemini 3.1 routing       | PASS via lazy-init Gemini subclass       | Production `_make_gemini` factory needs rewrite to lazy pattern; documented                                     |
| R2.5 prod agent shape         | PASS                                     | `SequentialAgent`, `ParallelAgent`, `output_key`, state-template substitution all work                          |
| R2.6 logs visibility          | FAIL — auto-capture not surfacing in API | Use Firestore-driven observability (already do); add explicit `setup_logging()` for stdout-style logs if needed |
| R2.7 Node `:streamQuery`      | PASS — NDJSON, not SSE frames            | Migration plan: use line-by-line JSON parser, not EventSource                                                   |
| R2.8 in-flight update         | INCONCLUSIVE (harness bug)               | Cutover during quiet window or via A/B resource swap                                                            |

**Net assessment:** migration is still approved. Five tests passed (some with workarounds), one failed (R2.2 SecretRef → use runtime fetch instead), one inconclusive (R2.8 → cutover strategy implication).

**Critical migration prerequisites surfaced by round 2:**

1. Rewrite `_make_gemini` to lazy-init Gemini subclass — required for Gemini 3.1.
2. Use `gcs_dir_name=f"agent_engine_{name}"` per deployment — avoids clobbering.
3. Grant BOTH `service-{N}@gcp-sa-aiplatform.iam.gserviceaccount.com` (deploy-time SA, e.g. for SecretRef) AND `service-{N}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (runtime SA, for Firestore/logs/secrets).
4. Use NDJSON parser in Node-side `agentStream` (not EventSource).
5. Fetch secrets via `secretmanager.SecretManagerServiceClient` inside `set_up()` rather than relying on SecretRef.
6. Add explicit `google.cloud.logging.Client.setup_logging()` if production debugging needs stdout/stderr surfaced.

---

## 2026-04-26 — Consolidated IAM grants made during the probe

For migration cleanup / rollback. Run by:

- `service-907466498524@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (runtime SA, the `-re` one):
  - `roles/datastore.user` — for Firestore writes from inside the plugin
  - `roles/logging.logWriter` — granted but logs still didn't surface (R2.6)
- `service-907466498524@gcp-sa-aiplatform.iam.gserviceaccount.com` (deploy/non-`-re` SA):
  - `roles/datastore.user` — granted by mistake initially (was hunting for the right SA before finding the `-re` variant)
  - `roles/logging.logWriter` — granted as part of R2.6 troubleshooting
  - `roles/secretmanager.secretAccessor` — for SecretRef in env_vars (R2.2)

**Production migration:** keep `roles/datastore.user`, `roles/logging.logWriter`, and `roles/secretmanager.secretAccessor` on the `-re` runtime SA. Drop the non-`-re` SA grants when the probe is cleaned up — they were either misdirected or are unnecessary if we use runtime secret fetch (the recommended path per R2.2).

---

## 2026-04-26 — Probe artifacts — what stays, what goes

**Probe Reasoning Engines deployed during this work** (for cleanup):

| flavour                | id                                                                                                                                               | purpose                                                    |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| lifecycle              | 329317476414259200                                                                                                                               | DeterministicSlowAgent (5-event run for Test 1, R2.8)      |
| event_shape            | 8725153081739706368                                                                                                                              | LlmAgent + echo_tool (Test 3, baseline)                    |
| kitchen                | 3851695334971408384                                                                                                                              | LlmAgent with outbound + env-read tools (R2.1, R2.3, R2.6) |
| gemini3 (final)        | 886074980347936768                                                                                                                               | Gemini 3.1 lazy-subclass — passing version                 |
| prod_shape (final)     | 7256416653263503360                                                                                                                              | SequentialAgent[ParallelAgent, synth] (R2.5)               |
| various failed deploys | 8483647551721963520, 5036142036969848832, 4896530448521363456, 3172777691145306112, 2397032655330738176, 629369801587818496, 7271616302005878784 | superseded — to delete                                     |

**Probe code committed to repo:** `agent/probe/` (8 files: `agent.py`, `gemini3.py`, `kitchen_sink.py`, `prod_shape.py`, `probe_plugin.py`, `deploy.py`, `run_probe.py`, `run_round2.py`, `watch_firestore.py`, `kill_after_first_event.sh`, `requirements.txt`, `deployed_resources.json`) plus `functions/probe-stream-query.js`.

**Migration cutover decision:** keep these in repo as reference for the migration plan. Move to `agent/probe-archive/` after migration completes.

---

# Round 3 — verifying P0 mechanics before v3

**Plan:** [`docs/gear-probe-plan-round3-2026-04-26.md`](./gear-probe-plan-round3-2026-04-26.md)
**Triggered by:** reviewer findings on v2 — two unverified mechanics (per-turn session.state mutation + Cloud Function explicit-abort handoff). Both must pass for migration approval.
**Operating principle:** R3.2 gate is the **explicit-abort variant** (`reader.cancel()` + `controller.abort()` before `res.send()`), NOT a leave-open fetch. Leave-open is captured separately as a diagnostic.

---

## 2026-04-26 — R3 setup

**Plugin update:** added `invocation_id` to `ProbePlugin._meta()` so every Firestore doc tags which `stream_query` invocation produced it. Lets R3.1 isolate turn-1 docs from turn-2 docs within the same session by `invocation_id` (primary) plus `ts >= turn{N}_started_at` markers (sanity).

**Kitchen redeploy required** to pick up the plugin change.

---

## 2026-04-26 — Setup completed

- `agent/probe/probe_plugin.py` updated — `_meta()` now records `invocation_id` from `getattr(ctx, 'invocation_id', None)` in every doc.
- Kitchen probe redeployed via `agent_engines.update()` — completed in 196.8s (~3.3 min). Same resource id `3851695334971408384`.
- `functions/package.json` — added `google-auth-library@^9.15.1` as direct dependency. `npm install` ran cleanly.
- `functions/index.js` — added `probeHandoffAbort` and `probeHandoffLeaveOpen` Cloud Functions per plan. Both use shared `_runHandoff()` helper. Initial deploy used `timeoutSeconds=30` per the plan.
- ADC quota project: had to add `quota_project_id: superextra-site` to `~/.config/gcloud/legacy_credentials/adam@finebite.co/adc.json` AND set `GOOGLE_CLOUD_QUOTA_PROJECT` env var for `firebase deploy` to succeed.
- CF deploy: `firebase deploy --only "functions:probeHandoffAbort,functions:probeHandoffLeaveOpen" --project=superextra-site --force` worked. URLs:
  - `probeHandoffAbort`: `https://probehandoffabort-22b3fxahka-uc.a.run.app`
  - `probeHandoffLeaveOpen`: `https://probehandoffleaveopen-22b3fxahka-uc.a.run.app`

---

## 2026-04-26 — R3 blocker hit and resolved: CF timeout vs lifecycle agent's 60s first-event delay

First R3.2 attempt with CF `timeoutSeconds=30` hit `504 Gateway Timeout` at 30.25s. Cause: the lifecycle `DeterministicSlowAgent` sleeps 60s before yielding the first event. CF can't read first NDJSON line within 30s, so it times out before reaching the abort step.

**Resolution:** bumped CF `timeoutSeconds` from 30 → 90. Acknowledged deviation from production's current 30s, but documented as a finding — production agentStream's 30s is for the OLD pattern (Cloud-Tasks-enqueue is sub-second). The new pattern needs to wait for first-NDJSON-line handoff proof, which takes up to ~60s for our deepest specialists' first response. Migration plan v3 must bump agentStream's timeout to ≥90s.

Also bumped harness's `requests.post` timeout from 60s → 120s for the same reason (CF can take up to 90s; harness needs to wait longer than the CF).

Redeployed CFs with new timeout. R3.2 retest succeeded (see below).

---

## 2026-04-26 — R3.1 PASS — `:appendEvent` mutates session.state per turn

**Mechanism that worked:** REST `:appendEvent` with camelCase JSON body containing `actions.stateDelta` and an RFC3339 timestamp.

**Mechanism (a) — PATCH:** rejected by platform with explicit error message: _"Can't update the session state for session [...], you can only update it by appending an event."_ The platform tells you exactly where to go. Mechanism (a) is intentionally not supported.

**Mechanism (b) — `:appendEvent`:** worked. Successful payload:

```json
POST .../sessions/{sid}:appendEvent
{
  "author": "system",
  "invocationId": "r31-mutate-{ts}",
  "timestamp": "2026-04-26T18:18:41.775335Z",
  "actions": {"stateDelta": {"runId": "r-2", "turnIdx": 1, "attempt": 1}}
}
→ 200 {}
```

**First attempt failure mode worth recording:** my initial `:appendEvent` body had `timestamp: time.time()` (Unix float). Platform rejected with: _"Invalid value at 'event.timestamp' (type.googleapis.com/google.protobuf.Timestamp), Field 'timestamp', Invalid data type for timestamp, value is 1777227316.81987"_. Fix: use RFC3339 string format (`datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")`). camelCase fields (`invocationId`, `stateDelta`) are required — snake_case (`invocation_id`, `state_delta`) was wrong.

**Verification chain:**

1. After `:appendEvent`, REST `:getSession` returns the new state: `{runId: r-2, turnIdx: 1, attempt: 1}`.
2. Turn 2 `async_stream_query` invocation produces 6 plugin docs (1 before_run, 3 event, 1 agent_event, 1 after_run).
3. All 6 docs (filtered by turn 2's `invocation_id=e-b4aa7386-ee60-4da7-8db5-4a5561f54dfe`) carry `runId=r-2, turnIdx=1, attempt=1` — the mutated state, not turn 1's original `r-1`.

**Verdict: PASS.** Per-turn metadata propagation works via `:appendEvent`. Production migration plan should call `:appendEvent` from `agentStream` _before_ invoking `streamQuery` for each turn, with the new turn's `runId`/`attempt`/`turnIdx` in `actions.stateDelta`.

Reviewer P0 #1 resolved: not just discovered, but with the exact REST recipe documented.

---

## 2026-04-26 — R3.2 abort variant PASS — explicit clean disconnect

**Setup:** `probeHandoffAbort` Cloud Function calls `:streamQuery` against the lifecycle probe (5-min `DeterministicSlowAgent`), reads first NDJSON line, then **explicitly** `reader.cancel()` + `controller.abort()` BEFORE `res.status(202).send()`.

**Run 1 evidence:**

- CF response time: 62.26s (waited for first NDJSON line, ~60s after streamQuery started)
- CF response body: `{"handoff":"received_first_event","variant":"abort","first_line_len":353}`
- `cf_returned_at` server timestamp: `2026-04-26T18:24:19.664Z`
- Watched Firestore for `after_run`:
  - elapsed=62s: event 2 landed (post-abort)
  - elapsed=123s: event 3 landed (post-abort)
  - elapsed=184s: event 4 landed (post-abort)
  - elapsed=244s: event 5 + agent_event + `after_run` all landed
- `after_run.ts`: `2026-04-26T18:28:20.293Z`
- **Gap between explicit abort and terminal write: 240.6 seconds.**
- Final doc count: 8 (1 before_run + 5 event + 1 agent_event + 1 after_run) — all expected docs landed.

**Verdict: PASS.** Agent Runtime survives explicit clean disconnect from a Cloud Function. The CF can read first NDJSON line as handoff proof, abort the request, return 202, and the runtime continues to drive the agent to completion. This is the supported clean-handoff pattern the migration's `agentStream` design needs. **Reviewer P0 #2 resolved with timestamp-precise evidence.**

---

## 2026-04-26 — R3.2 abort run 2 PASS — repeatability confirmed

Repeated the gate variant from cold to rule out warm-instance caching effects.

- CF response time: ~62s (consistent with run 1)
- `cf_returned_at`: `2026-04-26T18:30:59.424Z`
- `after_run.ts`: `2026-04-26T18:35:00.054Z`
- **Gap: 240.6s** — identical to run 1 to one decimal. Highly reproducible.
- Final doc count: 8 (full expected shape).

**Repeatability confirmed. Two passes under cold conditions.**

---

## 2026-04-26 — R3.2 leave_open diagnostic — completes, but informationally only

Same Cloud Function infrastructure, different variant: `probeHandoffLeaveOpen` skips `reader.cancel()` and `controller.abort()` before returning 202. Per Firebase docs, this is undefined behaviour — the fetch may be killed by CPU throttling, or it may continue, no guarantees.

**First attempt error:** `requests.exceptions.HTTPError: 400` — sessionId `se-r32-leave_open-{ts}` violates `[a-z0-9-]` constraint (underscore in `leave_open`). Fixed harness to convert `_` → `-` for the sid: `se-r32-leave-open-{ts}`. Worth recording: same hyphen-only constraint applies to user-supplied IDs.

**After fix:**

- CF response: 202, ~62s elapsed (similar to abort variant — both wait for first NDJSON line)
- `cf_returned_at`: `2026-04-26T18:36:14.827Z`
- `after_run.ts`: `2026-04-26T18:40:15.277Z`
- **Gap: 240.4s** — essentially identical to abort variant.
- All 8 docs landed.

**Diagnostic interpretation:** in _this_ run, leave-open and explicit-abort produced indistinguishable platform behaviour. **This does NOT change the gate.** Firebase's documented termination semantics still apply — the leave-open pattern is unsupported and may break under different CF instance lifetimes or scaling conditions. The migration's `agentStream` MUST use the explicit-abort pattern.

The interesting finding: under our specific test conditions, the platform appears to treat both disconnect modes identically. This is consistent with the round-1 Test 1 finding (`kill -9` of an external process also caused full completion). Agent Runtime's caller-disconnect-survival appears robust across all observed failure modes — but we should not lean on undocumented behavior in production.

---

## 2026-04-26 — R3 complete — VERDICT: APPROVE migration with v3

**Gate evaluation per plan §"Decision contract":**

| Test | Variant                 | Result             | Evidence                                                                                                            |
| ---- | ----------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------- |
| R3.1 | sessionState mutability | **PASS**           | `:appendEvent` with `actions.stateDelta` + RFC3339 timestamp; turn-2 plugin docs all carry `runId=r-2`, `turnIdx=1` |
| R3.2 | explicit abort (gate)   | **PASS** (run 1)   | Gap 240.6s, full 8 docs                                                                                             |
| R3.2 | explicit abort (gate)   | **PASS** (run 2)   | Gap 240.6s, full 8 docs (identical)                                                                                 |
| R3.2 | leave-open (diagnostic) | informational PASS | Gap 240.4s — same behaviour, but undocumented                                                                       |

**Decision: MIGRATION APPROVED. Write v3.**

**v3 must include (delta from v2):**

1. **Per-turn metadata propagation via `:appendEvent`** — not via `createSession` state field alone. agentStream's per-turn flow becomes:
   1. `:createSession` (first turn only) with initial `sessionState`
   2. For every turn: `:appendEvent` with `actions.stateDelta={runId, attempt, turnIdx}` to mutate state for the upcoming invocation
   3. Then `:streamQuery` — the plugin will read the just-mutated state from `invocation_context.session.state`
   4. Read first NDJSON line as handoff proof
   5. Explicit `reader.cancel()` + `controller.abort()`
   6. Return 202 to browser
2. **agentStream timeout bumped from 30s → 90s+** to wait for first NDJSON line. Document this — current 30s is for old Cloud-Tasks-enqueue pattern.
3. **`:appendEvent` payload is camelCase** with RFC3339 timestamp string (NOT Unix float).
4. **sessionId regex constraint**: `[a-z][a-z0-9-]*[a-z0-9]` — no underscores, no uppercase. Our `se-{uuid}` pattern is fine since UUIDs are hex.
5. **Reviewer P1/P2 corrections from v2 review** — fold all of them in:
   - session-stickiness routing via `transport: 'cloudrun'|'gear'` field on session doc
   - keep `adkSessionId` field through 30-day rollback window; delete in cleanup commit only after worker decommission
   - plugin-owned heartbeat asyncio task (spawned in `before_run_callback`, cancelled in `after_run_callback`)
   - write-class taxonomy (best-effort vs critical vs heartbeat) for plugin defensive code
   - `google-auth-library` direct dep in `functions/package.json` (already added during R3 setup, keeping)
   - `google-cloud-secret-manager` in `agent/requirements.txt` for runtime secret fetch
   - recommendation-section narrative correction: heartbeat/takeover/fencing SURVIVE; deletable code is FastAPI/Cloud Run/Cloud Tasks/in-process Runner

**Reviewer P0 issues both resolved with empirical evidence.** No outstanding gates blocking the migration.

---

## 2026-04-26 — Round 3 cleanup checklist

- [ ] Delete deployed Cloud Functions explicitly (Gen 2 doesn't auto-clean):
  ```bash
  firebase functions:delete probeHandoffAbort --region us-central1 --project=superextra-site --force
  firebase functions:delete probeHandoffLeaveOpen --region us-central1 --project=superextra-site --force
  ```
- [ ] Remove `_runHandoff`, `probeHandoffAbort`, `probeHandoffLeaveOpen`, and the `GoogleAuth` import from `functions/index.js` after CF delete.
- [ ] Keep `google-auth-library` in `functions/package.json` — migration's `agentStream` rewrite will use it.
- [ ] Keep `agent/probe/probe_plugin.py`'s `invocation_id` change — clean improvement, no rollback.
- [ ] R3 probe scripts (`run_r31.py`, `run_r32.py`) stay in repo as reference until migration completes.
- [ ] R3 sessions (`se-r31-*`, `se-r32-*`) remain in their parent Reasoning Engines until cleanup of all R1/R2/R3 probe resources.
