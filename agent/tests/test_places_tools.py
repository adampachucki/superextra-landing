"""Tests for places_tools.py — Google Places API wrappers."""

import pytest
import respx
import httpx

from superextra_agent.places_tools import (
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
    async def test_captures_google_maps_uri_into_state(self):
        """B2: `googleMapsUri` is written to tool_context.state so downstream
        tools (get_google_reviews) can cite the Google Maps page without
        relying on places_context prose."""
        place_data = {
            "displayName": {"text": "Test"},
            "location": {"latitude": 52.5, "longitude": 13.4},
            "googleMapsUri": "https://maps.google.com/?cid=12345",
        }
        respx.get(f"{BASE_URL}/places/test123").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        ctx = MockToolCtx()
        await get_restaurant_details("test123", tool_context=ctx)

        assert ctx.state["_target_lat"] == 52.5
        assert ctx.state["_target_lng"] == 13.4
        assert ctx.state["_target_google_maps_uri"] == "https://maps.google.com/?cid=12345"

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_google_maps_uri_does_not_write_state(self):
        """If the Places API omits googleMapsUri, don't write a garbage key —
        leave it absent so get_google_reviews can skip the source entry."""
        place_data = {
            "displayName": {"text": "Test"},
            "location": {"latitude": 52.5, "longitude": 13.4},
        }
        respx.get(f"{BASE_URL}/places/test123").mock(
            return_value=httpx.Response(200, json=place_data)
        )

        ctx = MockToolCtx()
        await get_restaurant_details("test123", tool_context=ctx)

        assert "_target_google_maps_uri" not in ctx.state

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
