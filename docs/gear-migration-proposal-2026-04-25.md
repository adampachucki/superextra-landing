# Migrating to Gemini Enterprise Agent Platform

> **[SUPERSEDED 2026-04-26]** This is the original proposal written before the kill-or-commit probe ran. Several claims in this document were proven wrong or under-specified by the probes — most notably the "fire-and-forget" dispatch story, the custom-session-ID claim, sub-1-min provisioning, and the ~1,000-LOC reduction estimate. **Read [`gear-migration-proposal-2026-04-26-v2.md`](./gear-migration-proposal-2026-04-26-v2.md) for the corrected plan.** This document is kept verbatim for the audit trail of how the original wrong assumptions were reached.

**Status:** Proposal for committee review
**Author:** Architecture working session, 2026-04-25
**Decision sought:** Whether to migrate the Superextra agent runtime from a self-hosted Cloud Run + Cloud Tasks transport onto Google's managed **Gemini Enterprise Agent Platform Runtime** (formerly Vertex AI Agent Engine).
**Recommendation, in one line:** Moderate-to-strong yes — execute a 5–7 day migration in parallel with current production, then cut over.

---

## 0. TL;DR for the committee

We currently run a 7–15 minute multi-agent research pipeline behind a chat UI. To make that pipeline survive long browser absences (mobile backgrounding, tab refresh, network roaming), we built a custom transport layer: Cloud Tasks → private Cloud Run worker → Firestore progress stream → watchdog. That layer exists in three large files totalling roughly **2,243 lines of plumbing** (`agent/worker_main.py`, `functions/index.js`, `functions/watchdog.js`) which we have rewritten three times in the last twelve months.

In April 2026, at Cloud Next, Google rebranded **Vertex AI Agent Builder** to **Gemini Enterprise Agent Platform** and shipped four runtime improvements that directly address the constraints we used to justify _not_ being on the platform six weeks ago: long-running operations up to 7 days, sub-second cold starts, custom container support, and user-supplied session IDs. The platform's trajectory is toward exactly our workload shape.

If we migrate, we expect to **delete approximately 1,000 lines of runtime plumbing** (heartbeat, takeover, ownership fencing, signal handling, FastAPI scaffolding) while moving another ~300 lines into an ADK plugin. The Cloud Function proxy, the Firestore-based progress UI, the watchdog, the chat-state machine, and the capability-URL session sharing all survive the move — they are inherent to the long-running-pipeline UX, not to where the agent itself runs.

**What this migration will fix:** ownership of a runtime we should not own; ongoing maintenance of a custom dispatch/heartbeat/fence machinery; risk of falling behind ADK upgrades. **What this migration will not fix:** the inherent complexity of keeping a 15-minute server-side pipeline visible to a browser that may close, sleep, or change device. That complexity is paid once regardless of runtime.

---

## 1. Product context

The reviewing committee may not need this section — skip if you already know what Superextra does.

Superextra is a market intelligence service for restaurants. The core product surface is a chat agent at `agent.superextra.ai` that, given a restaurant, runs a multi-stage research pipeline: pulls Google Places data, plans an investigation, dispatches 3–8 parallel specialist agents (market, menu, revenue, guest intelligence, location, operations, marketing, reviews), runs a gap-researcher to catch contradictions, and finally synthesises a report with charts.

Two facts shape every architectural decision below:

1. **Pipeline duration.** Narrow queries take 2–4 minutes; deep ones take 7–15 minutes. This is multiples longer than typical chat products (10–30 seconds) and longer than every common HTTP request timeout in our stack.
2. **Promise of continuity.** The product memo (`/memo`) commits to _"we keep the intelligence current"_ — a long-lived agent per restaurant, not a single-shot Q&A. Users are expected to come back. Mobile is a first-class surface.

Together, these mean the system must keep running when the browser disappears and reconnect cleanly when it returns — even on a different device, hours later.

---

## 2. The current architecture

The full design lives in `docs/pipeline-decoupling-plan.md`. The committee-friendly summary is below.

```
Browser
  │  POST /agentStream  (Firebase auth, place context, query text)
  ▼
agentStream  (Firebase Cloud Function v2, Node 22)
  │   ├─ verify Firebase ID token
  │   ├─ Firestore txn: upsert session doc, stamp currentRunId
  │   ├─ rate limit (per-IP, per-UID)
  │   └─ enqueue Cloud Task with OIDC token, dispatchDeadline 1800s
  ▼
Cloud Tasks queue agent-dispatch
  │   guarantees retry + 24h dedup + signed delivery
  ▼
superextra-worker  (private Cloud Run, Python, FastAPI, ADK in-process)
  │   ├─ takeover transaction (fenced ownership of this run)
  │   ├─ heartbeat task writes lastHeartbeat every 30s
  │   ├─ ADK Runner with VertexAiSessionService(agent_engine_id=...)
  │   ├─ event loop maps each ADK event → Firestore event doc
  │   └─ terminal write: status=complete or status=error, fenced
  ▼
Firestore  sessions/{sid} + sessions/{sid}/turns/{nnnn} + sessions/{sid}/events/{eid}
  ▲
  │  onSnapshot listeners (4 of them, see chat-state.svelte.ts)
  │
Browser  shows live progress, survives reload/device-switch via capability URL
```

There is also a **watchdog** Cloud Function (`functions/watchdog.js`, 223 lines) that runs every 2 minutes and fails any session whose `lastHeartbeat` or `lastEventAt` has gone stale.

The notable thing about this architecture is what it _does not do_: it does not stream from the worker to the browser. The browser ↔ worker channel is broken into two halves connected through Firestore: the worker writes events, the browser reads them via `onSnapshot`. This was a deliberate design choice — it makes mobile backgrounding and tab refresh into "the listener happens to be detached for a while" rather than "the pipeline died."

### 2.1 Where the line counts live

Measured by `wc -l` at `8fcdb17`:

| File                                         | Lines | Role                                                                                  |
| -------------------------------------------- | ----: | ------------------------------------------------------------------------------------- |
| `agent/worker_main.py`                       | 1,371 | FastAPI handler, takeover, heartbeat, ADK Runner loop, fenced writes, signal handling |
| `agent/superextra_agent/firestore_events.py` |   449 | Map ADK events → Firestore doc shape for the UI                                       |
| `functions/index.js`                         |   572 | `agentStream` (enqueue) + `agentCheck` (REST fallback) + Firebase auth                |
| `functions/watchdog.js`                      |   223 | Stuck-session sweeper                                                                 |
| `src/lib/chat-state.svelte.ts`               |   697 | Four Firestore listeners + UI state machine                                           |
| `src/lib/firebase.ts`                        |   131 | Firestore client, anon auth, capability URLs                                          |

Total transport plumbing: **3,443 lines**. The agent code itself (`agent/superextra_agent/agent.py` + `specialists.py`) is only 600 lines. We have spent 5.7× more code on transport than on the actual agents.

### 2.2 Where the time has gone — three transport rewrites

This is the part that motivates the proposal. From `git log`:

**Rewrite 1 — Original `adk deploy cloud_run` + Cloud Function SSE streaming** (mid-to-late 2025).
The browser opened an SSE stream to a Cloud Function, which proxied to ADK's `/run_sse` endpoint. Browser drop = pipeline drop. Mobile Safari kills SSE on background within ~30 s. Symptoms produced commits like `a893744 Auto-retry SSE stream on instant connection close`, `2fa5b1a Document Cloud Functions SSE streaming gotchas`, `a263330 Bypass GFE proxy for SSE streaming`, `5beef70 Fix chat recovery when Safari kills SSE connections on background`, `09915a9 Fix session reliability: client recovery race conditions + server pipeline resilience`. About 10 dedicated fix commits.

**Rewrite 2 — Pipeline decoupling: Cloud Tasks + private Cloud Run worker + Firestore stream + watchdog** (March/April 2026, commit `a687004`).
The plan went through nine validation spikes (A–I) and a parallel-validator review pass before implementation. Five follow-up "P1–P5" PRs corrected issues found post-deploy: missing terminal events, recovery race, follow-up agent terminal mapping, missing Firestore composite index hotfix.

**Rewrite 3 — Server-stored sessions with capability-URL access** (April 2026, commit `5f810d5`).
Reshaped the Firestore data model. Replaced client-side conversation storage with a participant-array model so a session can be opened on any device that has the capability URL.

The pattern is consistent: each rewrite solved one class of problem and introduced the next. The reason isn't poor planning — each plan was carefully reviewed and validated. The reason is that **building a robust long-running-agent-in-a-browser transport from primitives is genuinely hard**, and we are spending agent-team cycles on plumbing that has nothing to do with agent quality. Every rewrite was followed by a wave of "stage-N+1, stage-N+2" review passes, post-implementation audits, and bugfix PRs. The agent capability work — better specialists, better data sources, better synthesis — has shared mind-share with this for the entire year.

---

## 3. What changed in April 2026

At Google Cloud Next 2026 (held April 8–10, 2026 in Las Vegas), Google announced a comprehensive rebrand and expansion of Vertex AI as the **Gemini Enterprise Agent Platform**. The rebrand is more than naming — it consolidates and meaningfully extends the agent infrastructure. The components most relevant to us are:

- **Agent Runtime** (formerly Agent Engine) — managed serverless runtime for agents. This is what we'd be moving execution to.
- **Agent Platform Sessions** (formerly Agent Engine Sessions) — managed conversation state. _We already use this product._
- **Agent Platform Memory Bank** — managed long-term memory across sessions. _We are not using this yet, and the user has explicitly deferred adoption until we have user accounts._
- **Agent Identity, Agent Registry, Agent Gateway, Agent Observability** — governance plumbing for enterprise rollouts. Not load-bearing for design-partner stage.

The April 2026 release notes ([Gemini Enterprise Agent Platform release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes)) include four capability changes that directly address constraints we hit during our 2025/early-2026 spike work:

| New capability                           | Constraint it removes                                                                                                                                          |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Long-running operations up to **7 days** | Our pipelines run 7–15 min — was always at risk against typical request timeouts. 7 days is a different category.                                              |
| **Sub-second cold starts**               | Was previously ~4.7 s cold, requiring `min_instances=1` to avoid UX regression. Now mitigated.                                                                 |
| **Custom container deployment**          | We can lift our existing `agent/Dockerfile` rather than re-package for whatever the runtime's default packaging would have been. Big migration risk reduction. |
| **User-specified session IDs**           | Spike A from our March validation flagged "VertexAiSessionService doesn't accept user-provided IDs" as an irritation. Resolved.                                |

In addition, the runtime now also exposes Agent Observability in preview (replaces some of our custom structured logging) and provisioning under one minute (was 30–60 minutes on the prior base image, per the open ADK GitHub issue [#4762](https://github.com/google/adk-python/issues/4762)).

The honest read on platform direction: Google is investing heavily in making Agent Runtime suitable for long-running, multi-agent, persistent-state workloads. Six weeks ago this class of workload was a second-class citizen and we routed around the platform. Six weeks ago is also when we did the validation spikes that justified building our own Cloud Run worker. **Three of the four spike findings that justified self-hosting have been fixed in the last 30 days.**

---

## 4. How Gemini Enterprise Agent Platform works (technical primer)

Sources for this section are linked at the bottom of the document; key references are the official ADK deployment docs and the Agent Runtime overview page.

### 4.1 The two deployment paths

Agent Runtime accepts ADK agents in two ways:

1. **Managed packaging** — you call `agent_engines.create(agent_engine=root_agent, requirements=[...], env_vars={...})` from Python. Google packages your code into a container, deploys it, and gives you back a `ReasoningEngine` resource with a stable resource name. This is the path most documentation shows. It is the simpler path and is appropriate when you do not need filesystem access, a custom Dockerfile, or a custom HTTP framework.
2. **Custom container** — new in April 2026. You bring your own Dockerfile and image; Agent Runtime hosts it. This is the path that matters for us, because it lets us reuse `agent/Dockerfile` essentially as-is.

### 4.2 The runtime contract — what your code must implement

A deployed ADK agent on Agent Runtime exposes a small set of methods:

- `create_session(user_id, session_id?)` — managed by `VertexAiSessionService`; we already use this.
- `stream_query(user_id, session_id, message)` — invokes the agent and streams events back as they fire. Synchronous and async variants. This replaces our Cloud-Tasks→worker dispatch.
- `query` — non-streaming variant.

The agent code itself (the `LlmAgent` / `SequentialAgent` / `ParallelAgent` graph in `agent/superextra_agent/agent.py`) does not change at all. The contract is the same — Agent Runtime just hosts the same `Runner` we already construct in `worker_main.py:178`.

### 4.3 The plugin model — how progress events would flow

ADK's plugin system is the load-bearing piece for the migration. A plugin is a class extending `BasePlugin` registered once on the `Runner`; its callbacks fire globally for every agent, tool, and LLM call. We already use this pattern: `agent/superextra_agent/chat_logger.py` defines `ChatLoggerPlugin` and writes JSONL logs.

Documented callback hooks ([ADK Plugins reference](https://google.github.io/adk-docs/plugins/)):

- `before_run_callback` / `after_run_callback`
- `before_agent_callback` / `after_agent_callback`
- `before_model_callback` / `after_model_callback` / `on_model_error_callback`
- `before_tool_callback` / `after_tool_callback` / `on_tool_error_callback`
- `on_event_callback` — fires for every event before it streams to the client
- `on_user_message_callback`

**For our migration, the key hook is `on_event_callback`.** Today, `agent/worker_main.py` has an event loop iterating `runner.run_async(...)` and calling `firestore_events.map_event` + `write_event_doc` per event (`firestore_events.py:124, 98`). After migration, that exact logic moves into `on_event_callback` of a new `FirestoreProgressPlugin` registered on the `App`. The plugin reads `sid`, `runId`, and `attempt` from the `CallbackContext` (which carries session state); writes are unchanged.

The two known plugin gotchas to watch:

- ADK GitHub [#4464](https://github.com/google/adk-python/issues/4464): plugin lifecycle callbacks not invoked under `InMemoryRunner` in some versions. Mitigation: we use `Runner(app=app, ...)`, not `InMemoryRunner`. Verified in our existing setup (the `ChatLoggerPlugin` works in production). Will re-verify under Agent Runtime in Phase A.
- Some streaming consumers of `stream_query` see empty event sequences on deployed Agent Runtime (ADK GitHub [#1830](https://github.com/google/adk-python/issues/1830)). **This bug class does not affect us** because we do not consume the stream from the client — progress flows through Firestore from inside the agent.

### 4.4 How the browser reaches the agent

Agent Runtime does **not** expose a public CORS-friendly endpoint suitable for direct browser calls. Per Google's authentication guidance ([Authenticate to Agent Platform](https://docs.cloud.google.com/vertex-ai/docs/authentication)), all REST calls require a service-account-signed bearer token, and the canonical pattern for client-side use is a backend proxy. This is the same conclusion any team building a branded chat UI on Vertex reaches.

In practice this means our Firebase Cloud Function `agentStream` survives the migration. Its job changes: instead of _enqueueing a Cloud Task_, it makes a server-side `async_stream_query` call against the deployed Agent Runtime resource. Firebase auth, rate limiting, and session-doc upsert remain. The fire-and-forget pattern is preserved by not awaiting the stream — we kick the call off, return to the browser, and rely on the FirestoreProgressPlugin to land progress as the agent runs.

### 4.5 Pricing model

Agent Runtime is billed like Cloud Run: per vCPU-hour and per GiB-hour during request processing. There is a free tier ([Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)). Today our worker runs on Cloud Run with a similar billing shape — we do not expect a step-change in compute cost. We _do_ gain the option to keep `min_instances=1` warm cheaply if cold-start matters, which the new sub-second cold-start announcement may make unnecessary.

---

## 5. Mapping our pain points to GEAR capabilities

This is the most important table in the document.

| Pain point (ours)                                                                         | GEAR capability that addresses it                                                             | Confidence                                                                   |
| ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| 1,371-line custom worker maintaining ADK Runner, takeover, heartbeat, FastAPI scaffolding | Agent Runtime hosts ADK natively; managed lifecycle, managed scaling                          | **High** — explicit product claim, GA                                        |
| Cold-start regression on idle traffic                                                     | Sub-second cold starts (April 2026)                                                           | **Medium-High** — announced, needs verification under our load               |
| 7–15 minute pipeline vs typical request timeouts                                          | Long-running operations up to 7 days (April 2026)                                             | **High** — explicit release-notes claim                                      |
| User-supplied session IDs needed for capability-URL UX (we worked around this)            | User-specified session IDs (April 2026)                                                       | **High** — explicit release-notes claim                                      |
| Custom Dockerfile already tuned for our deps                                              | Custom container deployment (April 2026)                                                      | **High** — explicit release-notes claim                                      |
| Following ADK upgrades (we own the runner construction)                                   | Agent Runtime tracks ADK; lifts our maintenance burden                                        | **High** — direct consequence of managed runtime                             |
| Cloud Tasks dispatch + dedup + retry                                                      | Replaced by Agent Runtime invocation + watchdog re-enqueue                                    | **Medium** — needs explicit retry pattern design                             |
| Firestore-based progress stream                                                           | Unchanged — driven by FirestoreProgressPlugin from inside agent                               | **High** — same pattern as today, just relocated                             |
| Browser ↔ pipeline state sync (mobile background, tab refresh, multi-device)              | **Not addressed.** Inherent to long-running UX, paid once regardless of runtime               | **High** — confirmed by industry pattern (no managed product solves this)    |
| Watchdog for stuck sessions                                                               | Still needed; sessions can fail (network, OOM, model error). Possibly simpler retry semantics | **Medium** — depends on Agent Runtime failure modes we have not yet measured |

### What this table means in plain language

Of the things we are unhappy with, **most are addressed** by Agent Runtime — directly, as documented features. The exception is browser ↔ pipeline coordination, which is the source of the chat-state machine, the recovery code, the multiple Firestore listeners, and the capability-URL system. Agent Runtime does not solve that and no commercial product does. ChatGPT, Claude, and Perplexity all have similar code under their hoods; their typical response is 10–30 seconds, ours is 7–15 minutes, so we feel the cost more.

---

## 6. What gets removed, what moves, what stays

Counted against current `HEAD` at commit `8fcdb17`.

### 6.1 Removed (~1,000 lines)

- **`agent/worker_main.py`** — most of it. Specifically:
  - FastAPI app + lifespan management
  - Structured logging setup (Agent Runtime logs to Cloud Logging by default)
  - Cloud Tasks request validation (no more Cloud Tasks)
  - Atomic takeover transaction in Firestore (Agent Runtime owns concurrency)
  - Stale-run guard / ownership fencing (Agent Runtime owns invocation lifecycle)
  - Heartbeat asyncio task (Agent Runtime knows if its own runtime is alive)
  - ADK `Runner` construction (Agent Runtime constructs it for us)
  - Event loop processing ADK events (replaced by `on_event_callback` in plugin)
  - Signal handler for SIGTERM (Agent Runtime owns container lifecycle)
- **`agent/Dockerfile`** as currently used for Cloud Run deploy — only if we go the managed-packaging path. If we use custom container, this stays as-is.
- **`functions/index.js`** — the `enqueueRunTask` helper, Cloud Tasks client setup, dispatch-deadline logic. Roughly 50–80 lines.
- **`.github/workflows/deploy.yml`** — the `deploy-worker` job that runs `gcloud run deploy superextra-worker --source=agent`. Replaced by `agent_engines.create(...)` or `agent_engines.update(...)`.
- **Cloud Tasks queue `agent-dispatch`** infrastructure resource.
- **Cloud Run service `superextra-worker`** infrastructure resource.

### 6.2 Moved (~300 lines)

- **`agent/superextra_agent/firestore_events.py`** — the event mapping logic stays line-for-line; what changes is the _caller_. Today it is called from the worker's event loop. After migration, it is called from `FirestoreProgressPlugin.on_event_callback`. This is a clean relocation.
- **Worker-side title generation** (`worker_main.py` uses `_genai_client` to title sessions on first turn). Moves into a plugin or the agent itself.

### 6.3 Stays exactly as-is

- **`functions/index.js` agentStream** — Firebase auth, rate limiting, Firestore session doc upsert. Only the dispatch line changes (Cloud Tasks → Agent Runtime call).
- **`functions/index.js` agentCheck** — REST fallback for the browser. Unchanged.
- **`functions/watchdog.js`** — still need a stuck-session sweeper. The thresholds it watches (heartbeat, lastEventAt) are still produced — by the FirestoreProgressPlugin instead of the worker.
- **`src/lib/chat-state.svelte.ts`** (697 lines) — four Firestore listeners, capability-URL routing, multi-turn state machine. Untouched.
- **`src/lib/firebase.ts`** — anon auth, Firestore client, capability URL generation. Untouched.
- **All four Firestore composite indexes** declared in `firestore.indexes.json`. The data shape does not change.
- **Capability-URL session sharing model** — purely a frontend/Firestore-rules concern.
- **Cross-device continuity** — same pattern, same Firestore reads.

### 6.4 Net code change

- Removed: ~1,000 lines (most of `worker_main.py`).
- Added: ~150 lines (a `FirestoreProgressPlugin` and adapter glue in `agentStream`).
- Net reduction: **~850 lines**, all of it the gnarliest, most-rewritten parts of the codebase.

---

## 7. Migration plan (5–7 days, parallel rollout)

This is a phased plan. Phases A–C are reversible local work; Phase D is the parallel deploy; Phase E is the cutover.

### Phase A — Validation spike (1 day)

**Goal:** prove Agent Runtime works for our specific shape before changing any production code.

Steps:

1. In a staging GCP project (or a separate region in `superextra-site`), call `agent_engines.create(agent_engine=adk_app, requirements=requirements.txt-equivalent, env_vars={GOOGLE_CLOUD_LOCATION: global, ...})`. Capture the resource name.
2. Use the existing `ChatLoggerPlugin` to verify plugin lifecycle callbacks fire under Agent Runtime (mitigates [#4464](https://github.com/google/adk-python/issues/4464)).
3. Run one end-to-end query — a real "deep" query like the validation set in `agent/tests/fixtures/phase0_queries.json`. Confirm the agent runs to completion and `stream_query` yields events including the synthesizer's final report.
4. Measure cold start latency on the first call after idle, and warm latency on a follow-up. Compare against announced sub-second figure.
5. Verify the existing `VertexAiSessionService(agent_engine_id=...)` still works. We are already on this for sessions — should be transparent — but worth confirming the deployed Agent Runtime resource ID equals the existing Sessions backend ID, or if not, what migration is required.

**Exit criteria:** one full deep query runs end-to-end on Agent Runtime; plugin callbacks confirmed firing; latency measured.

**Risk if it fails:** low — this is a local spike. We discover a blocker before any production change.

### Phase B — FirestoreProgressPlugin (1 day)

**Goal:** move the worker's event-mapping logic into an ADK plugin so progress writes happen from inside the agent rather than from a wrapper.

Steps:

1. New file `agent/superextra_agent/firestore_progress.py`. Define `FirestoreProgressPlugin(BasePlugin)`. Constructor takes a Firestore client + sid/runId/attempt provided via `CallbackContext.state` at run start.
2. Implement `on_event_callback(self, *, callback_context, event)`: reuse `map_event(event, state)` and `write_event_doc(...)` from `firestore_events.py` unchanged.
3. Implement `before_run_callback`: write `lastHeartbeat` / `lastEventAt` to satisfy the watchdog.
4. Implement `after_run_callback`: write the terminal state (status=complete or status=error, final reply, sources).
5. Register the plugin on the `App` in `agent/superextra_agent/agent.py`.
6. Local test: run the agent via ADK Web with the plugin registered, confirm the same Firestore docs land that `worker_main.py` produces today.

**Exit criteria:** local ADK runs produce identical Firestore output to the production worker.

**Risk:** medium — the existing `firestore_events.py` is well-tested; the change is wiring not logic. The risk is plugin lifecycle quirks (e.g., a callback that fires twice or not at all under specific event shapes).

### Phase C — Adapt agentStream Cloud Function (1 day)

**Goal:** swap the Cloud Tasks dispatch for an Agent Runtime call without changing the browser's contract.

Steps:

1. In `functions/index.js`, replace `enqueueRunTask({runId, body})` with a helper that calls Agent Runtime's `streamQuery` REST endpoint (or the Node SDK equivalent) using the deployed resource name and the worker SA's service-account token.
2. Do not await the stream — kick it off, return to the browser. Progress flows through Firestore via the plugin.
3. Keep the Firestore session doc upsert, rate limiting, Firebase auth, and turn-doc creation exactly as today.
4. Rate-limit dimension change: Cloud Tasks dedup goes away (we no longer have a queue). We replace it with idempotency on the Agent Runtime side — `runId` becomes the session-id-or-suffix passed to `stream_query`, and a duplicate dispatch is detected as "session already running this runId" by the existing Firestore session doc.

**Exit criteria:** browser sends the same payload to `agentStream`; agentStream invokes Agent Runtime; progress lands in Firestore; `chat-state.svelte.ts` requires zero changes.

**Risk:** medium — the rate-limit/dedup story needs to be airtight. Cloud Tasks gave us 24h dedup essentially for free (`functions/index.js:153`). We'd replicate this in Firestore via a transactional check on `currentRunId` before dispatch.

### Phase D — Parallel rollout (1–2 days)

**Goal:** deploy both paths and split traffic so we have a production canary before cutover.

Steps:

1. Add a feature flag `USE_AGENT_RUNTIME` read by `agentStream`. Default false.
2. Deploy. Smoke test: flag on for the developer's UID only. Run a deep query end-to-end in production. Confirm Firestore progress shape matches existing.
3. Roll the flag to 10% of traffic. Watch Cloud Logging, Firestore writes, watchdog activations. Specifically watch for:
   - `stream_query` yielding empty event sequences ([#1830](https://github.com/google/adk-python/issues/1830))
   - Plugin callbacks not firing for some event types ([#4464](https://github.com/google/adk-python/issues/4464))
   - Cold-start regressions exceeding announced sub-second figure
   - Watchdog tripping on lastHeartbeat from the plugin
4. Roll to 50%, then 100% over 5–7 days assuming clean traffic. Hold at any stage if errors appear.

**Exit criteria:** 100% of production traffic flows through Agent Runtime cleanly for at least 48 hours.

**Risk:** medium — this phase is where Agent Runtime quirks specific to our agent shape will surface. Mitigation is the 10%/50%/100% gradient and instant rollback by flipping the flag.

### Phase E — Cutover and deletion (1 day)

**Goal:** remove the old transport.

Steps:

1. Decommission Cloud Run service `superextra-worker`.
2. Decommission Cloud Tasks queue `agent-dispatch`.
3. Delete `agent/worker_main.py` (kept ~70 lines if any of it survives in adapter form, otherwise full deletion).
4. Remove `enqueueRunTask` and Cloud Tasks client from `functions/index.js`.
5. Remove the `deploy-worker` job from `.github/workflows/deploy.yml`. Replace with an `agent_engines.update(...)` step gated on agent code changes.
6. Update `docs/deployment-gotchas.md`. Archive `docs/pipeline-decoupling-plan.md` and `docs/pipeline-decoupling-fixes-plan.md` under `docs/archived/` — they served their purpose.
7. Update `CLAUDE.md` to point future agents at the new architecture.

**Exit criteria:** old code/infra deleted, docs updated, CI green.

**Risk:** low — this is hygiene after the parallel rollout proves the new path.

### Total time

5–7 working days of agent-engineering time. The user has signalled this is acceptable as agent work, not as developer-team work.

---

## 8. Risks and mitigations

| Risk                                                                                                                         | Severity    | Mitigation                                                                                                                                                                                                                                                          |
| ---------------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `stream_query` returns empty events on deployed Agent Runtime ([#1830](https://github.com/google/adk-python/issues/1830))    | Medium      | We do not consume the stream from the client; the FirestoreProgressPlugin writes from inside the agent. Bug class does not bite us. Verify in Phase A.                                                                                                              |
| Plugin lifecycle callbacks not invoked under some Runner configs ([#4464](https://github.com/google/adk-python/issues/4464)) | Medium-High | Verify in Phase A using the same `App`-based runner construction we already use. Our `ChatLoggerPlugin` already works in production.                                                                                                                                |
| Vendor lock-in deepens                                                                                                       | Medium      | Real but bounded — the agent code itself (specialists, instructions, tools) is portable; only the deployment harness becomes Google-specific. Leaving Agent Runtime later means re-implementing what we just deleted, but it's the same code we have working today. |
| Cold-start latency exceeds announced sub-second figure under our load                                                        | Low-Medium  | Phase A measures it. Mitigation: `min_instances=1`.                                                                                                                                                                                                                 |
| Pricing surprises on long-running invocations                                                                                | Low         | Same vCPU+memory model as Cloud Run today. Worth a back-of-envelope estimate during Phase A using one deep query as the unit.                                                                                                                                       |
| Agent Runtime container_concurrency tuning needed for parallel specialists                                                   | Medium      | ADK recommendation is `container_concurrency = 9 × N` for async agents ([Optimize Agent Runtime](https://docs.cloud.google.com/agent-builder/agent-engine/optimize-runtime)). Default may not fit our 3–8 parallel specialists. Tune in Phase A.                    |
| New platform features have settling-in bugs (April 2026 release)                                                             | Medium      | Parallel rollout is the primary mitigation. Roll to 10% first; halt if anything regresses.                                                                                                                                                                          |
| Watchdog semantics shift                                                                                                     | Low         | Watchdog still reads `lastHeartbeat` / `lastEventAt`. The plugin writes both. The only change is who-writes; the read path is unchanged.                                                                                                                            |
| Custom domain / CORS for browser access                                                                                      | None        | Solved already — the Firebase Cloud Function `agentStream` is the public endpoint. Agent Runtime is private behind it.                                                                                                                                              |
| ADK version ceiling under Agent Runtime                                                                                      | Low         | Python 3.9–3.12 cap. Our agent runs on 3.12. Verify on Phase A.                                                                                                                                                                                                     |

The biggest _unknown unknown_ is whether deployed Agent Runtime + our specific multi-agent shape (3–8 parallel specialists, 7–15 min run) will produce some failure mode we have not seen in self-hosted Cloud Run. That is exactly what Phase A and the 10% canary in Phase D are designed to surface.

---

## 9. What this migration will _not_ fix

This section is here so the committee does not approve the migration on a false premise.

The migration **does not remove** any of the following:

- **The chat-state machine** (`src/lib/chat-state.svelte.ts`, 697 lines). Four Firestore listeners, recovery, capability-URL routing, multi-turn state. This is inherent to mobile-resilient long-running-pipeline UX.
- **The watchdog** (`functions/watchdog.js`, 223 lines). Agent runs can still fail; we still need a sweeper.
- **The Firebase Cloud Function proxy** (`functions/index.js`, ~500 lines after removing the Cloud Tasks bits). Agent Runtime has no public CORS-friendly endpoint; we need the proxy.
- **Capability URLs** (Firestore rules + frontend logic). Purely a UX choice we made; unrelated to runtime.

If the committee's primary frustration is "browser-cloud-agent session sync feels too complicated," the honest answer is **most of that complexity is a long-running-pipeline UX tax, not a self-hosting tax**, and migrating to Agent Runtime will not eliminate it. The migration's value is in the runtime layer specifically — not in the UX layer.

---

## 10. Open questions for the committee

These are explicit asks for the committee's judgment.

1. **Tolerance for deeper Google lock-in.** Today the agent could migrate to any Python host with two days' work. Post-migration, leaving Agent Runtime means re-implementing what we just deleted (~1,000 LOC). Acceptable trade-off?

2. **Timing.** The April 2026 release is six weeks old. Some of the new features (custom containers, sub-second cold starts, 7-day LRO) are GA per release notes; some adjacent features (Agent Designer, Agent Observability) are in preview. Are we comfortable being on a settling platform, or do we wait 3 months for it to stabilize and re-evaluate?

3. **Rollout aggressiveness.** Plan above is 10%/50%/100% over 5–7 days post-cutover. The committee may prefer a slower (2 weeks at 10%) or faster (50% on day 1) gradient.

4. **Memory Bank deferral.** The user has explicitly deferred Memory Bank until user accounts exist. The committee should confirm this — Memory Bank is the most product-relevant GEAR feature for our memo's "agent that knows the restaurant" promise, and it is GA. Deferring is reasonable but worth re-affirming.

5. **Parallel infra retention.** Should we keep the Cloud Run worker resource defined but undeployed for 30 days post-cutover as a "break glass" rollback? Cost is near-zero; cognitive cost is small.

---

## 11. Recommendation

**Approve the migration.** Execute Phases A–E over 5–7 working days starting on a date the committee chooses. Plan owner: agent-engineering (the user). Reviewer: at least one independent reader on each plan + post-implementation audit (matches the cadence we used for the prior two transport rewrites).

The reasoning, condensed:

- **The platform has come to us.** Three of four spike findings that originally justified self-hosting were fixed in the last 30 days. Continued investment is highly likely given the strategic posture announced at Cloud Next 2026.
- **The deletable code is the worst code we own.** The 1,000 lines of takeover/heartbeat/fence/signal/lifecycle plumbing in `worker_main.py` are the parts most likely to need future rework, and the parts least connected to product value.
- **The pieces that survive are the right pieces.** The chat-state machine, the Firestore data model, the capability-URL UX, the watchdog — these are decisions we'd make again. Keeping them is signal that we built the right shape; we just hosted it on the wrong layer.
- **The migration is reversible up to Phase E.** The parallel rollout means we can abort cleanly any time before cutover.
- **The opportunity cost of not migrating is ongoing.** Every quarter we don't move, we accumulate more drift between our custom Runner and ADK's Runner, more pinned dependencies, more watchdog edge cases, more "stage-N+5 review" docs. The cost of the migration is bounded; the cost of not migrating is open-ended.

**Honest counterweight:** the migration does not solve the chat-state/recovery complexity, will deepen vendor lock-in, and exposes us to ~1 month of platform settling-in risk. If the committee weights any of these as decisive, "wait until July 2026 and re-evaluate" is a defensible alternative.

---

## 12. References

Primary documentation, all consulted at write-time (2026-04-25):

- [Gemini Enterprise Agent Platform — release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes)
- [Vertex AI Agent Engine overview](https://docs.cloud.google.com/agent-builder/agent-engine/overview)
- [Optimize and scale Agent Runtime](https://docs.cloud.google.com/agent-builder/agent-engine/optimize-runtime)
- [Use an ADK agent with Agent Runtime](https://docs.cloud.google.com/agent-builder/agent-engine/use/adk)
- [Manage sessions with ADK on Agent Engine](https://docs.cloud.google.com/agent-builder/agent-engine/sessions/manage-sessions-adk)
- [Bidirectional streaming on Agent Runtime — 10-min cap is Live API only](https://docs.cloud.google.com/agent-builder/agent-engine/bidirectional-streaming)
- [Agent Runtime quickstart with ADK](https://docs.cloud.google.com/agent-builder/agent-engine/quickstart-adk)
- [ADK Plugins reference](https://google.github.io/adk-docs/plugins/)
- [ADK Callbacks reference](https://google.github.io/adk-docs/callbacks/)
- [ADK Agent Engine deployment guide](https://google.github.io/adk-docs/deploy/agent-engine/)
- [Authenticate to Agent Platform](https://docs.cloud.google.com/vertex-ai/docs/authentication)
- [Vertex AI pricing](https://cloud.google.com/vertex-ai/pricing)

Coverage of Cloud Next 2026 announcements:

- [Google Unveils Gemini Enterprise Agent Platform — AIwire](https://www.hpcwire.com/aiwire/2026/04/23/google-unveils-gemini-enterprise-agent-platform/)
- [The new Gemini Enterprise — Google Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/the-new-gemini-enterprise-one-platform-for-agent-development)

ADK GitHub issues referenced:

- [adk-python#1830 — `stream_query` empty on deployed Agent Engine](https://github.com/google/adk-python/issues/1830)
- [adk-python#4464 — Plugin callbacks not invoked by InMemoryRunner](https://github.com/google/adk-python/issues/4464)
- [adk-python#4762 — Deploy hangs at step 19 (Poetry venv)](https://github.com/google/adk-python/issues/4762)
- [adk-samples#190 — No response returned for streamQuery](https://github.com/google/adk-samples/issues/190)

Internal documents (in this repo):

- `docs/pipeline-decoupling-plan.md` — current architecture rationale
- `docs/pipeline-decoupling-spike-results.md` — March 2026 validation spikes (some findings invalidated by April release)
- `docs/deployment-gotchas.md` — current operational notes
- `docs/server-stored-sessions-plan.md` — capability-URL session model

Internal code anchors (commit `8fcdb17`):

- `agent/worker_main.py:175–178` — current `VertexAiSessionService` + `Runner` construction
- `agent/superextra_agent/firestore_events.py:124, 98` — event mapping that becomes the FirestoreProgressPlugin
- `agent/superextra_agent/chat_logger.py:85` — existing `ChatLoggerPlugin` proves plugin pattern works in our setup
- `functions/index.js:144–167` — `enqueueRunTask` that becomes an Agent Runtime invoke
- `src/lib/chat-state.svelte.ts:1–22` — header comment documenting the four Firestore listeners (unchanged by migration)
