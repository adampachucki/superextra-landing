"""Tests for TripAdvisor tools in tripadvisor_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.tripadvisor_tools import (
    find_tripadvisor_restaurant,
    get_tripadvisor_reviews,
)

# --- Fixtures: mock SerpAPI responses ---

SEARCH_RESPONSE = {
    "places": [
        {
            "position": 1,
            "title": "Umami P-Berg",
            "place_type": "EATERY",
            "place_id": "6796040",
            "rating": 4.1,
            "reviews": 886,
            "location": "Berlin, Germany",
            "link": "https://www.tripadvisor.com/Restaurant_Review-umami-p-berg",
        },
        {
            "position": 2,
            "title": "Umami Restaurant",
            "place_type": "EATERY",
            "place_id": "9999999",
            "rating": 3.8,
            "reviews": 120,
            "location": "Berlin, Germany",
            "link": "https://www.tripadvisor.com/Restaurant_Review-umami-restaurant",
        },
        {
            "position": 3,
            "title": "Umami Sushi",
            "place_type": "EATERY",
            "place_id": "8888888",
            "rating": 4.0,
            "reviews": 55,
            "location": "Berlin, Germany",
            "link": "https://www.tripadvisor.com/Restaurant_Review-umami-sushi",
        },
    ]
}

# Umami P-Berg's real-ish TripAdvisor coords. Matches TARGET_COORDS below for
# the happy-path tests; tests that need a coord mismatch substitute a
# different PLACE_RESPONSE or pass mismatched target coords via state.
TARGET_COORDS = (52.536, 13.421)
TARGET_ADDRESS_LINK = (
    "https://maps.google.com/maps?saddr=&daddr=Knaackstr. 16-18, 10405 Berlin"
    f"@{TARGET_COORDS[0]},{TARGET_COORDS[1]}"
)

PLACE_RESPONSE = {
    "place_result": {
        "type": "restaurant",
        "name": "Umami P-Berg",
        "rating": 4.1,
        "reviews": 886,
        "is_claimed": True,
        "ranking": "#169 of 9,505 Restaurants in Berlin",
        "categories": [{"name": "Mid-range"}, {"name": "Asian"}, {"name": "Vietnamese"}],
        "cuisines": ["Asian", "Vietnamese"],
        "diets": ["Gluten free options"],
        "meal_types": ["Lunch", "Dinner"],
        "dining_options": ["Takeout", "Reservations", "Outdoor Seating"],
        "address": "Knaackstr. 16-18, 10405 Berlin",
        "address_link": TARGET_ADDRESS_LINK,
        "phone": "+49 30 28860626",
        "email": "info@umami-restaurants.de",
        "website": "http://www.facebook.com/umamirestaurantpberg",
        "menu": {"link": "https://umami-restaurants.de/menu.pdf"},
        "nearby": {
            "restaurants": [
                {"name": "Pasternak", "place_id": "718266", "rating": 4.4, "reviews": 1003, "distance": 0.026},
            ]
        },
        "reviews_list": [
            {
                "title": "Great food",
                "snippet": "Delicious Vietnamese food.",
                "rating": 5,
                "date": "2026-03-23",
                "author": {"hometown": "London, UK"},
            }
        ],
    }
}


def _ctx_with_target(lat: float | None = TARGET_COORDS[0], lng: float | None = TARGET_COORDS[1], target_place_id: str = "ChIJtarget") -> "MockCtx":
    """MockCtx preloaded with target coordinates + place_id. Tests that need
    a coord mismatch pass different lat/lng (or None). Default puts the target
    at exactly TARGET_COORDS so the happy-path coord check passes with 0m drift."""
    class MockCtx:
        def __init__(self):
            self.state = {"_target_place_id": target_place_id}
            if lat is not None:
                self.state["_target_lat"] = lat
            if lng is not None:
                self.state["_target_lng"] = lng
    return MockCtx()


def _ctx_with_place(
    place_id: str = "ChIJtarget",
    *,
    lat: float | None = TARGET_COORDS[0],
    lng: float | None = TARGET_COORDS[1],
    name: str = "Umami",
    target_place_id: str = "ChIJtarget",
) -> "MockCtx":
    class MockCtx:
        def __init__(self):
            self.state = {
                "_target_place_id": target_place_id,
                "original_target_place_id": target_place_id,
                "places_by_id": {
                    place_id: {
                        "google_place_id": place_id,
                        "name": name,
                    }
                },
            }
            if lat is not None:
                self.state["places_by_id"][place_id]["lat"] = lat
            if lng is not None:
                self.state["places_by_id"][place_id]["lng"] = lng
            if place_id == target_place_id and lat is not None and lng is not None:
                self.state["_target_lat"] = lat
                self.state["_target_lng"] = lng

    return MockCtx()

REVIEWS_RESPONSE_PAGE_0 = {
    "search_information": {"total_reviews": 886},
    "reviews": [
        {
            "position": i + 1,
            "title": f"Review {i}",
            "snippet": f"Review text {i}",
            "rating": 4,
            "date": f"2026-03-{10 + i:02d}",
            "original_language": "en",
            "trip_info": {"type": "COUPLES", "date": "2026-03-31"},
            "author": {"hometown": "Paris, France", "contributions": 50},
            "votes": 2,
            "response": {"snippet": "Thank you!"},
        }
        for i in range(10)
    ],
}

REVIEWS_RESPONSE_PAGE_1 = {
    "search_information": {"total_reviews": 886},
    "reviews": [
        {
            "position": i + 11,
            "title": f"Review {i + 10}",
            "snippet": f"Review text {i + 10}",
            "rating": 3,
            "date": f"2026-02-{10 + i:02d}",
            "original_language": "de",
            "trip_info": {"type": "SOLO", "date": "2026-02-28"},
            "author": {"hometown": "Berlin, Germany"},
            "votes": 0,
        }
        for i in range(10)
    ],
}


def _mock_response(json_data, status_code=200):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class TestFindTripadvisorRestaurant:
    @pytest.mark.asyncio
    async def test_success_when_coords_close(self):
        """Happy path: TripAdvisor's coords match the target's coords within
        the 150m threshold → status=success with full payload."""
        ctx = _ctx_with_place()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Prenzlauer Berg Berlin",
                google_place_id="ChIJtarget",
                tool_context=ctx,
            )

        assert result["status"] == "success"
        assert result["google_place_id"] == "ChIJtarget"
        assert result["place_id"] == "6796040"
        assert result["name"] == "Umami P-Berg"
        assert result["rating"] == 4.1
        assert result["ranking"] == "#169 of 9,505 Restaurants in Berlin"
        assert result["cuisines"] == ["Asian", "Vietnamese"]
        assert result["tripadvisor_link"] == "https://www.tripadvisor.com/Restaurant_Review-umami-p-berg"
        assert len(result["sample_reviews"]) == 1
        # No candidates field on success — callers don't need it.
        assert "candidates" not in result
        # No match_confidence field — status alone carries the identity signal.
        assert "match_confidence" not in result

    @pytest.mark.asyncio
    async def test_unverified_when_coords_far(self):
        """Regression test for the 2026-04-24 Bar Leon bug. If the target's
        coords (54.347, 18.658 Gdansk) are 508m from the TripAdvisor
        candidate's coords (52.536, 13.421 Berlin — the fixture's built-in
        Umami location), we must return `unverified` and strip every rich
        field so no wrong-venue data leaks downstream."""
        ctx = _ctx_with_place(lat=54.347, lng=18.658, name="Bar Leon")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Bar Leon", "Gdansk",
                google_place_id="ChIJtarget",
                tool_context=ctx,
            )

        assert result["status"] == "unverified"
        assert "error_message" in result
        # Rich fields must be absent so downstream analysis can't use wrong-venue data.
        assert "tripadvisor_link" not in result
        assert "name" not in result
        assert "rating" not in result
        assert "candidates" not in result
        assert "sample_reviews" not in result

    @pytest.mark.asyncio
    async def test_unverified_when_place_coords_missing(self):
        """If the requested Google place has no coords, don't call SerpAPI."""
        ctx = _ctx_with_place(lat=None, lng=None)

        with patch(
            "superextra_agent.tripadvisor_tools._get_client",
            side_effect=AssertionError("client should not be created"),
        ), patch(
            "superextra_agent.tripadvisor_tools._get_api_key",
            side_effect=AssertionError("api key should not be read"),
        ):
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin",
                google_place_id="ChIJtarget",
                tool_context=ctx,
            )

        assert result["status"] == "unverified"
        assert "tripadvisor_link" not in result

    @pytest.mark.asyncio
    async def test_unverified_when_address_link_missing(self):
        """Some TripAdvisor responses may omit address_link. Without coords
        to verify, we can't accept the match."""
        ctx = _ctx_with_place()
        place_response_no_link = {
            "place_result": {**PLACE_RESPONSE["place_result"], "address_link": ""},
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(place_response_no_link),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin",
                google_place_id="ChIJtarget",
                tool_context=ctx,
            )

        assert result["status"] == "unverified"
        assert "tripadvisor_link" not in result

    @pytest.mark.asyncio
    async def test_search_uses_name_area_ssrc_and_lat_lon(self):
        """Query shape verification. `q` is always `f"{name} {area}"` (no
        street address). `ssrc=r` filters to eateries. The requested Google
        place coords bias SerpAPI's ranking."""
        ctx = _ctx_with_place()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Umami", "Prenzlauer Berg Berlin",
                google_place_id="ChIJtarget",
                tool_context=ctx,
            )

        search_params = mock_client.get.call_args_list[0].kwargs["params"]
        assert search_params["engine"] == "tripadvisor"
        assert search_params["q"] == "Umami Prenzlauer Berg Berlin"
        assert search_params["ssrc"] == "r"
        assert search_params["lat"] == str(TARGET_COORDS[0])
        assert search_params["lon"] == str(TARGET_COORDS[1])

    @pytest.mark.asyncio
    async def test_legacy_target_coords_fallback_when_registry_missing(self):
        """Old sessions can still verify the original target from _target_*."""
        ctx = _ctx_with_target(lat=TARGET_COORDS[0], lng=TARGET_COORDS[1])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin", google_place_id="ChIJtarget", tool_context=ctx,
            )

        search_params = mock_client.get.call_args_list[0].kwargs["params"]
        assert result["status"] == "success"
        assert search_params["lat"] == str(TARGET_COORDS[0])
        assert search_params["lon"] == str(TARGET_COORDS[1])

    @pytest.mark.asyncio
    async def test_unverified_when_no_places_returned(self):
        """Search ran but returned no candidates at all — unverified, not
        error. Error status is reserved for transport/API failures."""
        ctx = _ctx_with_place()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({"places": []}))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Nonexistent", "Nowhere", google_place_id="ChIJtarget", tool_context=ctx,
            )

        assert result["status"] == "unverified"

    @pytest.mark.asyncio
    async def test_error_when_serpapi_search_fails(self):
        """Transport failure on the search call → error (distinct from
        unverified). Timeline wording and metrics can distinguish."""
        ctx = _ctx_with_place()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({}, status_code=500))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin", google_place_id="ChIJtarget", tool_context=ctx,
            )

        assert result["status"] == "error"
        assert "500" in result["error_message"]

    @pytest.mark.asyncio
    async def test_error_when_serpapi_detail_fails(self):
        """Transport failure on the detail call → error."""
        ctx = _ctx_with_place()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response({}, status_code=429),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin", google_place_id="ChIJtarget", tool_context=ctx,
            )

        assert result["status"] == "error"
        assert "429" in result["error_message"]


class TestFindTripadvisorRestaurantSourceWrite:
    """Source pills write for any verified Google place."""

    @pytest.mark.asyncio
    async def test_writes_source_on_verified_target_match(self):
        """Happy path: Google place coords match candidate coords → pill writes."""
        ctx = _ctx_with_place(target_place_id="ChIJtarget", name="Umami")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Umami", "Berlin", google_place_id="ChIJtarget", tool_context=ctx,
            )

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        entry = ctx.state[source_keys[0]]
        assert entry["provider"] == "tripadvisor"
        assert entry["title"] == "TripAdvisor - Umami"
        assert entry["domain"] == "tripadvisor.com"
        assert entry["url"] == "https://www.tripadvisor.com/Restaurant_Review-umami-p-berg"
        assert entry["place_id"] == "ChIJtarget"
        assert ctx.state["places_by_id"]["ChIJtarget"]["tripadvisor"]["place_id"] == "6796040"

    @pytest.mark.asyncio
    async def test_skips_source_when_coords_diverge(self):
        """2026-04-24 Bar Leon regression — search returns a candidate at a
        different address; coord check rejects it; no pill."""
        ctx = _ctx_with_place(lat=54.347, lng=18.658, target_place_id="ChIJtarget", name="Bar Leon")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Bar Leon", "Gdansk", google_place_id="ChIJtarget", tool_context=ctx,
            )

        assert not any(k.startswith("_tool_src_") for k in ctx.state)

    @pytest.mark.asyncio
    async def test_writes_source_when_place_id_is_competitor(self):
        ctx = _ctx_with_place(
            place_id="ChIJgeranium",
            target_place_id="ChIJnoma",
            name="Geranium",
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Geranium", "Copenhagen",
                google_place_id="ChIJgeranium",  # competitor, not the target
                tool_context=ctx,
            )

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        assert ctx.state[source_keys[0]]["title"] == "TripAdvisor - Geranium"
        assert ctx.state[source_keys[0]]["place_id"] == "ChIJgeranium"

    @pytest.mark.asyncio
    async def test_skips_source_when_place_id_empty(self):
        """Defense in depth: empty google_place_id (LLM schema violation) →
        no pill even if everything else would have passed."""
        ctx = _ctx_with_target(target_place_id="ChIJtarget")

        with patch(
            "superextra_agent.tripadvisor_tools._get_client",
            side_effect=AssertionError("client should not be created"),
        ), patch(
            "superextra_agent.tripadvisor_tools._get_api_key",
            side_effect=AssertionError("api key should not be read"),
        ):
            await find_tripadvisor_restaurant(
                "Umami", "Berlin",
                google_place_id="",
                tool_context=ctx,
            )

        assert not any(k.startswith("_tool_src_") for k in ctx.state)


class TestGetTripadvisorReviews:
    @pytest.mark.asyncio
    async def test_fetches_and_parses_reviews(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews("6796040", num_pages=1)

        assert result["status"] == "success"
        assert result["total_reviews"] == 886
        assert result["fetched_reviews"] == 10
        assert len(result["reviews"]) == 10

        review = result["reviews"][0]
        assert review["title"] == "Review 0"
        assert review["text"] == "Review text 0"
        assert review["rating"] == 4
        assert review["trip_type"] == "COUPLES"
        assert review["author_hometown"] == "Paris, France"
        assert review["has_owner_response"] is True

    @pytest.mark.asyncio
    async def test_paginates_correctly(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(REVIEWS_RESPONSE_PAGE_0),
            _mock_response(REVIEWS_RESPONSE_PAGE_1),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews("6796040", num_pages=2)

        assert result["fetched_reviews"] == 20
        # Verify offset params: page 0 = offset 0, page 1 = offset 10
        calls = mock_client.get.call_args_list
        assert calls[0].kwargs["params"]["offset"] == 0
        assert calls[1].kwargs["params"]["offset"] == 10

    @pytest.mark.asyncio
    async def test_caps_at_10_pages(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews("6796040", num_pages=50)

        # Should cap at 10 pages = 10 API calls
        assert mock_client.get.call_count == 10

    @pytest.mark.asyncio
    async def test_stops_on_empty_page(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(REVIEWS_RESPONSE_PAGE_0),
            _mock_response({"search_information": {"total_reviews": 886}, "reviews": []}),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews("6796040", num_pages=5)

        assert result["fetched_reviews"] == 10
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_first_page_error_returns_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({}, status_code=429))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews("6796040")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_later_page_error_returns_partial(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(REVIEWS_RESPONSE_PAGE_0),
            _mock_response({}, status_code=500),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews("6796040", num_pages=3)

        assert result["status"] == "success"
        assert result["fetched_reviews"] == 10


class TestApiKeyRequired:
    @pytest.mark.asyncio
    async def test_missing_key_raises(self):
        # Clear env AND block the Secret Manager fallback. Without the SM
        # patch this test would reach production Secret Manager from CI.
        ctx = _ctx_with_place(place_id="ChIJdummy", target_place_id="ChIJdummy", name="Test")
        with patch.dict("os.environ", {}, clear=True), \
             patch("superextra_agent.tripadvisor_tools._client", None), \
             patch("superextra_agent.secrets._get_client",
                   side_effect=RuntimeError("sm unreachable in test")):
            result = await find_tripadvisor_restaurant(
                "Test", "Berlin", google_place_id="ChIJdummy", tool_context=ctx,
            )
            assert result["status"] == "error"
            assert "SERPAPI_API_KEY" in result["error_message"]
