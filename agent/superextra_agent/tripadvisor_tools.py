import atexit
import os
import re
import uuid

import httpx

BASE_URL = "https://serpapi.com/search.json"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


def _cleanup_client():
    global _client
    if _client is not None:
        try:
            import asyncio
            asyncio.run(_client.aclose())
        except RuntimeError:
            pass
        _client = None


atexit.register(_cleanup_client)


def _get_api_key() -> str:
    key = os.environ.get("SERPAPI_API_KEY", "")
    if not key:
        raise RuntimeError("SERPAPI_API_KEY environment variable is not set")
    return key


def _normalize_address(addr: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for address comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", addr.lower())).strip()


def _address_match_score(a: str, b: str) -> float:
    """Simple word-overlap score between two normalized addresses (0.0–1.0)."""
    if not a or not b:
        return 0.0
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    return len(overlap) / min(len(words_a), len(words_b))


async def find_tripadvisor_restaurant(name: str, area: str, address: str = "", tool_context=None) -> dict:
    """Find a restaurant on TripAdvisor and return its full profile.

    Searches TripAdvisor for the restaurant, then fetches detailed place data
    including ranking, cuisines, dining options, nearby restaurants, and sample
    reviews. Returns up to 3 search candidates so you can verify the match.
    Costs 2 SerpAPI calls.

    Returns `status: "low_confidence"` (not "success") when the address-match
    score is below 0.4 — the selected candidate may be the wrong place. The
    caller should inspect `candidates` and decide whether to retry with a more
    specific query.

    Args:
        name: Restaurant name (e.g. 'Umami P-Berg').
        area: City or neighborhood for search context (e.g. 'Prenzlauer Berg Berlin').
        address: Optional full street address from Google Places for matching confidence.
    """
    try:
        client = _get_client()
        api_key = _get_api_key()

        # Step 1: Search for the restaurant. When the caller provides an
        # address, include it in the query — SerpAPI's relevance ranking then
        # has the disambiguating signal it needs to put the right place first,
        # rather than us picking candidate 0 blindly and relying purely on the
        # post-selection confidence check to catch wrong matches.
        search_q = f"{name} {address}" if address else f"{name} {area}"
        search_resp = await client.get(BASE_URL, params={
            "engine": "tripadvisor",
            "q": search_q,
            "api_key": api_key,
        })
        if search_resp.status_code != 200:
            return {"status": "error", "error_message": f"SerpAPI search error {search_resp.status_code}: {search_resp.text}"}

        search_data = search_resp.json()
        places = search_data.get("places", [])
        if not places:
            return {"status": "error", "error_message": f"No TripAdvisor results found for '{name} {area}'"}

        # Build candidate list from top 3 results. `link` is preserved so
        # the downstream source-accumulator (B2) can cite the TripAdvisor
        # page URL without a second API call.
        candidates = []
        for p in places[:3]:
            candidates.append({
                "title": p.get("title"),
                "place_id": p.get("place_id"),
                "rating": p.get("rating"),
                "reviews": p.get("reviews"),
                "location": p.get("location"),
                "link": p.get("link"),
            })

        # Default to first result
        selected_index = 0
        match = candidates[selected_index]
        place_id = match.get("place_id")
        if not place_id:
            return {"status": "error", "error_message": "Selected search result has no place_id"}

        # Step 2: Get full place details for selected match
        place_resp = await client.get(BASE_URL, params={
            "engine": "tripadvisor_place",
            "place_id": place_id,
            "api_key": api_key,
        })
        if place_resp.status_code != 200:
            return {"status": "error", "error_message": f"SerpAPI place error {place_resp.status_code}: {place_resp.text}"}

        place_data = place_resp.json().get("place_result", {})

        # Determine match confidence using the detailed address
        ta_address = place_data.get("address", "")
        if address and ta_address:
            score = _address_match_score(
                _normalize_address(address), _normalize_address(ta_address)
            )
            match_confidence = "high" if score >= 0.4 else "low"
        elif len(candidates) == 1:
            match_confidence = "high"
        else:
            match_confidence = "low"

        # Extract nearby restaurants (compact)
        nearby = []
        for r in place_data.get("nearby", {}).get("restaurants", []):
            nearby.append({
                "name": r.get("name"),
                "place_id": r.get("place_id"),
                "rating": r.get("rating"),
                "reviews": r.get("reviews"),
                "distance_km": round(r.get("distance", 0), 2),
            })

        # Extract sample reviews (compact)
        sample_reviews = []
        for r in place_data.get("reviews_list", []):
            review = {
                "title": r.get("title"),
                "text": r.get("snippet"),
                "rating": r.get("rating"),
                "date": r.get("date"),
            }
            author = r.get("author", {})
            if author.get("hometown"):
                review["author_hometown"] = author["hometown"]
            sample_reviews.append(review)

        # Attach a provider source on high-confidence matches. Writes a
        # UNIQUE state key per tool call (`_tool_src_<uuid>`) so that when
        # ADK batches multiple parallel tool calls into one event's
        # state_delta, all of the writes survive as distinct keys rather
        # than overwriting each other. See apify_tools.get_google_reviews
        # for the same pattern and its reasoning.
        selected_link = match.get("link")
        if tool_context and match_confidence == "high" and selected_link:
            tool_context.state[f"_tool_src_{uuid.uuid4().hex}"] = {
                "title": f"TripAdvisor — {place_data.get('name') or match.get('title') or 'restaurant page'}",
                "url": selected_link,
                "domain": "tripadvisor.com",
            }

        return {
            "status": "success" if match_confidence == "high" else "low_confidence",
            "candidates": candidates,
            "selected_index": selected_index,
            "match_confidence": match_confidence,
            "place_id": place_id,
            "name": place_data.get("name"),
            "rating": place_data.get("rating"),
            "num_reviews": place_data.get("reviews"),
            "ranking": place_data.get("ranking"),
            "is_claimed": place_data.get("is_claimed"),
            "cuisines": place_data.get("cuisines", []),
            "diets": place_data.get("diets", []),
            "meal_types": place_data.get("meal_types", []),
            "dining_options": place_data.get("dining_options", []),
            "price_level": next(
                (c.get("name") for c in place_data.get("categories", [])
                 if c.get("name", "").startswith(("$", "€", "£", "Mid", "Fine", "Cheap"))),
                None,
            ),
            "address": place_data.get("address"),
            "phone": place_data.get("phone"),
            "email": place_data.get("email"),
            "website": place_data.get("website"),
            "menu_link": place_data.get("menu", {}).get("link") if place_data.get("menu") else None,
            "tripadvisor_link": selected_link,
            "nearby_restaurants": nearby,
            "sample_reviews": sample_reviews,
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


async def get_tripadvisor_reviews(place_id: str, num_pages: int = 5) -> dict:
    """Fetch TripAdvisor reviews for a restaurant. Returns full review text,
    ratings, trip types, reviewer origins, and owner responses.

    Each page returns 10 reviews. Default is 5 pages (50 reviews).
    Use the place_id from find_tripadvisor_restaurant.

    Args:
        place_id: TripAdvisor place ID (e.g. '6796040').
        num_pages: Number of pages to fetch (10 reviews each). Default 5, max 10.
    """
    try:
        client = _get_client()
        api_key = _get_api_key()
        num_pages = min(num_pages, 10)

        all_reviews = []
        total_reviews = None
        partial = False

        for page in range(num_pages):
            resp = await client.get(BASE_URL, params={
                "engine": "tripadvisor_reviews",
                "place_id": place_id,
                "offset": page * 10,
                "api_key": api_key,
            })
            if resp.status_code != 200:
                if page == 0:
                    return {"status": "error", "error_message": f"SerpAPI reviews error {resp.status_code}: {resp.text}"}
                partial = True
                break  # Return what we have if a later page fails

            data = resp.json()
            if total_reviews is None:
                total_reviews = data.get("search_information", {}).get("total_reviews")

            reviews = data.get("reviews", [])
            if not reviews:
                break  # No more reviews

            for r in reviews:
                review = {
                    "title": r.get("title"),
                    "text": r.get("snippet"),
                    "rating": r.get("rating"),
                    "date": r.get("date"),
                    "original_language": r.get("original_language"),
                }
                trip_info = r.get("trip_info", {})
                if trip_info:
                    review["trip_type"] = trip_info.get("type")
                    review["travel_date"] = trip_info.get("date")
                author = r.get("author", {})
                if author.get("hometown"):
                    review["author_hometown"] = author["hometown"]
                review["votes"] = r.get("votes", 0)
                review["has_owner_response"] = "response" in r
                all_reviews.append(review)

        if total_reviews and len(all_reviews) < total_reviews:
            partial = True

        # Source attribution for TripAdvisor is handled at the
        # `find_tripadvisor_restaurant` boundary (which has the URL). This
        # tool only fetches additional pages; the final `sources[]` already
        # carries the TripAdvisor entry.

        return {
            "status": "success",
            "place_id": place_id,
            "total_reviews": total_reviews,
            "fetched_reviews": len(all_reviews),
            "partial": partial,
            "reviews": all_reviews,
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
