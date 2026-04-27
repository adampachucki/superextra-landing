# GEAR migration probe — round 2 plan

**Date:** 2026-04-26
**Round 1 results:** [`docs/gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md)
**Decision after round 1:** migration approved on the gate. This round closes operational gaps that could surface as production issues during cutover. **It cannot reverse the migration decision** unless it uncovers a hard platform incompatibility (most likely candidate: Test R2.4 — Gemini 3.1 routing).

This plan is shorter than round 1 because the gate is settled. Each test below cites the docs we consulted, states the expected behaviour from those docs, defines pass/fail, and **explicitly lists the REST/fallback paths to try if the SDK rejects** — the lesson from Test 5 last round, where I drew a wrong conclusion from an SDK-side rejection without verifying the platform layer.

---

## Operating principle for round 2

**Assume the ADK Python SDK may be stale relative to the platform.** Last round, `User-provided Session id is not supported for VertexAISessionService` was a stale `raise ValueError` at line 121 of `vertex_ai_session_service.py` — the platform supported user IDs but the SDK guard said no. A round-2 finding of "this doesn't work" is only credible if it has been verified at the REST layer too.

For each test below: if the SDK fails, the **fallback path** column tells you which REST endpoint to hit. Only if both layers agree does the test conclusively fail.

---

## Tests, ranked by impact

### R2.1 — Outbound HTTPS to non-Google APIs

**Why:** production specialists call Apify (TripAdvisor scraping), Google Places, web grounding's referenced URLs via `fetch_web_content`. If Agent Runtime egress is sandboxed by default, migration is blocked.

**Doc grounding:** [Agent Engine Networking Overview](https://discuss.google.dev/t/vertex-ai-agent-engine-networking-overview/267934) — _"By default, with a standard deployment, public internet access is enabled."_ Outbound traffic egresses directly from Google-managed tenant. **VPC-SC is the only thing that blocks default egress, and we don't use VPC-SC.**

**Known caveat:** [forum thread](https://discuss.google.dev/t/vertex-ai-agent-engine-connecttimeouterror-to-outbound-urls/194141) — a user reported `ConnectTimeoutError` on outbound URLs even with permissive firewall. Worth treating egress as "probably works, but verify."

**Test design:**

- Deploy a probe `LlmAgent` with one custom tool `fetch_external_url(url)` that does `requests.get(url, timeout=10).status_code`.
- Invoke with three URLs: `https://places.googleapis.com/v1/places:searchText` (Google), `https://api.apify.com/v2/health` (third-party), `https://example.com` (generic).
- Capture status codes via the plugin's Firestore writes.

**Pass:** all three return 200/2xx (or appropriate auth-required code, but reach the server).
**Fail:** ConnectTimeoutError or DNS failure. Investigate before continuing — could be a regional network issue, a default firewall, or a quota.
**Fallback:** if the SDK appears to silently swallow errors, hit the runtime via curl from a local terminal pointing to the probe's `streamQuery` endpoint and watch the SSE response for the tool result.

---

### R2.2 — `SecretRef`-backed env vars at deploy time

**Why:** production needs `GOOGLE_PLACES_API_KEY`, `APIFY_TOKEN`, `SERPAPI_API_KEY`. We learned `GOOGLE_CLOUD_PROJECT` is reserved. We need to confirm that secret-backed env vars actually inject correctly at runtime.

**Doc grounding:** [Python SDK reference for `vertexai.agent_engines`](https://docs.cloud.google.com/python/docs/reference/vertexai/latest/vertexai.agent_engines) — `env_vars` typing is `Union[Sequence[str], Dict[str, Union[str, SecretRef]]]`. SecretRef constructor takes `secret` (name) and `version` (default `"latest"`).

**Critical IAM detail from [Deploy an agent](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/deploy):** the SA that fetches secrets at deploy time is `service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com` — the **non-`-re`** Vertex AI Service Agent. This is _different_ from the runtime SA we discovered last round (`service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com`). Both need separate IAM grants for different concerns.

**Test design:**

- Create a Secret Manager secret `probe-test-key` with value `hello-from-secrets`.
- Grant `roles/secretmanager.secretAccessor` to `service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com`.
- Deploy a probe with both shapes:
  ```python
  env_vars = {
      "PLAIN_VAR": "plain-value",
      "SECRET_VAR": SecretRef(secret="probe-test-key", version="latest"),
  }
  ```
- Add a tool `read_env(name)` that returns `os.environ.get(name)`. Invoke with both var names.

**Pass:** plain returns `"plain-value"`, secret returns `"hello-from-secrets"`.
**Fail (plain):** investigate reserved-vars list — there may be more reserved names than `GOOGLE_CLOUD_*`.
**Fail (secret):** check IAM grant; check secret name spelling; check whether `SecretRef` shape needs to be `projects/{}/secrets/{}/versions/{}` instead of bare name.
**Fallback if `SecretRef` import path is wrong:** the search results suggested `from google.cloud.aiplatform_v1.types.env_var import SecretRef`. If that import doesn't exist in our installed SDK version, try `from vertexai.agent_engines._utils import SecretRef` or inspect the `agent_engines.create()` source.

---

### R2.3 — Multi-turn session state semantics

**Why:** our chat reuses one session across many turns. State written by turn 1's specialists (`output_key` writes, `_tool_src_*` keys) must be readable by turn 2's plugin and agents.

**Doc grounding:** [Sessions overview](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/sessions/overview) — sessions persist events, state holds conversation-relevant data. The docs don't crisply say whether state survives across `stream_query` invocations on the same session, but the intent appears to be yes (otherwise output_key chains within one pipeline wouldn't work). Test empirically.

**Test design:**
Lifecycle probe agent already deployed. Two-turn invocation against same session:

- Create session with `state={"runId": "r-mt", "attempt": 1, "turnIdx": 0}`.
- Turn 1: invoke. Plugin reads state, writes 8 docs as before.
- Turn 2: invoke same session, message `"again"`. Plugin reads state.
- Verify in turn-2 plugin docs:
  - `runId="r-mt"` still present? (state preserved across turns)
  - `turnIdx=0` still present? (state not overwritten by something)
  - Or does turn 2 see fresh state?

Then **mutate** state during turn 1 by adding a custom plugin callback that does `invocation_context.session.state["mutated_in_turn1"] = "yes"` in `before_run_callback`. Re-invoke turn 2 and check whether the plugin sees `mutated_in_turn1` in state.

**Pass:** turn 2 sees turn 1's state including any mutations the agent/plugin made via `state_delta`. This matches the documented session model.
**Fail:** state resets between turns, OR mutations are lost. Either is a behavioural difference from our current self-hosted Runner that needs to be reflected in the migration plan.
**Fallback if SDK seems to lose state:** call REST `:appendEvent` directly between turns to write a state update, then verify via REST `:getSession` that state contains the expected keys.

---

### R2.4 — Gemini 3.1 routing with per-agent `location='global'` (HIGHEST RISK)

**Why:** our specialists run on Gemini 3.1, which is **only** available at the global Vertex endpoint. Our `_make_gemini` builds LlmAgents with custom `api_client(location='global')` to override the agent's global location. **This is a known broken interaction** — see [adk-python#3628](https://github.com/google/adk-python/issues/3628) (filed 2025-11-20, status: request-clarification). The reporter ran into exactly this: `GOOGLE_CLOUD_LOCATION=global` breaks Agent Engine session creation, and `GOOGLE_CLOUD_LOCATION=us-central1` breaks Gemini 3.1.

The official workaround is "set `GOOGLE_CLOUD_LOCATION` to a region for Agent Engine, override `location='global'` per-LlmAgent for Gemini 3.1." That's exactly the pattern we already use locally. **Whether it survives cloudpickle → deploy → unpickle is the unverified link.**

**Doc grounding:**

- [adk-python#3628](https://github.com/google/adk-python/issues/3628) — confirms the bug.
- [Gemini 3.1 region availability](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/get-started-with-gemini-3) — global only.
- Our own `agent/superextra_agent/specialists.py` `_make_gemini(force_global=True)` — the override site.

**Test design:**

- Deploy a probe with **one** `LlmAgent` configured exactly like our specialists: `model="gemini-3.1-flash"`, custom `api_client` overriding `location='global'`. (Use the actual `_make_gemini` factory if practical.)
- Invoke with a trivial prompt ("Say hi.").
- Observe: does the LLM call succeed? If it 404s, the override didn't stick after deploy.

**Pass:** LLM responds. We can use Gemini 3.1 on Agent Runtime via the per-agent override pattern.

**Fail:** `404 NOT_FOUND` for the model, OR a more cryptic error indicating the deployed runtime ignored the override. **This is a migration blocker** — we either:

- Wait for adk-python#3628 to land
- Downgrade all specialists to Gemini 2.5 (significant quality regression — our Phase 0 measurements were all on 3.1)
- Find a different override mechanism (maybe at the App level or via env var)

**Fallback investigation if the SDK errors:** read the deployed agent's Cloud Logs (`logName=projects/{}/logs/reasoning_engine_stderr`, see R2.6) to see the actual exception. Try setting `GOOGLE_GENAI_USE_VERTEXAI=True` and `GOOGLE_CLOUD_LOCATION=global` as `env_vars` at deploy time and see if Agent Engine still creates sessions in a regional endpoint internally — the bug report suggests this MIGHT work on newer ADK versions.

This is the riskiest test of round 2 by a wide margin. **If R2.4 fails, the migration scope shrinks dramatically** — we'd be downgrading agent quality to migrate, and that's a different cost-benefit conversation.

---

### R2.5 — Production agent shape end-to-end (`ParallelAgent`, `transfer_to_agent`, `output_key`)

**Why:** our pipeline structure (`SequentialAgent` containing `ParallelAgent` of 3–8 specialists, with `transfer_to_agent` routing and `output_key` state writes) was never tested under deployed Agent Runtime. We trust ADK because we use these locally — but the deployed runtime _could_ behave differently (concurrency caps, ordering, state isolation).

**Doc grounding:** ADK official docs document `SequentialAgent`, `ParallelAgent`, and `LlmAgent.transfer_to_agent` as supported. Agent Runtime claims framework-agnostic ADK support. So this is "verify that the documented support actually works for our specific shape," not "investigate undocumented behaviour."

**Test design:**

- Lift our actual `agent/superextra_agent/agent.py` (or a stripped version with 2 fake specialists instead of 8 real ones, to avoid invoking real APIs) and deploy as a probe.
- Invoke with a one-line prompt and a fake `placeContext` payload.
- Confirm:
  - `ParallelAgent` actually runs both sub-agents concurrently (events from both authors should appear interleaved, not strictly sequential).
  - `transfer_to_agent` works for routing decisions (router → research_pipeline path).
  - `output_key` writes from one LlmAgent are visible in `session.state` for the next agent (visible via plugin reads).

**Pass:** events from both parallel specialists appear in plugin's Firestore writes, with `state_delta` containing each one's `output_key` value.

**Fail:** sequential execution despite `ParallelAgent`, OR state writes lost between agents, OR `transfer_to_agent` errors. Each is a different fix in the migration plan.

**Fallback:** none needed at SDK level — this test exercises the runtime's framework-execution behaviour, not an SDK guard. If it fails, file a bug.

---

### R2.6 — Logs visibility from inside the deployed agent

**Why:** Production debugging requirement. My earlier query returned nothing — need to verify the documented log surface actually surfaces logs.

**Doc grounding:** [Logging an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/logging) — confirmed:

- Resource type: `aiplatform.googleapis.com/ReasoningEngine`
- Resource labels: `location`, `resource_container` (project ID), `reasoning_engine_id`
- Log IDs: `reasoning_engine_build` (build), `reasoning_engine_stdout`, `reasoning_engine_stderr` (runtime)
- Custom log IDs supported via `google.cloud.logging` client

**Why my earlier query came back empty:** likely (a) Cloud Logging propagation lag (typically 30–90s), (b) my filter freshness window too narrow, or (c) I queried `resource.type=` but the documented filter is `resource.type` plus `resource.labels.reasoning_engine_id=`.

**Test design:**

- Add `print("PROBE_STDOUT_MARKER", file=sys.stdout, flush=True)` and `print("PROBE_STDERR_MARKER", file=sys.stderr, flush=True)` to a tool function.
- Add a `logging.getLogger("probe").info("PROBE_LOGGING_MARKER")` call.
- Invoke. Wait 90s.
- Query: `gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine" AND resource.labels.reasoning_engine_id="{ID}"' --freshness=10m`
- Expect to see the three markers, possibly across `reasoning_engine_stdout`, `reasoning_engine_stderr`, and the custom log ID.

**Pass:** at least one of the markers visible via gcloud query within 5 min of invoke.
**Fail:** zero markers after 5 min. Investigate via Cloud Console Logs Explorer (which sometimes shows what gcloud filters miss).
**Fallback:** if gcloud queries fail but Console works, we have a "logs are visible but only in UI" outcome — workable but operationally annoying. Document the actual filter that works.

---

### R2.7 — Cloud Function Node 22 → Agent Runtime `:streamQuery` recipe

**Why:** our `agentStream` is Firebase Functions Node 22. The Python `agent_engines.AdkApp.async_stream_query` SDK isn't available there. We need a clean Node-side pattern for: (a) get a service-account token, (b) POST to `:streamQuery?alt=sse`, (c) parse SSE events, (d) detect terminal state. If this is awkward, the migration's agentStream rewrite is bigger than expected.

**Doc grounding:** [reasoningEngines.streamQuery REST reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.reasoningEngines/streamQuery) confirms endpoint shape. [GoogleAuth for Node](https://www.npmjs.com/package/google-auth-library) handles the token. SSE format is documented as `data: {...}\n\n` per chunk.

**Test design:**

- Standalone Node script in `functions/probe-stream-query.js` that:
  - Uses `GoogleAuth({scopes: ['https://www.googleapis.com/auth/cloud-platform']})` to get a token
  - Fetches `https://us-central1-aiplatform.googleapis.com/v1/{resource}:streamQuery?alt=sse` with `class_method: "async_stream_query"` body
  - Streams the response body, parses `data:` lines as JSON
  - Logs each event
- Run from local Node 22 against the deployed lifecycle probe.

**Pass:** Node script receives all 5 deterministic agent events, prints them parsed.
**Fail:** auth issue (token scope wrong), SSE parsing issue (chunks don't align with `data:` boundaries), or the request hangs. Each has a known mitigation.
**Fallback:** if `fetch` streaming is awkward in Node 22, fall back to `node-fetch` or `axios` with stream mode. If SSE parsing produces fragmented JSON, buffer until complete `\n\n` boundaries.

---

### R2.8 — In-flight invocation behaviour during `agent_engines.update()`

**Why:** zero-downtime deploys, or do we need a quiet window?

**Doc grounding:** none clean — `update()` is documented but not its in-flight semantics. Empirical only.

**Test design:**

- Start a 5-min lifecycle invocation.
- 90s in (after first event observed), trigger `agent_engines.update()` from another shell.
- Observe whether the running invocation continues or aborts.

**Pass:** running invocation completes; new code only affects subsequent invocations.
**Fail:** running invocation killed mid-flight. Implication: deploys need a quiet window, OR the old version stays around for in-flight requests (ideal but not assumed).
**Fallback:** none — this is a behaviour observation, no SDK layer to bypass.

---

## Order of execution

Tests are independent; can run in parallel after a single **shared deploy**. One probe app, with all the tools needed for R2.1, R2.2, R2.3, R2.6 (and R2.4 if we add a Gemini 3.1 LlmAgent — but that's a separate deploy because it needs different model setup).

Suggested execution order:

1. **R2.4 first** (highest risk; might invalidate the rest of the work).
2. **R2.5 second** (production-shape sanity — bigger deploy).
3. **R2.1, R2.2, R2.3, R2.6 batched** in one probe deploy (smaller).
4. **R2.7** is independent (Node-side, no probe deploy needed beyond what's already up).
5. **R2.8** runs concurrently with whichever lifecycle invocation is in flight from above.

Total time estimate: 3–4 hours of probe time + 1–2 deploys (3.5 min each).

---

## What this round does NOT address

For honesty about scope:

- **Crash recovery mid-invocation** — if the runtime's container itself crashes mid-run, what happens? Probably handled by the watchdog as today, but unverified.
- **Per-invocation memory ceiling** — we don't know the limit; large synthesizer responses could OOM.
- **Cost at scale** — back-of-envelope deferred to migration-time.
- **EU region availability** — doc check, not probed (the memo is Europe-first; we're in `us-central1` for the probe).
- **Default session TTL** — doc check; not running an aging test.

These are operational risks the migration plan should call out as "verify during cutover, not pre-cutover."

---

## Decision contract

**If R2.4 fails:** migration scope changes. Either downgrade specialists to Gemini 2.5 (quality regression) or wait for adk-python#3628. Re-evaluate the migration cost-benefit at that point.

**If R2.1 fails:** migration is blocked outright. The product depends on outbound HTTP to non-Google APIs; without it, the agent can't function. Stop here.

**If R2.5 fails on `ParallelAgent`:** migration is blocked or the agent must be restructured. Stop and investigate.

**Anything else fails:** migration proceeds, but the migration plan must reflect the constraint (e.g., R2.8 fail → deploys need a quiet window; R2.7 fail → bigger Node-side rewrite scope).

**All seven pass:** migration plan can be written with high confidence and minimal "we'll find out at cutover" caveats.

---

## References

- [Agent Engine Networking Overview (forum, authoritative)](https://discuss.google.dev/t/vertex-ai-agent-engine-networking-overview/267934)
- [Logging an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/logging)
- [Sessions overview](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/sessions/overview)
- [Manage sessions with ADK](https://docs.cloud.google.com/agent-builder/agent-engine/sessions/manage-sessions-adk)
- [Deploy an agent (env_vars + SecretRef IAM)](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/deploy)
- [reasoningEngines.streamQuery REST reference](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/reference/rest/v1/projects.locations.reasoningEngines/streamQuery)
- [Get started with Gemini 3 (region availability)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/get-started-with-gemini-3)
- [adk-python#3628 — Gemini 3 + Agent Engine bug](https://github.com/google/adk-python/issues/3628)
- [adk-python#987 — Custom session ID guard (round-1 finding)](https://github.com/google/adk-python/issues/987)
- [Vertex AI Agent Engine ConnectTimeoutError forum thread](https://discuss.google.dev/t/vertex-ai-agent-engine-connecttimeouterror-to-outbound-urls/194141)
- Round-1 results: [`docs/gear-probe-results-2026-04-26.md`](./gear-probe-results-2026-04-26.md)
- Round-1 log: [`docs/gear-probe-log-2026-04-26.md`](./gear-probe-log-2026-04-26.md)
