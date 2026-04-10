# Deployment Gotchas

## ADK Cloud Run

- **`adk deploy cloud_run` returns exit 0 even when gcloud fails.** The `deploy-agent` job in `deploy.yml` snapshots the revision before/after and fails if no new revision was created. If the ADK deploy "succeeds" but changes don't appear, check the deploy step output — it may have silently failed. **Always verify** after agent changes: `gcloud run revisions list --service=superextra-agent --region=us-central1 --project=superextra-site --limit=3` — check the latest revision timestamp matches your deploy.
- **Auto-generated Dockerfile** bakes `GOOGLE_CLOUD_LOCATION=us-central1` into the image from `--region`. Do not override this env var — Agent Engine sessions require `us-central1`.
- **Model routing is separate from session routing.** Some models (Gemini 3.1) only work via the global Vertex AI endpoint. `specialists.py` handles this by overriding `api_client` with `location='global'` on Gemini instances. If adding new models, check regional availability first.
- **`agent/.env` is NOT read at runtime in the container.** The file gets copied into the image but ADK's server ignores it. Any env var the agent code needs (e.g. `GOOGLE_PLACES_API_KEY`) must be set as a Cloud Run service-level env var. The deploy pipeline passes these via `--update-env-vars` in the gcloud passthrough after `--` in `deploy.yml`. **When adding a new env var:** add it as a GitHub secret, then append it to the `--update-env-vars` flag in `deploy.yml`. Use `--update-env-vars` (merges) not `--set-env-vars` (replaces all). Service-level env vars persist across deploys.
- **Filesystem is read-only** except `/tmp`. Detect Cloud Run via `K_SERVICE` env var.
- **AgentTool discards sub-agent grounding metadata.** Specialist agents called via `AgentTool` produce `grounding_metadata.grounding_chunks` with source URLs, but AgentTool only propagates text output back to the parent. The `_append_sources` callback in `specialists.py` works around this by appending a `## Sources` markdown section to the specialist's response text before AgentTool captures it.
- **ADK callbacks use keyword arguments.** Agent-level callbacks like `after_model_callback` receive `(*, callback_context, llm_response)` — not positional args. Wrong signatures cause silent TypeErrors.
- **Local deploy**: `cd agent && .venv/bin/adk deploy cloud_run --project=superextra-site --region=us-central1 --service_name=superextra-agent --session_service_uri=agentengine://2746721333428617216 --trace_to_cloud superextra_agent -- --no-allow-unauthenticated`

## Cloud Functions streaming

- **`cloudfunctions.net` GFE proxy kills SSE streams.** The Google Frontend proxy for Cloud Functions v2 terminates SSE/streaming responses after the first `res.write()`. The `agentStream` function bypasses this by having the frontend call the Cloud Run `run.app` URL directly (`agentstream-907466498524.us-central1.run.app`), not the `cloudfunctions.net` URL. Non-streaming endpoints (`agentCheck`, `agent`) can stay on `cloudfunctions.net`.
- **Use `res.on('close')`, never `req.on('close')` for SSE disconnect detection.** On Cloud Run with HTTP/2, `req.on('close')` fires when the request body stream ends — immediately for a POST request — not when the client disconnects. Using `req.on('close')` will abort the SSE stream at +0.0s. The `res.on('close')` event correctly fires only when the response connection is actually closed by the client.
- **The `agentStream` Cloud Run service must allow unauthenticated access** (`allUsers` with `roles/run.invoker`) since the frontend calls it directly without a Firebase auth layer.

## Debugging agent issues

- **Always read Cloud Run logs first**: `gcloud run services logs read superextra-agent --region=us-central1 --project=superextra-site --limit=30`
- **Check env vars**: `gcloud run services describe superextra-agent --region=us-central1 --project=superextra-site --format="yaml(spec.template.spec.containers[0].env)"`
- **Test end-to-end via Cloud Function**: `curl -X POST https://us-central1-superextra-site.cloudfunctions.net/agent -H 'Content-Type: application/json' -d '{"message":"hello","sessionId":"test"}'`
- **IAM**: Cloud Function SA `907466498524-compute@developer.gserviceaccount.com` needs `roles/run.invoker` on the Cloud Run service
