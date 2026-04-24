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
    async def test_returns_full_profile(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Prenzlauer Berg Berlin",
                address="Knaackstr. 16-18, 10405 Berlin",
            )

        assert result["status"] == "success"
        assert result["match_confidence"] == "high"
        assert result["place_id"] == "6796040"
        assert result["name"] == "Umami P-Berg"
        assert result["rating"] == 4.1
        assert result["num_reviews"] == 886
        assert result["ranking"] == "#169 of 9,505 Restaurants in Berlin"
        assert result["cuisines"] == ["Asian", "Vietnamese"]
        assert result["menu_link"] == "https://umami-restaurants.de/menu.pdf"
        assert result["tripadvisor_link"] == "https://www.tripadvisor.com/Restaurant_Review-umami-p-berg"
        assert len(result["nearby_restaurants"]) == 1
        assert result["nearby_restaurants"][0]["name"] == "Pasternak"
        assert len(result["sample_reviews"]) == 1

    @pytest.mark.asyncio
    async def test_returns_candidates_list(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant("Umami", "Prenzlauer Berg Berlin")

        assert len(result["candidates"]) == 3
        assert result["candidates"][0]["title"] == "Umami P-Berg"
        assert result["candidates"][1]["title"] == "Umami Restaurant"
        assert result["candidates"][2]["title"] == "Umami Sushi"
        assert result["selected_index"] == 0

    @pytest.mark.asyncio
    async def test_address_matching_high_confidence(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            # PLACE_RESPONSE has address "Knaackstr. 16-18, 10405 Berlin"
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin", address="Knaackstr. 16-18, 10405 Berlin"
            )

        assert result["match_confidence"] == "high"

    @pytest.mark.asyncio
    async def test_search_query_includes_address_when_provided(self):
        """Root-cause fix: when the caller provides an address, SerpAPI
        should see `name + address` in the search query so it can rank the
        geographically-correct candidate first. Previously the query was
        always `name + area`, throwing away disambiguating signal."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Umami", "Berlin", address="Knaackstr. 16-18, 10405 Berlin"
            )

        # First call is the tripadvisor search; inspect its params.
        first_call_params = mock_client.get.call_args_list[0].kwargs["params"]
        assert first_call_params["engine"] == "tripadvisor"
        assert "Knaackstr" in first_call_params["q"]
        assert "10405" in first_call_params["q"]

    @pytest.mark.asyncio
    async def test_search_query_falls_back_to_area_without_address(self):
        """When no address is provided, the old `name + area` query is used."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant("Umami", "Prenzlauer Berg Berlin")

        first_call_params = mock_client.get.call_args_list[0].kwargs["params"]
        assert first_call_params["q"] == "Umami Prenzlauer Berg Berlin"

    @pytest.mark.asyncio
    async def test_address_matching_low_confidence_flips_status(self):
        """When address matching fails, `status` must be `low_confidence`
        (not `success`) so the LLM doesn't treat the mismatched profile as
        authoritative. Keeps the `candidates` list so the caller can retry."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant(
                "Umami", "Berlin", address="Completely Different Street 99, 99999 Munich"
            )

        assert result["status"] == "low_confidence"
        assert result["match_confidence"] == "low"
        assert len(result["candidates"]) == 3

    @pytest.mark.asyncio
    async def test_backward_compatible_without_address(self):
        """Without an address to match against, we can't verify the match —
        multiple candidates therefore return `low_confidence`. Callers should
        pass the Places address; this behavior prevents silent misattribution
        when they don't."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant("Umami", "Berlin")

        assert result["status"] == "low_confidence"
        assert result["selected_index"] == 0
        assert "candidates" in result

    @pytest.mark.asyncio
    async def test_no_results_returns_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({"places": []}))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant("Nonexistent", "Nowhere")

        assert result["status"] == "error"
        assert "No TripAdvisor results" in result["error_message"]

    @pytest.mark.asyncio
    async def test_api_error_returns_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({}, status_code=500))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await find_tripadvisor_restaurant("Umami", "Berlin")

        assert result["status"] == "error"
        assert "500" in result["error_message"]


class TestFindTripadvisorRestaurantSourceWrite:
    """On high-confidence match, the tool writes a provider entry under a
    unique `_tool_src_<uuid>` state key so parallel tool calls batched
    into one ADK event's state_delta all survive."""

    @pytest.mark.asyncio
    async def test_writes_source_on_high_confidence(self):
        class MockCtx:
            def __init__(self):
                self.state = {}

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Umami", "Berlin",
                address="Knaackstr. 16-18, 10405 Berlin",
                tool_context=ctx,
            )

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        entry = ctx.state[source_keys[0]]
        assert entry["provider"] == "tripadvisor"
        assert entry["title"] == "TripAdvisor"
        assert entry["domain"] == "tripadvisor.com"
        assert entry["url"] == "https://www.tripadvisor.com/Restaurant_Review-umami-p-berg"

    @pytest.mark.asyncio
    async def test_skips_source_on_low_confidence(self):
        """Low-confidence matches must NOT attach a source — the whole point
        of the tightened contract is to keep uncertain matches from leaking
        into user-visible citations."""
        class MockCtx:
            def __init__(self):
                self.state = {}

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Umami", "Berlin",
                address="Completely Different Street 99, 99999 Munich",
                tool_context=ctx,
            )

        assert not any(k.startswith("_tool_src_") for k in ctx.state)

    @pytest.mark.asyncio
    async def test_skips_source_when_name_is_a_competitor(self):
        """If review_analyst's LLM deviates from the target-only invariant
        and looks up a competitor on TripAdvisor, the source write is gated
        by the target-name check so the pill doesn't end up linking to a
        competitor's TripAdvisor page. Regression guard for the bug caught
        in the 2026-04-24 E2E run (Geranium pill on a Noma brief)."""
        class MockCtx:
            def __init__(self):
                self.state = {
                    "_target_place_id": "ChIJnomaxx",
                    "_place_name_ChIJnomaxx": "Noma",
                }

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "Geranium", "Copenhagen",
                address="Per Henrik Lings Allé 4, 2100 København",
                tool_context=ctx,
            )

        assert not any(k.startswith("_tool_src_") for k in ctx.state)

    @pytest.mark.asyncio
    async def test_writes_source_when_name_matches_target(self):
        """Case/whitespace-tolerant comparison: LLM-authored name string
        resolves against the target's stored displayName."""
        class MockCtx:
            def __init__(self):
                self.state = {
                    "_target_place_id": "ChIJumami",
                    "_place_name_ChIJumami": "Umami",
                }

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await find_tripadvisor_restaurant(
                "  umami  ", "Berlin",   # casing + whitespace drift
                address="Knaackstr. 16-18, 10405 Berlin",
                tool_context=ctx,
            )

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        assert ctx.state[source_keys[0]]["provider"] == "tripadvisor"


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
        with patch.dict("os.environ", {}, clear=True), \
             patch("superextra_agent.tripadvisor_tools._client", None):
            result = await find_tripadvisor_restaurant("Test", "Berlin")
            assert result["status"] == "error"
            assert "SERPAPI_API_KEY" in result["error_message"]
