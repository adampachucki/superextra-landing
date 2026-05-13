# Place-Scoped Provider Data Plan

Status: proposed  
Date: 2026-05-13  
Audience: agent/runtime implementation team  
Scope: Google Places profiles, Google Maps reviews, TripAdvisor profiles, and TripAdvisor reviews for first-turn research and follow-up research.

## Summary

Follow-up research should be able to fetch structured provider data for any restaurant mentioned at any point in a conversation. That includes the original target, competitors from the first report, and newly named restaurants in later follow-ups.

The current setup is too target-centric. The first verified restaurant becomes a singleton target through `_target_place_id`, `_target_lat`, `_target_lng`, and `places_context`. That model works for a first-turn report, but it breaks down when a follow-up asks about a competitor or a new place. Google Places lookup may still work, but review fetching, TripAdvisor verification, and source attribution are partially tied to the original target.

The recommended direction is a broader place-scoped refactor:

- keep the original target immutable;
- introduce a session-state registry keyed by Google Place ID;
- make provider tools operate on an explicit Google Place ID;
- verify TripAdvisor matches against the requested place's own coordinates;
- emit sources for the specific place/provider used;
- keep review payloads out of durable session state except for compact metadata or summaries.

This is more work than patching the target keys, but it removes the root cause and keeps follow-up behavior flexible.

## Motivation

The product expectation is that follow-up chat can answer questions like:

- "Check Google reviews for that competitor."
- "What does TripAdvisor say about Nam-Viet?"
- "Pull Maps data for this new restaurant."
- "Compare review velocity for A and B."
- "Is this competitor still open, and what do recent reviews imply?"

These are not broad new market reports. They are bounded structured lookups that should fit inside a continuation turn.

The current architecture makes that awkward because structured provider access is not uniformly place-scoped. Some tools can technically accept a competitor Place ID, but state and attribution still assume the original target.

## Current Architecture

High-level agent flow:

```text
Router -> research_pipeline
           -> context_enricher
           -> research_lead
              -> specialists through AgentTool
           -> report_writer

Router -> continue_research
```

Relevant code:

- `agent/superextra_agent/agent.py`
- `agent/superextra_agent/places_tools.py`
- `agent/superextra_agent/apify_tools.py`
- `agent/superextra_agent/tripadvisor_tools.py`
- `agent/superextra_agent/specialists.py`
- `agent/superextra_agent/instructions/context_enricher.md`
- `agent/superextra_agent/instructions/continue_research.md`
- `agent/superextra_agent/instructions/review_analyst.md`

Current structured provider wiring:

- `continue_research` has direct access to:
  - `fetch_web_content`
  - `get_restaurant_details`
  - `get_batch_restaurant_details`
  - `find_nearby_restaurants`
  - `search_restaurants`
  - non-durable continuation specialists through `AgentTool`
- `review_analyst` has:
  - `get_google_reviews`
  - `find_tripadvisor_restaurant`
  - `get_tripadvisor_reviews`
- most non-review specialists have:
  - `google_search`
  - `fetch_web_content`

This means the capability exists in pieces, but the state model does not yet support "any place at any stage" cleanly.

## Findings

### 1. Places state is target-centric

`get_restaurant_details(place_id)` writes `_target_place_id` on the first detail call, and only writes `_target_lat`, `_target_lng`, and Google Maps source pills when the current `place_id` matches that target.

Relevant file:

- `agent/superextra_agent/places_tools.py`

This was originally reasonable. It protected the first report from competitor batch calls overwriting target coordinates. It also fixed a real class of bugs where a later competitor could bias downstream search or TripAdvisor verification toward the wrong venue.

But the same guard now prevents follow-up turns from treating a competitor or newly mentioned place as a valid structured-data subject.

### 2. TripAdvisor verification is target-scoped

`find_tripadvisor_restaurant(name, area, google_place_id)` searches TripAdvisor, fetches the top candidate, then verifies the candidate by comparing TripAdvisor coordinates to `_target_lat/_target_lng`.

That means a competitor TripAdvisor lookup can be verified against the original target's coordinates, not the competitor's coordinates.

Relevant file:

- `agent/superextra_agent/tripadvisor_tools.py`

This is the most important correctness issue. It can cause good competitor matches to be rejected, and in worse cases could allow wrong-venue logic if the state is stale or mismatched.

### 3. Source attribution is target-only

`get_google_reviews(place_id)` can fetch reviews for any Place ID, but it only emits a Google Reviews source pill if `place_id == _target_place_id`.

`find_tripadvisor_restaurant(...)` only emits a TripAdvisor source pill when the supplied Google Place ID matches `_target_place_id`.

Relevant files:

- `agent/superextra_agent/apify_tools.py`
- `agent/superextra_agent/tripadvisor_tools.py`

This means follow-up research can use provider data but fail to surface the provider source correctly for competitor/new-place answers.

### 4. `review_analyst` is prompted around a single target

`review_analyst.md` injects one `{target_place_id}` and directs the agent to use that exact ID for target TripAdvisor lookup. It mentions competitor Google Reviews, but the TripAdvisor flow remains effectively target-only.

Relevant file:

- `agent/superextra_agent/instructions/review_analyst.md`

The prompt should instead describe a place-scoped review workflow: resolve or use a Google Place ID, fetch Google Reviews, find and verify TripAdvisor for that same Google Place ID, then fetch TripAdvisor reviews if verified.

### 5. Continuation has tools but not durable structured place context

`continue_research` receives the original `places_context`, prior specialist reports, research coverage, final report, and continuation notes. It has direct Places tools, but new place lookups do not update a durable structured registry that future follow-up turns can reliably inspect.

Relevant file:

- `agent/superextra_agent/agent.py`

Continuation notes are useful for compact human-readable memory, but they should not be the only record of newly resolved provider identities.

## External Documentation And Best-Practice References

This plan aligns with the following documentation and provider contracts.

### ADK session state

ADK session state is intended for serializable per-session facts that agents and tools need across turns. Modifying `context.state` or `tool_context.state` is tracked into `EventActions.state_delta` and persisted by the session service.

References:

- https://adk.dev/sessions/state/
- https://github.com/google/adk-docs/blob/main/docs/sessions/state.md
- https://adk.dev/tools-custom/

Implication for this project:

- Use `session.state` for compact place identity/profile metadata.
- Do not create a separate Firestore-side memory model for this.
- Keep values serializable and bounded.
- Avoid storing full review payloads in durable state unless there is an explicit caching feature.

### ADK AgentTool and tool delegation

ADK `LlmAgent` can use regular function tools and other agents wrapped as `AgentTool`. The current architecture already uses this correctly for specialist helpers.

References:

- https://adk.dev/agents/llm-agents/
- https://adk.dev/tools-custom/

Implication for this project:

- Keep `review_analyst` as a focused helper for structured reviews.
- Let `continue_research` use direct place-resolution tools for small follow-up checks.
- Avoid inventing a separate orchestration system for follow-up enrichment.

### Google Places

Google Places API (New) supports Text Search, Nearby Search, and Place Details. Place Details uses a unique Place ID and a field mask to return selected fields such as address, phone, rating, reviews, hours, and location.

References:

- https://developers.google.com/maps/documentation/places/web-service/place-details
- https://developers.google.com/maps/documentation/places/web-service/text-search
- https://developers.google.com/maps/documentation/places/web-service/op-overview
- https://developers.google.com/maps/documentation/places/web-service/choose-fields

Implication for this project:

- Google Place ID should be the canonical key for structured place identity.
- Text Search and Nearby Search are discovery tools.
- Place Details is the profile hydration tool.
- Field masks should stay explicit for cost and response stability.

### Google reviews

Google Places can return review fields, but substantial review analysis needs richer review sampling. The current implementation uses an Apify Google Maps Reviews Scraper actor with Place IDs and `maxReviews`, which is suitable for analysis-grade review samples.

References:

- https://developers.google.com/maps/documentation/javascript/place-reviews
- https://developers.google.com/my-business/content/review-data
- https://apify.com/compass/google-maps-reviews-scraper
- https://apify.com/compass/google-maps-reviews-scraper/api

Implication for this project:

- Use Places reviews as profile context.
- Use Apify Google review extraction for structured review analysis.
- Google Business Profile APIs are owner/account-oriented and are not the right fit for arbitrary competitor public review research.

### TripAdvisor through SerpApi

SerpApi's TripAdvisor flow is place-oriented:

1. Search TripAdvisor with `engine=tripadvisor`.
2. Use restaurant filtering with `ssrc=r`.
3. Fetch place details with `engine=tripadvisor_place`.
4. Fetch reviews with `engine=tripadvisor_reviews`.

References:

- https://serpapi.com/tripadvisor-search-api
- https://serpapi.com/tripadvisor-place-api
- https://serpapi.com/tripadvisor-reviews-api

Implication for this project:

- TripAdvisor place IDs are provider-specific and should not replace Google Place IDs.
- Store the TripAdvisor match under the corresponding Google Place ID.
- Verify TripAdvisor identity against that Google place's coordinates, not against a global target.

## Target Design

### State model

Introduce an explicit place registry in ADK session state.

Suggested shape:

```json
{
	"original_target_place_id": "ChIJ...",
	"places_by_id": {
		"ChIJ...": {
			"google_place_id": "ChIJ...",
			"name": "Restaurant Name",
			"formatted_address": "Street, City",
			"lat": 54.35,
			"lng": 18.65,
			"google_maps_url": "https://maps.google.com/...",
			"rating": 4.5,
			"user_rating_count": 832,
			"price_level": "PRICE_LEVEL_MODERATE",
			"business_status": "OPERATIONAL",
			"website": "https://example.com",
			"phone": "+48...",
			"roles": ["target", "competitor", "mentioned"],
			"last_profile_fetch_turn": 3,
			"tripadvisor": {
				"place_id": "6796040",
				"url": "https://www.tripadvisor.com/...",
				"name": "Restaurant Name",
				"verified_distance_m": 21,
				"verified": true
			}
		}
	},
	"last_active_place_ids": ["ChIJ..."]
}
```

Names are suggestions. The implementation team should choose final key names, but the contract should preserve the concepts:

- immutable original target;
- dictionary keyed by Google Place ID;
- per-place coordinates;
- per-place provider metadata;
- active-place hint for follow-up turns.

### Backward compatibility

Existing sessions may only contain:

- `places_context`
- `_target_place_id`
- `_target_lat`
- `_target_lng`
- `_place_name_<place_id>`

The refactor should read these as fallback inputs. It does not need a migration job.

Recommended compatibility behavior:

- If `places_by_id` is missing and `_target_place_id` exists, construct a minimal target record lazily.
- Preserve `_target_place_id`, `_target_lat`, and `_target_lng` for existing geo-bias logic until that logic is explicitly replaced.
- Add `original_target_place_id` without deleting old keys.
- Do not overwrite `places_context` on follow-up place lookups.

### Tool contract

#### `search_restaurants(query, latitude=0, longitude=0, radius=5000)`

Keep this as discovery.

Recommended changes:

- Optionally register returned candidates as lightweight place records only if this does not bloat state.
- Prefer not to persist every search candidate by default.
- Persist only when a candidate is selected or hydrated with Place Details.

#### `get_restaurant_details(place_id, role=None)`

Make this the canonical profile hydration tool.

Responsibilities:

- call Google Place Details;
- return the profile;
- update `places_by_id[place_id]`;
- write `_place_name_<place_id>` for legacy timeline/source mapping;
- write a Google Maps source pill for that specific place;
- set `original_target_place_id` only when the call is explicitly target-role or when bootstrapping the first-turn target;
- avoid mutating original target coordinates for competitor/new-place calls.

Possible `role` values:

- `target`
- `competitor`
- `mentioned`
- `active`

If adding a `role` argument creates too much prompt friction, role can be inferred in wrapper tools instead. The important part is that per-place data is not blocked by target-only state.

#### `get_batch_restaurant_details(place_ids, role=None)`

Keep the batch helper, but have it call the same per-place update path.

Important behavior:

- batch competitor fetches must not overwrite original target;
- every fetched place can be registered under `places_by_id`;
- source emission should be place-scoped and deduped by URL downstream.

#### `get_google_reviews(place_id, max_reviews=50)`

Make this valid for any Google Place ID.

Responsibilities:

- fetch reviews from Apify;
- return review payload to the current turn;
- emit a Google Reviews source pill for that place;
- update compact per-place metadata if useful, such as `last_google_reviews_fetch_turn`, `last_google_reviews_count`, or review sample size;
- do not store the full review array in session state by default.

#### `find_tripadvisor_restaurant(google_place_id, name=None, area=None)`

Change the signature or semantics so Google Place ID is the anchor.

Responsibilities:

- find the Google place record in `places_by_id`;
- if the profile/coords are missing, fetch Place Details first or return a clear "place profile required" status;
- search TripAdvisor using the place name plus area;
- bias search with that place's lat/lng;
- fetch the top TripAdvisor candidate;
- verify candidate coordinates against that same Google place's lat/lng;
- store TripAdvisor match metadata under `places_by_id[google_place_id]["tripadvisor"]`;
- emit a TripAdvisor source pill for that place when verified.

Do not verify against `_target_lat/_target_lng`.

#### `get_tripadvisor_reviews(place_id, num_pages=5)`

This can remain a low-level SerpApi tool, but the higher-level prompt should keep it connected to a Google Place ID.

Optional cleaner tool:

```text
get_tripadvisor_reviews_for_google_place(google_place_id, num_pages=5)
```

This wrapper would:

- look up or resolve the TripAdvisor place ID for the Google place;
- fetch reviews;
- return reviews plus Google place identity;
- avoid the model juggling provider-specific IDs.

This wrapper is likely more reliable for agents.

### Prompt and agent behavior

#### `continue_research`

Update the continuation prompt to say:

- For a named restaurant, use report/context first to identify whether it is already known.
- If the user asks for Maps, Google Reviews, TripAdvisor, hours, rating, operating status, or review signals for a specific place, resolve or hydrate that place with structured tools.
- This is allowed for original target, competitors, and newly mentioned places.
- Do not rewrite the session's original target.
- If the request becomes a broad new market report or full rebuilt competitive set, suggest a new session.

#### `review_analyst`

Make `review_analyst` place-scoped.

Replace target-only language with:

- Use Google Place IDs from the brief or known place registry.
- For each requested place:
  - fetch Google reviews;
  - find and verify TripAdvisor against that same Google place;
  - fetch TripAdvisor reviews if verified;
  - show sample sizes and platform coverage.
- If a place is not resolved to a Google Place ID, use available place-resolution tools or ask the caller to provide one.

The review analyst should not inherit general web search. It should stay structured-provider focused.

#### `context_enricher`

Keep first-turn context enrichment, but move shared state writes into the same place registry.

The context enricher can still output human-readable `places_context` for downstream report writing. The new registry is the structured sibling, not a replacement for the prose packet.

### Source attribution

Provider source pills should become place-scoped.

Suggested source shape:

```json
{
	"provider": "google_reviews",
	"title": "Google Reviews - Restaurant Name",
	"url": "https://www.google.com/maps/place/?q=place_id:ChIJ...",
	"domain": "google.com",
	"place_id": "ChIJ..."
}
```

Equivalent for Google Maps and TripAdvisor.

The existing `_tool_src_<uuid>` pattern can remain. The important change is to stop suppressing sources for non-target places.

Potential concern: more source pills. This is acceptable for follow-ups because sources are already hidden when sparse and deduped by URL. If needed, source display can group by provider/place later. Do not block the data model for UI neatness.

### Geo-bias

Current `_inject_geo_bias` uses `_target_lat/_target_lng`. That remains useful for first-turn target-oriented web search.

Do not make dynamic follow-up active-place switching depend on mutating `_target_lat/_target_lng`.

Future improvement:

- add an invocation-scoped active location key such as `temp:active_lat` and `temp:active_lng`;
- have focused helpers set active location only for their own call;
- keep original target geo-bias unchanged for existing search behavior.

This can be deferred unless follow-up web search geo-bias is clearly wrong after the provider-data refactor.

## Implementation Plan

### Phase 1: Add place registry helpers

Add small helper functions, likely in a new module:

- `agent/superextra_agent/place_state.py`

Responsibilities:

- normalize a Google Places response into a compact state record;
- get or initialize `places_by_id`;
- upsert one place record;
- mark role without duplicate roles;
- get coordinates for a Google Place ID;
- get display name for a Google Place ID;
- store TripAdvisor match metadata;
- create source pill titles with place names.

Keep this module boring. It should not call external APIs. It should only transform and update state dictionaries.

Suggested functions:

```python
def upsert_google_place(state, place_id, place, role=None) -> dict: ...
def get_place_record(state, place_id) -> dict | None: ...
def get_place_coords(state, place_id) -> tuple[float, float] | None: ...
def mark_original_target(state, place_id) -> None: ...
def upsert_tripadvisor_match(state, google_place_id, match) -> None: ...
def place_source_title(state, place_id, provider_label) -> str: ...
```

### Phase 2: Refactor Places tools

Update:

- `agent/superextra_agent/places_tools.py`

Changes:

- `get_restaurant_details` writes to `places_by_id`;
- keep legacy `_place_name_<id>` writes;
- preserve first-turn `_target_*` writes only for first target setup;
- add source pill for each fetched detailed place, not only target, unless this creates unacceptable source volume in tests;
- ensure batch calls do not mutate original target identity.

Tests:

- first target initializes `original_target_place_id` and legacy `_target_*`;
- competitor detail writes `places_by_id[comp]` and does not overwrite original target;
- batch details registers all fetched places;
- Google Maps source emitted for competitor/new place;
- existing no-location safeguards remain.

### Phase 3: Refactor Google reviews tool

Update:

- `agent/superextra_agent/apify_tools.py`

Changes:

- remove `place_id == _target_place_id` source gate;
- emit source for any requested place;
- use place name from `places_by_id` or `_place_name_<id>` when available;
- optionally update compact review-fetch metadata on the place record;
- do not persist full review bodies.

Tests:

- competitor review fetch emits source;
- source title includes competitor name when known;
- no known place still emits safe generic Google Reviews source for the requested Place ID;
- max review cap remains.

### Phase 4: Refactor TripAdvisor tools

Update:

- `agent/superextra_agent/tripadvisor_tools.py`

Preferred change:

- make `find_tripadvisor_restaurant` anchor on `google_place_id`;
- read coords from `places_by_id[google_place_id]`;
- fallback to `_target_*` only when `google_place_id == original_target_place_id` and registry is missing;
- write verified TripAdvisor metadata under that Google place;
- emit source pill for any verified place.

Consider adding a higher-level wrapper:

```python
async def get_tripadvisor_reviews_for_google_place(
    google_place_id: str,
    name: str = "",
    area: str = "",
    num_pages: int = 5,
    tool_context=None,
) -> dict:
    ...
```

This wrapper is agent-friendly because it hides provider-specific sequencing.

Tests:

- competitor TripAdvisor lookup verifies against competitor coords;
- original target still works through backward-compatible state;
- missing coords returns unverified or profile-required status;
- source pill emitted for competitor when verified;
- wrong candidate remains stripped of rich fields;
- review pagination remains unchanged.

### Phase 5: Update specialist and continuation instructions

Update:

- `agent/superextra_agent/instructions/review_analyst.md`
- `agent/superextra_agent/instructions/continue_research.md`
- `agent/superextra_agent/instructions/AUTHORING.md`
- possibly `agent/superextra_agent/instructions/specialist_base.md`

Instruction changes:

- replace target-only review flow with place-scoped review flow;
- tell continuation that structured Maps/review lookup for a named competitor is allowed and bounded;
- keep broad new report boundary;
- state that original target context must not be rewritten during follow-ups;
- document the new state keys.

Tests:

- instruction provider tests assert no target-only TripAdvisor language remains;
- continue prompt mentions structured provider lookup for named places;
- AUTHORING documents `places_by_id` and `original_target_place_id`.

### Phase 6: Update agent wiring

Update:

- `agent/superextra_agent/agent.py`
- `agent/superextra_agent/specialists.py`

Changes:

- inject a compact known-place context into continuation and review analyst prompts if useful;
- give `review_analyst` place resolution/profile tools if it needs to handle names without Place IDs;
- otherwise require the caller/continue_research to resolve names before delegating review work.

Design preference:

- `continue_research` should resolve ambiguous named places.
- `review_analyst` should work best with explicit Google Place IDs but can hydrate details if a Place ID is supplied.
- Avoid making every specialist a place resolver.

### Phase 7: Timeline and source mapping polish

Update only if needed:

- `agent/superextra_agent/firestore_events.py`
- `agent/superextra_agent/gear_run_state.py`

The existing `_tool_src_*` drain can remain. If source titles now include place names directly, timeline/source mapping may need little or no change.

Possible improvements:

- read names from `places_by_id` in addition to `_place_name_<id>`;
- label source pills as `Google Reviews - <place>`;
- ensure activity rows stay user-facing and do not expose internal tool names.

## What Not To Do

Do not temporarily swap `_target_place_id`, `_target_lat`, or `_target_lng` for a follow-up place.

Why:

- brittle under parallel tool calls;
- brittle inside AgentTool child runs;
- likely to corrupt the original target;
- treats symptoms instead of the root cause.

Do not make follow-ups launch the existing `context_enricher` as-is.

Why:

- it has cached-skip behavior when `places_context` exists;
- it owns first-turn target/competitor context, not arbitrary follow-up provider lookup;
- it writes one prose `places_context` packet, not a structured per-place registry.

Do not persist full review payloads in session state by default.

Why:

- state bloat;
- slower prompts;
- higher risk of stale or irrelevant data affecting future turns;
- review data belongs to the current research turn unless deliberately summarized.

Do not expose generic SerpApi search to the parent continuation agent unless a separate product need emerges.

Why:

- this requirement is about structured TripAdvisor provider data;
- generic scraping/search increases tool ambiguity;
- the current specialist/search split is cleaner.

## Risks

### State bloat

Risk:

- `places_by_id` grows too large if every search candidate is persisted.

Mitigation:

- persist only hydrated places or explicitly selected places;
- keep records compact;
- avoid storing full review arrays.

### Source noise

Risk:

- competitor reviews produce more provider source pills.

Mitigation:

- dedupe by URL;
- title pills with provider and place name;
- rely on existing source-count hiding for sparse answers;
- add UI grouping later only if needed.

### Backward compatibility

Risk:

- existing sessions lack the registry.

Mitigation:

- lazy-bootstrap from `_target_*` and `places_context`;
- keep old keys while new registry rolls out;
- tests for both old and new state.

### Provider identity mismatch

Risk:

- TripAdvisor top result may not be the same restaurant.

Mitigation:

- keep coordinate verification;
- verify against the requested Google place's coordinates;
- return `unverified` without rich fields on mismatch.

### Prompt/tool ambiguity

Risk:

- model calls review tools before resolving a place.

Mitigation:

- prefer wrapper tools that anchor on Google Place ID;
- update `review_analyst` instructions;
- add tests and eval prompts for competitor/new-place review lookup.

## Acceptance Criteria

The refactor is successful when:

1. A follow-up can ask for Google Maps profile data for any named known competitor.
2. A follow-up can ask for Google Reviews for any Google Place ID or resolved restaurant.
3. A follow-up can ask for TripAdvisor profile/reviews for a competitor and verification uses that competitor's coordinates.
4. The original target remains unchanged after competitor/new-place lookups.
5. Sources appear for provider data used in the answer, including competitor/new-place sources.
6. Future follow-ups can see compact identity metadata for places resolved in earlier follow-ups.
7. Broad new market reports are still redirected to a new session instead of jammed into continuation.
8. Existing sessions without `places_by_id` still work.

## Suggested Test Matrix

### Unit tests

- `test_places_tools.py`
  - first target creates `original_target_place_id`;
  - target details populate `places_by_id`;
  - competitor details populate `places_by_id` without overwriting target;
  - batch details registers multiple places;
  - source pill emitted for non-target place.

- `test_apify_tools.py`
  - Google Reviews source emitted for competitor;
  - known place name used in source title;
  - full review payload not persisted in state;
  - max review cap remains.

- `test_tripadvisor_tools.py`
  - competitor TripAdvisor verification uses competitor coords;
  - mismatch returns `unverified` and strips rich fields;
  - source emitted for verified competitor;
  - fallback works for old `_target_*` sessions;
  - pagination remains correct.

- `test_instruction_providers.py`
  - review analyst prompt is place-scoped;
  - continuation prompt permits bounded structured provider lookup;
  - AUTHORING state keys stay accurate.

- `test_agent_config.py`
  - review analyst has the intended structured tools;
  - continuation has the intended direct place tools and helper access.

### Behavioral evals

Add or update live/recorded eval prompts:

- "Check Google reviews for Competitor A from the report."
- "What does TripAdvisor say about [competitor]?"
- "Pull Maps profile for [new restaurant] in [city]."
- "Compare recent Google Reviews for [target] and [competitor]."
- "Do a full new benchmark for a different city." Expected behavior: suggest new session.

### Manual smoke tests

Use one session with:

1. initial target and competitor report;
2. follow-up asking for a competitor's Maps profile;
3. follow-up asking for same competitor's Google Reviews;
4. follow-up asking for same competitor's TripAdvisor reviews;
5. follow-up asking about a new unrelated restaurant.

Verify:

- activity stream shows provider work;
- sources attach to the correct place;
- original target remains available;
- final answer does not expose internal tool/agent labels.

## Rollout Plan

1. Implement state helpers and update Places tools.
2. Update Google Reviews source attribution.
3. Update TripAdvisor verification.
4. Update review analyst prompt and tests.
5. Update continuation prompt and tests.
6. Run full agent tests.
7. Deploy Agent Engine.
8. Run smoke sessions and inspect Firestore session state/events.

Recommended command set before deploy:

```bash
cd agent && PYTHONPATH=. .venv/bin/pytest tests/ -q
npm run test
npm run check
npm run lint
```

Deploy path:

- push to `main` for Firebase Hosting, Functions, Firestore rules/indexes;
- redeploy Agent Engine with `cd agent && .venv/bin/python scripts/redeploy_engine.py --yes`;
- verify with `cd agent && .venv/bin/python scripts/redeploy_engine.py --check --skip-pickle-check`.

## Open Questions

1. Should `review_analyst` be allowed to resolve place names itself, or should `continue_research` always resolve to Google Place IDs before delegating?
   - Recommendation: `continue_research` resolves when the user names a place; `review_analyst` works from explicit Place IDs. Add review analyst profile hydration only for supplied IDs.

2. Should `places_by_id` store compact review summaries?
   - Recommendation: only store fetch metadata at first. Let continuation notes carry user-facing follow-up findings.

3. Should source pills include place names?
   - Recommendation: yes. Provider-only pills become ambiguous once multiple places can be reviewed in one turn.

4. Should `_target_*` keys be removed?
   - Recommendation: no immediate removal. Keep them for compatibility and current geo-bias behavior. Revisit after place registry is stable.

5. Should first-turn `places_context` be replaced by structured state?
   - Recommendation: no. Keep prose `places_context` for prompts/report writing. Add structured state as the reliable provider-data layer.

## Final Recommendation

Proceed with the broader place-scoped refactor.

The central design rule should be:

> Every structured provider operation must be anchored to an explicit Google Place ID. The original target is immutable context, not a mutable global pointer.

This solves the follow-up requirement without turning continuation into a full new research pipeline and without adding fragile target-swapping logic.
