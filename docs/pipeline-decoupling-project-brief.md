# Pipeline-Decoupling Project Brief

**Audience**: teammates and reviewers coming in cold. Read this first.
**Purpose**: gives you the full context — what we tried to fix, why, how we designed it, how implementation went, and what's true in production today. Points you at the right document for deeper detail on each topic.
**Last updated**: 2026-04-21, post-deploy.

---

## 1. What the project was about

### The problem

Superextra's chat agent answers restaurant-research questions by running a multi-stage research pipeline (router → context enricher → research orchestrator → 3–8 specialists → gap researcher → synthesiser). That legitimately takes **2–15 minutes** per turn for a real query.

Pre-refactor, the entire pipeline ran over an **SSE (Server-Sent Events) connection** from the browser, through a Cloud Function (`agentStream`), to a separate ADK Cloud Run service (`superextra-agent`). If the browser connection broke at any point, the whole pipeline died.

This failed in a lot of practical situations:

- **Mobile Safari/Chrome backgrounding** — iOS suspends SSE streams within ~30 s when the tab is backgrounded. Switching away from the app mid-research killed the run.
- **Network roaming** (Wi-Fi ↔ 5G) — reconnection broke the stream.
- **Cloud Function timeouts** — we had a 440 s `AbortSignal.timeout` that killed long runs.
- **Page refresh** — dropped the connection, pipeline died.

On 2026-04-18 a design partner hit exactly this on a 440 s query; the UI hung at "Researching…" for ~9 min then surfaced a generic timeout. Logs showed the pipeline was killed mid-specialist at T+441 s. Design-partner mobile traffic was hitting this daily.

### The goal

Decouple pipeline execution from the browser connection. The browser should be able to close, background, refresh, or roam — the pipeline keeps running and the final answer shows up when the user returns. Plus auto-retry on infrastructure failures, no stuck sessions, and clean multi-turn conversations.

**Stable, not MVP.** No "good enough for now" corners that'll break at scale. But also not over-engineered.

### The new architecture

```
Browser
  │
  ├─ POST {sid, message} ───▶ agentStream (Cloud Function)
  │                                │
  │◀─ 202 {sid, runId} ────────────┤ verify ID token, ownership, rate limit
  │                                ├─ Firestore txn: upsert session doc
  │                                └─ enqueue Cloud Task ──────────▶
  │
  │                                                  Cloud Tasks (agent-dispatch queue)
  │                                                             │
  │                                                             ▼
  │                                             superextra-worker (private Cloud Run)
  │                                                     │
  │                                                     ├─ takeover txn + fenced writes
  │                                                     ├─ in-process ADK runner
  │                                                     │  (Runner(app=app))
  │                                                     ├─ writes progress events + terminal
  │                                                     │  state to Firestore
  │                                                     └─ heartbeat every 30 s
  │
  │── onSnapshot(sessions/{sid}) + collectionGroup(events) ─────◀ (real-time progress)
  │── agentCheck REST fallback ─────────────────────────────◀ (when Firestore blocked)
  │
  │   Cloud Scheduler (every 2 min) ─▶ watchdog (Cloud Function)
  │                                        │
  │                                        └─ flips stuck sessions → status='error'
```

**Key design decisions** (verified by spikes before implementation — see §3):

- Worker runs ADK in-process (`Runner(app=app)`), not as a separate HTTP service. Avoids ADK SSE bugs, keeps plugins firing, one moving part fewer.
- Cloud Tasks for enqueue, `--dispatch-deadline=1800s` + Cloud Run `--timeout=1790s` (ordering is load-bearing — prevents zombie workers).
- Firestore as the durable progress store. Browser is read-only; all writes via Admin SDK.
- `sid` (conversation ID) stable across turns; `runId` fresh per turn (also used as Cloud Tasks task name to avoid 24 h dedup collisions).
- Ownership fencing on every status write (`currentAttempt` + `currentWorkerId` compared in a transaction).
- A watchdog sweeps every 2 min and flips stuck sessions to `error` with a specific reason code.
- No App Check — UID rate-limit + IP rate-limit + explicit ownership checks. Firebase Anonymous Auth.

---

## 2. What success means

From `docs/pipeline-decoupling-plan.md` §"Requirements this has to meet":

- No stuck sessions, ever.
- Page refresh mid-pipeline works — shows current progress, pipeline keeps running.
- Users close the app, come back 30 min later — the answer is there.
- Auto-retry on infrastructure failure (no manual user action).
- Multi-turn conversations work — each follow-up turn enqueues cleanly on the same `sid`.
- Stable, not MVP.

---

## 3. Document map — read in this order

### Start here (this doc)

**`docs/pipeline-decoupling-project-brief.md`** — this brief, giving you the shape of everything.

### The design (authoritative)

**`docs/pipeline-decoupling-plan.md`** — the source of truth for the design. Read this second. It has: problem statement, architecture diagram, design decisions with rationale, phased plan (Phase 0 through 10), files touched, risks+mitigations, rollout order. If you only read one deeper doc after this brief, make it this.

**`docs/pipeline-decoupling-spike-results.md`** — 9 de-risk spikes run before committing to the plan. Each settled a non-obvious claim (ADK Runner invocation pattern, Cloud Tasks dispatch-deadline behaviour, Firestore index scopes, bundle size, SIGTERM semantics, etc.). Reference this if you want to understand _why_ the plan made specific choices.

### The build

**`docs/pipeline-decoupling-execution-log.md`** — the long-form record of what was built, phase by phase. Covers each of the 10 phases, plus a "Follow-up triage" section for post-review fixes, a live-E2E smoke record, and a final "Post-review polish" section. This is the best narrative for how the implementation actually unfolded.

### The audits (four rounds of adversarial review)

Each of these was an independent agent's critical review at a different stage. The findings fed back into code/doc changes. Read them in order if you want to see what was caught at each step:

1. **`docs/pipeline-decoupling-post-implementation-audit.md`** — first audit after the implementation landed. Flagged three P1s (router-final promotion, deploy ordering, watchdog fencing).
2. **`docs/pipeline-decoupling-followup-audit.md`** — audit after the first round of fixes. Confirmed no new regressions, flagged minor cleanups.
3. **`docs/pipeline-decoupling-fix-execution-audit.md`** — audit specifically of the fix-execution work, not the original implementation.
4. **`docs/pipeline-decoupling-final-predeploy-audit.md`** — the last pre-deploy audit. Confirmed transport work was ready; flagged residual agent-routing quality issues (out of refactor scope).

**`docs/pipeline-decoupling-fixes-plan.md`** — the reconciled plan for addressing the audit findings, with every claim re-verified against code before committing to a fix. The plan itself went through three review passes.

**`docs/pipeline-decoupling-fixes-plan-review.md`** — reviewer notes on the fixes plan.

### The deploy

**`docs/pipeline-decoupling-deploy-report.md`** — the full deploy story, attempt by attempt. 5 workflow runs + 3 post-merge fix commits, the IAM grants we had to discover, the adversarial post-deploy review that caught two more defects (one of them a multi-turn blocker), and the live user-flow verification via Chrome DevTools MCP.

### Operational docs

**`docs/deployment-gotchas.md`** — operator-facing gotchas for the new topology. Cloud Run worker config, Cloud Tasks IAM, Firestore index rollout ordering, watchdog `skipReasons` diagnostic, the single-job-rerun caveat, and the old `superextra-agent` retirement path.

**`AGENTS.md`** / **`CLAUDE.md`** — project-level developer instructions (same content in two files — AGENTS.md for humans, CLAUDE.md for Claude-based tooling). Includes the new transport architecture section.

---

## 4. Code map — key files

If you're reviewing changes, these are the load-bearing files to read:

### Backend (agent)

- `agent/worker_main.py` — FastAPI worker. Reads Cloud Tasks dispatches, runs ADK in-process, writes to Firestore. Takeover transaction, heartbeat, fenced writes, graceful cancellation. ~720 lines.
- `agent/superextra_agent/firestore_events.py` — ADK event → Firestore doc mapper. Stateless; tested against 27-event taxonomy fixture.
- `agent/Dockerfile` — minimal Python 3.12 + uvicorn runtime for the worker.
- `agent/requirements.txt` — worker deps (`google-adk`, `fastapi`, `uvicorn`, `google-cloud-firestore`).

### Backend (functions)

- `functions/index.js` — rewritten. `agentStream` is now POST-and-enqueue (returns 202, not SSE); `agentCheck` is a REST fallback. Both verify Firebase ID token and do explicit ownership check.
- `functions/watchdog.js` — scheduled Cloud Function, every 2 min. Fenced transactional flip of stuck sessions to `status=error` with `skipReasons` per-classifier counters.
- `functions/utils.js` — trimmed to what's still used (esc/row/confirmationHtml/stripMarkdown/checkRateLimit/validators). SSE-era exports retired.

### Frontend

- `src/lib/firestore-stream.ts` — Firestore observer transport. Two onSnapshot subscribers (session doc + collection-group events), fromCache + currentRunId guards, first-snapshot timeout.
- `src/lib/firebase.ts` — Firebase anon-auth + Firestore bootstrap. Dynamic import so marketing pages don't pay the bundle cost.
- `src/lib/chat-state.svelte.ts` — chat state machine. POSTs `agentStream`, subscribes via Firestore, handles runId-scoped dedup, "Retrying…" cue on attempt changes, graceful resume via `resumeIfInFlight`.
- `src/lib/chat-recovery.ts` — REST fallback via `agentCheck` polling when Firestore is blocked (corporate firewall / ad-blocker scenarios).

### Infrastructure

- `firestore.rules` — browser read-only. Owner gates on `resource.data.userId`. Collection-group wildcard on events.
- `firestore.indexes.json` — 4 composite indexes + 2 TTL field overrides (sessions.expiresAt, events.expiresAt).
- `.github/workflows/deploy.yml` — the deploy workflow. Three jobs: `test`, `deploy-worker`, `deploy-hosting` (which waits for `deploy-worker` when agent code changes).

---

## 5. Implementation outcome

### Scope delivered

- **10 phases** from the plan — all shipped.
- **4 rounds of external audit** — findings addressed or explicitly accepted, documented.
- **141 legacy pre-refactor session docs** deleted from production Firestore (incompatible schema, backed up locally first).
- **8 commits** on the feature branch + **7 follow-up commits** on main for deploy-time fixes.
- **Multi-turn conversation support verified live** in a real browser (not just a headless E2E).

### Test gate at the final state

| Suite                    | Count             | Notes                                                                                                                                       |
| ------------------------ | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Vitest                   | 77 pass           | Frontend unit tests                                                                                                                         |
| Functions (Node)         | 47 pass           | `agentStream`, `agentCheck`, `watchdog`, `utils`                                                                                            |
| Firestore rules emulator | 10 pass           | Session + collection-group events                                                                                                           |
| Agent pytest             | 140 pass / 7 fail | The 7 failures are all in `test_follow_up_routing.py`, CI-excluded, pre-existing live-LLM routing-quality issues unrelated to this refactor |
| svelte-check             | 0 errors          | 13 pre-existing UI warnings                                                                                                                 |
| ESLint                   | 0 errors          | 22 pre-existing warnings                                                                                                                    |
| Prettier `--check`       | clean             |                                                                                                                                             |

### Live verification

- **Headless E2E** (`agent/tests/e2e_worker_live.py`) against production: full pipeline completes, 119 kB reply, 5 sources, 290 s elapsed.
- **Real-user browser flow** via Chrome DevTools MCP: Anonymous sign-in → Places autocomplete → query → live activity stream → 129 kB report with embedded chart + 8 sources → follow-up turn via `follow_up` agent → grounded reply referencing turn-1 content.
- **Firestore state verified** end-to-end: correct `userId`, `adkSessionId` reused across turns, fresh `runId` per turn, `currentAttempt` resets per turn, `title` preserved, `sources` populated.

See `docs/pipeline-decoupling-deploy-report.md` for the step-by-step deploy narrative.

---

## 6. What's open / what's deferred

### Intentionally deferred, documented

- **`test_follow_up_routing.py` routing-quality failures** — 4–7 flaky live-LLM failures. Pre-existing, CI-excluded, unrelated to the transport refactor. Separate agent-instruction-quality workstream.
- **`placeContext` HTML / control-char stripping** — currently truncates but doesn't strip. LLM input surface only (no DOM sink renders it raw). Low priority, track for a hygiene pass.
- **Worker `--max-scale=10`** — combined with `--concurrency=1` this caps effective simultaneous pipelines at 10. Cloud Tasks queue allows up to 1000 concurrent dispatches; any burst above 10 queues and retries. Design-partner scale is well within this. If real traffic exceeds 10 simultaneous pipelines steadily, raise `--max-scale`.
- **Vertex AI "Session Event Append" per-minute quota** — hit once during an adversarial load-test blast. Request a raise proactively if steady-state traffic grows.
- **Agent Engine session cleanup cadence** — sessions auto-TTL at 364 days, no Firestore→AgentEngine reconciliation. Low disk cost at current volume.

### Manual operator cleanup (low priority)

1. Delete the retired `superextra-agent` Cloud Run service once you've confirmed no traffic still hits it:
   ```
   gcloud run services delete superextra-agent --region=us-central1 --project=superextra-site
   ```
2. Delete `legacy-sessions-backup.json` from the dev machine when confident no rollback is needed.

### Infrastructure-as-code debt

Four IAM grants + one API enablement were applied manually during rollout:

- `firebase-adminsdk-fbsvc@` → `roles/run.invoker` on `superextra-worker`
- `firebase-adminsdk-fbsvc@` → `roles/firebaserules.admin` on project
- `firebase-adminsdk-fbsvc@` → `roles/datastore.indexAdmin` on project
- `firebase-adminsdk-fbsvc@` → `roles/cloudscheduler.admin` on project
- API `cloudscheduler.googleapis.com` enabled on project

For a fresh-project deploy of this stack, these should be scripted (Terraform or a bootstrap shell) rather than rediscovered.

---

## 7. Suggested review paths

### If you have 15 minutes

Read this brief + `docs/pipeline-decoupling-plan.md` §"What we're building" + `docs/pipeline-decoupling-deploy-report.md` §1–2.

### If you have an hour

Add `docs/pipeline-decoupling-plan.md` full + `docs/pipeline-decoupling-execution-log.md` §"Post-implementation review (independent agent pass)" and the "Follow-up triage" section + `docs/pipeline-decoupling-deploy-report.md` full.

### If you're reviewing a specific area

| You care about                                | Read                                                                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Why we made a particular architectural choice | `docs/pipeline-decoupling-spike-results.md` — every non-obvious claim has a spike that settled it                     |
| What each phase of the rollout actually did   | `docs/pipeline-decoupling-execution-log.md` — phase-by-phase                                                          |
| Which bugs were found post-implementation     | `docs/pipeline-decoupling-post-implementation-audit.md` → `docs/pipeline-decoupling-fixes-plan.md`                    |
| Whether the deploy was clean                  | `docs/pipeline-decoupling-deploy-report.md` — no, it took 5 runs + 2 post-merge blocker fixes, but all are documented |
| Code that's safe to delete                    | `docs/pipeline-decoupling-execution-log.md` "Phase 10 / Deferred to post-smoke cleanup" section                       |
| How to operate this in prod                   | `docs/deployment-gotchas.md`                                                                                          |

---

## 8. Key facts for Q&A

- **Why Cloud Tasks over Pub/Sub?** Named-task dedup (one task name per `runId`), explicit dispatch deadline, idempotent-retry semantics documented by GCP. Pub/Sub ack-deadline ceilings and at-least-once semantics are equivalent but named-dedup is cleaner for our "one task per turn" model.
- **Why in-process ADK runner vs. HTTP to ADK Cloud Run?** The ADK HTTP server has two known open bugs (`/run_sse` close edge cases, HTTP/2 idle-reaping) that bite long runs. Running the runner in-process sidesteps both. Spike A verified `Runner(app=app, session_service=...)` preserves plugins + session state as expected.
- **Why `concurrency=1` on the worker?** The worker keeps per-request state in process globals (`_current_sid`, `_current_attempt`, `_current_worker_id`, `_heartbeat_task`). Two concurrent requests would stomp each other's globals. Cloud Run's "if your code can't handle parallel, set concurrency=1" applies exactly.
- **Why not SSE anymore?** Browser connections are unreliable in exactly the scenarios our users hit (mobile backgrounding, network roaming). Once we persist progress to Firestore, SSE adds no value and carries multiple real failure modes.
- **What happens if the worker crashes mid-pipeline?** Cloud Tasks retries (3 attempts, exponential backoff). Next attempt's takeover logic sees the stale heartbeat and takes over, bumping `currentAttempt`. The frontend sees the attempt change and clears the UI. Stuck sessions that never complete are caught by the 2-min watchdog and flipped to `error` within ≤10 min.
- **What happens if Firestore is blocked for the user** (corporate proxy / ad-blocker)? `onSnapshot` fires `PERMISSION_DENIED` or the first-snapshot timeout triggers → `chat-recovery.ts` falls back to polling `agentCheck` (Cloud Function) every 3 s for the reply.
- **How do we know the refactor actually fixed anything?** The live browser verification (see deploy report §5): closed and reopened a session, refreshed mid-run, and backgrounded the tab — all scenarios that killed the old SSE pipeline now work cleanly.

---

## 9. Status summary

**Architecture delivered**: Cloud Tasks + private worker + Firestore progress stream + REST fallback + watchdog + Firebase anon auth.

**Deploy**: shipped 2026-04-21 after 5 workflow runs + 3 post-merge commits. Fully green final state.

**Post-deploy adversarial verification**: 2 rounds, 1 blocker (multi-turn `follow_up` mapping) caught and fixed live. Everything else either passed or is explicitly accepted.

**Real-user flow verified**: single-turn and multi-turn conversations complete end-to-end with correct state, sources, titles, grounding, charts.

**This refactor is production-validated. The old SSE path is no longer part of any live code path; the retired `superextra-agent` Cloud Run service is left in place for an operator to delete after a day of clean traffic.**

Questions? Start with the authoritative design doc (`docs/pipeline-decoupling-plan.md`) and this brief. Deeper dives via §3 above.
