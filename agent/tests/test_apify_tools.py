"""Tests for Google Reviews Apify tools in apify_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.apify_tools import get_google_reviews, _build_maps_url


# --- Fixtures ---

APIFY_DATASET_RESPONSE = [
    {
        "text": "Great coffee and atmosphere!",
        "stars": 5,
        "publishedAt": "2026-03-15T10:00:00Z",
        "originalLanguage": "en",
        "isLocalGuide": True,
        "likesCount": 3,
        "responseFromOwnerText": "Thank you!",
    },
    {
        "text": "Decent but overpriced.",
        "stars": 3,
        "publishedAt": "2026-03-10T08:00:00Z",
        "originalLanguage": "pl",
        "isLocalGuide": False,
        "likesCount": 0,
    },
]


def _mock_response(json_data, status_code=201):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


class TestBuildMapsUrl:
    def test_builds_url(self):
        url = _build_maps_url("Wanderlust Coffee", "Ząbkowska 27, 03-736 Warszawa")
        assert url == "https://www.google.com/maps/place/Wanderlust+Coffee,+Ząbkowska+27,+03-736+Warszawa/"


class TestGetGoogleReviews:
    @pytest.mark.asyncio
    async def test_fetches_and_parses_reviews(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("Test Coffee", "Main St 1, Berlin")

        assert result["status"] == "success"
        assert result["name"] == "Test Coffee"
        assert result["total_fetched"] == 2

        review = result["reviews"][0]
        assert review["text"] == "Great coffee and atmosphere!"
        assert review["rating"] == 5
        assert review["date"] == "2026-03-15T10:00:00Z"
        assert review["language"] == "en"
        assert review["is_local_guide"] is True
        assert review["likes"] == 3
        assert review["owner_response"] == "Thank you!"

        review2 = result["reviews"][1]
        assert "owner_response" not in review2

    @pytest.mark.asyncio
    async def test_caps_max_reviews(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            await get_google_reviews("Test", "Addr", max_reviews=500)

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_json["maxReviewsPerPlace"] == 200

    @pytest.mark.asyncio
    async def test_api_error_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response({}, status_code=401))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("Test", "Addr")

        assert result["status"] == "error"
        assert "401" in result["error_message"]

    @pytest.mark.asyncio
    async def test_empty_results_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response([]))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("Nonexistent Place", "Nowhere")

        assert result["status"] == "error"
        assert "No Google reviews" in result["error_message"]

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("Test", "Addr")

        assert result["status"] == "error"
        assert "timed out" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_token_returns_error(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("superextra_agent.apify_tools._client", None):
            result = await get_google_reviews("Test", "Addr")

        assert result["status"] == "error"
        assert "APIFY_TOKEN" in result["error_message"]

    @pytest.mark.asyncio
    async def test_sends_correct_place_url(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            await get_google_reviews("Wanderlust Coffee", "Ząbkowska 27, Warszawa")

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_json["placeUrls"] == ["https://www.google.com/maps/place/Wanderlust+Coffee,+Ząbkowska+27,+Warszawa/"]
        assert call_json["sortBy"] == "newest"
