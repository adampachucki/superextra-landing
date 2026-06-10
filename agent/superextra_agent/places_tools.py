import asyncio

from .http_client import LazyAsyncClient
from .place_state import (
    get_original_target_place_id,
    set_original_target_once,
    source_title,
    tool_source_key,
    upsert_google_place,
)
from .secrets import get_secret

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

FOOD_DRINK_PLACE_TYPES = {
    "acai_shop",
    "bagel_shop",
    "bakery",
    "bar",
    "bar_and_grill",
    "beer_garden",
    "bistro",
    "brewery",
    "brewpub",
    "cafe",
    "cafeteria",
    "cake_shop",
    "candy_store",
    "cat_cafe",
    "chocolate_factory",
    "chocolate_shop",
    "cocktail_bar",
    "coffee_roastery",
    "coffee_shop",
    "coffee_stand",
    "confectionery",
    "deli",
    "dessert_shop",
    "diner",
    "dog_cafe",
    "donut_shop",
    "food_court",
    "gastropub",
    "hookah_bar",
    "hot_dog_stand",
    "ice_cream_shop",
    "juice_shop",
    "kebab_shop",
    "lounge_bar",
    "meal_delivery",
    "meal_takeaway",
    "pizza_delivery",
    "pub",
    "restaurant",
    "salad_shop",
    "sandwich_shop",
    "snack_bar",
    "sports_bar",
    "steak_house",
    "tea_house",
    "wine_bar",
    "winery",
}

_get_client = LazyAsyncClient(timeout=15.0)


def _get_api_key() -> str:
    return get_secret("GOOGLE_PLACES_API_KEY")


def _is_food_service_place(place: dict) -> bool:
    def matches(value: object) -> bool:
        return (
            isinstance(value, str)
            and (value in FOOD_DRINK_PLACE_TYPES or value.endswith("_restaurant"))
        )

    if matches(place.get("primaryType")):
        return True
    types = place.get("types")
    return isinstance(types, list) and any(matches(value) for value in types)


def _set_geo_bias_once(state: dict, record: dict) -> None:
    lat = record.get("lat")
    lng = record.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return
    if state.get("_target_lat") is None or state.get("_target_lng") is None:
        state["_target_lat"] = lat
        state["_target_lng"] = lng


async def get_restaurant_details(place_id: str, tool_context=None) -> dict:
    """Get the full Google Places profile for a selected Place ID.

    The selected place may be a restaurant, proposed site, or area. Only
    food-service places initialize target-venue state.

    Args:
        place_id: The Google Places ID (e.g. 'ChIJN1t_tDeuEmsRUsoyG83frY4').
                  Found in the [Context: ...] prefix of the user's message.
    """
    result = await _fetch_restaurant_details(place_id)
    if result.get("status") == "success" and tool_context:
        _record_restaurant_details(place_id, result["place"], tool_context, allow_target_init=True)
    return result


async def _fetch_restaurant_details(place_id: str) -> dict:
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
        return {"status": "success", "place": place}
    except Exception as e:
        return {"status": "error", "error_message": str(e)}


def _record_restaurant_details(
    place_id: str,
    place: dict,
    tool_context,
    *,
    allow_target_init: bool,
) -> None:
    """Persist compact per-place state and provider source metadata."""
    state = tool_context.state
    record = upsert_google_place(state, place_id, place)

    existing_target = get_original_target_place_id(state)
    if existing_target:
        set_original_target_once(
            state,
            existing_target,
            place if existing_target == place_id else None,
        )
    elif allow_target_init and _is_food_service_place(place):
        set_original_target_once(state, place_id, place)
    elif allow_target_init:
        _set_geo_bias_once(state, record)

    name = (place.get("displayName") or {}).get("text")
    if name:
        state[f"_place_name_{place_id}"] = name

    maps_uri = place.get("googleMapsUri")
    if maps_uri:
        state[tool_source_key("google_maps", place_id)] = {
            "provider": "google_maps",
            "title": source_title(state, place_id, "Google Maps"),
            "url": maps_uri,
            "domain": "google.com",
            "place_id": place_id,
        }


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

    Fetches concurrently, then records compact per-place state sequentially so
    source metadata and `_place_name_<pid>` keys are populated consistently.

    Args:
        place_ids: List of Google Places IDs to fetch (max 10).
    """
    if not place_ids:
        return {"status": "error", "error_message": "No place_ids provided"}
    place_ids = place_ids[:10]
    results = await asyncio.gather(
        *(_fetch_restaurant_details(pid) for pid in place_ids),
        return_exceptions=True,
    )
    places = []
    for pid, result in zip(place_ids, results):
        if isinstance(result, Exception):
            places.append({"place_id": pid, "status": "error", "error_message": str(result)})
        else:
            if result.get("status") == "success" and tool_context:
                _record_restaurant_details(
                    pid,
                    result["place"],
                    tool_context,
                    allow_target_init=False,
                )
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
