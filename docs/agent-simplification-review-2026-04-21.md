# Agent Simplification Review

Date: 2026-04-21

## Executive verdict

The current system is too complex for the current stage of the product.

The queue plus worker plus Firestore plus watchdog transport is solving a real problem, but that problem is largely self-created by the depth and shape of the agent pipeline. The biggest simplification opportunity is not more transport cleanup. It is reducing the default research path so it needs fewer agents, less hidden context, fewer late-stage tools, and fewer fallbacks.

The most important distinction:

- The **background execution stack is justified** if the default product path really must stay 4-10+ minutes.
- The **agent graph is not justified** in its current shape for a young product. It is carrying too much prompt architecture, too much hidden coupling, and too many "repair" layers for failures caused upstream.

## Scope reviewed

Primary code paths:

- `agent/superextra_agent/agent.py`
- `agent/superextra_agent/specialists.py`
- `agent/superextra_agent/firestore_events.py`
- `agent/superextra_agent/places_tools.py`
- `agent/superextra_agent/tripadvisor_tools.py`
- `agent/superextra_agent/chat_logger.py`
- `agent/worker_main.py`
- `functions/index.js`
- `functions/watchdog.js`
- `src/lib/firestore-stream.ts`
- `src/lib/chat-state.svelte.ts`
- `src/lib/chat-recovery.ts`

Primary docs:

- `docs/pipeline-decoupling-plan.md`
- `docs/pipeline-decoupling-implementation-review-2026-04-21.md`
- `docs/archived/agent-architecture-review.md`
- `docs/archived/agent-architecture-simplification.md`
- `agent/superextra_agent/instructions/AUTHORING.md`

Operational evidence:

- `agent/logs/*.jsonl` (26 local session traces)

## Evidence snapshot

### Current shape

- Agent graph in production code:
  - `router`
  - `context_enricher`
  - `research_orchestrator`
  - parallel specialist pool
  - `gap_researcher`
  - `synthesizer`
- Instruction files: 809 lines total under `agent/superextra_agent/instructions/`
- Runtime/control code size:
  - `agent/worker_main.py`: 836 lines
  - `agent/superextra_agent/firestore_events.py`: 460 lines
  - `functions/index.js`: 544 lines
  - `src/lib/chat-state.svelte.ts`: 769 lines

### Real runtime cost from logs

Across 25 logged runs with model activity:

- median cumulative model time per run: about 209 seconds
- max cumulative model time per run: about 353 seconds

Per-agent median response-token totals from logs:

- `synthesizer`: 132,676 tokens, max 478,537
- `gap_researcher`: 71,342.5 tokens, max 153,232
- `review_analyst`: 41,057 tokens, max 121,272
- `guest_intelligence`: 24,882 tokens
- `research_orchestrator`: 13,621.5 tokens

Per-agent median `content_count` from `model_request` logs:

- `synthesizer`: 25
- `gap_researcher`: 24
- most specialists: 13
- `research_orchestrator`: 10

That is not an "isolated specialist" system. That is a system carrying a large implicit transcript through most of the pipeline.

### Logged failure patterns

From the local JSONL traces:

- 8 model-level error cases are recorded
- most are `MALFORMED_FUNCTION_CALL`
- almost all are in `synthesizer` or `gap_researcher`

TripAdvisor matching quality is also weak:

- 47 logged `find_tripadvisor_restaurant` results with visible confidence
- 27 `high`
- 20 `low`

Low-confidence examples still include obviously wrong candidates, including hotels, tourist attractions, and a restaurant in Greece for a Berlin coffee-shop workflow.

## Main findings

### 1. The architecture's mental model does not match runtime reality

The instruction system says specialists "only see their brief and Places context" and do not see each other. That is not what the runtime is doing.

`_make_specialist()` in `agent/superextra_agent/specialists.py` never sets `include_contents`, so ADK defaults to `include_contents='default'`. The installed ADK package confirms that `default` includes full conversation history and `none` only limits to current-turn context:

- `agent/.venv/lib/python3.12/site-packages/google/adk/agents/llm_agent.py:311`
- `agent/.venv/lib/python3.12/site-packages/google/adk/flows/llm_flows/contents.py:59-74`
- `agent/.venv/lib/python3.12/site-packages/google/adk/flows/llm_flows/contents.py:537-568`

This hidden context leak explains several problems at once:

- prompt growth
- blurred agent boundaries
- specialists behaving like they have more shared context than the instruction architecture assumes
- difficulty reasoning about what an agent actually saw

This is a root-cause issue, not a prompt-tuning issue.

### 2. The tail of the pipeline is compensating for unstable late-stage agents instead of removing the cause

The codebase now has multiple fallback layers whose job is to rescue the pipeline when the end of the workflow fails:

- fallback report generation in `agent/superextra_agent/agent.py:140-165`
- empty-response / no-text fallback handling in `agent/superextra_agent/agent.py:168-219`
- degraded reply stitching in `agent/worker_main.py:478-512`
- final reply sanity gate in `agent/worker_main.py:766-803`

Those layers exist because the highest-context agents are the least stable:

- `gap_researcher` is a second research pass over already-large outputs
- `synthesizer` adds code execution on top of already-large inputs
- the logs show that these stages are exactly where malformed tool-call failures occur

This is symptom handling. The cause is the late-stage design:

- too much context
- too many tools too late
- code execution in the final reporting step

### 3. `review_analyst` is too expensive and too unreliable for the default path

`find_tripadvisor_restaurant()` defaults to the first candidate before confidence is known:

- `agent/superextra_agent/tripadvisor_tools.py:98-126`

It then computes `match_confidence`, but it does not use that confidence to reject or retry the match. That means a low-confidence match can still become the canonical source for downstream analysis.

This is already showing up in logs:

- obvious wrong candidate sets
- low-confidence matches accepted as usable
- gap research later spending effort correcting or compensating for bad upstream evidence

The tool is also expensive:

- `review_analyst` is one of the slowest and highest-token specialists in the traces
- it requires external entity matching plus multi-source review fetching

This is another root-cause problem. A weak identity-resolution step is being treated as if it were deterministic.

### 4. The router is still an LLM where a state machine would be more reliable

The current router does work conceptually, but it is not robust enough to justify being an LLM control node for default operation.

Evidence:

- `agent/tests/test_follow_up_routing.py` documents realistic prompts that still misroute
- `docs/pipeline-decoupling-implementation-review-2026-04-21.md` calls out follow-up routing as still not release quality

The current router is solving a mostly structural problem:

- if no report exists and a place is known, research
- if no report exists and no place is known, ask one clarification
- if a report exists and the request is clearly formatting / summary / drill-down, answer from report
- otherwise research again

That can mostly be handled in deterministic application code with a very small ambiguity fallback.

### 5. The source-propagation workaround appears to have outlived the original cause

`_append_sources()` in `agent/superextra_agent/specialists.py:25-74` exists to preserve grounding metadata by appending sources into the text output.

But the post-decoupling design already extracts grounding directly in:

- `agent/superextra_agent/firestore_events.py:264-272`
- `agent/superextra_agent/firestore_events.py:317-326`

And the plan explicitly described direct grounding extraction as the replacement for that workaround:

- `docs/pipeline-decoupling-plan.md` Phase 2

Keeping both paths likely increases output size and prompt size for later agents, especially the gap researcher and synthesizer, while preserving a workaround that was introduced for an earlier transport shape.

This is exactly the kind of complexity that tends to stay forever once it "saved" the system once.

### 6. The transport stack is probably appropriate for deep research, but not for every request

If the default workflow stays this heavy, the transport stack is proportionate:

- background worker
- queue
- Firestore progress
- watchdog
- retry / takeover fencing

But if the product's default request can be simplified to something like:

- deterministic enrichment
- one analyst pass
- optional short summarization

then the execution model can simplify too. Right now execution complexity is downstream of pipeline complexity.

## Symptom vs cause map

| Symptom                                    | Current patch                                                 | Likely cause                                                        | Better simplification                                                                       |
| ------------------------------------------ | ------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `MALFORMED_FUNCTION_CALL` in late stages   | layered fallback replies in agent + worker                    | too much context plus too many tools plus code execution at the end | remove code execution from default path, remove gap stage from default path, shrink context |
| specialists overlap or behave unexpectedly | more detailed prompt rules and domain boundaries              | specialists still receive hidden shared transcript                  | set `include_contents='none'` for non-router agents and rely on explicit state only         |
| wrong review conclusions                   | gap research or synthesis compensates for bad review evidence | weak TripAdvisor entity resolution accepted as canonical            | fail closed on low confidence or drop TripAdvisor from default path                         |
| long-running transport complexity          | queue, worker, recovery, watchdog                             | default product path is too deep and slow                           | separate standard path from explicit deep-research path                                     |
| large prompts and slow synthesis           | preserve-depth instructions plus fallback stitching           | markdown-heavy state and source-append workaround                   | use structured outputs and direct metadata extraction                                       |

## Recommended target architecture

### Default mode: standard research

This should become the everyday product path.

Flow:

1. Deterministic pre-processing in code
   - validate place / area
   - fetch Google Places context
   - fetch a small, deterministic review summary if available
   - build a compact structured input object
2. One `research_agent`
   - tool access: `google_search`, `fetch_web_content`
   - `include_contents='none'`
   - structured output schema
   - no sub-agents
3. Optional lightweight formatter
   - no code execution
   - no new research

Properties:

- no router LLM on the happy path
- no specialist pool
- no gap researcher
- no review-specific agent
- no chart generation during final synthesis
- much easier to understand end to end

### Deep mode: explicit heavy research

Keep a background async workflow, but make it opt-in:

- "deep report"
- "full competitor benchmark"
- "full market scan"
- "background research"

This is where a multi-stage ADK workflow can still make sense.

The important change is product shape:

- deep mode becomes a deliberate escalation
- standard mode stops paying the operational and cognitive tax of deep mode

## Concrete simplifications

### Immediate cuts

1. Replace router LLM with deterministic routing in app code.
   - Keep only one ambiguity fallback question.
2. Set `include_contents='none'` on all non-router agents immediately.
   - `context_enricher`
   - `research_orchestrator`
   - specialists
   - `gap_researcher`
   - `synthesizer`
3. Remove `gap_researcher` from the default path.
   - Run only in explicit deep mode.
4. Disable synthesizer code execution by default.
   - Generate charts only from structured numeric outputs in a separate deterministic step, or skip until needed.
5. Make TripAdvisor matching fail closed.
   - If `match_confidence != 'high'`, return an error, not a venue.
6. Remove `_append_sources()` after verifying grounding metadata is present on all needed events.
   - Stop inflating downstream prompts with markdown source blocks.

### Structural simplifications

1. Collapse `context_enricher` and `research_orchestrator` responsibilities where possible.
   - Places enrichment does not need an LLM.
   - Competitive-set heuristics can be deterministic first, LLM-adjusted only if needed.
2. Replace markdown state with structured state.
   - plan object
   - competitor list
   - review metrics
   - evidence list
   - final answer sections
3. Replace `review_analyst` with a deterministic review-data step plus optional analyst interpretation.
   - tool fetches structured data
   - one general analyst interprets it
4. Reduce domain surface area.
   - keep 3-4 durable angles, not 8-10 quasi-specialists

Suggested core angles for deep mode only:

- market and competitors
- menu and pricing
- guest feedback
- operations and economics

Everything else can be a brief or section, not a permanent agent.

## Suggested phased plan

### Phase 1: stop the hidden coupling

Goal: make the current pipeline less opaque without changing product behavior too much.

- deterministic router
- `include_contents='none'` for non-router agents
- TripAdvisor fail-closed
- remove `_append_sources` if direct grounding extraction is sufficient

Expected result:

- easier debugging
- smaller prompts
- fewer "why did this agent know that?" surprises

### Phase 2: shrink the default product path

Goal: introduce a real standard mode.

- deterministic enrichment in code
- one `research_agent`
- structured output
- no gap stage
- no chart code execution

Expected result:

- lower latency
- less prompt architecture
- easier product iteration

### Phase 3: keep deep research, but behind an explicit boundary

Goal: preserve the ambitious workflow without making it the everyday system.

- async worker remains for deep mode
- specialist fan-out remains only for explicit heavy workflows
- standard mode can stay synchronous or use a much thinner async path

## What should stay

These pieces are earning their keep, or at least are directionally correct:

- background worker plus durable progress store if deep mode remains
- Places API integration
- ownership fencing in worker writes
- Firestore read-only browser model
- trace logging and eval harnesses

## Bottom line

The main problem is not "ADK" in the abstract. The main problem is using a deep-research workflow as the default product path before the product has earned that complexity.

The fastest path to a simpler system is:

1. make hidden context explicit
2. remove the gap and chart stages from default execution
3. stop trusting weak entity matching
4. collapse default research to one analyst
5. reserve the current heavy pipeline for explicit deep-research mode

That removes causes rather than adding the next recovery layer.
