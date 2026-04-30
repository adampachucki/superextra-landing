# Lean agent cleanup plan

**Date:** 2026-04-30
**Author:** drafted with Claude Code; verified against ADK Python `main`, Vertex AI Agent Engine docs, and the live Superextra codebase. Revised across three review passes: (1) eval-side helper dependency + URL-Context wording + phantom `turnSummary.notes` path; (2) prompt-baked-at-import deploy mechanics + ChatLogger ephemeral logs + public ToolContext fields; (3) `_RUNTIME_PATHS` directory-prefix matching + env_vars REPLACE-not-merge semantics + agent-level tool-error-callback duplicate-pill risk.
**Status:** ready for implementation review.

---

## What this plan is

Three targeted changes to Superextra's agent layer, all chosen so that the codebase ends up smaller and simpler after they land. Each one is either a **deletion**, a **prompt edit**, or a **one-line config flip** that lets us delete custom code we'd otherwise be maintaining.

The three items, in execution order:

1. **Turn on Cloud Trace** (one env-var change at deploy time). Gives us free engineering observability — span waterfalls, per-tool latency, token usage — without writing instrumentation.
2. **Refactor `FirestoreProgressPlugin` to subscribe to typed plugin hooks** instead of reverse-engineering ADK Event objects. Deletes the `_map_function_call` / `_map_function_response` / tool-error-detection branches in `firestore_events.py`. Net LOC reduction.
3. **Add a "no memory citations" rule to specialist instructions.** A one-line prompt fix that addresses the Domiporta/Gratka-style fabrications by removing the cause, instead of building a verifier downstream. (The original idea — swap `fetch_web_content` for ADK's `url_context` — turned out not to be a lean drop-in: Gemini 3 docs indicate the combination is supported model-side, but ADK/Vertex Agent Engine behavior for our specific multi-AgentTool configuration is unproven and would need its own spike. See Item 3 for the verification trail.)

No new production files. Two of these delete code or reduce prompt surface. The third (Cloud Trace) replaces ad-hoc engineering observability with a one-line config flip and an external dashboard. (Item 2 adds one new test file, `agent/tests/test_firestore_progress_hooks.py`.)

---

## How to read this plan if you're new to the codebase

If you've never touched the Superextra agent before, read these first in this order:

1. `CLAUDE.md` (repo root) — top-level project conventions: stack, dev server, testing, transport architecture.
2. `agent/superextra_agent/agent.py` (190 lines) — full pipeline assembly. Three agents (`router`, `research_pipeline`, `follow_up`); the lead has 9 specialists exposed as `AgentTool`.
3. `agent/superextra_agent/firestore_progress.py` (576 lines) — the plugin we're refactoring in §3. Currently subscribes to three hooks: `before_run_callback`, `on_event_callback`, `after_run_callback`.
4. `agent/superextra_agent/firestore_events.py` (438 lines) — the **mapper** that turns ADK events into user-facing timeline pill text ("Searching the web", "Google Maps"). This file stays, but its tool-call parsing helpers go away in §3.
5. `agent/scripts/redeploy_engine.py` (331 lines) — how we ship to Vertex AI Agent Engine. Touch this for §2.
6. `docs/agent-research-depth-summary-2026-04-28.md` — context on V2.3 (the source-priors / coverage work that preceded the recent rewrite).
7. `docs/agent-routing-collapse-plan-2026-04-29.md` and `docs/agent-routing-collapse-deploy-log-2026-04-30.md` — the most recent architectural change (orchestrator + synthesizer collapsed into one `research_lead` agent; specialists became `AgentTool`-wrapped). Many older plan docs reference the pre-collapse shape and are stale; treat the routing-collapse docs as the current architectural source of truth.

If you're returning to this work later, jump directly to the **Item** section you're picking up.

---

## Item 1 — Turn on Cloud Trace at deploy time

### Why

Today, when a research run misbehaves, our only debug path is reading Firestore events plus log lines. That's enough for "did the run finish" but not for "where did the lead spend 90s waiting" or "which specialist's tool calls cost the most tokens." We've also been talking about iterative-dispatch observability (see `docs/agent-iterative-dispatch-strategy-2026-04-29.md`) — the engineering question "did iteration actually happen?" wants per-tool timing data we don't currently emit.

ADK ≥1.17 emits OpenTelemetry spans following the GenAI semantic conventions automatically. Vertex AI Agent Engine has built-in Cloud Trace export. With the right env var set at deploy time, we get Cloud Trace's span waterfall, latency heatmaps, per-LLM-call token usage, and AgentTool nesting visualization — for free, no instrumentation code.

Reference: ADK observability page ([adk.dev/observability/traces/](https://adk.dev/observability/traces/)) and the Cloud Trace integration page ([adk.dev/integrations/cloud-trace/](https://adk.dev/integrations/cloud-trace/)). Authoritative deploy-side guidance at [cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/tracing](https://cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/tracing).

### What gets emitted (verified against `adk-python` source)

ADK auto-emits these span names:

- `invoke_agent` — once per agent invocation. Attributes: `gen_ai.operation.name=invoke_agent`, `gen_ai.agent.name`, `gen_ai.agent.description`, `gen_ai.conversation.id`. Source: `src/google/adk/telemetry/tracing.py:135` (`trace_agent_invocation`).
- `execute_tool` — once per tool call. Attributes: `gen_ai.operation.name=execute_tool`, `gen_ai.tool.name`, `gen_ai.tool.description`, `gen_ai.tool.type` (e.g. `AgentTool`, `FunctionTool`). Source: `src/google/adk/telemetry/tracing.py:168` (`trace_tool_call`); span opened in `src/google/adk/flows/llm_flows/functions.py:429`.
- `generate_content {model.name}` — once per LLM call. Attributes: `gen_ai.system='gcp.vertex.agent'`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.response.finish_reasons`. Source: `src/google/adk/telemetry/tracing.py:299` (`trace_call_llm`).

**Nested AgentTool spans propagate correctly.** When `research_lead` calls `AgentTool(agent=specialist)`, the specialist's internal `invoke_agent` span becomes a child of the parent's `execute_tool` span via OTel context propagation. Verified by reading `src/google/adk/tools/agent_tool.py:230-238` (inner `Runner` constructed with the same plugin/tracer chain). Net effect in Cloud Trace: one waterfall row per specialist nested inside the lead's row.

### How to enable

The recommended path on Agent Engine is **environment variables**, not the constructor flag. Per the Agent Engine tracing doc ([cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/tracing](https://cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/tracing)):

> If you were previously setting the `enable_tracing` flag, we recommend you use the environment variables instead.

Set these env vars at deploy time:

- `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true` — turns tracing on.
- `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` — opts into the current GenAI semconv (otherwise spans use a more conservative, older attribute set).
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY` — captures prompt/response payloads as span events. Optional; useful for debugging but increases trace size. Recommend leaving this **off** initially (so traces stay small and we don't accidentally export message content to a separate system) and turning it on per-incident.

### Files to change

- `agent/scripts/redeploy_engine.py:312-318` — extend the `agent_engines.update(...)` call with `env_vars={...}`. Current shape:

  ```python
  remote = agent_engines.update(
      args.resource_name,
      agent_engine=agent_engines.AdkApp(app=app),
      requirements=requirements,
      gcs_dir_name=args.gcs_dir_name,
      extra_packages=extra_packages,
  )
  ```

  Add `env_vars={"GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true", "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental"}` to that call.

  Both `agent_engines.update(env_vars=...)` and the legacy `AdkApp(app=app, enable_tracing=True)` flag are confirmed available in the SDK (verified via local introspection during the review pass). Use `env_vars=` per the Agent Engine doc's recommendation.

  **Deploy mechanics — no-op detection at `redeploy_engine.py:297`.** The redeploy script short-circuits when `is_current` is true (no change to files under `_RUNTIME_PATHS = ("agent/superextra_agent", "agent/requirements.txt")`, see `redeploy_engine.py:92`). When this Item ships _bundled_ with Item 3 (the recommended order — see "Order of execution" below), the prompt edit lives at `agent/superextra_agent/instructions/specialist_base.md`, which IS under `_RUNTIME_PATHS` (the path is a directory prefix used as a `git log` pathspec at `redeploy_engine.py:99`). A committed prompt edit naturally bumps the runtime SHA, so no `--force` is required.

  `--force` is required only in two situations: (a) an env-var-only deploy with no committed code or prompt change; (b) the prompt edit is uncommitted at deploy time (the SHA reflects only what's committed). The bundled, committed-prompt case is the smooth path:

  ```
  # Bundled Item 3 + Item 1 (recommended): commit the prompt edit + the env_vars
  # change, then redeploy. Runtime SHA bumps from the committed prompt edit;
  # --force not needed.
  git commit -am "feat(agent): no-memory-citations rule + Cloud Trace env vars"
  python agent/scripts/redeploy_engine.py --yes
  ```

  **Critical operational risk: env_vars REPLACES the entire env list.** Verified against the SDK source at `agent/.venv/lib/python3.12/site-packages/vertexai/agent_engines/_agent_engines.py:1377-1394`: when `env_vars` is provided to `update()`, the SDK builds a fresh `deployment_spec.env = []` and an `update_mask` of `spec.deployment_spec.env`. The server replaces the entire env-var list with whatever this dict contains. Any env vars set on the engine out-of-band (via console, gcloud, or another script) get wiped.

  **Before merging the env_vars addition, audit the engine's current env-var state** and preserve any intentional ones in the dict. Suspects to check (any that may have been set outside `redeploy_engine.py`):
  - `JINA_API_KEY` — used at `web_tools.py:47`. If this is set on the engine and not in the redeploy dict, web fetches degrade to unauthenticated.
  - `GEMINI_VERSION` — used at `specialists.py:23` (defaults to `"3.1"` if unset; if set to a different value on the engine, our model selection silently changes).
  - `SUPEREXTRA_INSTRUCTIONS_DIR` — used at `agent.py:38`, `specialists.py:20`. If set on the engine, instructions load from a different path.
  - `GOOGLE_CLOUD_PROJECT` — used at `agent.py:186` for the FirestoreProgressPlugin client. ADK auto-populates this in some deploy modes; verify before assuming.

  Inspect via `gcloud beta ai reasoning-engines describe <RESOURCE_NAME>` (or the console) and merge anything intentional into the dict before deploy.

### Cloud-side prerequisites

- **Telemetry API** must be enabled on the project. Enable via console or `gcloud services enable telemetry.googleapis.com --project=superextra-site`. ADK pre-flights this and warns if missing (`adk.py:1626-1628`).
- **Service account permissions**: the Agent Engine runtime service account (the one tied to the deployed Reasoning Engine) needs Cloud Trace ingestion. The standard role is `roles/cloudtrace.agent`. Confirm against the project's existing role bindings before merge.
- **Pricing**: Cloud Trace ingestion is $0.20 per million spans, with the first 2.5 M spans/month free per billing account ([cloud.google.com/stackdriver/pricing](https://cloud.google.com/stackdriver/pricing)). At a few hundred turns/day producing ~50 spans each (~500K spans/month), we're well inside the free tier.

### Verification

1. After the env-var deploy lands, run a single research turn through the live `agent.superextra.ai` URL.
2. Open Cloud Trace explorer (Console → Trace → Trace Explorer) and filter on `gen_ai.system="gcp.vertex.agent"`.
3. Expected: a top-level `invoke_agent` span for the router, nested `invoke_agent` for the lead, nested `execute_tool` rows per AgentTool/specialist, nested `generate_content` rows for each Gemini call.
4. Spot-check `gen_ai.usage.input_tokens` / `output_tokens` are populated on the LLM spans.

### What this does NOT replace in `firestore_events.py`

`firestore_events.py` builds **user-facing pill text** ("Searching Google Places for Joe's Pizza") consumed by `StreamingProgress.svelte` via Firestore `onSnapshot`. That UX feature is engineered for end-user narration on the agent's frontend — not engineering debugging. Cloud Trace data is not queryable from the browser without an authed proxy and isn't shaped for narration. The cleanups in **Item 2** are what trim `firestore_events.py`; Cloud Trace just gives engineering a separate, better surface.

### Known caveats

- ADK Python ≥1.17.0 required for the auto-on-via-env behaviour. Confirm the version pinned in `agent/requirements.txt` before deploy.
- Two open ADK GitHub issues touch tracing: `#4742` (`call_llm` spans not always ended in multi-agent setups) and `#4894` (OTel context detach errors when a `BaseAgent` wrapper exits early). Neither is known to affect Superextra's `SequentialAgent + AgentTool` shape, but worth knowing.
- I could not confirm from the public Vertex tracing doc the **exact IAM role** required for ingestion. `roles/cloudtrace.agent` is the standard Cloud Trace role; verify against the deployed runtime service account before flipping the env var on.

### Rollback

Remove the env var entry from the `agent_engines.update(...)` call and redeploy. No code changes elsewhere; nothing depends on tracing being on.

---

## Item 2 — Migrate `FirestoreProgressPlugin` to typed hooks; delete event parsers

### Why

`firestore_events.py` is 438 lines. The pill-construction parsers — `_map_function_call` (44 lines), `_map_function_response` (95 lines), `_map_router_complete` (10 lines), and the `narrate` detection inside `map_event` (11 lines) — exist solely to **reverse-engineer ADK Event objects** for tool-call observation. ADK provides typed plugin hooks that hand us the same information directly with structured arguments. Subscribing to those hooks lets us delete those parser branches.

This is a root-cause fix: stop parsing events to figure out "did a tool just get called", start subscribing to "tool just got called" and reading typed args.

**Important: the low-level introspection helpers `_iter_function_calls`, `_iter_function_responses`, `_state_delta`, `_get`, and `extract_sources_from_grounding` STAY** even after the parsers are deleted. The eval harness depends on them — `agent/evals/parse_events.py:14-19` imports four of them and uses `_iter_function_calls` at `:78` to compute `fetched_urls` and `tool_call_counts` for offline run analysis. Deleting them would break the eval pipeline. Treat them as the public introspection API of `firestore_events.py`.

### Verified plumbing — hook list, signatures, firing semantics

Reading `src/google/adk/plugins/base_plugin.py` on `main` (commit current as of 2026-04-30) — these are the real hooks:

- `before_tool_callback(*, tool, tool_args, tool_context) -> Optional[dict]` — fires before each tool execution. Source: `flows/llm_flows/functions.py:513` (sync path), `:744` (live). Once per `FunctionCall` part. Returning a non-`None` dict short-circuits actual tool execution and replaces the result.
- `after_tool_callback(*, tool, tool_args, tool_context, result) -> Optional[dict]` — fires after successful tool execution (or after `on_tool_error_callback` returned a substitute). Source: `flows/llm_flows/functions.py:551` (sync), `:787` (live). Non-`None` return replaces the result.
- `on_tool_error_callback(*, tool, tool_args, tool_context, error) -> Optional[dict]` — fires per exception, including the unknown-tool-name case which can fire **before** `before_tool_callback`. Source: `flows/llm_flows/functions.py:455, :494, :537`. Non-`None` return suppresses the exception.
- `before_model_callback(*, callback_context, llm_request) -> Optional[LlmResponse]` — once per LLM call. Source: `flows/llm_flows/base_llm_flow.py:217`.
- `after_model_callback(*, callback_context, llm_response) -> Optional[LlmResponse]` — once per model response. Source: `flows/llm_flows/base_llm_flow.py:288`. `llm_response.usage_metadata` exposes input/output token counts.
- `on_model_error_callback(*, callback_context, llm_request, error) -> Optional[LlmResponse]` — once per model exception. Source: `flows/llm_flows/base_llm_flow.py:354/396/402`.
- `before_agent_callback(*, agent, callback_context) -> Optional[Content]` and `after_agent_callback(*, agent, callback_context) -> Optional[Content]` — sub-agent transitions. Source: `base_plugin.py:198-231`.
- `on_event_callback(*, invocation_context, event) -> Optional[Event]` — fires for every event, including the same `function_call` and `function_response` events the typed hooks already cover.

**AgentTool nesting works without extra wiring.** `AgentTool.run_async` constructs the inner `Runner` with the parent's plugin list (`src/google/adk/tools/agent_tool.py:230-238`, `include_plugins=True` is the default and is what `agent.py:154` already passes). Same plugin instance fires for the specialist's internal model + tool calls.

### Critical fact: `on_event_callback` and `before_tool_callback` BOTH fire for the same call

Verified by reading `runners.py:891-905` and `flows/llm_flows/functions.py:507-599`: events are produced by the LLM flow and yielded to the runner's `_exec_with_plugin` loop, which calls `on_event_callback` for **every event** including the function-call event that immediately precedes tool execution. Nothing suppresses `on_event_callback` when the typed hooks fire.

So if we keep both, we'll see each tool call **twice on the way in** and **twice on the way out**. Rule for this migration: **typed hooks own all tool-call observation; `on_event_callback` keeps only the concerns it is uniquely needed for** (grounding metadata aggregation, state-delta observation, final-response detection).

A stable cross-hook ID exists if dedup is ever needed: `function_call.id` is on both `tool_context.function_call_id` (for typed hooks) and on `event.get_function_calls()[i].id` / `event.get_function_responses()[i].id` (for `on_event_callback`). Source: `src/google/adk/agents/context.py:73-84` and `src/google/adk/events/event.py:100-116`.

### Replacement map — what gets deleted, what stays

Target file: `agent/superextra_agent/firestore_events.py`.

| Concern in `firestore_events.py`                   | Current location          | Replacement                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `_map_function_call`                               | lines 240-283 (~44 lines) | **Delete.** Replace with `before_tool_callback` in the plugin. `tool.name`, `tool_args`, and `tool_context.function_call_id` are direct args.                                                                                                                                                                                                                                                                                 |
| `_map_function_response`                           | lines 286-380 (~95 lines) | **Delete.** Replace with `after_tool_callback` (success) + `on_tool_error_callback` (failure). `result` dict is a direct arg.                                                                                                                                                                                                                                                                                                 |
| `narrate` detection inside `map_event`             | lines 142-152 (~11 lines) | **Delete.** The `narrate` tool call is just a `before_tool_callback(tool.name='narrate', tool_args={'text': ...})` — we read `tool_args["text"]` directly and emit the timeline pill.                                                                                                                                                                                                                                         |
| `_iter_function_calls`, `_iter_function_responses` | lines 70-95               | **Keep.** Public introspection API; used by `agent/evals/parse_events.py:14, 78`. Deletion would break the eval harness.                                                                                                                                                                                                                                                                                                      |
| `_get`, `_state_delta`, `_has_state_delta`         | helpers throughout        | **Keep.** Same reason — public introspection API used by evals.                                                                                                                                                                                                                                                                                                                                                               |
| `extract_sources_from_grounding`                   | lines 177-197             | **Keep.** Grounding metadata lives on the LLM response and is not surfaced as a typed argument to any tool/model hook. Read it from `on_event_callback`'s event (current path) or from `after_model_callback`'s `llm_response.grounding_metadata` (cleaner — but the merged grounding output in events is already aggregated, so the migration cost vs. value isn't worth it right now). Also imported by evals.              |
| `_map_router_complete`                             | lines 200-209             | **Defer to a follow-up.** Router transfer detection _should_ become implicit via `before_tool_callback(tool.name='transfer_to_agent')` + `after_agent_callback(agent.name='router')`, but this needs a test that actually proves the typed-hook coverage on Agent Engine before we can drop it. Keep the parser in this first pass; remove in a follow-up after `transfer_to_agent` typed-hook firing is verified end-to-end. |
| `_map_final_complete`                              | lines 212-237             | **Keep.** The final-reply detection logic (reads `final_report_followup` then `final_report` from state delta, falls back to event text) is event-level state inspection that has no typed-hook equivalent. The `extract_sources_from_grounding` call inside it stays.                                                                                                                                                        |
| `_ingest_place_names`                              | lines 383-393             | **Keep.** State-delta observation; no typed hook for this (`on_state_change_callback` does not exist — issue `#4393` confirmed it as not-supported).                                                                                                                                                                                                                                                                          |

Net deletion in this first pass: ~150 lines (the three parser blocks above). The file's purpose stays the same — turn ADK runtime signals into pill rows for the UI — but tool-call observation switches from parsing event part shapes to reading typed hook arguments.

### Critical requirement: preserve the accumulator

The pill-write path today is **not** "build a dict, write it." Every detail event passes through `GearRunState.observe_event` (`gear_run_state.py:85-122`), which:

- Filters detail events through `TurnSummaryBuilder.accept_detail` for dedupe — keyed on `(group, family, text)` (`timeline.py:27-36`). Without this gate, parallel specialist tool calls that produce identical pill text (e.g. two specialists each searching for the same query) would emit duplicate rows.
- Drains `_tool_src_*` keys from event `state_delta` and routes them through `_merge_source` to populate `specialist_sources` (`gear_run_state.py:113-116, 124-131`). This is how the source pills under the final reply get assembled.
- Captures the final reply on the first `complete` event via `_capture_final` (`gear_run_state.py:119-120, 133-148`).

The typed-hook code MUST route through the same accumulator. Concretely: typed hooks build a pill dict, then call a new `GearRunState.observe_typed_pill(pill)` method (or similar) that runs the pill through `accept_detail` and writes via `timeline_writer` — mirroring the event-side path. **Do not** write pills directly to `TimelineWriter` from the hooks; that bypasses dedup and produces duplicate UI rows.

`_merge_source` and `_capture_final` are unaffected by this migration — they consume signals (`_tool_src_*` state-delta keys and `complete` events) that don't have typed-hook equivalents and stay on the `on_event_callback` path.

### Files to change

- `agent/superextra_agent/firestore_progress.py` — add the typed hook overrides on `FirestoreProgressPlugin`. Each one builds a timeline pill dict and hands it to the accumulator (per the requirement above). Sketch:

  ```python
  @override
  async def before_tool_callback(self, *, tool, tool_args, tool_context):
      per = self._state_for_tool(tool_context)  # invocation_id + run_id lookup
      if per is None:
          return None
      pill = _pill_for_tool_call(tool.name, tool_args, per.mapping_state)
      if pill is None:
          return None
      # Routes through accept_detail dedupe + writes via timeline_writer.
      # Mirrors the event-side observe_event path so pill semantics stay
      # identical regardless of whether a pill came from a typed hook or
      # from on_event_callback.
      await per.observe_typed_pill(pill)
      return None  # don't short-circuit the tool call

  @override
  async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
      ... # mirror of before_tool, builds the response-side pill
      return None

  @override
  async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
      ... # build a "Source fetch failed" / "TripAdvisor lookup failed" warning pill
      return None
  ```

  The `_state_for_tool(tool_context)` helper is the typed-hook analogue of the existing `_state_for_event(invocation_context)` at `firestore_progress.py:355-373`. Use the public `tool_context.invocation_id` (and `tool_context.agent_name`, `tool_context.session` if needed) — these are exposed on `ReadonlyContext` (verified at `agent/.venv/lib/python3.12/site-packages/google/adk/agents/readonly_context.py:43-65`). Don't reach into `tool_context._invocation_context.*`; that's private surface.

- `agent/superextra_agent/gear_run_state.py` — add the `observe_typed_pill(pill)` method that wraps the existing `accept_detail` + `timeline_writer.write_timeline` flow. Keep the method **sync at the dedupe step** (matching the existing `observe_event` discipline at `gear_run_state.py:85-122`); only the timeline write is async.

- `agent/superextra_agent/firestore_events.py` — delete the parsers per the table above. `map_event` keeps:
  - Author detection for grounding source extraction (`if author in SPECIALIST_AUTHORS`).
  - `_map_final_complete` for final-reply detection (router + research_lead + follow_up).
  - `_ingest_place_names` for state-delta key tracking.

- No changes needed in `agent/superextra_agent/agent.py` — plugins are already wired through `app = App(..., plugins=[ChatLoggerPlugin(), FirestoreProgressPlugin(...)])` (`agent.py:180-189`), and the deploy uses `agent_engines.AdkApp(app=app)` (`redeploy_engine.py:314`). The `App`-carries-plugins-through-AdkApp shape is the correct one (the foot-gun in issue `#4518` is when teams pass the bare `root_agent` to `AdkApp` and silently drop plugins; we're not doing that).

### Tests to add

- `agent/tests/test_firestore_progress_hooks.py` — assertions:
  1. `before_tool_callback` with `tool.name='google_search'`, `tool_args={'query': 'pizza Gdynia'}` produces a `("search", "Searching the web", "pizza Gdynia")` pill via the writer.
  2. `before_tool_callback` with `tool.name='narrate'`, `tool_args={'text': 'Pulling menu pricing…'}` produces a `note` kind pill.
  3. `on_tool_error_callback` with `tool.name='fetch_web_content'` produces a "Source fetch failed" warning pill.
  4. `before_tool_callback` does **not** also emit on `on_event_callback` (i.e. once we own tool observation in typed hooks, the `on_event_callback` path stops emitting tool pills — verify by feeding a synthetic event with `function_calls` parts and confirming `map_event` returns no `timeline_events` for that event).
  5. **Tool exception + agent-level fallback produces exactly ONE pill, not two.** Simulate a `fetch_web_content` exception inside a specialist (whose `on_tool_error_callback=_on_tool_error` returns `{"error": ...}` per `specialists.py:163-165`). Assert: plugin `on_tool_error_callback` emits the warning pill; plugin `after_tool_callback` then fires with the substitute as `result` and **skips** emission (because `result.get("error")` is set). Net: one warning pill, no duplicate.
- Existing tests in `agent/tests/` for `firestore_events.py` will need their fixtures updated to drop the function-call/response branches (or be deleted if their only purpose was to exercise those branches).

### Verification

After deploy:

1. Run a research turn live; watch the Firestore `events` subcollection in real time. Pill rows should still appear with the same `kind` / `group` / `family` / `text` shape as before (the UI render doesn't change).
2. Specifically verify nested AgentTool calls still produce specialist pill rows. Pick a turn that exercises at least three specialists and confirm one row per specialist's tool call.
3. Check that an intentional `fetch_web_content` failure (point at an invalid URL via a probe) produces a "Source fetch failed" warning pill.
4. Run all four test suites per `CLAUDE.md` Testing section: `npm run test`, `cd functions && npm test`, `npm run test:rules`, `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v`.

### Rollback

`git revert` the migration commit. No data-shape changes in Firestore (pills look identical), so the frontend stays compatible across both versions.

### Caveats

- **`after_tool_callback` firing after a tool exception depends on whether ANY error handler returns a substitute.** Source: `flows/llm_flows/functions.py:540-546`. The chain is plugin `on_tool_error_callback` → agent-level `on_tool_error_callback` → if any of them returns a non-`None` dict, that becomes the substitute result and `after_tool_callback` then fires with that substitute. If all error handlers return `None`, the exception propagates and `after_tool_callback` is skipped.

  **This matters here because Superextra's specialists already have an agent-level `on_tool_error_callback`** — `_on_tool_error` at `agent/superextra_agent/specialists.py:163-165` returns `{"error": f"Tool {tool.name} failed: ..."}` (non-`None`). The chain for a specialist's tool exception will be:
  1. Plugin `on_tool_error_callback` (the new one we're adding) — emits a "Source fetch failed" / "TripAdvisor lookup failed" warning pill, returns `None`.
  2. Agent-level `_on_tool_error` — returns the `{"error": ...}` substitute.
  3. Plugin `after_tool_callback` — fires with the substitute as `result`.

  Without care, step 3 emits a _second_ pill (a success-shaped one for the substitute), which would render as a duplicate next to the warning from step 1. **Add a test case** for "tool exception + agent-level fallback" that asserts only one pill is written. The plugin's `after_tool_callback` should detect substitute-style results (`result.get("error")` present) and skip pill emission, since the warning was already written in `on_tool_error_callback`.

  Note that for tools that don't have an agent-level error handler (e.g. tools on the lead or enricher), the chain stops at step 1 and there's no duplicate-pill risk. The risk is specialist-tool-only.

  To guarantee a terminal pill row per call regardless of path, plug into all three (`before_tool` / `after_tool` / `on_tool_error`) but make the three handlers aware of each other's emissions via the new test above.

- **Plugin order matters.** `runtime/PluginManager._run_callbacks` runs plugins in registration order; first non-`None` short-circuits subsequent plugins **and any agent-level callbacks of the same kind**. Source: `plugin_manager.py:284-307`. We currently register `[ChatLoggerPlugin(), FirestoreProgressPlugin(...)]` in `agent.py:184`. Verified during the review pass: `ChatLoggerPlugin`'s typed-hook overrides at `chat_logger.py:287-340` all `return None`, so they will not short-circuit the `FirestoreProgressPlugin` hooks. Don't change this without revisiting the order.
- **AgentTool's nested runner uses a fresh `InMemorySessionService`.** The `_is_nested_invocation` discriminator at `firestore_progress.py:251-266` already handles this for the run-level callbacks. Typed hooks don't need the same gate (they fire from inside the inner runner naturally and propagate to the same plugin instance), but the `_state_for_tool` helper has to look up the parent state via `invocation_id` or `run_id` rather than session id. The existing `_state_for_event` helper at `firestore_progress.py:355-373` already does this lookup pattern; mirror it.
- **Issue #4518** (closed 2026-02-19) — plugins silently dropped on Agent Engine deploy if you pass the bare `root_agent` to `AdkApp` instead of `App(plugins=[...])`. We're already on the correct shape; just don't change it.

---

## Item 3 — Add a "no memory citations" rule (and keep `web_tools.py`)

### Verification trail (why the original "swap to `url_context`" idea was deferred)

The original idea was to delete the custom `fetch_web_content` (`web_tools.py`, 79 lines) and replace it with ADK's built-in `url_context`, on the theory that built-in grounding would prevent the model from citing URLs it never fetched.

I verified this against the live ADK and Gemini docs and the conclusion is **"out of scope for this lean cleanup; not a one-line swap."** The picture is more nuanced than the first verification pass concluded:

- `url_context` is a real ADK built-in tool (defined at `src/google/adk/tools/url_context_tool.py`, importable as `from google.adk.tools import url_context`). Confirmed.
- It is a **passive grounding source**, not an active function tool — Gemini decides which URLs to fetch from prompt context. Confirmed via `ai.google.dev/gemini-api/docs/url-context` and `docs.cloud.google.com/vertex-ai/generative-ai/docs/url-context`.
- **Gemini 3 has documented support for combining URL Context with custom function tools.** The Gemini API page states: _"Gemini 3 models support combining built-in tools (like URL Context) with custom tools (function calling)."_ An older blanket prohibition (_"Tool use ... with function calling is currently unsupported"_) is still on the same page but reads as legacy language predating the Gemini 3 exception.
- The Vertex AI URL Context page (which governs our Agent Engine deploy) doesn't address the combination explicitly — neither confirms nor denies behavior for our setup.
- We're on Gemini 3.1 (`agent/superextra_agent/specialists.py:78-79` declares `MODEL = "gemini-3.1-pro-preview"` and `SPECIALIST_MODEL = "gemini-3.1-pro-preview-customtools"` — note the literal `customtools` suffix, which suggests a tool-supporting variant).
- ADK's `tools/limitations` page uses a `url_context_agent` sub-agent as a counter-example, and only `GoogleSearchTool` and `VertexAiSearchTool` have a `bypass_multi_tools_limit` escape hatch.

Conclusion: per the Gemini docs, the combination _should_ work for our model. But ADK's behavior on Vertex AI Agent Engine for our specific configuration (9 AgentTool specialists, `narrate` function tool, Places tools, all alongside `url_context`) is **unproven** — we have documented model-side support, no documented Vertex/Agent-Engine guidance, and an ADK limitations page that calls out `url_context` specifically as not safe to wrap in sub-agents. **Verifying that this works end-to-end for our setup is a spike and a behavioural eval, not a one-line config swap.** That's a non-lean semantic change with its own design space (would the lead use `url_context` directly, or only specialists; would we keep `google_search` alongside it; what's the citation-fabrication delta in production), and it doesn't belong in this small cleanup. Revisit as a separate piece of work if `fetch_web_content` ever accrues real complexity or if the citation-fabrication problem persists after Item 3's prompt rule lands.

### What we ship instead — a one-line prompt rule

The original concern (Domiporta/Gratka-style fabricated citations) is a **prompt discipline** problem. The lean fix is a single rule in `specialist_base.md` that takes ~2 lines.

### Files to change

- `agent/superextra_agent/instructions/specialist_base.md:13-19` — the existing "How to answer" section already contains:

  ```
  - Cite sources with origin noted.
  - Acknowledge gaps honestly. Never fabricate data.
  ```

  Tighten by replacing the second bullet with a single rule that names the failure mode explicitly:

  ```
  - Acknowledge gaps honestly. Never fabricate data.
  - **Cite only sources you actually fetched via tools (`google_search`, `fetch_web_content`, `get_*` tools).** If a source isn't in your tool results, do not cite it — even if you can recall the URL or domain from training data. When unsure whether a fact is grounded in this turn's evidence, omit it or say "no source verified this turn."
  ```

  This addresses the root cause (the model citing URLs it remembers from training instead of URLs it actually fetched in this turn) without adding a verifier downstream.

- `agent/superextra_agent/instructions/research_lead.md:75` — the existing rule reads:

  ```
  5. **Cite sources.** Google Places data can be cited as "Google Places." Preserve specialist citations. Do not add uncited findings from memory.
  ```

  This already has a "do not add uncited findings from memory" clause — verify the wording is strong enough; if not, tighten with the same explicit framing as the specialist rule.

### Why we keep `web_tools.py`

`agent/superextra_agent/web_tools.py` is 79 lines, all of which are necessary:

- A single `httpx.AsyncClient` + `_get_client()` factory + `atexit` cleanup (lines 1-29).
- `fetch_web_content(url)` (lines 32-78) — wraps Jina AI's `r.jina.ai` reader (`https://r.jina.ai`), follows redirects, caps content at 15K chars, returns a typed result dict with `status` + `content` or `status` + `error_message`.

Nothing in there is reinvented infrastructure. The Jina reader is doing the heavy lifting (HTML→Markdown extraction, JS rendering, ad/nav stripping). Our wrapper is a thin async HTTP client. The existing failure-mode pill ("Source fetch failed", `firestore_events.py:377-378`) handles the common failure cases.

### Verification

1. After the redeploy lands, replay any Tricity venue research query (e.g., the Monsun Gdynia Turn-1 from the V2.3 ship validation) **through the eval harness** — not directly against production. The harness captures the full ADK event stream, which is the only surface that lets you cross-check cited URLs against actually-fetched URLs.
2. Run `agent/evals/parse_events.py::parse_run` against the captured events. The output's `fetched_urls` set is the ground truth for what the agent actually fetched in this turn. The output's `final_report` is the report text the agent emitted.
3. Spot-check 3 random URLs from the report's citation list. Every cited URL should appear in `fetched_urls`. If any cited URL is not in the fetched set, the rule isn't biting — try a stronger prompt formulation or escalate to a verifier (out of scope for this plan).

(Earlier drafts pointed at two production verification surfaces that don't work for this purpose. `Firestore turnSummary.notes` doesn't exist — `TurnSummaryBuilder.build_summary` at `agent/superextra_agent/timeline.py:38-44` only emits `startedAtMs`, `finishedAtMs`, `elapsedMs`, and `agent/tests/test_gear_run_state.py:157` asserts `"notes" not in turn_update["turnSummary"]`. `ChatLoggerPlugin` JSONL files were also suggested, but `chat_logger.py:33` writes them to `/tmp/agent_logs` when `K_SERVICE` is set — i.e. on Agent Engine's Cloud Run-style runtime — and that path is ephemeral and not operator-accessible. The eval harness is the only viable verification surface; if a live citation audit ever becomes necessary, the right move is Cloud Trace content capture (Item 1, with `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY`) or explicit structured logging — not the ChatLogger files.)

### Rollback

Revert the two prompt files and run an Agent Engine redeploy (the same redeploy mechanics as the original ship; instructions are baked into the cloudpickled runtime, not read live). No frontend or Cloud Functions changes.

### Important: prompts ship via Agent Engine redeploy

`agent/superextra_agent/specialists.py:109` reads `specialist_base.md` at module import time, and `_make_instruction` at `:111-136` merges the body into per-specialist templates also at import. Both happen when the Agent Engine runtime cloudpickles and starts the agent. **Editing the prompt file and committing the change is not enough — it requires `python agent/scripts/redeploy_engine.py --yes` to take effect in production.** Plan accordingly with Item 1 (see "Order of execution" below).

---

## Order of execution

1. **Bundle Item 3 + Item 1 in one Agent Engine redeploy.** Item 3 is a prompt edit that requires a redeploy (prompts are baked at import time per `specialists.py:109`); Item 1 is an env-var change that also requires a redeploy. Doing them together saves a deploy cycle and there's no functional reason to separate them — they touch independent surfaces (prompt vs. tracing config) and are individually revertable. **Commit the prompt edit before deploying** — the runtime SHA reflects committed changes only (`redeploy_engine.py:99`), and `agent/superextra_agent/instructions/specialist_base.md` lives under `_RUNTIME_PATHS` so a committed prompt edit naturally bumps the SHA. The deploy then runs without `--force`. (`--force` is only needed if the prompt edit is uncommitted at deploy time, or if shipping env-var changes alone with no committed code/prompt change.)
2. **Item 2 next** (plugin hook refactor). Highest blast radius (touches the live progress plumbing). Doing it after Item 1 means Cloud Trace data is available to verify the migration didn't break tool-call observation. Deploy with extra eyes on the first few production runs after.

Each item is independently revertable (see per-item rollback notes).

---

## What this plan deliberately does not do

- **No claim-verification agent.** Symptom treatment. Item 3's prompt rule addresses the cause (memory citations), not the consequence (need to verify after the fact).
- **No intent-shaped prompting for prioritization questions.** The V2.3 summary flagged "focus loss on decision questions" as a _risk_ under "what we're watching," not a confirmed failure. We have no production evidence operators are unhappy with the current behaviour on decision-shaped questions. Adding conditional output-shape logic now would be design-for-hypothetical-future. Revisit if Cloud Trace data (post-Item-1) plus production observation reveal a real problem.
- **No replacement of `fetch_web_content` with `url_context`.** Gemini 3 docs indicate the combination is supported model-side, but ADK/Vertex Agent Engine behavior for our specific multi-AgentTool configuration is unproven; verifying it is a behavioural spike and an eval, not a one-line swap. Documented in Item 3.
- **No follow-up-turn eval extension.** The summary's "what's next" item is still open, but no production failure has been observed since the routing collapse to justify spending the time. Revisit if production traces (post-Item-1) show a real follow-up regression.
- **No cross-market source priors variant.** Same reasoning: no felt need yet.
- **No iterative-dispatch instrumentation.** Item 1 (Cloud Trace) will give us the per-tool timing data the iterative-dispatch strategy doc was asking for, without any custom instrumentation.
- **No deletion of `web_tools.py`.** Verified to be lean (79 lines) and infrastructure that the model uses. The original "delete custom code" instinct was good; the file just turned out to already be lean.

---

## Open questions (need verification before merge)

1. ~~`agent_engines.update(env_vars=...)`~~ — **resolved during review.** Both `agent_engines.update(env_vars=...)` and the legacy `AdkApp(app=app, enable_tracing=True)` flag are confirmed available; we use `env_vars=` per the doc's recommendation. Verified at `_agent_engines.py:807, 830`. **Caveat**: the SDK builds `deployment_spec.env = []` fresh and the update mask replaces the whole list (`_agent_engines.py:1377-1394`). Audit existing engine env vars before merge — see Item 1's "Critical operational risk" callout.
2. **Service account permissions for Cloud Trace** — confirm the Agent Engine runtime service account has `roles/cloudtrace.agent` (or equivalent) bound. Console: IAM page for project `superextra-site`.
3. ~~`ChatLoggerPlugin` typed-hook overrides~~ — **resolved during review.** Verified at `chat_logger.py:287-340` that all typed hooks return `None`; will not short-circuit the progress plugin.
4. **Plugin firing for `transfer_to_agent`** — confirm `transfer_to_agent` shows up as a `before_tool_callback` (it's a function tool from ADK's perspective) and that `after_agent_callback(agent.name='router')` fires on direct-answer turns. Both are required before `_map_router_complete` can be deleted in the follow-up pass referenced in Item 2's replacement-map table.

---

## Verification discipline for plans in this codebase

This plan went through three review passes; each surfaced material errors the prior pass missed. The errors clustered around four specific kinds of unverified claim. Future plans touching the agent runtime should run these checks explicitly:

- **Three-layer verification for agent-runtime plans.** Verify against (1) repo code, (2) the locally installed SDK in `agent/.venv/...`, and (3) the deployed configuration on Agent Engine. _Caught in pass 3:_ the `env_vars` REPLACE semantics live in the local SDK source (`_agent_engines.py:1377-1394`) — readable but not consulted on the first two passes.
- **Search all callers before claiming a deletion is safe.** Production code, tests, evals, and scripts. Don't stop at the first matching grep. _Caught in pass 2:_ `_iter_function_calls` was claimed deletable because "only the parsers use it" — but `agent/evals/parse_events.py:14` imports it.
- **Separate "documented by provider" from "verified in this repo's exact stack" for external APIs.** Provider docs describe the API surface; whether it works for our specific configuration is a separate question. _Caught in pass 2 and 3:_ `url_context` + function calling is documented as Gemini-3-supported, but ADK's behavior on Agent Engine for our 9-AgentTool setup is unproven.
- **Check the deploy script's staleness logic and replacement semantics for any deploy-impact claim.** The `_RUNTIME_PATHS` pathspec, the `--force` requirement, the env-var replacement behavior — all live in the deploy plumbing. _Caught in pass 3:_ a committed prompt edit _does_ bump the runtime SHA because `_RUNTIME_PATHS` uses directory-prefix matching at `redeploy_engine.py:99`.

These are operational checks, not process gates. Skip any that don't apply to a given plan.

---

## References

### ADK source paths cited (all on `github.com/google/adk-python` `main`)

- `src/google/adk/plugins/base_plugin.py` (BasePlugin signatures, lines 114-372)
- `src/google/adk/runners.py:891-905` (`Runner._exec_with_plugin` event yield + `on_event_callback` invocation)
- `src/google/adk/flows/llm_flows/functions.py:429-599` (tool-call lifecycle: span open, before_tool, run, after_tool, on_tool_error)
- `src/google/adk/flows/llm_flows/base_llm_flow.py:217-410` (model-call lifecycle: before_model, after_model, on_model_error)
- `src/google/adk/tools/agent_tool.py:115-238` (AgentTool inner-runner construction; `include_plugins=True` default)
- `src/google/adk/agents/context.py:73-84` (`function_call_id` property on `Context`)
- `src/google/adk/events/event.py:100-116` (`get_function_calls` / `get_function_responses`)
- `src/google/adk/telemetry/tracing.py:135, 168, 299, 716` (span emission)
- `src/google/adk/telemetry/setup.py:48` (`maybe_set_otel_providers`)
- `src/google/adk/telemetry/google_cloud.py` (Cloud-side exporter setup)
- `src/google/adk/tools/url_context_tool.py` (`UrlContextTool` definition)
- `src/google/adk/tools/__init__.py` (lazy import map)

### Vertex AI / Gemini docs

- Agent Engine tracing setup: <https://cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/tracing>
- ADK observability: <https://adk.dev/observability/traces/>
- ADK Cloud Trace integration: <https://adk.dev/integrations/cloud-trace/>
- ADK plugins: <https://adk.dev/plugins/>
- ADK callbacks: <https://google.github.io/adk-docs/callbacks/types-of-callbacks/>
- ADK tool limitations: <https://adk.dev/tools/limitations/>
- Gemini URL Context: <https://ai.google.dev/gemini-api/docs/url-context>
- Vertex AI URL Context: <https://cloud.google.com/vertex-ai/generative-ai/docs/url-context>
- OpenTelemetry GenAI semantic conventions: <https://opentelemetry.io/docs/specs/semconv/gen-ai/>
- Cloud Trace pricing: <https://cloud.google.com/stackdriver/pricing>

### ADK GitHub issues consulted

- `#4464` — Plugin callbacks not invoked by InMemoryRunner (closed 2026-03-02, not-reproducible).
- `#4518` — BigQuery plugin silently dropped on Agent Engine deploy when `App` is unwrapped (closed; root cause: deploy `AdkApp(app=app)`, not bare `root_agent`).
- `#4742` — `call_llm` spans not always ended in multi-agent setups (open).
- `#4894` — OTel context detach errors when a `BaseAgent` wrapper exits early.
- `#4393` — `on_state_change_callback` does not exist as a hook (closed correctly; we keep state-delta parsing in `on_event_callback`).
- `#5503` — `cli_eval` bypasses `App.plugins` (open; affects eval, not production).

### Local code referenced

- `agent/superextra_agent/agent.py` — pipeline assembly
- `agent/superextra_agent/firestore_progress.py:337-577` — `FirestoreProgressPlugin` class
- `agent/superextra_agent/firestore_events.py` — event mapper to be trimmed
- `agent/superextra_agent/web_tools.py` — `fetch_web_content` (kept)
- `agent/superextra_agent/instructions/specialist_base.md:13-43` — citation rules + source priors
- `agent/superextra_agent/instructions/research_lead.md:19-87` — lead process + final-report requirements
- `agent/scripts/redeploy_engine.py:312-318` — deploy command
