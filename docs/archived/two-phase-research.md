# Two-Phase Research with Gap-Filling

## Problem

Dynamic researchers currently run alongside core specialists in a single ParallelAgent, blind to what the core specialists find. They can't fill gaps because they don't know what gaps exist. The orchestrator assigns all briefs at once before any specialist runs.

In the Wen Cheng comparison (April 2026), the dynamic researcher produced the highest-value unique contribution (Reddit insider sentiment, "Instagram fast food" label, Exberliner "gamble" review) — but it was working blind. Meanwhile, nobody caught the Chungking Noodles closing because market_landscape was skipped entirely.

## Current pipeline

```
Router → SequentialAgent([
    context_enricher      → state["places_context"]
    research_orchestrator → state["specialist_briefs"] + state["research_plan"]
    specialist_pool       → ParallelAgent(all 9 specialists)
    synthesizer           → state["final_report"]
])
```

The orchestrator writes all briefs to state via `set_specialist_briefs`, then the ParallelAgent runs all 9 specialists concurrently. Unassigned specialists skip via `before_agent_callback`.

## Proposed pipeline

```
Router → SequentialAgent([
    context_enricher,
    research_orchestrator,    # assigns briefs to CORE specialists only
    core_pool,                # ParallelAgent(7 core specialists)
    gap_analyzer,             # reads Phase 1 results, assigns dynamic researcher briefs
    dynamic_pool,             # ParallelAgent(2 dynamic researchers)
    synthesizer
])
```

## What changes

### specialists.py

Export two lists instead of one:

```python
CORE_SPECIALISTS = [
    market_landscape, menu_pricing, revenue_sales,
    guest_intelligence, location_traffic, operations, marketing_digital,
]
DYNAMIC_SPECIALISTS = [dynamic_researcher_1, dynamic_researcher_2]
```

### agent.py

Split `specialist_pool` into `core_pool` + `dynamic_pool`, add `gap_analyzer` between them:

```python
core_pool = ParallelAgent(
    name="core_pool",
    sub_agents=CORE_SPECIALISTS,
)

gap_analyzer = LlmAgent(
    name="gap_analyzer",
    model=MODEL_GEMINI,
    instruction=_gap_analyzer_instruction,  # reads state, identifies gaps
    tools=[set_specialist_briefs],          # same tool, overwrites state
    output_key="gap_analysis",
    generate_content_config=THINKING_CONFIG,
)

dynamic_pool = ParallelAgent(
    name="dynamic_pool",
    sub_agents=DYNAMIC_SPECIALISTS,
)

research_pipeline = SequentialAgent(
    sub_agents=[
        _make_enricher(), research_orchestrator,
        core_pool, gap_analyzer, dynamic_pool,
        _make_synthesizer(),
    ],
)
```

### research_orchestrator.md

Add one line: "Do not assign dynamic_researcher_1 or dynamic_researcher_2. A gap analyzer will handle those after core specialists complete."

### New file: instructions/gap_analyzer.md

Instruction template that gets all specialist results injected (same pattern as synthesizer). Asks three questions:

1. **Unfulfilled angles** — What did the orchestrator expect that specialists didn't deliver?
2. **Surprising findings worth deeper investigation** — e.g., "Mr. Noodle Chen's unlimited refills" → investigate their cost model
3. **Contradictions between specialists** — e.g., guest says "overpriced" but pricing shows competitive

If gaps exist, calls `set_specialist_briefs` with targeted briefs for dynamic_researcher_1 and/or dynamic_researcher_2. If nothing meaningful is missing, sets no briefs and dynamic researchers skip.

The synthesizer then receives everything — core results + gap-filling results + gap_analysis — and combines as usual.

## Synthesizer update

Add `gap_analysis` to the `_SYNTHESIZER_KEYS` list so the synthesizer sees the gap analyzer's reasoning alongside specialist findings.

## Expected impact

- Dynamic researchers become informed by Phase 1 results instead of running blind
- Gaps like the Chungking closing (caught by old agent, missed by new) get surfaced
- Contradictions between specialists get targeted investigation
- Surprising findings (e.g., value threats) get deeper follow-up
- If no gaps exist, dynamic researchers skip — no wasted time

## Validation

Build it (small change), run the same Wen Cheng sentiment question, compare three outputs via the debug endpoint:

1. Old agent (all specialists self-triage, no orchestrator)
2. Current new agent (orchestrator + single parallel pool)
3. Two-phase agent (orchestrator + core pool + gap analyzer + dynamic pool)

Key metric: does the two-phase output contain insights that neither the old nor current agent found?
