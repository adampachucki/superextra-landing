# Plan: Decouple the agent pipeline from the browser's connection

## Status for implementers

This plan has been validated against the live `superextra-site` project via 9 independent spikes (A–I) plus a parallel validation pass by a second agent. The architecture is settled. Remaining work is implementation.

**Before writing code, read in this order:**

1. This plan (you're here).
2. [`docs/pipeline-decoupling-spike-results.md`](./pipeline-decoupling-spike-results.md) — the evidence behind every non-obvious claim below. **Its "For implementers" section lists one-time environment setup, settled facts you do NOT need to re-verify, and known gotchas.** Read it before committing to any sub-design.
3. [`docs/pipeline-decoupling-review.md`](./pipeline-decoupling-review.md) — multi-round review history showing what earlier plan versions got wrong and why.
4. [`docs/pipeline-decoupling-validation-findings.md`](./pipeline-decoupling-validation-findings.md) — parallel validation agent's independent pass. Largely overlaps with the spike-results doc; their notable adds are the IAM double-binding in Phase 6 and pre-existing routing regressions.
5. [`spikes/README.md`](../spikes/README.md) — reusable artifacts, including `adk_event_taxonomy_dump.json` (27 real ADK events — use as Phase 2's test fixture).

**Don't re-validate these load-bearing facts (they're settled):**

- `Runner(app=app, session_service=VertexAiSessionService(project, location, agent_engine_id="2746721333428617216"))` works in-process and fires plugins. `Runner(agent=…)` silently drops plugins.
- `VertexAiSessionService.create_session()` does not accept user-provided session IDs; capture from `Session.id`.
- In-process Runner emits **no partial-text events** with default `RunConfig`. Synthesizer emits one final event. No token batching needed.
- Firestore client query must be `collectionGroup(db, 'events')`, NOT subcollection. The `(userId, runId, attempt, seqInAttempt)` COLLECTION_GROUP index **already exists** in `superextra-site`.
- Cloud Tasks `dispatch_deadline` does NOT cancel in-flight Cloud Run handlers — only the Cloud Run request timeout does. Worker `--timeout=1790` is load-bearing.
- Cloud Run revision rollouts do NOT kill in-flight requests.
- Firebase SDK chunk is ~97 kB gzipped (lighter than the plan previously estimated).

**Pre-flight environment checklist (one-time per workstation):**

```bash
# 1. Ensure ADC has cloud-platform scope (VM's GCE metadata SA doesn't)
export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<you>/adc.json

# 2. Core env for ADK / Vertex calls
export GOOGLE_CLOUD_PROJECT=superextra-site
export GOOGLE_CLOUD_LOCATION=us-central1
export GOOGLE_GENAI_USE_VERTEXAI=TRUE

# 3. Agent venv (spikes installed these; requirements.txt doesn't yet — add in Phase 3)
cd agent && .venv/bin/pip install google-cloud-firestore google-cloud-tasks

# 4. If touching the frontend: `firebase` is not yet in package.json (intentional — Phase 1 adds it)
```

**Known pre-existing issues unrelated to this plan** (track separately, don't attribute to transport work):

- `test_follow_up_routing.py`: 4 failures. Some follow-ups don't route to the `follow_up` agent.
- `test_router_evals.py`: 2 failures. Some clarification messages transfer to `research_pipeline`.
- `npm run lint` fails on un-Prettier-formatted markdown — run `npx prettier --write docs/pipeline-decoupling-plan.md` before committing edits.

## Open questions — resolve before starting implementation

Decisions the implementer will hit that weren't fully nailed in earlier conversation. Ask the product owner before guessing.

1. **UID rate-limit threshold for Phase 4** — how many pipeline runs per anonymous UID per rolling hour? Plan says "UID-based rate-limit" but doesn't pin a number. Suggested starting point: 20/hour (generous for a design partner actively exploring; still bounds runaway abuse). Raise to 50 during active demo periods.

2. **Phase 0 gate — representative query set** — Phase 0 requires a p99 across "10+ representative queries." What's the canonical set? Suggested (pending confirmation): 3 narrow ("service issues in reviews", "menu trends", "operational cost benchmarks"), 3 mid ("competitor analysis", "customer sentiment overview", "pricing positioning"), 4 broad ("full competitive analysis" on 4 different restaurants of varying scale). Capture in `agent/tests/fixtures/phase0_queries.json` for reproducibility.

3. **Partial-text streaming as future work?** — Spike B observed zero partial-text events from in-process Runner (default `RunConfig`). We can enable streaming via `RunConfig(streaming_mode=SSE)` — would let the synthesiser reply stream in as a "typewriter" UX. Not required for correctness. **Is this desired for v1 of the new UX, or explicitly deferred?** If deferred, say so clearly so Phase 2's mapper stays simple.

4. **Cross-device continuity** — plan says out of scope (anon auth = per-browser UID). If a design partner opens the same `/chat?sid=…` URL on laptop after starting on mobile, they'll see 403 (different UID). Acceptable silent fail, or should Phase 5 surface a specific "continue on the original device" error message?

5. **`agentCheck` with stale `runId`** — user polls `agentCheck?sid=A&runId=X` while the conversation has moved to `runId=Y`. Return current `runId`'s state regardless, or 404 on mismatch? Plan's current silence implies return current state — confirm.

6. **Watchdog threshold for pathological long queries** — if a legitimate query runs >22 min (rare deep analysis + Gemini slow day), watchdog flips to `error`, user retries. Accept that tradeoff, or bump the threshold for certain query shapes? Phase 0 measurements inform this.

7. **Turn-error recovery UX** — if turn N fails (`status=error`), turn N+1's `send()` resets `status` to `queued`. localStorage still shows turn N errored. Does the UI leave the errored message visible (suggested: dimmed "this turn failed" record + new turn below), or replace it?

8. **Agent Engine session cleanup cadence** — each `send()` creates an Agent Engine session that persists. No TTL on Agent Engine side. Schedule a weekly sweep to delete sessions for Firestore sessions in `status='error'` >7 days? Low priority; post-launch hygiene.

## Reference skeletons + preflight

- **`spikes/preflight_check.sh`** — run this first. Verifies gcloud auth, ADC cloud-platform scope, agent venv deps, live API access, and the Firestore composite index. Green → proceed.
- **`spikes/skeletons/worker_main.py`** — reference FastAPI handler showing how takeover, fenced writes, heartbeat task, ADK Runner event loop, and SIGTERM handler fit together. Copy to `agent/worker_main.py` during Phase 3 and fill in TODOs.
- **`spikes/skeletons/firestore_events.py`** — reference event-mapper dispatcher for Phase 2. Copy to `agent/superextra_agent/firestore_events.py` and extend.

---

## The product context

Superextra's chat answers questions about a specific restaurant by running a multi-stage research pipeline: it pulls Google Places data, plans an investigation, dispatches 3–8 specialist research agents in parallel (market, menu, revenue, guest intelligence, location, operations, marketing, reviews), runs a gap-researcher to catch contradictions, and finally synthesises a report with charts. That's legitimately 7–15 minutes of work for deep queries, 2–4 minutes for narrow ones.

## What's broken

On 2026-04-18 we observed a session (`sid=85c26a17-556c-4c79-bc6c-bf354caa7cf1`) hang at "Researching…" for the whole pipeline, then eventually surface a timeout error. The UI showed all three research sub-agents as done, but the final report never arrived.

From Cloud Run logs, the exact chain:

| T+            | Event                                                                                                                                                       |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0 s           | Browser opens SSE to `agentStream` (Cloud Function). `agentStream` opens its own fetch to ADK's `/run_sse`.                                                 |
| 24 s          | Context enricher done (Places data in).                                                                                                                     |
| 67 s          | Research orchestrator finishes planning.                                                                                                                    |
| 75 s          | Three specialists start in parallel (Gemini 3.1 deep thinking + web grounding — legitimately slow).                                                         |
| **440 s**     | `agentStream`'s `AbortSignal.timeout(440_000)` fires. Our own `ac.abort()` in the `res.on('close')` handler is also wired into the upstream abort chain.    |
| +1 s          | ADK's Cloud Run cancels the `/run_sse` request; log shows `Truncated response body`. **The pipeline dies mid-specialist.** `final_report` is never written. |
| 540 s (9 min) | The recovery poller's age cutoff fires; frontend shows "timed out".                                                                                         |

Same failure triggers: closing the browser tab, mobile Safari/Chrome backgrounding the app, network roaming (Wi-Fi ↔ 5G), Cloud Function proxy glitches. Mobile design-partner traffic hits this daily.

## Requirements this has to meet

- **No stuck sessions, ever.** If the pipeline can't complete, the UI must show a clear error within minutes — not "running" forever.
- **Page refresh mid-pipeline must work.** User reloads the tab at T+10 min → sees current progress, pipeline keeps running.
- **Users will come back.** Mobile users close the app, users get frustrated — when they return 30 min later, the answer must be there.
- **Auto-retry on infrastructure failure.** Users should not have to manually retry because a Cloud Run instance restarted. The system retries for them.
- **Multi-turn conversations must keep working.** The chat UI reuses one conversation ID across many `send()` calls. Each follow-up turn must enqueue cleanly without collisions on the previous turn's state.
- **Stable, not MVP.** No "good enough for now" corners that'll break when traffic grows. But also not over-engineered — every component must earn its place.

## Why the obvious fixes don't work

1. **"Just raise the timeouts."** Doesn't help — the browser drops the connection long before a 15-min pipeline finishes (mobile Safari suspends SSE within ~30 s of backgrounding).
2. **"Finish in the background after the browser drops."** Cloud Run can scale instances to zero at any point after a response is written, regardless of `--no-cpu-throttling`. Unawaited async tasks after `res.send()` can be killed. Not reliable.
3. **ADK's `session_resumption=True`.** Verified against `google/adk-python` source: it's a Gemini Live WebSocket token, never consumed by `/run_sse`. Doesn't apply.
4. **Interactions API.** Public beta, not on Vertex AI, and `background=True` runs only Google's closed Deep Research agent. Can't host our pipeline.

## What we're building

```
Browser           agentStream (Cloud Function)       Cloud Tasks            superextra-worker (Python)
  │                      │                                │                        │
  ├─ POST {sid, runId} ─▶│                                │                        │
  │                      ├─ verify Firebase ID token                                │
  │                      ├─ Firestore txn: upsert session doc, stamp currentRunId   │
  │                      ├─ UID-based rate limit                                    │
  │                      ├─ enqueue task (name=runId) ───▶│                        │
  │◀─ 202 {sid, runId} ──┤                                │                        │
  │                                                       ├─ dispatch (1800s) ────▶│
  │                                                                                ├─ in-process ADK Runner
  │                                                                                │   (no HTTP to /run_sse)
  │── onSnapshot(sessions/{sid}) + events where runId==current ───────────────────│─ writes events + heartbeats
  │◀── progressive updates (survives page refresh) ────────────────────────────────│─ fenced status writes
  │◀── sessions/{sid}.status = complete ───────────────────────────────────────────│─ final doc (admin SDK only)
```

**Key identities:**

- `sid` — **conversation ID**. Stable across all turns in a thread. Already how the frontend works today (`currentId` in `chat-state.svelte.ts:366`).
- `runId` — **per-turn run ID**. Fresh UUID each time the user sends a message. Used as the Cloud Tasks task name (unique per turn, avoids 24-hour name-dedup collisions) and tags every event.
- `attempt` — incremented when Cloud Tasks retries a failed run. Stored on the session doc; client filters events to `attempt == currentAttempt` so retry reruns display cleanly.

In plain English:

- Browser POSTs, gets an instant `202`. Never holds the pipeline.
- Cloud Tasks dispatches the job. If the worker crashes, Cloud Tasks retries with exponential backoff (max 3 attempts). Workers are idempotent — takeover via atomic Firestore transaction.
- Worker imports the agent code directly and calls `Runner(app=app, session_service=…).run_async()` in-process. Dodges ADK open bugs #4216 / #4244 and the HTTP/2 idle-reaping problem.
- Worker writes events to Firestore as they arrive. Every 30 s it also writes a liveness heartbeat, and every ADK event updates `lastEventAt` (so a worker with fresh heartbeat but wedged pipeline is still detected).
- Browser subscribes to Firestore. Page refresh mid-pipeline: `onSnapshot`'s first callback delivers the full current event list in order (verified).
- Browser is read-only on Firestore. All writes go through Admin SDK (worker and Cloud Function). Rules enforce `allow write: if false`.
- A watchdog function sweeps Firestore every 2 min. Queued sessions older than 30 min → error (queue dispatch failure). Running sessions with silent heartbeat or no events → error (worker lost). No session sits in `running` forever.

## Design decisions (verified against docs and code)

| Decision                               | Choice                                                                                                                                                          | Why                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Worker runtime                         | **Python in-process ADK**, `Runner(app=app, session_service=VertexAiSessionService(project, location, agent_engine_id="2746721333428617216"))`                  | Matches ADK production guidance. `Runner(agent=…)` silently drops plugins — verified from source.                                                                                                                                                                                                                                                                                                                                                                             |
| Queue                                  | **Cloud Tasks**, `--dispatch-deadline=1800s`, `max-attempts=3`, exponential backoff 10s→60s                                                                     | At-least-once delivery: duplicate executions explicitly documented, so worker idempotency is mandatory. Default dispatch deadline is 10 min (Cloud Tasks docs), must override to 1800s for our 7–15 min pipeline.                                                                                                                                                                                                                                                             |
| Cloud Run timeout vs dispatch deadline | **Cloud Run `--timeout=1790s`** (just under the 1800s dispatch deadline)                                                                                        | Cloud Tasks docs: "set `dispatch_deadline` a few seconds longer than your app's handler timeout." Ensures Cloud Run cancels the worker before Cloud Tasks gives up, so zombie workers don't outlive the retry.                                                                                                                                                                                                                                                                |
| Identity                               | **Stable `sid` = conversation, fresh `runId` per turn**                                                                                                         | Chat reuses `sid` across turns (`chat-state.svelte.ts:366`, agent follow-up routing in `agent.py:230-237`). Task name = `runId` avoids Cloud Tasks 24-hour name-dedup collisions on follow-ups.                                                                                                                                                                                                                                                                               |
| Worker idempotency                     | **Task name = `runId` + atomic Firestore txn on takeover + ownership fencing on status writes + per-attempt event sequencing**                                  | Name-dedup is first-line defense. Txn on takeover serialises concurrent deliveries. Fenced writes prevent stale workers from overwriting a newer attempt's state. Per-attempt seq gives clean retry-rerun UX.                                                                                                                                                                                                                                                                 |
| Active-owner handling                  | **Poll-and-wait, bounded at 7 min**                                                                                                                             | If worker B arrives while A is actively running (fresh heartbeat): B polls the session doc every 5 s until A reaches terminal state, OR A's heartbeat goes stale, OR the watchdog flips status to error. If 7 min elapses without resolution, B returns 5xx so Cloud Tasks can retry later. 7 min aligns with the watchdog's worst-case detection window (5 min `lastEventAt` threshold + 2 min scheduler interval). Preserves auto-retry coverage under at-least-once races. |
| Liveness detection                     | **Dual-signal: heartbeat (30 s pulse from asyncio task) AND lastEventAt (updated per ADK event)**                                                               | Heartbeat alone doesn't catch "worker alive but pipeline deadlocked" (specialists stuck on a hung tool call). Watchdog ORs both signals.                                                                                                                                                                                                                                                                                                                                      |
| Progress store                         | **Firestore, browser-read-only, writes via Admin SDK**                                                                                                          | Rules are a direct `resource.data.userId == request.auth.uid` check on both sessions and events — `userId` is denormalised onto each event doc so no `get()` into the parent is needed. Admin SDK bypasses rules. `onSnapshot` first-callback delivers full current state → refresh works natively.                                                                                                                                                                           |
| Stuck-session watchdog                 | **Scheduled every 2 min. `queued` → error after 30 min of `queuedAt`; `running` → error after 10 min of stale `lastHeartbeat` OR 5 min of stale `lastEventAt`** | Split thresholds because queued sessions legitimately have no heartbeat (worker hasn't started yet). Running sessions have both signals available. `queuedAt` (not `createdAt`) is used because `createdAt` is preserved across turns — a 6-hour-old conversation's turn 5 would be falsely flagged on arrival.                                                                                                                                                               |
| Auth                                   | **Firebase Anonymous Auth on frontend; Firebase ID token verified on `agentStream` and `agentCheck`; explicit ownership checks in both endpoints**              | No App Check for now: added complexity (cold-start race, reCAPTCHA init, backend token verification) for marginal security gain over Firebase ID token verification + explicit ownership checks + UID-based rate-limit. Actual reCAPTCHA Enterprise cost is usage-dependent (first 10k assessments/month free, then tiered); defer decision is about the complexity/benefit tradeoff at this scale, not a specific dollar figure. Re-evaluate post-stabilisation.             |
| Abuse protection                       | **IP rate-limit + anonymous-UID rate-limit on `agentStream`**                                                                                                   | Protects against automated pipeline abuse without App Check's cost.                                                                                                                                                                                                                                                                                                                                                                                                           |
| Cleanup                                | **TTL on `sessions` + TTL on `events` collection group (separate policies)**                                                                                    | Verified: Firestore TTL does not cascade. Collection-group TTL is the documented fix.                                                                                                                                                                                                                                                                                                                                                                                         |
| Frontend REST fallback                 | **Keep `chat-recovery.ts`, tighten trigger**                                                                                                                    | Fires only on `onSnapshot` PERMISSION_DENIED error OR no first-snapshot within 10s. Covers ad-blockers targeting `*.googleapis.com`, corporate firewalls/proxies blocking Firestore's WebSocket channel, and intermittent Firebase Auth PERMISSION_DENIED edge cases. Not a general-purpose "network is slow" retry.                                                                                                                                                          |
| Feature flag                           | **None**                                                                                                                                                        | Git revert is the escape hatch for this scale.                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Worker SA                              | **Dedicated `superextra-worker@superextra-site.iam.gserviceaccount.com`**                                                                                       | Stable production deserves least-privilege isolation.                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Cross-device continuity                | **Out of scope** (same-browser only)                                                                                                                            | Anon auth gives a UID per browser. Cross-device requires account linking (future).                                                                                                                                                                                                                                                                                                                                                                                            |

## Phased plan

Effort estimates assume one engineer.

### Phase 0 — Agent speed-ups (½ day) — GATE for Phase 3

**Files:** `agent/superextra_agent/specialists.py`, `agent/superextra_agent/agent.py`

- New `MEDIUM_THINKING_CONFIG`.
- Apply MEDIUM to: `marketing_digital`, `guest_intelligence`, `location_traffic`, `gap_researcher`, **and the context enricher** (function-caller, not deep reasoner).
- Keep HIGH on: `revenue_sales`, `operations`, `market_landscape`, synthesiser.
- Gap researcher stays in the pipeline — quality gate.

**Gate before Phase 3:** measure p99 runtime on a representative query set (10+ runs). Require p99 < 22 min — preserves ≥8 min headroom on the 30-min Cloud Tasks ceiling for new-worker cold-start (3–30 s typical for a Python FastAPI+ADK image), Firestore write latency, and Gemini response-time variance. If p99 ≥ 22 min, pause Phase 3 and address pipeline depth before committing to the queue architecture.

**Observable outcome:** median pipeline time drops ~30–40 %.

### Phase 1 — Firebase Anon Auth + Firestore rules + indexes (1 day)

**Files:** `src/lib/firebase.ts` (new), `firestore.rules` (new), `firestore.indexes.json` (new), `firebase.json`, `src/routes/agent/chat/+page.svelte`

**Reference**: `spikes/firestore_rules_test.js` is a ready-to-run mocha starter for `@firebase/rules-unit-testing`. Install deps + run via `firebase emulators:exec` first — TDD the rules. Spike D verified the collection-group query + `(userId, runId, attempt, seqInAttempt)` index combination works end-to-end; that index is already live in `superextra-site`.

Frontend: dynamic `import('firebase/app')` + `import('firebase/firestore')` + `import('firebase/auth')` inside chat-route (keeps marketing bundle clean). Measured in spike G: ~97 kB actual gzipped for the Firebase modular v10 chunk when imported on a single route. `initializeApp` + `signInAnonymously()` on chat-route bootstrap with `onAuthStateChanged` gate.

**Rules — browser read-only**:

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /sessions/{sid} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.userId;
      allow write: if false;
    }

    // Collection-group match for events (client uses collectionGroup query;
    // see spike-results doc Finding D.1)
    match /{path=**}/events/{eid} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.userId;
      allow write: if false;
    }
  }
}
```

**`userId` is denormalized onto every event doc** at write time (worker includes it in `write_event()`). The rule checks `resource.data.userId` directly — no `get()` into the parent session doc on every event read. Avoids N extra billed reads per query (which at 50 events/turn × active users would add up). The storage cost is one UID field per event; rules are simpler and cheaper.

**Why collection-group rule, not nested**: verified empirically (spike D) that `COLLECTION_GROUP`-scoped composite indexes do NOT cover subcollection-scoped queries — and gcloud CLI cannot create `COLLECTION`-scoped indexes. The client therefore uses `collectionGroup('events').where('userId', '==', uid).where('runId', '==', runId).orderBy(...)` which needs collection-group rule matching.

**Indexes** (`firestore.indexes.json` — enumerate explicitly, don't discover at runtime):

- Collection group `events`: `(userId ASC, runId ASC, attempt ASC, seqInAttempt ASC)` — for client `collectionGroup('events')` query. The `userId` field is the leading filter that keeps each user's read cost bounded (verified in spike D to work correctly; existing index already created in `superextra-site` during spike).
- Collection group `sessions`: `(status ASC, queuedAt ASC)` — for watchdog queued-sweep query.
- Collection group `sessions`: `(status ASC, lastHeartbeat ASC)` — for watchdog running-sweep (heartbeat disjunct).
- Collection group `sessions`: `(status ASC, lastEventAt ASC)` — for watchdog running-sweep (event-activity disjunct). Firestore can't serve an OR across different fields from a single composite index, so the watchdog runs two queries (one per disjunct) and merges results in code.

Firestore also transparently creates a small extra internal index the first time a real `onSnapshot` listener is opened on the events query shape — observed once during spike D, one-time ~30 s build, no action needed.

**Observable outcome:** nothing user-visible. Sessions gated to their creator; writes impossible from browser.

### Phase 2 — Python event mapper (1.5 days)

**File:** `agent/superextra_agent/firestore_events.py` (new)

**Reference**: use `spikes/adk_event_taxonomy_dump.json` as a test fixture — it's a real capture of 27 Runner events from a full pipeline run. The mapper-rules table in the spike-results doc ("B — Event taxonomy") enumerates exactly which `(author, function_call, state_delta_keys)` combinations to handle.

Maps ADK Runner events (structured Python objects from `runner.run_async()`) to Firestore event docs. Realistic scope after inspecting current `parseADKStream` in `functions/utils.js:200-678`:

- Partial-text coalescing (synthesiser streaming).
- Author/specialist tagging for `onActivity` (each event carries author).
- Tool-call labelling (google_search, fetch_web_content, places APIs → UI-friendly activity IDs).
- Source harvesting from `grounding_metadata.grounding_chunks` (current workaround in `specialists.py:_append_sources` — may need mirroring or removal now that we have direct access).
- Synthesiser final-report detection (`is_final_response()`).

Signature: `async def write_event(sid, user_id, run_id, attempt, seq_in_attempt, event_type, data, firestore_client)`. Event doc shape: `{userId, runId, attempt, seqInAttempt, type, data, ts: serverTimestamp(), expiresAt}`. `userId` is denormalized onto each event so Firestore rules can check it directly without a `get()` into the parent session doc (cheaper reads, simpler rules).

**Parity test:** fixture-driven — feed the same Runner events to this mapper as today's SSE flow uses in `functions/utils.test.js`, assert equivalent output shape.

**Observable outcome:** internal only. Unit-testable.

### Phase 3 — Worker service: `superextra-worker` (3 days)

**Files:** `agent/worker_main.py` (new FastAPI entrypoint), `agent/requirements.txt` update, `agent/Dockerfile` (new — ~20 lines: `python:3.12-slim` base, install `google-adk`, `fastapi`, `uvicorn[standard]`, `firebase-admin`, `google-cloud-firestore`, `google-cloud-tasks`, copy `agent/`, entrypoint `uvicorn worker_main:app --host 0.0.0.0 --port 8080`).

**Reference**: `spikes/adk_runner_spike.py` shows the verified instantiation pattern. `spikes/cloudtasks_oidc/main.py` shows the minimal FastAPI + Cloud Tasks header-reading shape.

Single endpoint `POST /run`:

1. **Auth is handled by Cloud Run IAM — no in-handler token verification.** Cloud Tasks mints an OIDC token using the configured `serviceAccountEmail` (the worker SA). Cloud Run validates the token and checks the principal has `roles/run.invoker` before forwarding the request to the handler. Since only the worker SA has `run.invoker` on this service, and only Cloud Tasks can impersonate the worker SA via `serviceAccountUser`, a request that reaches the handler is already authenticated as "an OIDC-signed Cloud Tasks dispatch." Read `X-CloudTasks-TaskName` (= `runId`), `X-CloudTasks-TaskRetryCount`, `X-CloudTasks-TaskExecutionCount` as informational task metadata for logging and idempotency.

2. **Idempotent takeover / active-owner wait** — atomic Firestore transaction on `sessions/{sid}`:
   - Read existing doc.
   - **Defense-in-depth ownership assertion**: verify `existing.userId == payload.userId`. If not, abort (fatal error, return 500 — agentStream should have prevented this). This is a belt-and-suspenders check on the identity that agentStream already validated.
   - If `status ∈ {complete, error}` AND `currentRunId == runId`: return `200` immediately (duplicate delivery after terminal state for this run).
   - If `status == 'running'` AND `currentRunId == runId` AND `lastHeartbeat > now - 2min`: enter poll loop (see below).
   - Otherwise: set `status='running'`, `currentRunId=runId`, `currentAttempt=(existing.get('currentAttempt') or 0) + 1` (agentStream resets to 0 on new turn; in-run retries increment), `currentWorkerId=uuid4()` (fresh random UUID per worker invocation — unique identifier for fencing, no need to stringify Cloud Tasks headers), `lastHeartbeat=now`, `lastEventAt=now`. Commit.

   **Poll loop** for active-owner case: every 5 s re-read the session doc. Exit conditions: `status` becomes terminal (return `200` — the other worker succeeded or failed cleanly, or the watchdog flipped it to `error`); heartbeat goes stale (take over via a fresh takeover transaction); 7 min elapsed (raise `WorkerBusyError` → FastAPI returns 500 → Cloud Tasks backoff-retry). 7 min aligns with the watchdog's worst-case detection window — by then the watchdog has had an opportunity to classify the stale-pipeline case and B will observe a terminal state rather than timing out.

3. **Background heartbeat**: `asyncio.create_task` that writes `sessions/{sid}.lastHeartbeat` every 30 s via fenced transactional update (see step 6). **Cancellation ordering** (matters to avoid a late tick overwriting a terminal state): cancel the heartbeat task _before_ writing the final `status=complete`/`error`, await task completion with a 1 s cap, then proceed with the terminal write.

4. **Instantiate ADK**:

   ```python
   from google.adk.runners import Runner
   from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
   from superextra_agent.agent import app

   session_svc = VertexAiSessionService(
       project="superextra-site",
       location="us-central1",
       agent_engine_id="2746721333428617216",
   )
   runner = Runner(app=app, session_service=session_svc)  # plugins fire because we pass app
   ```

5. **Stream events**:

   ```python
   seq_in_attempt = 0
   async for event in runner.run_async(user_id, adk_session_id, new_message=content):
       seq_in_attempt += 1
       await write_event(sid, user_id, runId, currentAttempt, seq_in_attempt, event_type, data, fs)
       await fenced_update(sid, currentAttempt, currentWorkerId, {"lastEventAt": SERVER_TIMESTAMP})
   ```

   Events are tagged with `userId` + `runId` + `attempt` + `seqInAttempt`. `userId` matches the Phase 2 mapper signature and is required by the events read rule (`resource.data.userId == request.auth.uid`). No hot-doc counter. No fencing needed on event writes themselves (stale events from a taken-over worker are invisible to the client, which filters by `currentAttempt`).

6. **Ownership fencing on status/heartbeat/terminal writes**:

   ```python
   @firestore.transactional
   def _fenced(txn, session_ref, my_attempt, my_worker_id, update_fields):
       snap = session_ref.get(txn)
       if snap.get('currentAttempt') != my_attempt or snap.get('currentWorkerId') != my_worker_id:
           raise OwnershipLost()  # another worker took over; bail cleanly
       txn.update(session_ref, update_fields)
   ```

   Used for: heartbeat, lastEventAt, status transitions, reply/sources/title writes.

7. **On successful completion**: generate title (Gemini 2.5 Flash, first message only), reply sanity check (non-empty, length ≥ 100, doesn't start with `"Error:"`), then fenced write `{reply, sources, title, status='complete'}`. Return `200`.

8. **On caught pipeline exception**: fenced write `{status='error', error}`, return `200`.

9. **On infrastructure error** (Firestore write failed, OwnershipLost, etc.): don't catch. FastAPI returns 500 → Cloud Tasks retries.

10. **On hard crash** (OOM → SIGKILL; revision drain → SIGTERM + 10 s + SIGKILL): worker never returns. Cloud Tasks hits dispatch deadline, retries. Next attempt sees stale heartbeat, takes over (step 2).

**SIGTERM handler** (10 s fixed grace — do only minimal work):

1. Cancel the heartbeat asyncio task.
2. `asyncio.wait_for(heartbeat_task, timeout=1)` to ensure its last fenced transaction (if any) finishes before the next step.
3. Fenced write `sessions/{sid}.lastHeartbeat = null` (explicit takeover signal to the next retry).
4. Return immediately.

Rationale: without this ordering, the heartbeat coroutine can tick after the null-out and clobber with a fresh timestamp, making retry workers wait ~30 s extra before detecting the stale state.

**Cloud Run config:**

- `--no-cpu-throttling --timeout=1790s --memory=2Gi --max-instances=10 --min-instances=0 --concurrency=4 --no-allow-unauthenticated`
- `--concurrency=4` explicitly caps per-instance concurrency — avoids an instance absorbing 80 idle pollers during a duplicate-delivery race.

**Service account:** dedicated `superextra-worker@superextra-site.iam.gserviceaccount.com` (new) with:

- `roles/aiplatform.user` (Vertex AI / Gemini)
- `roles/datastore.user` (Firestore read/write)
- `roles/run.invoker` on itself (Cloud Tasks OIDC target auth)

### Phase 4 — `agentStream` refactor (1 day)

**File:** `functions/index.js`

Stops streaming. New flow:

1. Verify `Authorization: Bearer <idToken>` with `getAuth().verifyIdToken(token)` → `userId = decodedToken.uid`.
2. Validate inputs (existing logic) + IP rate-limit (existing) + **new UID rate-limit** (N pipeline runs per anon UID per hour).
3. Extract `sessionId` (= conversation ID, stable across turns) from request. If not provided, use the request-body's legacy `sessionId` field from the current frontend.
4. **Generate `runId = uuid()`** server-side (avoids client-trust issues; returned in the 202).
5. **Atomic Firestore transaction on `sessions/{sid}`**:
   - Read existing doc (if any).
   - **Ownership check** — if doc exists AND `existing.userId != decodedToken.uid`: **return 403**. Admin SDK bypasses Firestore rules, so the browser's read rule does not protect this path. Without this explicit check, any authenticated user who knows a `sid` could enqueue work against another user's conversation and see cross-user "turn" events appear in the victim's chat.
   - If doc exists AND `status ∈ {queued, running}`: **return 409** (previous turn still in flight; user must wait).
   - Otherwise, upsert. Two paths:

     **New session (doc does NOT exist)** — explicitly initialise every field:
     - `userId = decodedToken.uid` (the browser read rule requires this; must be present on turn 1).
     - `createdAt = serverTimestamp()`.
     - `adkSessionId = <created this request or null placeholder>`.
     - `placeContext = <from request body>`.
     - `title = null`.
     - Plus all per-turn + `expiresAt` fields below.

     **Existing session (doc exists, terminal status)** — preserve conversation-level fields, reset per-turn fields:
     - **Preserved**: `userId`, `createdAt`, `adkSessionId`, `placeContext`, `title`.
     - **Reset per turn**: `currentRunId: runId`, `currentAttempt: 0`, `currentWorkerId: null`, `status: 'queued'`, `queuedAt: serverTimestamp()`, `lastHeartbeat: null`, `lastEventAt: null`, `reply: null`, `sources: null`, `error: null`.
     - **Extended on activity**: `expiresAt` — Firestore has no server-side scalar `max()`, so this is computed client-side inside the transaction: read the existing `expiresAt`, compute `new_expires = max(existing?.toMillis() ?? 0, Date.now() + 30*24*60*60*1000)`, write that value. Never shrinks, so active conversations stay alive past the original 30-day TTL.

   - Any in-memory session cache (`sessionMap` in today's `functions/index.js`) must also gate cache hits on `cachedEntry.userId == decodedToken.uid`.

6. Ensure ADK session exists in Agent Engine (reuse existing session-cache logic from today's `functions/index.js`). One ADK session per conversation — shared across turns, which is how follow-up routing in `agent.py:230-237` works. **Note**: `VertexAiSessionService.create_session()` does not accept a user-provided `session_id` — Agent Engine assigns the ID. Capture the assigned ID from the returned `Session.id` and persist it as `adkSessionId` on our Firestore session doc (verified in spike A, finding A.1).
7. **Enqueue Cloud Task**:
   - Target: `https://superextra-worker-{hash}.us-central1.run.app/run`
   - OIDC token audience: exactly the worker's `run.app` URL.
   - `name`: `projects/.../tasks/{runId}` (**fresh per turn — no dedup collision on follow-up turns**).
   - `dispatchDeadline`: `1800s` (explicit — overrides 10-min default).
   - Body: `{sessionId, runId, adkSessionId, userId, queryText, isFirstMessage, placeContext, history}`.
8. Return `202 {sessionId, runId}`.

Drops: `parseADKStream` call, SSE headers/writes, `AbortSignal.timeout(440_000)`, 15 s keepalive, `res.on('close')` handler, `generateTitle` helper (moved to worker), source-fallback fetch.

**Observable outcome:** POST returns in <300 ms instead of streaming for minutes.

### Phase 5 — Frontend refactor (1.5 days)

**Files:** `src/lib/firestore-stream.ts` (new), `src/lib/chat-state.svelte.ts`, `src/lib/chat-recovery.ts` (rewritten, kept permanent), `src/lib/sse-client.ts` (delete post-smoke)

- `firestore-stream.ts`: `subscribeToSession(sid, runId, callbacks)`:
  - `onSnapshot` on `sessions/{sid}` for status + `currentAttempt`.
  - `query(collectionGroup(db, 'events'), where('userId','==',uid), where('runId','==',runId), orderBy('attempt'), orderBy('seqInAttempt'))`. Filters to this user's + this turn's events and orders correctly. (Not a subcollection query — see spike D finding D.1.)
  - Client state `lastAttempt` / `lastSeqInAttempt` — skip on reconnect to avoid re-dispatching events already rendered.
  - On `currentAttempt` change (retry during the same run): clear `streamingActivities`, show brief "Retrying…" indicator, repopulate from the new attempt's events.
  - Ignore `fromCache=true` snapshots for `status=complete` transitions (avoid rendering stale cache as final state).
- `chat-state.svelte.ts`:
  - `send()`: POSTs `agentStream`, receives `{sessionId, runId}`, subscribes via `subscribeToSession(sid, runId, callbacks)`.
  - **Mount handler**: if URL has `?sid=…` and the conversation in localStorage ends with an unanswered user message (or no messages), read `sessions/{sid}` from Firestore. If `status ∈ {queued, running}`: subscribe to `currentRunId` and render live progress. If `status == 'complete'`: render the final reply. If `status == 'error'`: surface error with retry.
  - `switchTo(sid)`: same logic.
- `chat-recovery.ts` **kept, tightened**:
  - Triggers only when `onSnapshot` fires a `PERMISSION_DENIED` error OR no first-snapshot within 10 s.
  - Polls `agentCheck?sid=…&runId=…` every 3 s; surfaces final reply or error.
- UI tree untouched. `ChatThread.svelte` and `StreamingProgress.svelte` render from `streamingActivities` regardless of source.
- Delete `sse-client.ts` + `.spec.ts` after smoke passes.

**Observable outcome:** session survives tab close, mobile backgrounding, network changes. Refresh mid-pipeline shows current state. Multi-turn conversations work. Retries mid-run swap the view cleanly.

### Phase 6 — Cloud Tasks queue + IAM (½ day)

**Files:** one-off `gcloud` commands, documented in `docs/deployment-gotchas.md`

**Reference**: `cloudtasks.googleapis.com` is already enabled on `superextra-site` (done during validation). Spike C verified the OIDC end-to-end chain with the compute SA; parallel agent verified with a dedicated SA required both `serviceAccountUser` AND `serviceAccountTokenCreator` — hence both in the binding list below.

- Queue: `agent-dispatch` in `us-central1`:
  - `--max-attempts=3`, `--min-backoff=10s`, `--max-backoff=60s`, `--max-doublings=4`
- **IAM** (combined from Cloud Tasks docs + live-validated project recipe — a parallel validation pass against a dedicated scratch SA needed both bindings, so specify both to avoid first-deploy 403s):
  - Cloud Tasks service agent `service-907466498524@gcp-sa-cloudtasks.iam.gserviceaccount.com` needs **`roles/iam.serviceAccountUser`** on the worker SA.
  - Cloud Tasks service agent also needs **`roles/iam.serviceAccountTokenCreator`** on the worker SA. (Docs call out `serviceAccountUser` as sufficient; empirically, private Cloud Run OIDC delivery needed both in this project. Safe to grant both.)
  - Worker SA needs `roles/run.invoker` on itself.
  - `agentStream` Cloud Function SA needs `roles/cloudtasks.enqueuer` on the queue.
- OIDC audience: exactly the worker's `run.app` URL. No trailing slash, no custom domain.

### Phase 7 — `agentCheck` post-migration (½ day)

**File:** `functions/index.js`

- Takes `?sid=…&runId=…` query params.
- **Verifies Firebase ID token** (same pattern as `agentStream`). Rejects if absent or invalid. No App Check.
- Reads `sessions/{sid}` from Firestore via Admin SDK.
- **Explicit ownership check**: if `session.userId != decodedToken.uid`, return **403**. Admin SDK bypasses Firestore rules — the browser-side `allow read` rule does not protect this path. Without this check, any authenticated user with a known `sid` could read another user's reply/sources/title.
- Only after the ownership check passes: return `{status, reply, sources, title, error}`.
- Kept permanently as the REST fallback path.

### Phase 7.5 — Stuck-session watchdog (1 day)

**File:** `functions/watchdog.js` (scheduled Cloud Function, every 2 min via Cloud Scheduler)

Three queries, merged in code (Firestore can't OR across different fields from one composite index):

1. **Queued too long**: `status == 'queued' AND queuedAt < now - 30min` → `error, reason='queue_dispatch_timeout'`. Keyed on `queuedAt` (per-turn), not `createdAt` (per-conversation) — otherwise any follow-up turn on a conversation older than 30 min would be flagged the moment it was enqueued.
2. **Running, heartbeat silent**: `status == 'running' AND lastHeartbeat < now - 10min` → `error, reason='worker_lost', errorDetails={lastHeartbeatAge, currentAttempt}`.
3. **Running, pipeline wedged** (fresh heartbeat but no ADK events): `status == 'running' AND lastEventAt < now - 5min` → `error, reason='pipeline_wedged', errorDetails={lastEventAge, currentAttempt}`.

Union of (2) and (3) is the "running but silent" case. Each query uses its own composite index; results merged and deduped by `sid`.

**Backfill note**: on first deploy, existing session docs won't have `queuedAt`. Watchdog query includes `queuedAt != null` guard, and the first deploy runs a one-shot backfill (`queuedAt = createdAt` where null) so stale pre-migration docs are classified correctly.

The `lastEventAt` threshold (5 min) catches "heartbeat fresh but pipeline wedged" — specialists stuck on a hung tool call, Runner deadlock, etc. The heartbeat pulse alone doesn't prove the pipeline is progressing.

### Phase 8 — Deploy pipeline (1 day)

**File:** `.github/workflows/deploy.yml`

- Rename `deploy-agent` → `deploy-worker`. `gcloud run deploy superextra-worker --source=agent --timeout=1790 --no-cpu-throttling --memory=2Gi --max-instances=10 --concurrency=4 --no-allow-unauthenticated --service-account=superextra-worker@superextra-site.iam.gserviceaccount.com`.
- Agent code moves from `adk deploy cloud_run` generated wrapper to our own `agent/worker_main.py` + `agent/Dockerfile`.
- Retire the current `superextra-agent` Cloud Run service; merge its env vars into `superextra-worker`.
- Extend the existing `firebase deploy --only functions` step in `deploy-hosting` to also deploy Firestore rules and indexes: `firebase deploy --only functions,firestore:rules,firestore:indexes`. (The existing `--only functions` already covers the new `watchdog` function; no separate step needed.)

### Phase 9 — Observability + TTL (½ day)

**Files:** `agent/worker_main.py`, Firestore console, `firestore.indexes.json`

- Worker logs structured JSON keyed by `sid`, `runId`, `attempt`, `taskName`. Trace-context passthrough.
- Firestore TTL — two policies:
  1. `sessions` collection: `expiresAt` field, 30-day TTL. `gcloud firestore fields ttls update expiresAt --collection-group=sessions --enable-ttl`.
  2. `events` collection group: `expiresAt` field (set at write, equal to parent's `expiresAt`). `gcloud firestore fields ttls update expiresAt --collection-group=events --enable-ttl`.
- Firestore rules emulator tests in CI — confirm owner can read, non-owner can't, all writes denied.

### Phase 10 — Verification (1.5 days)

Two consecutive passes required before full rollout.

**Unit tests:**

- `firestore_events` Python tests against fixture Runner events.
- `firestore-stream.spec.ts`: mocks `onSnapshot`, verifies callback dispatch matches current `chat-state.spec.ts` expectations.
- Worker integration test: mocks `Runner.run_async`, asserts Firestore writes carry `userId`/`runId`/`attempt`/`seqInAttempt`, verifies fenced writes bail on ownership loss.
- **Runner exception propagation**: unit test that raises a synthetic exception mid-stream inside `runner.run_async()`. Assert (a) exception propagates out of the `async for`, (b) worker writes `status='error'` via fenced transaction, (c) heartbeat task is cancelled cleanly before the error write, (d) Cloud Tasks retry semantics trigger for infra-like errors vs. terminate for caught pipeline errors.
- **Plugin activation**: small worker-startup test that invokes `Runner(app=app, ...).run_async(...)` on a trivial request and asserts `ChatLoggerPlugin`'s hooks fire (or whichever plugin hook we verify). Confirms the `app=app` vs `agent=…` claim in Phase 3 step 4 holds in our worker context. If plugins don't fire, decide whether to manually instrument or drop the plugin before committing to Phase 8.
- Firestore rules emulator tests.

**Integration smoke (manual):**

1. **Desktop happy path**: full pipeline, progress renders from Firestore, final report lands.
2. **Multi-turn**: start conversation, complete turn 1, send turn 2 → verify new `runId`, new Cloud Task, agent follow-up routing works.
3. **Browser close at T+30 s**: worker logs + Firestore show `status=complete`; reopening shows the full report.
4. **Mobile backgrounding**: iOS Safari, background at T+60 s, foreground at T+5 min, again at T+30 min — state accurate each time.
5. **Page refresh mid-pipeline**: hard-reload at T+3, T+8, T+20 min — live progress each time, pipeline completes.
6. **Worker kill mid-run**: roll out a new revision. Pipeline completes on old revision OR retry on new revision.
7. **OOM mid-run**: force OOM. Within ~3 retries, either completes or watchdog → error.
8. **Double-send race**: spam Send during turn 1 → second request gets 409.
9. **Duplicate Cloud Tasks delivery**: force a retry before A finishes → B polls, returns A's result on completion.
10. **Concurrent-turns race**: send turn 2 while turn 1 still running → turn 2 gets 409 with "previous turn still in flight."
11. **Firestore-blocked client**: block `firestore.googleapis.com` in DevTools → `chat-recovery.ts` delivers final reply via `agentCheck`.
12. **Cross-session comeback**: start a query, close tab, wait 1 hour, reopen `?sid=…` URL → final report or error shown.
13. **Stale-worker overwrite**: force a takeover scenario, verify stale worker's status write is rejected by ownership fencing.
14. **Cross-user access attempt**: with user B's token, call `agentStream` and `agentCheck` against a `sid` owned by user A. Both must return 403. Repeat against the in-memory session cache (warm cache path).

No feature flag; `git revert` is the rollback.

## Files touched

**Modified:** `functions/index.js`, `functions/utils.js` (parseADKStream retired post-smoke), `agent/superextra_agent/specialists.py`, `agent/superextra_agent/agent.py`, `src/lib/chat-state.svelte.ts`, `src/lib/chat-recovery.ts` (rewritten), `.github/workflows/deploy.yml`, `firebase.json`

**New:** `agent/worker_main.py`, `agent/Dockerfile`, `agent/superextra_agent/firestore_events.py`, `functions/watchdog.js`, `src/lib/firebase.ts`, `src/lib/firestore-stream.ts`, `firestore.rules`, `firestore.indexes.json`

**Deleted post-smoke:** `src/lib/sse-client.ts`, `src/lib/sse-client.spec.ts`, `functions/utils.js` parseADKStream section

**Retired infrastructure:** standalone `superextra-agent` Cloud Run service (from `adk deploy cloud_run`) — replaced by `superextra-worker`.

## Reusable building blocks

- `ActivityItem` shape and `onActivity` upsert at `src/lib/chat-state.svelte.ts:29-40, 313-339` — source-agnostic; callback shape preserved.
- `ChatThread.svelte:246-303` and `StreamingProgress.svelte` — zero UI changes.
- `agent/superextra_agent/` package — imported wholesale into the worker; no changes to agent composition, instructions, or session service.
- Agent Engine session service (`agent_engine_id=2746721333428617216`) — kept; worker Runner connects via `VertexAiSessionService`.

## Risks + mitigations

| Risk                                                         | Mitigation                                                                                                                                                                                                                                                |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cloud Tasks default 10-min dispatch deadline breaks runs     | Explicit `--dispatch-deadline=1800s` on every enqueue.                                                                                                                                                                                                    |
| Pipeline p99 exceeds 1800s ceiling                           | Phase 0 is a gate: measure, confirm <22 min p99 before committing to Phase 3 (preserves ≥8 min headroom on the 30-min Cloud Tasks ceiling). If exceeded, revisit pipeline depth.                                                                          |
| `Runner(agent=…)` drops plugins silently                     | Use `Runner(app=app, …)`. Verified from source.                                                                                                                                                                                                           |
| Duplicate task delivery races two workers                    | Task-name dedup (runId) + atomic status txn + poll-wait for active owner + per-attempt seq + ownership fencing on status writes.                                                                                                                          |
| Stale worker overwrites new owner's state                    | Ownership fencing: `currentAttempt`+`currentWorkerId` checked on every status/heartbeat/terminal write. Stale worker's writes fail with `OwnershipLost`.                                                                                                  |
| Follow-up turn 2 collides with turn 1's task name            | `runId` is fresh per turn; session doc is upserted (not "create if absent").                                                                                                                                                                              |
| Watchdog falsely flags follow-up turns on old conversations  | Watchdog uses `queuedAt` (reset per turn) not `createdAt` (preserved). Composite index on `(status, queuedAt)`.                                                                                                                                           |
| Active conversation's TTL expires mid-use                    | `expiresAt` extended on every upsert via `max(existing, now + 30d)`. Never shrinks. Long-running conversations stay alive while in active use.                                                                                                            |
| Concurrent turns on same conversation                        | 409 if `status ∈ {queued, running}` when new `send()` arrives. User waits for turn 1 to finish.                                                                                                                                                           |
| Worker crashes (OOM → SIGKILL, revision drain)               | Cloud Tasks retry with backoff, max-attempts=3. Idempotent takeover picks up.                                                                                                                                                                             |
| Zombie heartbeat (pipeline deadlocked, worker process alive) | `lastEventAt` second signal — watchdog ORs both.                                                                                                                                                                                                          |
| All retries exhausted                                        | Watchdog flips to `status=error` within 10–12 min. User sees "Try again."                                                                                                                                                                                 |
| Cloud Run SIGTERM grace is 10 s fixed                        | Handler does only fenced heartbeat invalidate. Retry is the real cleanup.                                                                                                                                                                                 |
| `seq` ordering on `onSnapshot` reconnect                     | `(runId, attempt, seqInAttempt)` ordering + client skip-already-rendered.                                                                                                                                                                                 |
| Firestore TTL doesn't cascade                                | Two separate TTL policies. Collection-group TTL for events.                                                                                                                                                                                               |
| Corporate firewall / ad-blocker blocks Firestore             | `chat-recovery.ts` REST fallback with tightened trigger.                                                                                                                                                                                                  |
| App Check deferred → abuse risk                              | UID-based rate limit on `agentStream` + IP rate limit. App Check listed under "Deferred / future work" — add when abuse metrics justify it.                                                                                                               |
| Cloud Tasks OIDC audience mismatch                           | Audience = worker `run.app` URL exactly; documented.                                                                                                                                                                                                      |
| Composite index discovered at runtime                        | Enumerated in `firestore.indexes.json`, deployed in CI.                                                                                                                                                                                                   |
| ADK synthetic-error in reply                                 | Moot via in-process Runner. Reply sanity check before writing `complete`.                                                                                                                                                                                 |
| Cross-device continuity broken by anon auth                  | Documented out of scope; future account-linking work.                                                                                                                                                                                                     |
| Cross-user session hijack via leaked `sid`                   | Admin SDK bypasses Firestore rules — `agentStream` and `agentCheck` each do an explicit `session.userId == decodedToken.uid` check before any reuse, enqueue, or data return. Worker does a defense-in-depth check on the `userId` passed by agentStream. |

## Rollout order

Phase 0 (gate) → 1 → 6 → (2 + 3 parallel) → 4 → 5 → 7 → 7.5 → 8 → 9 → 10. **Phase 0 is the only truly independent phase.** Everything else depends on the schema/worker/IAM chain.

## Total effort estimate

~14 engineer-days baseline. Worst case (auth iteration, event-mapper parity debugging, Cloud Tasks IAM ironing, ADK Runner/plugin verification, ownership-fencing edge cases): ~17 days.

## Deferred / future work

- **App Check + reCAPTCHA Enterprise** — add when abuse metrics justify the complexity. reCAPTCHA Enterprise billing is tiered (10k assessments/month free, then `$8` up to 100k, then `$1`/1000 above) — real cost depends on session length, token TTL, and traffic volume.
- **Cross-device continuity** — account linking via email magic link. Product decision.
- **Multi-region Firestore (`nam5`)** — only if `us-central1` outages become measurable.
- **Firestore TTL single-field index exemption** — apply only if write-rate metrics show hotspotting per Firestore best-practices docs. Not needed at design-partner scale.
- **Pub/Sub push with larger ack deadline** — alternative to Cloud Tasks if we need >30-min runs. Deep architectural change; defer unless Phase 0 gate reveals pipeline depth issues.
