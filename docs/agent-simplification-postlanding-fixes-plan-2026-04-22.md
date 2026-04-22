# Post-landing fixes for the follow-ups round (PR A/B/C)

> Planned 2026-04-22 after an external code review of the follow-ups execution (PR A/B/C). When approved, copy this plan to `docs/agent-simplification-postlanding-fixes-plan-2026-04-22.md` per the repo convention.

## Context

The follow-ups round (commits `a4e6738..af49c5b`) shipped three PRs: prompt tidies (A), review-pipeline quality (B: TripAdvisor confidence + provider-level sources), and structural dedup (C: specialist catalog). Post-landing review surfaced two real product-impacting bugs and one latent risk. All three have root-cause fixes that shrink or preserve code rather than add layers.

Verified empirically:

1. **`.replace()` corrupts content in three instruction providers.** Confirmed locally: setting `market_result = "literal token {pricing_result}"` caused the synth to render "literal token PRICE" (the `{pricing_result}` placeholder inside the already-inserted market value got rewritten on a later iteration). A post-plan review caught the same bug in `_follow_up_instruction` via `final_report = "literal token {places_context}"` → "literal token PLACECTX". Same shape also broke brace-escape in the chart JSON example inside `synthesizer.md` — it renders `{{"type":"bar"...}}` instead of `{"type":"bar"...}`. Synth + gap regressions were introduced by PR A3; follow_up was already on `.replace()` and was never actually correct. All three were "fixing" a KeyError that `.format()` doesn't actually raise on inserted values (verified: `.format()` does NOT re-scan values; only unknown TEMPLATE placeholders crash it, which only happens on typos).
2. **Google Reviews citation mislabels competitor calls.** `get_google_reviews` reads the single target-scoped `_target_google_maps_uri` from state regardless of which `place_id` was passed, so a competitor review fetch gets attributed to the target's Maps URL in `sources[]`. Reviewer reproduced locally.
3. **TripAdvisor search can pick the wrong place to begin with.** Current `find_tripadvisor_restaurant` builds its SerpAPI query from `name + area` only; the caller's `address` is used post-selection to compute `match_confidence` but never to steer the search itself. Root cause of wrong-place fetches: we throw away the disambiguating signal the caller provided.

Plus two cosmetic items flagged in my own /review: a dead `tool_context` parameter on `get_tripadvisor_reviews`, and a missing one-line note in the worker about the "one event per tool call" assumption that `_tool_sources` drain relies on.

Intended outcome: a single bundled commit that fixes all three bugs via root-cause changes, not symptom patches. Net LOC should go **down**, not up.

## Scope — one bundled commit

### 1. Restore `.format()` for all three instruction providers (synth + gap + follow_up)

**Root cause removed.** Chained `.replace()` has two regressions that `.format()` does not:

- Each `.replace()` re-scans the growing template, so placeholder-shaped text inside already-inserted specialist outputs gets rewritten by later iterations. Reviewer reproduced with `final_report = "literal token {places_context}"` — follow_up renders "literal token PLACECTX".
- `.replace()` doesn't honour `{{`/`}}` escape semantics, so the chart-JSON example in `synthesizer.md` renders with literal double braces and the LLM sees malformed JSON in its own instructions.

`.format()` does NOT re-scan values (verified in Sim 1) and unescapes `{{`/`}}` correctly. The original comment that pushed `follow_up` onto `.replace()` — "LLM output may contain curly braces" — was based on the same misreading of `.format()` that later produced A3. Fixing all three callers (not just synth + gap) is the actual root-cause removal.

**Changes:**

- `agent/superextra_agent/agent.py`: `_synthesizer_instruction` returns `_SYNTHESIZER_TEMPLATE.format(**values)` (as before A3).
- `agent/superextra_agent/agent.py`: `_follow_up_instruction` returns `_FOLLOW_UP_TEMPLATE.format(**values)` — `follow_up.md` only contains three plain placeholders (`{final_report}`, `{places_context}`, `{research_plan}`) with no literal `{` characters, so `.format()` works with no escaping needed.
- `agent/superextra_agent/specialists.py`: `_gap_researcher_instruction` returns `_GAP_RESEARCHER_TEMPLATE.format(**values)` (as before A3).
- Delete the two brace-regression tests added in A3: `test_literal_braces_in_values_do_not_raise` in `test_instruction_providers.py` and `test_gap_researcher.py` — they assert behaviour that `.format()` never exhibited.
- `synthesizer.md` keeps its existing `{{`/`}}` escapes (they were correct before A3, and still are).
- Existing follow_up tests in `test_follow_up_routing.py` / `test_instruction_providers.py` remain green under `.format()` — no new test work needed.

### 2. Per-place Google Reviews citations

**Root cause removed.** `_target_google_maps_uri` is a single-scope state key but the tool is called for multiple restaurants. Replace it with per-place lookups that don't require new state plumbing for competitors either.

Key insight: Google Maps has a deterministic URL format for any place_id — `https://www.google.com/maps/place/?q=place_id:<PLACE_ID>`. No API call needed to derive the URL (verified in Sim 2). Only the human-readable NAME for the pill label needs state-backed lookup.

**State-shape choice: per-place keys, not a shared dict.** `get_batch_restaurant_details` runs its inner calls via `asyncio.gather`, so a shared `_place_names` dict with read-modify-write would be fragile under concurrent completion. Using one key per place (`_place_name_<place_id>`) eliminates the concern entirely — each coroutine writes its own independent key, no shared mutable state, no setdefault dance, no assumption about where awaits sit. Cost: a few extra state keys per session (~3-5), acceptable.

**Changes:**

- `agent/superextra_agent/places_tools.py`:
  - `get_restaurant_details`: alongside the existing `_target_lat`/`_target_lng` writes, stash `tool_context.state[f"_place_name_{place_id}"] = displayName.text`. Applies to every call — target and competitors.
  - `get_batch_restaurant_details`: thread `tool_context` through to inner `get_restaurant_details` calls. Currently it omits the kwarg, so competitor details never reach state. One-line change to the gather args.
  - Delete the `_target_google_maps_uri` write (no longer read by anyone after the apify change below).
- `agent/superextra_agent/apify_tools.py`:
  - `get_google_reviews`: derive `maps_uri = f"https://www.google.com/maps/place/?q=place_id:{place_id}"` deterministically from the `place_id` argument. Read name from `tool_context.state.get(f"_place_name_{place_id}")`, fall back to `"restaurant"` if not cached.
  - Emit source entry `{title: f"Google Reviews — {name}", url: maps_uri, domain: "google.com"}`. Overwrite-only write to `_tool_sources` — unchanged pattern.
- Worker accumulator (`worker_main.py`) is unchanged — it already dedupes by URL across `_tool_sources` state_deltas. Multiple calls with distinct place_ids produce distinct URLs, so each restaurant's pill survives. The old flaw (single target URL reused) goes away naturally.

**Tests:**

- `test_places_tools.py`: assert `get_restaurant_details` writes `_place_name_<pid>` for the passed place_id; assert `get_batch_restaurant_details` writes one such key per id in the batch.
- `test_apify_tools.py`: two successive `get_google_reviews` calls for different place_ids write distinct URL source entries; title uses the stashed name; missing key falls back to `"restaurant"`.
- Drop `test_skips_source_when_uri_missing` (based on the now-deleted `_target_google_maps_uri` key) and replace with "URL is always derivable from place_id, so citation always emits."

### 3. TripAdvisor search: include address in the query (root-cause fix for wrong-place matches)

**Root cause, explained.** Today:

1. Orchestrator tells review_analyst to pass `name + area + address` (per `review_analyst.md:28`).
2. `find_tripadvisor_restaurant` uses only `name + area` in the SerpAPI query.
3. SerpAPI returns top candidates — no address signal. Possible wrong first result.
4. We take candidate 0, fetch `tripadvisor_place` details, THEN compare addresses for confidence.
5. If score < 0.4, we flag `status="low_confidence"` and bail.

Step 2 throws away the disambiguating signal the caller already provides. The confidence check (step 4–5, shipped in B1) is a safety net for a problem that didn't need to happen.

**Change:** when `address` is provided, include it in the search query: `q = f"{name} {address}"`. When `address` is empty, keep the existing `q = f"{name} {area}"`. The `area` doesn't disappear — the full address usually contains city/postal-code tokens, so SerpAPI has at least as much geographic signal.

Keep the post-selection confidence check exactly as-is — it's cheap, and it's the safety net that catches the rare case where SerpAPI's first result is still wrong despite the richer query.

**Known remaining tradeoff (reviewer concurs).** This fix does not remove the hard-coded candidate-0 selection bias at the SerpAPI layer — we still pick the first result. In combination with B1's `low_confidence` status contract, that's acceptable: the richer query makes candidate-0 correct more often, and B1 catches the remainder. Iterating across top-3 candidates via extra API calls is out of scope; revisit only if live data shows candidate-0-but-not-candidate-1 mismatches after this change.

This is a literal one-line change in the search-query construction plus one-word change in the search-query fallback.

**Changes:**

- `agent/superextra_agent/tripadvisor_tools.py`: in `find_tripadvisor_restaurant`, construct `q = f"{name} {address}" if address else f"{name} {area}"`.
- Tests already exercise address-vs-no-address paths via `test_address_matching_high_confidence` / `test_backward_compatible_without_address` — the first one will continue to pass; the second (no-address path) keeps the `area`-only query. Add one test that when address is provided, the outbound SerpAPI request's `q` param contains the street number / postal code — proves the richer query wins.

### 4. Drop dead `tool_context` parameter from `get_tripadvisor_reviews`

**Change:** remove the unused `tool_context=None` parameter from `get_tripadvisor_reviews` in `tripadvisor_tools.py`. Update the docstring.

Tests: the existing `test_does_not_touch_tool_sources` asserts the non-effect; rewrite as "calling the tool with no state returns reviews without error" — same guarantee without the dead param.

### 5. One-line assumption comment in `worker_main.py`

**Change:** add a short comment above the `_tool_sources` drain in `worker_main.py` noting that the overwrite-only pattern assumes ADK emits one event per tool call; if that ever changes, the drain must batch-merge multiple writes per event instead.

No code change, just a future-reader signpost.

## Explicitly deferred

- **Full low-confidence-profile trimming** in `find_tripadvisor_restaurant`. Today the tool returns `rating`, `ranking`, `sample_reviews`, etc. even when `status="low_confidence"`. Defence-in-depth would strip those fields when confidence is low so the LLM has nothing to misuse. Defer: the prompt-level gate + the search-query fix above together should make low-confidence rare enough that this isn't urgent. Revisit if real traffic shows LLMs ignoring the status field.
- **MockCtx dedup across 3 test files.** Three-line class duplicated; cheaper than a shared fixture nobody remembers about.

## Critical files

- `agent/superextra_agent/agent.py` — revert `_synthesizer_instruction` AND `_follow_up_instruction` to `.format()`.
- `agent/superextra_agent/specialists.py` — revert `_gap_researcher_instruction` to `.format()`.
- `agent/superextra_agent/places_tools.py` — stash `_place_name_<place_id>` per call + thread `tool_context` through `get_batch_restaurant_details`; delete `_target_google_maps_uri` write.
- `agent/superextra_agent/apify_tools.py` — derive Maps URL from place*id, read name from `\_place_name*<place_id>`.
- `agent/superextra_agent/tripadvisor_tools.py` — richer search query; drop dead `tool_context` param from `get_tripadvisor_reviews`.
- `agent/worker_main.py` — one-line comment.
- Tests touched: `test_instruction_providers.py`, `test_gap_researcher.py`, `test_places_tools.py`, `test_apify_tools.py`, `test_tripadvisor_tools.py`, `test_worker_main.py`.

## Reusable existing pieces

- `_merge_source` (`worker_main.py`) — already dedupes by URL, so multiple per-place Google Reviews citations automatically collapse when they share a URL.
- `_address_match_score` + `_normalize_address` (`tripadvisor_tools.py`) — unchanged; the confidence check stays as the safety net.
- `.format()` with `{{`/`}}` escapes (`synthesizer.md`, `gap_researcher.md`) — pre-A3 behaviour, restored.
- `AUTHOR_TO_OUTPUT_KEY` / the specialist catalog (`specialist_catalog.py`) — untouched.

## Pre-execution simulation — 2026-04-22

Five behaviors simulated at `/tmp/plan_simulation.py` before any code change:

- **Sim 1 — `.format()` restoration safe.** Rendered `market_result = "literal token {pricing_result}"` stays verbatim under `.format()`; chart-JSON `{{"type":"bar"}}` unescapes to `{"type":"bar"}`. Note: this sim only covered the synth template; a later reviewer repro showed the same bug in `_follow_up_instruction` under the old `.replace()`, extending Section 1 to include follow_up.
- **Sim 2 — `https://www.google.com/maps/place/?q=place_id:<PID>` resolves (302 via consent wall from the EU-based VM).** Real browsers that already accepted consent go straight to the Maps page. URL format is valid.
- **Sim 3 — Richer TripAdvisor query is safe; upside concentrated on ambiguous names.** For unique names like "Noma", both `"Noma Copenhagen"` and `"Noma Refshalevej 96, 1432 København"` return the correct restaurant as result 0 (place_id 694971). 30 candidates returned in both — richer query does not over-constrain. The fix's real value is ambiguous names ("Joe's Pizza", "Umami", etc.); it's a one-line structural improvement regardless.
- **Sim 4 — `_address_match_score` tolerates realistic variants.** Punctuation/abbreviation/diacritic/suffix pairs all clear the 0.4 threshold; totally-different addresses correctly score 0. The post-selection confidence check stays a reliable safety net.
- **Sim 5 — Per-place citation flow (mock with new per-place-key shape).** Three `get_google_reviews` calls with `_place_name_<pid>` keys populated → three distinct pills with correct names + place-specific URLs. Missing key → `"Google Reviews — restaurant"` fallback.

Verdict: plan is empirically sound. Sim 3's caveat about unique vs ambiguous names is acknowledged but doesn't gate shipping.

## Verification

1. **Unit:** `cd agent && PYTHONPATH=. .venv/bin/pytest tests/` — green (currently 169, expect ≈169 after swaps: +3 new assertions in places/apify/tripadvisor, −2 brace-regression tests, −1 "skips_source_when_uri_missing").
2. **Instruction rendering smoke:** small repl check — `_synthesizer_instruction` with `market_result = "literal token {pricing_result}"` must render the text unchanged, AND the chart-JSON example in the rendered prompt must contain single braces (`{"type":...}`), not double.
3. **Vitest + functions tests:** unchanged, still green.
4. **Live E2E:**
   - Q1 pricing comparison: sources_n should still be ~20+; chart fences still render; synth_outcome=ok.
   - Q2 review-sentiment: sources list should now contain **multiple** "Google Reviews — <name>" pills when review_analyst analyses target + competitors — verify both target and at least one competitor URL appear.
   - Q3 broad landscape: confidence-flagged TripAdvisor calls (if any) should be rarer — the richer query usually picks the right candidate the first time.
5. **UI verification:** per saved memory, open Chrome DevTools MCP on one rendered reply and confirm the source pills show per-place labels correctly.

## What gets worse (honest tradeoffs)

- **Revert A3:** specialists that ever DO emit a literal `{typo}` matching a template placeholder key will still NOT crash `.format()` (because `.format()` doesn't re-scan values). The A3 regression tests that claimed to protect against this were asserting nothing real; dropping them loses nothing.
- **Richer TripAdvisor query:** a search for a restaurant whose TripAdvisor listing has a WILDLY different address formatting could, in theory, return zero results where the old `name + area` query would have returned (wrong) candidates. The existing `"No TripAdvisor results found"` error path handles this; the LLM would need to retry with a simpler brief. Net: fewer wrong matches, possibly slightly more "no match" errors. Acceptable.
- **Per-place Google citations:** if the enricher didn't run (e.g. cached `places_context` from a prior turn, no fresh `_place_name_<pid>` writes), new competitors won't have stashed names and their pills fall back to "Google Reviews — restaurant". Cosmetic; the URL is still correct.

## Rollback plan

Single commit → single revert. Each of the five sub-changes stands alone if one proves problematic, so a surgical reversion via `git revert -n <sha>` + un-revert of the three good ones is possible.
