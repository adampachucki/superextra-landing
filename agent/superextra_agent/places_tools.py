import logging
import os
import httpx

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


def _get_api_key() -> str:
    key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY environment variable is not set")
    return key


async def get_restaurant_details(place_id: str) -> dict:
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
        return {"status": "success", "place": resp.json()}
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
        return {"status": "success", "results": resp.json().get("places", [])}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


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
        return {"status": "success", "results": resp.json().get("places", [])}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}
