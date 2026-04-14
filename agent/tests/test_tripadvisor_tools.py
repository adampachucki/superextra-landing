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
        },
        {
            "position": 2,
            "title": "Umami Restaurant",
            "place_type": "EATERY",
            "place_id": "9999999",
            "rating": 3.8,
            "reviews": 120,
            "location": "Berlin, Germany",
        },
        {
            "position": 3,
            "title": "Umami Sushi",
            "place_type": "EATERY",
            "place_id": "8888888",
            "rating": 4.0,
            "reviews": 55,
            "location": "Berlin, Germany",
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
            result = await find_tripadvisor_restaurant("Umami", "Prenzlauer Berg Berlin")

        assert result["status"] == "success"
        assert result["place_id"] == "6796040"
        assert result["name"] == "Umami P-Berg"
        assert result["rating"] == 4.1
        assert result["num_reviews"] == 886
        assert result["ranking"] == "#169 of 9,505 Restaurants in Berlin"
        assert result["cuisines"] == ["Asian", "Vietnamese"]
        assert result["menu_link"] == "https://umami-restaurants.de/menu.pdf"
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
    async def test_address_matching_low_confidence_when_no_match(self):
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

        assert result["match_confidence"] == "low"

    @pytest.mark.asyncio
    async def test_backward_compatible_without_address(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(SEARCH_RESPONSE),
            _mock_response(PLACE_RESPONSE),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            # Call without address — should still work, select first result
            result = await find_tripadvisor_restaurant("Umami", "Berlin")

        assert result["status"] == "success"
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
