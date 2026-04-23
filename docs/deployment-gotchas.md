# Deployment Gotchas

The pipeline-decoupling refactor (design in `docs/pipeline-decoupling-plan.md`;
follow-up fixes in `docs/pipeline-decoupling-fixes-plan.md`) moved the agent
pipeline from `adk deploy cloud_run` + SSE Cloud Function to a Cloud Tasks →
private Cloud Run worker → Firestore progress stream. Gotchas below are for
the new topology. Pre-refactor notes (ADK deploy quirks, SSE GFE-proxy bypass)
were retired when those paths were deleted — see git history of this file if
you need them.

## Cloud Run worker (`superextra-worker`)

- **Build from source uses our `agent/Dockerfile`.** `adk deploy cloud_run` is
  gone (it silently swallowed deploy failures); the workflow now runs
  `gcloud run deploy superextra-worker --source=agent` with explicit flags
  (see `.github/workflows/deploy.yml:170-195`).
- **Cloud Run timeout `1790s` < Cloud Tasks `dispatchDeadline 1800s` is
  load-bearing.** Cloud Tasks `dispatch_deadline` does NOT cancel the inbound
  request; only Cloud Run's own timeout does. Keeping Cloud Run strictly below
  the queue's deadline prevents zombie workers outliving the retry.
- **Verify a revision actually shipped.** Even with `--source=` gcloud usually
  reports exit codes honestly, but the workflow keeps a before/after revision
  check (`deploy.yml:189-203`) because this was the failure mode under ADK.
- **`agent/.env` is NOT read at runtime in the container.** The file is copied
  into the image but uvicorn doesn't load it. Any env var the agent code needs
  (`GOOGLE_PLACES_API_KEY`, `SERPAPI_API_KEY`, `APIFY_TOKEN`, etc.) must be set
  as a Cloud Run service-level env var via `--update-env-vars` (see
  `deploy.yml:185`). **Adding a new env var:** add it as a GitHub secret, then
  append it to the `--update-env-vars` flag in the workflow.
  `--update-env-vars` merges (`--set-env-vars` would replace all).
- **Model routing is separate from session routing.** Some models
  (Gemini 3.1) only work via the global Vertex AI endpoint. `specialists.py`
  overrides `api_client` with `location='global'` on those instances. If
  adding new models, check regional availability first.
- **Filesystem is read-only** except `/tmp`. Detect Cloud Run via `K_SERVICE`.
- **ADK callbacks use keyword arguments.** Agent-level callbacks like
  `after_model_callback` receive `(*, callback_context, llm_response)` — not
  positional args. Wrong signatures cause silent TypeErrors.

## Cloud Tasks + OIDC

- **Queue `agent-dispatch` in `us-central1`** with `maxAttempts=3,
minBackoff=10s, maxBackoff=60s` (Phase 6).
- **`dispatch_deadline` is NOT a gcloud CLI flag.** Set it via the
  `@google-cloud/tasks` Node client on the Task resource's `dispatchDeadline`
  field (`functions/index.js` agentStream sets `{seconds: 1800}`).
- **IAM requires both `serviceAccountUser` AND `serviceAccountTokenCreator`**
  on the worker SA for the Cloud Tasks service agent. Docs say the former is
  sufficient; empirically, private Cloud Run OIDC delivery needs both in this
  project.
- **OIDC audience = worker `run.app` URL exactly.** No trailing slash, no
  custom domain. `WORKER_URL` is set at deploy time by
  `.github/workflows/deploy.yml`: the `deploy-hosting` job runs
  `gcloud run services describe superextra-worker --format='value(status.url)'`
  and writes the result to `functions/.env.superextra-site`, which
  firebase-functions v2 loads into `process.env` on deploy. Cloud Run URL
  format for this project is
  `<service>-<project-hash>-uc.a.run.app` (hash `22b3fxahka` in
  `superextra-site`); the code default (`functions/index.js`
  `DEFAULT_WORKER_URL`) follows this pattern as defense-in-depth for local
  runs. Older project-number URL format
  (`<service>-<project-number>.<region>.run.app`) still resolves on legacy
  services but is NOT what new services in this project get provisioned at.

## Firestore

- **Composite indexes must be rolled out before traffic hits
  `agentStream`.** `firestore.indexes.json` declares: the three `sessions`
  indexes for the watchdog's status+queuedAt / lastHeartbeat / lastEventAt
  sweeps, a `sessions(participants array-contains, updatedAt desc)` composite
  for the client sidebar listener, and the legacy
  `events (userId, runId, attempt, seqInAttempt)` collection-group index
  (unused after the per-session events listener migration — remove in a
  follow-up cleanup). First `firebase deploy --only firestore:indexes` on a
  new project takes ~5 min to reach ACTIVE; on an existing project with an
  empty `participants` field the composite becomes ACTIVE almost instantly.
- **Data shape is three-layer.** `sessions/{sid}` holds lightweight
  metadata + operational state (no terminal content). `sessions/{sid}/turns/{nnnn}`
  holds per-turn user message, reply, sources, and turn summary. `sessions/{sid}/events/{eid}`
  holds live activity for the in-flight turn.
- **Terminal source is the TURN doc.** The worker's `_fenced_update_session_and_turn`
  writes `status=complete` + `reply`/`sources`/`turnSummary` to the turn doc
  atomically with `status=complete` + `updatedAt` on the session doc. Old
  code (pre-rearchitecture) wrote terminal content to the session doc; that
  path is gone.
- **Events are per-session now.** The client observer queries
  `collection(db, 'sessions', sid, 'events')` with `where('runId','==',runId)`
  - `orderBy(attempt, seqInAttempt)`. No `userId` filter needed — reads are
    gated by the path-scoped rule. The legacy collection-group events query is
    no longer used.
- **Capability-URL rules.** `sessions/{sid}` allows `get` for any signed-in
  visitor; `list` requires `where('participants','array-contains',uid)` to
  match the rule; all writes are Admin-SDK-only. Subcollections
  (`turns`, `events`) allow path-scoped `read` for any signed-in visitor;
  writes server-only.
- **TTL only on events.** `events.expiresAt` is 3 days (was 30 days before
  the rearchitecture; bumped down because events are operational artifacts,
  not permanent transcript data). Sessions and turns have NO TTL — they
  persist until the creator deletes the chat via `agentDelete`.

## Watchdog (`functions/watchdog.js`)

- **Terminal flips are fenced in a transaction.** The txn re-reads the
  session and aborts if `status` / `currentRunId` / the stale `thresholdField`
  changed between the initial query and the write. Per-reason skip counters
  (`{missing, status_changed, run_advanced, field_freshened}`) are logged in
  the invocation summary — useful for ops debugging without full log trace.
- **Classifier precedence**: `queue_dispatch_timeout` > `worker_lost` >
  `pipeline_wedged`. `findStuckSessions` dedupes by `sid`.

## GitHub Actions deploy workflow

- **`deploy-hosting` waits for `deploy-worker`** via
  `needs: [test, deploy-worker]` + `if: always() && ... && (success ||
skipped)`. Hosting proceeds when the agent filter skips the worker deploy,
  and blocks when the worker deploy runs but fails.
- **Single-job rerun does NOT re-trigger dependent jobs.** If
  `deploy-worker` fails and the operator clicks "Re-run this job" alone,
  `deploy-hosting` stays skipped — GitHub Actions doesn't re-evaluate the
  `needs` graph for single-job reruns. Use "Re-run failed jobs" or re-run
  the whole workflow; a partial rerun can leave a fresh worker paired with
  stale hosting, undoing the rollout-ordering guarantee.
- **Worker-existence preflight** runs at the top of `deploy-hosting`
  (`setup-gcloud@v2` + `gcloud run services describe superextra-worker`).
  Fails fast if the worker service is missing (drift-catcher — not
  blocking if `deploy-worker` just ran).

## Retired service (`superextra-agent`)

Old `adk deploy cloud_run` target. No longer deployed to; intentionally left
in place during cutover so operators can verify the new worker before
deleting. When ready:

```bash
gcloud run services delete superextra-agent \
  --region=us-central1 --project=superextra-site
```

## Debugging

- **Worker logs**:
  `gcloud run services logs read superextra-worker --region=us-central1 --project=superextra-site --limit=50`
- **Worker env vars**:
  `gcloud run services describe superextra-worker --region=us-central1 --project=superextra-site --format="yaml(spec.template.spec.containers[0].env)"`
- **Worker health** (resolve URL first — the hash portion is project-stable
  but never hardcode it in one-off checks):
  `URL=$(gcloud run services describe superextra-worker --region=us-central1 --project=superextra-site --format='value(status.url)') && TOKEN=$(gcloud auth print-identity-token --audiences=$URL) && curl -H "Authorization: Bearer $TOKEN" $URL/healthz`
- **Cloud Function `agentDelete` from shell** (needs a Firebase ID token; only
  the creator's UID succeeds — contributors get 403):
  `curl -X POST "https://us-central1-superextra-site.cloudfunctions.net/agentDelete" -H "Authorization: Bearer $ID_TOKEN" -H "Content-Type: application/json" -d '{"sid":"SID"}'`
- **IAM check**: Cloud Function SA
  `907466498524-compute@developer.gserviceaccount.com` needs
  `roles/cloudtasks.enqueuer` on the `agent-dispatch` queue; worker SA
  `superextra-worker@superextra-site.iam.gserviceaccount.com` needs
  `roles/run.invoker` on the worker service itself plus
  `roles/datastore.user` and `roles/aiplatform.user` on the project.

## Live E2E via Chrome DevTools MCP

Ad-hoc real-prompt monitoring — drive the real UI against the real backend
and stitch the signals together. No harness, no automation, no new code;
all of this relies on observability that already exists (structured JSON
logs keyed by `sid`, Cloud Trace IDs embedded in every log line, sid in the
URL, Chrome DevTools MCP). Runs cost real Gemini/Places/SerpAPI/Apify
tokens and leave a permanent session + per-turn doc until the creator
deletes it via `agentDelete`; use sparingly, not as a CI gate.

1. **Navigate.** Chrome MCP `new_page` → `http://localhost:5199/agent/chat`.
   Anonymous Firebase auth bootstraps silently; no login or modal blocks
   the first prompt.
2. **Submit.** `fill` the textarea, `press_key` Enter (Shift+Enter is
   multiline — use Enter). Poll the page URL; once `?sid=<sid>` appears,
   the session id is yours. That's the only correlation key needed — the
   session doc carries `currentRunId` for anything deeper.
3. **Watch the user's view.** Periodic `take_screenshot` + `take_snapshot`
   while `chatState.loading` would be true (phase labels, elapsed timer,
   source counts, recovery/error banners, final typewriter text all render
   in the DOM). `list_console_messages` and `list_network_requests` give
   client-side signal for free.
4. **Backend logs, one command.** Worker JSON logs carry top-level `sid`:
   ```bash
   gcloud logging read 'jsonPayload.sid="<sid>"' \
     --project=superextra-site --limit=500 --format=json
   ```
   Every line also has `logging.googleapis.com/trace`. Open that URL in
   Cloud Trace — full waterfall across router → enricher → orchestrator →
   specialists → synthesizer. Usually the fastest way in.
5. **Firestore state.** Session doc `sessions/<sid>` (run status, fencing
   info, heartbeats, participants); turn docs `sessions/<sid>/turns/<nnnn>`
   (terminal reply, sources, turnSummary — this is the terminal source,
   not the session doc); events subcollection `sessions/<sid>/events`
   (in-flight activity, 3-day TTL). Firebase console works; so does
   `gcloud firestore documents describe sessions/<sid>`.

For backend-only reproduction (UI is innocent, want to isolate the worker),
`agent/tests/e2e_worker_live.py` drives the pipeline in-process against the
real stack without involving Chrome or the dev server.
