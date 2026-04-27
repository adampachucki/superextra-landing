# Migrating to Gemini Enterprise Agent Platform — v3

**Status:** Proposal for committee review — final, all gates verified
**Date:** 2026-04-26
**Supersedes:** [`gear-migration-proposal-2026-04-26-v2.md`](./gear-migration-proposal-2026-04-26-v2.md) (v2 — gated on two unverified mechanics, both now resolved by R3)
**Probe artifacts (load-bearing):**

- [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md) — R1 (caller-disconnect survival, plugin model, agent shape)
- [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md) — R2 (Gemini 3.1 routing, env vars, multi-turn, logs, Node SSE)
- [`gear-probe-results-round3-2026-04-26.md`](./gear-probe-results-round3-2026-04-26.md) — R3 (per-turn state mutation, CF clean-disconnect handoff)
- [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md) — full execution log with corrections marked

**Decision sought:** approve migration of the Superextra agent runtime from the self-hosted Cloud Run + Cloud Tasks transport onto **Gemini Enterprise Agent Platform Runtime** (GEAR).
**Recommendation, in one line:** **Approve.** All gates verified empirically across three probe rounds. Five concrete code prerequisites + an A/B cutover, ~7–10 days of agent-engineering work.

---

## 0. TL;DR for the committee

This v3 is the post-R3 version. v2 hung on two unverified mechanics that the reviewer correctly flagged as P0; R3 closed both with timestamp-precise evidence.

**Two new R3 findings that reshape the plan vs. v2:**

1. **Per-turn metadata propagation must use REST `:appendEvent`, not `createSession` state alone.** The platform explicitly rejects `sessions.patch` on `sessionState` and tells you (via the error message) to use `:appendEvent` with `actions.stateDelta`. Verified end-to-end: turn-2 plugin callbacks see the new `runId`/`turnIdx` after `:appendEvent`. Production migration adds one REST call per turn before each `streamQuery`.

2. **Cloud Function handoff with explicit `reader.cancel()` + `controller.abort()` works.** Agent Runtime continued for **240.6s** (twice, repeatable) after a CF read the first NDJSON line, explicitly aborted the request, and returned 202. This is the supported clean-disconnect pattern the migration design requires. **The CF needs `timeoutSeconds: 90`** (vs. production's current 30s) to wait for first-NDJSON-line handoff proof.

**What v3 inherits unchanged from v2:**

- Migration is still approved. v2's gate (caller-disconnect survival) remains satisfied.
- Five code prerequisites (now expanded to seven with R3 findings).
- A/B cutover with `transport: 'cloudrun'|'gear'` field, NOT in-place `update()`.
- ~700 LOC net deletion — heartbeat/takeover/fencing SURVIVE; Cloud Run/FastAPI/Cloud Tasks/in-process Runner are deleted.
- Reviewer P1/P2 corrections from the v2 review all fold in (session-stickiness routing, `adkSessionId` deletion sequencing, plugin-owned heartbeat, write-class taxonomy, dependency adds, narrative fixes).

**Estimated effort:** 7–10 working days of agent-engineering. Same as v2 — the R3 findings change the _what_ of the prerequisites but not their total complexity.

---

## 1. Product context

(Unchanged from v2.)

Superextra is a market intelligence service for restaurants. Core surface is a chat agent that runs a 7–15 min multi-stage research pipeline (Google Places → orchestrator → 3–8 parallel specialists → gap researcher → synthesizer with charts). Two facts shape every architectural decision:

1. **Pipeline duration** — multiples longer than every typical chat product (10–30s) and longer than every common HTTP request timeout in our stack.
2. **Promise of continuity** — the memo commits to "we keep the intelligence current." Long-lived per-restaurant agent. Mobile is first-class.

Together these mean the system must keep running when the browser disappears and reconnect cleanly when it returns — even on a different device, hours later.

---

## 2. Current architecture

(Unchanged from v2.)

```
Browser
  │ POST /agentStream  (Firebase auth, place context, query text)
  ▼
agentStream  (Firebase Cloud Function v2, Node 22, timeoutSeconds: 30)
  ├─ verify Firebase ID token
  ├─ Firestore txn: upsert session doc, stamp currentRunId
  ├─ rate limit (per-IP, per-UID)
  └─ enqueue Cloud Task with OIDC token, dispatchDeadline 1800s
  ▼
Cloud Tasks queue agent-dispatch
  │ retry + 24h dedup + signed delivery
  ▼
superextra-worker  (private Cloud Run, Python, FastAPI, ADK in-process)
  ├─ takeover transaction (fenced ownership of this run)
  ├─ heartbeat task writes lastHeartbeat every 30s
  ├─ ADK Runner with VertexAiSessionService(agent_engine_id=...)
  ├─ event loop maps each ADK event → Firestore event doc
  └─ terminal write: status=complete or status=error, fenced
  ▼
Firestore  sessions/{sid} + sessions/{sid}/turns/{nnnn} + sessions/{sid}/events/{eid}
  ▲
  │ onSnapshot listeners (4 of them, see chat-state.svelte.ts)
  │
Browser  shows live progress, survives reload/device-switch via capability URL
```

Watchdog Cloud Function runs every 2 minutes; fails any session whose `lastHeartbeat` or `lastEventAt` has gone stale. Total transport plumbing is ~3,376 lines (worker + functions + chat-state); agent code itself is 600 lines.

Three transport rewrites in twelve months (`adk deploy cloud_run` → pipeline-decoupling → server-stored sessions). The migration to GEAR would be v4 — but the case is "stop owning a runtime we shouldn't own," not "fix another failure mode."

---

## 3. What changed in April 2026 (calibrated against probe findings)

| Release-notes claim                    | Probe finding                                                                                                                                                                                                                                                      | Migration impact                                                                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| "Long-running operations up to 7 days" | **Misleading phrasing.** No invocation-level LRO API for chat turns. But the underlying durability property is real: R1 Test 1 proved `streamQuery` survives caller `kill -9` for ≥5 min; R3.2 proved it survives explicit Cloud Function abort for ≥240s (twice). | Caller-disconnect-survival is the durability mechanism. Watchdog continues polling Firestore liveness, not `operations.get`. |
| "Sub-second cold starts"               | Directionally consistent — ~2s observed first-event including LLM thinking.                                                                                                                                                                                        | Production should set `min_instances=1` if user-configurable.                                                                |
| "Custom session IDs"                   | **Platform supports it; ADK SDK rejects with stale guard ([adk-python#987](https://github.com/google/adk-python/issues/987)).** Bypass via direct REST.                                                                                                            | We use `se-{sid}` end-to-end and delete `adkSessionId` plumbing.                                                             |
| "Provisioning under 1 minute"          | **Wrong** — ~3.5 min observed for both `create()` and `update()`.                                                                                                                                                                                                  | CI/CD planning: assume 4 min.                                                                                                |
| (R3 finding, not in release notes)     | **`sessionState` mutability post-create is via `:appendEvent` only.** PATCH on `sessionState` is intentionally rejected by the platform.                                                                                                                           | Per-turn metadata propagation requires one REST call per turn — see §4.6.                                                    |
| (R3 finding, not in release notes)     | **Cloud Function clean-disconnect handoff works.** Explicit `reader.cancel()` + `controller.abort()` after first NDJSON line, then 202. Agent Runtime continues.                                                                                                   | Production `agentStream` uses this exact shape; `timeoutSeconds: 90` to wait for first NDJSON line.                          |

---

## 4. How GEAR works (after three probe rounds)

### 4.1 Deployment

`agent_engines.create(agent_engine=AdkApp(app=our_app), requirements=[...], extra_packages=[...], gcs_dir_name="...", env_vars={...})` is the entry point. Python 3.9–3.12. ~3.5 min provisioning. Returns a `ReasoningEngine` resource with stable name.

**Operational gotchas (must land in deploy.yml):**

- Wrap in `agent_engines.AdkApp(app=our_app)` — direct `App` rejected.
- `gcs_dir_name=f"agent_engine_{name}"` per distinct deployment — without it, parallel deploys overwrite the same staging pickle.
- `App.name` must be a Python identifier (no hyphens). Display name takes hyphens.
- `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` are reserved env vars — rejected if passed.
- Cloudpickle records the module name where a class is defined; use relative imports inside the bundled package.

### 4.2 Invocation contract

Deployed agent exposes:

- `:createSession?sessionId=…` — REST. Custom IDs accepted at platform layer (round-1 finding); ADK Python wrapper has stale guard, so we call REST directly.
- `:appendEvent` — REST. Adds an event to the session's history. **Carries `actions.stateDelta` to mutate `sessionState`.** This is the only way to update state post-create (R3.1 finding).
- `:streamQuery?alt=sse` — REST. Returns NDJSON (newline-delimited JSON, NOT standard SSE `data: ...\n\n` frames despite the flag — round-2 finding). **Survives caller disconnect** including explicit `controller.abort()` (R3.2 finding).

### 4.3 Plugin model

`BasePlugin` callbacks fire reliably under deployed runtime. Signatures verified against `google-adk==1.28.0`:

| Callback                       | Signature                                                  | Use                                                                                                                                          |
| ------------------------------ | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `before_run_callback`          | `(*, invocation_context: InvocationContext)`               | Setup, write session-doc heartbeat                                                                                                           |
| `after_run_callback`           | `(*, invocation_context: InvocationContext)`               | Terminal state, close timeline                                                                                                               |
| `on_event_callback`            | `(*, invocation_context: InvocationContext, event: Event)` | **Load-bearing** — replaces `worker_main.py`'s event loop. Receives full ADK Events with function_call/function_response/grounding payloads. |
| `before_/after_agent_callback` | `(*, agent: BaseAgent, callback_context: CallbackContext)` | Per-sub-agent observability                                                                                                                  |
| `before_/after_tool_callback`  | `(*, tool, tool_args, tool_context: ToolContext, ...)`     | Per-tool intercepts                                                                                                                          |

**Defensive pattern (write-class taxonomy):** uncaught exceptions in plugin callbacks halt the run. Different writes need different handling:

| Write class     | Examples                                                             | Failure handling                                |
| --------------- | -------------------------------------------------------------------- | ----------------------------------------------- |
| **Critical**    | `before_run` heartbeat, terminal `after_run`, ownership-claim writes | Retry with backoff; propagate on final failure  |
| **Best-effort** | Per-event timeline writes, source extraction, intermediate progress  | `try/except` swallow + log; never halt the run  |
| **Heartbeat**   | Periodic `lastHeartbeat` writes from the asyncio task                | `try/except` swallow; log if N consecutive fail |

### 4.4 Browser ↔ Agent Runtime path

Agent Runtime has no public CORS-friendly endpoint. The Firebase Cloud Function `agentStream` survives the migration as the proxy — its dispatch flow changes substantially.

**The new agentStream flow (R3.2-verified):**

```javascript
// agentStream — Node 22, timeoutSeconds: 90 (was 30)
const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/cloud-platform'] });
const { token } = await (await auth.getClient()).getAccessToken();

// 1. (First turn only) createSession via REST
if (isFirstTurn) {
	await fetch(
		`https://${LOCATION}-aiplatform.googleapis.com/v1beta1/${RESOURCE}/sessions?sessionId=se-${sid}`,
		{
			method: 'POST',
			headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
			body: JSON.stringify({ userId, sessionState: { runId, attempt, turnIdx } })
		}
	);
}

// 2. (Every turn) appendEvent to mutate state with new turn metadata
await fetch(
	`https://${LOCATION}-aiplatform.googleapis.com/v1beta1/${RESOURCE}/sessions/se-${sid}:appendEvent`,
	{
		method: 'POST',
		headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
		body: JSON.stringify({
			author: 'agentStream',
			invocationId: `turn-${turnIdx}-${runId}`,
			timestamp: new Date().toISOString(), // RFC3339 string, NOT Unix float
			actions: { stateDelta: { runId, attempt, turnIdx } } // camelCase, NOT snake_case
		})
	}
);

// 3. Initiate streamQuery
const controller = new AbortController();
const res = await fetch(
	`https://${LOCATION}-aiplatform.googleapis.com/v1/${RESOURCE}:streamQuery?alt=sse`,
	{
		method: 'POST',
		signal: controller.signal,
		headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
		body: JSON.stringify({
			class_method: 'async_stream_query',
			input: { user_id: userId, session_id: `se-${sid}`, message: queryText }
		})
	}
);

// 4. Read first NDJSON line (handoff proof — proves Agent Runtime accepted the request)
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
	const { value, done } = await reader.read();
	if (done) break;
	buffer += decoder.decode(value, { stream: true });
	const idx = buffer.indexOf('\n');
	if (idx >= 0 && buffer.slice(0, idx).trim()) break;
}

// 5. Explicit clean disconnect — Agent Runtime continues server-side
await reader.cancel().catch(() => {});
controller.abort();

// 6. Return 202 to browser; FirestoreProgressPlugin handles the rest
res.status(202).json({ ok: true, sid });
```

**The progress UI keeps reading Firestore via onSnapshot — that path is unchanged.** Only the dispatch shape changes.

### 4.5 Service accounts

Two distinct SAs, different roles (R1+R2 finding):

- `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` (note `-re` suffix) — **runtime SA**, the one our deployed code runs as. Needs:
  - `roles/datastore.user` (FirestoreProgressPlugin writes)
  - `roles/logging.logWriter` (granted but logs still don't surface — see §6 R2.6 caveat)
  - `roles/secretmanager.secretAccessor` (runtime secret fetch)
- `service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com` (no `-re`) — **deploy-time SA**. Default Vertex AI Service Agent. Needed only if using SecretRef in `env_vars` (we don't — see §5 R2.2 below).

### 4.6 Per-turn `:appendEvent` recipe (R3.1)

The platform's documented `sessions.patch` does NOT update `sessionState` — explicit error: _"Can't update the session state for session [...], you can only update it by appending an event."_ The intentional mechanism is `:appendEvent` with `actions.stateDelta`. Verified payload:

```http
POST https://us-central1-aiplatform.googleapis.com/v1beta1/{resource}/sessions/{sid}:appendEvent
Authorization: Bearer {token}
Content-Type: application/json

{
  "author": "agentStream",
  "invocationId": "turn-1-r-abc123",
  "timestamp": "2026-04-26T18:18:41.775335Z",
  "actions": {
    "stateDelta": {"runId": "r-abc123", "turnIdx": 1, "attempt": 1}
  }
}

→ 200 OK
{}
```

**Field-format gotchas:**

- camelCase only: `invocationId`, `stateDelta`, `sessionState`. snake_case rejected.
- Timestamp must be RFC3339 string (`2026-04-26T18:18:41.775335Z`), NOT Unix float.
- `sessionId` regex: `[a-z][a-z0-9-]*[a-z0-9]` — no underscores, no uppercase.
- Response body is empty JSON `{}` — success indicated by 200 status only.

### 4.7 Pricing

vCPU-hour + GiB-hour during request processing, like Cloud Run. Free tier exists. Three rounds of probes cost single-digit dollars total; production cost should be in the same ballpark as the current Cloud Run worker.

---

## 5. Probe results — verified migration mapping

Each row is one operational concern, with empirical evidence from one of the three probe rounds.

| Concern                                                                     | Verdict                                                                            | Source            | Migration impact                                                  |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------- | ----------------------------------------------------------------- |
| Caller-disconnect survival                                                  | **PROVEN** (kill -9 → 238.8s gap)                                                  | R1 Test 1         | Migration unblocked at the load-bearing gate.                     |
| Plugin callbacks under deployed runtime                                     | **PROVEN** (all callbacks fire)                                                    | R1 Test 3         | FirestoreProgressPlugin design viable.                            |
| Initial metadata via `session.state` at create                              | **PROVEN**                                                                         | R1 Test 4         | Production-intended mechanism works on first turn.                |
| **Per-turn metadata mutation**                                              | **PROVEN via `:appendEvent`**                                                      | **R3.1**          | One REST call per turn before `streamQuery`.                      |
| Custom session IDs                                                          | SDK fail, REST works                                                               | R1 doc-vs-reality | Bypass ADK; delete `adkSessionId` plumbing.                       |
| Production agent shape (`SequentialAgent` + `ParallelAgent` + `output_key`) | **PROVEN**                                                                         | R2.5              | No agent restructuring needed.                                    |
| Multi-turn `session.state` persistence (no mutation)                        | **PROVEN**                                                                         | R2.3              | Existing pattern transfers cleanly.                               |
| Outbound HTTPS to Apify/TripAdvisor                                         | **PROVEN**                                                                         | R2.1              | No VPC config needed.                                             |
| Gemini 3.1 routing via `location='global'`                                  | Lazy-init Gemini subclass                                                          | R2.4              | Code prerequisite — see §7.                                       |
| SecretRef env vars                                                          | FAIL — use runtime fetch                                                           | R2.2              | Use `SecretManagerServiceClient` in `set_up()`.                   |
| Logs visibility from agent                                                  | FAIL — no logs surface in API                                                      | R2.6              | Use Firestore-driven observability (already in use).              |
| Node-side `:streamQuery`                                                    | NDJSON, not SSE frames                                                             | R2.7              | agentStream uses line-by-line JSON parser.                        |
| Concurrent invocations on same session                                      | NOT serialized                                                                     | R1 Test 6         | Idempotency stays in Firestore — `currentRunId`/takeover survive. |
| **Cloud Function clean-disconnect handoff**                                 | **PROVEN** (explicit `reader.cancel()` + `controller.abort()` → 240.6s gap, twice) | **R3.2**          | Production agentStream uses this shape; `timeoutSeconds: 90`.     |
| In-flight `update()` behaviour                                              | INCONCLUSIVE (R2.8 harness bug)                                                    | R2.8              | A/B cutover with `transport` field, not in-place update.          |
| No invocation-level LRO API                                                 | confirmed                                                                          | R1 Test 2 + R2    | Watchdog continues polling Firestore liveness.                    |

**Net:** every load-bearing mechanic the migration depends on is empirically verified. The only items that fail (SecretRef env vars, log auto-capture in API) have documented workarounds.

---

## 6. What gets removed, moved, kept

### 6.1 Removed (~700 lines)

- **`agent/worker_main.py`** — most of it:
  - FastAPI scaffolding + lifespan management
  - Structured logging setup (Agent Runtime auto-configures, but auto-capture has caveats — §"What this won't fix")
  - ADK `Runner` construction and event loop (replaced by `on_event_callback`)
  - Signal handler (Agent Runtime owns container lifecycle)
  - Cloud Tasks request validation
- **`agent/Dockerfile`** as currently used for Cloud Run. (Custom container deployment is available if managed packaging hits a dep issue.)
- **`functions/index.js`** Cloud Tasks portions — `enqueueRunTask` helper, `CloudTasksClient` setup. ~50–80 lines.
- **The `adkSessionId` field** on session docs and the read/write at `worker_main.py:1086-1093`.
- **`.github/workflows/deploy.yml` `deploy-worker` job.** Replaced by `agent_engines.update(...)` step.
- **Cloud Tasks queue `agent-dispatch`** infra resource (after 30-day rollback window).
- **Cloud Run service `superextra-worker`** infra resource (after 30-day rollback window).

### 6.2 Moved (~300 lines)

- **`agent/superextra_agent/firestore_events.py`** — event mapping logic stays line-for-line; what changes is the _caller_. Today: called from worker's event loop. After: called from `FirestoreProgressPlugin.on_event_callback`. Defensive `try/except` wrappers required around external writes.
- **Worker-side title generation** moves into a plugin or the agent's `set_up()` method.

### 6.3 Stays as-is

- **`functions/index.js` agentStream** — Firebase auth, rate limiting, Firestore session doc upsert. The dispatch flow changes (Cloud Tasks → REST `:appendEvent` + `:streamQuery` + clean abort) but the surrounding code is unchanged.
- **`functions/index.js` agentDelete** — unchanged.
- **`functions/watchdog.js`** — still need a stuck-session sweeper. Reads `lastHeartbeat`/`lastEventAt` written by the FirestoreProgressPlugin's heartbeat task.
- **`src/lib/chat-state.svelte.ts`** (697 lines) — four Firestore listeners, capability-URL routing, multi-turn state. Untouched.
- **`src/lib/firebase.ts`** — anon auth, Firestore client. Untouched.
- **All six Firestore composite indexes** in `firestore.indexes.json`.
- **Capability-URL session sharing model** — purely frontend/Firestore-rules.
- **Takeover transaction + currentRunId/currentAttempt fencing** in `worker_main.py:293-364` — must survive (R1 Test 6 confirmed Agent Runtime does NOT serialize concurrent invocations on the same session). Relocates from `worker_main.py` into `agentStream` as a pre-dispatch transactional check.
- **`adkSessionId` field** — KEPT through the 30-day rollback window. Legacy sessions on the Cloud Run worker still need it. Delete in a cleanup commit ONLY after Cloud Run worker decommission is complete.

### 6.4 Net code change

- Removed: ~700 lines (worker plumbing + dispatch portions of `index.js`).
- Added: ~250 lines (FirestoreProgressPlugin + lazy Gemini subclass + Secret Manager runtime fetch + Node `:appendEvent`/`:streamQuery` recipe + plugin-owned heartbeat task + write-class taxonomy).
- **Net reduction: ~450 lines.** Real, but smaller than v1's ~850 estimate. The migration's value is in _what_ gets deleted (the gnarliest plumbing) more than the count.

---

## 7. Code prerequisites (must land before any production deploy)

These are the seven required code changes before any production-shape Agent Runtime deploy. Each has empirical proof from the probes.

### 7.1 Lazy-init Gemini subclass — `agent/superextra_agent/specialists.py` (R2.4)

Production's eager `g.api_client = Client(vertexai=True, location='global', ...)` fails at cloudpickle: `TypeError: cannot pickle '_thread.lock' object`. Replace with:

```python
class GeminiGlobalEndpoint(Gemini):
    @property
    def api_client(self) -> Client:
        client = self.__dict__.get("_lazy_global_client")
        if client is not None: return client
        client = Client(vertexai=True, location="global", http_options=types.HttpOptions(retry_options=RETRY))
        self.__dict__["_lazy_global_client"] = client
        return client

    @api_client.setter
    def api_client(self, value): self.__dict__["_lazy_global_client"] = value
```

~30 LOC. Verified end-to-end with `gemini-3.1-pro-preview`.

### 7.2 Secret Manager runtime fetch — `agent/superextra_agent/agent.py` `set_up()` (R2.2)

Replace any reliance on `SecretRef` in `env_vars` (which deploys but runtime fails to start). Inside the agent's `set_up()`:

```python
from google.cloud import secretmanager
client = secretmanager.SecretManagerServiceClient()
def fetch_secret(name: str) -> str:
    return client.access_secret_version(name=f"projects/{PROJECT}/secrets/{name}/versions/latest").payload.data.decode("utf-8")
PLACES_API_KEY = fetch_secret("google-places-api-key")
APIFY_TOKEN = fetch_secret("apify-token")
# ...
```

Add `google-cloud-secret-manager` to `agent/requirements.txt`. Grant runtime SA `roles/secretmanager.secretAccessor`.

### 7.3 `FirestoreProgressPlugin` — `agent/superextra_agent/firestore_progress.py` (R1, R2.3, R3.1)

Subclass `BasePlugin`. Implements:

- `before_run_callback` — write `before_run` doc, set `lastHeartbeat`, **spawn heartbeat asyncio task** (mirrors today's worker pattern).
- `on_event_callback` — call existing `firestore_events.map_event` + `write_event_doc`, update `lastEventAt`. Reads `runId`/`attempt`/`turnIdx` from `invocation_context.session.state` (verified by R3.1 `:appendEvent` mechanism).
- `after_run_callback` — write terminal `after_run` + close timeline + cancel heartbeat task.
- All external writes wrapped in **write-class taxonomy try/except** (§4.3 above).

### 7.4 Per-turn `:appendEvent` — `functions/index.js` `agentStream` (R3.1)

Before every `streamQuery`, agentStream calls `:appendEvent` to mutate `sessionState` with the new turn's `runId`/`attempt`/`turnIdx`. Concrete recipe in §4.6 above. Critical format: camelCase JSON, RFC3339 timestamp.

### 7.5 Cloud Function clean-disconnect handoff — `functions/index.js` `agentStream` (R3.2)

Replace Cloud Tasks dispatch with: `fetch(:streamQuery)` → read first NDJSON line → `reader.cancel()` + `controller.abort()` → return 202. Concrete recipe in §4.4 above. **`agentStream` `timeoutSeconds: 90`** (vs. current 30s) to wait for first NDJSON line.

### 7.6 NDJSON parser in agentStream (R2.7)

`:streamQuery?alt=sse` returns NDJSON (newline-delimited JSON), NOT standard SSE `data: ...\n\n` frames despite the flag. Parse line-by-line as plain JSON. Don't use EventSource libraries. Don't look for `data: ` prefix.

### 7.7 Custom session ID via direct REST (R1 doc-vs-reality)

ADK's `create_session(session_id=...)` raises `ValueError` due to a stale client-side guard. Bypass: REST `:createSession?sessionId=se-{sid}` directly from agentStream. Use our existing UUID-based sids prefixed with `se-`. Session ID regex: `[a-z][a-z0-9-]*[a-z0-9]`.

---

## 8. IAM matrix (one-time setup)

```bash
PROJECT_NUMBER=907466498524

# Runtime SA (the -re suffix is for "reasoning engine") — what the deployed agent runs as
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

Add `google-auth-library` to `functions/package.json` as a direct dependency (already added during R3 setup).
Add `google-cloud-secret-manager` to `agent/requirements.txt`.
Add ADC `quota_project_id` for `firebase deploy` from CI/local.

---

## 9. Migration plan — A/B cutover

### Phase 1 — Code prerequisites (3–4 days)

Land §7 prerequisites on `main`. Each is independently testable:

- Lazy Gemini subclass — unit test with cloudpickle round-trip.
- Secret Manager fetch — integration test with a probe secret.
- FirestoreProgressPlugin — local InMemoryRunner test with mocked Firestore client.
- Per-turn `:appendEvent` — REST integration test against a staging Agent Runtime.
- agentStream clean-disconnect — unit test with mocked fetch + verifier that abort/cancel is called.
- NDJSON parser — unit test with sample streamQuery response.
- Custom session ID via REST — integration test.

### Phase 2 — IAM matrix (½ day)

Run §8 grants. Add to `deploy.yml` as one-time setup job.

### Phase 3 — Production deploy + A/B (2–3 days)

1. Deploy production agent (with all Phase 1 prerequisites + lazy Gemini for all specialists) to a staging Agent Runtime resource via `agent_engines.create(gcs_dir_name="agent_engine_staging", ...)`.
2. Add **`transport: 'cloudrun'|'gear'`** field to the Firestore session doc. Set on first turn based on a feature flag; subsequent turns read the session's stored transport (sticky per-session, not per-UID).
3. Add feature flag `USE_AGENT_RUNTIME_PCT` in `agentStream` that determines what fraction of NEW sessions get `transport: 'gear'`. Existing sessions stay on whatever transport they were created with.
4. Smoke test: flag at 0%, but force `transport: 'gear'` for the developer's UID. Run a deep query end-to-end. Confirm Firestore progress shape matches existing.
5. Roll the flag to 10% (new sessions), then 50%, then 100% over 5–7 days. Hold at any stage if errors appear. Existing legacy sessions continue running on the Cloud Run worker.

### Phase 4 — Cutover (1 day, after 48h of clean 100% new-session traffic)

1. Promote staging Agent Runtime resource as production — update the `WORKER_URL` (or equivalent Agent-Runtime resource pointer) in `agentStream`. Or simply switch the feature flag to 100% and let `transport` field route.
2. Keep the legacy worker deployed for 30 days as "break glass" rollback. Old sessions with `transport: 'cloudrun'` keep working.
3. After 30 days clean: decommission Cloud Tasks queue + Cloud Run service. Delete `agent/worker_main.py`. Remove `enqueueRunTask` from `functions/index.js`. Remove `deploy-worker` job from `deploy.yml`. Delete the `adkSessionId` field on session docs in a cleanup commit. Replace with `agent_engines.update(...)` step gated on agent code changes.

---

## 10. Risks and mitigations

| Risk                                                                                                        | Severity | Mitigation                                                                                                                                                                |
| ----------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lazy Gemini subclass interacts badly with ADK internals at scale                                            | Medium   | Phase 3 smoke runs the 8-specialist parallel pipeline. Discover during 10% rollout, not 100%.                                                                             |
| Per-turn `:appendEvent` adds latency to follow-up turns                                                     | Low      | Single REST call (~200ms p50) before each streamQuery. Negligible vs. 7–15 min pipeline.                                                                                  |
| Cloud Function clean-disconnect race — 202 returns before runtime acknowledges first event                  | Low      | Probe verified the handoff with timestamp evidence. The first NDJSON line IS the runtime acknowledgement.                                                                 |
| Concurrent dispatch race during A/B traffic split                                                           | Low      | `transport` field is sticky per-session; one user can't be split mid-conversation. Plus existing `currentRunId`/takeover transaction protects against duplicate dispatch. |
| `:streamQuery` returns 200 but empty stream (ADK [#1830](https://github.com/google/adk-python/issues/1830)) | Low      | Probes confirmed events arrive correctly when parsed as NDJSON. Bug class is consumer-side parsing.                                                                       |
| Cold-start regression on idle traffic                                                                       | Low      | Probe observed sub-second cold start. If production exhibits worse, set `min_instances=1` if available.                                                                   |
| Pricing surprises                                                                                           | Low      | Same vCPU/GiB-hour model as Cloud Run. Back-of-envelope estimate during Phase 3.                                                                                          |
| Vendor lock-in deepens                                                                                      | Medium   | Real but bounded — agent code (specialists, instructions, tools) is portable; only the deployment harness becomes Google-specific.                                        |
| Rollback during A/B                                                                                         | Low      | `transport` field flip is instant for new sessions; old sessions keep working on legacy worker. 30-day worker preservation is the hard fallback.                          |
| `:appendEvent` breaks if Google changes the schema                                                          | Low      | The `:appendEvent` API is documented in v1beta1; v1 will inherit when promoted. We pin `aiplatform_v1beta1` in tests.                                                     |

---

## 11. What this migration will NOT fix

(Same as v2 — repeating because it shapes committee expectations.)

The migration **does not remove** any of the following:

- **`src/lib/chat-state.svelte.ts`** (697 lines). Four Firestore listeners, recovery, capability-URL routing, multi-turn state. Inherent to mobile-resilient long-running-pipeline UX.
- **`functions/watchdog.js`** (223 lines). Agent runs can still fail; we still need a sweeper.
- **`functions/index.js` agentStream** (~500 lines after removing Cloud Tasks bits). Agent Runtime has no public CORS-friendly endpoint; we need the proxy.
- **Capability URLs and Firestore rules.** Purely UX choices.
- **Takeover transaction + currentRunId/currentAttempt fencing.** R1 Test 6 confirmed Agent Runtime does NOT serialize concurrent invocations.
- **Logs visibility caveat.** Auto-capture from Agent Runtime to our project's Cloud Logging API didn't work in R2 even with full IAM. Production observability via Firestore (which we already do) is the primary path. Adding explicit `google.cloud.logging.Client.setup_logging()` in `set_up()` is recommended during cutover and verify before declaring observability complete.

If the committee's primary frustration is "browser-cloud-agent session sync is too complicated," the honest answer remains: **most of that complexity is a long-running-pipeline UX tax, not a self-hosting tax**, and migration to Agent Runtime will not eliminate it. The migration's value is in the runtime layer specifically.

---

## 12. Open questions for the committee

1. **Tolerance for deeper Google lock-in.** Today the agent could migrate to any Python host with a few days' work. Post-migration, leaving Agent Runtime means re-implementing what we just deleted (~700 LOC) plus the per-turn `:appendEvent` recipe. Acceptable trade-off?

2. **Feature-flag rollout aggressiveness.** Plan above is 10%/50%/100% over 5–7 days. Slower (2 weeks at 10%) or faster (50% on day 1) acceptable?

3. **30-day rollback window.** Keep the Cloud Run worker resource defined-but-undeployed for 30 days post-cutover as "break glass" rollback? Cost is near-zero; cognitive cost is low.

4. **Memory Bank deferral confirmation.** Still deferred until user accounts exist (per Adam's explicit instruction). Re-affirm.

5. **agentStream timeout bump from 30s → 90s** is a public-API behaviour change. Browser-side handling expects sub-second responses today. Verify this doesn't break any client retry/backoff logic.

---

## 13. Recommendation

**Approve the migration.** Execute Phases 1–4 over 7–10 working days starting on a date the committee chooses.

The reasoning, condensed:

- **Both reviewer-flagged P0s resolved with empirical evidence.** Per-turn metadata via `:appendEvent`; clean-disconnect handoff with explicit abort. Both reproducible (R3.2 ran twice with identical 240.6s gaps).
- **Every load-bearing mechanic the migration depends on is verified across three probe rounds.** Caller-disconnect-survival, plugin model, agent shape, multi-turn state, outbound HTTPS, Gemini 3.1 routing, NDJSON parsing, custom session IDs — all have empirical proof.
- **The deletable code is the worst code we own.** Cloud Run/FastAPI scaffolding, in-process Runner, signal handling, Cloud Tasks dispatch — most-likely-to-need-future-rework, least-connected-to-product-value. Heartbeat/takeover/fencing SURVIVE; the narrative correction in §6 reflects this honestly.
- **A/B cutover with `transport` field is reversible at every step.** 30-day worker preservation is the hard fallback.
- **Opportunity cost of NOT migrating is ongoing.** Every quarter we don't move, we accumulate more drift between our custom Runner and ADK's Runner, more pinned dependencies, more watchdog edge cases.

**Honest counterweight:** the migration does not solve the chat-state/recovery complexity that drove the original frustration; that's UX tax, not self-hosting tax. The `agentStream` rewrite is more substantial than v2 implied (per-turn `:appendEvent`, clean-disconnect handoff, NDJSON parser, 90s timeout — collectively ~150 LOC of new logic). If the committee weights these differently, "wait until July 2026 and re-evaluate" remains a defensible alternative.

---

## 14. References

**Probe artifacts (load-bearing for v3):**

- [`gear-probe-plan-2026-04-26.md`](./gear-probe-plan-2026-04-26.md) — round 1 plan
- [`gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md) — round 1 results (caller-disconnect, plugin model, agent shape)
- [`gear-probe-plan-round2-2026-04-26.md`](./gear-probe-plan-round2-2026-04-26.md) — round 2 plan
- [`gear-probe-results-round2-2026-04-26.md`](./gear-probe-results-round2-2026-04-26.md) — round 2 results (Gemini 3.1, env vars, multi-turn, logs, Node SSE)
- [`gear-probe-plan-round3-2026-04-26.md`](./gear-probe-plan-round3-2026-04-26.md) — round 3 plan
- [`gear-probe-results-round3-2026-04-26.md`](./gear-probe-results-round3-2026-04-26.md) — round 3 results (per-turn state, CF clean-disconnect)
- [`gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md) — full execution log

**Superseded (audit trail):**

- [`gear-migration-proposal-2026-04-25.md`](./gear-migration-proposal-2026-04-25.md) — v1 (pre-probe, multiple wrong claims)
- [`gear-migration-proposal-2026-04-26-v2.md`](./gear-migration-proposal-2026-04-26-v2.md) — v2 (post-R2, two unverified P0 mechanics that R3 resolved)

**Probe code (kept in repo for reference until migration completes):**

- `agent/probe/` — all probe agents, plugin (with R3's `invocation_id` field), harnesses, deploy script
- `functions/probe-stream-query.js` — proven Node `:streamQuery` recipe (becomes part of `agentStream`)
- Diagnostic Cloud Functions (`probeHandoffAbort`, `probeHandoffLeaveOpen`) — to delete after R3 cleanup

**Internal architecture docs:**

- `docs/pipeline-decoupling-plan.md` — current architecture rationale
- `docs/server-stored-sessions-cleanup-plan-2026-04-23.md` — `agentCheck` deletion record
- `docs/deployment-gotchas.md` — current operational notes (will be updated post-migration)

**Internal code anchors (commit `8fcdb17`):**

- `agent/worker_main.py:175–178` — current `VertexAiSessionService` + `Runner` construction (becomes obsolete)
- `agent/worker_main.py:1086-1093` — current `adkSessionId` write (deletable after rollback window)
- `agent/superextra_agent/firestore_events.py:124, 98` — event mapping (becomes plugin internals)
- `agent/superextra_agent/specialists.py:31` — current `_make_gemini` (needs lazy-subclass rewrite per §7.1)
- `agent/superextra_agent/chat_logger.py:113,134,144` — proven plugin signature reference
- `functions/index.js:177` — current `agentStream` `timeoutSeconds: 30` (becomes 90 per §7.5)
- `functions/index.js:144–167` — current `enqueueRunTask` (replaced by `:appendEvent` + `:streamQuery` + clean abort)
- `src/lib/chat-state.svelte.ts:1–22` — header documenting four-listener architecture (unchanged by migration)

**External references:**

- [Gemini Enterprise Agent Platform release notes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/release-notes)
- [Vertex AI Agent Engine overview](https://docs.cloud.google.com/agent-builder/agent-engine/overview)
- [Sessions REST API](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1beta1/projects.locations.reasoningEngines.sessions)
- [Logging an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/logging)
- [Authenticate to Agent Platform](https://docs.cloud.google.com/vertex-ai/docs/authentication)
- [Agent Engine networking](https://discuss.google.dev/t/vertex-ai-agent-engine-networking-overview/267934)
- [Firebase Cloud Functions termination semantics](https://firebase.google.com/docs/functions/terminate-functions)
- [adk-python#987 — Custom session ID guard](https://github.com/google/adk-python/issues/987)
- [adk-python#3628 — Gemini 3 + Agent Engine bug](https://github.com/google/adk-python/issues/3628)
- [adk-python#1830 — stream_query empty stream class](https://github.com/google/adk-python/issues/1830)
- [adk-python#4464 — plugin callback firing (does NOT reproduce on Agent Runtime)](https://github.com/google/adk-python/issues/4464)
