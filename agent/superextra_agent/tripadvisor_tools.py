import atexit
import math
import os
import re
import uuid

import httpx

BASE_URL = "https://serpapi.com/search.json"

# Max distance (meters) between Google Places and TripAdvisor coordinates for
# us to accept them as the same venue. Observed drift on verified matches is
# <30m (Geranium 25.5m, Umami 21.9m); 150m gives ~5× margin while still
# cleanly separating "different venue in the same neighborhood" (Bar Leon vs
# Hola Tapas measured 508m). Revisit if E2E calibration shows matches
# creeping past ~100m.
_COORD_MATCH_RADIUS_M = 150.0

_COORD_RE = re.compile(r"@([-\d.]+),([-\d.]+)")

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


def _extract_coords_from_address_link(address_link: str) -> tuple[float, float] | None:
    """Pull `(lat, lng)` out of TripAdvisor's Google Maps URL.

    SerpAPI's `tripadvisor_place` response embeds the venue's coordinates in
    `address_link` as the `@lat,lng` suffix of a Google Maps URL. This is
    the only reliable coordinate signal the TripAdvisor engine exposes.
    """
    if not address_link:
        return None
    m = _COORD_RE.search(address_link)
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two lat/lng points, in meters."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000.0 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


async def find_tripadvisor_restaurant(
    name: str,
    area: str,
    google_place_id: str,
    tool_context=None,
) -> dict:
    """Find a restaurant on TripAdvisor and return its full profile.

    Searches TripAdvisor (eateries only, biased toward the target's coords
    when available), fetches the top candidate's detail page, and verifies
    identity by comparing TripAdvisor's coordinates against the target's
    Google Places coordinates. Two SerpAPI calls per invocation.

    Three return statuses:
      - `success` — coord check passed (≤ 150 m). Full payload: rating,
        ranking, cuisines, tripadvisor_link, sample_reviews, etc.
      - `unverified` — search ran; top candidate's coords didn't match the
        target. No rich fields, no link. The LLM should skip TripAdvisor for
        this target, not retry.
      - `error` — SerpAPI transport failure or response parse error.

    Args:
        name: Restaurant name (e.g. 'Umami P-Berg').
        area: City or neighborhood for search context (e.g. 'Prenzlauer Berg Berlin').
        google_place_id: REQUIRED. The Google Place ID of the restaurant being
            looked up, copied from the Places context (e.g.
            'ChIJN1t_tDeuEmsRUsoyG83frY4'). Used only for source-pill
            attribution — TripAdvisor never sees it.
    """
    try:
        client = _get_client()
        api_key = _get_api_key()

        # Step 1: search. `ssrc=r` filters to eateries (otherwise the response
        # is polluted with hotels and attractions). `lat`/`lon` biases the
        # ranking toward the target's location when we have it — verified
        # empirically to shift candidate[1+] toward local venues. Keep the
        # query lean: `f"{name} {area}"` — appending street addresses hurts
        # TripAdvisor's fuzzy search, not helps it (tested).
        search_params = {
            "engine": "tripadvisor",
            "q": f"{name} {area}",
            "ssrc": "r",
            "api_key": api_key,
        }
        target_lat = tool_context.state.get("_target_lat") if tool_context else None
        target_lng = tool_context.state.get("_target_lng") if tool_context else None
        if target_lat and target_lng:
            search_params["lat"] = str(target_lat)
            search_params["lon"] = str(target_lng)

        search_resp = await client.get(BASE_URL, params=search_params)
        if search_resp.status_code != 200:
            return {
                "status": "error",
                "error_message": f"SerpAPI search error {search_resp.status_code}: {search_resp.text}",
            }

        places = search_resp.json().get("places", [])
        if not places:
            return {
                "status": "unverified",
                "error_message": f"No TripAdvisor results for '{name} {area}'",
            }

        top = places[0]
        ta_place_id = top.get("place_id")
        if not ta_place_id:
            return {
                "status": "unverified",
                "error_message": "Top TripAdvisor candidate has no place_id",
            }

        # Step 2: fetch detail for candidate[0].
        place_resp = await client.get(BASE_URL, params={
            "engine": "tripadvisor_place",
            "place_id": ta_place_id,
            "api_key": api_key,
        })
        if place_resp.status_code != 200:
            return {
                "status": "error",
                "error_message": f"SerpAPI place error {place_resp.status_code}: {place_resp.text}",
            }

        place_data = place_resp.json().get("place_result", {})

        # Identity check: compare TripAdvisor's coordinates against the
        # target's Google Places coordinates. TripAdvisor embeds its lat/lng
        # in the address_link as `@lat,lng`. If the target coords aren't in
        # state (degraded run) or the address_link doesn't parse, default to
        # unverified — can't prove identity, don't accept.
        ta_coords = _extract_coords_from_address_link(place_data.get("address_link", ""))
        if not (target_lat and target_lng and ta_coords):
            return {
                "status": "unverified",
                "error_message": "Could not verify TripAdvisor match (missing coordinates)",
            }
        distance_m = _haversine_meters((float(target_lat), float(target_lng)), ta_coords)
        if distance_m > _COORD_MATCH_RADIUS_M:
            return {
                "status": "unverified",
                "error_message": (
                    f"TripAdvisor top candidate is {distance_m:.0f}m from the target — "
                    f"treating as a different venue"
                ),
            }

        # Verified match. Build the rich payload.
        selected_link = top.get("link")

        nearby = []
        for r in place_data.get("nearby", {}).get("restaurants", []):
            nearby.append({
                "name": r.get("name"),
                "place_id": r.get("place_id"),
                "rating": r.get("rating"),
                "reviews": r.get("reviews"),
                "distance_km": round(r.get("distance", 0), 2),
            })

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

        # Pill write. `google_place_id == _target_place_id` gate is unchanged;
        # TripAdvisor's API doesn't speak Google IDs, so this arg is purely
        # local gating metadata.
        if (
            tool_context
            and selected_link
            and google_place_id
            and tool_context.state.get("_target_place_id") == google_place_id
        ):
            tool_context.state[f"_tool_src_{uuid.uuid4().hex}"] = {
                "provider": "tripadvisor",
                "title": "TripAdvisor",
                "url": selected_link,
                "domain": "tripadvisor.com",
            }

        return {
            "status": "success",
            "place_id": ta_place_id,
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
