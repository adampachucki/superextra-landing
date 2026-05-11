# Current Agent Setup and Prompt Review

Date: 2026-05-11  
Status: full re-review after comments on the external standard and first review.  
Scope: current Superextra agent code, prompt files, tool code, source plumbing, follow-up path, evals, tests, and relevant docs.  
Purpose: decision document for the upcoming prompt revamp. This report reviews the current setup; it does not implement prompt changes.

## Executive Verdict

The current agent topology is usable, but the prompt layer should be treated as an ad hoc system that needs a full cleanup, not a few local patches. The earlier review was too preservation-biased. A fairer assessment is:

- The architecture is not fundamentally wrong: Router -> Context Enricher -> Research Lead -> Specialist AgentTools -> final report is a reasonable shape for this product.
- The prompt prose is uneven: some parts are lean, some are over-prescriptive, some are under-specified, and several instructions duplicate or conflict.
- The prompt system is harder to maintain than it should be because shared rules, market-specific source priors, source-quality guidance, tool-use rules, visible-output rules, and role boundaries are spread across too many places.
- The next prompt task should be a full prompt revamp aimed at cleaner, leaner, more scalable instructions. The goal should be fewer repeated rules, fewer use-case recipes, clearer boundaries, and a smaller surface area for future changes.
- Citations, web fetching, review-fetch depth, follow-up experience, and eval expansion are important but should be separate streams. The prompt revamp should not try to solve tool or product mechanics with more prose.

This verdict is based on the current files, not on the setup's history. The observed issues are enough to justify a full rewrite of prompt prose while preserving the parts that are already strong.

## External Standard Applied

The review uses the external standard in `docs/agent-design-prompting-standard-2026-05-09.md` plus fresh checks against current official Google and Gemini documentation.

The most relevant external facts are:

- ADK `LlmAgent` behavior is non-deterministic and shaped primarily by identity, descriptions, instructions, tools, and state. Instructions should clearly describe task, constraints, tool use, and output format.[^adk-llm]
- ADK workflow agents are deterministic orchestration constructs. `SequentialAgent`, `ParallelAgent`, and `LoopAgent` should be used when deterministic control flow is needed, not as a default substitute for clearer prompts.[^adk-workflow][^adk-parallel][^adk-loop]
- ADK tools are developer-defined capabilities. Tool names, docstrings, schemas, return values, callbacks, and code should carry behavior that can be enforced; prompt prose should guide when and why to use them.[^adk-tools][^adk-callbacks]
- ADK sessions and state are for the current conversation; long-term memory is a separate concept. That supports using session state/history now and deferring durable user memory.[^adk-sessions][^adk-state]
- ADK evaluation supports both final response quality and tool trajectory checks. That does not block a fast prompt revamp, but it means production confidence should eventually come from evals, not taste.[^adk-eval]
- Gemini prompt docs recommend clear, specific instructions, constraints, response format guidance, examples where useful, and prompt decomposition for complex tasks. They also warn that too many examples can make responses overfit to examples.[^gemini-prompt]
- Gemini Search grounding is explicitly designed to improve factuality and provide citation metadata. Prompt text can request citations, but robust citation UX needs source metadata and product plumbing.[^gemini-search]
- Gemini function calling connects models to external tools and APIs, but the application executes the functions and returns results. That reinforces the prompt/code boundary: enforce hard tool policy in code, not just text.[^gemini-function]

## Desired Future State

The target prompt system should be:

- **Scalable:** works across PL, UK, US, DE, and later markets without rewriting the core prompt.
- **Lean:** one rule appears once, in the layer that owns it.
- **Structured:** prompts have short stable sections: role, inputs, process, boundaries, output contract.
- **Flexible:** agents reason from evidence surfaces, not brittle known query recipes.
- **Reliable:** enough guidance to produce grounded work, but not so much that the model is boxed into stale examples.
- **Developable:** future changes are easy because source policy, market config, role boundaries, report shape, and tool constraints are not mixed together.

The current setup does not meet that standard yet.

## Severity Map

| Area                                                                            | Severity | Evidence                                                                                                                                                                                                                                                          | Review judgment                                                                     |
| ------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Specialist shared base leaks web-search instructions into `review_analyst`      | High     | Base tells specialists to use `google_search` and `fetch_web_content`; `review_analyst` explicitly has no `google_search` and its tool override only includes review tools.[^base-web][^review-no-search][^review-tools]                                          | This is a real prompt-composition defect, not a taste issue.                        |
| `guest_intelligence` conflicts with `review_analyst`                            | High     | Guest prompt names Google and TripAdvisor as platforms to gather, then says not to duplicate the structured Google/TripAdvisor specialist.[^guest-conflict][^catalog-guest-review]                                                                                | This can cause duplicate work and confused synthesis.                               |
| `research_lead` is overloaded and internally inconsistent                       | High     | It mandates 3-5 reconnaissance searches, asks for at least 2 specialists, later says no floors, and has a dense final-report paragraph plus a separate report structure block.[^lead-recon][^lead-dispatch][^lead-floors][^lead-final]                            | Rewrite the prompt, do not patch line by line.                                      |
| Source priors are hardcoded to PL/Tricity in the shared base                    | High     | Base prompt names Tricity/Polish domains and communities; current eval venues are also Polish/Tricity-heavy.[^base-priors][^eval-venues]                                                                                                                          | This is market-specific config masquerading as universal guidance.                  |
| Claim-level citation expectations exceed current plumbing                       | Medium   | Grounding chunks and provider pills become a source drawer; UI renders source chips, not verified claim-source mappings.[^grounding-extract][^sources-merge][^source-ui]                                                                                          | Add in-text citation prompt rules, but treat source mechanics as a separate stream. |
| Follow-up experience needs a fuller product stream                              | Medium   | The prompt revamp now gives `follow_up` prior report, specialist notes, Places context, and narrow web fill-in, but active-session retargeting and full follow-up research modes remain separate product work.[^followup-prompt][^followup-code][^followup-tests] | Keep the narrow fill-in path; handle full follow-up experience separately.          |
| Context enricher assumes a target place, but product/code can accept null place | Medium   | Frontend and backend accept nullable `placeContext`; context prefix is only injected when first message has place context; router allows first-turn city/general trend research.[^nullable-place][^context-injection][^router-first]                              | Add a no-target branch or code bypass. Do not rely on "usually selected place."     |
| Evals are too narrow for market scalability                                     | Medium   | Eval venue set is local; routing subset encodes expected specialist sets, including known use cases.[^eval-venues][^eval-routing]                                                                                                                                 | Evals are a later stream, but prompt review should not optimize for these examples. |

## Overall Agent Setup

### Keep the Basic Topology

The broad architecture should stay for the prompt revamp:

- The root `router` chooses `research_pipeline`, `follow_up`, or clarification.[^agent-router]
- `research_pipeline` is a `SequentialAgent` that runs context enrichment before research planning.[^agent-pipeline]
- `research_lead` owns planning, specialist dispatch, sufficiency checking, and final synthesis.[^agent-lead]
- Specialists are exposed through `AgentTool`, and the specialist catalog centralizes labels, descriptions, output keys, and instruction mapping.[^agent-tools][^catalog]
- `review_analyst` has direct structured review tools; other specialists default to search and page-fetch tools.[^review-tools][^default-tools]

This is not an argument that the current prompts are good. It means the cleanup should start by simplifying the existing roles, not by adding a planner, verifier, synthesizer, or extra nested agent layer.

### Do Not Add Workflow Layers Yet

ADK provides `ParallelAgent` and `LoopAgent`, but the current evidence does not justify adding them now. `ParallelAgent` is useful for independent branches that can run concurrently, but its docs warn that branches do not automatically share conversation history or state.[^adk-parallel] `LoopAgent` is useful for iterative refinement, but it requires an explicit termination mechanism or max iteration limit.[^adk-loop]

For Superextra, those patterns may become useful later:

- A verifier loop could draft, critique support, revise, and stop when evidence is sufficient.
- A parallel workflow could run fixed independent data pulls and then synthesize.

But the current priority is prompt clarity. Adding loops before cleaning up role contracts would increase surface area and debugging cost.

### Agent Boundaries Are Directionally Right, But Prompt Boundaries Drift

The specialist roster is mostly organized by evidence surface rather than by one-off user query:

- `market_landscape`: openings, closings, competitor mapping, saturation, white space.
- `menu_pricing`: menus, price positioning, delivery platforms, promotions.
- `revenue_sales`: revenue estimates, check size, seasonality, channel mix.
- `guest_intelligence`: qualitative customer voice outside structured review APIs.
- `review_analyst`: structured Google Reviews and TripAdvisor analysis.
- `location_traffic`, `operations`, `marketing_brand`: trade area, cost/labor, and marketing/brand presence.
- `dynamic_researcher_1`: non-standard angles and gaps.

The problem is not the idea of specialists. The problem is that boundaries are repeated in the catalog, research lead prompt, specialist base, and specialist body prompts, and those copies are not always aligned.

## Prompt-by-Prompt Review

| Prompt                  | Current verdict                                                                                                              | Revamp direction                                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `AUTHORING.md`          | Useful operational memory, but it codifies current patch history and some over-specific rules.                               | Update after the prompt revamp so it describes the cleaner system, not past accidents.                                               |
| `router.md`             | One of the leanest prompts. Good decision table. Some no-place/general-trend ambiguity remains.                              | Keep the style; tighten first-turn research criteria and avoid adding more examples.                                                 |
| `context_enricher.md`   | Clear for venue-backed starts, brittle when no Place ID exists, and competitor selection is partly hardcoded.                | Add explicit no-target branch; make competitor selection based on relevance, not closest/highest-rated defaults alone.               |
| `research_lead.md`      | The most important and most bloated prompt. Strong ideas, weak structure.                                                    | Rewrite as a compact orchestration contract with one report-shape section and one dispatch policy.                                   |
| `follow_up.md`          | Lean. The revamp adds specialist notes and narrow web fill-in without turning follow-up into a full research agent.          | Keep this narrow path; move retargeting and full follow-up research modes to the follow-up stream.                                   |
| `specialist_base.md`    | Useful shared grounding rules, but too broad, too localized, and incompatible with `review_analyst`.                         | Rewrite as a minimal universal contract; move market priors to config; avoid tool-specific rules unless tool availability is known.  |
| `market_landscape.md`   | Scope is good; example is overly specific and Polish-styled.                                                                 | Keep scope, remove or generalize example, rely on market config.                                                                     |
| `menu_pricing.md`       | Useful scope; overstates delivery platform accessibility and is PLN/platform-specific.                                       | Keep task, soften availability claims, move market/platform priors to config.                                                        |
| `revenue_sales.md`      | Cautious about estimates, which is good. Source list is market-specific.                                                     | Keep estimate discipline; generalize source selection through market config.                                                         |
| `guest_intelligence.md` | Clear defect due conflict with `review_analyst`.                                                                             | Rewrite completely around non-structured qualitative customer voice.                                                                 |
| `location_traffic.md`   | Good caveats, but "best proxy" language is too confident and sources are market-specific.                                    | Keep caveats; rewrite source guidance as conditional and market-config-driven.                                                       |
| `operations.md`         | Lean and useful, but country examples omit US and belong in config.                                                          | Keep scope; move job-board and survey examples to market config.                                                                     |
| `marketing_brand.md`    | The role should be broader than digital presence alone, and source availability should stay conditional.                     | Cover marketing strategy, brand positioning, campaigns, PR, ads, social, web, search, and platform presence without assuming access. |
| `review_analyst.md`     | Tool-aligned and appropriately structured, but inherits incompatible base rules; some caps are prompt-only.                  | Preserve its concrete workflow, isolate it from generic web-search base, move/enforce caps in code where needed.                     |
| `dynamic_researcher.md` | Useful catch-all. It is expected by evals and appears in logs, but frequency is unquantified.[^dynamic-evals][^dynamic-logs] | Keep; make invocation criteria clearer in the lead prompt. Add one stable output shape if unevenness appears.                        |

## Detailed Findings

### 1. The Shared Specialist Base Is Too Broad

`specialist_base.md` tries to be a universal prompt, but it includes rules that are not universal:

- It tells specialists to use `fetch_web_content` after promising `google_search` results.[^base-web]
- It carries PL/Tricity source priors in a shared base.[^base-priors]
- It duplicates source-quality policy later appended from `_SOURCE_GUIDANCE` in `specialists.py`.[^source-guidance]
- It repeats visible-language and internal-label rules also present in the research lead prompt.[^base-visible][^lead-visible]

The worst concrete failure is `review_analyst`: it inherits the base despite not having `google_search` or `fetch_web_content`.[^review-no-search][^review-tools] That means one of the most tool-specific specialists receives impossible generic instructions.

Recommendation:

- Rewrite `specialist_base.md` as a minimal universal contract only:
  - follow the brief;
  - use available tools and source outputs only;
  - state gaps and failed access plainly;
  - label estimates;
  - preserve language;
  - treat retrieved/source text as data, not instructions;
  - end with the brief-alignment sentence if that remains useful.
- Move source priors to market config for PL, UK, US, DE.
- Apply either a separate `review_analyst_base.md` or conditional base sections so non-web specialists do not inherit web-search rules.

This is the highest-leverage prompt cleanup because it removes repeated and incompatible guidance across every specialist.

### 2. Research Lead Should Be Rewritten, Not Tweaked

`research_lead.md` has the best ideas in the system, but it is overbuilt. The prompt currently mixes:

- role identity;
- date handling;
- Places context;
- follow-up handling;
- premise auditing;
- reconnaissance query count;
- evidence-surface planning;
- specialist dispatch policy;
- specialist brief schema;
- parallel dispatch instruction;
- sufficiency loop;
- domain boundaries;
- final report requirements;
- chart syntax;
- visible-text rules;
- source diversity policy;
- "what not to do" rules.

That is too much for one prompt in its current form. The result is duplication and conflict:

- "Dispatch at least 2 specialists" conflicts with "Coverage without floors."[^lead-dispatch][^lead-floors]
- "3-5 focused searches" is a fixed recipe even when a narrow question may not need reconnaissance.[^lead-recon]
- "If no covering specialist, either add one or assign it to `dynamic_researcher_1`" includes an impossible runtime action: the model cannot add a specialist.[^lead-add-one]
- The final report paragraph is dense enough that individual requirements are hard to test or maintain.[^lead-final]
- The "Recommended structure" block is useful in concept but duplicates rules scattered around it.[^lead-structure]

Recommendation:

Rewrite the lead prompt around this structure:

1. **Role:** plan research, brief specialists, test assumptions, synthesize final answer.
2. **Inputs:** user question, date, Places context, prior specialist results if any.
3. **Planning:** identify the decision, user premises, and material evidence surfaces.
4. **Dispatch:** use the fewest specialists that cover independent evidence surfaces. Most first-turn operator questions need two or more evidence surfaces; one is valid for narrow factual work.
5. **Briefs:** include question, target, geography, competitive set, source expectations, boundaries, date, language.
6. **Sufficiency:** one focused extra round when evidence is missing or contradictory; otherwise state limitations.
7. **Report shape:** one canonical output structure with inline citations and evidence labels.
8. **Stop rules:** no unsupported claims, no invented data, no unused-specialist discussion.

Keep the assumption-audit idea. It is concise and product-critical: user premises like "why is this area down?" should be treated as hypotheses, not accepted facts.[^lead-assumptions] But revise it so the Lead can assign specialists to test the premise, rather than implying the Lead can verify it alone.

### 3. Report Structure Should Stay, But Only Once

The previous review suggested removing the report structure block. After the new feedback, the better recommendation is different: keep a report-shape block, but make it the single source of truth for final output.

The current problem is not that structure exists. The problem is that structure, citation rules, evidence-preservation rules, and length rules are split across multiple bullets and one long paragraph.[^lead-final][^lead-structure]

Recommendation:

- Keep a short `Final report shape` section.
- Delete the giant evidence-preservation paragraph and rewrite it as short bullets.
- Remove duplicate rules from other sections once they exist in report shape.
- Avoid a fixed `2-5` section count if the evidence naturally needs one, three, or six sections.

Suggested report contract for the future prompt:

```md
## Final report shape

- Start with the answer, including whether the user's premise is supported.
- Organize by insight, not specialist name.
- Use sections that each carry one decision-relevant finding.
- Cite specific claims inline using sources from this turn only.
- Preserve central names, numbers, dates, quotes, sample sizes, and confidence labels.
- Separate observed facts from estimates and interpretations.
- End with 2-3 useful follow-up questions.
```

This preserves consistency without forcing brittle prose.

### 4. Specialist Dispatch Needs Evidence-Surface Guidance, Not Floors

The current "minimum 2, ideally 3" language was meant to create perspective and avoid single-agent tunnel vision.[^lead-dispatch] That intent is reasonable. The wording is still too rigid.

The desired rule should be:

- First-turn strategic operator questions usually need more than one independent evidence surface.
- Two or three specialists is a common result, not a fixed requirement.
- One specialist is correct for narrow factual or tool-specific questions.
- More specialists are justified only when they add non-overlapping evidence.

This better matches the product goal: variety without pointless calls. It also avoids accidentally optimizing for routing evals that encode expected specialist sets for known examples.[^eval-routing]

### 5. Guest Intelligence Must Be Rewritten

`guest_intelligence.md` is the clearest prompt defect. It says the scope includes Google and TripAdvisor and tells the specialist to gather at minimum Google Reviews plus another platform.[^guest-conflict] But the catalog and research lead say structured Google Reviews and TripAdvisor belong to `review_analyst`.[^catalog-guest-review][^lead-boundaries]

This can cause:

- duplicate specialist work;
- conflicting sample sizes;
- unclear source ownership;
- repeated Google/TripAdvisor findings in the final synthesis;
- harder debugging when review results disagree.

Recommendation:

Rewrite `guest_intelligence.md` around:

- qualitative customer voice outside structured Google/TripAdvisor tools;
- delivery app comments where accessible;
- TheFork/OpenTable/Foursquare/local review sites where relevant by market;
- food blogs, local press, Reddit/forums, social posts;
- recurring themes, guest expectations, language/tourist-local signals;
- explicit no-overlap rule: do not analyze structured Google Reviews or TripAdvisor when `review_analyst` is assigned.

`review_analyst` should remain a sibling specialist, not a subagent of Guest Intelligence. Nesting would hide useful structured-review work behind another agent and make debugging harder. Pair them only when the question needs both structured review quantification and broader qualitative voice.

### 6. Review Analyst Is Mostly Good, But Should Not Inherit Generic Web Guidance

`review_analyst.md` is prescriptive, and much of that prescriptiveness is justified. It uses exact tools, requires Place IDs, verifies TripAdvisor matching, shows sample sizes, and computes structured review breakdowns.[^review-tools-prompt]

The issues are:

- It inherits `specialist_base.md`, which tells it to use unavailable web-search tools.[^base-web][^review-no-search]
- Competitor review depth of `max_reviews=30` is prompt-only, not code-enforced.[^review-competitor-cap]
- Google review default and hard cap are in code: default 50, max 200.[^google-review-cap]
- TripAdvisor default and hard cap are in code: default 5 pages/50 reviews, max 10 pages/100 reviews.[^ta-review-cap]

Recommendation:

- Keep Review Analyst as a direct specialist with structured review tools.
- Give it either a separate base or a conditional base that does not mention web search.
- Keep default sample sizes in the prompt, but enforce any hard product budget in tool code if it matters.
- Add a prompt branch for review-heavy questions: default 50 reviews; fetch deeper only when the user's question is explicitly about sentiment over time, review trajectory, or detailed competitor review analysis.

### 7. Context Enricher Needs a No-Target Branch

User intent may be to start every session from a selected place, but the current product/code can accept no place:

- `startNewChat` accepts `PlaceContext | null`.[^nullable-place]
- backend validation accepts optional `placeContext` and only injects `[Context: ...]` when a first message has a place name.[^context-injection]
- router routes city/general industry questions to `research_pipeline` even without a place.[^router-first]
- eval matrix runs force place context, so tests may underrepresent null-place behavior.[^matrix-context]

`context_enricher.md` currently says always fetch the target restaurant from a `[Context: ...]` prefix.[^enricher-always]

Recommendation:

- Add a no-target branch in prompt or code.
- If no Place ID exists, the enricher should not call Places tools. It should output that no target was provided and that no competitive set was fetched.
- If no-place sessions should be impossible in product, enforce that in UI/backend and simplify router/enricher accordingly.

Do not encode "every run has a target place" as a universal prompt assumption while the code path still permits null.

### 8. Market-Specific Source Priors Should Move Out Of Core Prompts

Current source priors are useful for PL/Tricity, but they do not scale:

- `specialist_base.md` names Tricity sites, Polish forums, Polish bloggers, and Gdynia/Gdansk municipal sources.[^base-priors]
- `menu_pricing.md` names Pyszne.pl, Wolt, Glovo, Uber Eats, Bolt Food and uses PLN examples.[^menu-pricing]
- `operations.md` lists PL, Germany, and UK job/salary sources but not US, even though market focus should include US.[^ops-sources]
- `location_traffic.md` lists PL, Germany, and UK demographic sources.[^location-sources]
- `market_landscape.md` uses a specific Polish-style example for Mokotow and Q4 2025.[^market-example]

Recommendation:

- Create market config for `PL`, `UK`, `US`, `DE`.
- Prompt core should say "use market config and local-language sources."
- Market config should hold platform names, source families, official statistics bodies, job boards, review platforms, delivery platforms, local press patterns, and currency conventions.
- The prompt should distinguish direct integrations from suggested public sources. Certainty belongs only where the system has a direct tool/integration and structured output.

This also improves eval design later: the same prompts can be tested against multiple markets without rewriting prompt prose.

### 9. Several Prompts Overstate Source Availability

Some prompts imply public pages are available and parseable:

- `menu_pricing.md` says delivery platform menus are publicly visible and the single best source for live structured menu/price data.[^menu-pricing]
- `marketing_brand.md` should treat Instagram, Meta Ad Library, and platform surfaces as useful when accessible, not guaranteed inputs.[^marketing-sources]
- `location_traffic.md` says Google Popular Times is the best publicly available proxy for foot traffic.[^location-popular]

The product may often need these sources, but pages can be blocked, incomplete, dynamic, region-specific, or inaccessible to the current tools. Prompts should not imply certainty unless there is a direct integration.

Recommendation:

- Replace absolute claims with conditional source priorities:
  - "When accessible, delivery platform menus are strong live menu/price evidence."
  - "If social profiles are public and current, use them for activity signals."
  - "Treat Google Popular Times or similar public busyness indicators as relative, not measured footfall."
- Require unavailable source families to be stated plainly.
- Keep better website fetching as a separate tool stream.

### 10. Follow-Up Still Needs A Product Stream

The prompt revamp now adds a pragmatic middle path for narrow same-target questions:

- answer from prior report;
- use specialist notes and Places context;
- use one focused current-source check when it clearly improves a narrow answer.

That is enough for the prompt revamp, but it is not the full follow-up product design. Active-session retargeting, broad follow-up research, and richer route tests still belong in the follow-up stream.[^followup-code][^followup-tests]

Recommendation:

- Keep the narrow fill-in path in the prompt revamp.
- In the follow-up stream, design full behavior for retargeting and broad follow-up research.
- Add route tests for narrow fill-in, broad same-target research, and different-target follow-ups.

### 11. Citations Should Be Introduced, But Not Oversold

The prompt revamp should ask for in-text citations because the product needs source-backed research. However, current plumbing does not structurally validate claim-level citations:

- grounding extraction collects `grounding_chunks` into `{title, url, domain}` objects.[^grounding-extract]
- tool provider pills are merged into final sources.[^sources-merge]
- final turn writes a `sources` array to the turn document.[^sources-turn]
- the UI renders markdown plus source chips, not verified inline citation objects.[^source-ui]

Recommendation:

- In the prompt revamp, require inline citations in final prose using sources from the turn.
- Do not make prompts longer to compensate for missing source metadata.
- In the citation stream, investigate support spans, source metadata, retrieved dates, quoted excerpts, and claim-source mapping.

Prompt rule:

```md
Cite specific claims inline. Use only sources actually returned in this turn. If a source family was unavailable, say so instead of implying it was checked.
```

Product implementation can become stronger later.

### 12. Evals Should Expand, But Not Block The Prompt Revamp

Normally, prompt changes should be validated before production. ADK supports both final-response and tool-use evaluation, and the existing eval harness already measures source categories, tool counts, tokens, final length, and judge dimensions.[^adk-eval][^score]

For this project, it is reasonable to revamp prompts first without expanding evals first, because the immediate goal is to raise the design level quickly. That is a conscious risk, not a denial that evals matter.

After the prompt revamp:

- add market coverage for PL, UK, US, DE;
- add no-target/city/national questions;
- add holdout questions outside current UI examples;
- separate routing/specialist-selection evals from final-report quality evals;
- avoid treating exact specialist sets as universal truth.

## What Should Not Change

Do not change these unless later evidence shows a problem:

- Keep the basic Router -> Context Enricher -> Research Lead -> Specialists topology.
- Keep specialists organized by evidence surface, not one-off use case.
- Keep `review_analyst` as a direct sibling specialist with structured review tools.
- Keep `dynamic_researcher_1` as an escape hatch for rare or uncovered angles.
- Keep the Research Lead's premise-audit concept.
- Keep bounded sufficiency checking, but make it shorter.
- Keep router boundary clarity, but do not keep worked examples in the runtime prompt.
- Keep charts as an optional final-report affordance, but do not let chart instructions dominate the research prompt.

## Recommended Prompt Revamp Direction

The prompt revamp should produce a cleaner instruction system, not just line edits.

### Proposed Prompt Architecture

1. **Router prompt**
   - Short routing contract.
   - Clear treatment of no-place, city, market, and follow-up cases.
   - Explicit narrow same-target fill-in route to follow-up.

2. **Context enricher prompt**
   - Places-only responsibility.
   - Explicit target and no-target branches.
   - Competitor selection based on relevance, not only distance/rating.

3. **Research lead prompt**
   - Compact orchestration contract.
   - Evidence-surface planning.
   - Flexible dispatch guidance.
   - One canonical final-report shape.
   - Clear stop/no-data behavior.

4. **Specialist base**
   - Universal rules only.
   - No market-specific domains.
   - No tool-specific web-search rule unless the specialist actually has web tools.

5. **Specialist body prompts**
   - Scope.
   - Unique evidence surfaces.
   - Boundaries.
   - Domain-specific output hints only where needed.

6. **Market config**
   - PL, UK, US, DE source families and platform names.
   - Currencies, official statistics bodies, job boards, review/delivery platforms, local press patterns.
   - Kept out of core universal prompts.

7. **Authoring guide**
   - Updated after the new prompts exist.
   - Describes where each kind of rule belongs.
   - Removes historical patch logic that no longer applies.

### Prompt Ownership Rules

Use these as the design filter during the revamp:

| Rule type                                         | Belongs in                                       |
| ------------------------------------------------- | ------------------------------------------------ |
| Agent role and responsibility                     | Prompt                                           |
| Tool availability and hard limits                 | Code/tool schema                                 |
| Market source families                            | Market config injected into prompt               |
| Source metadata and claim support                 | Code/product source pipeline                     |
| Citation formatting expectation                   | Prompt plus product validation later             |
| Retry, timeout, cap, auth, page-blocking behavior | Tools/callbacks/code                             |
| Report structure                                  | Research lead prompt                             |
| Specialist dispatch examples                      | Evals, not prompt, except rare boundary examples |
| Evaluation thresholds                             | Evals                                            |
| Durable user memory                               | Future memory design, not current prompts        |

## Streams To Track Separately

1. **Prompt revamp**
   - Primary next work.
   - Rewrite prompts for simplicity, structure, and scalability.
   - Do not wait for expanded evals, but document the risk.

2. **Citation/source stream**
   - Inline citation UX.
   - Claim-source mapping.
   - Grounding support spans/source metadata investigation.
   - Source drawer improvements.

3. **Tool/data stream**
   - Website fetching reliability.
   - Review fetch depth controls.
   - Market-specific config.
   - Better unavailable-source error types.

4. **Follow-up stream**
   - Full follow-up behavior beyond narrow fill-in.
   - Active-session retargeting.
   - Route tests for narrow fill-in, broad same-target research, and different-target follow-ups.

5. **Evals stream**
   - Market expansion: PL, UK, US, DE.
   - Off-matrix and holdout questions.
   - Routing, specialist selection, citation quality, and final-answer quality.

## Final Recommendation

Proceed with a full prompt revamp. Preserve the basic architecture and the few strong behavioral ideas, but rewrite the instruction prose around a simpler system:

- one owner per rule;
- one report contract;
- one shared specialist base;
- market-specific source guidance outside universal prompts;
- no duplicated source-quality rules;
- no impossible instructions;
- no hidden conflict between specialists;
- no fixed use-case recipes unless they are boundary examples.

The current prompts can work for known examples, but they are not clean enough to be the long-term standard for a scalable product.

## References

[^adk-llm]: Google ADK, "LLM Agent", https://adk.dev/agents/llm-agents/. The docs state that `LlmAgent` behavior is non-deterministic and guided by identity, description, instruction, tools, and output format.

[^adk-workflow]: Google ADK, "Workflow Agents", https://adk.dev/agents/workflow-agents/. Workflow agents provide deterministic orchestration: sequential, parallel, and loop.

[^adk-parallel]: Google ADK, "Parallel agents", https://adk.dev/agents/workflow-agents/parallel-agents/. The docs state parallel sub-agents run independently and do not automatically share conversation history or state during execution.

[^adk-loop]: Google ADK, "Loop agents", https://adk.dev/agents/workflow-agents/loop-agents/. The docs state loops require max iterations or another termination mechanism.

[^adk-tools]: Google ADK, "Custom Tools for ADK", https://adk.dev/tools-custom/. Tools are developer-defined functions or agents with structured inputs and outputs; instructions should guide when tools are used and how return values are handled.

[^adk-callbacks]: Google ADK, "Callbacks", https://adk.dev/callbacks/. Callbacks can observe, modify, guard, or replace model/tool/agent behavior.

[^adk-sessions]: Google ADK, "Session, State, and Memory", https://adk.dev/sessions/. Sessions hold one conversation thread; memory is searchable cross-session information.

[^adk-state]: Google ADK, "State: The Session's Scratchpad", https://adk.dev/sessions/state/. State is serializable key-value data for the current session, user, app, or invocation depending on prefix.

[^adk-eval]: Google ADK, "Evaluation Criteria", https://adk.dev/evaluate/criteria/. ADK supports tool trajectory, final response, hallucination, safety, and multi-turn evaluation criteria.

[^gemini-prompt]: Google AI for Developers, "Prompt design strategies", https://ai.google.dev/gemini-api/docs/prompting-strategies. The docs recommend clear/specific instructions, constraints, response formats, examples, and breaking complex prompts into components; they also warn that too many examples can cause overfitting to examples.

[^gemini-search]: Google AI for Developers, "Grounding with Google Search", https://ai.google.dev/gemini-api/docs/google-search. The docs describe real-time grounding, factuality, citations, and `groundingMetadata`.

[^gemini-function]: Google AI for Developers, "Function calling with the Gemini API", https://ai.google.dev/gemini-api/docs/function-calling. The docs describe function declarations, structured tool-call responses, application-side execution, and returning results to the model.

[^agent-router]: `agent/superextra_agent/agent.py:168-175`.

[^agent-pipeline]: `agent/superextra_agent/agent.py:160-164`.

[^agent-lead]: `agent/superextra_agent/agent.py:143-155`.

[^agent-tools]: `agent/superextra_agent/agent.py:148-152`.

[^catalog]: `agent/superextra_agent/specialist_catalog.py:50-193`.

[^catalog-guest-review]: `agent/superextra_agent/specialist_catalog.py:97-107` and `agent/superextra_agent/specialist_catalog.py:160-171`.

[^default-tools]: `agent/superextra_agent/specialists.py:179-185`.

[^review-tools]: `agent/superextra_agent/specialists.py:199-203`.

[^source-guidance]: `agent/superextra_agent/specialists.py:102-110` and `agent/superextra_agent/specialists.py:137`.

[^base-web]: `agent/superextra_agent/instructions/specialist_base.md:22-24`.

[^base-priors]: `agent/superextra_agent/instructions/specialist_base.md:26-40`.

[^base-visible]: `agent/superextra_agent/instructions/specialist_base.md:46-50`.

[^lead-visible]: `agent/superextra_agent/instructions/research_lead.md:104-114`.

[^review-no-search]: `agent/superextra_agent/instructions/review_analyst.md:21`.

[^review-tools-prompt]: `agent/superextra_agent/instructions/review_analyst.md:13-34` and `agent/superextra_agent/instructions/review_analyst.md:44-53`.

[^review-competitor-cap]: `agent/superextra_agent/instructions/review_analyst.md:34`.

[^google-review-cap]: `agent/superextra_agent/apify_tools.py:43-57`.

[^ta-review-cap]: `agent/superextra_agent/tripadvisor_tools.py:257-271`.

[^guest-conflict]: `agent/superextra_agent/instructions/guest_intelligence.md:5-23`.

[^lead-recon]: `agent/superextra_agent/instructions/research_lead.md:23`.

[^lead-dispatch]: `agent/superextra_agent/instructions/research_lead.md:41`.

[^lead-floors]: `agent/superextra_agent/instructions/research_lead.md:107`.

[^lead-final]: `agent/superextra_agent/instructions/research_lead.md:69-85`.

[^lead-add-one]: `agent/superextra_agent/instructions/research_lead.md:37`.

[^lead-structure]: `agent/superextra_agent/instructions/research_lead.md:79-85`.

[^lead-assumptions]: `agent/superextra_agent/instructions/research_lead.md:19-23`.

[^lead-boundaries]: `agent/superextra_agent/instructions/research_lead.md:60-68`.

[^router-first]: `agent/superextra_agent/instructions/router.md:27-31`.

[^enricher-always]: `agent/superextra_agent/instructions/context_enricher.md:5-9`.

[^nullable-place]: `src/lib/chat-state.svelte.ts:613-630`.

[^context-injection]: `functions/index.js:174-176` and `functions/index.js:282-293`.

[^matrix-context]: `agent/evals/run_matrix.py:114-131`.

[^grounding-extract]: `agent/superextra_agent/firestore_events.py:208-228`.

[^sources-merge]: `agent/superextra_agent/gear_run_state.py:106-144`.

[^sources-turn]: `agent/superextra_agent/gear_run_state.py:227-231`.

[^source-ui]: `src/lib/components/restaurants/ChatThread.svelte:58-63` and `src/lib/components/restaurants/ChatThread.svelte:158-175`.

[^followup-prompt]: `agent/superextra_agent/instructions/follow_up.md:21-30`.

[^followup-code]: `agent/superextra_agent/agent.py:110-146`.

[^followup-tests]: `agent/tests/test_follow_up_routing.py:140-181`.

[^eval-venues]: `agent/evals/venues.json`.

[^eval-routing]: `agent/evals/queries_routing_subset.json:1-75`.

[^score]: `agent/evals/score.py:1-5`, `agent/evals/score.py:276-343`, and `agent/evals/score.py:400-441`.

[^dynamic-evals]: `agent/evals/queries_routing_subset.json:40-48` and `agent/evals/queries_routing_subset.json:63-72`.

[^dynamic-logs]: `agent/logs/2026-05-08_1410528145462788096.jsonl:26` and `agent/logs/2026-05-08_1410528145462788096.jsonl:31`.

[^menu-pricing]: `agent/superextra_agent/instructions/menu_pricing.md:7-21`.

[^ops-sources]: `agent/superextra_agent/instructions/operations.md:18-26`.

[^location-sources]: `agent/superextra_agent/instructions/location_traffic.md:21-27`.

[^location-popular]: `agent/superextra_agent/instructions/location_traffic.md:19` and `agent/superextra_agent/instructions/location_traffic.md:35-39`.

[^market-example]: `agent/superextra_agent/instructions/market_landscape.md:15-19`.

[^marketing-sources]: `agent/superextra_agent/instructions/marketing_brand.md:17-25`.
