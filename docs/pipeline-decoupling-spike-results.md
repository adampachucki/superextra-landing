# Pipeline-decoupling spike results

Running log of de-risk spikes executed against the assumptions in `docs/pipeline-decoupling-plan.md`.

Each section records: what we tried, what happened, and what it implies for the plan.

## For implementers — read this section first

If you're picking up the implementation, these are the things we've already
verified or ruled out. Don't re-litigate them unless you hit contradicting
evidence.

### One-time environment setup you will need

- **Local ADC must have `cloud-platform` scope.** VM's GCE metadata SA doesn't.
  Fix: `export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<user>/adc.json`
  (the file written by `gcloud auth login` — has broad user scopes including
  cloud-platform). Spike A finding A.2.
- **Agent venv missing Firestore / Cloud Tasks libraries.** We pip-installed
  `google-cloud-firestore` and `google-cloud-tasks` into `agent/.venv/` during
  spikes; they are NOT yet in `agent/requirements.txt`. Add them as part of
  Phase 3's Dockerfile work.
- **Production dep change pending revert**: `package.json` picked up
  `"firebase": "^12.12.0"` from Spike G's `npm install --save`. Phase 1 adds
  this intentionally; the spike leak has been reverted on `main` before this
  commit.
- **`cloudtasks.googleapis.com` is already enabled** on `superextra-site`
  (done during parallel validation). No need to enable it again.

### Settled facts (do not re-validate)

- `Runner(app=app, session_service=VertexAiSessionService(project=…, location=…, agent_engine_id="2746721333428617216"))` is the correct invocation pattern. `Runner(agent=…)` silently drops `App.plugins` — verified from `google/adk-python` source. **Do not use `agent=`**.
- `VertexAiSessionService.create_session()` rejects user-provided `session_id`. Always let Agent Engine assign it; capture from `Session.id`.
- Multi-turn follow-up routing in `agent.py:230-237` reads `ctx.state.get("final_report")` from the Agent Engine session state. The in-process Runner path preserves this — verified in Spike A.
- `ChatLoggerPlugin` hooks fire correctly via `Runner(app=app, …)`. The plugin writes JSONL to `agent/logs/<date>_<sessionId>.jsonl` and covers `invocation_start`, `user_message`, `agent_start`, `model_request`, `model_response`, `adk_event`, `agent_end`, `invocation_end`.
- In-process Runner emits **zero partial-text events** with default `RunConfig`. The synthesizer's full reply arrives in a single final event. Don't add token batching / streaming logic until we explicitly enable it via `RunConfig(streaming_mode=...)` for a UX reason.
- Firestore `onSnapshot` delivers the full current dataset on its first callback, in `orderBy` order. No need to pre-seed client state from a separate `get()`.
- **Firestore query shape MUST be `collectionGroup(db, 'events')` with `where('userId','==',uid).where('runId','==',runId).orderBy('attempt').orderBy('seqInAttempt')`.** Subcollection queries on `sessions/{sid}/events` with the same filters REQUIRE a COLLECTION-scoped composite index, which `gcloud` CLI cannot create — they must go through `firestore.indexes.json` + `firebase deploy`. Avoid that path by using collection-group queries. Spike D finding D.1.
- Firestore composite index `(userId, runId, attempt, seqInAttempt)` COLLECTION_GROUP scope on `events` **already exists** in the project (created during Spike D, matches plan). It's the only production index needed for client reads. The plan's `firestore.indexes.json` will replicate it declaratively.
- Cloud Tasks `dispatch_deadline` is **not a gcloud CLI flag**. Set it via the Node `@google-cloud/tasks` client's `Task.dispatch_deadline` field. Same applies to Python.
- **Cloud Tasks `dispatch_deadline` does NOT cancel the handler.** The inbound Cloud Run request keeps running even after Cloud Tasks gives up and retries. Worker-side cancellation only happens at Cloud Run's own request timeout. Plan's `--timeout=1790 < dispatch_deadline=1800s` is therefore load-bearing (Spike H).
- **Cloud Run revision rollout does NOT kill in-flight requests.** Old revision instances drain; current requests finish up to the request timeout. Phase 8 deploys are safe (Spike I).
- Named-task dedup works: `Task.name=<runId>` + second enqueue with same name → `ALREADY_EXISTS`. This backs the plan's `runId`-as-task-name strategy. 24-hour dedup window post-deletion.
- Firebase v10 modular web SDK (`firebase/app` + `firebase/firestore` + `firebase/auth`) compiles to ~97 kB gzipped on the chat-route chunk (not the 200–250 kB the plan previously estimated).

### Known gotchas to plan around

- **Dedicated worker SA needs BOTH `roles/iam.serviceAccountUser` AND `roles/iam.serviceAccountTokenCreator`** on the Cloud Tasks service agent. My spike with the pre-privileged compute SA worked with just `serviceAccountUser`; the parallel agent's spike with a fresh SA needed both. Grant both to avoid a first-deploy 403 (Plan Phase 6).
- **Baseline has routing regressions unrelated to this refactor** — parallel agent observed `test_follow_up_routing.py`: 4 failures; `test_router_evals.py`: 2 failures. Some follow-ups that should hit `follow_up` fall through to `research_pipeline`. Track these separately from transport stability; fixing them is not this plan's scope.
- **Current `agentStream` and `agentCheck` are public** (`allUsers` invoker). Privatization moves into this plan (Phase 4 verifies ID token + App Check-free ownership check). Don't assume the baseline is already gated.
- **Agent Engine sessions persist.** Each spike run created a persistent session in Agent Engine. These are small but not garbage-collected on a short interval. Worth noting if doing high-volume testing during implementation.
- **Lint blocker**: `npm run lint` currently fails because `docs/pipeline-decoupling-plan.md` is not Prettier-formatted. Run `npx prettier --write docs/pipeline-decoupling-plan.md` before committing any subsequent edits.

### Reading order for implementers

1. `docs/pipeline-decoupling-plan.md` — the actual plan.
2. This file (`pipeline-decoupling-spike-results.md`) — for every claim the plan makes, the evidence is here.
3. `docs/pipeline-decoupling-review.md` — final review round's findings; shows the plan's iteration history.
4. `docs/pipeline-decoupling-validation-findings.md` — parallel validation agent's independent pass.
5. `spikes/README.md` + `spikes/adk_event_taxonomy_dump.json` — concrete fixture for Phase 2 test-writing.

### Artifacts you can reuse

- **`spikes/preflight_check.sh`** — run first. Green → safe to start. Catches every env-setup mistake we hit during validation.
- **`spikes/skeletons/worker_main.py`** — reference FastAPI handler for Phase 3: takeover txn, fenced writes, heartbeat task, ADK Runner event loop, SIGTERM handler — all wired together. ~250 lines. TODOs mark fill-in points.
- **`spikes/skeletons/firestore_events.py`** — reference event mapper for Phase 2: dispatcher by author + event type → Firestore event docs. Uses the taxonomy rules table below.
- **`spikes/adk_event_taxonomy_dump.json`** — 27 real ADK Events from a full-pipeline run. **Use as Phase 2 mapper test fixture.** Exact shapes documented in "B — Event taxonomy" section below.
- `spikes/cloudtasks_oidc/main.py` — minimal FastAPI + OIDC echo pattern. Phase 3's worker reuses the `X-CloudTasks-*` header handling.
- `spikes/firestore_rules_test.js` — mocha test-file starter. Move to repo root, extend during Phase 1.
- `spikes/adk_runner_spike.py` — reference invocation pattern for `Runner(app=app, ...)` + `VertexAiSessionService`.

### Reference docs we actually read (not every doc Google has, just the ones that mattered)

- [Cloud Tasks: Create HTTP target tasks](https://cloud.google.com/tasks/docs/creating-http-target-tasks) — OIDC flag semantics, retry config.
- [Cloud Tasks: Configuring queues (retry)](https://cloud.google.com/tasks/docs/configuring-queues#retry) — `max-attempts`, backoff semantics.
- [Cloud Tasks: Common pitfalls — duplicate execution](https://cloud.google.com/tasks/docs/common-pitfalls#duplicate_execution) — at-least-once delivery explicitly called out.
- [Cloud Run: Request timeout](https://cloud.google.com/run/docs/configuring/request-timeout) — max 3600 s.
- [Cloud Run: Container contract — instance shutdown](https://cloud.google.com/run/docs/container-contract#instance-shutdown) — 10 s SIGTERM grace, fixed.
- [Cloud Run: Authenticating service-to-service](https://cloud.google.com/run/docs/authenticating/service-to-service) — OIDC audience semantics.
- [Firestore: Realtime listeners](https://firebase.google.com/docs/firestore/query-data/listen) — first-callback delivery behaviour.
- [Firestore: Indexing](https://firebase.google.com/docs/firestore/query-data/indexing) — COLLECTION vs COLLECTION_GROUP scopes (where we got burned).
- [Firestore: Security rules structure](https://firebase.google.com/docs/firestore/security/rules-structure) — subcollection rules don't inherit.
- [Firestore: TTL](https://firebase.google.com/docs/firestore/ttl) — no cascade; per-collection-group policies.
- [Firebase App Check: Custom backend verification](https://firebase.google.com/docs/app-check/custom-resource-backend) — API shape if we add App Check in the future.
- [ADK Python source — `Runner`](https://github.com/google/adk-python/blob/main/src/google/adk/runners.py) — the `app=app` vs `agent=…` distinction.
- [ADK Python — `VertexAiSessionService`](https://github.com/google/adk-python/blob/main/src/google/adk/sessions/vertex_ai_session_service.py) — constructor signature.
- [ADK Python issue #4216](https://github.com/google/adk-python/issues/4216) — `/run_sse` close edge case (we avoid by going in-process).
- [ADK Python issue #4244](https://github.com/google/adk-python/issues/4244) — `/run_sse` swallows exceptions as synthetic text (avoided by in-process).

## TL;DR — plan deltas

All 9 spikes ran to verdict. No showstoppers. Four plan changes needed:

1. **Client query shape**: `collectionGroup('events')` instead of subcollection query (Spike D). `firestore.indexes.json` gets a `(userId, runId, attempt, seqInAttempt)` COLLECTION_GROUP composite. Rules use `match /{path=**}/events/{eid}` with `userId` check instead of a nested events match.
2. **Event mapper simpler than planned**: no partial-text events observed from in-process Runner by default. Drop the 250 ms token batching language. Phase 2 realistic scope drops from 2 d → ~1.5 d (Spike B).
3. **Bundle size estimate was 2× pessimistic**: actual Firebase gzipped chunk is 97 kB, not 200–250 kB (Spike G). Prose tweak in Phase 1.
4. **Agent Engine assigns session IDs**: `VertexAiSessionService.create_session()` does not accept user-provided `session_id`. Plan's data model already separates `sid` from `adkSessionId`; just clarify in Phase 4 step 6 that `adkSessionId` is received from the service (Spike A, finding A.1).

Two plan confirmations (no change needed, but worth knowing):

- Cloud Run timeout < Cloud Tasks dispatch_deadline is **load-bearing** (Spike H verified dispatch_deadline does not cancel in-flight handlers).
- Revision rollout does NOT kill in-flight requests (Spike I). SIGTERM handler is nice-to-have only for scale-down edge cases, not deployment safety.

## Findings so far

### A — ADK Runner in-process (complete)

**Finding A.1** — `VertexAiSessionService.create_session()` does **not** accept a user-provided `session_id`. Agent Engine assigns the ID; caller must capture it from the returned `Session.id`.

Plan impact: minor prose tweak. The plan already separates `sid` (our Firestore conversation ID) from `adkSessionId` (Agent Engine's ID), so the data model is right. But Phase 4 step 6 ("Ensure ADK session exists in Agent Engine, reuse existing session-cache logic") should explicitly note that `adkSessionId` is received from the service at create time, not generated client-side.

**Finding A.2** — VM's GCE-metadata ADC doesn't have `cloud-platform` scope. For local spikes, set `GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/legacy_credentials/<user>/adc.json` (the file `gcloud auth login` writes) — those user creds include `cloud-platform`. Production code is unaffected (Cloud Run's metadata SA has whatever scopes we grant the worker SA).

Plan impact: none at the plan level. Add to `docs/deployment-gotchas.md` for future local-dev spikes.

**Verdicts (all PASS)**:

| Assumption                                                                                                                                | Result                                                                                                                                                                                                   |
| ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Runner(app=app, session_service=VertexAiSessionService(...))` constructs                                                                 | ✅                                                                                                                                                                                                       |
| `run_async` yields events (`author='router'`, `is_final=True`, `state_delta=['router_response']` after ~3.9 s for a trivial "hi" message) | ✅                                                                                                                                                                                                       |
| `ChatLoggerPlugin` hooks fire via `Runner(app=app)`                                                                                       | ✅ — 8 plugin entries written to `agent/logs/<date>_<sessionId>.jsonl`: `invocation_start`, `user_message`, `agent_start`, `model_request`, `model_response`, `adk_event`, `agent_end`, `invocation_end` |
| Session state persisted in Agent Engine                                                                                                   | ✅ — re-fetched session had `state_keys=['router_response']` and 2 events                                                                                                                                |

**Finding A.3 (implementation detail for worker)** — After `Runner.run_async()` completes for a message, Agent Engine session has 2 events (user message + router response). These are what `ctx.state.get("final_report")` and friends read on subsequent turns. Confirms multi-turn follow-up routing logic (`agent.py:230-237`) will work through in-process Runner.

**What A did NOT cover** — only captured one event because the "hi" query produced an immediate router-final response (no placeContext → router short-circuited). Deeper event types (function_call, function_response, partial-text streaming, grounding_metadata, specialist `state_delta`s) are Spike B's scope.

### B — Event taxonomy (complete)

**Script**: `spikes/adk_event_taxonomy_spike.py` — runs a real restaurant-research query ("What service issues come up in reviews?" against Umami Berlin) through the full pipeline, captures up to 50 events with a 3-min timeout.

**Result**: Pipeline completed end-to-end in **163 s** (2:43) with 21 events. Full dump at `spikes/adk_event_taxonomy_dump.json`.

**Taxonomy observed**:

| Dimension                 | Values                                                                                                                                                                                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Authors (14)              | `router`, `context_enricher`, `research_orchestrator`, `market_landscape`, `menu_pricing`, `revenue_sales`, `location_traffic`, `operations`, `marketing_digital`, `dynamic_researcher_1`, `review_analyst`, `guest_intelligence`, `gap_researcher`, `synthesizer` |
| Function calls            | `transfer_to_agent`, `get_restaurant_details`, `set_specialist_briefs`, `find_tripadvisor_restaurant`                                                                                                                                                              |
| State_delta keys          | `_target_lat`, `_target_lng`, `_web_search_queries` (internal), `places_context`, `specialist_briefs`, `research_plan`, `review_result`, `guest_result`, `dynamic_result_2`, `final_report`                                                                        |
| `is_final=True` events    | 13 of 21                                                                                                                                                                                                                                                           |
| Grounding-metadata events | 3 (from `review_analyst`, `guest_intelligence`, `gap_researcher`)                                                                                                                                                                                                  |
| Partial-text events       | **0**                                                                                                                                                                                                                                                              |

**Finding B.1** — agent-to-agent delegation manifests as a `transfer_to_agent` function-call event on `author=router` followed by a function-response on the same author. The actual transfer target is in the function-call args. The Phase 2 mapper needs to recognize this as "routing" rather than misinterpret as a tool call.

**Finding B.2** — specialists that don't get a brief (via `_make_skip_callback`) emit a single `is_final=True` event with **no state_delta** at their output_key. Currently 6 of 9 specialists skipped on this "service issues" query (correct routing). Mapper rule: `is_final=True` + author is a specialist + no output_key in state_delta → don't emit a UI activity (same as today's parseADKStream behavior).

**Finding B.3** — specialists that produce output (`review_analyst`, `guest_intelligence`, `gap_researcher`) emit `is_final=True` with their output_key in state_delta. The text content is on the event's `content.parts[].text`. The `grounding_metadata.grounding_chunks` on those events carries source URLs — the plan's Phase 2 "source harvesting from `grounding_metadata.grounding_chunks`" is confirmed feasible.

**Finding B.4 (plan simplification)** — **no partial-text events were emitted** in this run. Current SSE pipeline's parseADKStream has elaborate partial-text coalescing logic because SSE streams partials. In-process Runner (at least with default `RunConfig`) emits only final events. This means:

- The "250 ms token batching" item in the plan is moot and can be deleted — there are no tokens to batch.
- Synthesizer produces its full report in a single event; worker writes it once.
- Phase 2 event-mapper is simpler than expected. Realistic scope drops from "2 days" to "1–1.5 days".

(Caveat: this was observed with default `RunConfig`. If we ever want partial streaming for UX reasons, we'd set `RunConfig(streaming_mode=StreamingMode.SSE)` on `run_async` — worth testing separately before ruling out. For now, default non-partial behavior is simpler and sufficient.)

**Finding B.5 (Phase 0 signal)** — a real narrow query ("service issues in reviews") completed in 163 s, 6 of 9 specialists skipped because orchestrator only briefed the 3 relevant ones. A deep cross-all-specialists query would run specialists in parallel and be bounded by the slowest single specialist + the synthesizer, so maybe 5–10 min realistically. p99 < 22 min for the Phase 0 gate looks comfortable. Not conclusive — need more representative runs to call Phase 0 PASS.

**Mapper scope (final-events only)** — the Phase 2 mapper needs to handle exactly these rules:

| Trigger                                                                         | Emit                                                             |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `author=router` with `transfer_to_agent` function_call                          | progress "routing" (optional; UI doesn't need it)                |
| `author=context_enricher` function_call on Places tool                          | activity category=data, status=running                           |
| `author=context_enricher` function_response on Places tool                      | activity category=data, status=complete (accumulate place names) |
| `author=context_enricher` `is_final=True` + `places_context` in state_delta     | progress "context done"                                          |
| `author=research_orchestrator` `set_specialist_briefs` function_call            | pending activity entries for each briefed specialist             |
| `author=research_orchestrator` `is_final=True` + `research_plan` in state_delta | progress "planning done"                                         |
| Specialist `author=X` function_call on `google_search` or `fetch_web_content`   | activity category=search                                         |
| Specialist `author=X` function_response                                         | activity status update                                           |
| Specialist `author=X` with `grounding_metadata.grounding_chunks`                | activity category=read (one per chunk)                           |
| Specialist `author=X` `is_final=True` + `<X>_result` in state_delta             | activity category=analyze, status=complete                       |
| Specialist `author=X` `is_final=True` with no state_delta                       | skip (NOT_RELEVANT)                                              |
| `author=synthesizer` `is_final=True` + `final_report` in state_delta            | complete event with reply + sources                              |

This is a ~150-line Python mapper. Testable with fixture events from this spike's `adk_event_taxonomy_dump.json`.

### D — Firestore query + index + rules (complete)

**Script**: `spikes/firestore_query_spike.py` (initial subcollection-query version) + follow-up inline Python verifying collection-group pattern.

**Finding D.1 (PLAN CHANGE REQUIRED)** — `COLLECTION_GROUP`-scoped composite indexes **do not** cover subcollection-scoped queries. Empirically: I created a `COLLECTION_GROUP`-scoped index on `events` with `(runId, attempt, seqInAttempt)`, confirmed it READY, and then ran `db.collection('sessions').document(sid).collection('events').where('runId','==',X).order_by('attempt').order_by('seqInAttempt')` — it returned `FAILED_PRECONDITION: The query requires an index`. The equivalent `collectionGroup()` query on the same data returned `SUCCESS`.

This contradicts the plan's assumption that the plan's `events (runId, attempt, seqInAttempt) COLLECTION_GROUP` index in `firestore.indexes.json` covers the subcollection client query. Subcollection-scoped queries need `COLLECTION`-scoped indexes, which gcloud CLI can't create and must be pushed via `firebase.json`/`firestore.indexes.json`.

**Recommendation (simpler than juggling index scopes)**: use a **collection-group query** on the client:

```ts
query(
	collectionGroup(db, 'events'),
	where('userId', '==', uid),
	where('runId', '==', runId),
	orderBy('attempt'),
	orderBy('seqInAttempt')
);
```

Verified to work with a single COLLECTION_GROUP-scoped index on `(userId, runId, attempt, seqInAttempt)`. 20 docs returned in correct order; cross-user events correctly excluded (via the `userId` filter, not rules).

**Plan changes that flow from D.1**:

- Update `firestore.indexes.json` entry for `events` to include `userId` as the leading field: `(userId ASC, runId ASC, attempt ASC, seqInAttempt ASC)`.
- Update rules from nested `match /sessions/{sid}/events/{eid}` to a `match /{path=**}/events/{eid}` recursive wildcard (required for `collectionGroup` reads) — still gated on `userId == request.auth.uid`.
- Update `firestore-stream.ts` in Phase 5 to use `collectionGroup(db, 'events')` instead of `collection(db, 'sessions', sid, 'events')`. Same callback shape, same filters; just a different collection reference.
- Ensure `userId` is indeed set on every event write (already in Phase 2 mapper signature).

**Finding D.2** — `onSnapshot` delivers full current state in one callback (20/20 docs), in order `(attempt ASC, seqInAttempt ASC)`. Refresh-mid-pipeline recovery path confirmed feasible. First listener subscription transiently fails while an auto-generated internal index builds (~30 s one-time cost after first deploy); then works. Test code already handles — no plan change needed.

**Finding D.3 (CORRECTED)** — earlier I claimed gcloud can't create COLLECTION-scoped indexes. That's **wrong**: `gcloud firestore indexes composite create --query-scope=collection ...` is supported and is in fact the CLI default (valid values: `collection`, `collection-group`, `collection-recursive`). The COLLECTION-scoped alternative to our collection-group design was viable. We chose collection-group queries because they give a cleaner unified index + rule shape (one index covers all sessions), not because of CLI limitations.

**Verdicts**:

| Assumption                                      | Result                               |
| ----------------------------------------------- | ------------------------------------ |
| Composite index covers the client event query   | ✅ with collection-group query shape |
| Query orders by `(attempt, seqInAttempt)`       | ✅                                   |
| Cross-user event isolation (userId filter)      | ✅                                   |
| `onSnapshot` first callback delivers full state | ✅                                   |

### G — Firebase SDK bundle size (complete)

**Script**: `spikes/bundle_size_spike.js` — creates a throwaway Svelte route that imports `firebase/app` + `firebase/firestore` + `firebase/auth`, runs `npm run build`, measures resulting chunks.

**Result**: modular Firebase v10 SDK compiled into a single lazy-loaded chunk of **312.7 kB raw, 97 kB actual gzipped** (measured with `gzip -c | wc -c`, not estimated).

**Finding G.1** — my plan claimed "200–250 kB gzipped." Actual is ~97 kB. Plan overstated by ~2×. Tree-shaking in Vite/Rollup is more effective than my estimate.

**Plan change**: update the Phase 1 bundle-size sentence. No architectural impact — just adjust prose.

**Verdicts**:

| Assumption                                     | Result                                                                       |
| ---------------------------------------------- | ---------------------------------------------------------------------------- |
| Firebase SDK adds bounded weight to chat route | ✅ (~97 kB gzipped)                                                          |
| Dynamic-import keeps marketing bundle clean    | ✅ (confirmed: firebase only appears in the spike-page chunk, not in shared) |

### C — Cloud Tasks → Cloud Run OIDC (complete)

**Script**: `spikes/cloudtasks_oidc/main.py` deployed as a throwaway `spike-echo` Cloud Run service with the compute SA. Cloud Tasks queue `spike-queue` created with `max-attempts=3, min-backoff=10s, max-backoff=60s`. IAM bindings:

- `serviceAccountUser` on worker SA granted to Cloud Tasks service agent.
- `run.invoker` on `spike-echo` granted to worker SA.
- `cloudtasks.enqueuer` on project granted to the user for enqueue testing.

Task enqueued via Python `google-cloud-tasks` client with `oidc_token.audience = worker run.app URL`.

**Verdicts**:

| Assumption                                                                        | Result                                                                        |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Queue + OIDC IAM bindings as specified in Phase 6 work end-to-end                 | ✅                                                                            |
| OIDC token reaches Cloud Run and is accepted (request 200s)                       | ✅                                                                            |
| `X-CloudTasks-TaskName` header is the task's explicit name (when `task.name` set) | ✅ (`run-id-dedup-test-…` name reflected back correctly)                      |
| `X-CloudTasks-TaskRetryCount` / `TaskExecutionCount` headers present              | ✅ (both appeared on first delivery with value `0`)                           |
| Named-task dedup: same task name within dedup window → `ALREADY_EXISTS`           | ✅ (second enqueue with identical name returned `ALREADY_EXISTS` immediately) |
| Dispatch latency: queue → handler                                                 | ~15 s end-to-end in testing (first dispatch)                                  |

**Finding C.1 (plan prose tweak)** — `gcloud tasks create-http-task` does NOT support `--dispatch-deadline`. The real agentStream implementation (Node `@google-cloud/tasks` client) does — it's on the Task resource's `dispatch_deadline` field. Plan's Phase 4 step 7 already describes this correctly; just worth calling out in `docs/deployment-gotchas.md` that CLI and library differ here.

### H — Cloud Tasks dispatch-deadline behaviour (complete)

**Setup**: task with `dispatch_deadline=30s`, handler `/sleep?seconds=90`.

**Key finding**: the handler **ran to completion for all 90 s** — Cloud Tasks did NOT propagate cancellation to the handler coroutine. Cloud Tasks marked the attempt as failed at T+30 s (in its own state) and retried, but the original Cloud Run instance kept processing the request.

**This confirms Finding 2 from earlier review rounds is load-bearing**: the plan's `Cloud Run timeout (1790s) < Cloud Tasks dispatch_deadline (1800s)` is **mandatory**. Without it, zombie workers outlive retries. With it, Cloud Run cancels the request at its own timeout (1790 s), returning control to the container before Cloud Tasks gives up at 1800 s — clean handoff.

Also observed: with `dispatch_deadline=30s` and `sleep=90s`, Cloud Tasks retried aggressively while the original was still running — multiple worker instances ran the same task concurrently. The plan's idempotent-takeover + ownership-fencing pattern (Phase 3 step 2 + 6) is what protects us from this.

**Verdicts**:

| Assumption                                                                    | Result                                              |
| ----------------------------------------------------------------------------- | --------------------------------------------------- |
| Cloud Tasks dispatch-deadline does NOT cancel in-flight handlers              | ✅ (confirmed — handler ran the full 90 s)          |
| Concurrent-retry race happens when deadline < handler duration                | ✅ (observed multiple simultaneous worker attempts) |
| Cloud Run timeout < dispatch-deadline is the only way to avoid zombie workers | ✅ (follows from above)                             |

### I — SIGTERM during revision rollout (complete)

**Setup**: enqueue `/sleep?seconds=60`, 5 s later trigger a new revision deploy of the echo service.

**Key finding**: the in-flight request **ran to completion without a SIGTERM** during the 60-second window. Cloud Run's standard behaviour: a new revision's deployment does not send SIGTERM to old-revision instances that are actively serving requests. Old instances drain gracefully as their active requests finish; they stop receiving new requests but are allowed to complete their current ones up to the request timeout.

**Implications for plan**:

- The SIGTERM handler in Phase 3 step "SIGTERM handler (10 s fixed grace)" is only invoked when the instance is actually being scale-in-terminated (not on revision rollout mid-request).
- Worker crashes we need to survive are: OOM (no SIGTERM), request-timeout expiry, Cloud Run instance scale-down (rare). The SIGTERM-invalidate-heartbeat path exists for the last case and is a nice-to-have, not load-bearing.
- Phase 8's deploy pipeline is safer than I feared: rolling out a new worker revision during an active long-running task does NOT kill that task. The in-flight specialist finishes on the old revision; next Cloud Tasks delivery goes to the new revision.

**Verdicts**:

| Assumption                                            | Result                        |
| ----------------------------------------------------- | ----------------------------- |
| Revision rollout allows in-flight requests to finish  | ✅                            |
| SIGTERM handler required for Phase 8 deploy safety    | ❌ nice-to-have, not required |
| SIGTERM handler still useful for scale-down edge case | ✅ keep as designed           |

### E — Phase 0 measurement (preliminary)

Two data points, pre-Phase-0 (HIGH thinking still on all specialists):

| Query                                                                                                       | Duration       | Events | Specialists run                                                      |
| ----------------------------------------------------------------------------------------------------------- | -------------- | ------ | -------------------------------------------------------------------- |
| "What service issues keep coming up in reviews?" (narrow)                                                   | 163 s (2:43)   | 21     | review_analyst, guest_intelligence, dynamic_researcher_1 (6 skipped) |
| "Full competitive analysis: market, pricing, revenue, sentiment, location, ops, marketing, reviews" (broad) | 244.9 s (4:05) | 27     | likely most/all specialists                                          |

**Preliminary verdict**: both runs complete in <5 min, well under the 22 min Phase 0 gate. Phase 0 speedups (MEDIUM thinking on 4 specialists + enricher) will reduce further. Phase 0 gate is highly likely to PASS.

**Caveat**: n=2 is too small to call p99. Formal Phase 0 should run 10+ representative queries (ranging from narrow single-specialist to deep multi-specialist + long-thinking queries with complex restaurants). But the preliminary signal is strong enough that Cloud Tasks' 30-min ceiling is very unlikely to bite.

### F — Rules emulator test suite (starter written)

**File**: `spikes/firestore_rules_test.js` — ready-to-run mocha test suite using `@firebase/rules-unit-testing`. Covers:

- Session owner can read own doc; non-owner and unauthenticated can't.
- Owner cannot write session doc (server-only).
- Collection-group query over events works for owner filtering on own userId + runId.
- Non-owner query attempting to read others' events is denied.
- Owner cannot write events (server-only).

Setup for Phase 1 implementer:

```
cd spikes
npm install --save-dev @firebase/rules-unit-testing mocha chai@4 firebase
firebase emulators:exec --only firestore "npx mocha firestore_rules_test.js --timeout 10000"
```

Once Phase 1 lands, move this file to the repo root and extend as the rules evolve.

## Status

| #   | Spike                                   | Status                    | Plan impact                                                         |
| --- | --------------------------------------- | ------------------------- | ------------------------------------------------------------------- |
| A   | ADK `Runner(app=app)` in-process        | **PASS**                  | no plan change; small prose tweak to Phase 4                        |
| B   | Event taxonomy mapping                  | **PASS**                  | simplifies plan (no partials)                                       |
| C   | Cloud Tasks → Cloud Run OIDC            | **PASS**                  | no plan change                                                      |
| D   | Firestore query + index + rules         | **PASS with plan change** | query goes collection-group; rules use `{path=**}` wildcard         |
| E   | Phase 0 measurement (p99 gate)          | **PASS (preliminary)**    | 2 data points, both well under gate; needs more runs during Phase 0 |
| F   | Rules emulator test suite               | **Starter written**       | file ready for Phase 1 TDD                                          |
| G   | Firebase SDK bundle size                | **PASS**                  | bundle estimate in plan is 2x pessimistic (~97 kB actual gzipped)   |
| H   | Cloud Tasks dispatch-deadline behaviour | **PASS**                  | confirms Cloud Run timeout < dispatch deadline is mandatory         |
| I   | SIGTERM on revision rollout             | **PASS**                  | revision rollout lets in-flight requests finish                     |
