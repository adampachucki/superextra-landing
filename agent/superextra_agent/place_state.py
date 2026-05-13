"""Compact per-session place registry helpers.

The registry is session state, not a database. Keep it small and keyed by
Google Place ID so provider-specific IDs can hang off the canonical place.
"""

from __future__ import annotations

import hashlib
from typing import Any


PLACES_BY_ID_KEY = "places_by_id"
ORIGINAL_TARGET_PLACE_ID_KEY = "original_target_place_id"
TOOL_SOURCE_PREFIX = "_tool_src_"


def _get_state(state: Any, key: str, default: Any = None) -> Any:
    getter = getattr(state, "get", None)
    if callable(getter):
        return getter(key, default)
    try:
        return state[key]
    except (KeyError, TypeError):
        return default


def _assign_state(state: Any, key: str, value: Any) -> None:
    state[key] = value


def _places_by_id(state: Any) -> dict[str, dict[str, Any]]:
    raw = _get_state(state, PLACES_BY_ID_KEY, {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(place_id): dict(record)
        for place_id, record in raw.items()
        if isinstance(place_id, str) and isinstance(record, dict)
    }


def _set_places_by_id(state: Any, places: dict[str, dict[str, Any]]) -> None:
    # ADK 1.28 tracks state deltas through top-level assignment. Reassign the
    # registry after every nested change so AgentTool forwarding persists it.
    _assign_state(state, PLACES_BY_ID_KEY, places)


def _display_name(place: dict[str, Any]) -> str | None:
    display = place.get("displayName")
    if isinstance(display, dict):
        text = display.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _coords(place: dict[str, Any]) -> tuple[float, float] | None:
    loc = place.get("location")
    if not isinstance(loc, dict):
        return None
    lat = loc.get("latitude")
    lng = loc.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


def _put_if_present(record: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        record[key] = value


def upsert_google_place(state: Any, place_id: str, place: dict[str, Any]) -> dict[str, Any]:
    """Store compact Google Places profile metadata under ``place_id``."""
    places = _places_by_id(state)
    existing = dict(places.get(place_id, {}))
    record: dict[str, Any] = {**existing, "google_place_id": place_id}

    name = _display_name(place)
    _put_if_present(record, "name", name)
    _put_if_present(record, "formatted_address", place.get("formattedAddress"))
    _put_if_present(record, "google_maps_url", place.get("googleMapsUri"))
    _put_if_present(record, "rating", place.get("rating"))
    _put_if_present(record, "user_rating_count", place.get("userRatingCount"))
    _put_if_present(record, "price_level", place.get("priceLevel"))
    _put_if_present(record, "business_status", place.get("businessStatus"))
    _put_if_present(record, "website", place.get("websiteUri"))
    _put_if_present(record, "phone", place.get("nationalPhoneNumber"))

    coords = _coords(place)
    if coords:
        record["lat"], record["lng"] = coords

    places[place_id] = record
    _set_places_by_id(state, places)
    return record


def get_place_record(state: Any, place_id: str) -> dict[str, Any] | None:
    record = _places_by_id(state).get(place_id)
    if isinstance(record, dict):
        return dict(record)
    return None


def get_place_name(state: Any, place_id: str) -> str | None:
    record = get_place_record(state, place_id)
    if record:
        name = record.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    legacy = _get_state(state, f"_place_name_{place_id}")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    return None


def get_place_coords(state: Any, place_id: str) -> tuple[float, float] | None:
    record = get_place_record(state, place_id)
    if record:
        lat = record.get("lat")
        lng = record.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return float(lat), float(lng)

    original = get_original_target_place_id(state)
    if original == place_id:
        lat = _get_state(state, "_target_lat")
        lng = _get_state(state, "_target_lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return float(lat), float(lng)
    return None


def get_original_target_place_id(state: Any) -> str | None:
    value = _get_state(state, ORIGINAL_TARGET_PLACE_ID_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    legacy = _get_state(state, "_target_place_id")
    if isinstance(legacy, str) and legacy.strip():
        return legacy.strip()
    return None


def set_original_target_once(state: Any, place_id: str, place: dict[str, Any] | None = None) -> None:
    """Initialize original target keys if absent, preserving legacy state."""
    if not _get_state(state, ORIGINAL_TARGET_PLACE_ID_KEY):
        _assign_state(state, ORIGINAL_TARGET_PLACE_ID_KEY, place_id)
    if not _get_state(state, "_target_place_id"):
        _assign_state(state, "_target_place_id", place_id)

    if place and (
        _get_state(state, "_target_lat") is None
        or _get_state(state, "_target_lng") is None
    ):
        coords = _coords(place)
        if coords:
            _assign_state(state, "_target_lat", coords[0])
            _assign_state(state, "_target_lng", coords[1])


def tool_source_key(provider: str, google_place_id: str) -> str:
    """Bound source marker state to one key per provider/place."""
    digest = hashlib.sha1(f"{provider}:{google_place_id}".encode("utf-8")).hexdigest()[:16]
    return f"{TOOL_SOURCE_PREFIX}{provider}_{digest}"


def upsert_tripadvisor_match(
    state: Any,
    google_place_id: str,
    match: dict[str, Any],
) -> dict[str, Any]:
    places = _places_by_id(state)
    record = dict(places.get(google_place_id, {"google_place_id": google_place_id}))
    record["tripadvisor"] = {
        key: value
        for key, value in match.items()
        if value is not None and value != ""
    }
    places[google_place_id] = record
    _set_places_by_id(state, places)
    return record


def source_title(state: Any, google_place_id: str, provider_label: str) -> str:
    name = get_place_name(state, google_place_id)
    return f"{provider_label} - {name}" if name else provider_label


def format_known_places_context(
    state: Any,
    default: str = "No structured place registry available.",
) -> str:
    """Return a compact prompt-readable index of hydrated places."""
    places = _places_by_id(state)
    if not places:
        return default

    original = get_original_target_place_id(state)
    lines: list[str] = []
    for place_id, record in places.items():
        name = record.get("name") or "Unknown place"
        bits = [f"Google Place ID: {place_id}"]
        if place_id == original:
            bits.append("original target")
        address = record.get("formatted_address")
        if address:
            bits.append(f"address: {address}")
        lat = record.get("lat")
        lng = record.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            bits.append(f"coords: {lat}, {lng}")
        tripadvisor = record.get("tripadvisor")
        if isinstance(tripadvisor, dict) and tripadvisor.get("place_id"):
            bits.append(f"TripAdvisor place ID: {tripadvisor['place_id']}")
        lines.append(f"- {name} ({'; '.join(bits)})")
    return "\n".join(lines)
