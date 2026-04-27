import atexit
import asyncio
import logging
import os
import uuid
import httpx

from .secrets import get_secret

logger = logging.getLogger(__name__)

BASE_URL = "https://places.googleapis.com/v1"

# Search results: lighter fields for nearby/text search
SEARCH_FIELDS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.types",
    "places.primaryType",
    "places.businessStatus",
    "places.googleMapsUri",
])

# Detail view: full fields including reviews, hours, service modes
DETAIL_FIELDS = ",".join([
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "rating",
    "userRatingCount",
    "priceLevel",
    "types",
    "primaryType",
    "businessStatus",
    "googleMapsUri",
    "reviews",
    "reviewSummary",
    "regularOpeningHours",
    "editorialSummary",
    "dineIn",
    "delivery",
    "takeout",
    "websiteUri",
    "nationalPhoneNumber",
    "servesBreakfast",
    "servesLunch",
    "servesDinner",
    "outdoorSeating",
])

# Warn early if API key is missing (actual RuntimeError raised on first call)
if not os.environ.get("GOOGLE_PLACES_API_KEY"):
    logger.warning("GOOGLE_PLACES_API_KEY not set — Places API calls will fail")

# Lazy-initialized client and API key
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


def _cleanup_client():
    global _client
    if _client is not None:
        try:
            asyncio.run(_client.aclose())
        except RuntimeError:
            pass
        _client = None


atexit.register(_cleanup_client)


def _get_api_key() -> str:
    return get_secret("GOOGLE_PLACES_API_KEY")


async def get_restaurant_details(place_id: str, tool_context=None) -> dict:
    """Get the full Google Places profile of a restaurant including reviews,
    hours, and service modes.

    Args:
        place_id: The Google Places ID (e.g. 'ChIJN1t_tDeuEmsRUsoyG83frY4').
                  Found in the [Context: ...] prefix of the user's message.
    """
    try:
        client = _get_client()
        resp = await client.get(
            f"{BASE_URL}/places/{place_id}",
            headers={
                "X-Goog-Api-Key": _get_api_key(),
                "X-Goog-FieldMask": DETAIL_FIELDS,
            },
        )
        if resp.status_code != 200:
            return {"status": "error", "error_message": f"Places API error {resp.status_code}: {resp.text}"}
        place = resp.json()
        if not isinstance(place, dict):
            return {"status": "error", "error_message": "Unexpected response format from Places API"}
        # Stash per-place metadata so downstream tools (esp. apify_tools.
        # get_google_reviews) can cite the right restaurant without extra API
        # calls. `_place_name_<pid>` is per-place and written every call —
        # batch competitor fetches need to populate it too. `_target_place_id`
        # is set on the first Places call (the enricher's target fetch by
        # convention) and independent of whether location came back, so target
        # identity survives a location-less response. `_target_lat`/`_target_lng`
        # and the Google Maps source pill are gated on the current call being
        # the target — without that gate, a later competitor batch could
        # silently overwrite missing target coords with the competitor's, and
        # downstream geo-bias / TripAdvisor verification would point at the
        # wrong venue.
        if tool_context:
            if "_target_place_id" not in tool_context.state:
                tool_context.state["_target_place_id"] = place_id

            name = (place.get("displayName") or {}).get("text")
            if name:
                tool_context.state[f"_place_name_{place_id}"] = name

            if tool_context.state.get("_target_place_id") == place_id:
                loc = place.get("location", {})
                if (
                    loc.get("latitude") and loc.get("longitude")
                    and "_target_lat" not in tool_context.state
                ):
                    tool_context.state["_target_lat"] = loc["latitude"]
                    tool_context.state["_target_lng"] = loc["longitude"]

                maps_uri = place.get("googleMapsUri")
                if maps_uri:
                    tool_context.state[f"_tool_src_{uuid.uuid4().hex}"] = {
                        "provider": "google_maps",
                        "title": "Google Maps",
                        "url": maps_uri,
                        "domain": "google.com",
                    }
        return {"status": "success", "place": place}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


async def find_nearby_restaurants(latitude: float, longitude: float, radius: float = 1000.0) -> dict:
    """Find restaurants near a location. Returns up to 20 results ranked by distance.

    Args:
        latitude: Center latitude of search area.
        longitude: Center longitude of search area.
        radius: Search radius in meters (default 1000, max 50000).
    """
    try:
        client = _get_client()
        resp = await client.post(
            f"{BASE_URL}/places:searchNearby",
            json={
                "includedTypes": ["restaurant"],
                "maxResultCount": 20,
                "rankPreference": "DISTANCE",
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": latitude, "longitude": longitude},
                        "radius": min(radius, 50000.0),
                    }
                },
            },
            headers={
                "X-Goog-Api-Key": _get_api_key(),
                "X-Goog-FieldMask": SEARCH_FIELDS,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            return {"status": "error", "error_message": f"Places API error {resp.status_code}: {resp.text}"}
        data = resp.json()
        return {"status": "success", "results": data.get("places", []) if isinstance(data, dict) else []}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


async def get_batch_restaurant_details(place_ids: list[str], tool_context=None) -> dict:
    """Get full Google Places profiles for multiple restaurants at once.
    Much faster than calling get_restaurant_details one at a time.

    Forwards `tool_context` to each inner call so `_place_name_<pid>` keys
    get populated for every restaurant (target + competitors), enabling
    per-place source citations downstream.

    Args:
        place_ids: List of Google Places IDs to fetch (max 10).
    """
    if not place_ids:
        return {"status": "error", "error_message": "No place_ids provided"}
    place_ids = place_ids[:10]
    results = await asyncio.gather(
        *(get_restaurant_details(pid, tool_context=tool_context) for pid in place_ids),
        return_exceptions=True,
    )
    places = []
    for pid, result in zip(place_ids, results):
        if isinstance(result, Exception):
            places.append({"place_id": pid, "status": "error", "error_message": str(result)})
        else:
            places.append(result)
    return {"status": "success", "places": places}


async def search_restaurants(query: str, latitude: float = 0.0, longitude: float = 0.0, radius: float = 5000.0) -> dict:
    """Search for restaurants by text query, optionally near a location.

    Args:
        query: Search text like 'Italian restaurants in Mokotow Warsaw'.
        latitude: Optional center latitude for location bias (0 = no bias).
        longitude: Optional center longitude for location bias (0 = no bias).
        radius: Bias radius in meters when lat/lng provided (default 5000).
    """
    try:
        client = _get_client()
        body: dict = {"textQuery": query, "pageSize": 20}
        if latitude != 0.0 and longitude != 0.0:
            body["locationBias"] = {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": min(radius, 50000.0),
                }
            }
        resp = await client.post(
            f"{BASE_URL}/places:searchText",
            json=body,
            headers={
                "X-Goog-Api-Key": _get_api_key(),
                "X-Goog-FieldMask": SEARCH_FIELDS,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            return {"status": "error", "error_message": f"Places API error {resp.status_code}: {resp.text}"}
        data = resp.json()
        return {"status": "success", "results": data.get("places", []) if isinstance(data, dict) else []}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
