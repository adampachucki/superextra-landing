# Writing Agent Instructions

Read this before editing any file in this directory.

## Architecture

```
Router -> research_pipeline
           |-- Context Enricher
           `-- Research Lead
               `-- Specialists through AgentTool

Router -> follow_up
```

The router routes. The context enricher builds Google Places context. The Research Lead plans, briefs specialists, checks sufficiency, and writes the final report. Specialists answer one evidence surface from the Lead's brief. Follow-up answers from the existing report, specialist notes, Places context, and limited web fill-in for narrow same-target questions.

## State Keys

- `places_context`: Google Places context from the enricher.
- `_target_place_id`, `_target_lat`, `_target_lng`: target metadata written by Places tools.
- Specialist result keys such as `market_result`, `pricing_result`, and `review_result`: specialist outputs.
- `final_report`: final Research Lead report.
- `final_report_followup`: final follow-up answer, separate from the original report.

## Rule Ownership

| Rule type | Owner |
| --- | --- |
| Routing and clarification | `router.md` |
| Places lookup and competitor context | `context_enricher.md` |
| Research planning, specialist dispatch, task-specific research depth, sufficiency, and final report shape | `research_lead.md` |
| Universal specialist behavior and substantial evidence report shape | `specialist_base.md` |
| Market source families | `market_source_profiles.md` |
| Specialist-specific source surface and boundaries | Specialist body files |
| Hard tool limits, retries, errors, and caps | Tool code |
| Citation plumbing and source validation | Product/source pipeline |
| Eval thresholds and pass/fail criteria | Evals |

Put each rule in one place. If the same instruction seems needed in three prompts, move it to the shared owner or delete it.

## Prompt Style

- Use short, plain sentences.
- Prefer stable sections: `Job`, `Inputs`, `Process`, `Boundaries`, `Output`.
- Avoid recipes for known eval cases.
- Avoid "be thorough" without observable behavior.
- Avoid hardcoded market examples in universal prompts.
- Avoid broad claims about source availability. Say "when accessible" unless a direct tool guarantees access.
- Keep examples for boundary decisions only.

## Specialist Template System

Specialist instructions use two prompt layers:

1. `specialist_base.md`: universal specialist contract and substantial evidence report shape.
2. `{specialist_name}.md`: domain-specific scope, evidence, boundaries, and narrow output notes.

`specialists.py` composes the base and body. It injects:

- `{places_context}`;
- `{target_place_id}` for `review_analyst`;
- `{role_title}`;
- `{specialist_body}`.

Do not append extra shared source policy in code. `market_source_profiles.md` is injected into the Research Lead. The Lead passes relevant source expectations to specialists in each brief.

## Specialist Body Rules

Each body should answer four questions:

1. What evidence surface does this specialist own?
2. What source families should it seek?
3. What neighboring work should it avoid?
4. What output details help the Lead synthesize?

Do not define generic "depth" rules in body files. The Lead frames depth for the specific task in the brief. Do not repeat the universal evidence-report shape from `specialist_base.md`.

Do not paste generic source policy into body files. Do not repeat another specialist's scope. Do not include `places_context` in body files; the base already injects it.

## Research Lead Rules

The Lead owns:

- question-type handling and premise checks when relevant;
- evidence-surface planning;
- specialist selection;
- non-overlap;
- task-specific research depth in specialist briefs;
- specialist brief quality;
- market/source guidance for each specialist brief;
- a focused extra round if evidence is weak;
- final report shape.

The Lead should usually use multiple specialists for first-turn operator research. 2-4 is common. Add another specialist when it gives a useful perspective, test, or evidence surface.

The Lead should ask specialists for the causes, mechanisms, counter-signals, and evidence tests that matter for the specific task. Do not hardcode domain-specific depth checklists in specialist body files unless a tool or domain boundary requires it.

## Market Source Profiles

`market_source_profiles.md` is a compact source guide for PL, UK, US, and DE plus a general source order.

These profiles are starting points, not checklists. They should name source families and examples that help search. They must not imply that every source exists, is accessible, or was checked.

When adding a market, update this file instead of putting country-specific lists into the Lead or specialist bodies.

## Code Versus Prompt

Use prompts for:

- role and responsibility;
- when to use a source family;
- how to state uncertainty;
- specialist evidence report shape;
- task-specific research depth;
- final report shape;
- specialist boundaries.

Use code/tools/evals for:

- hard caps and budgets;
- retries, timeouts, and error types;
- auth and source access;
- structured source metadata;
- citation validation;
- eval scoring and thresholds.

Do not solve tool problems with longer prompt prose.

## Template Variables

Runtime templates use Python `str.format()`.

Files with runtime variables:

- `research_lead.md`: `{places_context}`, `{market_source_profiles}`.
- `follow_up.md`: `{final_report}`, `{specialist_reports}`, `{places_context}`.
- `specialist_base.md`: `{role_title}`, `{places_context}`, `{specialist_body}`.
- `review_analyst.md`: `{target_place_id}`.

Never add literal curly braces to runtime-formatted prompt files. Escape them as doubled braces: `{{` and `}}`.

Chart JSON in `research_lead.md` must keep doubled braces so `.format()` leaves valid JSON.

## Modification Checklist

### Editing A Prompt

1. Identify the rule owner.
2. Delete duplicates before adding new wording.
3. Keep wording short and testable.
4. Check for literal braces.
5. Run instruction provider tests.

### Adding A Specialist

1. Add a short specialist body file.
2. Add one catalog entry in `specialist_catalog.py`.
3. Add a tool override in `specialists.py` only if default tools are wrong.
4. Add boundary wording to `research_lead.md` only if the new scope overlaps with an existing specialist.

### Adding A Template Variable

1. Add the placeholder to the prompt.
2. Update the instruction provider.
3. Add or update tests for successful formatting.
4. Ensure an upstream agent or tool writes the state key.

## Known Deferred Streams

Keep these out of the prompt revamp unless the stream is explicitly opened:

- claim-level citation plumbing;
- website fetching improvements;
- review fetch budget enforcement;
- active-session target changes;
- full follow-up research mode beyond narrow web fill-in;
- expanded evals;
- durable memory.
