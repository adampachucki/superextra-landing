"""Tests for TripAdvisor tools in tripadvisor_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.tripadvisor_tools import get_tripadvisor_reviews

# --- Fixtures ---

# Real-shape Restaurant_Review URL the model would receive from search_serpapi.
TA_URL = "https://www.tripadvisor.com/Restaurant_Review-g187323-d6796040-Reviews-Umami_P_Berg-Berlin.html"
# Pagination form with -or<offset>- that TA itself emits on later pages.
TA_URL_PAGED = "https://www.tripadvisor.com/Restaurant_Review-g187323-d6796040-Reviews-or45-Umami_P_Berg-Berlin.html"


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

APIFY_REVIEWS = [
    {
        "title": "Deep Review",
        "text": "Detailed review text",
        "rating": 5,
        "publishedDate": "2026-04-01",
        "originalLanguage": "en",
        "tripType": "COUPLES",
        "travelDate": "2026-03",
        "helpfulVotes": 4,
        "ownerResponse": {
            "text": "Thanks for visiting.",
            "publishedDate": "2026-04-02",
            "lang": "en",
        },
        "subratings": [{"name": "Food", "value": 5}],
        "photos": [{"url": "https://img.example/review.jpg"}],
        "user": {
            "userLocation": {"name": "Berlin, Germany"},
            "contributions": {"reviews": 40, "restaurantReviews": 2},
        },
        "placeInfo": {
            "id": "6796040",
            "name": "Umami P-Berg",
            "rating": 4.1,
            "numberOfReviews": 886,
            "locationString": "Berlin",
            "webUrl": TA_URL,
            "ratingHistogram": {"count5": 439},
        },
    }
]


def _mock_response(json_data, status_code=200):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class _Ctx:
    """Minimal stub matching tool_context.state contract."""
    def __init__(self):
        self.state: dict = {}


class TestGetTripadvisorReviews:
    @pytest.mark.asyncio
    async def test_fetches_and_parses_reviews(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=10)

        assert result["status"] == "success"
        assert result["url"] == TA_URL
        assert result["place_id"] == "6796040"
        assert result["backend"] == "serpapi"
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

        # Confirm the parsed place_id is the one passed to SerpAPI, not the URL.
        params = mock_client.get.call_args.kwargs["params"]
        assert params["engine"] == "tripadvisor_reviews"
        assert params["place_id"] == "6796040"
        assert params["offset"] == 0

    @pytest.mark.asyncio
    async def test_parses_paginated_url_form(self):
        # `-or<offset>-` pagination form emitted by TripAdvisor itself on later
        # pages must still resolve to the same place_id as the canonical URL.
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews(TA_URL_PAGED, max_reviews=10)

        assert result["status"] == "success"
        assert result["place_id"] == "6796040"

    @pytest.mark.asyncio
    async def test_rejects_non_restaurant_review_url(self):
        # Hotel_Review URLs are NOT valid inputs to the tripadvisor_reviews engine.
        hotel_url = "https://www.tripadvisor.com/Hotel_Review-g187323-d99999-Reviews-Some_Hotel-Berlin.html"
        with patch("superextra_agent.tripadvisor_tools._get_client",
                   side_effect=AssertionError("client should not be created on parse failure")), \
             patch("superextra_agent.tripadvisor_tools._get_api_key",
                   side_effect=AssertionError("api key should not be read on parse failure")):
            result = await get_tripadvisor_reviews(hotel_url, max_reviews=10)

        assert result["status"] == "error"
        assert "Restaurant_Review" in result["error_message"]

    @pytest.mark.asyncio
    async def test_rejects_empty_url(self):
        result = await get_tripadvisor_reviews("", max_reviews=10)
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_paginates_correctly(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(REVIEWS_RESPONSE_PAGE_0),
            _mock_response(REVIEWS_RESPONSE_PAGE_1),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=20)

        assert result["fetched_reviews"] == 20
        calls = mock_client.get.call_args_list
        assert calls[0].kwargs["params"]["offset"] == 0
        assert calls[1].kwargs["params"]["offset"] == 10

    @pytest.mark.asyncio
    async def test_fast_path_caps_at_100_reviews(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await get_tripadvisor_reviews(TA_URL, max_reviews=100)

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
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=50)

        assert result["fetched_reviews"] == 10
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_first_page_provider_error_with_no_reviews_returns_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({
            "search_information": {"total_reviews": 0},
            "error": "Tripadvisor hasn't returned any reviews for this query.",
        }))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=10)

        assert result["status"] == "error"
        assert "hasn't returned any reviews" in result["error_message"]

    @pytest.mark.asyncio
    async def test_any_page_http_error_returns_error(self):
        # Any HTTP failure surfaces as error — no silent partial-sample
        # success that would bias quantitative review analysis.
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[
            _mock_response(REVIEWS_RESPONSE_PAGE_0),
            _mock_response({}, status_code=500),
        ])

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=30)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_emits_source_pill_on_success(self):
        ctx = _Ctx()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            await get_tripadvisor_reviews(TA_URL, max_reviews=10, tool_context=ctx)

        pills = [v for k, v in ctx.state.items() if k.startswith("_tool_src_tripadvisor_")]
        assert len(pills) == 1
        assert pills[0] == {
            "provider": "tripadvisor",
            "title": "TripAdvisor",
            "url": TA_URL,
            "domain": "tripadvisor.com",
        }

    @pytest.mark.asyncio
    async def test_no_source_pill_when_no_context(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(REVIEWS_RESPONSE_PAGE_0))

        # No tool_context passed — must not raise even on success path.
        with patch("superextra_agent.tripadvisor_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.tripadvisor_tools._get_api_key", return_value="test-key"):
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=10)

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        # Clear env AND block the Secret Manager fallback so the test stays hermetic.
        with patch.dict("os.environ", {}, clear=True), \
             patch("superextra_agent.tripadvisor_tools._client", None), \
             patch("superextra_agent.secrets._get_client",
                   side_effect=RuntimeError("sm unreachable in test")):
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=10)

        assert result["status"] == "error"
        assert "SERPAPI_API_KEY" in result["error_message"]

    @pytest.mark.asyncio
    async def test_deep_mode_uses_apify_and_parses_superset_fields(self):
        with patch(
            "superextra_agent.tripadvisor_tools._run_actor_sync",
            AsyncMock(return_value={"status": "success", "items": APIFY_REVIEWS}),
        ) as run_actor:
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=300, mode="deep")

        assert result["status"] == "success"
        assert result["backend"] == "apify"
        assert result["total_reviews"] == 886
        assert result["fetched_reviews"] == 1
        assert result["place_info"]["ratingHistogram"] == {"count5": 439}

        actor, payload = run_actor.call_args.args
        assert actor == "maxcopell~tripadvisor-reviews"
        assert payload["startUrls"] == [{"url": TA_URL}]
        assert payload["maxReviews"] == 300
        assert payload["scrapeReviewerInfo"] is True
        assert payload["disableMachineTranslations"] is True

        review = result["reviews"][0]
        assert review["text"] == "Detailed review text"
        assert review["owner_response"]["text"] == "Thanks for visiting."
        assert review["author_hometown"] == "Berlin, Germany"
        assert review["author_contributions"] == 42
        assert review["subratings"] == [{"name": "Food", "value": 5}]
        assert review["photo_count"] == 1

    @pytest.mark.asyncio
    async def test_max_reviews_above_fast_limit_selects_deep_mode(self):
        with patch(
            "superextra_agent.tripadvisor_tools._run_actor_sync",
            AsyncMock(return_value={"status": "success", "items": APIFY_REVIEWS}),
        ) as run_actor:
            result = await get_tripadvisor_reviews(TA_URL, max_reviews=101)

        assert result["backend"] == "apify"
        assert run_actor.call_args.args[1]["maxReviews"] == 101

    @pytest.mark.asyncio
    async def test_deep_mode_caps_at_300_reviews(self):
        with patch(
            "superextra_agent.tripadvisor_tools._run_actor_sync",
            AsyncMock(return_value={"status": "success", "items": APIFY_REVIEWS}),
        ) as run_actor:
            await get_tripadvisor_reviews(TA_URL, max_reviews=500, mode="deep")

        assert run_actor.call_args.args[1]["maxReviews"] == 300
