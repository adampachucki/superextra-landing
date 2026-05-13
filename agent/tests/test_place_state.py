"""Tests for the compact session place registry helpers."""

from superextra_agent.place_state import (
    format_known_places_context,
    get_place_coords,
    get_place_name,
    set_original_target_once,
    upsert_google_place,
    upsert_tripadvisor_match,
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


def test_get_place_coords_falls_back_to_legacy_target():
    state = {
        "_target_place_id": "ChIJtarget",
        "_target_lat": 54.0,
        "_target_lng": 18.0,
    }

    assert get_place_coords(state, "ChIJtarget") == (54.0, 18.0)
    assert get_place_coords(state, "ChIJother") is None


def test_tripadvisor_match_stored_under_google_place():
    state = {"places_by_id": {"ChIJcomp": {"google_place_id": "ChIJcomp", "name": "Comp"}}}

    upsert_tripadvisor_match(
        state,
        "ChIJcomp",
        {"place_id": "123", "url": "https://tripadvisor.example/123", "verified": True},
    )

    assert state["places_by_id"]["ChIJcomp"]["tripadvisor"] == {
        "place_id": "123",
        "url": "https://tripadvisor.example/123",
        "verified": True,
    }


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
