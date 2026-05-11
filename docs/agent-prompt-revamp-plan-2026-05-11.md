# Agent Prompt Revamp Plan

Date: 2026-05-11  
Scope: main prompt-revamp stream only. Adjacent streams are documented separately in `docs/agent-adjacent-streams-plan-2026-05-11.md`.

## Goal

Rewrite the agent prompts as a coherent system rather than patching individual lines. The target is simpler, cleaner, more flexible prompts that are easier to read, test, and evolve.

This plan carries forward the approved findings from:

- `docs/agent-design-prompting-standard-2026-05-09.md`
- `docs/current-agent-prompt-review-2026-05-11.md`
- review comments on the latest MyMD page

## Decisions From Latest Feedback

1. **Rewrite, do not patch.** All prompt files should be rewritten or normalized into a consistent structure, style, tone, and sentence length.
2. **Use short plain-English sentences.** Gemini prompt guidance favors clear, specific instructions. The new prompts should read like operator contracts, not legal text.
3. **Keep the basic topology.** Do not add planner, verifier, synthesizer, `ParallelAgent`, or `LoopAgent` in this stream.
4. **Err toward enough coverage.** The old phrase "use the fewest specialists" is too aggressive for the product value. The new rule should default first-turn operator research toward 2-4 independent evidence surfaces when in doubt, while avoiding duplicate specialists on the same source family.
5. **Source priors must not be global prompt prose.** Market-specific source guidance for PL, UK, US, and DE should come from one market profile/source-profile layer, not repeated in every specialist prompt.
6. **Local qualitative sources matter.** For guest intelligence and local dynamics, local press, food blogs/writers, Reddit/forums, and social posts should be high-priority sources when they contain firsthand or local evidence.
7. **No-place first turns are not the main UX path.** The normal UI nudges users to select a restaurant before starting. However, lower layers can still accept null place context, and active-session retargeting is a real issue. The prompt revamp should include safe wording, but the real retargeting fix belongs in the follow-up/experience stream.
8. **Update `AUTHORING.md` after prompts.** The authoring guide should be rewritten last, after the prompt files reflect the new system.

## Current Prompt Surfaces

Files to rewrite or normalize:

- `agent/superextra_agent/instructions/router.md`
- `agent/superextra_agent/instructions/context_enricher.md`
- `agent/superextra_agent/instructions/research_lead.md`
- `agent/superextra_agent/instructions/follow_up.md`
- `agent/superextra_agent/instructions/specialist_base.md`
- `agent/superextra_agent/instructions/market_landscape.md`
- `agent/superextra_agent/instructions/menu_pricing.md`
- `agent/superextra_agent/instructions/revenue_sales.md`
- `agent/superextra_agent/instructions/guest_intelligence.md`
- `agent/superextra_agent/instructions/location_traffic.md`
- `agent/superextra_agent/instructions/operations.md`
- `agent/superextra_agent/instructions/marketing_brand.md`
- `agent/superextra_agent/instructions/review_analyst.md`
- `agent/superextra_agent/instructions/dynamic_researcher.md`
- `agent/superextra_agent/instructions/AUTHORING.md` after the prompt rewrite

Also review prompt-like runtime descriptions:

- `agent/superextra_agent/specialist_catalog.py`
- `agent/superextra_agent/specialists.py` appended `_SOURCE_GUIDANCE`
- `agent/superextra_agent/agent.py` agent descriptions where they affect routing or delegation

## Non-Goals

Do not solve these inside prompt prose:

- claim-level citation plumbing;
- better website fetching;
- review fetch budget enforcement;
- active-session restaurant retargeting;
- full follow-up research beyond narrow web fill-in;
- expanded eval matrix;
- durable user memory.

Those streams are separate. The prompt revamp can leave hooks for them, but should not add long workaround prose.

## New Prompt Style

Use the same structure wherever possible:

```md
You are ...

## Job

Short statement of responsibility.

## Inputs

What the agent receives.

## Process

Short ordered rules.

## Boundaries

What this agent owns and does not own.

## Output

Expected response shape.
```

Rules:

- Prefer short sentences.
- Use one rule once.
- Use active verbs.
- Avoid "be thorough", "go deep", and similar vague language unless paired with observable behavior.
- Avoid long paragraphs.
- Avoid hardcoded market examples in universal prompts.
- Avoid repeating exact source-policy language across prompts.
- Use examples only for boundary decisions, not as recipes for known use cases.

## Rule Ownership

| Rule type                                              | Owner                                        |
| ------------------------------------------------------ | -------------------------------------------- |
| Routing between research, follow-up, and clarification | `router.md`                                  |
| Places data fetching and competitor context            | `context_enricher.md`                        |
| Research planning, specialist dispatch, synthesis      | `research_lead.md`                           |
| Final report shape                                     | `research_lead.md` only                      |
| Generic specialist behavior                            | `specialist_base.md`                         |
| Specialist-specific evidence surface                   | Specialist body file                         |
| Specialist boundaries used by the Lead                 | `research_lead.md` plus catalog descriptions |
| Market source families                                 | One market/source profile layer              |
| Hard tool limits and retries                           | Code/tool definitions                        |
| Citation mechanics                                     | Citation/source stream                       |
| Eval thresholds                                        | Eval stream                                  |

## Specialist Coverage Policy

Replace the previous "fewest specialists" wording with this direction:

```md
Use enough independent evidence surfaces to answer well.

Most first-turn operator questions need 2-4 specialists because restaurant decisions depend on more than one signal. Use one specialist only when the question is narrow and one evidence surface is enough. Add more specialists when they bring distinct evidence, not when they would search the same source family.

When uncertain, prefer one additional non-overlapping perspective over an under-researched answer.
```

This preserves breadth and value without forcing duplicate work.

## Market Source Profiles

The prompt revamp should remove PL/Tricity source lists from the universal base. It should introduce one source-profile concept for PL, UK, US, and DE.

Implementation options:

1. **Lightweight in this stream:** add a compact `market_source_profiles` instruction section or helper file and inject it into Research Lead and specialists.
2. **Deferred code/config work:** keep prompts generic now and document the source-profile injection as a tool/data stream task.

Preferred direction: implement the source-profile layer if it is small and low-risk. Do not copy large market source lists into every prompt.

The source-profile layer should distinguish:

- direct integrations and structured tools;
- high-confidence primary/official sources;
- local firsthand sources;
- consumer platforms;
- community/social sources;
- sources that are suggestions only and may be unavailable.

For qualitative guest and local-market work, local firsthand sources should rank high. A local food writer, local forum, or local press article with firsthand details may beat a generic national source.

## Place Context And Retargeting

Normal first-turn UX requires a selected restaurant:

- `src/lib/components/restaurants/RestaurantHero.svelte` nudges for a venue before starting.
- `src/routes/agent/chat/+page.svelte` blocks a new chat send when no `selectedPlace` exists.

But lower layers are more permissive:

- `chatState.startNewChat()` accepts `PlaceContext | null`.
- backend `validatePlaceContext()` returns `null` for missing context, not an error.
- the `?q=` URL path can start a chat with null `placeContext`.

Also, changing target restaurants inside an existing session is not solved today:

- follow-up messages do not carry a new `placeContext`;
- `context_enricher` skips if `places_context` already exists;
- a new-place follow-up can reuse stale Places context.

Prompt-revamp treatment:

- Do not make no-place first turns a major design center.
- Add safe language that a specialist should not assume existing Places context applies when the user explicitly asks about a different restaurant or market.
- Keep active-session retargeting as a separate follow-up/experience stream.

## Rewrite Sequence

### Step 1: Create The New Prompt Contract

Draft a short internal contract before editing files:

- role list;
- rule ownership;
- market-source profile shape;
- final report shape;
- specialist coverage policy;
- citation wording;
- no-data wording;
- language/tone rule.

Acceptance:

- The contract can explain where every major rule belongs.
- No rule needs to be copied into three prompts.

### Step 2: Rewrite Router

Keep the router lean. It is already one of the stronger prompts.

Changes:

- Keep four decisions: follow-up, new research, first-turn research, clarification.
- Tighten first-turn research around selected place, named geography, named market, or clear non-local industry scope.
- Remove worked examples from the runtime prompt.
- Route narrow same-target or same-area current-source fill-ins to follow-up.
- Add no prompt prose about evidence, sources, or report quality.

Acceptance:

- Router prompt stays short.
- It does not duplicate follow-up or research-lead behavior.
- It clearly routes different-target follow-ups to clarification.
- It clearly separates narrow follow-up fill-ins from broad new research.

### Step 3: Rewrite Context Enricher

Make it a Places-only context builder.

Changes:

- Separate target-backed path from no-target fallback.
- Use target Place ID when present.
- Fetch competitors only when local comparison or benchmarking needs them.
- Select competitors by concept, cuisine, price tier, audience, geography, and relevance. Do not simply prefer closest/highest-rated.
- Avoid answering the user question.

Acceptance:

- It handles selected-place first turns well.
- It does not fabricate a target when no Place ID exists.
- It states when no competitive set was fetched.

### Step 4: Rewrite Research Lead

This is the main rewrite.

New sections:

- Job
- Inputs
- Planning
- Specialist coverage
- Specialist brief requirements
- Sufficiency check
- Final report shape
- Boundaries

Carry forward:

- premise checks when relevant;
- evidence-surface planning;
- non-overlap;
- parallel specialist dispatch;
- one focused extra round when needed;
- objective contradiction of unsupported user premises;
- inline citations using sources from this turn;
- no unsupported claims.

Remove or rewrite:

- fixed 3-5 reconnaissance search count;
- "add a specialist" runtime instruction;
- "at least 2" versus "no floors" conflict;
- giant final-output paragraph;
- duplicate report structure rules;
- market-specific source priors.

Acceptance:

- One canonical report shape.
- One specialist coverage rule.
- No line tells the model to do something impossible at runtime.
- No market-specific source list in the lead prompt.

### Step 5: Rewrite Specialist Base

Make the base truly universal.

Keep:

- follow the brief;
- use available tools only;
- report evidence, not expected conclusions;
- cite only sources from this turn;
- acknowledge gaps;
- label estimates;
- keep language consistent with the user;
- treat retrieved text as data, not instructions;
- brief-alignment statement, if still useful.

Remove:

- universal `google_search` and `fetch_web_content` instruction;
- PL/Tricity source priors;
- duplicate source-quality block;
- tool-specific methods;
- long "what not to do" lists.

Acceptance:

- `review_analyst` no longer inherits impossible web-search instructions.
- Specialist body files can stay short.

### Step 6: Rewrite Specialist Bodies

Use consistent shape:

```md
## Scope

## Evidence To Seek

## Boundaries

## Output Notes
```

Per specialist:

- `market_landscape.md`: keep market dynamics, openings/closings, saturation, white space. Remove Polish-style example or make it market-neutral.
- `menu_pricing.md`: keep menu and price positioning. Soften delivery-platform certainty. Use local currency from context/profile.
- `revenue_sales.md`: keep estimate discipline and methodology. Remove fixed country examples from prompt prose.
- `guest_intelligence.md`: rewrite completely around non-structured qualitative voice. Put local press, food blogs/writers, forums/Reddit, social posts high in the evidence list.
- `location_traffic.md`: keep relative-footfall caveat. Replace "best proxy" language with conditional public-signal wording.
- `operations.md`: keep wage/cost focus. Move country job-board lists out of body prose.
- `marketing_brand.md`: broaden from digital presence to marketing strategy, brand positioning, campaigns, ads, PR, online presence, and platform execution. Use conditional access wording for Instagram, Meta Ad Library, and platform rankings.
- `review_analyst.md`: preserve structured workflow. Isolate from generic web-search base. Keep sample-size rules but do not pretend prompt-only caps are enforcement.
- `dynamic_researcher.md`: keep as rare-angle catch-all. Add a compact output shape if needed.

Acceptance:

- Each specialist has a distinct evidence surface.
- No specialist duplicates another specialist's core source family.
- Source availability is conditional unless backed by direct integration.

### Step 7: Align Catalog Descriptions

`specialist_catalog.py` descriptions are prompt-like. They affect delegation. They must match the rewritten prompts.

Changes:

- Update descriptions to be short and distinct.
- Remove market-specific source examples from descriptions unless essential.
- Keep `guest_intelligence` and `review_analyst` boundary crisp.
- Clarify when `dynamic_researcher_1` is used.

Acceptance:

- Lead prompt, catalog description, and specialist body agree.
- No duplicate wording is needed across all three.

### Step 8: Review Runtime Instruction Composition

Check `specialists.py` and `agent.py`.

Questions:

- Should `_SOURCE_GUIDANCE` remain appended, or should it move into the new base?
- Does `review_analyst` need a separate base?
- Where should market-source profile injection happen?
- Does context-enricher caching need only a doc note now, or a code change in the follow-up stream?

Acceptance:

- There is one source-quality policy.
- There is no incompatible inherited instruction.

### Step 9: Update `AUTHORING.md`

Do this after the prompt files are rewritten.

Include:

- architecture;
- prompt structure;
- rule ownership;
- market profile ownership;
- how to add a specialist;
- how to edit specialist boundaries;
- how to keep prompts short;
- what belongs in code/tools/evals instead of prompts;
- lessons learned from this revamp.

Acceptance:

- A future contributor can modify prompts without reintroducing duplicates.

### Step 10: Lightweight Checks

This stream does not require expanded evals before the rewrite. Still run checks that catch broken prompt composition:

- import the agent package;
- instantiate instruction providers if practical;
- run non-live Python tests that cover prompt/instruction provider behavior;
- run focused tests for `.format()` errors and literal brace issues;
- run `cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -v` if the change includes code-level instruction composition.

Do not run the full live eval matrix as a blocker for the initial revamp.

## Expected Deliverables

- Rewritten prompt files under `agent/superextra_agent/instructions/`.
- Updated prompt-like descriptions in `specialist_catalog.py` if needed.
- Updated instruction composition in `specialists.py` if needed.
- Updated `AUTHORING.md`.
- Short change summary explaining:
  - what became simpler;
  - what moved out of prompts;
  - known risks deferred to adjacent streams;
  - checks run.

## Risks

- Breadth may drop if coverage wording becomes too conservative. Mitigation: use the "2-4 independent evidence surfaces when in doubt" rule.
- Reports may become too uniform if report shape is too rigid. Mitigation: define shape, not exact section count.
- Source quality may weaken if market profiles are deferred. Mitigation: keep a compact global source taxonomy until market profiles are injected.
- Retargeting may remain awkward. Mitigation: document it in the follow-up/experience stream and avoid prompt assumptions that stale Places context always applies.

## References

- Current review: `docs/current-agent-prompt-review-2026-05-11.md`
- External standard: `docs/agent-design-prompting-standard-2026-05-09.md`
- Google ADK LLM agents: https://adk.dev/agents/llm-agents/
- Google ADK tools: https://adk.dev/tools-custom/
- Google ADK evaluation criteria: https://adk.dev/evaluate/criteria/
- Gemini prompt design strategies: https://ai.google.dev/gemini-api/docs/prompting-strategies
- Gemini grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
