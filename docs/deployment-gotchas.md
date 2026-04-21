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
  `agentStream`.** `firestore.indexes.json` declares four indexes:
  `events (userId, runId, attempt, seqInAttempt)` collection-group for the
  client observer; plus three `sessions` indexes for the watchdog's
  status+queuedAt / lastHeartbeat / lastEventAt sweeps. First `firebase
deploy --only firestore:indexes` takes ~5 min to reach ACTIVE; agentStream
  will fail reads until then.
- **Events write via plain `ref.set(...)` — unfenced.** The client observer
  in `src/lib/firestore-stream.ts` deliberately ignores `type='complete'`/
  `'error'` event docs to prevent a fenced-out stale worker from leaking a
  terminal via the events stream. The **session doc** (fenced via
  `_fenced_update` in the worker) is the only terminal source.
- **Events carry `userId` denormalized.** The collection-group rule
  (`match /{path=**}/events/{eid}` in `firestore.rules:17-22`) reads
  `resource.data.userId` directly — no `get()` into the parent session. The
  client query MUST include `where('userId','==',uid)` or it 403s.
- **TTL does NOT cascade.** Two separate TTL policies: `sessions.expiresAt`
  (30-day) and the `events` collection-group `expiresAt` (30-day). Enabled
  via `gcloud firestore fields ttls update`; events TTL spends ~hours in
  `CREATING` before it becomes `ACTIVE`.

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
- **Cloud Function `agentCheck` from shell** (needs a Firebase ID token):
  `curl "https://us-central1-superextra-site.cloudfunctions.net/agentCheck?sid=SID&runId=RID" -H "Authorization: Bearer $ID_TOKEN"`
- **IAM check**: Cloud Function SA
  `907466498524-compute@developer.gserviceaccount.com` needs
  `roles/cloudtasks.enqueuer` on the `agent-dispatch` queue; worker SA
  `superextra-worker@superextra-site.iam.gserviceaccount.com` needs
  `roles/run.invoker` on the worker service itself plus
  `roles/datastore.user` and `roles/aiplatform.user` on the project.
