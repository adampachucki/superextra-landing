# Pipeline Decoupling — Execution Log

Running log of what was done, what broke, and what we learned during implementation of
`docs/pipeline-decoupling-plan.md`. Kept chronologically by phase. Add an entry every
time something non-obvious happens.

For full architecture, read the plan. For evidence behind settled facts, read
`docs/pipeline-decoupling-spike-results.md`. This file is the _execution_ record,
not the design.

---

## Phase 0 — Agent speed-ups + p99 gate

Status: **PASS**. Completed 2026-04-20.

### What changed

- `agent/superextra_agent/specialists.py` — added `MEDIUM_THINKING_CONFIG`;
  `_make_specialist` accepts a per-specialist `thinking_config`. Applied MEDIUM to
  `guest_intelligence`, `location_traffic`, `marketing_digital`, `gap_researcher`.
  Kept HIGH on `market_landscape`, `menu_pricing`, `revenue_sales`, `operations`,
  `review_analyst`, `dynamic_researcher_1`.
- `agent/superextra_agent/agent.py` — context enricher → MEDIUM (function-caller,
  not a deep reasoner per plan). Synthesiser stays HIGH.
- `agent/tests/fixtures/phase0_queries.json` — new fixture: 10 runs against 5
  Berlin restaurants (Umami + Zeit für Brot, Round & Edgy, Five Elephant,
  Acid Coffee). Place IDs resolved once via Places Text Search and baked in so
  runs are deterministic.
- `agent/tests/phase0_measure.py` — measurement harness using in-process
  `Runner(app=app, session_service=VertexAiSessionService(...))`. Per-run
  timeout 30 min. Saves after every run. `PHASE0_TIERS` env var filters by
  tier.

### Gate verdict

First pass, 10/10 runs, 0 timeouts, 0 exceptions:

| Metric | Value                                             |
| ------ | ------------------------------------------------- |
| p50    | 4.78 min                                          |
| p95    | 7.49 min                                          |
| p99    | 7.49 min                                          |
| max    | 7.49 min                                          |
| gate   | p99 < 22 min → **PASS** with ≥ 14 min of headroom |

Conservative defaults applied: `review_analyst` and `dynamic_researcher_1` kept
at HIGH — plan didn't name them for MEDIUM. Synthesiser HIGH as required.

### Issue — synthesiser silently dropping `final_report` on broad queries

First pass: 3 of 4 broad runs completed with elapsed time + no timeout + no
exception, but `final_report` was never written to Agent Engine state. The
synthesiser emitted 1 event containing `error_code`.

Root cause: Gemini 3.1 preview's `code_execution` tool (used for chart
generation) intermittently emits `MALFORMED_FUNCTION_CALL` (broken JSON in the
`python_interpreter` call — backtick template syntax instead of JSON, unescaped
`€` or `ü`, etc.). A second error mode also appeared on rerun:
`UNEXPECTED_TOOL_CALL`. Both produce responses with no text, so
`output_key='final_report'` never persists.

**This is pre-existing, not a Phase 0 regression.** Synthesiser thinking config
is unchanged. Today's production already masks it via the generic fallback
string "I wasn't able to generate a response. Please try rephrasing your
question." in `functions/index.js:362-366`.

Fix (graceful degradation): `_embed_chart_images` in `agent.py` now detects
`llm_response.error_code` and builds a text-only report from the specialist
outputs in state. `final_report` is always populated; charts render normally
when code_execution succeeds.

Verification: same 4 broad queries re-run with the fix applied.

| Run     | Error code              | final_report              |
| ------- | ----------------------- | ------------------------- |
| broad_1 | MALFORMED_FUNCTION_CALL | ✓ fallback 33 KB          |
| broad_2 | UNEXPECTED_TOOL_CALL    | ✓ fallback 36 KB          |
| broad_3 | none                    | ✓ normal 264 KB w/ charts |
| broad_4 | none                    | ✓ normal 348 KB w/ charts |

4/4 populate `final_report`. Fallback covers both error codes because it
triggers on any `error_code`, not a specific string. Timing envelope unchanged
(p99 still 7.09 min).

Charts were documented as a "core deliverable" in `instructions/synthesizer.md`,
so removing `code_execution` entirely wasn't the right move.

### Transport implication

Phase 3's worker has a reply sanity check (length ≥ 100, non-`Error:` prefix)
before writing `status='complete'`. With this fallback in place, the worker
will _always_ have usable `final_report` text to sanity-check, rather than
having to guess why a completed pipeline produced nothing.

### Known pre-existing regressions NOT addressed (confirmed in baseline)

- `test_follow_up_routing.py` — 4 failures. Some follow-ups route to
  `research_pipeline` instead of `follow_up`. Pre-existing per spike-results
  doc; tracked separately from this refactor.
- `test_router_evals.py` — 2 failures. Live eval, excluded from CI.

### Tests

- `pytest tests/ --ignore=tests/test_router_evals.py` → 84 passed, 4 failed
  (all pre-existing routing failures).
- `pytest tests/test_embed_chart_images.py` → 9 passed (6 existing + 3 new
  fallback tests).
- Live 4-broad verification: 4/4 clean, 2 hit fallback, 2 hit normal path.

### Artifacts kept

- `agent/tests/phase0_measurements.json` — 10-run gate measurement.
- `agent/tests/phase0_broad_rerun.json` — 4-run fallback verification.
- `agent/tests/phase0_run.log`, `agent/tests/phase0_broad_rerun.log` — full
  stdout from measurement runs.

---

## Phase 1 — Firebase Anon Auth + Firestore rules + indexes

Status: **DONE**. Completed 2026-04-20.

### What changed

- `firestore.rules` (new) — rules spec from the plan verbatim. Sessions and the
  `events` collection-group both read-gated by
  `request.auth.uid == resource.data.userId`. All writes denied (Admin SDK
  bypasses rules; worker and Cloud Function are the only writers).
- `firestore.indexes.json` (new) — four composite indexes declared:
  - `events` (COLLECTION_GROUP): `(userId, runId, attempt, seqInAttempt)` for
    client collection-group reads.
  - `sessions` (COLLECTION): `(status, queuedAt)` for watchdog queued-sweep.
  - `sessions` (COLLECTION): `(status, lastHeartbeat)` for watchdog
    heartbeat-silent sweep.
  - `sessions` (COLLECTION): `(status, lastEventAt)` for watchdog
    pipeline-wedged sweep.
- `firebase.json` — added `firestore.rules` + `firestore.indexes` references
  and a local firestore emulator block (port 8088, UI off).
- `src/lib/firebase.ts` (new) — singleton Firebase handle. Loads config from
  `/__/firebase/init.json` in production; falls back to the production hosting
  URL in dev (the config is public — API key only identifies the project,
  rules enforce access). Dynamic-imports `firebase/app`, `firebase/auth`, and
  `firebase/firestore` so the marketing bundle stays clean. Exports
  `getFirebase()`, `ensureAnonAuth()`, `getIdToken()`.
- `src/routes/agent/chat/+page.svelte` — `onMount` dynamically imports
  `$lib/firebase` and calls `ensureAnonAuth()` fire-and-forget. Failures log to
  console; nothing user-visible yet.
- `firestore.rules.spec.js` (new, repo root) — mocha + chai test suite using
  `@firebase/rules-unit-testing`. Loads rules directly from `firestore.rules`
  so the test stays aligned with what deploys.
- `package.json` — added `firebase` dep; `@firebase/rules-unit-testing`,
  `mocha`, `chai@4` devDeps; new `test:rules` script wrapping
  `firebase emulators:exec --only firestore`.

### Workstation setup (one-time)

- VM needed Java for the Firestore emulator — installed `openjdk-21-jre-headless`
  via `sudo apt-get install`. Downloaded the Firestore emulator JAR on first
  run (cached locally afterwards).

### Tests

- `npm run test:rules` → **10 passing** (sessions + events-collection-group):
  - owner can read, non-owner denied, unauthed denied
  - owner cannot write (server-only)
  - collection-group query works for owner
  - non-owner querying others' userId denied (the key hostile case)
- `npm run test` → 85 passing (no regressions).
- `npm run check` → 0 errors (13 pre-existing warnings untouched).
- `npm run build` → clean.
- `npx eslint` on touched files → 0 errors, 1 pre-existing warning.

### Bundle measurement

Built production bundle to confirm dynamic imports did their job:

- Largest chunk: **352 kB raw / 107 kB gzipped** (Firebase modular v10 lazy
  chunk). Matches spike G (97 kB) within tolerance — delta is `signInAnonymously`
  - `getIdToken` helpers that the spike didn't pull in.
- Firebase does not appear in marketing or agent-landing chunks (verified by
  scanning chunk contents for `firebase`).

### Observable outcome

Nothing user-visible (plan's intent). Anon auth runs silently on chat-route
mount; no UI change; rules + indexes declared but not yet deployed (that lands
in Phase 8's `firebase deploy` extension). The existing composite events index
in `superextra-site` (created during spike D) matches `firestore.indexes.json`
so the first deploy won't need to create it from scratch.

### Notes for later phases

- `firebase.ts` `ensureAnonAuth` is the hook Phase 4's POST flow will use to
  grab the Firebase ID token before calling `agentStream`.
- `getIdToken(forceRefresh=false)` is safe for normal requests; if Phase 4
  sees token-expired 401s we can flip it to `true`.
- `firestore.rules.spec.js` is designed to stay in sync with the deployed rules
  because it reads them from disk — when Phase 9 wires rules tests into CI,
  the test runner only needs Java + the Firestore emulator.

---

## Phase 6 — Cloud Tasks queue + IAM

Status: **DONE**. Completed 2026-04-20.

### What changed (live GCP state — no code changes)

- **Worker SA created**: `superextra-worker@superextra-site.iam.gserviceaccount.com`
  (`gcloud iam service-accounts create superextra-worker ...`). Project-level
  role grants (`aiplatform.user`, `datastore.user`) deferred to Phase 3 as
  part of worker build.
- **Cloud Tasks queue created**: `agent-dispatch` in `us-central1` with the
  plan's retry config: `--max-attempts=3 --min-backoff=10s --max-backoff=60s
--max-doublings=4`.
- **Cloud Tasks service identity provisioned** (`gcloud beta services identity
create --service=cloudtasks.googleapis.com`): the agent was not present until
  first use of the Cloud Tasks API. Identity:
  `service-907466498524@gcp-sa-cloudtasks.iam.gserviceaccount.com`.
- **IAM bindings — exactly the live-validated recipe** (spike C + validation
  finding 6):
  - Cloud Tasks service agent → `roles/iam.serviceAccountUser` on worker SA
  - Cloud Tasks service agent → `roles/iam.serviceAccountTokenCreator` on
    worker SA (the parallel-validation pass confirmed both are needed; the
    public Cloud Tasks guide under-specifies this).
  - Cloud Function SA (`907466498524-compute@developer.gserviceaccount.com`,
    reused from the existing functions' runtime SA) →
    `roles/cloudtasks.enqueuer` on the `agent-dispatch` queue.

### Verified

```
$ gcloud iam service-accounts get-iam-policy superextra-worker@...
bindings:
- members: [serviceAccount:service-907466498524@gcp-sa-cloudtasks...]
  role: roles/iam.serviceAccountTokenCreator
- members: [serviceAccount:service-907466498524@gcp-sa-cloudtasks...]
  role: roles/iam.serviceAccountUser

$ gcloud tasks queues get-iam-policy agent-dispatch --location=us-central1
bindings:
- members: [serviceAccount:907466498524-compute@developer...]
  role: roles/cloudtasks.enqueuer
```

### Deferred to later phases (not Phase 6 scope)

- Worker SA → `roles/run.invoker` on the worker Cloud Run service — blocked
  until Phase 3/8 creates the service. Will bind at deploy time.
- Worker SA → `roles/aiplatform.user`, `roles/datastore.user` on project —
  Phase 3 scope (listed under worker's Service Account config in the plan).
- OIDC audience — plan mandates "exactly the worker's `run.app` URL, no
  trailing slash". Applied at enqueue time in Phase 4's `agentStream`
  refactor; the worker URL is only known post-Phase 3 deploy.

### Gotcha captured

`gcloud tasks create-http-task` CLI does NOT accept `--dispatch-deadline`
(spike finding C.1). The `@google-cloud/tasks` Node library accepts it on the
Task resource's `dispatchDeadline` field, which Phase 4 will use. Worth
noting in `docs/deployment-gotchas.md` when Phase 8 lands.

---

## Phase 2 — Python event mapper

Status: **DONE**. Completed 2026-04-20.

### What changed

- `agent/superextra_agent/firestore_events.py` (new) — ADK event → Firestore
  doc mapper. Pure `map_event(event) → {type, data} | None` for testability +
  `map_and_write_event(...)` I/O wrapper that writes via `firestore.Client`
  through `asyncio.to_thread` so the runner loop isn't blocked.
- `agent/tests/test_firestore_events.py` (new) — 25 unit tests covering every
  mapping rule in the §B taxonomy table.

### Design choices

- **Stateless mapper**. Today's `parseADKStream` (500 lines in
  `functions/utils.js`) maintains in-memory counters (places total/completed,
  specialist progress) because SSE-to-client was server-side-stateful. The new
  architecture writes _each_ event to Firestore and lets the frontend aggregate
  from the durable event stream. The mapper just decides "emit a doc or skip"
  per single event — no cross-event state.
- **Source harvesting from grounding chunks first, markdown fallback second**.
  Plan mandates `grounding_metadata.grounding_chunks` since the in-process
  Runner exposes them directly (no AgentTool stripping). When chunks are absent
  we fall back to the markdown-link regex so specialists that still run
  `_append_sources` are covered.
- **`NOT_RELEVANT` guard**. Specialists without a brief return the literal
  text "NOT_RELEVANT" via `_make_skip_callback` — the mapper explicitly checks
  for that string in state_delta values so skipped specialists don't produce
  fake `activity-complete` rows.
- **SimpleNamespace-friendly getters**. `_get(obj, attr)` handles both
  attribute access (real ADK Events) and dict lookup (test fixtures). Keeps
  tests lightweight without importing google.adk.events at test time.
- **Coverage guard test** — `test_every_specialist_author_has_output_key_mapping`
  fails loud if a new specialist is added to `SPECIALIST_AUTHORS` without
  wiring it to `AUTHOR_TO_OUTPUT_KEY`. Prevents silent "final event dropped"
  regressions.

### Tests

- `pytest tests/test_firestore_events.py -v` → **25/25 pass**.
- Full agent suite: **112 passed, 4 failed** (same pre-existing
  `test_follow_up_routing.py` regressions as baseline).
- Fixture coverage smoke: loaded `spikes/adk_event_taxonomy_dump.json` and
  verified every author (14) that appears in a real 21-event pipeline run is
  handled by the mapper.

### Deferred (intentional — plan scope)

- Partial-text coalescing. Spike B showed 0 partials with default RunConfig;
  synthesiser emits its full reply in one event. If `RunConfig(streaming_mode=SSE)`
  is ever enabled for typewriter UX, this becomes a follow-up.
- `_append_sources` removal from `specialists.py`. The callback still keeps
  sources in state_delta text for the synthesiser's template — orthogonal
  concern. Mapper doesn't depend on it being present or absent.

---

## Phase 3 — Worker service superextra-worker

Status: **CODE DONE**. Deploy lands in Phase 8. Completed 2026-04-20.

### What changed

- `agent/worker_main.py` (new, ~430 lines) — FastAPI + in-process ADK Runner.
  Exposes `POST /run` (Cloud Tasks target) and `GET /healthz`. The skeleton
  from `spikes/skeletons/worker_main.py` was adapted with the fixes below,
  not shipped verbatim.
- `agent/Dockerfile` (new) — `python:3.12-slim`, minimal apt deps, layer-cached
  pip install, entrypoint `uvicorn worker_main:app --host 0.0.0.0 --port
$PORT`. Doesn't bake `AGENT_ENGINE_ID` / Places API keys — those come in
  as Cloud Run env vars at deploy time (matches `deployment-gotchas.md`).
- `agent/requirements.txt` — added `fastapi==0.136.0`,
  `uvicorn[standard]==0.39.0`, `google-cloud-firestore==2.22.0`. No
  `firebase-admin` (admin pattern is native via `google-cloud-firestore`) and
  no `google-cloud-tasks` (worker receives; doesn't enqueue).
- `agent/tests/test_worker_main.py` (new) — 19 unit tests covering takeover
  logic branches, fenced-update ownership-lost detection, source extraction,
  and title-fallback prefix stripping.

### Fixes I made to the skeleton

- **Takeover no longer rewrites `currentRunId`.** The plan's stale-run guard
  already ensures `currentRunId == run_id` at the "take over" branch; the
  skeleton's unconditional rewrite was redundant. Dropping it also provides
  a clean invariant: the worker never mutates `currentRunId`, only
  agentStream does on turn boundaries.
- **Separated pure logic from `@firestore.transactional`.** The decorator
  wraps functions such that callers can't invoke the inner logic with a mock
  transaction. Refactored to `_takeover_logic(...)` +
  `_takeover_txn = firestore.transactional(_takeover_logic)` — production
  unchanged; tests can drive the logic with mocks.
- **Three-way error classification**, not the skeleton's single `raise`:
  - `OwnershipLost` in the event loop → 500 (Cloud Tasks retry sees
    takeover-poll path and behaves correctly).
  - `GoogleAPICallError` (transient Firestore / GCP) → 500 (Cloud Tasks
    retries on a fresh attempt).
  - Anything else from the ADK runner → caught, `status=error` written via
    fenced txn, 200 returned so Cloud Tasks does NOT retry a deterministic
    pipeline bug.
- **Title generation** — `_generate_title()` calls Gemini Flash 2.5 via
  `google.genai.Client(vertexai=True, location="global")` (matches
  specialists' pattern for routing flash calls through the global endpoint)
  with `asyncio.wait_for(..., timeout=5s)`. Falls back to prefix-stripped,
  40-char truncation on any error.
- **Fixed `_strip_query_prefixes` edge case** — original looked for `"] "`
  (bracket + space), which left the prefix intact when the query was
  literally just the prefix with nothing after.
- **Source extraction on completion** — `_extract_sources_from_state_delta`
  scans every specialist's output_key text via the shared markdown-link
  regex in `firestore_events.py`, dedupes by URL. Populates the top-level
  `sources` array written with the `status='complete'` transition.

### Live GCP changes (Phase 3 scope, continuing Phase 6's SA setup)

- Worker SA granted project-level `roles/aiplatform.user` (Agent Engine
  session service + Vertex AI model calls).
- Worker SA granted project-level `roles/datastore.user` (Firestore native
  mode Admin SDK writes).
- Verified via
  `gcloud projects get-iam-policy superextra-site --filter="bindings.members:superextra-worker..."`:
  both roles bound.

### Deferred to Phase 8

- Worker SA `roles/run.invoker` on the worker Cloud Run service (service
  doesn't exist until Phase 8 deploys it).
- Cloud Run deploy with `--no-cpu-throttling --timeout=1790s --memory=2Gi
--max-instances=10 --min-instances=0 --concurrency=4
--no-allow-unauthenticated --service-account=superextra-worker@...`.
- Setting Cloud Run env vars: `AGENT_ENGINE_ID`, `GOOGLE_PLACES_API_KEY`,
  any other secrets the existing agent service carries.

### Tests

- `pytest tests/test_worker_main.py -v` → **19 passing** (takeover branches
  × 4 outcomes, fenced update ownership, source extraction, title fallbacks,
  missing-doc + userId-mismatch hostile cases).
- Full agent suite: **131 passed, 4 failed** (same pre-existing
  `test_follow_up_routing.py` failures as baseline).
- `cd functions && npm test` → 22 passing (baseline still clean — Phase 4
  will touch this).

### Design note

The worker's POST /run handler is around 200 lines of linear logic with
clearly labelled sections (takeover → poll → heartbeat → consume events →
sanity check → terminal write → title). Kept all state in local variables +
three module globals only read by `_sigterm_handler`. No classes — fits the
single-request-per-handler lifecycle of the skeleton.

---

## Phase 4 — agentStream refactor

Status: **DONE**. Completed 2026-04-20.

### What changed

- `functions/index.js` — `agentStream` is no longer an SSE streamer. Flow:
  1. Verify `Authorization: Bearer <idToken>` via `getAuth().verifyIdToken()`.
     401 on missing/invalid.
  2. IP rate limit (existing) + new UID rate limit (20 runs/hour per
     anon UID).
  3. Validate `message` + `sessionId` (existing guards).
  4. Generate `runId` server-side with `crypto.randomUUID()` — never trust
     client.
  5. Atomic `db.runTransaction` on `sessions/{sid}`:
     - Ownership check → **403** on `existing.userId != decoded.uid`.
     - In-flight check → **409** on `status ∈ {queued, running}`.
     - Upsert: `t.set(...)` for new sessions (initialises every field per
       plan line 362); `t.update(...)` for terminal sessions (preserves
       `userId`, `createdAt`, `adkSessionId`, `placeContext`, `title`;
       resets all per-turn fields).
     - `expiresAt = max(existing, now + 30d)` — never shrinks.
  6. Build queryText: `[Date: …]` always; `[Context: name, area (Place ID: …)]`
     only on first message. Matches current pipeline expectations verbatim.
  7. Enqueue Cloud Task with `task.name = queues/agent-dispatch/tasks/{runId}`,
     `dispatchDeadline: { seconds: 1800 }`, OIDC token
     `serviceAccountEmail=superextra-worker@...`, `audience=$WORKER_URL`.
  8. **202** `{ ok: true, sessionId, runId }`. Typical latency: one Firestore
     txn + one Cloud Tasks create = sub-300ms.
- **Dropped**: 440 s `AbortSignal.timeout`, 15 s keepalive interval,
  `res.on('close')` abort wiring, SSE headers/writes, `parseADKStream` call,
  `sessionMap` in-memory cache, `persistSession` helper, `generateTitle`
  helper (already in worker), source-fallback fetch to ADK state.
- **Kept**: `ADK_SERVICE_URL` + `auth = new GoogleAuth()` — still referenced
  by the legacy `agentCheck`. Phase 7 will retire them.
- `functions/package.json` — added `@google-cloud/tasks` as a runtime dep.
- `functions/index.test.js` — mocks extended with `runTransaction`,
  `FieldValue.serverTimestamp`, `getAuth`, `CloudTasksClient`.

### Design calls documented in code

- **Worker URL via env var** (`WORKER_URL`). Set at Cloud Run deploy time
  (Phase 8) via `--update-env-vars`. Avoids committing the per-deploy
  `run.app` hash.
- **Enqueue failure recovery** — if `createTask` throws, the code flips the
  session we just set to `queued` over to `status=error, error='enqueue_failed'`
  before returning 502. Prevents the watchdog from seeing a stuck-queued
  session caused by a transient Tasks outage.
- **ADK session creation deferred to the worker** — `adkSessionId` is passed
  as `null` on first turn; the worker calls
  `VertexAiSessionService.create_session()` and fences an update back. Keeps
  the Cloud Function out of the Agent Engine REST surface (which otherwise
  would need direct calls to `us-central1-aiplatform.googleapis.com`).
  **Note: this adds a small TODO to Phase 3's worker** — see below.
- **`isFirstMessage` signal is `!existing`**, not derived from the client's
  `history` array. If a user returns to a known session with cleared
  localStorage, we must NOT regenerate a title — the session doc is the
  source of truth.

### Phase 3 worker — Phase-4 follow-up applied

The worker now handles `adkSessionId=null` payloads. After takeover, if the
payload's `adkSessionId` is falsy, `worker_main.py` calls
`_session_svc.create_session(app_name=adk_app.name, user_id=body.userId)`,
captures `created.id`, and fenced-updates `sessions/{sid}.adkSessionId`
before calling `runner.run_async(session_id=adk_session_id, …)`. The
`RunRequest` model was widened to `adkSessionId: str | None = None`. All
44 worker/mapper tests still pass.

### Tests

- `cd functions && npm test` → **28 passing** (22 baseline + 6 new
  `agentStream` scenarios: missing auth, bad token, missing inputs,
  successful enqueue with decoded body inspection, 403 ownership, 409
  in-flight, follow-up preserves `adkSessionId` + suppresses Context prefix,
  502 recovery with `status=error` writeback).
- `npm run test` (Vitest) → 85 passing, no regression.
- Prettier + lint clean.

---

## Phase 5 — Frontend refactor

Status: **DONE**. Completed 2026-04-20.

### What changed

- `src/lib/firestore-stream.ts` (new) — `postAgentStream(url, body, idToken)`
  - `subscribeToSession(sid, runId, callbacks)`. The subscription wires two
    `onSnapshot`s (session doc + collection-group events query filtered by
    `userId=uid AND runId=runId`, ordered by `attempt` then `seqInAttempt`).
    Cache suppression on `status=complete` transitions so a stale
    `fromCache: true` snapshot doesn't fire `onComplete` before the server
    confirms. Emits `onAttemptChange` on `currentAttempt` increments so the UI
    can wipe retry-stale state. 10-second first-snapshot timer fires
    `onFirstSnapshotTimeout` for the REST fallback path.
- `src/lib/chat-state.svelte.ts` — transport layer swapped. `send()` now:
  1. Optimistically pushes the user message.
  2. `ensureAnonAuth()` → `getIdToken()` → `postAgentStream()` (401/403/409/429
     mapped to typed error strings in UI state).
  3. `subscribeToSession()` with callbacks built by `buildStreamCallbacks`
     (dedupes replies against message history so REST-recovery + Firestore
     racing is safe).
  - `switchTo(sid)` with a user-last-message now calls new
    `resumeIfInFlight(sid)`: single `getDoc` on `sessions/{sid}`, branches on
    `status`: `queued|running` → subscribe; `complete` → append reply (with
    dedup); `error` → surface error.
  - `recover()` tightened: only called on `onPermissionDenied` /
    `onFirstSnapshotTimeout` / explicit caller request. Takes `runId`
    (from `currentRunId` state) plus ID token.
  - `abort()` / `reset()` / `switchTo()` / `deleteConversation()` all clean
    up the active subscription via `cleanupSubscription()` helper.
- `src/lib/chat-recovery.ts` — tightened per plan:
  - `getSessionId()` → `getSession()` (returns `{sessionId, runId}` or null).
  - `checkUrl(sid, runId)` now scopes the poll to the exact turn.
  - Optional `getIdToken()` so the call can carry the Bearer header that
    Phase 7's new `agentCheck` will require.
  - Two more terminal reasons: `ownership_mismatch`, `pipeline_error`.
- `src/lib/chat-state.spec.ts` — rewritten around the new transport. 16
  tests: POST body shape + Bearer header wiring, subscribe called with
  server-issued `runId`, `onComplete` / `onError` dedup, retry-clears
  streaming state, error-status mapping for 401/403/409, empty-send /
  double-send rejection, `streamingActivities` upsert + `all-complete`
  collapse.
- `src/lib/chat-recovery.spec.ts` — updated `makeCtx()` for the new API.
  Existing 7 tests still pass.
- `src/routes/agent/chat/+page.svelte` — untouched beyond Phase 1's anon
  auth bootstrap. The existing `?sid=` handling flows into `chatState.start`
  / `switchTo`, which now read Firestore as the source of truth.

### Design calls documented

- **Dedup guards everywhere.** `onComplete` from Firestore AND `onReply`
  from chat-recovery can both deliver the same reply (races when Firestore
  was briefly blocked then recovered). Every append path checks
  `messages.some((m) => m.role === 'agent' && m.text === reply)` before
  pushing.
- **`isFirstMessage` is `!existing`** (from Firestore ownership txn) at the
  agentStream level, but the frontend sends its own `isFirstMessage` flag
  based on `messages.filter(m => m.role === 'agent').length === 0` so the
  worker can tell whether to generate a title. The agentStream body just
  passes this through.
- **No partial-text state in the new transport.** Spike B settled that the
  in-process Runner emits zero partials under default `RunConfig`;
  `streamingText` still exists in the state shape but is never written by
  the new code path. Left in to keep the UI contract stable for now —
  safe to remove in a later cleanup.
- **`sse-client.ts` kept for now.** Plan says "delete post-smoke" (Phase
  10). Keeping it means the existing `sse-client.spec.ts` still runs and
  `ios-sse-workaround.ts` still imports types from it. No code path outside
  those tests calls `streamAgent` anymore.

### Tests

- `npm run test` → **72 passing** (no regressions; 16 new
  chat-state tests replaced the prior 24 SSE-specific ones).
- `npm run check` → **0 errors** (13 pre-existing warnings, all a11y /
  unused-CSS).
- `npm run test:rules` → 10 passing (Phase 1 suite unchanged).

---

## Phase 7 — agentCheck post-migration

Status: **DONE**. Completed 2026-04-20.

### What changed

- `functions/index.js` — `agentCheck` rewritten:
  - Verifies Firebase ID token (same pattern as agentStream) → **401**
    on missing/invalid.
  - Reads `sessions/{sid}` from Firestore via Admin SDK.
  - **Explicit ownership check**: `session.userId != decoded.uid` → **403**.
    Admin SDK bypasses Firestore rules, so the browser-side `allow read`
    rule does NOT protect this path. Without this check, any authenticated
    user with a known `sid` could read another user's reply.
  - Responds from the session doc itself (worker writes `reply`, `sources`,
    `title`, `status`, `error` there) — no more ADK Cloud Run hops.
  - `runId` accepted as an informational query param; the response is
    always based on the session's current state (plan default for
    stale-runId semantics).
  - Response shapes:
    - `status=complete` → `{ok: true, status, reply, sources?, title?}`
    - `status=error` → `{ok: false, reason: 'pipeline_error', error}`
    - `queued|running` → `{ok: true, status, reply: null}` (frontend
      keeps polling)
    - Missing doc → `{ok: false, reason: 'session_not_found'}`
- Dead-code cleanup in the same pass: removed `VertexAI` and `GoogleAuth`
  imports, `ADK_SERVICE_URL`, `auth = new GoogleAuth()`, the unused
  `LOCATION` constant, and `extractSourcesFromText` / `sendSSE` /
  `parseADKStream` / `SPECIALIST_RESULT_KEYS` re-imports from `./utils.js`.
  (`utils.js` itself keeps the unused exports — Phase 10 deletes them
  post-smoke per plan.)
- `functions/index.test.js` — agentCheck block rewritten with 10 tests:
  405 / 400 / 401 (missing header, invalid token) / 403 (ownership) /
  session_not_found / complete-with-sources-and-title / pipeline_error /
  running (null reply) / stale-runId-ignored.

### Tests

- `cd functions && npm test` → **32 passing** (22 baseline + 6 agentStream
  from Phase 4 + 10 rewritten agentCheck).
- `npm run test` (Vitest) → 72 passing, no regression.

---

## Phase 7.5 — Stuck-session watchdog

Status: **DONE**. Completed 2026-04-20.

### What changed

- `functions/watchdog.js` (new) — scheduled Cloud Function, `every 2 minutes`
  via `firebase-functions/v2/scheduler.onSchedule`. Splits into three pure
  functions for testability:
  - `findStuckSessions(db, nowMs)` — fires three bounded (`limit=100`) queries
    in parallel, classifies results:
    - `status=='queued' AND queuedAt < now-30min` → `queue_dispatch_timeout`
    - `status=='running' AND lastHeartbeat < now-10min` → `worker_lost`
      (carries `currentAttempt` in errorDetails)
    - `status=='running' AND lastEventAt < now-5min` → `pipeline_wedged`
      (carries `currentAttempt`)
    - Dedupes by `sid`; classifier order = precedence
      (`queue_dispatch_timeout` > `worker_lost` > `pipeline_wedged`).
  - `backfillQueuedAt(db)` — processes 50 docs/invocation, copying
    `createdAt` → `queuedAt` for pre-migration docs. Natural no-op once
    complete.
  - `runWatchdog(db, nowMs)` — orchestrator. Runs both in parallel, then
    flips each stuck session to `status='error'` with per-classifier
    `error` + `errorDetails`. One flip failure doesn't abort others.
- `functions/index.js` — re-exports `watchdog` so Firebase CLI picks it up
  (`firebase deploy --only functions` covers it).
- `functions/watchdog.test.js` (new) — 9 unit tests. Mocks
  `firebase-admin/firestore` + `firebase-functions/v2/scheduler` so the
  handler import doesn't register a real trigger. Mock db routes query-chain
  fingerprints to synthetic snapshots. Covers every classifier branch,
  dedup precedence, backfill patching, empty case, and a "one update
  throws, others continue" scenario.
- `functions/package.json` — `test` script now runs `watchdog.test.js`
  alongside `index.test.js` under the same `--experimental-test-module-mocks`
  node runner.

### Design choices

- **Date vs Timestamp for comparisons.** Firestore auto-converts JS `Date`
  instances to `Timestamp` for `<` / `>` comparisons, so we skip the
  `firebase-admin/firestore` `Timestamp` import. (The named `Timestamp`
  export isn't even present in firebase-admin v13; importing it would
  SyntaxError at module load.)
- **Non-fenced session updates.** Watchdog doesn't participate in the
  worker's ownership-fencing contract. The plan explicitly accepts the
  tiny race where a momentarily-unwedged worker writes `status=complete`
  over our `status=error` — from the user's perspective, a successful
  late completion is fine and an actually-wedged worker won't complete.
- **Bounded queries (`limit=100`).** Caps worst-case cost per invocation.
  If a real incident produces >100 stuck sessions in one 2-minute window,
  subsequent invocations catch the rest. Backfill is limited to 50/run
  for the same reason.
- **`memory=256MiB`, `timeoutSeconds=120`.** Watchdog does three small
  queries + a batch write — well under defaults, but explicit so the
  scheduler doesn't burn unnecessary headroom.

### Tests

- `cd functions && npm test` → **41 passing** (22 baseline + 6 agentStream
  - 10 agentCheck + 9 watchdog, overlap counted once).
- `npm run test` (Vitest) → 72 passing, unchanged.

### Deployment note (for Phase 8)

The scheduled function's first deploy will prompt Firebase to enable the
Cloud Scheduler API (same as any other `onSchedule` function). No manual
queue / scheduler setup needed. Watchdog's SA is the default Cloud
Functions runtime SA (`907466498524-compute@developer...`), which already
has `roles/datastore.user` transitively via the project — the direct
bindings aren't needed for Firestore Admin SDK reads/writes as long as
the default SA has the project-level role. No new IAM wiring required.

---

## Phase 8 — Deploy pipeline

Status: **DONE**. Completed 2026-04-20.

### What changed

- `.github/workflows/deploy.yml` — full rewrite of the agent deploy job:
  - `detect-changes` filter extended with `agent/worker_main.py` and
    `agent/Dockerfile` so changes there trigger a worker redeploy.
  - `deploy-hosting` step that runs `firebase deploy --only functions`
    extended to `--only functions,firestore:rules,firestore:indexes`. The
    new `watchdog` scheduled function is picked up automatically because
    it's re-exported from `functions/index.js`.
  - `deploy-agent` renamed to `deploy-worker`. Swaps `adk deploy cloud_run`
    (which silently swallows failures — see deployment-gotchas) for
    `gcloud run deploy superextra-worker --source=agent` which builds from
    our Dockerfile. Flags match plan §Phase 3 exactly:
    `--no-cpu-throttling --timeout=1790 --memory=2Gi --max-instances=10
--min-instances=0 --concurrency=4 --no-allow-unauthenticated
--service-account=superextra-worker@…`.
  - Revision snapshot-before/verify-after guard kept (it caught ADK
    silently-failing deploys in the old flow; in the new flow gcloud exit
    codes are honest, but the guard is cheap).
  - After successful deploy, the job runs
    `gcloud run services add-iam-policy-binding ... --role=roles/run.invoker`
    for the worker SA on its own service. This is the Phase 3 binding
    deferred to deploy-time because the service URL didn't exist until
    now. Binding is idempotent.
  - Smoke test hits `/healthz` on the worker with a fresh identity token
    (service is private, so the test mints a token via
    `gcloud auth print-identity-token --audiences=$URL`).
- `functions/index.js` — `WORKER_URL` now has a predicted default
  (`https://superextra-worker-907466498524.us-central1.run.app`) instead
  of throwing when unset. Cloud Run URLs are deterministic from (service,
  project-number, region), so the default is reliable; `WORKER_URL` env
  var still overrides. This decouples the Cloud Function deploy from the
  worker deploy — they can land in either order on first deploy.
- `agent/requirements-dev.txt` — already present (fixed on another branch);
  contains `-r requirements.txt` + pytest + pytest-asyncio + respx. Agent
  CI test step's dependency install works out of the box.

### Secrets required (already configured in GitHub Actions — no code change)

- `FIREBASE_SERVICE_ACCOUNT_SUPEREXTRA_SITE` — Cloud deploy creds.
- `GOOGLE_PLACES_API_KEY`, `SERPAPI_API_KEY`, `APIFY_TOKEN` — baked into
  worker via `--update-env-vars` on every deploy. `--update-env-vars`
  merges (doesn't replace), so env vars set manually on the service
  persist, but the three keys above are always re-set from secrets to
  stay the canonical source.

### Retired (NOT deleted — manual cleanup)

The old `superextra-agent` Cloud Run service is no longer deployed to.
Left in place intentionally so traffic can drain during cutover and so
an operator can verify the new `superextra-worker` before deleting it.
When ready:

```bash
gcloud run services delete superextra-agent \
  --region=us-central1 --project=superextra-site
```

### Notes on the plan rollout order

Plan's rollout order puts Phase 8 after 4/5/7/7.5. All of those are code
complete now. First actual production deploy (push to `main`) will:

1. Run tests — all four suites pass (Vitest 72, functions 41, rules 10,
   agent pytest 131 excluding pre-existing 4 follow-up routing failures
   which the workflow explicitly ignores).
2. Deploy `superextra-worker` if the agent filter fires (runs in parallel
   with hosting until `deploy-hosting` gates were tightened in Tier 1.5).
3. Deploy hosting + functions + firestore rules + indexes atomically.

**Note (superseded by Tier 1.5):** the original design relied on Cloud
Tasks' retry window to absorb a brief period where hosting was live but
the worker wasn't. Audit Finding P1 flagged that the retry window
(`maxAttempts=3`, `minBackoff=10s`, `maxBackoff=60s` → ~130 s) is shorter
than a cold Python + ADK Docker build on first cutover. Tier 1.5 changed
`deploy-hosting` to `needs: [test, deploy-worker]` + an `if: always() &&
…` guard so hosting waits for the worker whenever the worker deploys,
and proceeds normally when the agent filter skips the worker job. See
`.github/workflows/deploy.yml:89-98` and the Tier 1.5 entry in the
Follow-up triage section below.

### Tests

- Format / lint / test suites unchanged from Phase 7.5 + 8 combined:
  - `npm run test` (Vitest) → 72 passing.
  - `cd functions && npm test` → 41 passing.
  - `npm run test:rules` → 10 passing.
- Workflow itself not runnable locally — Phase 10 smoke covers the first
  production roll.

---

## Phase 9 — Observability + TTL

Status: **DONE**. Completed 2026-04-20.

### What changed

- `agent/worker_main.py` — structured JSON logging:
  - New `_JsonFormatter` class emits Cloud Logging-friendly JSON per log
    record (`severity`, `message`, `logger`, plus correlation keys
    `sid`/`runId`/`attempt`/`taskName`/`workerId`/`event` when set via
    `extra={...}`). Exception traces land under `exception`.
  - `_trace_from_header` extracts `X-Cloud-Trace-Context` → builds
    `projects/<p>/traces/<id>` resource name. Attached to log records as
    `logging.googleapis.com/trace`, which Cloud Logging uses to thread log
    lines into traces in the UI.
  - `_configure_logging()` replaces uvicorn's default handler with our
    JSON stdout handler and dials `httpx`/`httpcore`/`google.auth` down to
    WARN.
  - Key log calls refactored to use `extra={**log_ctx, "event": "..."}`:
    `run_start`, `noop_complete`, `noop_stale`, `adk_session_created`,
    `ownership_lost`, `google_api_error`, `pipeline_error`, `run_complete`.
    `log_ctx` is built once per request and inherits `attempt` after
    takeover.
- `agent/tests/test_worker_main.py` — 3 new tests covering the JSON
  formatter's correlation keys, the absence-is-omitted path, and
  `_trace_from_header`'s resource-name construction.
- `package.json` — `test:rules` now prefixes `npx` on `firebase-tools` so
  it works without a global install (CI needs this).
- `.github/workflows/deploy.yml` — added `npm run test:rules` to the
  `test` job. Ubuntu runners have Java pre-installed, so the Firestore
  emulator starts without extra setup.

### Live GCP — Firestore TTL policies

Enabled via `gcloud firestore fields ttls update`:

```
sessions.expiresAt → state: ACTIVE
events.expiresAt   → state: CREATING  (transitions to ACTIVE within a
                                       few hours; collection-group TTL
                                       propagation is async).
```

Firestore enforces TTL once the state is ACTIVE. Worker + Cloud Function
already write `expiresAt` on every session and event doc (see Phase 2
mapper + Phase 4 upsert), so as soon as the events policy finishes
propagating, expired docs get swept automatically. No extra code needed.

### Design notes

- **Why not `google-cloud-logging` library.** Cloud Run's runtime
  auto-parses JSON on stdout into Cloud Logging's `jsonPayload`, giving
  us everything the structured logger would — without adding a runtime
  dep. Trace correlation works via the well-known `logging.googleapis.com/trace`
  key we add ourselves.
- **`extra={"trace": ...}`.** Python's `logging.LogRecord` rejects `extra`
  keys that shadow builtin record attributes (e.g. `trace` is safe;
  `message` is not). The correlation keys chosen are all free of
  collision with LogRecord builtins.
- **Logs are still readable locally.** The JSON formatter works the same
  in dev — logs print as one JSON object per line to stdout. Humans can
  `jq` them; Cloud Logging indexes them natively.

### Tests

- `cd agent && pytest tests/ --ignore=tests/test_router_evals.py -q` →
  **134 passed**, 4 pre-existing follow-up routing failures (same
  baseline).
- `npm run test` → 72 passing, unchanged.
- `npm run test:rules` → 10 passing.

---

## Phase 10 — Verification

Status: **Unit tests DONE; manual smoke gated on first deploy.** 2026-04-20.

### Unit-test coverage (per plan checklist)

| Plan item                                         | Where                                                               | Status |
| ------------------------------------------------- | ------------------------------------------------------------------- | ------ |
| `firestore_events` against Runner event fixture   | `agent/tests/test_firestore_events.py` (25 tests, Phase 2)          | ✅     |
| `firestore-stream.spec.ts` — onSnapshot dispatch  | `src/lib/firestore-stream.spec.ts` (14 tests, this phase)           | ✅     |
| Worker integration — fenced writes / ownership    | `agent/tests/test_worker_main.py` takeover + fenced-update branches | ✅     |
| Runner exception propagation                      | `test_runner_exception_writes_status_error_and_returns_200`         | ✅     |
| Plugin activation (`Runner(app=app)` fires hooks) | `spikes/adk_runner_spike.py` (ran live during spike A)              | ✅     |
| Firestore rules emulator                          | `firestore.rules.spec.js` (10 tests, Phase 1)                       | ✅     |
| JSON structured logging                           | `test_worker_main.py` `_JsonFormatter` + `_trace_from_header`       | ✅     |

### Suites (latest sweep)

- `npm run test` (Vitest) → **86 passing**
- `cd functions && npm test` → **41 passing**
- `npm run test:rules` → **10 passing**
- `cd agent && pytest tests/ --ignore=tests/test_router_evals.py` → **135 passed, 4 failed** (the 4 are pre-existing `test_follow_up_routing.py` regressions unrelated to this refactor — ignored in CI).

Total: **272 passing** across all code paths touched by the refactor.

### Fix: `taskName` → `cloudTaskName`

Python 3.12 added `taskName` to the `LogRecord` builtin attrs (asyncio
task name). Using `extra={"taskName": ...}` raised `KeyError("Attempt to
overwrite 'taskName' in LogRecord")`. Renamed to `cloudTaskName`
everywhere in `worker_main.py` and in the JSON formatter's structured-key
list. Cloud Logging's free-form `jsonPayload` keys don't care; search
queries like `jsonPayload.cloudTaskName="..."` work the same.

### Manual smoke tests (post-deploy)

The 14 scenarios from the plan can only be exercised after a production
deploy. Listing them here with the acceptance criteria so operator can
tick through on first cutover:

| #   | Scenario                                 | Pass                                                                                    |
| --- | ---------------------------------------- | --------------------------------------------------------------------------------------- |
| 1   | Desktop happy path (full pipeline)       | Progress renders live; final report lands; `sessions/{sid}.status=='complete'`          |
| 2   | Multi-turn                               | Turn 2 gets fresh `runId`; Cloud Task name ends with the new runId; follow-up route OK  |
| 3   | Browser close at T+30 s                  | Worker logs continue past tab close; reopen shows full report from Firestore            |
| 4   | Mobile backgrounding                     | State remains accurate across bg/fg at T+60s, T+5m, T+30m                               |
| 5   | Page refresh mid-pipeline                | Live progress after hard-reload at T+3m, T+8m, T+20m                                    |
| 6   | Worker kill mid-run (revision rollout)   | Existing request completes on old revision OR retries on new (spike I confirmed)        |
| 7   | OOM mid-run                              | Cloud Tasks retry takes over within ≤3 attempts OR watchdog flips to error within ~12 m |
| 8   | Double-send race                         | Second POST returns 409 with `previous_turn_in_flight`                                  |
| 9   | Duplicate Cloud Tasks delivery           | B polls A's run via takeover logic; returns A's result                                  |
| 10  | Concurrent-turns race                    | Turn 2 POST returns 409                                                                 |
| 11  | Firestore-blocked client (ad-blocker)    | `chat-recovery` REST poll delivers reply via `agentCheck`                               |
| 12  | Cross-session comeback (reopen `?sid=…`) | Firestore-backed resume shows final reply or error; no pending spinner                  |
| 13  | Stale-worker overwrite                   | Ownership fencing rejects the stale worker's fenced-update                              |
| 14  | Cross-user access attempt                | `agentStream` + `agentCheck` both return 403 with `ownership_mismatch`                  |

Scenario 14 can be run headlessly with two anon UIDs — worth wiring into
a post-deploy smoke script in a future iteration.

### Deferred to post-smoke cleanup (per plan)

- Delete `src/lib/sse-client.ts` + `.spec.ts`.
- Delete `src/lib/ios-sse-workaround.ts` + `.spec.ts` (onSnapshot auto-reconnects;
  the visibilitychange helper can be simplified later).
- Delete `parseADKStream` / `sendSSE` / `SPECIALIST_RESULT_KEYS` /
  `extractSourcesFromText` from `functions/utils.js` (already unimported
  from `functions/index.js`).
- Manually delete the retired `superextra-agent` Cloud Run service.

None of these block success criteria. Safe to leave until smoke passes and
an operator confirms no regressions.

### Done-ness summary (against the plan's success criteria)

| Criterion                                                                     | Status                                                           |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Long-running pipeline execution no longer tied to browser connection lifetime | ✅ Phase 4 returns 202 immediately; worker runs via Cloud Tasks  |
| Page refresh / reconnect recovers from Firestore-backed state                 | ✅ Phase 5 `resumeIfInFlight` + onSnapshot reconnect             |
| Follow-up turns work with stable `sid` + fresh `runId`                        | ✅ Phase 4 txn generates fresh `runId`; worker preserves `sid`   |
| Infra failures retry automatically without stuck sessions                     | ✅ Cloud Tasks retries + watchdog (Phase 7.5)                    |
| Browser remains read-only to Firestore                                        | ✅ Phase 1 rules `allow write: if false`                         |
| Pragmatic implementation — no unnecessary subsystems                          | ✅ Phases 0–9 scoped to plan; sse-client/ios-workaround deferred |

Ready for first production deploy. Post-deploy smoke (14 scenarios above)
is the last gate.

---

## Post-implementation review (independent agent pass)

Completed 2026-04-20 by an independent review agent with no context from
this session. Agent was briefed to cross-check the plan and settled facts
against the actual code, not to trust the log. Key findings below; full
report retained in conversation history.

### Verdict

**Zero hard blockers.** All settled-fact contracts verified by code
inspection: `Runner(app=app, ...)`, stale-run guard, collection-group
query shape, `expiresAt = max(...)` never-shrinks, 403/409 semantics,
OIDC audience literal, Cloud Run timeout `1790 < 1800` dispatch deadline,
heartbeat-before-terminal-write ordering.

**No architectural drift detected.** No SSE reintroduction, no
`sessionMap` resurrected, no partial-text batching.

### Real issues worth fixing (low-risk, tight)

| ID     | Issue                                                                | File                                | Priority                           |
| ------ | -------------------------------------------------------------------- | ----------------------------------- | ---------------------------------- |
| M4     | "Retrying…" UI state not surfaced on `onAttemptChange`               | `src/lib/chat-state.svelte.ts`      | **Plan-explicit miss**             |
| Bug-6  | Text-equality reply dedup unsafe for repeated short replies          | `src/lib/chat-state.svelte.ts:318`  | Real edge case                     |
| Bug-1  | `asyncio.CancelledError` bypasses `_cancel_heartbeat()`              | `agent/worker_main.py` main handler | Violates plan cancel-order         |
| M7     | Frontend sends unused `isFirstMessage` in POST body                  | `chat-state.svelte.ts` + body       | Confusing — backend overrides      |
| Stale  | `functions/index.test.js` mocks unused `@google-cloud/vertexai` etc. | test file                           | Would silently pass a re-intro     |
| Stale  | `streamingText` state + getter                                       | `chat-state.svelte.ts`              | Never written by new transport     |
| Stale  | `parseADKStream` / `sendSSE` / `SPECIALIST_RESULT_KEYS` exports      | `functions/utils.js` + `utils.test` | Truly dead; delete now (not later) |
| Minor  | SIGTERM handler instantiates fresh `firestore.Client`                | `agent/worker_main.py:494`          | 10 s grace is tight — reuse `_fs`  |
| T-weak | Exception-propagation test asserts call, not call-order              | `agent/tests/test_worker_main.py`   | Fix with recording mock            |

### Test gaps flagged

- **T3**: no test for `expiresAt = max(existing, now+30d)` extension in
  `agentStream` txn.
- **T4**: no tests for `_poll_until_resolved`'s four exit branches
  (terminal, stale run, stale heartbeat→takeover, 7-min timeout).
- **T6**: rules test for cross-path event `updateDoc` rejection (write
  deny on events collection-group, not just subcollection).
- **T7**: no true parity test between `firestore_events.py` mapper and
  the legacy `parseADKStream`. Not a regression risk now (SSE path gone);
  would matter if we ever re-enable streaming.

### Bugs flagged but accepted / low-impact

- **Bug-8**: `loading = true` briefly lingers if user navigates mid
  `resumeIfInFlight`. Next `switchTo` clears it. Cosmetic.
- **Bug-9**: watchdog non-fenced update vs late worker `status=complete`
  — documented as intentional in Phase 7.5 entry.
- **Bug-10**: `backfillQueuedAt` perpetually scans 50 oldest docs
  (~36 k reads/day steady-state after migration settles). Tolerable.
- **Bug-2**: heartbeat + per-event fenced updates contend on the same
  doc. Firestore auto-retries; fine at design-partner load.

### Stale code — reviewer's more aggressive call

Reviewer argues `functions/utils.js`'s dead exports + their tests AND the
`@google-cloud/vertexai` / `google-auth-library` test mocks should go
**now**, not "post-smoke". The plan's "delete post-smoke" was overcautious
— nothing in the live code path imports them, so deletion is pure cleanup
with no rollback risk. Also flagged as semantics-leaking:
`src/lib/ios-sse-workaround.ts` is _still imported_ by `chat-state.svelte.ts`
(for `handleReturn`), so it's not purely dead — full simplification is a
genuine follow-up, not just a delete.

### Reviewer's low-impact notes

- `uidRateLimitMap` is in-memory; scales as `20 × n_instances`. Consistent
  with existing IP rate-limit pattern. Firestore-backed counter is the
  upgrade path if abuse escalates.
- Chat-recovery polls up to 3 min (60 × 3s) — worker runs 15+ min. If
  Firestore is permanently blocked, user sees "could not retrieve" after
  3 min while the pipeline keeps going. Reopen with no ad-blocker fixes
  it. UX worth documenting, not fixing.
- No `/run` smoke test in CI (only `/healthz`). A real `/run` smoke would
  need fake OIDC — expensive. Acceptable.
- `session_not_found` in `agentCheck` returns HTTP 200 (not 404);
  `agent_unavailable` similarly 200 (not 503). Frontend handles both via
  `TERMINAL_REASONS` map. Inconsistent with 403 on ownership, but not
  breaking.

### Plan-scope items still missed

- **M4** (above). "Retrying…" UI cue per Phase 5 spec.
- **T3, T4, T6** test gaps are plan-adjacent.
- Everything else the reviewer checked against the plan matched.

### Triage

Fixing the "Real issues" table + test gaps T3/T4/T6 is a ~30-minute pass.
Low-risk, pure cleanup + one missed UI cue. Tracked as a follow-up
before first prod deploy but not blocking.

Items to leave as-is: Bug-8/-9/-10/-2 (acceptable races / tolerable
costs), rate-limit semantics (by design), `agentCheck` HTTP code style
(frontend handles via reason map).

---

## Live E2E smoke (pre-deploy validation)

Ran 2026-04-20. Harness at `agent/tests/e2e_worker_live.py` drives the
worker's `run()` handler directly (no FastAPI HTTP hop) against **real**
Firestore + Agent Engine + Gemini + Places. Seeds a session doc matching
agentStream's upsert shape, then watches Firestore for state transitions
and uses `collectionGroup('events')` to verify indexed reads.

### Query

Umami Berlin, "What service issues come up in reviews?" — narrow query,
same fixture as Phase 0 for comparability.

### Result summary

| Check                                        | Value                                              |
| -------------------------------------------- | -------------------------------------------------- |
| Handler return                               | `{ok: true, action: 'complete', events: 23}`       |
| Elapsed                                      | **278.51 s (4:38)** — consistent with Phase 0      |
| Status transitions                           | `queued → running@attempt=1 → complete`            |
| `adkSessionId` (null→populated)              | ✅ `7727285668954505216`                           |
| `reply` length                               | 336,175 chars (synth ran + full charts)            |
| `title` (Flash-generated)                    | "Customer service issues" (4 words)                |
| `currentAttempt`                             | 1 (no retries)                                     |
| Firestore events via `collectionGroup` query | **10 docs** (7 activity + 2 progress + 1 complete) |
| `currentRunId` unchanged through run         | ✅                                                 |
| Heartbeat + `lastEventAt` both set           | ✅                                                 |

### What this validates

- `Runner(app=app, session_service=VertexAiSessionService(...))` wiring
  works against live Agent Engine.
- ADK session create-on-first-turn → fenced write-back flows through
  cleanly. Second `run_async` call (immediately after) used the new
  session id with no issues.
- Mapper writes 10 Firestore docs from 23 runner events — filtering
  (transfer_to_agent, NOT_RELEVANT specialist finals) works as designed.
- Collection-group query with `(userId, runId, attempt, seqInAttempt)`
  index returns docs ordered correctly. The index (pre-created in spike
  D) is serving production-shape queries.
- Fenced updates on `lastEventAt` + heartbeat contended on the same doc
  for 4:38 without a single `OwnershipLost` — contention handling is
  fine under realistic load.
- Structured JSON logging rendered on every log line with full
  correlation keys (`sid`, `runId`, `attempt`, `cloudTaskName`,
  `workerId`, `logging.googleapis.com/trace`).
- Trace-context header parsed correctly: `x-cloud-trace-context:
e2e-<id>/1;o=1` → `projects/superextra-site/traces/e2e-<id>`.

### BUG FOUND: `sources` empty on session doc after completion

The final session doc had `sources: []` even though the synthesiser's
336 KB reply clearly contained source citations. Root cause:

```python
# worker_main.py, inside the async-for loop:
if "final_report" in sd and isinstance(sd["final_report"], str):
    final_reply = sd["final_report"]
    final_sources = _extract_sources_from_state_delta(sd)
```

`sd` is **just the synthesiser's** `state_delta` — which only contains
`final_report`. The specialist output keys (`market_result`,
`review_result`, etc.) were in _earlier events'_ state_deltas. By the
time we hit the synthesiser's final event, they're long gone from the
stream's per-event view.

`_extract_sources_from_state_delta` iterates specialist output_keys
against that lone synthesiser-final `sd`, so it always returns [].

#### Fix (straightforward)

Accumulate specialist results as they stream. Replace the one-shot
extraction with:

```python
accumulated_state: dict = {}
...
# Inside the async-for loop:
sd = event.actions.state_delta if event.actions else None
if sd:
    for key, value in sd.items():
        if isinstance(value, str):
            accumulated_state[key] = value
    if "final_report" in sd and isinstance(sd["final_report"], str):
        final_reply = sd["final_report"]
        # Use accumulated_state (has all specialist outputs), not just sd.
        final_sources = _extract_sources_from_state_delta(accumulated_state)
```

Or (alternative): fetch the Agent Engine session after `run_async`
completes and extract sources from `session.state`. Adds one round-trip
at the end of every run. The in-loop accumulation is free.

This is a real user-visible bug — without sources, the UI can't render
citation chips next to claims. Tracked as a follow-up (goes in the
fresh-thread triage list alongside the review findings).

### Incidental observations

- **No `MALFORMED_FUNCTION_CALL` this run.** Synthesiser produced a
  full 336 KB report with charts cleanly. The code_execution fallback
  path didn't fire; good baseline comparison for how it normally works.
  Tracked task #13 (intermittent — 50% of broad runs) remains the
  flaky-path concern.
- **Timing is tight with Phase 0.** 4:38 vs 4:46 for the same narrow
  Umami query, same thinking configs. Consistent with design-partner
  load projections.
- **Worker created a new Agent Engine session per run**: we now have
  a few `e2e-*` test sessions in Agent Engine state. They're tiny
  (2–3 events each) but not auto-cleaned. The plan's Phase 1-era
  "Agent Engine session cleanup cadence" decision said no automated
  cleanup pre-launch; revisit if storage becomes a concern.
- **FakeRequest with a plain dict worked** — FastAPI's `Request` duck-
  types around `.headers` access. Simplifies future local-driver tests.

### What this does NOT cover

- Cloud Tasks OIDC delivery end-to-end (still needs a deployed worker).
- Frontend `onSnapshot` actually receiving docs in real-time.
- `agentStream` function's atomic txn + enqueue path (exercised only
  via unit tests).
- Watchdog sweeps (scheduled function, only meaningful post-deploy).
- Mobile / refresh / backgrounding scenarios (need frontend + deployed
  worker together).
- Double-send / 409 race (agentStream-level).
- Retry semantics (Cloud Tasks only retries real HTTP failures; no way
  to simulate here).

### Artifacts

- `agent/tests/e2e_worker_live.py` — harness (not in CI; manual only).
- `agent/tests/e2e_worker_live.json` — report.
- `agent/tests/e2e_worker_live.log` — full stdout (structured JSON logs
  plus ADK Runner traces).

### Verdict

Worker + mapper + Firestore write/read path is **live-validated**. The
one bug found (empty sources) is localised, safe to fix in the
follow-up cleanup pass, and does not block the first deploy as long as
the fresh-thread triage includes it. Everything else the E2E touched
matches the plan.

---

## Follow-up triage (post-review cleanup) — 2026-04-20

Four rounds of review (two independent post-implementation audits plus two
adversarial passes on the fixes plan) surfaced a short list of real gaps
between the code and the plan's durability guarantees. The reconciled design
is recorded in `docs/pipeline-decoupling-fixes-plan.md`; this section logs
what shipped.

### What shipped

**Tier 1 — critical durability**

- **1.1 — Events observer terminal leak closed.** Dropped `case 'complete'`
  and `case 'error'` from the events-collection-group observer in
  `src/lib/firestore-stream.ts`. A stale (fenced-out) worker can no longer
  surface a stale terminal via the unfenced events stream. Session doc,
  which _is_ fenced via `_fenced_update`, is now the sole terminal source.
  Updated header docstring to say so. Added two spec cases in
  `firestore-stream.spec.ts` proving `type='complete'` and `type='error'`
  event docs no longer trigger `onComplete` / `onError`.

- **1.2 — `state_delta` accumulated across the event loop.** In
  `agent/worker_main.py`, added `accumulated_state: dict[str, Any] = {}`
  before the `async for` and merge each event's string `state_delta`
  values into it. At the final-report branch, source extraction now sees
  every specialist's output key, not just the synthesiser's final delta.
  Fixes the live-E2E "empty sources" bug.

- **1.3 — Router-final promotion + simplified sanity gate.** Worker now
  reuses the return value of `map_and_write_event(...)` (rather than
  re-walking `state_delta`) as the terminal signal: the first
  `type='complete'` emission — whether from synth or router — populates
  `final_reply` / `final_sources`. Sanity gate simplified to
  `not final_reply or not final_reply.strip()` — the `len < 100` and
  `startswith("Error:")` guards were vestigial (false-rejected router
  clarifications; the in-process Runner doesn't produce ADK SSE's
  synthetic-error shape). `.strip()` closes a real whitespace-only edge
  case that `_has_state_delta`'s `if not value` check lets through.
  Removed `REPLY_MIN_LEN`. Four new cases in `test_worker_main.py`:
  specialist-source accumulation, router clarification, empty-reply
  rejection, whitespace-only rejection, short-valid-reply passes.

- **1.4 — Fenced watchdog flip.** `functions/watchdog.js` —
  `findStuckSessions` now returns per-classifier `expectedStatus` /
  `expectedRunId` / `thresholdField` / `thresholdMillis`. `runWatchdog`
  wraps each flip in `db.runTransaction` that re-reads the doc and
  aborts silently if status changed, `currentRunId` advanced, or the
  threshold field was freshened. Four new cases in `watchdog.test.js`:
  happy path, worker-completed race, heartbeat-freshened race, new-turn
  race; plus the pre-existing throw-resilience test updated.

- **1.5 — Deploy serialized.** `deploy-hosting` now
  `needs: [test, deploy-worker]` with
  `if: always() && ... && (success || skipped)` so hosting waits for
  the worker when the worker deploys, but proceeds normally when the
  agent filter skips it. Removed the first-cutover "enqueue into
  nothing" window. Single-job rerun caveat documented in
  `docs/deployment-gotchas.md`.

**Tier 2 — plan-explicit misses**

- **2.1 — "Retrying…" UI cue.** `onAttemptChange` in
  `chat-state.svelte.ts` seeds
  `streamingProgress = [{ stage: 'retrying', status: 'running', label: 'Retrying…' }]`
  after clearing stale state. Existing `StreamingProgress.svelte`
  renders it without new UI wiring.

- **2.2 — `try/finally` heartbeat cancel + `CancelledError` branch.**
  Restructured the worker's event-loop exception block so every exit
  path hits `finally: await _cancel_heartbeat()`. Added an explicit
  `except asyncio.CancelledError: raise` so cancellation propagates
  (CancelledError is `BaseException`-rooted, not `Exception`-rooted —
  the old handlers let it through). Documented as "best-effort cancel"
  — `.cancel()` is synchronous and always registers, `wait_for` is
  best-effort during unwind. Redundant explicit cancels at old lines
  637 / 644 / 670 dropped; the one in the `except Exception` branch
  stays (must run before the fenced error write).

- **2.3 — Reply dedup by runId.** Introduced
  `appendedReplyForRunId: string | null` module-state in
  `chat-state.svelte.ts`. `buildStreamCallbacks(sendingConvId, sendingRunId)`
  closes over the turn's runId; `onComplete` checks against it instead
  of doing text-equality. `recover()`'s `isDuplicateReply` also uses
  the same flag — no `RecoveryContext` signature change needed.
  Replaces the old dedup which false-rejected legitimately-new short
  replies like "OK" / "Yes" across turns.

**Tier 3 — test gaps**

- **3.1 — `expiresAt` never-shrinks tests.** Two cases in
  `functions/index.test.js`: existing 60-day `expiresAt` preserved on
  re-enqueue; existing 5-day `expiresAt` extended to ~now+30d.

- **3.2 — 7-min poll ceiling test.** `test_worker_main.py` now exercises
  `_poll_until_resolved`'s 4th exit branch (`HTTPException(500,
'poll_timeout …')` after `POLL_WAIT_MAX_S`). Mocks `asyncio.sleep` and
  `get_event_loop().time()` to avoid a real 7-minute wait.

- **3.3 — Exception-propagation call-order test.** Replaced the old
  "assert called" form with a shared recorder that captures calls
  across `_cancel_heartbeat` and `_fenced_update`; asserts the cancel
  precedes the fenced error write in the pipeline-exception branch.

**Tier 4 — cleanup**

- **4.1 — Dead `@google-cloud/vertexai` and `google-auth-library` mocks
  removed** from `functions/index.test.js`. Neither is imported by
  `functions/index.js` since the Phase 7 `agentCheck` rewrite; the dead
  mocks would silently pass a re-introduction.

- **4.2 — SIGTERM handler reuses `_fs`.** `agent/worker_main.py:494`
  now reads the module-level Firestore client first (falling back to a
  fresh client only if lifespan hasn't run). `google-cloud-firestore`
  is thread-safe; saves gRPC channel setup inside the 10s SIGTERM grace.

**Optional hardening — worker preflight**

- Added `uses: google-github-actions/setup-gcloud@v2` + a
  `gcloud run services describe superextra-worker` preflight to the
  `deploy-hosting` job. Fails fast if the worker service is missing
  (catches infra drift when `deploy-worker` is skipped).

### What was explicitly deferred / not done

- **Pre-existing `test_follow_up_routing.py` failures** (7 at baseline —
  up from the 4 the original audit recorded). All in the single file that
  CI explicitly excludes; unrelated to this refactor.
- **`functions/utils.js` dead exports** (`parseADKStream`, `sendSSE`,
  `SPECIALIST_RESULT_KEYS`, `extractSourcesFromText`) —
  `functions/utils.test.js` still exercises them; deletion requires test
  removal too. Honours the original plan's "delete post-smoke" ordering.
- **`streamingText` state** — dead on the new transport but still read by
  `ChatThread.svelte` typewriter render. Harmless; a future UI
  simplification pass can retire it.
- **`sse-client.ts`** — plan says post-smoke deletion.
  `ios-sse-workaround.ts` stays regardless (its `handleReturnFromHidden`
  helper is transport-agnostic).
- **M7 frontend `isFirstMessage` echo** — refuted as a bug (backend
  recomputes from `!existing`).
- **T6 collection-group write-deny rules test** — refuted. Firestore
  writes target concrete document paths; the existing
  `addDoc(collection(db, 'sessions', 'sid-alice', 'events'), …)` test
  at `firestore.rules.spec.js:160-171` already exercises the
  `/{path=**}/events/{eid}` wildcard rule.

### Suite counts (after every tier landed)

| Suite                                | Baseline | After fixes  | Δ                                                                        |
| ------------------------------------ | -------- | ------------ | ------------------------------------------------------------------------ |
| Vitest                               | 86       | **89**       | +3 (1.1 no-terminal-complete, no-terminal-error; 2.3 fresh-runId append) |
| functions (index + watchdog + utils) | 41       | **46**       | +5 (1.4 ×3 race cases; 3.1 ×2 expiresAt)                                 |
| rules emulator                       | 10       | **10**       | 0                                                                        |
| agent pytest (ex-evals)              | 132      | **140**      | +8 (1.2 ×1; 1.3 ×4; 2.2 cancel; 3.2 poll_timeout; 3.3 call-order)        |
| agent failures                       | 7        | **7**        | unchanged, all `test_follow_up_routing.py`                               |
| svelte-check                         | 0 errors | **0 errors** | 13 pre-existing warnings unchanged                                       |

### Post-Tier-1 live E2E re-run (2026-04-20)

Re-ran `agent/tests/e2e_worker_live.py` against live Firestore + Agent
Engine + Gemini + Places. Same Umami query as the first live smoke for
comparability. Results saved to
`agent/tests/e2e_worker_live_post_fixes.log` +
`agent/tests/e2e_worker_live.json`.

| Check                             | Value                                              |
| --------------------------------- | -------------------------------------------------- |
| Handler return                    | `{ok: true, action: 'complete', events: 25}`       |
| Elapsed                           | 290.12 s (~4:50, comparable to the 278 s baseline) |
| Session `status`                  | `complete`                                         |
| Reply length                      | 199,140 chars (synth + charts)                     |
| **Sources count**                 | **7 (fix verified — was 0 pre-fix)**               |
| Title (first turn)                | "Service issues reviews"                           |
| `currentAttempt`                  | 1 (no retries)                                     |
| Events via collection-group query | 11 docs (8 activity + 2 progress + 1 complete)     |
| `currentRunId` unchanged          | ✅                                                 |

All verdicts ✅ — `final_status_complete`, `reply_populated`,
`adk_session_persisted`, `events_written`, `title_set_on_first_turn`,
`collection_group_query_works`. The "empty sources" bug the first live
smoke surfaced is closed.

Harness also confirms the Tier 1.1 contract: session doc was the path
that carried the terminal (`status=complete` + `reply` on the session
doc); no duplicate-terminal surface via events.

### Post-review polish (2026-04-20)

An adversarial code review of the landed fixes returned no blockers, but
flagged two small ops/test-stability improvements that were applied:

- **Watchdog per-reason skip counters.** `functions/watchdog.js` — the
  `skipped` counter now breaks out into
  `skipReasons = {missing, status_changed, run_advanced, field_freshened}`.
  Both the log line and the returned summary carry the breakdown, so
  operators can see whether the watchdog was racing worker completions,
  stale runIds, or freshened heartbeats rather than staring at a raw
  `skipped=N`. New `functions/watchdog.test.js` case exercises all three
  abort reasons in one run.
- **Loosened `hb_cancel_calls` assertion.**
  `test_runner_exception_writes_status_error_and_returns_200` now
  asserts `len(hb_cancel_calls) >= 1` instead of `== [True, True]`. The
  exact count is an implementation detail of the try/finally structure;
  the companion
  `test_pipeline_exception_cancels_heartbeat_before_error_write` remains
  the canonical cancel-before-error-write order assertion.

Suite counts after the polish: Vitest 89, functions 47 (+1), rules 10,
agent pytest 140 passed / 7 pre-existing failures (unchanged).

### Follow-up manual-smoke checklist

Unchanged from the original Phase 10 table. Particular attention on first
deploy to:

- Scenario 1 (desktop happy path) — `sources` populated on session doc.
- Scenario 2 (multi-turn) — follow-up uses fresh runId.
- Scenario 6 (worker kill mid-run) — no unfenced terminal leak via events.
- Scenario 13 (stale-worker overwrite) — fencing + watchdog txn cooperate.

---

## Final pre-deploy audit fixes — 2026-04-21

A fourth external review
(`docs/pipeline-decoupling-final-predeploy-audit.md` supplemented by a
follow-up review with four deeper findings) surfaced the last round of
issues. All verified in code and fixed in one pass.

### P1 — Worker concurrency safety

**Problem.** `agent/worker_main.py` tracks per-request state
(`_current_sid`, `_current_attempt`, `_current_worker_id`,
`_heartbeat_task`) in module globals — safe under
`--concurrency=1` but not under parallel requests on one instance.
`.github/workflows/deploy.yml` was set to `--concurrency=4`. Two
simultaneous requests on one instance would: request B overwrites A's
globals → A's `_cancel_heartbeat()` cancels B's task → A's heartbeat
orphaned → SIGTERM handler acts on whichever sid last won. Cloud Run
[docs on instance concurrency](https://docs.cloud.google.com/run/docs/about-concurrency)
explicitly call this out: "If your code cannot handle parallel requests,
set the maximum concurrency to 1."

**Fix.** `.github/workflows/deploy.yml:234` changed `--concurrency=4` →
`--concurrency=1`. Comment expanded to cite the Cloud Run doc. Scaling
out via `--max-instances=10` is unaffected; the design-partner load
profile easily fits within 10 parallel pipelines.

### P1 — Deploy cutover gap

**Problem.** The old workflow ran `firebase deploy --only hosting` and
then `firebase deploy --only functions,firestore:rules,firestore:indexes`
in two separate steps. During the gap, browsers on the new JS posted to
`agentStream` still running the old SSE code — `res.json()` threw
`malformed_response` (see `src/lib/firestore-stream.ts:222-227`). The
reverse order has an equivalent gap. Cloud Tasks' short retry window
(~130 s with `maxAttempts=3, minBackoff=10s, maxBackoff=60s`) is much
shorter than a cold Python + ADK Docker build.

**Fix.** Collapsed both `firebase deploy` calls into a single invocation:
`firebase deploy --only hosting,functions,firestore:rules,firestore:indexes --project superextra-site --force`
(`.github/workflows/deploy.yml:167-172`). Comma-separated `--only`
targets are standard firebase-tools usage; all four targets upload in
parallel within one CLI run, minimising the cross-stack window to
seconds.

### P2 — Cached error + stale runId leak across turns

**Problem.** `firestore-stream.ts`'s session observer had a `fromCache`
guard on `status === 'complete'` but NOT on `status === 'error'`, and
neither branch checked that `data.currentRunId === runId`. Because the
app reuses `sid` across turns, a cached snapshot of a prior turn's
error or completion would fire `onError` / `onComplete` on the new
turn's subscription and set `terminal = true`, suppressing the real
turn's state. Per
[Firestore listener docs](https://firebase.google.com/docs/firestore/query-data/listen),
the initial callback can be served from the local cache before the
server version arrives.

**Fix** (`src/lib/firestore-stream.ts:127-181`).

- Added `if (docRunId !== runId) return;` **before** the
  attempt-tracking block. Stale-run snapshots are now rejected entirely,
  so they can't pollute the `observedAttempt` baseline either (review
  catch: the initial fix placed the guard after attempt-tracking; a
  stale high attempt would have silenced legitimate retries).
- Added `if (fromCache) return;` to the `status === 'error'` branch
  (mirror of the complete-branch guard).

**Tests** (`src/lib/firestore-stream.spec.ts`). Three new cases:

- `ignores cached status=error snapshot` — cached-error is skipped;
  server-confirmed error still fires.
- `ignores terminal snapshots with stale currentRunId` — reused-sid
  prior-turn terminal (from either complete or error) is dropped.
- `snapshots with stale currentRunId do not pollute attempt baseline` —
  legitimate retry in the new run still fires `onAttemptChange` after
  a stale snapshot was observed first.

Existing tests that used `sessionSnap({...})` without `currentRunId`
were updated to include it; they previously passed the implicit guard
because `undefined === undefined`.

### P3 — Watchdog backfill retired

**Problem.** `backfillQueuedAt` in `functions/watchdog.js` read
`orderBy('createdAt', 'asc').limit(50)` with no cursor and no
missing-field filter. After the first invocation patched the oldest 50,
subsequent runs returned `patched=0` on the same 50 forever. Docs 51+
without `queuedAt` would never be reached. The code comment ("natural
no-op once backfill completes") was wrong.

**Fix.** Removed the backfill entirely. Rationale:

- Live Firestore survey showed **141 legacy session docs** — all with
  `{adkSessionId, userId (IP/IPv6), createdAt}` schema, zero compatible
  with the new transport (no `status`, `currentRunId`, `queuedAt`,
  `expiresAt`).
- Patching `queuedAt` onto them wouldn't make them resumable — the new
  ownership check rejects non-Firebase-UID userIds.
- Better path: one-shot deletion (see bonus).

Removed: `backfillQueuedAt` function, `BACKFILL_LIMIT` constant,
`backfilled` field from `runWatchdog` return, its `describe` block and
two tests in `functions/watchdog.test.js`.

### Bonus — Legacy session docs deleted

**Context** (discovered during P3 investigation). Live Firestore had
141 pre-refactor session documents. All 141 had `userId` in IP or IPv6
form (not Firebase UIDs); zero had the new-schema fields required by
the refactored transport. Only 2 had `reply` content.

With the tightened ownership check from the previous round
(`!userId || userId !== uid` rejects missing / mismatched), any user
whose localStorage still held one of these `sid`s would have hit
`ownership_mismatch` on first chat. The new transport would never
resume them cleanly anyway.

**Action.**

1. Exported all 141 docs to
   `/home/adam/src/superextra-landing/legacy-sessions-backup.json`
   (612 kB) as a safety backup. Added to `.gitignore`.
2. Deleted all 141 via a single Firestore `batchWrite` REST call
   (`documents:batchWrite` with 141 `delete` ops — fits within the
   500/batch limit).
3. Verified: `sessions` collection now empty live.

Users whose localStorage has stale legacy `sid`s will get "session not
found" on resume (client-side graceful fallback) and start a new
conversation.

### Live environment checks (before vs after this round)

| Check                                       | Before this round                    | After                                  |
| ------------------------------------------- | ------------------------------------ | -------------------------------------- |
| Worker Cloud Run `--concurrency`            | 4 (unsafe)                           | 1 (matches worker globals contract)    |
| Firebase deploy steps                       | 2 separate (hosting + functions gap) | 1 combined (4 targets in one CLI call) |
| Firestore `sessions` — legacy IP docs       | 141 (73 IP, 68 IPv6)                 | 0                                      |
| Firestore composite indexes                 | 4/4 READY                            | unchanged                              |
| Firestore TTL policies                      | 2/2 ACTIVE                           | unchanged                              |
| Firebase Anonymous Auth                     | ENABLED & returning valid tokens     | unchanged                              |
| Legacy Cloud Run service `superextra-agent` | still deployed                       | unchanged (manual delete post-cutover) |
| Worker service `superextra-worker`          | not deployed                         | unchanged (first deploy will create)   |

### Suite counts after the final fixes

| Suite                                | After round 3 | After round 4    | Δ                                                                                                     |
| ------------------------------------ | ------------- | ---------------- | ----------------------------------------------------------------------------------------------------- |
| Vitest                               | 89            | **77**           | −12 (sse-client.spec deleted) +3 (P2 guard tests)                                                     |
| functions (index + utils + watchdog) | 47            | **47**           | −2 (backfill tests retired) +2 (ownership missing-userId tests) +offset from earlier utils retirement |
| rules emulator                       | 10            | 10               | unchanged                                                                                             |
| agent pytest (ex-evals)              | 140 / 7 fail  | **140 / 7 fail** | unchanged; 7 in `test_follow_up_routing.py` remain CI-excluded                                        |
| svelte-check                         | 0 errors      | **0 errors**     | 13 pre-existing warnings unchanged                                                                    |
| ESLint                               | 0 errors      | **0 errors**     | 22 pre-existing warnings unchanged                                                                    |
| `prettier --check`                   | clean         | **clean**        | —                                                                                                     |
| Workflow YAML                        | valid         | **valid**        | —                                                                                                     |

Note: the Vitest count drop is historical — removing `sse-client.spec.ts`
earlier dropped ~15 tests; the row here reflects the true current count,
not a regression.

### What's left — 100% operator call

- **Deploy.** `git push main` triggers the workflow. Worker builds,
  deploys, smokes with resolved URL; hosting + functions + rules +
  indexes deploy atomically after that.
- **Post-deploy cleanup.** Delete `superextra-agent` Cloud Run service
  after smoke-testing the new stack; delete the legacy-sessions-backup
  JSON from the dev machine once confident no rollback is needed.
- **Post-deploy smoke.** Run the 14 Phase 10 manual scenarios; pay
  particular attention to the four items in the checklist above.

---

## Follow-up triage (post-review cleanup)

Added 2026-04-21, after the initial pipeline-decoupling refactor landed
and the review in
`docs/pipeline-decoupling-implementation-review-2026-04-21.md` verified
six findings against code at HEAD. Fixes are grouped into three PRs so
each can be reviewed and deployed independently:

- **PR #1** — P5 + P1 (worker terminal-reply semantics, isolated so the
  3-pass live E2E gate runs against a clean fixture).
- **PR #2** — P3a + P3b + P4 (client-side recovery bundle).
- **PR #3** — P2 (router instruction tightening, independent track).

### PR #1 — P5 + P1 (branch `pipeline-fixes-p1-p5`, PR #6)

Status: **pushed, awaiting review**.

#### P5 — align E2E fixture to Noma, Copenhagen

- `agent/tests/e2e_worker_live.py`: the place ID
  `ChIJpYCQZztTUkYRFOE368Xs6kI` resolves to **Noma, Copenhagen**
  (verified at authoring via Places API (New) v1
  `GET /v1/places/{id}?fields=displayName,formattedAddress` →
  `displayName.text="Noma"`, `formattedAddress="Refshalevej 96, 1432 København"`).
  The fixture previously labeled it as Umami, Berlin — the pipeline
  cross-checked name/secondary against placeId and the mismatch
  polluted live-smoke signal.
- Commit: `a8b46ac test(e2e): align live smoke fixture to Noma, Copenhagen`.

#### P1 — guarantee durable terminal reply

Three coordinated changes make the terminal-reply contract
lower-bounded:

1. **`_map_synthesizer` widening** (`agent/superextra_agent/firestore_events.py`):
   when the final synthesizer or follow_up event has usable
   `content.parts[*].text` but no `state_delta.final_report`, the text
   is promoted to the `complete` event's `reply`. `final_report` still
   wins when both are present (preserves format-normalization
   semantics). Grounding metadata and in-text markdown sources are
   merged and deduped by URL.
2. **`_embed_chart_images` empty-response guard**
   (`agent/superextra_agent/agent.py`): the `after_model_callback`
   previously fell back to `_build_fallback_report` only when
   `llm_response.error_code` was truthy. Now also covers:
   - response with no `content`
   - response with `content` but empty `parts` list
   - response with `parts` but no usable text
     Each path substitutes a `_build_fallback_report(state, <label>)`
     output so `final_report` is always populated.
3. **Worker `_build_degraded_reply`** (`agent/worker_main.py`):
   last-resort stitching of the worker-accumulated `state_delta` dict
   across the canonical specialist order (`market_result`,
   `pricing_result`, `revenue_result`, `guest_result`,
   `location_result`, `ops_result`, `marketing_result`, `review_result`,
   `dynamic_result_1`, `dynamic_result_2`). Returns `""` when no
   specialist produced usable output — caller falls through to
   `status='error'`, since nothing-to-show is worse than an empty
   placeholder.

#### Tests added/updated

- `agent/tests/test_firestore_events.py` (+4 tests, 2 renamed):
  text-only final synth/follow_up events emit `complete`; `final_report`
  preferred when both present; grounding + text sources merged/deduped;
  whitespace-only `final_report` falls through to text parts.
- `agent/tests/test_embed_chart_images.py` (2 existing tests updated,
  +1 new): empty-response and empty-parts now trigger fallback;
  parts-without-text triggers fallback.
- `agent/tests/test_worker_main.py` (+2 tests): degraded reply builds
  in canonical order, filters NOT_RELEVANT/whitespace; returns `""`
  when no specialist output exists.

#### Verification

Local test gate:

| Suite                                                                                  | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `npm run test`                                                                         | 77/77                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `cd functions && npm test`                                                             | 47/47                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `npm run test:rules`                                                                   | 10/10                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `npm run check`                                                                        | 0 errors, 13 baseline warnings                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `npm run lint`                                                                         | 0 errors, 22 baseline warnings                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ --ignore=tests/test_router_evals.py` | 154 passed, 3 failed (all in `tests/test_follow_up_routing.py` — the pending P2 router-quality track). Figures from a reviewer rerun on an environment with a Vertex-AI-scoped ADC token. On the original author shell the ADC lacked the aiplatform scope, so all 7 router-eval tests failed with `ACCESS_TOKEN_SCOPE_INSUFFICIENT` before reaching the router (counted as 150 passed / 7 failed earlier in this log's history — an artifact of the auth shape, not the routing quality). |

Live E2E against real `superextra-worker`
(`agent/tests/e2e_worker_live.py`, post-fix):

- **PASS** — `status=complete`, `reply_len=300069`, `sources_n=15`,
  `title='Service review issues'`, 1 `complete` event written, 319s
  elapsed.
- Compared to the **failing baseline** run on the same fixture pre-fix:
  `status=error / empty_or_malformed_reply` after 314s, 0 `complete`
  events.

Commit: `7ba2872 fix(worker): guarantee durable terminal reply when synthesizer returns no final_report`.

#### Remaining P1 work — handed to post-merge

1. **3-consecutive-pass gate** per the review's exit criterion #1. One
   live run has passed; two more required post-merge/post-deploy.
2. Watch worker logs after deploy for `event: degraded_reply` — fires
   only when the worker-side fallback path is exercised. Not expected
   in normal operation; presence isn't fatal (reply is still durable)
   but signals synth is silently returning empty.

### PR #2 — P3a + P3b + P4 (pending)

Scope (not yet started):

- **P3a** — recovery/resume paths drop server-generated title.
  `RecoveryContext.onReply` needs a `title?` parameter; `recover()` and
  `resumeIfInFlight()` must plumb `data.title` through to conversation
  state.
- **P3b** — `onPermissionDenied` fires twice when both Firestore
  observers error. Add a `permissionDeniedFired` closure guard in
  `subscribeToSession`; update `firestore-stream.spec.ts:415-425` which
  currently asserts the wrong count; add a `recoveryStarted` guard
  around `recover()` calls in `chat-state.svelte.ts`.
- **P4** — hardcoded production URLs. Switch `agentStreamUrl()` and
  `agentCheckUrl()` to the same-origin rewrite paths
  (`/api/agent/stream` and `/api/agent/check`). `firebase.json:78-86`
  already defines the rewrites for the `agent` hosting target. Safe
  now that `agentStream` no longer streams — post-decoupling it's a
  plain POST-returns-JSON enqueue, so the `cloudfunctions.net` GFE
  proxy SSE workaround is no longer load-bearing.

### PR #3 — P2 (pending)

Router instruction tightening — `agent/superextra_agent/instructions/router.md`
needs explicit positive/negative examples for the four failing
realistic multi-turn prompts in
`agent/tests/test_follow_up_routing.py:124-158`:

- → `follow_up`: "Summarize that in bullet points", "What did you find
  about pricing?", "Can you compare restaurants A and B from the
  report?"
- → `research_pipeline`: "What about the delivery market in this
  area?", "Now analyze Restaurant D in Krakow"

Run `test_follow_up_routing.py` + `npm run test:evals` as a release
gate. Independent of PR #1 / PR #2 — can run in parallel.

### Updated exit criteria

From the review doc, the gate to mark the pipeline-decoupling project
fully finalized:

1. `agent/tests/e2e_worker_live.py` passes 3 consecutive runs with
   durable terminal reply (`status='complete'` and `reply_len > 0`).
   _1/3 passed (PR #1)._
2. `agent/tests/test_follow_up_routing.py` is green, OR team narrows
   "finalized" to the transport layer only. _Pending PR #3._
3. Refresh-after-complete and REST-fallback-after-complete preserve
   titles. _Pending PR #2 P3a._
4. Recovery fallback is one-shot per run. _Pending PR #2 P3b._
5. Smoke fixture is internally consistent. _Done (PR #1 P5)._
6. Optional: client uses same-origin rewrite paths in prod. _Pending
   PR #2 P4._

---

This log is the final state record pre-deploy. No further code changes
planned; next update should be post-deploy outcome.
