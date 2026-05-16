# Tool integrations — wiring plan

**Date**: 2026-05-14
**Status**: design, not implementation

Plans for wiring four new tools into the agent. Test outcomes for `google_maps_photos` and the bigger `compass/crawler-google-places` test will land in a follow-up section.

Engineering principles (apply to every change): optimize for the end state of the codebase, not diff size. Find root causes, prefer the smallest reliable core, delete dead paths, reject speculative guards/retries/fallbacks. Verify against docs and the codebase. State only facts.

---

## 1. `google_trends` — wire into market_landscape + marketing_brand

### Where it lives

New module `agent/superextra_agent/trends_tools.py`. Pattern after `tripadvisor_tools.py` (SerpAPI client + httpx + secrets module).

### Function shape

```python
async def get_search_trends(
    queries: list[str],
    geo: str,
    date_range: str = "today 12-m",
    tool_context=None,
) -> dict:
    """Fetch Google Trends interest-over-time for up to 5 search queries in a region.

    Returns a timeseries (one number per week, 0-100 scale) for each query.
    100 = peak interest in that window; values are RELATIVE, not absolute volumes.

    Use for demand-side signals: which cuisines, dishes, or formats are
    trending up or down in a market. Do NOT use for small-venue brand
    tracking — single-venue brand queries return noise.

    Args:
        queries: 1-5 search terms (e.g. ["ramen", "pho", "udon"]).
        geo: ISO 3166-2 region code (e.g. "DE-BE" for Berlin,
             "PL-PM" for Pomeranian voivodeship, "US-NY" for New York state,
             "GB-LND" for London). Use country code alone ("DE", "PL") for
             national signal.
        date_range: SerpAPI date string. "today 12-m" (12 months),
                    "today 5-y" (5 years), "now 7-d", or custom
                    "YYYY-MM-DD YYYY-MM-DD".
    """
```

Returns a typed dict: `{"status": "success", "queries": [...], "geo": "...", "timeseries": [{"date": "2025-05", "values": {"ramen": 67, "pho": 42, ...}}, ...]}`.

### Wiring

Add to `_SPECIALIST_TOOLS` in `specialists.py:194`:

```python
"market_landscape": [get_search_trends, ...],
"marketing_brand": [get_search_trends, ...],
```

Other specialists do not get this tool — they don't have demand-trend use cases that aren't covered by their existing search affordance, and tool ambiguity per the literature is a top failure mode.

### Instruction additions

In `instructions/market_landscape.md`, under **Evidence To Seek**, add one line:

> Google Trends interest-over-time for cuisines, dishes, formats, and category terms when demand-shift is the question (not for small-venue brand names).

In `instructions/marketing_brand.md`, under **Evidence To Seek**:

> Google Trends search-interest comparison for established brand names against competitors (skip for venues with <100k reviews / unknown brand recognition).

### Cost + gates

SerpAPI flat per-call pricing. ~$0.005–0.015 per query depending on tier. No volume gates needed.

Code-level gate: refuse to run on queries where `len(query) < 4` (too short, garbage) or where all queries are venue-name-shaped strings — heuristic check, just log a warning. Not a hard block.

### What we delete

Nothing yet — this is additive.

### Open question

Whether subregional geo codes work uniformly across all markets. Verified for `DE-BE` and `PL-PM` in the prior smoke test. Verify on first calls per market.

---

## 2. Maps Grounding + Places — both, model decides

### What's special about Maps Grounding

Unlike Python-function tools (`find_nearby_restaurants`), Maps Grounding is a Gemini-native `Tool` declared in `GenerateContentConfig`. Same shape as `google_search` is wired today in `specialists.py:176`.

The grounding tool returns answers + `grounding_chunks` (place IDs + maps URIs) + `grounding_supports` (text-span-to-chunk mapping). It is a retrieval tool the model invokes implicitly during generation, not a function it calls explicitly.

### Where to wire

In `agent/superextra_agent/specialists.py`, modify `_make_specialist()` to accept a flag for which "model-level" tools to enable. Today the function adds `google_search` to every specialist via the default `tools` list. Add a sibling flag for Maps Grounding.

Concrete change — extend `_make_specialist()`:

```python
def _make_specialist(
    name,
    description,
    output_key=None,
    tools=None,
    instruction_name=None,
    thinking_config=None,
    enable_maps_grounding=False,   # NEW
):
    model_tools = tools or [google_search, fetch_web_content, fetch_web_content_batch]
    if enable_maps_grounding:
        model_tools = list(model_tools) + [
            types.Tool(google_maps=types.GoogleMaps(enable_widget=False))
        ]
    # rest unchanged...
```

The `_inject_geo_bias` callback already sets `RetrievalConfig.lat_lng` which is used by BOTH `google_search` and `google_maps`. No new bias plumbing needed.

### Which specialists get it

Three with the strongest "what's near here / who competes here" use case:

- `context_enricher` — uses it to pre-build the trade-area snapshot
- `market_landscape` — competitor discovery
- `location_traffic` — trade-area quality signals

Others (revenue_sales, operations, menu_pricing, etc.) stay on `google_search` only — they don't need geographic POI grounding and adding another retrieval tool to a specialist increases tool-selection ambiguity (recent literature: arXiv:2505.18135).

### Both Places nearby AND Maps Grounding

The user's pushback was right — keep both, let the model decide.

Specialist instructions need to say so explicitly. In `instructions/market_landscape.md` and `instructions/location_traffic.md`, add a "Tool guidance" section:

> - Use `find_nearby_restaurants(lat, lng, radius)` for **deterministic enumeration**: "list all restaurants within 500m," competitor census, density counts.
> - Use Google Maps grounding for **curated answers**: "best seafood competitors of X," "highly-rated places nearby in cuisine Y." May pull places beyond the strict radius.
> - When you need both, call Places nearby first; refine with Maps grounding if the census misses an obvious named competitor.

### Coverage check

`grounding_metadata.grounding_chunks` returns place IDs but only `title` + `uri`. For numeric fields (rating, review count, price level), the model has to re-call Places details for each cited place ID. This is fine — the Firestore cache (planned separately) makes that effectively free on cache hits.

### Cost

Maps Grounding: $25 / 1,000 grounded prompts at the standard tier (5,000/day cap on Gemini 3 Pro). Cheaper than Search grounding ($35/1k). Real cost driver is model tokens (13k total tokens on a Monsun call in the smoke test).

### What we delete

Nothing. Both stay.

### Open question

Whether the model picks correctly between the two without explicit per-question routing. The instruction guidance above is the cheapest mechanism; if it fails in practice, the fallback is to drop one of the two from the specialist's tool list rather than write a router.

---

## 3. `maxcopell/tripadvisor-reviews` — replace SerpAPI path

### What changes

`get_tripadvisor_reviews()` in `agent/superextra_agent/tripadvisor_tools.py:275-345` gets rewritten to call the Apify actor instead of the three SerpAPI engines. `find_tripadvisor_restaurant()` (search + name-match guard) stays as-is — the SerpAPI search path is more reliable than maxcopell's query mode (verified in smoke test).

### New function body

```python
async def get_tripadvisor_reviews(place_id: str, max_reviews: int = 100) -> dict:
    """Fetch TripAdvisor reviews for a restaurant. Returns full review text,
    ratings, trip types, reviewer origins, and owner responses.

    Replaces the previous SerpAPI 100-review ceiling — the Apify actor
    returns the full review corpus in one call (verified: 300 reviews,
    8 years of history in ~55s).

    Args:
        place_id: TripAdvisor place ID (e.g. '6796040').
        max_reviews: Maximum reviews to fetch. Default 100, no hard upper bound.
    """
    try:
        api_key = get_secret("APIFY_TOKEN")
        ta_url = f"https://www.tripadvisor.com/Restaurant_Review-d{place_id}-Reviews.html"
        # Apify actor accepts startUrls of any TA review page; the place_id-only
        # URL form above redirects to the canonical localized one.

        client = _get_apify_client()
        resp = await client.post(
            f"{APIFY_BASE}/acts/maxcopell~tripadvisor-reviews/run-sync-get-dataset-items",
            params={"token": api_key},
            json={
                "startUrls": [{"url": ta_url}],
                "maxReviews": max_reviews,
                "scrapeReviewerInfo": True,
            },
            timeout=120.0,
        )
        if resp.status_code not in (200, 201):
            return {"status": "error",
                    "error_message": f"Apify error {resp.status_code}: {resp.text[:500]}"}

        items = resp.json()
        # The first item carries placeInfo; subsequent items are reviews.
        # Map fields to the same shape the existing callers expect.
        reviews = [_map_review(r) for r in items]
        total_reviews = items[0].get("placeInfo", {}).get("numberOfReviews") if items else None

        return {
            "status": "success",
            "place_id": place_id,
            "total_reviews": total_reviews,
            "fetched_reviews": len(reviews),
            "reviews": reviews,
        }
    except httpx.TimeoutException:
        return {"status": "error",
                "error_message": "Apify actor timed out after 120s"}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
```

### Field map (kept identical to existing SerpAPI output shape)

| Existing field       | Apify field                                                      |
| -------------------- | ---------------------------------------------------------------- |
| `title`              | `title`                                                          |
| `text`               | `text` (was `snippet` in SerpAPI)                                |
| `rating`             | `rating`                                                         |
| `date`               | `publishedDate` (ISO format — current code stores raw, no parse) |
| `original_language`  | `lang` (single field; user confirmed lang doesn't matter)        |
| `trip_type`          | `tripType`                                                       |
| `travel_date`        | `travelDate`                                                     |
| `author_hometown`    | `user.userLocation.name`                                         |
| `votes`              | `helpfulVotes`                                                   |
| `has_owner_response` | bool(`ownerResponse`)                                            |

New fields available but not yet consumed (defer until specialist instruction updates ask for them):

- `ownerResponse` full text (currently we only store bool)
- `user.contributions.totalContributions` — reviewer trustworthiness proxy
- `publishedPlatform` — MOBILE/WEB

### What we delete

- The pagination loop in `tripadvisor_tools.py:294-313` (10-page sweep). The actor paginates internally.
- The `num_pages` parameter (replaced by `max_reviews`).
- SerpAPI's `tripadvisor_reviews` engine call entirely. Three engines in `tripadvisor_tools.py` go to two.

### What we keep

- `find_tripadvisor_restaurant()` and its name-match guard (lines 25-272). The SerpAPI search engine is empirically more reliable than maxcopell's query mode.
- `tool_source_key` provider registration for the TripAdvisor source pill (currently in `find_tripadvisor_restaurant`).
- 120s client timeout (matches the existing `_get_client()`).

### Cost

~$1.52/1k reviews observed (vs $0.90 advertised). At default 100 reviews per call: ~$0.15/place. Acceptable.

### Open question

Whether the actor accepts `startUrls` with the placeholder URL form (`...-d{place_id}-Reviews.html`) or needs the full localized canonical URL. Verified in smoke test that the Umami canonical URL worked; the placeholder form is untested. If it fails, fall back to building the URL from `tripadvisor_link` already stored in `place_state` by `find_tripadvisor_restaurant`.

---

## 4. `google_maps_photos` — wire SerpAPI as the dedicated menu-photos tool

### What changes

Add `get_menu_photos(place_id, max_photos=60)` to `agent/superextra_agent/serpapi_tools.py` (new module — same pattern as `trends_tools.py`). The SerpAPI path won the head-to-head: ~4× faster wall-clock (2–11s vs 14–40s on Apify), already in our integration surface, $0.075 per 60 photos.

### Function shape

```python
async def get_menu_photos(
    place_id: str,
    max_photos: int = 60,
    tool_context=None,
) -> dict:
    """Fetch menu-tagged photos for a restaurant from Google Maps.

    Two-call: resolves the place's hex `data_id` via Google Maps search,
    then fetches photos filtered to the menu category. Paginates up to
    3 pages (Google caps menu-tab photos at ~20-80 per place regardless
    of total uploaded).

    Use in `menu_pricing` when the operator hasn't published a digital menu —
    the agent will hand resulting photo URLs to `visual_inspect` for OCR.

    Args:
        place_id: Google Place ID (e.g. 'ChIJN1t_tDeuEmsRUsoyG83frY4').
        max_photos: Cap on photos returned. Default 60 (3 pages).
    """
```

Returns: `{"status": "success", "place_id": "...", "photos": [{"photo_id": "...", "image_url": "https://lh3.googleusercontent.com/p/...=s2000", "width": 793, "height": 1122}, ...]}`.

The `image_url` is rewritten with `=s2000` so Gemini vision gets native resolution (Google's CDN serves up-to-native, never upscales).

### Wiring

Add to `_SPECIALIST_TOOLS` in `specialists.py:194`:

```python
"menu_pricing": [get_menu_photos, ...],
```

`menu_pricing` is the only specialist with use cases here. `review_analyst` already gets photo URLs embedded in `reviewImageUrls` on individual reviews via the crawler-google-places swap.

### Instruction additions

In `instructions/menu_pricing.md`, under **Evidence To Seek**, add:

> Menu-tagged photos from Google Maps when the restaurant has no published online menu. Hand resulting `image_url` strings to `visual_inspect` (when wired) for OCR. Photos are capped by Google at ~20–80 per place — don't promise comprehensive menus for tiny independents.

### What we delete

Nothing — additive.

### Decided from the bigger-crawler test (2026-05-14)

`compass/crawler-google-places` returns a **flat, uncategorized** `imageUrls` array — `imageCategories` is just the list of tab names Google has, not per-photo tags. Apify product docs explicitly confirm there's no way to filter image scraping by category.

So **menu photos always go through SerpAPI `get_menu_photos`** — the dedicated tool above is the only path. The crawler's `maxImages` opt-in stays low (default 20) for generic hero photos when convenient; it's not the menu source.

### Open questions

- **Ceiling realism**. Monsun has only 21 menu photos available across both paths; Umami ~60–80. Independents with low review counts will return <10. Specialist needs to gracefully say "menu photos unavailable" when count is too low.
- **Owner-uploaded vs user-uploaded** — SerpAPI doesn't expose this flag. Apify does (`uploadedByOwner`). If menu OCR quality turns out to depend strongly on whether the operator posted the photo themselves, we'd reconsider the path choice. Verify after the first round of `visual_inspect` runs.
- **Caching TTL**. Menu photos change rarely (operators don't reupload often). 30-day cache TTL is appropriate when the Firestore cache layer ships.

---

## Sequencing

If implementing in one sweep:

1. New `trends_tools.py` (google_trends) — additive, no risk.
2. `tripadvisor_tools.py` rewrite of `get_tripadvisor_reviews` — replacement, single function.
3. `specialists.py` `_make_specialist` extension for Maps Grounding flag — single function signature change.
4. Three specialist instruction files: `market_landscape.md`, `marketing_brand.md`, `location_traffic.md` — small edits per file.
5. `google_maps_photos` wiring — after test result.

Each step is independently shippable.

### Verification at each step

- After step 1: run a specialist that hits `market_landscape` against a Berlin question that's clearly cuisine-trend-shaped; confirm trends gets called.
- After step 2: run `review_analyst` against Umami P-Berg, confirm >100 reviews come back.
- After step 3: run `location_traffic` against Monsun and check the model invokes Maps grounding at least once.
- After step 4: same prompts, watch for the model's reasoning showing it consulted the right tool per the new guidance.
