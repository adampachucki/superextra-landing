# Thought Stream + Activity Production Plan

**Date:** 2026-05-04
**Scope:** Ship the live "thought stream + tool activity" UX from `/agent/preview` (Step blocks variant) into the production chat at `/agent/chat`. Keep the implementation lean by using ADK / Google primitives wherever they exist; add our own code only where we have verified no native equivalent.

---

## 0. Source of truth for this plan

Two parallel research passes were run before writing this plan:

- **ADK / Vertex AI Agent Engine gap audit** — reads `agent/.venv/lib/python3.12/site-packages/google/adk/` source (ADK 1.28.0), `adk.dev`, `cloud.google.com/vertex-ai/...`, `ai.google.dev/gemini-api/docs/...`. Goal: catch every place we hand-rolled something Google ships.
- **mikeoss precision re-review** — reads `willchen96/mike` files at HEAD via `gh api`. Goal: catch every cadence / UX trick we should mirror.

Verbatim file/line citations are inline. **No claim in this plan is unverified.** If something below is uncertain, it is marked `RISK` or `OPEN`.

---

## 1. Where we are right now

### 1.1 Live engine state — IMPORTANT

The live Reasoning Engine is running these changes today (deployed via `redeploy_engine.py --force --yes`):

- **`include_thoughts=True`** on `THINKING_CONFIG` and `MEDIUM_THINKING_CONFIG` (`agent/superextra_agent/specialists.py:84–90`). All research-path agents — `context_enricher`, `research_lead`, and every specialist via AgentTool — emit Gemini thought summaries. **Excluded:** `router` and `follow_up`, which both run on `_FAST_MODEL` (`gemini-2.5-flash`) with no `generate_content_config` (`agent.py:117`); a simple follow-up turn is expected to produce no thought stream.
- **Thought-part mapper** in `agent/superextra_agent/firestore_events.py:120–149` — `map_event` extracts `part.thought=True` text and emits `kind: 'thought'` rows; `_extract_search_queries` extracts `event.grounding_metadata.web_search_queries` and emits `Searching the web` rows. Three new unit tests in `agent/tests/test_firestore_events.py`.
- Agent tests pass; after the Stage 2 test additions, the suite is 161 passed / 17 skipped.

**⚠️ The above edits are uncommitted in the working tree.** The deploy bundles `./superextra_agent` from the working tree, so the live engine has the dirty code, but the deployed-marker SHA in GCS still points to the last committed runtime sha. Implications:

- A fresh `redeploy_engine.py --yes` (without `--force`) will **skip** because the marker equals HEAD — the noop guard fires before staging.
- Anyone redeploying must pass `--force --yes`, OR commit the runtime files first and then deploy normally.
- Recommended: commit `specialists.py`, `firestore_events.py`, and the three instruction-file nudges, push, then redeploy plain `--yes`. After commit, the marker advances naturally on the next deploy.

### 1.2 In production frontend code (already used by `/agent/chat`)

- `src/lib/chat-types.ts` — `TimelineEvent` union extended with `{ kind: 'thought'; id; author; text; ts? }`.
- `src/lib/components/agent/LiveActivity.svelte` — has a `kind === 'thought'` branch that renders `ev.text` as markdown via `marked`.
- `src/lib/typewriter.ts` — `setTarget` now keeps position when the new target extends the displayed prefix (so growing thought buffers don't restart from char 0).
- `src/lib/components/agent/TypewriterText.svelte` — reuses one `TypewriterController` across text changes instead of creating a fresh one each $effect run.

### 1.3 Pending deploy

Three prompt edits added local-only — nudges so Gemini avoids leaking internal tool names in thought summaries:

- `agent/superextra_agent/instructions/specialist_base.md` (one bullet under Boundaries)
- `agent/superextra_agent/instructions/research_lead.md` (one bullet under Key principles)
- `agent/superextra_agent/instructions/context_enricher.md` (one bullet under What you do NOT do)

Deploy after committing runtime files with `cd agent && .venv/bin/python scripts/redeploy_engine.py --yes`. If deploying the current dirty tree intentionally, use `--force --yes`; plain `--yes` skips while the marker still equals HEAD.

### 1.4 Preview-only (not in production yet)

`/agent/preview` has three switchable variants (Stream, Stream + Rail, Step blocks), live Firestore subscription with `?sid=` URL param + replay-speed controls, header label derived from `event.author` / latest tool family, animated `...` typing dots, and `fade`/`fly` transitions on new blocks. The user has chosen **Step blocks** as the production shape.

---

## 2. What ADK / Google ships — and what they don't

All claims below are read directly from the installed ADK source (1.28.0) at `agent/.venv/lib/python3.12/site-packages/google/adk/`.

### 2.1 Things ADK provides that we are **already using correctly**

| Primitive                                                                | File                                                                                             | Our usage                                                                                                                                               |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BasePlugin` lifecycle hooks                                             | `plugins/base_plugin.py`                                                                         | `FirestoreProgressPlugin` subclasses `BasePlugin` — same shape as `LoggingPlugin` (`plugins/logging_plugin.py:106-127`).                                |
| `Event.is_final_response()`                                              | `events/event.py:83-98`                                                                          | `firestore_events._map_complete` calls it — exact predicate we need.                                                                                    |
| `Part.thought: bool`                                                     | typed field on `google.genai.types.Part` (referenced in `utils/streaming_utils.py:64, 320, 379`) | `_collect_thought_text` checks `getattr(part, "thought", False)`. Defensive but the field IS documented; safe to rely on.                               |
| `EventActions.transfer_to_agent`, `actions.end_of_agent`, `event.branch` | `events/event_actions.py:74, 101-104`; `events/event.py:60-68`                                   | (See §2.4 — we don't use these yet but should consider for phase grouping.)                                                                             |
| `ThinkingConfig(include_thoughts=True)`                                  | `google.genai.types` `ThinkingConfig` (`types.py:5314-5347`)                                     | Set on research-path `LlmAgent`s (§1.1): `context_enricher`, `research_lead`, and specialists. Not set on `router` / `follow_up`.                       |
| `PROGRESSIVE_SSE_STREAMING` feature flag                                 | `features/_feature_registry.py:133-135` (default-on)                                             | Active by default; we receive partial events. (See §2.4.)                                                                                               |
| Cloud Trace / OTel telemetry                                             | `telemetry/google_cloud.py:103-108`; `redeploy_engine.py:33-34`                                  | Writes `gen_ai.client.inference.operation.details` log entries. Useful for post-hoc debugging, NOT for live activity (`BatchSpanProcessor` is offline). |

### 2.2 Things ADK does **not** provide for our use case (verified absent)

| Need                                                 | What we do                                                                               | Why no native alternative                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Persist progress to Firestore from inside the engine | Hand-rolled `FirestoreProgressPlugin` (≈640 lines)                                       | Python ADK has zero Firestore session services — verified by listing `agent/.venv/lib/python3.12/site-packages/google/adk/sessions/` (in_memory, database, sqlite, vertex_ai only). The Firestore session-service page (`https://adk.dev/integrations/firestore-session-service/index.md`) is **adk-java only** (`google/adk-java/contrib/firestore-session-service`). The **nine** plugins shipped in `plugins/` (`logging_plugin`, `debug_logging_plugin`, `bigquery_agent_analytics_plugin`, `multimodal_tool_results_plugin`, `save_files_as_artifacts_plugin`, `reflect_retry_tool_plugin`, `context_filter_plugin`, `global_instruction_plugin`, plus `base_plugin` itself) are observability / tooling, not progress emitters.                                                                    |
| Browser-direct SSE to the engine                     | Browser → Cloud Function → `:streamQuery?alt=sse` then Firestore `onSnapshot`            | `:streamQuery` requires `aiplatform.user` IAM and a Google bearer token — not browser-safe. `templates/adk.py:1095-1100` flushes OTel **per call** in `async_stream_query` (the engine is a server-side runtime). The closest endorsed browser path is **AG-UI** (`https://adk.dev/integrations/ag-ui/`), which is an open protocol — CopilotKit is the most-documented adapter, but Kotlin/CLI/Go clients also exist. Adopting AG-UI for our app would replace our Cloud Function with a long-lived Node middle tier; lateral, not simpler. **`bidi_stream_query` is verified absent** on `AdkApp` in `vertexai/agent_engines/templates/adk.py` (only `async_stream_query` and the deprecated `stream_query` are exposed). **Our Cloud-Function-bridge is the supported pattern**, not an anti-pattern. |
| Display labels on agents                             | Hard-coded `AUTHOR_LABEL` map in `LiveActivity.svelte`                                   | `BaseAgent` exposes only `name: str` and `description: str = ''` (`agents/base_agent.py:111, 118-123`). No `display_name` / `title`. `description` is verbose schema text used by the LLM, not user-facing.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Display names on tools                               | Hard-coded family verbs (`google_search → "Searching the web"`) in `firestore_events.py` | `BaseTool` has `name`, `description` only (`tools/base_tool.py:50-53`). Same shape as agents.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| UI helper to render thought summaries                | `marked` in `LiveActivity.svelte`                                                        | ADK ships A2UI / AG-UI integrations only. No widget for thought summaries. (`react-markdown + remark-gfm` in mikeoss is a pure React choice; not portable.)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| Typed grounding accessors                            | Hand-iterated `web_search_queries` / `grounding_chunks[i].web.{uri,title,domain}`        | `GroundingMetadata` is a plain Pydantic schema (`types.py:7269-7307`) with no helper methods. Hand-iteration matches docs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Plugin test harness / `MockEvent`                    | `SimpleNamespace` in `test_firestore_events.py`                                          | `adk-python/tests` uses `pytest` with stub agents — same shape as ours.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Retry / fallback when Gemini omits thoughts          | Accept that some turns may have no thought parts                                         | `ThinkingConfig` exposes only `include_thoughts`, `thinking_budget` (2.5), `thinking_level` (3.x) — no retry knob. `https://ai.google.dev/gemini-api/docs/thinking` documents the level defaults but does not characterise `include_thoughts` as best-effort in those words; the empirical reality (probes of 2026-05-04 captured 11 thoughts on a 25-event run, none on some shorter runs) confirms summaries are not produced for every Gemini call.                                                                                                                                                                                                                                                                                                                                                   |

### 2.3 Things mikeoss does that we should _consider_ adopting (priority order)

| #   | Mike pattern                                                                                                                                                                                          | Mike file                                                      | Should we?                                                                                                                                                                                                                                                                                                                                                                                        |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Drop `thinking_level`** — Mike sets `{ includeThoughts: true }` only, no level. `"high"` is the documented Gemini 3 default per `ai.google.dev/gemini-api/docs/thinking`.                           | `gemini.ts:67-69`                                              | **Yes.** Removing the explicit level matches Mike, is documented as a no-op for Gemini 3, and reduces config we maintain. Keep MEDIUM where it's used (orchestrator) — that IS a deliberate cadence reduction. Net: 1-line change in `specialists.py:84`.                                                                                                                                         |
| 2   | **Wrapper auto-collapse + "Completed in N steps" label**                                                                                                                                              | `PreResponseWrapper.tsx:31-78`, latched via `hasMinimizedRef`. | **Defer out of v1.** Cannot ship as a small frontend tweak in our current architecture — `ChatThread.svelte:209` only mounts `LiveActivity` while `chatState.loading` is true, and `chat-state.svelte.ts:432` clears `liveTimeline` on terminal state, so the wrapper has no DOM to collapse into. See §3.3 for the v2 scope.                                                                     |
| 3   | **5-phrase cycling cosmetic phrase** ("Thinking → Pondering → Analyzing → Reviewing → Reasoning"), every 2 s while streaming.                                                                         | `AssistantMessage.tsx:347-373`                                 | **No** — preview already has a more honest derived label (latest tool family / agent author). The animated `...` dots cover the "still alive" cue. Skipping the cycle is a deliberate choice over a copy-paste from Mike.                                                                                                                                                                         |
| 4   | **`onReasoningBlockEnd` placeholder bridge** — when a Gemini call emits its last thought delta, push a transient "Thinking..." event so the wrapper doesn't look idle between events.                 | `useAssistantChat.ts:496-525` (`pushThinkingPlaceholder`)      | **Probably no.** We already have animated header dots that render while `chatState.loading`. The placeholder bridge solves a Mike-specific gap (their wrapper otherwise shows nothing between events). Track the visual idle gap on a real run before adding more state.                                                                                                                          |
| 5   | **Char-level streaming of thoughts** — Mike forwards every Gemini stream chunk's thought text to SSE without buffering (`gemini.ts:79-108`). Effect: thoughts type themselves character-by-character. | `gemini.ts:79-108`, `chatTools.ts:2425-2429`                   | **No (for v1).** ADK's `StreamingResponseAggregator` (`utils/streaming_utils.py:266-297`) emits `partial=True` events per chunk, so we COULD wire char-level streaming through Firestore. But the cost is ~10× more Firestore writes per turn (§3.2.A) and our typewriter already gives a typed-on feel from per-event chunks. Defer until a real run shows the per-event chunk feel falls short. |

### 2.4 Things ADK provides that we should _consider_ using (verified, simplifies our code)

| Find                                                                                                       | What it replaces                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Cost                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Skip mapping/timeline writes on partial events**                                                      | `firestore_progress.py:on_event_callback` currently runs the mapper and writes a Firestore row per partial event. `Event` extends `LlmResponse`; `LlmResponse.partial: Optional[bool]` lives at `models/llm_response.py:71`. Each thought arriving via the aggregator (`utils/streaming_utils.py:266-297`) flows through 10–50 partials per turn. Each partial creates a fresh `event.id` (`event.py:77-81 model_post_init` calls `Event.new_id()`), so our `f"thought:{author}:{event.id}"` dedupe key produces N rows for N partials, plus the final aggregated event (`partial=False`, yielded from `streaming_utils.py:340-367`) = **N+1 timeline writes per logical thought**. | **Do NOT early-return on partial.** That would skip the `lastEventAt` bump (`firestore_progress.py:535`), and `functions/watchdog.js:13` flips a session to `error` after `lastEventAt > 5 min` regardless of heartbeat freshness. Instead, gate **only the mapping + timeline writes** on `not event.partial`; keep the `fenced_session_update({lastEventAt: SERVER_TIMESTAMP})` bump for every event. Net: ~10× fewer **timeline document** writes per turn (session-doc updates still happen, by design). Removes the "thought re-renders mid-paragraph" artefact. |
| **B. ~~Phase grouping by `event.branch` + `actions.end_of_agent`~~** `RISK / DOWNGRADED`                   | These fields exist (`events/event.py:60-68`, `events/event_actions.py:101-104`), **but neither is reliably populated for our AgentTool-based topology.** `event.branch` is set by ADK Sequential / Parallel workflow agents to keep peers' histories isolated; `AgentTool` spawns a brand-new child Runner with `InMemorySessionService`, so the parent-runner sees `branch=None` on its own events. `actions.end_of_agent` is set only by ADK workflow agents per its docstring (`event_actions.py:101-104`). Empirically, the 2026-05-04 probe shows specialist thoughts arriving on the parent stream with `event.author='review_analyst'` etc., not via branch / end_of_agent.  | **Do NOT rely on these fields for phase grouping.** Use the rule documented in §3.1: bold-lead detection is primary; author change is secondary and gated through the `LEAD_AUTHORS` allowlist so AgentTool round-trips don't open new top-level steps.                                                                                                                                                                                                                                                                                                               |
| **C. `event.get_function_calls()` / `event.get_function_responses()` helpers** (`events/event.py:100-116`) | `_iter_function_calls` (`firestore_events.py:70-81`) and the response-iteration sites elsewhere hand-iterate parts.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Trivial code reduction; semantically identical.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |

These are **SHOULD-CONSIDER, not MUST-USE.** A is the only one with measurable runtime impact.

---

## 3. Production migration plan (lean cuts only)

The user picked the **Step blocks** layout as production. Stages below are ordered to ship value first.

### 3.1 Stage 1 — port Step blocks into `LiveActivity` (frontend only)

Replace the current flat list inside `<ProgressWrapper>` with the Step-blocks rendering from the preview. Same data, same types.

**Files to change**

- `src/lib/components/agent/LiveActivity.svelte`
  - Reuse the existing markdown renderer — `marked` is already imported and `renderMarkdown` already exists at `LiveActivity.svelte:9-11`.
  - Add a `$derived steps` computed from `events`. Step-boundary rule (precise):
    1. Maintain `LEAD_AUTHORS = new Set(['router', 'context_enricher', 'research_lead', 'follow_up'])`.
    2. **Open a new top-level step when** a thought event whose markdown starts with `**Bold lead**` arrives (regardless of author). The lead's `**title**` becomes the step title.
    3. **Or, fall back to:** open a new top-level step when `event.author` changes AND (a) the new author is in `LEAD_AUTHORS`, AND (b) the previous step has at least one row, AND (c) the previous author was also in `LEAD_AUTHORS`. This handles the `context_enricher → research_lead` handoff while ignoring `research_lead → review_analyst → research_lead` AgentTool round-trips.
    4. **Specialist (non-`LEAD_AUTHORS`) thoughts and tool rows attach to the current top-level step's body / tools list with no special prefix.** Adding a "via review_analyst"-style label requires plumbing `author` through the `kind: 'detail'` row schema (`chat-types.ts:34`, `firestore_events._detail`), which is out of scope for v1. Specialists' rows still show their tool family (Google reviews, TripAdvisor, etc.) — that's enough signal.
    5. Notes attach to the current step's body; details (`Searching the web`, `Google reviews`, etc.) attach to the current step's tools list.
  - Render: numbered circle + vertical guideline + step title + thoughts (markdown via `renderMarkdown`) + nested tool rows.
  - Keep the existing `Working for Xs` timer (already correct, see `LiveActivity.svelte:42`). The header label can stay simple "Working" + bouncing dots since `ProgressWrapper` already provides that — derived label is an optional layer (see §5 OPEN).
- `src/routes/agent/preview/+page.svelte`
  - Update the page header text to mark it as a reference / implementation playground (it stays — explicitly per the user's request).

**Net LOC:** ≈+90 / −10 in `LiveActivity.svelte`. No backend change. No new dependencies.

**Verification:** open `/agent/chat`, ask one real restaurant question, observe Step blocks rendering thought summaries with bold headers, tool rows nested under each step.

### 3.2 Stage 2 — apply the verified ADK simplifications

These are independent of stage 1 and can ship in any order.

**A. Skip mapping + timeline writes on partial events** (§2.4 A)

- `agent/superextra_agent/firestore_progress.py:on_event_callback` — wrap the `observe_event(event)` call and the timeline-write loop in `if not getattr(event, "partial", False):`. Leave the `fenced_session_update({lastEventAt: SERVER_TIMESTAMP})` bump (currently around line 535) outside that branch — it must fire for every event so watchdog liveness holds.
- Adds ≈4 lines (one if-guard, one comment).
- **Why:** ~10× fewer **timeline document** writes per turn (session-doc updates still happen, intentionally); eliminates the mid-paragraph re-render artefact.
- **Test:** add a deterministic unit test in `tests/test_firestore_progress.py` (alongside the existing `on_event_callback` tests at `:658+` that already monkey-patch `fenced_session_update`): a synthetic `event.partial=True` event must NOT trigger `observe_event` or `write_timeline`, but MUST trigger `fenced_session_update` exactly once. A `partial=False` event must trigger all three.
- **Deploy:** required (`redeploy_engine.py --force --yes` until backend changes are committed; plain `--yes` afterwards).

**B. Drop explicit `thinking_level="HIGH"`** (§2.3 #1)

- `agent/superextra_agent/specialists.py:80-83` — `THINKING_CONFIG = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(include_thoughts=True))`.
- Documented per `ai.google.dev/gemini-api/docs/thinking`: HIGH is Gemini 3's default. Removing the explicit value is a no-op for cadence and matches mikeoss's exact config.
- Keep `MEDIUM_THINKING_CONFIG` (still a deliberate reduction for orchestrator-class calls).
- **Deploy:** required.

**C. Delete dead code: `_iter_function_calls`** (§2.4 C)

- `agent/superextra_agent/firestore_events.py:70-81` — `grep -rn "_iter_function_calls"` returns one match (the definition itself). It's unused. Delete the function. Net `-12 LOC`.
- If a future caller needs to iterate function calls, use `event.get_function_calls()` (`events/event.py:100-107`) and `event.get_function_responses()` (`:109-116`) — already shipped helpers, no need to roll our own.

### 3.3 Stage 3 — DEFERRED out of v1

The previous draft proposed wrapper auto-collapse with a "Completed in N steps" label (mikeoss `PreResponseWrapper.tsx`). **This cannot ship as a small frontend change in our current architecture:**

- `src/lib/components/restaurants/ChatThread.svelte:209` only mounts `LiveActivity` while `chatState.loading` is `true`.
- `src/lib/chat-state.svelte.ts:432` detaches the events listener and clears `liveTimeline = []` on terminal state.

So the moment the turn ends, the wrapper unmounts and `liveTimeline` empties — there's no DOM left to show "Completed in N steps". Adding the props in `ProgressWrapper` accomplishes nothing visible.

**Path forward (separate v2 plan):** persist the activity timeline alongside the final reply on the message itself, and have `ChatThread` keep rendering a collapsed `LiveActivity` per past turn. That's a real scope expansion — turn-doc schema, message-history rendering, scroll behaviour. Not v1 work. Tracked here so we don't re-open it casually.

### 3.4 Stage 4 — explicit non-adoptions (decisions, not work)

The plan states these consciously so we don't revisit:

- **No 5-phrase cycling word.** Honest derived label > cosmetic rotation.
- **No char-level thought streaming.** Per-event chunks are good enough for v1; revisit only if a real run reads as too "bursty".
- **No `pushThinkingPlaceholder` bridge.** Animated header dots already cover the idle gap.
- **No switch from `AgentTool` → `transfer_to_agent` for specialists.** Empirically verified the parent plugin already sees specialist thoughts via `include_plugins=True` (probe of 2026-05-04 captured 11 thoughts, 4 from specialists).
- **No browser-direct `:streamQuery`.** Verified non-browser-safe (§2.2).
- **No `BigQueryAgentAnalyticsPlugin`.** Writes completed-run analytics to BigQuery; not a live activity channel.
- **No `ReflectRetryToolPlugin`.** Auto-retries failing tools with reflection — would emit additional thought rounds, but the plumbing change isn't needed.
- **No `bidi_stream_query`.** Verified absent on `AdkApp` in `vertexai/agent_engines/templates/adk.py` (only `async_stream_query` and the deprecated `stream_query` are exposed).
- **No `event.actions.render_ui_widgets` (UiWidget).** Provider enum currently exposes only `'mcp'` (`events/ui_widget.py:45-47`); MCP iframe widgets aren't a fit for thought rows.

**Backlog item (not in this plan):** consider hoisting the three per-instruction "no internal tool names in thoughts" prompt nudges into one App-level instruction via `GlobalInstructionPlugin`. Defer until we see if the per-file nudges hold up across a few weeks of real runs.

---

## 4. Validation plan

Lean — no permanent assertion scripts. One deterministic unit test for the partial filter; everything else reuses what already exists.

```bash
# 0. Deploy backend (prompt nudges + partial-filter + dead-code cleanup
#    + thinking_level cleanup).
#
#    redeploy_engine.py:318 skips when the runtime SHA marker matches HEAD.
#    Two safe ways to run it:
#
#      a) Commit runtime changes first (recommended), then plain --yes:
#           git add agent/superextra_agent agent/superextra_agent/instructions \
#                   agent/tests
#           git commit -m "feat(agent): production thought stream"
#           cd agent && .venv/bin/python scripts/redeploy_engine.py --yes
#
#      b) If you must deploy uncommitted work:
#           cd agent && .venv/bin/python scripts/redeploy_engine.py --force --yes

# 1. Unit tests — must include the new partial-filter test
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q
cd .. && npm test
cd .. && npm run check    # svelte-check

# 2. End-to-end probe — captures a real run, writes to Firestore
cd agent && GOOGLE_APPLICATION_CREDENTIALS=$ADC_PATH .venv/bin/python \
  scripts/probe_thought_cadence.py
# Note the sid printed at the bottom.

# 3. Manual smoke: open /agent/preview?sid=<sid> in a browser, switch to Step
#    blocks. Confirm:
#      - thought rows render as markdown with bold leads
#      - no internal tool names (get_restaurant_details, etc.) appear in any thought
#      - thought blocks don't re-render mid-paragraph (verifies partial filter)
#      - tool rows (Google Maps, TripAdvisor, web search, sources) nest under steps
#
# 4. Manual smoke: same /agent/chat path with a fresh real question. Same checks.
```

**Required pass criteria:**

- pytest + Vitest + svelte-check all green
- A manual probe run shows no `get_restaurant_details`-style identifiers in thought text
- Live activity in `/agent/chat` matches `/agent/preview` Step blocks layout

**Deterministic unit test (part of Stage 2.A delivery)** — add to `agent/tests/test_firestore_progress.py`:

```python
async def test_partial_event_skips_mapping_but_bumps_lastEventAt(...):
    """Partial events must not write timeline rows (avoids duplicates)
    but must bump lastEventAt (watchdog liveness)."""
    # event with partial=True →
    #   GearRunState.observe_event NOT called
    #   timeline_writer.write_timeline NOT called
    #   fenced_session_update called once with {'lastEventAt': SERVER_TIMESTAMP}
```

---

## 5. Open questions / risks

- `RISK` Gemini 3.1 occasionally returns NO thought parts on some turns. Production UX must degrade gracefully — Step blocks layout already does this (steps with empty thought bodies).
- `OPEN` Should the production header use the preview's derived label (`event.author` → friendly name + latest tool family) or stay as the existing `"Working for Xs" + dots`? Recommend: ship Step blocks first with the existing header, layer in the derived label only if it tests better.
- `OPEN` `event.id` is regenerated per partial event (`event.py:77-81`). The §2.4-A filter eliminates this concern, but if A is _not_ shipped, our dedupe key `f"thought:{author}:{event.id}"` will produce duplicates. Ship A.
- `RISK` `_is_nested_invocation` discriminator (`firestore_progress.py:253-268`) detects AgentTool children by `isinstance(svc, InMemorySessionService)`. This matches ADK 1.28.0: `AgentTool.run_async` passes parent plugins when `include_plugins=True` and constructs the child `Runner` with `InMemorySessionService` (`agent_tool.py:223-235`). `google-adk==1.28.0` is already pinned in `agent/requirements.txt` and consumed by `redeploy_engine.py`; watch this assumption on ADK upgrades.
- `RISK` Long-running sessions may emit `EventCompaction` events (`event_actions.py:31-48` defines the type, `:98-99` declares the field). These markers carry no text/parts; our `map_event` should ignore them gracefully but lacks an explicit unit test. **Add a test** confirming an `event.actions.compaction` non-null event produces zero timeline rows.

---

## 6. References

### Our code

- `agent/superextra_agent/specialists.py:84–90` — thinking configs
- `agent/superextra_agent/firestore_events.py:120–149` — thought + grounding mapping
- `agent/superextra_agent/firestore_events.py:70–81` — `_iter_function_calls`
- `agent/superextra_agent/firestore_progress.py:494–552` — `on_event_callback`
- `agent/superextra_agent/firestore_progress.py:253–268` — `_is_nested_invocation`
- `src/lib/components/agent/LiveActivity.svelte` — current rendering
- `src/routes/agent/preview/+page.svelte` — preview implementation reference
- `src/lib/chat-types.ts` — TimelineEvent union

### Verified ADK / Google sources (read directly)

- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event.py:60–68` — `Event.branch`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event.py:77–81` — `model_post_init` and `Event.new_id()`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event.py:83–98` — `Event.is_final_response()`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event.py:100–116` — `get_function_calls()` / `get_function_responses()`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event_actions.py:31–48` — `EventCompaction`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event_actions.py:74` — `transfer_to_agent`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event_actions.py:98–99` — `compaction` field
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/event_actions.py:101–104` — `end_of_agent`
- `agent/.venv/lib/python3.12/site-packages/google/adk/events/ui_widget.py:45–47` — `UiWidget.provider` (`mcp` only)
- `agent/.venv/lib/python3.12/site-packages/google/adk/models/llm_response.py:71` — `LlmResponse.partial`
- `agent/.venv/lib/python3.12/site-packages/google/adk/utils/streaming_utils.py:266–297` — progressive aggregator (per-chunk `partial=True`)
- `agent/.venv/lib/python3.12/site-packages/google/adk/utils/streaming_utils.py:340–367` — close path (`partial=False` aggregated)
- `agent/.venv/lib/python3.12/site-packages/google/adk/features/_feature_registry.py:133–135` — `PROGRESSIVE_SSE_STREAMING` default-on
- `agent/.venv/lib/python3.12/site-packages/google/adk/agents/base_agent.py:111, 118–123` — agent base fields
- `agent/.venv/lib/python3.12/site-packages/google/adk/tools/base_tool.py:50–53` — tool base fields
- `agent/.venv/lib/python3.12/site-packages/google/adk/tools/agent_tool.py:223–235` — `include_plugins` propagation + child `InMemorySessionService`
- `agent/.venv/lib/python3.12/site-packages/google/adk/plugins/logging_plugin.py:106–127` — Plugin shape we mirror
- `agent/.venv/lib/python3.12/site-packages/google/genai/types.py:5314–5347` — `ThinkingConfig`
- `agent/.venv/lib/python3.12/site-packages/google/genai/types.py:7269–7307` — `GroundingMetadata`
- `agent/.venv/lib/python3.12/site-packages/vertexai/agent_engines/templates/adk.py:999, 1095–1100, 1102` — `async_stream_query`, OTel flush, deprecated `stream_query`
- `https://ai.google.dev/gemini-api/docs/thinking` — `include_thoughts`, level defaults (HIGH = Gemini 3 default)
- `https://cloud.google.com/vertex-ai/generative-ai/docs/thinking` — Vertex parallel
- `https://adk.dev/integrations/firestore-session-service/index.md` — adk-java only (NOT for Python)
- `https://adk.dev/integrations/ag-ui/index.md` — open AG-UI protocol; CopilotKit is one adapter, not the only one

### mikeoss (`willchen96/mike` HEAD)

- `backend/src/lib/llm/gemini.ts:54–145` — Gemini adapter, thinkingConfig, iteration loop
- `backend/src/lib/chatTools.ts:78–135, 258–416, 2410–2454` — system prompt, tools, SSE wiring
- `frontend/src/app/components/assistant/AssistantMessage.tsx:347–422, 1156–1390` — ReasoningBlock + grouping
- `frontend/src/app/components/shared/PreResponseWrapper.tsx` — auto-collapse latch + step count
- `frontend/src/app/hooks/useAssistantChat.ts:49–177, 211–229, 449–525` — drip + placeholder bridge + reasoning handlers
- `frontend/src/app/components/shared/types.ts:83–143` — AssistantEvent union
