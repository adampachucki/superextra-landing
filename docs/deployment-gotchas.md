# Deployment Gotchas

The agent runtime is hosted as a Vertex AI Agent Engine Reasoning Engine. Browser POSTs to `agentStream` (Cloud Function) → `gearHandoff()` → Reasoning Engine. Inside the engine, `FirestoreProgressPlugin` writes progress + terminal state to Firestore.

## Vertex AI Agent Engine

- **Redeploy via `agent_engines.update(...)`.** No Cloud Run build, no Dockerfile. The agent venv (`agent/.venv/`) carries the deploy tooling; pickle the agent app + redeploy in-place. Engine resource ID stays stable across redeploys.
- **`GEAR_REASONING_ENGINE_RESOURCE` is read by `agentStream` at request time.** Set in `functions/.env.superextra-site` (which the GHA workflow writes at deploy time) and as a fallback constant in `functions/gear-handoff.js:DEFAULT_RESOURCE`. Belt-and-suspenders: the env-var path is the override, the constant is the floor.
- **Calls FROM INSIDE the engine to Gemini are billed against the engine's tenant project**, not `superextra-site`. Cloud Monitoring metrics for `aiplatform.googleapis.com/generate_content_*` therefore return 0 at our project level even when gear runs are happening. Use the GCP Console → Billing UI for actual spend; see `scripts/cost_baseline.py` for the proxy queries.
- **Filesystem inside the engine is read-only** except `/tmp`.

## Firebase Functions deploy — env-vars REPLACE, not merge

This bit one in production on 2026-04-27. `firebase deploy` reads `functions/.env.<projectId>` at deploy time and **replaces** the deployed function's env vars with whatever the file declares; vars not in the file are stripped. Consequence: every var the function needs at runtime must be in `functions/.env.superextra-site` at deploy time, or the next deploy quietly removes it.

The GHA workflow writes the file fresh on each run (see `.github/workflows/deploy.yml` step "Write functions .env"). Adding a new env var means: append it to the workflow's heredoc AND add a defaulted constant in code as a floor (see `gear-handoff.js:DEFAULT_RESOURCE`).

## Firestore

- **Composite indexes must be rolled out before traffic hits `agentStream`.** `firestore.indexes.json` declares: three `sessions` indexes for the watchdog's `status+queuedAt` / `lastHeartbeat` / `lastEventAt` sweeps, and a `sessions(participants array-contains, updatedAt desc)` composite for the client sidebar listener.
- **Data shape is three-layer.** `sessions/{sid}` holds lightweight metadata + operational state (no terminal content). `sessions/{sid}/turns/{nnnn}` holds per-turn user message, reply, sources, and turn summary. `sessions/{sid}/events/{eid}` holds live activity for the in-flight turn.
- **Terminal source is the TURN doc.** The plugin's terminal write puts `status=complete` + `reply`/`sources`/`turnSummary` on the turn doc atomically with `status=complete` + `updatedAt` on the session doc.
- **Capability-URL rules.** `sessions/{sid}` allows `get` for any signed-in visitor; `list` requires `where('participants','array-contains',uid)`; all writes are Admin-SDK-only. Subcollections (`turns`, `events`) allow path-scoped `read` for any signed-in visitor; writes server-only.
- **TTL only on events.** `events.expiresAt` is 3 days. Sessions and turns persist until the creator deletes the chat via `agentDelete`.

## Watchdog (`functions/watchdog.js`)

- **Terminal flips are fenced in a transaction.** The txn re-reads the session and aborts if `status` / `currentRunId` / the stale `thresholdField` changed between the initial query and the write. Per-reason skip counters (`{missing, status_changed, run_advanced, field_freshened}`) are logged in the invocation summary.
- **Classifier precedence**: `queue_dispatch_timeout` > `worker_lost` > `pipeline_wedged`. `findStuckSessions` dedupes by `sid`.

## Debugging

- **Cloud Function `agentDelete` from shell** (needs a Firebase ID token; only the creator's UID succeeds — contributors get 403):
  `curl -X POST "https://us-central1-superextra-site.cloudfunctions.net/agentDelete" -H "Authorization: Bearer $ID_TOKEN" -H "Content-Type: application/json" -d '{"sid":"SID"}'`
- **agentStream warnings**:
  `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="agentstream" AND severity>=WARNING' --project=superextra-site --freshness=24h`
- **agentStream env vars**:
  `gcloud run services describe agentstream --region=us-central1 --project=superextra-site --format='value(spec.template.spec.containers[0].env)'`

## Live E2E via Chrome DevTools MCP

Ad-hoc real-prompt monitoring — drive the real UI against the real backend and stitch the signals together. Runs cost real Gemini/Places/SerpAPI/Apify tokens and leave a permanent session + per-turn doc until the creator deletes it via `agentDelete`; use sparingly, not as a CI gate.

1. **Navigate.** Chrome MCP `new_page` → `http://localhost:5199/agent/chat`. Anonymous Firebase auth bootstraps silently.
2. **Submit.** `fill` the textarea, `press_key` Enter (Shift+Enter is multiline — use Enter). Poll the page URL; once `?sid=<sid>` appears, the session id is yours.
3. **Watch the user's view.** Periodic `take_screenshot` + `take_snapshot` while `chatState.loading` would be true. `list_console_messages` and `list_network_requests` give client-side signal for free.
4. **Backend logs.** Reasoning Engine logs carry the structured `sid`/`runId` payload; query via `gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine"' --project=superextra-site --limit=500 --format=json --freshness=10m`.
5. **Firestore state.** Session doc `sessions/<sid>` (run status, fencing info, heartbeats, participants); turn docs `sessions/<sid>/turns/<nnnn>` (terminal reply, sources, turnSummary); events subcollection `sessions/<sid>/events` (in-flight activity, 3-day TTL).

## ADC quota project (required for `firebase deploy` from the VM)

`firebase deploy` and other Google APIs called from the VM use Application Default Credentials. ADC needs a quota project pinned to `superextra-site` or you'll see `403 PERMISSION_DENIED` errors against APIs that bill per project (Firebase Hosting, Cloud Functions, Cloud Build).

Two ways, either works:

- Edit `~/.config/gcloud/legacy_credentials/<email>/adc.json` and set `"quota_project_id": "superextra-site"`.
- Or export `GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site` in your shell before running `firebase deploy`.

Discovered during R3 setup of the GEAR migration probe work. Once set, ADC stays sticky across sessions.
