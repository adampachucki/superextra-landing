# GEAR migration probe — round 2 results

**Date:** 2026-04-26
**Plan:** [`docs/gear-probe-plan-round2-2026-04-26.md`](./gear-probe-plan-round2-2026-04-26.md)
**Round 1 results:** [`docs/gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md)
**Execution log:** [`docs/gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md)
**Decision:** **MIGRATION STILL APPROVED.** Round 2 surfaced operational gaps that must land in the migration plan, but no test reversed the binary gate from round 1.

---

## Summary table

| #    | Test                       | Result                             | Notes                                                                                                          |
| ---- | -------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| R2.1 | Outbound HTTPS             | PASS                               | All three URLs reached; default egress is open                                                                 |
| R2.2 | SecretRef env vars         | FAIL                               | Plain env vars work. SecretRef deploys but runtime fails to start. Use Secret Manager runtime fetch instead.   |
| R2.3 | Multi-turn `session.state` | PASS                               | State at `createSession` persists across `stream_query` invocations                                            |
| R2.4 | Gemini 3.1 routing         | PASS via lazy-init Gemini subclass | Three failed attempts before getting it right; production `_make_gemini` needs rewrite                         |
| R2.5 | Production agent shape     | PASS                               | `SequentialAgent`+`ParallelAgent`+`output_key`+state template substitution all work                            |
| R2.6 | Logs visibility            | FAIL                               | No agent logs surfaced via gcloud or Cloud Logging API even with `roles/logging.logWriter` granted to both SAs |
| R2.7 | Node-side `:streamQuery`   | PASS                               | Returns NDJSON, NOT standard SSE — Node parser must do line-by-line JSON                                       |
| R2.8 | In-flight `update()`       | INCONCLUSIVE                       | Long invocation completed, update() never actually fired due to harness config bug                             |

**Net:** five PASS (one with significant code-shape workaround), one FAIL with a clear alternative path, one operational FAIL with a Firestore-based mitigation we already use, one INCONCLUSIVE.

---

## Per-test detail

### R2.1 — Outbound HTTPS: PASS

Probe agent invoked `fetch_external_url` tool against three URLs, all reached:

- `https://places.googleapis.com/` — server reached (404 from Google for that bare path)
- `https://api.apify.com/v2/` — server reached (404, expected)
- `https://example.com/` — 200 OK

**Implication:** the Agent Engine networking docs are right — public internet egress is on by default outside VPC-SC. Production specialists' tool calls (Apify, TripAdvisor, Places) will work without additional network config.

### R2.2 — SecretRef env vars: FAIL; runtime fetch is the path

Three deploy attempts failed identically with "Reasoning Engine resource failed to start and cannot serve traffic":

1. `version="latest"` with one IAM grant
2. `version="latest"` with both deploy-SA and runtime-SA grants, isolated `gcs_dir_name`
3. `version="1"` (numeric, explicit) with both grants

**Plain env vars in the same deploys work fine.** Only the SecretRef shape causes startup failure. Logs from the failed engine were not visible (R2.6 issue), so the actual exception is hidden.

**Migration path:** use the `google.cloud.secretmanager.SecretManagerServiceClient` directly inside the agent's `set_up()` method. Read the secret once at startup and cache it. Grant `roles/secretmanager.secretAccessor` to the runtime SA (`service-{N}@gcp-sa-aiplatform-re.iam.gserviceaccount.com`). This is _also better_ than SecretRef because it lets secrets rotate without redeploy.

**Implication for migration plan:** drop SecretRef from the deploy spec; add Secret Manager runtime fetch to `set_up()`.

### R2.3 — Multi-turn session.state: PASS

Created a session via REST `:createSession?sessionId=se-multiturn-...` with `sessionState={runId, attempt, turnIdx, preexisting_key}`. Two `async_stream_query` calls 2s apart:

| moment                  | session.state                                                           |
| ----------------------- | ----------------------------------------------------------------------- |
| after createSession     | `{runId: r-mt, attempt: 1, turnIdx: 0, preexisting_key: set_at_create}` |
| after turn 1 (3 events) | identical                                                               |
| after turn 2 (3 events) | identical                                                               |

Plugin docs across both turns: 12 total (2× before_run, 2× after_run, 2× agent_event, 6× event), **all carrying `runId='r-mt'`** — meaning create-time state was visible in every callback for both turns.

**Sub-finding:** plain function tools that return values do NOT mutate session.state. Only documented mechanisms — `output_key` on LlmAgent, `state_delta` from BaseAgent events, or `ToolContext.state`-aware tools — change state. Our production specialists already use `output_key`; transfers cleanly.

### R2.4 — Gemini 3.1 routing: PASS via lazy-init Gemini subclass

**Three attempts before success.** This is the most consequential round-2 finding because it requires a code change to production.

**Attempt 1** — match production exactly: build Gemini, attach `Client(location='global')` eagerly. Fails at deploy time with `TypeError: cannot pickle '_thread.lock' object`. The live `genai.Client` carries a `_thread.lock` that cloudpickle can't serialize. Exactly [adk-python#3628](https://github.com/google/adk-python/issues/3628).

**Attempt 2** — plugin-based hot-swap via `before_model_callback`. Deploy succeeds but invocation fails: `'Context' object has no attribute 'invocation_context'`. The callback's `Context` type doesn't expose the agent.

**Attempt 3 — SUCCESS** — Gemini subclass with lazy `api_client` property:

```python
class GeminiGlobalEndpoint(Gemini):
    @property
    def api_client(self) -> Client:
        client = self.__dict__.get("_lazy_global_client")
        if client is not None:
            return client
        client = Client(vertexai=True, location="global", ...)
        self.__dict__["_lazy_global_client"] = client
        return client

    @api_client.setter
    def api_client(self, value):
        self.__dict__["_lazy_global_client"] = value
```

No live Client at pickle time → cloudpickle survives. First `.api_client` read on the deployed runtime constructs the global-routed Client lazily. Verified: `gemini-3.1-pro-preview` returned `'ok-from-gemini-3.1'`.

**Migration prerequisite:** rewrite `agent/superextra_agent/specialists.py:_make_gemini` from the eager pattern to the lazy-subclass pattern before migrating. Without this rewrite, every specialist deploy fails at cloudpickle.

### R2.5 — Production agent shape: PASS

Deployed `SequentialAgent[ParallelAgent[spec_a, spec_b], synth]` with each LlmAgent using `output_key`. Result:

```
event 1: author=prod_spec_b state_delta={'result_b': 'spec_b_output'}
event 2: author=prod_spec_a state_delta={'result_a': 'spec_a_output'}
event 3: author=prod_synth   state_delta={'final': 'synth_combined: spec_a_output spec_b_output'}
final session.state: {result_b, result_a, final}
```

- `ParallelAgent` runs sub-agents concurrently (events arrived in completion order, not definition order)
- `output_key` writes propagate to `state_delta` and into `session.state`
- Synthesizer's `instruction="...{result_a}...{result_b}..."` template substitution resolved correctly from upstream state writes

Every framework primitive our production agent depends on works under deployed Agent Runtime. **No restructuring needed for the agent itself** — only the model construction (R2.4) needs the lazy pattern.

### R2.6 — Logs visibility: FAIL (operational)

Despite:

- Documented resource type (`aiplatform.googleapis.com/ReasoningEngine`) and log IDs (`reasoning_engine_stdout`, `reasoning_engine_stderr`) per [Logging an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/logging)
- Granting `roles/logging.logWriter` to both Vertex SAs
- Waiting 90+ seconds for log propagation
- Querying via gcloud + direct Cloud Logging API
- Print to stdout, print to stderr, and `logging.getLogger(...).info(...)` markers in the agent

**Zero log entries surfaced for any reasoning engine via API.** Multiple queries (by resource_type, by reasoning_engine_id, broad textPayload regex). Direct Cloud Logging API also empty.

**Hypotheses (not isolated):**

- Auto-capture of stdout/stderr to `reasoning_engine_*` log IDs may not actually be implemented despite docs
- Logs may go to a different log scope (folder/org tenant project) and require Console UI to surface
- Explicit `google.cloud.logging.Client.setup_logging()` inside `set_up()` may be required for any log to appear

**Migration mitigation:** production already uses Firestore-based observability (FirestoreProgressPlugin writes per-event docs). That observability path works on Agent Runtime (R2.3 confirmed). For run-level visibility, this is enough. For deeper agent-internal debugging, plan to add explicit `setup_logging()` during cutover and verify before declaring observability complete.

**This is not a migration blocker** — Firestore already gives us per-run observability — but it's a _worse_ operational story than the current Cloud Run worker, where stdout shows up reliably via `gcloud logging`.

### R2.7 — Node-side `:streamQuery`: PASS, with NDJSON gotcha

Node 22 standalone script in `functions/probe-stream-query.js`:

- `google-auth-library` for service-account bearer token: works
- `fetch` POST to `:streamQuery?alt=sse`: 200 OK in 836ms cold, then events stream
- 3 events parsed (function_call, function_response, text) for an LLM+tool run

**Critical undocumented finding:** the stream is **newline-delimited JSON, NOT standard SSE `data: ...\n\n` frames**, even with `?alt=sse` and `Accept: text/event-stream`. Verified by raw curl — each chunk is a bare JSON object on its own line.

My initial parser looked for `data: ` prefix and got 0 events from a 200 OK response — same symptom as [adk-python#1830](https://github.com/google/adk-python/issues/1830). The fix is parse line-by-line as plain JSON.

**Migration implication:** the `agentStream` Cloud Function rewrite uses the line-by-line JSON parser, not an EventSource library. Mitigates ~1 day of debugging at cutover.

### R2.8 — In-flight `update()`: INCONCLUSIVE

Triggered `update()` 60s into a 5-min running invocation. The long invocation **completed cleanly** (all 5 events at expected 60s intervals), but the `update()` call itself errored with `ValueError: Please provide a 'staging_bucket' in vertexai.init(...)` — my harness bug, never actually fired the update.

We don't have proof either way of in-flight-update behaviour. **Migration cutover strategy:** either (a) deploy during a quiet window, or (b) A/B deploy a new reasoning engine resource and switch traffic via a feature flag. Don't rely on "update() preserves in-flight" without verification.

---

## Operational findings (not from a single test)

These surfaced during round 2 and need to land in the migration runbook:

### Concurrent-deploy clobber via shared `gcs_dir_name`

Two parallel `agent_engines.create()` calls both write to `gs://{bucket}/agent_engine/agent_engine.pkl` and clobber each other. After both deploys complete, both engines list the same `pickleObjectGcsUri` and serve whoever wrote last.

**Fix:** pass `gcs_dir_name=f"agent_engine_{flavour}"` per deploy. Verified: with isolated paths, each engine serves its own code correctly.

**Add to runbook:** every distinct deploy must use a distinct `gcs_dir_name`.

### Two service accounts, different roles

The `service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com` SA (without `-re`) handles **deploy-time** concerns (e.g., fetching secrets via SecretRef during deploy). The `service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com` SA (with `-re`) handles **runtime** concerns (Firestore writes, outbound API calls if SA-authed, log writes).

Both need explicit IAM grants for the things our agent does:

- Runtime `-re` SA: `roles/datastore.user` (Firestore), `roles/logging.logWriter` (logs, even if not surfacing as expected), `roles/secretmanager.secretAccessor` (if fetching secrets at runtime).
- Deploy SA (no `-re`): `roles/secretmanager.secretAccessor` (only if using SecretRef in env_vars — recommend skipping per R2.2).

### Reserved env vars

`GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` are reserved and rejected with 400 if passed in `env_vars={}`. Agent Runtime sets them automatically. Our `_make_gemini` workaround (R2.4) is the only override needed.

### ADK App name must be a Python identifier

Hyphens rejected with `ValidationError: must be a valid identifier`. Use underscores (`superextra_probe_lifecycle`). Display name takes hyphens (`superextra-probe-lifecycle`).

### Module-path discipline

Cloudpickle records the module name where a class is defined. If you run deploy from `agent/` cwd with `PYTHONPATH=.` and bundle `extra_packages=["./probe"]`, the deployed runtime imports as `probe.X`. If your code uses `from agent.probe.X import ...`, cloudpickle records that path and the deployed runtime fails to import. **Use relative imports inside the bundled package.**

---

## Decision

**MIGRATION APPROVED, with the round-2 prerequisites added to the migration plan.**

Five must-do items before cutover (none is blocking, all are tractable):

1. **Rewrite `_make_gemini` to the lazy-init Gemini subclass pattern.** Without this, every Gemini 3.1 specialist deploy fails. ~30 LOC change in `agent/superextra_agent/specialists.py`.
2. **Replace SecretRef with Secret Manager runtime fetch** inside the agent's `set_up()`. Read API keys once at startup, cache.
3. **Use `gcs_dir_name` per deploy** — required to avoid clobber when staging deploys (e.g., during A/B cutover).
4. **NDJSON parser in `agentStream`** for parsing `:streamQuery` events on the Node side, not EventSource.
5. **Add explicit `google.cloud.logging.setup_logging()`** inside the agent's `set_up()` if stdout/stderr visibility matters during cutover. Firestore observability is the primary path either way.

Two operational notes:

- **Cutover strategy:** plan on A/B deploy + traffic switch, not in-place update during traffic. R2.8 inconclusive on whether update kills in-flight invocations.
- **IAM grants:** both Vertex SAs need explicit grants for the services our agent calls.

---

## Migration plan rewrite scope

These round-2 findings should land in the next revision of `docs/gear-migration-proposal-2026-04-25.md`:

- §6 ("What gets removed, moved, kept") — drop the `adkSessionId` plumbing claim's caveat; custom session IDs DO work via REST (round-1 finding) so we can remove the mapping entirely
- New §"Code prerequisites": lazy-init Gemini subclass, runtime secret fetch, gcs_dir_name pattern
- New §"IAM runbook": two-SA grant matrix
- §"Migration cutover plan": A/B + traffic switch, not in-place update
- New §"Operational gotchas surfaced by probes": NDJSON parsing, log visibility caveat, reserved env vars, App-name identifier constraint, module-path discipline

I'll write the revised migration proposal next, incorporating all of round 1 + round 2.

---

## Cleanup TODOs

- [ ] Delete probe Reasoning Engines once migration plan is finalized:
  - lifecycle (`329317476414259200`)
  - event_shape (`8725153081739706368`)
  - kitchen (`3851695334971408384`)
  - gemini3 (`886074980347936768`) — also old failed deploys: `5036142036969848832`, `8483647551721963520`
  - prod_shape (`7256416653263503360`) — also old failed deploys: `4896530448521363456`
  - failed SecretRef deploys: `2397032655330738176`, `629369801587818496`
  - minimal `superextra-probe-minimal`: `7271616302005878784`
- [ ] Decide whether `agent/probe/` and `functions/probe-stream-query.js` stay in repo as reference, or get archived
- [ ] Keep `roles/datastore.user`, `roles/logging.logWriter`, `roles/secretmanager.secretAccessor` grants on the production runtime SA when migration moves to production
