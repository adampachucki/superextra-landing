"""Tests for places_tools.py — Google Places API wrappers."""

import pytest
import respx
import httpx

from superextra_agent.places_tools import (
    get_batch_restaurant_details,
    get_restaurant_details,
    find_nearby_restaurants,
    search_restaurants,
    _get_api_key,
    BASE_URL,
)


class MockToolCtx:
    def __init__(self):
        self.state = {}


class TestGetRestaurantDetails:
    @respx.mock
    @pytest.mark.asyncio
    async def test_success(self):
        """200 response returns status=success with place data."""
        place_data = {"displayName": {"text": "Test Restaurant"}, "rating": 4.5}
        respx.get(f"{BASE_URL}/places/test123").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        result = await get_restaurant_details("test123")

        assert result["status"] == "success"
        assert result["place"]["displayName"]["text"] == "Test Restaurant"

    @respx.mock
    @pytest.mark.asyncio
    async def test_stashes_place_name_per_place(self):
        """Per-place state key (_place_name_<pid>) is written so downstream
        tools (get_google_reviews) can label citations per restaurant.
        Lat/lng and _target_place_id stay target-scoped as before."""
        place_data = {
            "displayName": {"text": "Test Restaurant"},
            "location": {"latitude": 52.5, "longitude": 13.4},
        }
        respx.get(f"{BASE_URL}/places/test123").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        ctx = MockToolCtx()
        await get_restaurant_details("test123", tool_context=ctx)

        assert ctx.state["_target_lat"] == 52.5
        assert ctx.state["_target_lng"] == 13.4
        assert ctx.state["_target_place_id"] == "test123"
        assert ctx.state["_place_name_test123"] == "Test Restaurant"
        # No googleMapsUri in payload → no Google Maps source pill written.
        assert not any(k.startswith("_tool_src_") for k in ctx.state)

    @respx.mock
    @pytest.mark.asyncio
    async def test_writes_google_maps_source_for_target(self):
        """When the target's Places response includes googleMapsUri, a
        single _tool_src_* entry tagged provider=google_maps is written."""
        maps_uri = "https://www.google.com/maps/place/?q=place_id:target123"
        place_data = {
            "displayName": {"text": "Target"},
            "location": {"latitude": 55.68, "longitude": 12.61},
            "googleMapsUri": maps_uri,
        }
        respx.get(f"{BASE_URL}/places/target123").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        ctx = MockToolCtx()
        await get_restaurant_details("target123", tool_context=ctx)

        src_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(src_keys) == 1
        entry = ctx.state[src_keys[0]]
        assert entry["provider"] == "google_maps"
        assert entry["title"] == "Google Maps"
        assert entry["url"] == maps_uri
        assert entry["domain"] == "google.com"

    @respx.mock
    @pytest.mark.asyncio
    async def test_target_identity_survives_missing_location(self):
        """Target identity (`_target_place_id`) is written on the first
        Places call regardless of whether `location` came back. Decoupled
        from lat/lng so source pills still resolve on location-less
        payloads."""
        maps_uri = "https://www.google.com/maps/place/?q=place_id:noloc"
        place_data = {
            "displayName": {"text": "No Location"},
            "googleMapsUri": maps_uri,
            # No "location" field at all.
        }
        respx.get(f"{BASE_URL}/places/noloc").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        ctx = MockToolCtx()
        await get_restaurant_details("noloc", tool_context=ctx)

        assert ctx.state["_target_place_id"] == "noloc"
        assert "_target_lat" not in ctx.state
        assert "_target_lng" not in ctx.state
        src_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(src_keys) == 1
        assert ctx.state[src_keys[0]]["provider"] == "google_maps"

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_display_name_does_not_write_place_name(self):
        """If the Places API omits displayName, don't write a garbage key —
        leave it absent so get_google_reviews falls back to its generic
        label rather than citing 'None'."""
        place_data = {
            "location": {"latitude": 52.5, "longitude": 13.4},
        }
        respx.get(f"{BASE_URL}/places/test123").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        ctx = MockToolCtx()
        await get_restaurant_details("test123", tool_context=ctx)

        assert "_place_name_test123" not in ctx.state

    @respx.mock
    @pytest.mark.asyncio
    async def test_error_status(self):
        """Non-200 response returns status=error with message."""
        respx.get(f"{BASE_URL}/places/bad_id").mock(
            return_value=httpx.Response(400, text="Bad Request")
        )

        result = await get_restaurant_details("bad_id")

        assert result["status"] == "error"
        assert "400" in result["error_message"]

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout(self):
        """Timeout returns status=error."""
        respx.get(f"{BASE_URL}/places/slow").mock(
            side_effect=httpx.ReadTimeout("timeout")
        )

        result = await get_restaurant_details("slow")

        assert result["status"] == "error"
        assert "timeout" in result["error_message"].lower()


class TestGetBatchRestaurantDetails:
    @respx.mock
    @pytest.mark.asyncio
    async def test_threads_tool_context_so_each_place_gets_name_stashed(self):
        """get_batch_restaurant_details forwards tool_context to every
        inner get_restaurant_details call, so competitor fetches populate
        their own _place_name_<pid> keys concurrently."""
        respx.get(f"{BASE_URL}/places/target").mock(
            return_value=httpx.Response(200, json={"displayName": {"text": "Target"}})
        )
        respx.get(f"{BASE_URL}/places/comp1").mock(
            return_value=httpx.Response(200, json={"displayName": {"text": "Competitor 1"}})
        )
        respx.get(f"{BASE_URL}/places/comp2").mock(
            return_value=httpx.Response(200, json={"displayName": {"text": "Competitor 2"}})
        )

        ctx = MockToolCtx()
        result = await get_batch_restaurant_details(
            ["target", "comp1", "comp2"], tool_context=ctx,
        )

        assert result["status"] == "success"
        assert ctx.state["_place_name_target"] == "Target"
        assert ctx.state["_place_name_comp1"] == "Competitor 1"
        assert ctx.state["_place_name_comp2"] == "Competitor 2"

    @respx.mock
    @pytest.mark.asyncio
    async def test_competitor_batch_does_not_overwrite_target_coords(self):
        """Regression: previously `get_restaurant_details` unconditionally
        wrote `_target_lat`/`_target_lng`, so a competitor batch fetch
        (which runs AFTER the enricher's target fetch per context_enricher.md
        Steps 1 and 3) silently overwrote the target's coords, biasing
        downstream google_search toward whichever competitor finished last.

        Guard: target coords are written once (first-write-wins). This
        mirrors the actual enricher flow — target fetched solo, then
        competitors fetched via batch."""
        target_coords = {"latitude": 55.6876, "longitude": 12.6100}   # Noma
        comp1_coords = {"latitude": 55.6989, "longitude": 12.5896}    # Alchemist
        comp2_coords = {"latitude": 55.6803, "longitude": 12.5730}    # Geranium
        target_uri = "https://www.google.com/maps/place/?q=place_id:target"
        comp1_uri = "https://www.google.com/maps/place/?q=place_id:comp1"
        comp2_uri = "https://www.google.com/maps/place/?q=place_id:comp2"
        respx.get(f"{BASE_URL}/places/target").mock(
            return_value=httpx.Response(200, json={
                "displayName": {"text": "Target"},
                "location": target_coords,
                "googleMapsUri": target_uri,
            })
        )
        respx.get(f"{BASE_URL}/places/comp1").mock(
            return_value=httpx.Response(200, json={
                "displayName": {"text": "Competitor 1"},
                "location": comp1_coords,
                "googleMapsUri": comp1_uri,
            })
        )
        respx.get(f"{BASE_URL}/places/comp2").mock(
            return_value=httpx.Response(200, json={
                "displayName": {"text": "Competitor 2"},
                "location": comp2_coords,
                "googleMapsUri": comp2_uri,
            })
        )

        ctx = MockToolCtx()
        # Step 1 of enricher flow: solo target fetch.
        await get_restaurant_details("target", tool_context=ctx)
        # Step 3: competitor batch (target is NOT included per the instruction).
        await get_batch_restaurant_details(["comp1", "comp2"], tool_context=ctx)

        # Target coords and identity survive the competitor batch.
        assert ctx.state["_target_lat"] == target_coords["latitude"]
        assert ctx.state["_target_lng"] == target_coords["longitude"]
        assert ctx.state["_target_place_id"] == "target"
        # Per-place names still get written for every place.
        assert ctx.state["_place_name_target"] == "Target"
        assert ctx.state["_place_name_comp1"] == "Competitor 1"
        assert ctx.state["_place_name_comp2"] == "Competitor 2"
        # Exactly one Google Maps source survives — the target's. Competitor
        # fetches in the batch skip the source write.
        src_entries = [
            v for k, v in ctx.state.items() if k.startswith("_tool_src_")
        ]
        google_maps_entries = [
            e for e in src_entries if e.get("provider") == "google_maps"
        ]
        assert len(google_maps_entries) == 1
        assert google_maps_entries[0]["url"] == target_uri


class TestGetApiKey:
    def test_missing_env_var(self, monkeypatch):
        """Missing GOOGLE_PLACES_API_KEY raises RuntimeError."""
        monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)

        with pytest.raises(RuntimeError):
            _get_api_key()


class TestFindNearbyRestaurants:
    @respx.mock
    @pytest.mark.asyncio
    async def test_radius_capped(self):
        """Radius is capped at 50000 meters."""
        route = respx.post(f"{BASE_URL}/places:searchNearby").mock(
            return_value=httpx.Response(200, json={"places": []})
        )

        await find_nearby_restaurants(40.0, -74.0, radius=999999)

        # Verify the request body had radius capped at 50000
        import json

        body = json.loads(route.calls[0].request.content)
        assert body["locationRestriction"]["circle"]["radius"] == 50000.0


class TestSearchRestaurants:
    @respx.mock
    @pytest.mark.asyncio
    async def test_no_location_bias_when_zero(self):
        """lat=0, lng=0 means no locationBias in request body."""
        route = respx.post(f"{BASE_URL}/places:searchText").mock(
            return_value=httpx.Response(200, json={"places": []})
        )

        await search_restaurants("pizza", latitude=0.0, longitude=0.0)

        import json

        body = json.loads(route.calls[0].request.content)
        assert "locationBias" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_location_bias_when_provided(self):
        """lat/lng provided → locationBias present in request body."""
        route = respx.post(f"{BASE_URL}/places:searchText").mock(
            return_value=httpx.Response(200, json={"places": []})
        )

        await search_restaurants("sushi", latitude=52.2, longitude=21.0, radius=3000)

        import json

        body = json.loads(route.calls[0].request.content)
        assert "locationBias" in body
        circle = body["locationBias"]["circle"]
        assert circle["center"]["latitude"] == 52.2
        assert circle["center"]["longitude"] == 21.0
        assert circle["radius"] == 3000.0
