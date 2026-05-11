# Agent Adjacent Streams Plan

Date: 2026-05-11  
Scope: work intentionally separated from the main prompt-revamp stream.

The main prompt revamp should stay focused on cleaner instruction design. These streams cover product, tool, citation, follow-up, and evaluation work that should not be hidden inside longer prompts.

## Stream 1: Citation And Source Plumbing

### Rationale

The product needs in-text citations, but prompts alone cannot guarantee claim-level citation quality. Current implementation stores source drawer entries, not verified claim-source mappings.

Current evidence:

- `firestore_events.extract_sources_from_grounding()` collects `grounding_chunks` into `{title, url, domain}`.
- `gear_run_state.py` merges grounding sources and `_tool_src_*` provider pills.
- final turn docs store a `sources` array.
- `ChatThread.svelte` renders markdown plus source chips.
- there is no structural parser that verifies inline citations against claims.

User feedback:

- We do want in-text citations.
- This is a feature stream on top of research quality, not the main prompt issue.
- Do not make citation rules longer as a substitute for source plumbing.

### Direction

Build a citation layer that supports inline references without relying only on model prose.

Investigate:

- Gemini `groundingMetadata`;
- support spans or equivalent claim-grounding data;
- source chunk title, URI, domain, retrieved date, and rendered URL behavior;
- source records from custom tools;
- whether citations should be model-authored, post-processed, or both.

Deliverables:

- source object schema proposal;
- inline citation syntax decision;
- source drawer plus inline citation UX plan;
- claim-source validation approach;
- fallback behavior when support spans are absent;
- test cases for unsupported citation, duplicate citation, and provider-only source.

Prompt impact:

- Keep prompt rule short: cite specific claims inline using sources returned in this turn.
- Do not add detailed source-plumbing logic to prompts.

References:

- Gemini grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
- Current source extraction: `agent/superextra_agent/firestore_events.py`
- Current final source merge: `agent/superextra_agent/gear_run_state.py`
- Current UI rendering: `src/lib/components/restaurants/ChatThread.svelte`

## Stream 2: Tool And Data Improvements

### Rationale

Several quality issues are tool/data problems, not prompt problems:

- web pages can be blocked or dynamic;
- delivery and social platforms may be inaccessible;
- review fetch depth should depend on query type;
- market-specific source profiles should be centralized;
- tools should return structured unavailable/error metadata.

User feedback:

- Better website fetching should be kept aside from prompt engineering.
- Review fetching should default around 50 reviews, but fetch more for explicit sentiment-over-time or deep review-analysis questions.
- Certainty should be reserved for direct integrations with structured outputs.
- Market focus should cover PL, UK, US, DE.

### Work Packages

#### 2.1 Website Fetching

Problem:

- `fetch_web_content` returns truncated page content and limited metadata.
- It cannot solve blocked pages, rendered app pages, or source-specific restrictions.

Direction:

- Evaluate better fetching options.
- Return structured metadata: status, URL, final URL, title, domain, retrieved_at, content_length, truncated, error_type.
- Distinguish `blocked`, `not_found`, `timeout`, `unsupported_dynamic_page`, `paywalled`, and `empty_content`.

Prompt impact:

- Prompts should say "if inaccessible, state unavailable and use next-best source."
- Tools should provide the reason.

#### 2.2 Review Fetch Depth

Current code:

- Google Reviews defaults to 50 and caps at 200.
- TripAdvisor defaults to 5 pages, 50 reviews, and caps at 10 pages, 100 reviews.
- competitor `max_reviews=30` is prompt-only, not enforced.

Direction:

- Define review-depth policy:
  - default target: 50;
  - default competitor: 30-50 depending on query;
  - deep review analysis: up to cap or all accessible pages if justified;
  - time-series sentiment: prefer broader sample and preserve date distribution.
- Enforce hard caps in tool code or wrappers, not just prompt text.
- Expose sample counts and truncation clearly in tool output.

Prompt impact:

- `review_analyst.md` can request deeper samples for review-heavy questions.
- Budget enforcement belongs in code.

#### 2.3 Market Source Profiles

Problem:

- Current prompts embed Polish/Tricity source examples.
- Prompt core should be market-independent.
- Specialists still need source instincts. A fully generic "use sources" rule is too vague, but exhaustive per-agent source lists would recreate prompt bloat and stale recipes.

Direction:

- Create source profiles for PL, UK, US, DE.
- Include:
  - official statistics bodies;
  - municipal/local authority sources;
  - job boards and wage sources;
  - delivery platforms;
  - review/reservation platforms;
  - local press patterns;
  - food blogs/writers/community sources;
  - currency and language expectations.
- Inject the relevant profile based on selected place, explicit user market, or fallback locale.
- Add specialist-level source recommendations as directional guidance, not exhaustive lists:
  - point the specialist toward the right evidence families;
  - describe source quality and useful source variety;
  - avoid implying that named examples are required or complete;
  - avoid copying full market lists into every specialist prompt.
- Keep ownership clear:
  - the Lead owns market selection and brief-specific source priorities;
  - specialists own domain source instincts;
  - code/config should eventually inject only the relevant market + specialist hints.

Open question:

- If only Place ID is supplied, what reliable country/market signal is available from Places details? If not enough, store market on the frontend/backend session.
- Should source hints be generated by the Lead from a config object, or injected directly into specialist instructions at runtime after market detection?

Prompt impact:

- Core prompts refer to "market profile" and "local-language sources."
- Source profiles supply the concrete market names.
- Specialist prompts should keep short `Evidence To Seek` guidance that is quality-focused and non-limiting.
- Do not turn source recommendations into checklists. They should improve taste and direction, not constrain research.

#### 2.4 Tool Error Semantics

Direction:

- Standardize tool errors: `no_data`, `ambiguous_entity`, `source_unavailable`, `blocked`, `timeout`, `rate_limited`, `auth_error`, `retryable_error`.
- Let prompts react to a small set of statuses instead of parsing arbitrary text.

References:

- Gemini function calling docs: https://ai.google.dev/gemini-api/docs/function-calling
- ADK custom tools docs: https://adk.dev/tools-custom/
- Google review tool: `agent/superextra_agent/apify_tools.py`
- TripAdvisor tool: `agent/superextra_agent/tripadvisor_tools.py`
- Web fetch tool: `agent/superextra_agent/web_tools.py`

## Stream 3: Follow-Up And Retargeting Experience

### Rationale

Before the prompt revamp, follow-up behavior was too binary:

- answer from old report;
- or launch full research.

The prompt revamp now gives follow-up access to the final report, specialist notes, Places context, and limited web/page tools for narrow same-target fill-ins. This is a pragmatic first step, not the full follow-up product design.

There is also a retargeting issue:

- normal first-turn UX requires a selected restaurant;
- active-session follow-ups do not carry a new place context;
- `context_enricher` skips if `places_context` already exists;
- a user asking to research a different restaurant in the same session can be served stale context.

User feedback:

- The middle ground is missing.
- The current full research relaunch for a small new need feels strange.
- Users may want to change the provided place during a session.

### Direction

Design three follow-up modes:

1. **Answer from existing report**
   - no new tools;
   - concise answer;
   - cite existing report/source references where possible.

2. **Light follow-up research**
   - one or two focused tool calls or one specialist;
   - short latency budget;
   - updates only the requested angle;
   - no full multi-specialist report.

3. **Full research**
   - new place, broad new topic, or multi-surface investigation;
   - explicit progress state;
   - new context if the target changes.

### Retargeting Work

Questions to solve:

- Should active chat expose a place picker for "research another restaurant"?
- Should follow-up requests carry optional `placeContext`?
- Should a new target create a new session by default?
- If the same session is used, should `places_context` be versioned by target/turn?
- Should `_skip_enricher_if_cached` check whether the active target changed?

Likely direction:

- For a different restaurant, prefer a new session unless the UX intentionally supports comparison or retargeting.
- If retargeting stays in-session, pass a new Place ID and invalidate or version cached Places context.

Prompt impact:

- Router can route "new restaurant" to research.
- Research Lead should not assume prior Places context applies when the user names a new target.
- Real correctness needs product/code support.

Tests:

- follow-up answer from existing report;
- misrouted follow-up that requires new research;
- new restaurant in existing session;
- changed target with new Place ID;
- no stale `places_context` reuse.

References:

- Follow-up prompt: `agent/superextra_agent/instructions/follow_up.md`
- Router follow-up tests: `agent/tests/test_follow_up_routing.py`
- Enricher cache callback: `agent/superextra_agent/agent.py`
- Chat start/send path: `src/routes/agent/chat/+page.svelte`

## Stream 4: Evals

### Answer: Current Evals vs ADK/Google Agent Platform

Current Superextra evals are mostly custom, not the ADK evaluation framework as the primary harness.

Current setup:

- `npm run test:evals` runs live Gemini routing tests for router/follow-up behavior.
- `agent/evals/run_matrix.py` runs venue x query matrices using ADK `Runner`, `App`, and `VertexAiSessionService`.
- `agent/evals/parse_events.py` parses captured ADK events into product-specific run records.
- `agent/evals/score.py` computes custom deterministic metrics and optional Gemini judge scores.
- `agent/evals/pairwise.py` supports pairwise report comparison with a judge model.

So the stack uses ADK primitives and Vertex sessions, but the evaluation definitions, scoring, and reports are custom.

### Rationale

ADK evaluation criteria are still useful as a reference because they distinguish final response quality, tool trajectory, hallucination, safety, and multi-turn behavior. But Superextra needs restaurant-specific metrics too:

- source diversity;
- specialist set reasonableness;
- review/provider coverage;
- evidence specificity;
- operator usefulness;
- local-market faithfulness;
- citation quality.

### Direction

Do not block the prompt revamp on expanded evals. After prompt revamp:

- expand venues/markets to PL, UK, US, DE;
- add holdout queries outside current known UI examples;
- add no-target and retargeting cases if product supports them;
- separate routing evals from research quality evals;
- avoid overfitting to exact specialist sets;
- add citation-quality checks once citation plumbing exists.

Work packages:

1. **Market coverage**
   - Add venues in PL, UK, US, DE.
   - Use varied restaurant types and city sizes.

2. **Query coverage**
   - First-turn local operator questions.
   - Follow-up questions.
   - New-place/retargeting questions.
   - Sparse evidence questions.
   - Unsupported premise questions.

3. **Scoring**
   - Keep custom metrics.
   - Consider mapping some checks to ADK-like categories:
     - tool trajectory;
     - final response quality;
     - hallucination/groundedness;
     - multi-turn success.

4. **Human review**
   - Add a small expert/operator review loop for high-impact prompt changes.
   - Use it to calibrate judge metrics.

References:

- ADK evaluation criteria: https://adk.dev/evaluate/criteria/
- Current matrix runner: `agent/evals/run_matrix.py`
- Current scorer: `agent/evals/score.py`
- Current pairwise judge: `agent/evals/pairwise.py`
- Current routing eval tests: `agent/tests/test_router_evals.py`, `agent/tests/test_follow_up_routing.py`

## Stream 5: Deployment And Observability For Agent Changes

### Rationale

Prompt changes are production behavior changes. Even if eval expansion comes later, deployment needs basic observability.

Direction:

- Record prompt version in run metadata.
- Preserve old prompt version for rollback.
- Capture specialist dispatch counts and source counts by run.
- Track error and no-data rates by tool.
- Track follow-up mode once follow-up stream exists.

Prompt impact:

- None, except a version label if helpful.

References:

- Firestore progress plugin: `agent/superextra_agent/firestore_progress.py`
- Run state: `agent/superextra_agent/gear_run_state.py`
- Deployment gotchas: `docs/deployment-gotchas.md`

## Suggested Ownership

| Stream                   | Suggested owner type         |
| ------------------------ | ---------------------------- |
| Citation/source plumbing | backend + frontend           |
| Tool/data improvements   | backend/agent tools          |
| Follow-up/retargeting    | product + frontend + agent   |
| Evals                    | agent/eval engineering       |
| Deployment/observability | backend/agent infrastructure |

## References

- Prompt revamp plan: `docs/agent-prompt-revamp-plan-2026-05-11.md`
- Current review: `docs/current-agent-prompt-review-2026-05-11.md`
- External standard: `docs/agent-design-prompting-standard-2026-05-09.md`
- Google ADK evaluation criteria: https://adk.dev/evaluate/criteria/
- Google ADK custom tools: https://adk.dev/tools-custom/
- Gemini prompt design strategies: https://ai.google.dev/gemini-api/docs/prompting-strategies
- Gemini grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
- Gemini function calling: https://ai.google.dev/gemini-api/docs/function-calling
