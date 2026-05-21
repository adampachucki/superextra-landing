"""Tests for the compact session place registry helpers."""

from superextra_agent.place_state import (
    format_known_places_context,
    get_place_name,
    set_original_target_once,
    upsert_google_place,
)


def test_upsert_google_place_reassigns_registry_top_level():
    state = {}
    place = {
        "displayName": {"text": "Noma"},
        "formattedAddress": "Refshalevej 96, Copenhagen",
        "location": {"latitude": 55.6828, "longitude": 12.6105},
        "googleMapsUri": "https://maps.google.com/?cid=noma",
        "rating": 4.7,
        "userRatingCount": 9000,
    }

    record = upsert_google_place(state, "ChIJnoma", place)

    assert state["places_by_id"]["ChIJnoma"] == record
    assert record["name"] == "Noma"
    assert record["lat"] == 55.6828
    assert record["lng"] == 12.6105


def test_original_target_is_set_once():
    state = {}

    set_original_target_once(
        state,
        "ChIJtarget",
        {"location": {"latitude": 1.0, "longitude": 2.0}},
    )
    set_original_target_once(
        state,
        "ChIJcompetitor",
        {"location": {"latitude": 3.0, "longitude": 4.0}},
    )

    assert state["original_target_place_id"] == "ChIJtarget"
    assert state["_target_place_id"] == "ChIJtarget"
    assert state["_target_lat"] == 1.0
    assert state["_target_lng"] == 2.0


def test_known_places_context_ignores_stale_tripadvisor_field():
    """A legacy `tripadvisor` field persisted on a place record (e.g. from a
    pre-unification Firestore session resumed today) must NOT inject a
    `TripAdvisor place ID:` hint into the prompt. The unified flow only
    accepts URLs; a numeric place_id hint would steer the model toward
    malformed get_tripadvisor_reviews calls."""
    state = {
        "places_by_id": {
            "ChIJlegacy": {
                "google_place_id": "ChIJlegacy",
                "name": "Legacy Place",
                "tripadvisor": {"place_id": "9999", "url": "https://tripadvisor.example/9999"},
            }
        }
    }

    text = format_known_places_context(state)

    assert "TripAdvisor place ID" not in text
    assert "9999" not in text


def test_known_places_context_is_compact_and_prompt_readable():
    state = {}
    upsert_google_place(
        state,
        "ChIJtarget",
        {
            "displayName": {"text": "Target"},
            "formattedAddress": "Main St",
            "location": {"latitude": 1.0, "longitude": 2.0},
        },
    )
    set_original_target_once(state, "ChIJtarget")

    text = format_known_places_context(state)

    assert "Target" in text
    assert "Google Place ID: ChIJtarget" in text
    assert "original target" in text
    assert get_place_name(state, "ChIJtarget") == "Target"
