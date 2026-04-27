# GEAR migration kill-or-commit probe — plan

**Status:** Plan, ready to execute
**Author:** Architecture working session, 2026-04-26
**Decision being made:** Whether Gemini Enterprise Agent Platform's Agent Runtime can own the durable run lifecycle for a Superextra-shaped chat turn (7–15 min, multi-agent, plugin-driven Firestore progress writes). Pass = rewrite migration plan and execute. Fail = stay on current architecture, no further transport work, re-evaluate only when Google ships a documented LRO/durable-invocation primitive for ADK chat turns.

This document specifies the probe. It does not migrate anything. It exists to prevent a fourth transport rewrite from happening on unverified assumptions.

---

## 0. Why this exists

The April 2026 Cloud Next release notes mention "long-running operations up to 7 days" for Agent Runtime, but the public REST reference for `projects.locations.reasoningEngines` exposes only `:query` and `:streamQuery` — both synchronous/streaming HTTP. There is no documented per-invocation LRO API for ADK chat turns, and Google does not document caller-disconnect behavior. The migration proposal (`docs/gear-migration-proposal-2026-04-25.md`) assumed fire-and-forget would work; reviewer's P0 correctly flagged this as unverified. Until we test it, we cannot decide.

The probe answers one question with binary precision: **can Agent Runtime complete a chat-turn run durably without a live caller?** §1 defines the gate; every other piece of this document exists to make that gate decidable from evidence rather than vibes.

---

## 1. Decision criteria

The real question is **"can Agent Runtime complete a chat-turn run durably without a live caller?"** That can be answered two ways: (a) `streamQuery` survives caller disconnect, or (b) a documented durable invocation primitive (LRO, background mode, operation ID) exists for ADK chat turns and works. Either path satisfies the gate.

Each probe is rated **Pass / Fail / Inconclusive**. The migration proceeds if **Test 1 passes OR Test 2 demonstrates a documented durable invocation path**. Both are first-class gates; either alone is sufficient.

| #     | Test                                                 | Pass criterion                                                                                                                                                                                                                                                                                                                                                                                                       | Fail criterion                                                                                                                                                                                                             |
| ----- | ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1** | **Caller-disconnect survival** (gate A)              | Run completes after caller is killed mid-stream. `after_run_callback` lands in Firestore _after_ the kill, with timestamp evidence (`after_run.ts > caller_killed_at + 60s` — see §4 Test 1).                                                                                                                                                                                                                        | No `after_run` doc within 10 min of kill, OR the doc landed before the kill (proves nothing).                                                                                                                              |
| **2** | **Documented durable invocation primitive** (gate B) | A documented durable primitive (LRO, background mode, operation ID) is **invoked end-to-end against the probe**: chat turn started through the primitive, caller detached, run polled to success via `operations.get` (or equivalent), `after_run_callback` lands in Firestore. API-shape evidence alone is not pass — the primitive must complete a real run without a live caller. See §4 Test 2.                  | No documented durable primitive exists, OR one exists but cannot complete a probe run end-to-end without a live caller.                                                                                                    |
| 3     | Plugin callbacks fire on deployed runtime            | `before_run_callback`, `on_event_callback`, and `after_run_callback` all observed firing on Agent Runtime via Firestore writes. `on_event_callback` is the load-bearing one — the production `FirestoreProgressPlugin` will iterate real ADK `Event` objects through it. `after_agent_callback` is captured as supplementary evidence only. Mitigates ADK [#4464](https://github.com/google/adk-python/issues/4464). | `on_event_callback` doesn't fire on deployed runtime, OR `before_run`/`after_run` missing.                                                                                                                                 |
| 4     | Plugin metadata propagation via session state        | `runId`, `attempt`, `turnIdx` set at `create_session(state={...})` time are readable inside callbacks via `invocation_context.session.state`. `userId` and `session_id` are read directly from `invocation_context`. **This is the production-intended mechanism — no fallback to message-text encoding is acceptable for pass.**                                                                                    | `session.state` not exposed to deployed-runtime callbacks. (Failure here is a major migration blocker — without reliable metadata propagation, the FirestoreProgressPlugin cannot attribute writes to the right run/turn.) |
| 5     | Custom session ID acceptance                         | `se-{uuid}` prefixed ID accepted; raw UUID starting with a digit rejected by Google's `[a-z][a-z0-9-]*[a-z0-9]` regex.                                                                                                                                                                                                                                                                                               | Prefixed ID rejected (would contradict docs; investigate).                                                                                                                                                                 |
| 6     | Duplicate dispatch behavior                          | Two `streamQuery` calls with the same `(user_id, session_id)` either: (a) Agent Runtime serializes/rejects the second, or (b) both run independently. Either result is informative — it tells us where idempotency must live.                                                                                                                                                                                        | Test errors out before completion (inconclusive).                                                                                                                                                                          |
| 7     | Cold start + concurrency                             | Measure: first call after >10 min idle (cold), immediate re-run (warm), 5 concurrent runs (load). **Record config used for each measurement: `min_instances`, `container_concurrency`, container size.** No fixed thresholds — output is a config-tagged latency table that informs whether `min_instances=1` warming is needed for production.                                                                      | Soft-fail interpretation only; this test does not gate migration approval.                                                                                                                                                 |

**Output artifact:** `docs/gear-probe-results-{date}.md`. One section per test: result, evidence (Firestore doc paths, log excerpts, raw curl/HTTP responses), one-paragraph conclusion. **Pinned dependency versions and Agent Runtime config recorded at top.** No prose padding.

---

## 2. Probe architecture

The smallest agent that exercises the patterns we care about. Lives in a throwaway directory `agent/probe/` so it can't accidentally affect production.

### 2.1 The probe agent — two flavours, one app

For lifecycle tests (1, 4, 6, 7) we want **deterministic** behaviour — an LlmAgent told to "call slow_step" can decide not to, or hallucinate args. So the lifecycle path uses a custom `BaseAgent` subclass that yields events on a timer, no LLM in the loop. Test 3 (callback shape verification with realistic ADK events) keeps a small `LlmAgent` + tool path so we exercise the actual event taxonomy plugins will see in production.

```python
# agent/probe/agent.py
import asyncio
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.apps import App
from google.adk.events.event import Event
from google.genai import types

class DeterministicSlowAgent(BaseAgent):
    """Yields N events spaced by sleep_seconds. No LLM, no tools, no
    decisions. Total runtime = num_events * sleep_seconds. Used for the
    lifecycle gate so probe outcomes can't be confounded by LLM behaviour."""

    num_events: int = 5
    sleep_seconds: int = 60

    async def _run_async_impl(self, ctx):
        for i in range(self.num_events):
            await asyncio.sleep(self.sleep_seconds)
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=f"step_{i}_done")],
                ),
            )

# Lifecycle path: 5 events × 60s = 5 min run.
lifecycle_root = DeterministicSlowAgent(name="probe_lifecycle")

# Event-shape path (Test 3 only): real LLM + tool call so plugins see the
# actual event taxonomy.
def echo_tool(message: str) -> dict:
    return {"echoed": message}

event_shape_root = LlmAgent(
    name="probe_event_shape",
    model="gemini-2.5-flash",
    instruction="Call echo_tool with message='hello'. Then reply 'done'.",
    tools=[echo_tool],
)

# Single deployed app, two roots selected at invocation time via a
# wrapper agent that reads the message intent. Simpler: deploy two apps,
# probe both. Choose at probe time.
lifecycle_app = App(
    name="superextra-probe-lifecycle",
    root_agent=lifecycle_root,
    plugins=[ProbePlugin()],
)
event_shape_app = App(
    name="superextra-probe-event-shape",
    root_agent=event_shape_root,
    plugins=[ProbePlugin()],
)
```

### 2.2 The probe plugin

Signatures match what `agent/superextra_agent/chat_logger.py:113,134,144` already proves works in our setup with `google-adk==1.28.0`. The run-level callbacks (`before_run_callback`, `after_run_callback`) take `invocation_context: InvocationContext`, not `callback_context`. That distinction matters — using the wrong signature will cause silent registration failure rather than a clean error.

```python
# agent/probe/probe_plugin.py
import asyncio
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.base_agent import BaseAgent
from google.cloud import firestore
from typing_extensions import override

class ProbePlugin(BasePlugin):
    def __init__(self):
        super().__init__(name="probe_plugin")
        self.fs = firestore.Client()

    def _meta(self, ctx) -> tuple[str, dict]:
        """Read sid (== session.id) and the runId/attempt/turnIdx that the
        harness placed in session.state at create_session() time. This is
        the production-intended mechanism — see Test 4."""
        sid = ctx.session.id
        st = ctx.session.state or {}
        return sid, {
            "runId": st.get("runId", "missing"),
            "attempt": st.get("attempt", "missing"),
            "turnIdx": st.get("turnIdx", "missing"),
            "userId": getattr(ctx, "user_id", "missing"),
        }

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext) -> None:
        sid, meta = self._meta(invocation_context)
        await self._write(sid, "before_run", meta)

    @override
    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        sid, meta = self._meta(invocation_context)
        await self._write(sid, "after_run", meta)

    # Load-bearing per-event hook. The production FirestoreProgressPlugin
    # will iterate real ADK Event objects here. ADK 1.28.0 BasePlugin
    # exposes on_event_callback(invocation_context, event) — if the actual
    # signature differs, the probe records the TypeError and reports.
    @override
    async def on_event_callback(self, *, invocation_context: InvocationContext, event) -> None:
        sid, meta = self._meta(invocation_context)
        await self._write(sid, "event", {
            **meta,
            "event_author": getattr(event, "author", None),
            "event_id": getattr(event, "id", None),
            "is_final": bool(getattr(event, "is_final_response", lambda: False)()),
        })

    # Supplementary evidence — not gate-bearing. Confirms agent-level
    # callbacks also work, useful for production callbacks like the
    # existing ChatLoggerPlugin pattern.
    @override
    async def after_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> None:
        sid, meta = self._meta(callback_context)
        await self._write(sid, "agent_event", {**meta, "agent": agent.name})

    async def _write(self, sid: str, kind: str, extra: dict) -> None:
        doc = {
            "sid": sid,
            "kind": kind,
            "ts": firestore.SERVER_TIMESTAMP,
            **extra,
        }
        ref = (
            self.fs.collection("probe_runs")
            .document(sid)
            .collection("events")
            .document()
        )
        await asyncio.to_thread(ref.set, doc)
```

### 2.3 The probe harness

Three small scripts in `agent/probe/`:

- `run_probe.py` — deploy (or reuse) the probe app, create a session with `state={runId, attempt, turnIdx}`, fire `async_stream_query`, iterate events, write a local `last_event_received_at` marker per event.
- `kill_after_first_event.sh` — observe-then-kill wrapper. Tails Firestore for the first `kind=before_run` or `kind=agent_event` doc, _then_ writes `caller_killed_at` marker to Firestore + `kill -9`s the harness. **Killing on a fixed sleep risks killing before the runtime has actually started** — observe-then-kill avoids that.
- `watch_firestore.py` — polls `probe_runs/{sid}/events` for `kind=after_run`, returns exit 0 if found AND `after_run.ts > caller_killed_at + 60s`. Non-zero otherwise.

```bash
# Test 1 baseline — no kill, full run, confirms agent + plugin work together
.venv/bin/python agent/probe/run_probe.py --sid se-run001 --no-kill

# Test 1 actual — observe first event, then kill, then verify post-kill completion
./agent/probe/kill_after_first_event.sh --sid se-run002
.venv/bin/python agent/probe/watch_firestore.py --sid se-run002 --min-gap-seconds 60 --timeout 600
echo "Test 1 result: $?"
```

The watch script's exit code is the test result:

- **0 = pass:** `after_run` doc exists AND its server timestamp is > 60s after `caller_killed_at`. Both conditions required — the time-gap proves the runtime continued executing past the kill, not that the doc was already in flight when we killed.
- **1 = fail:** no `after_run` doc within 10 min of kill.
- **2 = inconclusive:** `after_run` exists but timestamp is <= `caller_killed_at` (means the run completed before the kill landed; re-run with longer agent).

Run twice to confirm not-flake. Both must pass.

---

## 3. Setup

### 3.1 Cloud project

Use `superextra-site` with a test prefix. **Do not create a separate project** — IAM and ADC are already set up; it's not worth the friction. Resource isolation:

- Agent Runtime resource name: `superextra-probe-{date}`. Deleted after probe.
- Firestore collection: `probe_runs/*` — outside the production `sessions/*` namespace, with TTL set to 7 days.
- Service account: reuse `superextra-worker@superextra-site.iam.gserviceaccount.com` (already has Vertex + Firestore perms).

### 3.2 Dependencies

Pinned exactly so probe results are reproducible. Match production where it matters (`google-adk==1.28.0`, `google-cloud-firestore==2.22.0` per `agent/requirements.txt`). Record the lockfile in the result report.

`agent/probe/requirements.txt`:

```
google-cloud-aiplatform[agent_engines,adk]==1.144.0
google-adk==1.28.0
google-cloud-firestore==2.22.0
typing-extensions>=4.12
```

If `agent_engines.create()` fails to install the probe app due to dep resolution, record the exact error in the report. The [March 2026 Poetry venv hang](https://github.com/google/adk-python/issues/4762) was reportedly fixed in the new base image — verify by timing the deploy.

### 3.3 Environment

The Cloud Next 2026 release notes flagged that Gemini 3 series models still need `GOOGLE_CLOUD_LOCATION=global`. Set it via `env_vars` on `agent_engines.create(...)` — verified pattern from [How to Run Gemini 3 on Agent Engine with ADK](https://dev.to/koichi73/how-to-run-gemini-3-on-agent-engine-with-adk-4caj). Probe uses `gemini-2.5-flash` so this won't bite, but document for the migration if probe passes.

---

## 4. Test execution plan

Tests 1, 2, 3, 4 are gating. Tests 5, 6, 7 are informative — they shape the migration but don't gate it. Run all of them regardless of Test 1's outcome (Test 2 in particular, per reviewer P2 — its result informs watchdog/cancellation/observability design even if Test 1 already passed).

### Test 1 — Caller-disconnect survival (gate A)

**Setup:** lifecycle probe app deployed. Harness creates session `se-run001` with `state={runId: "r1", attempt: 1, turnIdx: 0}` and starts `async_stream_query`.

**Action — observe-then-kill:**

1. Harness streams events; each one writes a local marker file with the event timestamp.
2. `kill_after_first_event.sh` watches Firestore for the _first_ `kind=before_run` or `kind=agent_event` doc with `sid=se-run001`. Only after observing one does it write a `caller_killed_at` doc to Firestore (`probe_runs/se-run001/markers/caller_killed_at`) AND `kill -9` the harness.
3. This avoids the race where a fixed-delay kill happens before the runtime has actually started executing the agent.

**Pass check (both required):**

- A `kind=after_run` doc exists in `probe_runs/se-run001/events/`.
- That doc's server timestamp is **at least 60 s after** the `caller_killed_at` marker. The 60s gap is the load-bearing evidence — it proves the runtime continued executing past the kill, not that the terminal write was already in flight.

**Fail check:** No `after_run` doc within 10 min of `caller_killed_at`.

**Inconclusive:** `after_run` exists but timestamp is `<= caller_killed_at`. Means the run completed before the kill — re-run with a longer-running agent (bump `num_events` in `DeterministicSlowAgent`).

**Repeat:** Run twice to rule out flake. Both must pass.

### Test 2 — Documented durable invocation primitive (gate B, always run)

Run regardless of Test 1's outcome. Even if Test 1 passes, the result here informs watchdog design, cancellation semantics, delete-mid-run behavior, and observability.

**Phase 2a — discovery (cheap, ~30 min):** Inspect three sources for _evidence_ of a durable invocation primitive for ADK chat turns (not for deploy/lifecycle):

1. **REST response on `:streamQuery`.** Issue a raw `requests.post(..., stream=True)` against `https://{location}-aiplatform.googleapis.com/v1/{resource}:streamQuery?alt=sse`. Capture full HTTP response headers and the first SSE chunk. Look for: an `Operation-Name` header, an `operation`/`name` field in the response body matching `projects/.../operations/...`, a `Location:` header pointing to a poll endpoint.
2. **`agent_engines` SDK surface.** `dir(remote_app)` and `dir(remote_app.async_api_client)`. Look for `*_long_running`, `*_async_lro`, `start_invocation`, `get_operation`, `cancel_operation`-style methods on the deployed reasoning engine handle.
3. **`projects.locations.operations.list`** filtered by the reasoning engine resource name during an in-flight run. Does an operation appear?

If 2a surfaces nothing, **Test 2 fails immediately** — no point running 2b. Record headers seen, SDK methods listed, list-operations response. Migration depends on Test 1.

If 2a surfaces a candidate primitive, proceed to 2b.

**Phase 2b — end-to-end verification (load-bearing):** API shape alone is not pass. The primitive must complete a real probe run without a live caller.

1. Invoke a fresh probe run (`se-test2`) through the discovered primitive (e.g., the LRO endpoint, or the SDK background method).
2. Capture the operation/job ID from the response.
3. Detach the caller (kill the harness, close the connection — whatever the primitive's contract calls "detach").
4. From a separate process, poll `operations.get` (or equivalent) every 30s.
5. Wait for the operation to report success.
6. Verify the probe plugin's `after_run_callback` landed in Firestore for `se-test2` with timestamp **at least 60s after** the caller-detach moment (same evidence pattern as Test 1).

**Pass (gate B):** All six steps complete. Operation reports success AND `after_run` lands AND the 60s-post-detach gap is satisfied.

**Fail:** Operation never reports success within 15 min, OR no `after_run` doc, OR `after_run.ts <= caller_detached_at`.

### Test 3 — Plugin callbacks fire under deployed runtime

**Setup:** event-shape probe app deployed (real `LlmAgent` + `echo_tool`). Harness runs to completion, no kill.

**Pass check:** Firestore docs in `probe_runs/{sid}/events/` include:

- 1× `kind=before_run`
- ≥1× `kind=event` (the load-bearing `on_event_callback` firings — these carry `event_author`, `event_id`, `is_final` fields populated from real ADK `Event` objects)
- 1× `kind=after_run`
- Optional: `kind=agent_event` docs (supplementary `after_agent_callback` evidence)

`on_event_callback` is the gating callback. Production `FirestoreProgressPlugin` will iterate real ADK events through it; `after_agent_callback` is not an equivalent substitute because it doesn't carry the full event payload (function calls, function responses, grounding metadata) that production progress mapping requires.

**Fail check:** `on_event_callback` doesn't fire (zero `kind=event` docs), OR `before_run` / `after_run` missing. ADK [#4464](https://github.com/google/adk-python/issues/4464) reproducing under deployed Agent Runtime would block the FirestoreProgressPlugin design entirely.

### Test 3b — Caller-disconnect on a real-tool path (sanity check)

**Why:** The lifecycle gate (Test 1) uses `DeterministicSlowAgent` to remove LLM/tool flakiness. That's right for the gate, but doesn't catch runtime behaviour specific to model and tool event streaming (e.g., does Agent Runtime cancel an in-flight model call differently than an in-flight `asyncio.sleep`?). One short real-tool disconnect run de-risks this.

**Setup:** event-shape probe app (the `LlmAgent` + `echo_tool` from Test 3). Harness creates session `se-real001`, fires `async_stream_query`.

**Action:** Same observe-then-kill pattern as Test 1 — wait for first event, write `caller_killed_at`, kill harness.

**Pass check:** `after_run` doc lands with timestamp > `caller_killed_at + 30s` (shorter gap than Test 1 because the tool path is shorter). Plus all `on_event_callback` writes that the run produces appear in Firestore — proves event streaming continues post-disconnect.

**Fail check:** `after_run` missing, OR event writes stop at the kill moment.

This is supplementary, not a third gate. If Test 1 passes and Test 3b shows different behaviour for the LLM path, that's a finding to document and design around in the migration — not necessarily a migration blocker, but the kind of thing we'd want to know before cutover.

### Test 4 — Plugin metadata propagation via session state (production-intended mechanism)

**Setup:** harness calls `agent_engines.AdkApp(...).create_session(user_id="probe_user", session_id="se-meta001", state={"runId": "r-meta", "attempt": 1, "turnIdx": 0})`. Then `async_stream_query(...)`.

**Pass check:** Firestore docs from `before_run` / `after_run` / `agent_event` callbacks contain:

- `runId="r-meta"`, `attempt=1`, `turnIdx=0` (read from `invocation_context.session.state`)
- `userId="probe_user"` (read from `invocation_context.user_id`)
- `sid="se-meta001"` (read from `invocation_context.session.id`)

All five must be the expected values, not `"missing"`. **No fallback acceptable** — message-text encoding is a different architecture, not the same test. If session-state propagation fails, mark the test as failed and document the fallback as future investigation, but do not pretend the test passed.

**Fail check:** Any field is `"missing"` or wrong. This is a major migration blocker — the FirestoreProgressPlugin needs reliable per-run metadata to attribute writes correctly.

### Test 5 — Custom session ID format

**Action:** Three `create_session()` calls:

- `se-{uuid}` (prefixed) — expect 200
- UUID that happens to start with a letter (e.g. `aaaa-...`) — expect 200
- UUID that starts with a digit (e.g. `1234-...`) — expect 400 (violates `[a-z][a-z0-9-]*[a-z0-9]`)

**Pass:** First two succeed; third 400s. Locks ID-generation to the `se-` prefix.

### Test 6 — Duplicate dispatch behavior

**Action:** Two harnesses fire `async_stream_query` on the same `(user_id, session_id)` 1s apart, both using the lifecycle probe.

**Observe:**

- (a) Agent Runtime rejects the second (ALREADY_EXISTS or similar) → it owns invocation idempotency; we can simplify.
- (b) Both run independently, both fire all callbacks → idempotency must stay in our Firestore (currentRunId / takeover survives the migration).

Either result is informative. Result determines the size of the migration's lifecycle-code reduction.

### Test 7 — Cold start + concurrency (informative, not gating)

**Action — record actual deployed config for each measurement, do not assume defaults:**

Before each measurement, query `gcloud ai reasoning-engines describe {resource}` (or the SDK equivalent) and capture the actual `min_instances`, `container_concurrency`, and container size that Agent Runtime is running with. Per Google's [Optimize and scale](https://docs.cloud.google.com/agent-builder/agent-engine/optimize-runtime) docs the default scenario is `min_instances=1`, but Agent Runtime defaults can change between releases — record what the deployed instance actually has, don't assume.

| Run                             | Actual `min_instances` | Actual `container_concurrency` | Container size     | Idle time before run | First-event latency (ms) |
| ------------------------------- | ---------------------- | ------------------------------ | ------------------ | -------------------- | ------------------------ |
| Cold (deployed default)         | _query and record_     | _query and record_             | _query and record_ | 15 min               | _measured_               |
| Warm (deployed default)         | _query and record_     | _query and record_             | _query and record_ | <30s                 | _measured_               |
| Cold (forced `min_instances=1`) | 1                      | _query and record_             | _query and record_ | 15 min               | _measured_               |
| Concurrent ×5                   | _query and record_     | _query and record_             | _query and record_ | warm                 | _per-run measured_       |

Record raw milliseconds. Output is a config-tagged table that informs whether explicit warming is needed for production. No fixed pass/fail thresholds. The "configured `min_instances=1`" row exists to compare against the deployed default — if the default is already 1, the two cold rows will agree.

---

## 5. Probe report shape

`docs/gear-probe-results-{date}.md`. One section per test. Each section is ≤ 200 words and contains:

- **Result:** Pass / Fail / Inconclusive
- **Evidence:** Firestore doc paths, log excerpts, curl output. Inline, not appendix.
- **Conclusion:** one sentence.

Final section: **Decision** — single paragraph stating "migration approved" or "migration rejected" with primary reason.

---

## 6. What the probe will NOT test

To keep the probe honest about its own scope:

- **End-to-end with real specialists.** Probe uses `DeterministicSlowAgent` for the lifecycle gate and a small `LlmAgent + echo_tool` for callback-shape verification (Test 3) and real-tool disconnect (Test 3b). We are not testing whether our actual production specialists (8 parallel agents, web grounding, TripAdvisor/Places tools, gap researcher, synthesizer with chart fences) work on Agent Runtime. That's migration-time work, not probe-time work. Residual risk: "specialists work locally and on our Cloud Run worker but break on Agent Runtime." This risk is low because specialists only depend on Vertex Gemini + our Python tools, not on the runtime host — but it is non-zero and would be caught during migration cutover, not by the probe.
- **Cost at scale.** Probe is one-off. Cost analysis happens during migration if probe passes.
- **Memory Bank integration.** User has deferred Memory Bank pending user accounts. Out of scope.
- **Agent Observability features.** Nice-to-have, not load-bearing.
- **Custom container deployment path.** Probe uses managed packaging via `agent_engines.create(requirements=...)`. Custom container becomes relevant during full migration if we hit a packaging issue with the real agent's tools.

---

## 7. Time and risk

**Time:** 1 working day end-to-end. Breakdown: 2h to write probe agent + plugin + harness; 1h to deploy and run baseline; 2h to run tests 1–7; 1h to write probe report; 2h buffer for cleanup, IAM debugging, and unexpected platform behavior.

**Risk:** very low. Probe is isolated (separate Agent Runtime resource, separate Firestore collection). No production code touched. Worst case: we deploy a probe agent that fails to start; we delete it; we learn nothing. Cost is bounded — single-digit dollars of Vertex compute.

**Failure mode of the probe itself:** the harness cannot deploy because the local Python venv is missing a dep, or IAM rejects, or `agent_engines.create()` hangs (the [March 2026 Poetry venv bug](https://github.com/google/adk-python/issues/4762) was reportedly fixed in the new base image but worth watching). Document any blockers and treat them as setup-time pain, not as probe failures.

---

## 8. Decision contract

The gate is **(Test 1 PASS) OR (Test 2 PASS)**. Either path proves Agent Runtime can complete a chat-turn run durably without a live caller — which is the real underlying question. Tests 3 and 4 must also pass for the migration to proceed (without working plugin callbacks and metadata propagation, the FirestoreProgressPlugin can't be built).

Once the probe completes:

- **Gate = Pass (T1 ∨ T2 succeed, AND T3, T4 succeed):** Rewrite the migration proposal. New version reflects probe results, fixes the P2 stale-against-main errors flagged in earlier review (`agentCheck` is gone, six indexes not four, `chat-recovery.ts` deleted), replaces the unverified fire-and-forget claim with the verified durability mechanism, pins migration to the exact ADK + `agent_engines` versions used in the probe. Execute migration as a single binary cutover. Probe IS the validation phase — no production parallel rollout.
- **Gate = Fail (T1 ∧ T2 both fail, OR T3 fails, OR T4 fails):** Archive the migration proposal under `docs/archived/`. Mark transport work closed for this quarter. Re-evaluation trigger is documented externally: Google ships an LRO query API or documented background-mode for ADK invocations on Agent Runtime. No exploratory work until then.

No third option. No "let's try a thin worker for a few weeks." No long-term hybrid. The probe's value is precisely that it makes the binary call possible.

---

## 9. References

- [`docs/gear-migration-proposal-2026-04-25.md`](./gear-migration-proposal-2026-04-25.md) — proposal to be ratified or archived based on probe outcome
- [Reviewer findings (this thread)](#) — including reviewer's strong-form recommendation to make this binary
- [Method: reasoningEngines.streamQuery — REST reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.reasoningEngines/streamQuery)
- [Vertex AI long-running operations pattern](https://docs.cloud.google.com/vertex-ai/docs/general/long-running-operations)
- [ADK Plugins reference](https://google.github.io/adk-docs/plugins/)
- [ADK plugin lifecycle bug — adk-python#4464](https://github.com/google/adk-python/issues/4464)
- [How to Run Gemini 3 on Agent Engine — Koichi](https://dev.to/koichi73/how-to-run-gemini-3-on-agent-engine-with-adk-4caj)
