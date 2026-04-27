# Migrating to Gemini Enterprise Agent Platform — v2

> **[SUPERSEDED 2026-04-26]** Reviewer found two unverified P0 mechanics in this v2: per-turn `sessionState` mutability and Cloud Function clean-disconnect handoff. Both were probed in R3 and resolved (`:appendEvent` for state mutation, `reader.cancel()` + `controller.abort()` for clean disconnect). **Read [`gear-migration-proposal-2026-04-26-v3.md`](./gear-migration-proposal-2026-04-26-v3.md) for the corrected and verified plan.** This v2 is kept verbatim for the audit trail of what was assumed before R3.

**Status:** Proposal for committee review (revised after probe validation)
**Date:** 2026-04-26
**Supersedes:** [`gear-migration-proposal-2026-04-25.md`](./gear-migration-proposal-2026-04-25.md) (v1, pre-probe — kept for audit trail)
**Probe artifacts:** [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md) (round 1), [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md) (round 2), [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md) (full execution log)
**Decision sought:** Whether to migrate the Superextra agent runtime from a self-hosted Cloud Run + Cloud Tasks transport onto Google's managed **Gemini Enterprise Agent Platform Runtime** (formerly Vertex AI Agent Engine).
**Recommendation, in one line:** Yes — but with five non-trivial code prerequisites identified by the probes, and an A/B cutover strategy rather than in-place update.

---

## 0. TL;DR for the committee

This v2 reflects what we actually learned by deploying probes to Agent Runtime over April 26, not what release notes claimed. The migration is still approved, but the case has shifted in three meaningful ways since v1.

**What the probes confirmed (the case to migrate is real):**

- Agent Runtime `streamQuery` invocations **survive caller disconnect** (Test 1: 238.8s gap between `kill -9` and terminal write). This is the load-bearing durability property — we don't need a custom worker holding the connection.
- The plugin model works exactly as documented: `before_run`/`on_event`/`after_run` callbacks fire reliably under deployed runtime, with full ADK `Event` payloads (function_call, function_response, grounding metadata).
- Session metadata (runId, attempt, turnIdx, userId) propagates correctly via `session.state` set at `createSession` time.
- Production agent shape (`SequentialAgent[ParallelAgent[…specialists], synth]` with `output_key` chains) deploys and runs correctly.
- Custom session IDs work end-to-end via direct REST (the platform supports them; only the ADK SDK has a stale guard).
- Outbound HTTPS to non-Google APIs (Apify, TripAdvisor) works without VPC config.

**What the probes contradicted (corrections to v1):**

- v1 said "fire and forget" dispatch worked. **Wrong framing.** The actual mechanism is caller-disconnect-survival on the streamQuery request — once the request lands at Agent Runtime, the runtime drives the agent to completion regardless of caller state. v1's call-and-don't-await pattern needs the right HTTP shape (NDJSON parser, not EventSource).
- v1 claimed "user-supplied session IDs landed in April 2026" as a clean SDK win. **Reality:** ADK Python `VertexAiSessionService` has a stale guard rejecting custom IDs; the platform accepts them. We bypass via REST `:createSession?sessionId=…` and gain a _bigger_ simplification than v1 anticipated (delete `adkSessionId` plumbing entirely).
- v1 claimed "<1 minute provisioning" from the release notes. **Wrong:** ~3.5 min consistently for both `create()` and `update()`. CI/CD planning assumes ~4 min.
- v1 estimated ~1,000 LOC deletion. **Reality:** ~700–800 LOC, because takeover/heartbeat/fencing must stay (concurrent invocations on the same session are _not_ serialized by Agent Runtime — Test 6 confirmed our product invariants don't disappear).
- v1 had stale references to `agentCheck`, four indexes, and `chat-recovery.ts` that no longer match `main`. **Fixed below** against `8fcdb17`.

**What the probes added (new prerequisites for the migration plan):**

1. **Lazy-init Gemini subclass** — required for Gemini 3.1 specialists. The current `_make_gemini(force_global=True)` pattern fails at cloudpickle (`TypeError: cannot pickle '_thread.lock'`). ~30 LOC change.
2. **Secret Manager runtime fetch** — `SecretRef` in `env_vars` consistently failed three deploys. Use `secretmanager.SecretManagerServiceClient` inside `set_up()`.
3. **`gcs_dir_name` per deployment** — concurrent deploys clobber the same staging pickle.
4. **NDJSON parser, not EventSource, for the Node-side `agentStream`** — `:streamQuery?alt=sse` returns newline-delimited JSON despite the `?alt=sse` flag.
5. **Two-SA IAM matrix** — runtime `-re` SA needs `datastore.user` + `logging.logWriter` + `secretmanager.secretAccessor`. Deploy SA grants are mostly unnecessary if we skip SecretRef.

**What the probes did not change:** the migration is still approved on the same gate (caller-disconnect-survival proven). It's still a meaningful code-deletion win. The chat-state machine, capability URLs, watchdog, and Firestore-driven progress UI all survive the move.

**Estimated effort revised:** 7–10 working days of agent-engineering time (up from v1's 5–7), accounting for the prerequisite work in §"Code prerequisites" below. A/B cutover instead of in-place update (Test R2.8 inconclusive on whether `update()` kills in-flight runs).

---

## 1. Product context

(Unchanged from v1.)

Superextra is a market intelligence service for restaurants. The core product surface is a chat agent at `agent.superextra.ai` that, given a restaurant, runs a multi-stage research pipeline: pulls Google Places data, plans an investigation, dispatches 3–8 parallel specialist agents (market, menu, revenue, guest intelligence, location, operations, marketing, reviews), runs a gap-researcher to catch contradictions, and finally synthesises a report with charts.

Two facts shape every architectural decision:

1. **Pipeline duration.** Narrow queries take 2–4 minutes; deep ones take 7–15 minutes. This is multiples longer than typical chat products (10–30 seconds) and longer than every common HTTP request timeout in our stack.
2. **Promise of continuity.** The product memo (`/memo`) commits to _"we keep the intelligence current"_ — a long-lived agent per restaurant, not a single-shot Q&A. Users are expected to come back. Mobile is a first-class surface.

Together, these mean the system must keep running when the browser disappears and reconnect cleanly when it returns — even on a different device, hours later.

---

## 2. Current architecture

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

A separate **watchdog** Cloud Function (`functions/watchdog.js`, 223 lines) runs every 2 minutes and fails any session whose `lastHeartbeat` or `lastEventAt` has gone stale.

The architecture deliberately _does not_ stream from worker to browser. Worker writes events to Firestore; browser reads via `onSnapshot`. This makes mobile backgrounding and tab refresh into "the listener happens to detach for a while" rather than "the pipeline died."

### 2.1 Line counts (against `8fcdb17`)

| File                                         | Lines | Role                                                                                                                                                                                    |
| -------------------------------------------- | ----: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `agent/worker_main.py`                       | 1,371 | FastAPI handler, takeover, heartbeat, ADK Runner loop, fenced writes, signal handling                                                                                                   |
| `agent/superextra_agent/firestore_events.py` |   449 | Map ADK events → Firestore doc shape                                                                                                                                                    |
| `functions/index.js`                         |   572 | `agentStream` + `agentDelete` + Firebase auth (note: `agentCheck` has been removed; see `docs/server-stored-sessions-cleanup-plan-2026-04-23.md`)                                       |
| `functions/watchdog.js`                      |   223 | Stuck-session sweeper                                                                                                                                                                   |
| `src/lib/chat-state.svelte.ts`               |   697 | Four Firestore listeners + UI state machine (note: `chat-recovery.ts` has been deleted; the Firestore SDK's persistent cache + auto-listener-resumption cover what it used to mitigate) |
| `firestore.indexes.json`                     |    64 | **Six** composite indexes (not four as v1 claimed)                                                                                                                                      |

Total transport plumbing: ~3,376 lines. Agent code itself (`agent.py` + `specialists.py`) is 600 lines. Transport is 5.6× the agent.

### 2.2 Three transport rewrites in twelve months (motivation, unchanged)

v1 (mid-2025): `adk deploy cloud_run` + Cloud Function SSE. Browser drop = pipeline drop. Dozens of fix commits (Safari background, GFE proxy, iOS workarounds).

v2 (March/April 2026, `a687004`): pipeline decoupling — Cloud Tasks + private worker + Firestore stream + watchdog. Five follow-up "P1–P5" PRs after the main land.

v3 (April 2026, `5f810d5`): server-stored sessions with capability-URL access. Reshaped Firestore data model; `chat-recovery.ts` was deleted in this round (Stage 6 of the migration, per `chat-state.svelte.ts:18`).

The migration to GEAR would be v4. Each prior rewrite was driven by a real failure mode — the work isn't sloppy, the underlying problem is genuinely hard. v4's case is "stop owning a runtime we shouldn't own," not "fix another failure mode."

---

## 3. What changed in April 2026 (corrected against probe findings)

Cloud Next 2026 (April 8–10) rebranded Vertex AI Agent Builder as **Gemini Enterprise Agent Platform** and shipped runtime improvements. Calibrated against probe findings:

| Release-notes claim                    | Probe finding                                                                                                                                                                                                                  | Migration impact                                                                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "Long-running operations up to 7 days" | **Misleading phrasing.** No invocation-level LRO API exists for chat turns. But the underlying durability property is real: Test 1 proved `streamQuery` requests survive caller disconnect for at least 5 min (likely longer). | Functionally equivalent to what we want — caller-disconnect-survival lets us not own the runtime.                                                           |
| "Sub-second cold starts"               | Directionally consistent — ~2s observed first-event latency including LLM thinking, so cold-start overhead ≤1s. Not rigorously measured.                                                                                       | Production should set `min_instances=1` if user-configurable, but Agent Runtime appears to manage this internally; accept directional sub-second behaviour. |
| "Custom container deployment"          | Not exercised in probes; we used managed packaging via `agent_engines.create()` with `extra_packages`.                                                                                                                         | Managed packaging worked; custom container becomes relevant if we hit packaging issues with the real agent's dependencies.                                  |
| "User-specified session IDs"           | **Platform supports it; ADK SDK rejects with stale guard ([adk-python#987](https://github.com/google/adk-python/issues/987)).** Bypass via direct REST `:createSession?sessionId=…`.                                           | We can use `se-{sid}` end-to-end and **delete** the `adkSessionId` mapping plumbing — bigger simplification than v1 anticipated.                            |
| "Provisioning under 1 minute"          | **Wrong.** ~3.5 min observed for both `create()` and `update()`.                                                                                                                                                               | CI/CD planning assumes ~4 min, not <1 min.                                                                                                                  |

Other April 2026 items not directly relevant: Agent Studio (low-code), Agent Garden (templates), Agent Identity / Registry / Gateway (governance), Memory Bank (deferred per user instruction until accounts exist).

---

## 4. How GEAR works (corrected against empirical findings)

### 4.1 Deployment

`agent_engines.create(agent_engine=AdkApp(app=our_app), requirements=[...], extra_packages=[...], gcs_dir_name="...", env_vars={...})` is the entry point. Python 3.9–3.12 supported. Provisioning takes ~3.5 min consistently. Returns a `ReasoningEngine` resource with a stable resource name.

**Probe-discovered gotchas (must land in deploy.yml):**

- **Wrap in `agent_engines.AdkApp(app=our_app)`** — passing our `App` directly to `agent_engines.create()` fails because `AdkApp` is what exposes the `query`/`stream_query`/`async_stream_query` methods Agent Runtime expects.
- **`gcs_dir_name=f"agent_engine_{name}"` per distinct deployment** — without this, parallel deploys overwrite the same `gs://{bucket}/agent_engine/agent_engine.pkl` and serve whoever wrote last.
- **`App.name` must be a Python identifier** (no hyphens). Display name takes hyphens.
- **`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` are reserved** — rejected if passed in `env_vars`.
- **Cloudpickle records the module name where a class is defined.** If you run deploy from `agent/` cwd with `extra_packages=["./probe"]`, the deployed runtime imports as `probe.X`. Use relative imports inside the bundled package.

### 4.2 Invocation contract

Deployed agent exposes:

- `create_session(user_id, session_id?, state?)` — managed by `VertexAiSessionService`. SDK rejects user-provided `session_id` (stale guard). REST `:createSession?sessionId=...` accepts.
- `async_stream_query(user_id, session_id, message)` — fires the agent and streams events. **Survives caller disconnect** (Test 1 verified, 238.8s gap).
- REST `:streamQuery?alt=sse` returns **NDJSON** (newline-delimited JSON), NOT standard SSE `data: ...\n\n` frames despite the flag. Node-side parser must handle bare-JSON-per-line.

### 4.3 Plugin model

`BasePlugin` callbacks fire reliably under deployed runtime (Test 3 verified — ADK [#4464](https://github.com/google/adk-python/issues/4464) does not reproduce on Agent Runtime in `google-adk==1.28.0`):

| Callback                       | Signature                                                  | Use                                                                                                                                          |
| ------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `before_run_callback`          | `(*, invocation_context: InvocationContext)`               | Setup, write session-doc heartbeat                                                                                                           |
| `after_run_callback`           | `(*, invocation_context: InvocationContext)`               | Terminal state, close timeline                                                                                                               |
| `on_event_callback`            | `(*, invocation_context: InvocationContext, event: Event)` | **Load-bearing** — replaces `worker_main.py`'s event loop. Receives full ADK Events with function_call/function_response/grounding payloads. |
| `before_/after_agent_callback` | `(*, agent: BaseAgent, callback_context: CallbackContext)` | Per-sub-agent observability                                                                                                                  |
| `before_/after_tool_callback`  | `(*, tool, tool_args, tool_context: ToolContext, ...)`     | Per-tool intercepts                                                                                                                          |

**Critical defensive pattern:** uncaught exceptions in `on_event_callback` HALT the run. Production `FirestoreProgressPlugin` must wrap external writes in `try/except` (matches today's `worker_main.py:_fenced_update` pattern).

### 4.4 Browser ↔ Agent Runtime path

Agent Runtime has **no public CORS-friendly endpoint**. The Firebase Cloud Function `agentStream` survives the migration as the proxy — only its dispatch line changes (Cloud Tasks → REST `:streamQuery` call against Agent Runtime).

**Probe-discovered Node recipe (verified working):**

```js
const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
const { token } = await (await auth.getClient()).getAccessToken();
const res = await fetch(
	`https://${LOCATION}-aiplatform.googleapis.com/v1/${RESOURCE}:streamQuery?alt=sse`,
	{
		method: 'POST',
		headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
		body: JSON.stringify({
			class_method: 'async_stream_query',
			input: { user_id, session_id, message }
		})
	}
);
// Stream is NDJSON, NOT SSE — parse line-by-line as JSON, no `data: ` prefix.
```

### 4.5 Service accounts

**Two distinct SAs, different roles:**

- `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (note `-re` suffix — "reasoning engine") — **runtime SA**, the one our deployed code runs as. Needs:
  - `roles/datastore.user` (FirestoreProgressPlugin writes)
  - `roles/logging.logWriter` (granted but logs still don't surface — see §5 R2.6)
  - `roles/secretmanager.secretAccessor` (runtime secret fetch)
- `service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com` (no `-re`) — **deploy-time SA**. Default Vertex AI Service Agent. Needed only if using SecretRef in `env_vars` (which we don't recommend per §"Code prerequisites").

### 4.6 Pricing

vCPU-hour + GiB-hour during request processing, like Cloud Run. Free tier exists. Probe runs cost single-digit dollars total; production cost should be in the same ballpark as the current Cloud Run worker.

---

## 5. Probe results — verified migration mapping

Each row is one operational concern from v1, calibrated against probe evidence.

| Concern                                                                     | v1 claim                                 | Probe verdict                                                                                   | Migration impact                                                              |
| --------------------------------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Caller-disconnect survival                                                  | Implied via "fire-and-forget"            | **PROVEN** (Test 1 — 238.8s gap)                                                                | Migration unblocked at the load-bearing gate.                                 |
| Plugin callbacks under deployed runtime                                     | Assumed working from local dev           | **PROVEN** (Test 3 — all callbacks fire)                                                        | FirestoreProgressPlugin design is viable.                                     |
| Metadata propagation via `session.state`                                    | Assumed                                  | **PROVEN** (Test 4 — runId/attempt/turnIdx/userId all readable)                                 | Production-intended mechanism works.                                          |
| Custom session IDs                                                          | Claimed clean SDK win                    | **SDK fail, REST works**                                                                        | Bypass ADK; delete `adkSessionId` plumbing.                                   |
| Production agent shape (`SequentialAgent` + `ParallelAgent` + `output_key`) | Trusted ADK                              | **PROVEN** (Test R2.5)                                                                          | No agent restructuring needed.                                                |
| Multi-turn `session.state`                                                  | Untested                                 | **PROVEN** (Test R2.3)                                                                          | Existing pattern transfers cleanly.                                           |
| Outbound HTTPS to Apify/TripAdvisor                                         | Untested                                 | **PROVEN** (Test R2.1)                                                                          | No VPC config needed (we don't use VPC-SC).                                   |
| Gemini 3.1 routing via `location='global'`                                  | Untested                                 | **Eager Client pattern fails at cloudpickle. Lazy subclass works.**                             | Code prerequisite — see §"Code prerequisites" below.                          |
| SecretRef env vars                                                          | Assumed available                        | **Deploys but runtime fails to start** ([R2.2 fail](./gear-probe-results-round2-2026-04-26.md)) | Use Secret Manager runtime fetch instead.                                     |
| Logs visibility from agent                                                  | Assumed Cloud Logging auto-capture       | **No logs surface in API even with full IAM grant**                                             | Mitigation: Firestore-driven observability (already in use).                  |
| Node-side `:streamQuery`                                                    | Assumed standard SSE                     | **NDJSON, not SSE**                                                                             | agentStream rewrite uses line-by-line JSON parser.                            |
| Concurrent invocations on same session                                      | v1 said Agent Runtime "owns concurrency" | **NOT serialized at API layer** (Test 6)                                                        | Idempotency stays in Firestore — `currentRunId`/takeover/fencing all survive. |
| In-flight `update()` behaviour                                              | Untested                                 | **INCONCLUSIVE** (R2.8 harness bug)                                                             | Cutover: A/B deploy + traffic switch, not in-place.                           |
| No invocation-level LRO API                                                 | v1 read "7-day LRO" as fire-and-forget   | **No such API exists**                                                                          | Watchdog continues polling Firestore liveness, not `operations.get`.          |

**Net:** the gate is satisfied; most concerns either pass cleanly or have a documented workaround. The only true blocker we found (Gemini 3.1 cloudpickle) has a clean fix.

---

## 6. What gets removed, moved, kept (revised line counts)

### 6.1 Removed (~700–800 lines, down from v1's ~1,000)

- **`agent/worker_main.py`** — most of it:
  - FastAPI scaffolding + lifespan management
  - Structured logging setup
  - ADK `Runner` construction and event loop (replaced by `on_event_callback`)
  - Signal handler (Agent Runtime owns container lifecycle)
  - Cloud Tasks request validation
- **`agent/Dockerfile`** as currently used for Cloud Run deploy — only if we use managed packaging. (Custom container deployment available if needed.)
- **`functions/index.js`** — the `enqueueRunTask` helper, Cloud Tasks client setup. ~50–80 lines.
- **The `adkSessionId` field on session docs and the read/write at `worker_main.py:1086-1093`** — round-1 doc-vs-reality finding lets us delete this. Use `se-{sid}` end-to-end.
- **`.github/workflows/deploy.yml` — `deploy-worker` job**. Replaced by `agent_engines.update(...)` step.
- **Cloud Tasks queue `agent-dispatch`** infra resource.
- **Cloud Run service `superextra-worker`** infra resource.

### 6.2 Moved (~300 lines)

- **`agent/superextra_agent/firestore_events.py`** — the event mapping logic stays line-for-line; what changes is the _caller_. Today called from worker's event loop. After migration: called from `FirestoreProgressPlugin.on_event_callback`. **Defensive `try/except` wrappers required around external writes** (round-2 finding).
- **Worker-side title generation** (the `_genai_client` calls). Moves into a plugin or the agent's `set_up()` method.

### 6.3 Stays as-is

- **`functions/index.js` agentStream** — Firebase auth, rate limiting, Firestore session doc upsert. Only the dispatch line changes (Cloud Tasks → `:streamQuery` REST call with NDJSON parser).
- **`functions/index.js` agentDelete** — unchanged. (`agentCheck` was already removed from the codebase pre-migration; v1's reference was stale.)
- **`functions/watchdog.js`** — still need a stuck-session sweeper. Reads `lastHeartbeat`/`lastEventAt` written by the FirestoreProgressPlugin.
- **`src/lib/chat-state.svelte.ts`** (697 lines) — four Firestore listeners, capability-URL routing, multi-turn state. Untouched. (`chat-recovery.ts` was already deleted; the Firestore SDK's persistent cache covers what it mitigated.)
- **`src/lib/firebase.ts`** — anon auth, Firestore client. Untouched.
- **All six Firestore composite indexes** in `firestore.indexes.json` (not four as v1 said).
- **Capability-URL session sharing model** — purely frontend/Firestore-rules.
- **Takeover transaction + ownership fencing** in `worker_main.py:293-364` — must survive the move (Test R2.6 confirmed Agent Runtime does NOT serialize concurrent invocations on the same session). Could relocate from `worker_main.py` into the FirestoreProgressPlugin's `before_run_callback`, or stay in `agentStream` as a pre-dispatch transactional check. Migration plan §7 covers this.

### 6.4 Net code change

- Removed: ~700–800 lines (most of `worker_main.py`, plus `adkSessionId` plumbing).
- Added: ~200 lines (FirestoreProgressPlugin + lazy Gemini subclass + Secret Manager runtime fetch + Node NDJSON parser).
- **Net reduction: ~500–600 lines.** Real, but smaller than v1's ~850 estimate. The migration is still worthwhile but proportionally less of a deletion win than v1 implied.

---

## 7. Migration plan — A/B cutover (revised from v1's parallel rollout)

v1 proposed a 5-phase parallel-rollout plan ending in a single binary cutover. **v2 replaces the "validation phase" with the probe results we already have** — the Phase A spike, Phase B plugin design, and Phase C agentStream adaptation are largely _done_ in throwaway form (`agent/probe/`). What remains is converting the throwaway probe code into production code, the Code prerequisites, the IAM matrix, and the A/B switch.

**Total estimated time: 7–10 working days of agent-engineering time.** Up from v1's 5–7 because of prerequisites.

### Phase 1 — Code prerequisites (2–3 days)

These must land before any production-shape Agent Runtime deploy.

1. **Lazy-init Gemini subclass** in `agent/superextra_agent/specialists.py`. Replace the eager `g.api_client = Client(...)` pattern with a `Gemini` subclass exposing `api_client` as a `@property` that lazy-constructs on first read. Pickle-safe; deploys correctly. Probe verified with `gemini-3.1-pro-preview`. ~30 LOC.

2. **Secret Manager runtime fetch.** Replace any reliance on `SecretRef` env vars (we don't currently use them, but the migration plan would have) with `secretmanager.SecretManagerServiceClient` reads inside the agent's `set_up()` method. Cache values at startup. Migration prerequisite: grant `roles/secretmanager.secretAccessor` to the runtime `-re` SA.

3. **`FirestoreProgressPlugin`** in `agent/superextra_agent/firestore_progress.py`. Subclass `BasePlugin`. Implement `before_run_callback` (write `before_run` doc, set `lastHeartbeat`), `on_event_callback` (call existing `firestore_events.map_event` + `write_event_doc`, update `lastEventAt`), `after_run_callback` (write terminal `after_run` + close timeline). All external writes wrapped in `try/except` so plugin failures don't halt the run. Per-run metadata read via `invocation_context.session.state` (set at `createSession` time).

4. **NDJSON parser** in `functions/index.js`'s `agentStream`. Replace the Cloud-Tasks-enqueue path with a `fetch` to `:streamQuery?alt=sse` using bearer-token auth via `google-auth-library`. Stream parser splits on `\n` and parses each line as JSON (NOT EventSource). The Node call doesn't need to consume events — the plugin writes Firestore directly. `agentStream` returns to the browser immediately after the streamQuery is fired off; the request keeps running server-side until completion.

5. **Custom session IDs via REST.** Replace ADK's `create_session(session_id=...)` (which raises `ValueError` due to stale guard) with a direct `requests.post` to `…/v1beta1/{resource}/sessions?sessionId=se-{sid}`. Use our existing UUID-based sids prefixed with `se-`.

### Phase 2 — IAM matrix (½ day)

Add to `.github/workflows/deploy.yml` or a one-time setup script:

```bash
# Runtime SA — what the deployed agent runs as
gcloud projects add-iam-policy-binding superextra-site \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/datastore.user"
gcloud projects add-iam-policy-binding superextra-site \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
gcloud projects add-iam-policy-binding superextra-site \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Phase 3 — Production deploy + A/B (2–3 days)

1. Deploy production agent (with all Phase 1 prerequisites) to a staging Agent Runtime resource via `agent_engines.create(gcs_dir_name="agent_engine_staging", ...)`. Capture resource name.
2. Add a feature flag `USE_AGENT_RUNTIME` in `agentStream` that routes traffic to either the legacy Cloud Tasks path or the new Agent Runtime resource based on the flag's value.
3. Smoke test: flag on for the developer's UID only. Run a deep query end-to-end. Confirm Firestore progress shape matches existing.
4. Roll the flag to 10% of traffic. Monitor:
   - Firestore plugin docs match expected per-run shape
   - Watchdog activations stay at zero
   - Cold-start latency observed
   - Any new error classes from the plugin's `on_event_callback`
5. Roll to 50%, then 100% over 5–7 days assuming clean traffic. Hold at any stage if errors appear.

### Phase 4 — Cutover (1 day)

After 48h of clean 100% traffic:

1. Promote the staging Agent Runtime resource as production. Keep the legacy worker deployed for 30 days as a "break glass" rollback path.
2. Decommission Cloud Tasks queue `agent-dispatch` and Cloud Run service `superextra-worker` after the 30-day window.
3. Delete `agent/worker_main.py`.
4. Remove `enqueueRunTask` and Cloud Tasks client from `functions/index.js`.
5. Remove the `deploy-worker` job from `.github/workflows/deploy.yml`. Replace with an `agent_engines.update(...)` step gated on agent code changes.
6. Update `docs/deployment-gotchas.md`. Archive `docs/pipeline-decoupling-plan.md` and `docs/pipeline-decoupling-fixes-plan.md` under `docs/archived/`.

### Why A/B and not in-place `update()`

Test R2.8 was inconclusive — the long invocation completed during a planned mid-stream `update()`, but the `update()` call itself failed for harness-config reasons (not agent runtime), so we don't have proof the update wouldn't have killed the run. A/B with a feature flag is reversible at any moment; in-place `update()` is not.

---

## 8. Risks and mitigations

| Risk                                                                                                         | Severity | Mitigation                                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lazy Gemini subclass interacts badly with ADK's internal Client management                                   | Medium   | Probe verified the pattern works for one `LlmAgent` + `gemini-3.1-pro-preview`. Validate with a 2-specialist parallel-agent deploy in Phase 3 smoke.                                                                                                    |
| Production specialists hit a runtime quirk we missed (e.g., grounding metadata shape under deployed runtime) | Medium   | Phase 3 smoke runs the actual production agent shape end-to-end. Discover during smoke, not during 100% rollout.                                                                                                                                        |
| Concurrent dispatch race during A/B traffic split                                                            | Medium   | Feature flag is per-UID; one user can't be split mid-conversation. Plus existing `currentRunId`/takeover transaction protects against duplicate dispatch.                                                                                               |
| `:streamQuery` returns 200 but empty stream (ADK [#1830](https://github.com/google/adk-python/issues/1830))  | Low      | Probe confirmed events arrive correctly when parsed as NDJSON. Bug class is consumer-side parsing, not platform.                                                                                                                                        |
| Cold-start regression on idle traffic                                                                        | Low      | Probe observed sub-second cold start in practice. If production exhibits worse, set `min_instances=1` if available.                                                                                                                                     |
| Pricing surprises                                                                                            | Low      | Same vCPU/GiB-hour model as Cloud Run; back-of-envelope estimate during Phase 3.                                                                                                                                                                        |
| Vendor lock-in deepens                                                                                       | Medium   | Real but bounded — agent code (specialists, instructions, tools) is portable; only the deployment harness becomes Google-specific. Leaving Agent Runtime later means re-implementing the worker, but that worker code lives in this repo's git history. |
| Rollback during A/B                                                                                          | Low      | Feature flag flip is instant. 30-day worker preservation gives us a hard fallback.                                                                                                                                                                      |

---

## 9. What this migration will NOT fix

(Same as v1 — repeating because it shapes committee expectations.)

The migration **does not remove** any of the following:

- **`src/lib/chat-state.svelte.ts`** (697 lines). Four Firestore listeners, recovery, capability-URL routing, multi-turn state. Inherent to mobile-resilient long-running-pipeline UX.
- **`functions/watchdog.js`** (223 lines). Agent runs can still fail; we still need a sweeper.
- **`functions/index.js` agentStream** (~500 lines after removing Cloud Tasks bits). Agent Runtime has no public CORS-friendly endpoint; we need the proxy.
- **Capability URLs and Firestore rules.** Purely UX choices.
- **Takeover transaction + currentRunId/currentAttempt fencing.** Test R2.6 confirmed Agent Runtime does NOT serialize concurrent invocations.

If the committee's primary frustration is "browser-cloud-agent session sync is too complicated," the honest answer is **most of that complexity is a long-running-pipeline UX tax, not a self-hosting tax**, and migration to Agent Runtime will not eliminate it. The migration's value is in the runtime layer specifically.

---

## 10. Open questions for the committee

1. **Tolerance for deeper Google lock-in.** Today the agent could migrate to any Python host with a few days' work. Post-migration, leaving Agent Runtime means re-implementing what we just deleted (~700 LOC). Acceptable trade-off?

2. **Feature-flag rollout aggressiveness.** Plan above is 10%/50%/100% over 5–7 days. Slower (2 weeks at 10%) or faster (50% on day 1) acceptable?

3. **30-day rollback window.** Keep the Cloud Run worker resource defined-but-undeployed for 30 days post-cutover as "break glass" rollback? Cost is near-zero; cognitive cost is low.

4. **Memory Bank deferral confirmation.** Still deferred until user accounts exist (per Adam's explicit instruction). Re-affirm.

---

## 11. Recommendation

**Approve the migration.** Execute Phases 1–4 over 7–10 working days starting on a date the committee chooses.

The reasoning, condensed:

- The probe gate (caller-disconnect-survival) is satisfied with timestamp-precise evidence.
- The deletable code is the worst code we own (heartbeat, takeover, fencing, signal handling, FastAPI scaffolding) — most-likely-to-need-future-rework, least-connected-to-product-value.
- Five non-trivial code prerequisites identified (lazy Gemini, runtime secret fetch, FirestoreProgressPlugin, NDJSON parser, custom-ID-via-REST) are tractable; ~2–3 days of work total.
- A/B cutover with feature flag is reversible at every step until the 30-day worker decommissioning.
- The opportunity cost of NOT migrating is ongoing — every quarter we don't move, we accumulate more drift between our custom Runner and ADK's Runner, more pinned dependencies, more watchdog edge cases.

**Honest counterweight:** the migration does not solve the chat-state/recovery complexity that drove the original frustration; that's UX tax, not self-hosting tax. If the committee weights this differently than v1 framed it, "wait until July 2026 and re-evaluate" remains a defensible alternative.

---

## 12. References

**Probe artifacts (load-bearing):**

- [`docs/gear-probe-plan-2026-04-26.md`](./gear-probe-plan-2026-04-26.md) — round 1 plan
- [`docs/gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md) — round 1 results
- [`docs/gear-probe-plan-round2-2026-04-26.md`](./gear-probe-plan-round2-2026-04-26.md) — round 2 plan
- [`docs/gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md) — round 2 results
- [`docs/gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md) — full execution log with corrections marked
- [`docs/gear-migration-proposal-2026-04-25.md`](./gear-migration-proposal-2026-04-25.md) — v1 (superseded)

**Probe code (kept in repo for reference):**

- `agent/probe/` — all probe agents, plugin, harness, deploy script
- `functions/probe-stream-query.js` — Node-side `:streamQuery` recipe

**Internal architecture docs:**

- `docs/pipeline-decoupling-plan.md` — current architecture rationale
- `docs/server-stored-sessions-cleanup-plan-2026-04-23.md` — `agentCheck` deletion record
- `docs/deployment-gotchas.md` — current operational notes (will be updated post-migration)

**Internal code anchors (commit `8fcdb17`):**

- `agent/worker_main.py:175–178` — current `VertexAiSessionService` + `Runner` construction (becomes obsolete)
- `agent/worker_main.py:1086-1093` — current `adkSessionId` write (deletable)
- `agent/superextra_agent/firestore_events.py:124, 98` — event mapping (becomes plugin internals)
- `agent/superextra_agent/specialists.py:31` — current `_make_gemini` (needs lazy-subclass rewrite)
- `agent/superextra_agent/chat_logger.py:113,134,144` — proven plugin signature reference
- `functions/index.js:144–167` — current `enqueueRunTask` (replaced by streamQuery REST call)
- `src/lib/chat-state.svelte.ts:1–22` — header documenting four-listener architecture (unchanged by migration)

**External references:**

- [Gemini Enterprise Agent Platform release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes)
- [Vertex AI Agent Engine overview](https://docs.cloud.google.com/agent-builder/agent-engine/overview)
- [Logging an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/logging)
- [Authenticate to Agent Platform](https://docs.cloud.google.com/vertex-ai/docs/authentication)
- [Agent Engine networking](https://discuss.google.dev/t/vertex-ai-agent-engine-networking-overview/267934)
- [adk-python#987 — Custom session ID guard](https://github.com/google/adk-python/issues/987)
- [adk-python#3628 — Gemini 3 + Agent Engine bug](https://github.com/google/adk-python/issues/3628)
- [adk-python#1830 — stream_query empty stream class](https://github.com/google/adk-python/issues/1830)
- [adk-python#4464 — plugin callback firing (does NOT reproduce on Agent Runtime)](https://github.com/google/adk-python/issues/4464)
