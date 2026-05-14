import math
import re
import unicodedata

import httpx

from .place_state import (
    get_place_coords,
    get_place_name,
    get_place_record,
    source_title,
    tool_source_key,
    upsert_tripadvisor_match,
)
from .secrets import get_secret

BASE_URL = "https://serpapi.com/search.json"

# 5km veto on chain-branch / wrong-city matches that pass the name check.
_COORD_SANITY_RADIUS_M = 5000.0

_COORD_RE = re.compile(r"@([-\d.]+),([-\d.]+)")


def _normalize_name(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _names_align(a: str | None, b: str | None) -> bool:
    """One name's normalized form contains the other (substring)."""
    a, b = _normalize_name(a), _normalize_name(b)
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return short in long_


_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


def _get_api_key() -> str:
    return get_secret("SERPAPI_API_KEY")


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

    Searches TripAdvisor (eateries only, biased toward the requested Google
    place's coords), fetches the top candidate's detail page, and verifies
    identity by name match (with a loose 5km coord-distance veto on obvious
    wrong-city / wrong-branch matches). Two SerpAPI calls per verified
    profile.

    Three return statuses:
      - `success` — name match passed. Full payload: rating, ranking,
        cuisines, tripadvisor_link, sample_reviews, etc.
      - `unverified` — search ran; top candidate's name didn't match the
        Google place (or coord drift exceeded the sanity radius). No rich
        fields, no link. The LLM should skip TripAdvisor for this place,
        not retry.
      - `error` — SerpAPI transport failure or response parse error.

    Args:
        name: Restaurant name (e.g. 'Umami P-Berg').
        area: City or neighborhood for search context (e.g. 'Prenzlauer Berg Berlin').
        google_place_id: REQUIRED. The Google Place ID of the restaurant being
            looked up, copied from the Places context (e.g.
            'ChIJN1t_tDeuEmsRUsoyG83frY4'). This is the local identity
            anchor; TripAdvisor never sees it.
    """
    try:
        state = tool_context.state if tool_context else {}

        if not google_place_id:
            return {
                "status": "unverified",
                "error_message": "Google Place ID is required for TripAdvisor verification",
            }

        coords = get_place_coords(state, google_place_id)
        if not coords:
            return {
                "status": "unverified",
                "error_message": "Google place profile coordinates required for TripAdvisor verification",
            }

        record = get_place_record(state, google_place_id) or {}
        search_name = (name or get_place_name(state, google_place_id) or "").strip()
        search_area = (area or str(record.get("formatted_address") or "")).strip()
        query = f"{search_name} {search_area}".strip()
        if not search_name:
            return {
                "status": "unverified",
                "error_message": "Google place profile name required for TripAdvisor search",
            }

        client = _get_client()
        api_key = _get_api_key()

        # Step 1: search. `ssrc=r` filters to eateries (otherwise the response
        # is polluted with hotels and attractions). `lat`/`lon` biases the
        # ranking toward the requested Google place.
        search_params = {
            "engine": "tripadvisor",
            "q": query,
            "ssrc": "r",
            "lat": str(coords[0]),
            "lon": str(coords[1]),
            "api_key": api_key,
        }

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
                "error_message": f"No TripAdvisor results for '{query}'",
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

        # Identity check: name match is the primary signal. SerpAPI's
        # `address_link` coord is geocoded from the address string and drifts
        # hundreds of meters even for the right venue, so it's only a veto on
        # obvious wrong-city / wrong-branch matches.
        ta_name = place_data.get("name")
        if not _names_align(search_name, ta_name):
            return {
                "status": "unverified",
                "error_message": (
                    f"TripAdvisor top candidate '{ta_name}' does not match "
                    f"the Google place name"
                ),
            }
        coord_match = _COORD_RE.search(place_data.get("address_link", ""))
        ta_coords = (float(coord_match[1]), float(coord_match[2])) if coord_match else None
        if ta_coords and _haversine_meters(coords, ta_coords) > _COORD_SANITY_RADIUS_M:
            return {
                "status": "unverified",
                "error_message": (
                    f"TripAdvisor candidate '{ta_name}' is too far from "
                    f"the Google place — likely a different venue"
                ),
            }

        # Verified match. Build the rich payload.
        selected_link = top.get("link")

        nearby = [
            {
                "name": r.get("name"),
                "place_id": r.get("place_id"),
                "rating": r.get("rating"),
                "reviews": r.get("reviews"),
                "distance_km": round(r.get("distance", 0), 2),
            }
            for r in place_data.get("nearby", {}).get("restaurants", [])
        ]

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

        if tool_context and selected_link:
            upsert_tripadvisor_match(
                tool_context.state,
                google_place_id,
                {
                    "place_id": ta_place_id,
                    "url": selected_link,
                    "name": place_data.get("name"),
                    "verified": True,
                },
            )
            tool_context.state[tool_source_key("tripadvisor", google_place_id)] = {
                "provider": "tripadvisor",
                "title": source_title(tool_context.state, google_place_id, "TripAdvisor"),
                "url": selected_link,
                "domain": "tripadvisor.com",
                "place_id": google_place_id,
            }

        return {
            "status": "success",
            "google_place_id": google_place_id,
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

        # The TripAdvisor source pill is written by find_tripadvisor_restaurant
        # on verified matches. This tool only fetches additional review pages
        # for an already-resolved place_id.

        return {
            "status": "success",
            "place_id": place_id,
            "total_reviews": total_reviews,
            "fetched_reviews": len(all_reviews),
            "reviews": all_reviews,
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
