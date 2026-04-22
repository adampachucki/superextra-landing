# Review of `agent-simplification-followups-plan-2026-04-22.md`

Reviewed on 2026-04-22 against the current repo state, focused unit tests, and primary documentation from ADK, Google Places, SerpApi, Apify, and Anthropic.

## Verdict

The plan is directionally good and mostly consistent with the simplification goal. PR A1, A3, B1's contract tightening, and C1/C2/C4 all address real issues. The two parts that need revision before implementation are A2 and B2.

The main standard I used here was simple: does the change remove moving parts, or does it quietly replace one workaround with another?

## Findings

### [P1] PR B2 has the right goal, but the proposed implementation understates the work and currently leans on data paths that do not exist in the wrapper code

Plan section: `docs/agent-simplification-followups-plan-2026-04-22.md:94-115`

Verified locally:

- `agent/superextra_agent/tripadvisor_tools.py:185-257` `get_tripadvisor_reviews()` does not currently accept `tool_context`, so the plan's "already has access to tool_context" claim is not true in the current code.
- `agent/superextra_agent/apify_tools.py:43-109` `get_google_reviews()` also does not accept `tool_context`.
- Neither wrapper currently returns a provider-level restaurant URL in the shape the frontend consumes. `get_tripadvisor_reviews()` returns review data only; `get_google_reviews()` returns `place_id`, `total_fetched`, and reviews.
- The frontend `ChatSource` contract requires a URL: `src/lib/firestore-stream.ts:33-37`.
- The worker currently merges only mapped `sources[]` payloads, deduped by URL: `agent/worker_main.py:642-675`.

Externally verified:

- SerpApi's TripAdvisor Search API exposes a place `link`, and the TripAdvisor Reviews API exposes per-review `link` fields.
- Google Places exposes `placeUri` and `reviewsUri`.
- Apify's Google Maps Reviews Scraper output includes Google Maps URLs in its dataset examples.

Assessment:

The **goal** is correct: review-heavy runs should surface user-visible provider citations. But the **implementation path** in the plan is not yet the lowest-change path, because it introduces a new `_tool_sources` state channel before proving simpler existing data sources are insufficient.

What I would change in the plan:

1. Keep the requirement: provider-level sources must land in final `sources[]`.
2. Rewrite the implementation note to reflect current code truth:
   - For Google, prefer deriving the citation URL from Google Places (`googleMapsUri` or `reviewsUri`) instead of inventing a new Apify-specific source path.
   - For TripAdvisor, preserve the selected result's `link` from the search step; the underlying API supports it, but the current wrapper drops it.
3. Only add `_tool_sources` state plumbing if those two simpler paths still cannot land the citations where the worker needs them.

That keeps PR B focused on restoring missing user-visible sources, not on adding a new general-purpose state mechanism.

### [P2] PR A2 treats the markdown-link fallback as dead before proving it

Plan section: `docs/agent-simplification-followups-plan-2026-04-22.md:45-55`

Verified locally:

- `_map_specialist()` still intentionally falls back to `extract_sources_from_text()` when grounding sources are absent: `agent/superextra_agent/firestore_events.py:262-283`.
- `_map_synthesizer()` still intentionally merges reply-text links into terminal `sources[]`: `agent/superextra_agent/firestore_events.py:317-326`.
- The helper is still covered by passing tests: `agent/tests/test_firestore_events.py:448-460`.
- Focused test run:
  - `cd agent && PYTHONPATH=. .venv/bin/pytest tests/test_firestore_events.py -q` → `32 passed`

Assessment:

It is valid to remove dead code. The problem is that the plan has not yet shown this path is dead. The specialist-side markdown source stuffing is gone, but the synthesizer text fallback is still an active, documented escape hatch for inline citations in reply text.

What I would change in the plan:

1. Narrow A2 to "remove the specialist activity text fallback first" only if live logs show grounding fully covers specialist citations.
2. Keep the synthesizer text fallback until runtime evidence shows it never contributes legitimate sources.
3. If the goal is deletion-first, add one short verification sentence to the plan: inspect recent complete runs and confirm zero terminal sources were supplied only by markdown-link parsing before deleting the code.

That preserves the simplification principle without deleting a still-exercised safety net on assumption alone.

### [P2] PR B1 slightly misstates the current prompt problem; the real root cause is the tool contract

Plan section: `docs/agent-simplification-followups-plan-2026-04-22.md:77-90`

Verified locally:

- `agent/superextra_agent/instructions/review_analyst.md:27-30` already tells the model to check `match_confidence`, review candidates, and only retry if candidate addresses do not match the Places address.
- `agent/superextra_agent/tripadvisor_tools.py:153-180` still returns `status: "success"` even when `match_confidence == "low"`.
- Existing tests already assert low confidence can happen without treating it as a failure: `agent/tests/test_tripadvisor_tools.py:188-201`.
- Focused test run:
  - `cd agent && PYTHONPATH=. .venv/bin/pytest tests/test_tripadvisor_tools.py -q` → `14 passed`

Assessment:

The plan is right that this path must be tightened. But the prompt is not blank today; the real failure is that the tool exposes low confidence as a successful result. That makes the contract ambiguous and invites downstream misuse.

What I would change in the plan:

1. Keep the tool contract change exactly as proposed: low-confidence match should not be `success`.
2. Make the prompt edit optional and minimal, since a version of that instruction is already present.
3. Explicitly say the root fix is "make the tool contract reflect uncertainty," not "add more prompt text."

That keeps PR B1 aligned with removing the cause instead of layering more instruction on top of a misleading tool response.

## What Is Strong In The Plan

### A1 is a good prompt simplification

`agent/superextra_agent/instructions/synthesizer.md:40-56` is currently chart-biased. Loosening that wording is a real simplification because it removes pressure on the synthesizer to manufacture visuals for weakly quantitative prompts.

### A3 is valid hardening, and the repo already has precedent for it

`agent/superextra_agent/agent.py:73-76` and `agent/superextra_agent/specialists.py:250-252` still use `.format(**values)`. The risk described in the plan is real. Focused tests confirmed current instruction-provider coverage is healthy:

- `cd agent && PYTHONPATH=. .venv/bin/pytest tests/test_instruction_providers.py -q` → `14 passed`

External verification also supports the concern: ADK's state docs explicitly call out literal-brace issues in instruction templates and provide an official `inject_session_state` helper for InstructionProviders.

For this PR, the plan's `.replace()` loop is a reasonable low-risk fix. If the goal later becomes "remove custom template code entirely," ADK's built-in helper is worth revisiting.

### C1/C2/C4 are the right kind of structural cleanup if kept mechanical

The duplicated specialist mappings are real across `agent.py`, `specialists.py`, and `firestore_events.py`. Consolidating them into one data table is compatible with the simplification goal **only if** the new module stays boring:

- one flat catalog
- local derivations
- no helper classes, registries, or extra indirection

If implemented that way, C1/C2/C4 reduce drift and remove repeated edits. If implemented as a mini-framework, they would miss the point.

### C3 is optional and should stay optional

I agree with the plan's own framing here: Gemini client unification is cleanup, not a user-facing simplification. If C1 gets wider than expected, C3 should drop out.

## External Guidance Check

The plan's general direction matches current best-practice guidance:

- Anthropic recommends finding the simplest solution possible first and warns that frameworks and abstraction layers can obscure prompts and responses, making systems harder to debug: [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
- ADK documents `ToolContext.state` as the supported way to persist tool-side state into `EventActions.state_delta`: [ADK State](https://adk.dev/sessions/state/)
- ADK also documents that InstructionProviders avoid automatic brace interpolation and provides `inject_session_state()` for safer template injection: [ADK State](https://adk.dev/sessions/state/)
- Google Places documents stable user-facing place and review URLs (`placeUri`, `reviewsUri`), which matters for the `sources[]` contract: [Places REST Resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places)
- SerpApi documents TripAdvisor search-result `link` and TripAdvisor review `link` fields: [Tripadvisor Search API](https://serpapi.com/tripadvisor-search-api), [Tripadvisor Reviews API](https://serpapi.com/tripadvisor-reviews-api)
- Apify documents Google Maps URL fields in review scraper output examples: [Google Maps Reviews Scraper](https://apify.com/compass/google-maps-reviews-scraper)

## Recommended Revision To The Plan

If the goal is to keep this follow-up round aggressively simple, I would revise the plan like this:

1. Ship A1 exactly as written.
2. Ship A3 exactly as written, with the new brace-regression tests.
3. Ship B1 with emphasis on the tool contract change; keep the prompt diff minimal.
4. Rewrite B2 before implementation:
   - preserve or derive provider URLs from existing vendor/Places data first
   - only add `_tool_sources` state if a simpler path fails
5. Narrow A2:
   - delete only the proven-dead text-source path
   - keep the synthesizer text fallback until measured away
6. Ship C1/C2/C4 only if the catalog stays data-only and removes more duplicated maps than it adds files/helpers.
7. Keep C3 deferred unless it falls out nearly for free.

## Bottom Line

This follow-up plan is mostly on the right track. The strongest parts are the ones that make existing contracts honest and remove duplicated structure. The weakest parts are the ones that assume a path is dead or jump straight to new plumbing before exhausting simpler existing data.

If revised along the lines above, the plan would stay much closer to the standard you set: remove causes, remove duplication, and do not add a new layer unless the simpler route has clearly failed.
