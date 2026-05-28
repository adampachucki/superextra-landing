# Deployment Gotchas

The agent runtime is hosted as a Vertex AI Agent Engine Reasoning Engine. Browser POSTs to `agentStream` (Cloud Function) → `gearHandoff()` → Reasoning Engine. Inside the engine, `FirestoreProgressPlugin` writes progress + terminal state to Firestore.

## Vertex AI Agent Engine

- **Redeploy via `agent/scripts/redeploy_engine.py`.** No Cloud Run build, no Dockerfile. The agent venv (`agent/.venv/`) carries the deploy tooling; the script wraps `agent_engines.update(...)`, applies the local ADC credential workaround, pickle-checks the app, and redeploys in-place when run with `--yes`. Engine resource ID stays stable across redeploys.
- **Commit before every Agent Engine deploy.** Never run `agent/scripts/redeploy_engine.py` from an uncommitted worktree. The deploy script records the latest committed runtime SHA, so a dirty deploy puts production ahead of git and makes rollback/audit ambiguous. If this happens, commit the exact deployed source immediately and redeploy so the recorded runtime SHA matches the committed code.
- **`GEAR_REASONING_ENGINE_RESOURCE` is read by `agentStream` at request time.** Set in `functions/.env.superextra-site` (which the GHA workflow writes at deploy time). `gearHandoff()` throws if the env var is unset — no fallback constant.
- **Calls FROM INSIDE the engine to Gemini are billed against the engine's tenant project**, not `superextra-site`. Cloud Monitoring metrics for `aiplatform.googleapis.com/generate_content_*` therefore return 0 at our project level even when gear runs are happening. Use the GCP Console → Billing UI for actual spend; see `scripts/cost_baseline.py` for the proxy queries.
- **Filesystem inside the engine is read-only** except `/tmp`.
- **Agent observability is enabled in the Agent Engine deploy script.** `agent/scripts/redeploy_engine.py` preserves/adds `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true`, `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`, `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`, and `ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS=false`. `EVENT_ONLY` intentionally captures full GenAI prompt/response content in official OTel telemetry for debugging; treat those traces/logs as sensitive production data.

## Manual deploy invariant

Manual production deploys must start from a clean committed tree. Commit first, then deploy from that commit. This applies to Firebase Hosting, Cloud Functions, Firestore rules/indexes, and Vertex AI Agent Engine. A manual deploy from dirty local files creates a production state that cannot be audited, reproduced, or rolled back from git.

## Firebase Functions deploy — env-vars REPLACE, not merge

This bit one in production on 2026-04-27. `firebase deploy` reads `functions/.env.<projectId>` at deploy time and **replaces** the deployed function's env vars with whatever the file declares; vars not in the file are stripped. Consequence: every var the function needs at runtime must be in `functions/.env.superextra-site` at deploy time, or the next deploy quietly removes it.

The GHA workflow writes the file fresh on each run (see `.github/workflows/deploy.yml` step "Write functions .env"). Adding a new env var means appending it to the workflow's heredoc.

## GitHub Actions deploy — push trigger can silently drop

The `Deploy to Firebase` workflow runs on `push` to `main`. During a GitHub Actions outage on 2026-05-26, four consecutive pushes registered (visible in the repo's PushEvent feed) but produced zero workflow runs — `workflow_dispatch` returned HTTP 500, and `gh run list` showed nothing new for the affected SHAs. Check `https://www.githubstatus.com/api/v2/components.json` for the `Actions` component when this happens.

Two unblock paths once you confirm GHA is the problem:

- **Manual re-trigger** (preferred once Actions recovers): `gh workflow run deploy.yml --ref main` — workflow_dispatch is wired up for exactly this case. Re-runs the full workflow against the current HEAD of `main`.
- **Manual deploy from the VM** (last resort, bypasses CI test gate): get a CI token from a desktop via `firebase login:ci` (interactive, browser-paste), then on the VM run `FIREBASE_TOKEN=<token> GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site npx firebase-tools deploy --only hosting,functions,firestore:rules,firestore:indexes --project superextra-site --force --token "$FIREBASE_TOKEN"`. Build the frontend first with `npm run build`, and overwrite `functions/.env.superextra-site` to match what the GHA workflow writes (single `GEAR_REASONING_ENGINE_RESOURCE=...` line) — anything else gets deployed as a function env var.

## Firestore

Data shape and listeners are documented in CLAUDE.md's "Transport architecture" section — this section covers only what isn't there.

- **Composite indexes must be rolled out before traffic hits `agentStream`.** `firestore.indexes.json` declares two `sessions` indexes for the watchdog (`status+queuedAt`, `status+lastHeartbeat`), a `sessions(participants array-contains, updatedAt desc)` composite for the client sidebar listener, and an `events(runId, attempt, seqInAttempt)` index for the in-flight events listener.
- **Capability-URL rules.** `sessions/{sid}` allows `get` for any signed-in visitor; `list` requires `where('participants','array-contains',uid)`; all writes are Admin-SDK-only. Subcollections (`turns`, `events`) allow path-scoped `read` for any signed-in visitor; writes server-only.
- **TTL only on events.** `events.expiresAt` is 180 days. Sessions and turns persist until the creator deletes the chat via `agentDelete`. Existing session events were backfilled to the 180-day expiry on 2026-05-20.

## Watchdog (`functions/watchdog.js`)

- **Terminal flips are fenced in a transaction.** The txn re-reads the session and aborts if `status` / `currentRunId` / the stale `thresholdField` changed between the initial query and the write. Per-reason skip counters (`{missing, status_changed, run_advanced, field_freshened}`) are logged in the invocation summary.
- **Two flip reasons**: `handoff_start_timeout` (no heartbeat after enqueue) and `heartbeat_lost` (heartbeat went stale mid-run). `findStuckSessions` dedupes by `sid`.

## Debugging

- **Cloud Function `agentDelete` from shell** (needs a Firebase ID token; only the creator's UID succeeds — contributors get 403):
  `curl -X POST "https://us-central1-superextra-site.cloudfunctions.net/agentDelete" -H "Authorization: Bearer $ID_TOKEN" -H "Content-Type: application/json" -d '{"sid":"SID"}'`
- **agentStream warnings**:
  `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="agentstream" AND severity>=WARNING' --project=superextra-site --freshness=24h`
- **agentStream env vars**:
  `gcloud run services describe agentstream --region=us-central1 --project=superextra-site --format='value(spec.template.spec.containers[0].env)'`

## Live E2E via Chrome DevTools MCP

Ad-hoc real-prompt monitoring — drive the real UI against the real backend and stitch the signals together. Runs cost real Gemini/Places/SerpAPI/Apify tokens and leave a permanent session + per-turn doc until the creator deletes it via `agentDelete`; use sparingly, not as a CI gate.

1. **Navigate.** Chrome MCP `new_page` → `http://localhost:5199/chat`. Anonymous Firebase auth bootstraps silently.
2. **Submit.** `fill` the textarea, `press_key` Enter (Shift+Enter is multiline — use Enter). Poll the page URL; once `?sid=<sid>` appears, the session id is yours.
3. **Watch the user's view.** Periodic `take_screenshot` + `take_snapshot` while `chatState.loading` would be true. `list_console_messages` and `list_network_requests` give client-side signal for free.
4. **Backend logs.** Reasoning Engine logs carry the structured `sid`/`runId` payload; query via `gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine"' --project=superextra-site --limit=500 --format=json --freshness=10m`.
5. **Firestore state.** Session doc `sessions/<sid>` (run status, fencing info, heartbeats, participants); turn docs `sessions/<sid>/turns/<nnnn>` (terminal reply, sources, turnSummary); events subcollection `sessions/<sid>/events` (in-flight activity, 180-day TTL).

## ADC quota project (required for `firebase deploy` from the VM)

`firebase deploy` and other Google APIs called from the VM use Application Default Credentials. ADC needs a quota project pinned to `superextra-site` or you'll see `403 PERMISSION_DENIED` errors against APIs that bill per project (Firebase Hosting, Cloud Functions, Cloud Build).

Two ways, either works:

- Edit `~/.config/gcloud/legacy_credentials/<email>/adc.json` and set `"quota_project_id": "superextra-site"`.
- Or export `GOOGLE_CLOUD_QUOTA_PROJECT=superextra-site` in your shell before running `firebase deploy`.

Discovered during R3 setup of the GEAR migration probe work. Once set, ADC stays sticky across sessions.

### gRPC clients (`firestore.Client()` etc.) fail with `ACCESS_TOKEN_SCOPE_INSUFFICIENT`

A script using `google.auth.default()` / `google.cloud.*` clients from the VM can fail with `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT` (distinct from the quota `PERMISSION_DENIED` above). Root cause: there is **no `~/.config/gcloud/application_default_credentials.json`** and `GOOGLE_APPLICATION_CREDENTIALS` is unset, so `google.auth.default()` falls back to the GCE metadata server's default Compute Engine service account, whose token carries only the VM's narrow access scopes (no Firestore / `cloud-platform`). `gcloud auth print-access-token` works because it uses the gcloud _user_ account (full `cloud-platform`), and `redeploy_engine.py` works because it explicitly points `GOOGLE_APPLICATION_CREDENTIALS` at the legacy user cred.

Root-cause fix (do once): `gcloud auth application-default login` then `gcloud auth application-default set-quota-project superextra-site`. Creates a real `cloud-platform`-scoped ADC and pins the quota project — clearing both this and the quota gotcha above for every script that uses `google.auth.default()`. On the headless VM, complete the OAuth callback over an `ssh -L` tunnel.

Per-script workaround if ADC isn't fixed: mint a token with `gcloud auth print-access-token` and pass it explicitly, e.g. `Credentials(token=...).with_quota_project("superextra-site")`.
