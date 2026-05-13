"""Tests for Google Reviews Apify tools in apify_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.apify_tools import get_google_reviews


# --- Fixtures ---

APIFY_DATASET_RESPONSE = [
    {
        "text": "Great coffee and atmosphere!",
        "stars": 5,
        "publishedAtDate": "2026-03-15",
        "originalLanguage": "en",
        "isLocalGuide": True,
        "likesCount": 3,
        "responseFromOwnerText": "Thank you!",
    },
    {
        "text": "Decent but overpriced.",
        "stars": 3,
        "publishedAtDate": "2026-03-10",
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


class TestGetGoogleReviews:
    @pytest.mark.asyncio
    async def test_fetches_and_parses_reviews(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("ChIJtest123")

        assert result["status"] == "success"
        assert result["place_id"] == "ChIJtest123"
        assert result["total_fetched"] == 2

        review = result["reviews"][0]
        assert review["text"] == "Great coffee and atmosphere!"
        assert review["rating"] == 5
        assert review["date"] == "2026-03-15"
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
            await get_google_reviews("ChIJtest123", max_reviews=500)

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_json["maxReviews"] == 200

    @pytest.mark.asyncio
    async def test_api_error_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response({}, status_code=401))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("ChIJtest123")

        assert result["status"] == "error"
        assert "401" in result["error_message"]

    @pytest.mark.asyncio
    async def test_empty_results_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response([]))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("ChIJtest123")

        assert result["status"] == "error"
        assert "No Google reviews" in result["error_message"]

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await get_google_reviews("ChIJtest123")

        assert result["status"] == "error"
        assert "timed out" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_token_returns_error(self):
        # Clear env AND block the Secret Manager fallback so we exercise
        # the no-secret-anywhere path. Without the SM patch this test
        # would reach production Secret Manager from CI.
        with patch.dict("os.environ", {}, clear=True), \
             patch("superextra_agent.apify_tools._client", None), \
             patch("superextra_agent.secrets._get_client",
                   side_effect=RuntimeError("sm unreachable in test")):
            result = await get_google_reviews("ChIJtest123")

        assert result["status"] == "error"
        assert "APIFY_TOKEN" in result["error_message"]

    @pytest.mark.asyncio
    async def test_sends_correct_place_id(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            await get_google_reviews("ChIJMRpv9_HNHkcRdzbAYDXx7fc")

        call_json = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert call_json["placeIds"] == ["ChIJMRpv9_HNHkcRdzbAYDXx7fc"]
        assert call_json["reviewsSort"] == "newest"


class TestGoogleReviewsSourceWrite:
    """Google Reviews provider sources are written for the requested place."""

    @pytest.mark.asyncio
    async def test_target_call_writes_provider_source(self):
        class MockCtx:
            def __init__(self):
                self.state = {
                    "_target_place_id": "ChIJtarget",
                    "places_by_id": {
                        "ChIJtarget": {
                            "google_place_id": "ChIJtarget",
                            "name": "Target",
                        }
                    },
                }

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            await get_google_reviews("ChIJtarget", tool_context=ctx)

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        entry = ctx.state[source_keys[0]]
        assert entry["provider"] == "google_reviews"
        assert entry["title"] == "Google Reviews - Target"
        assert entry["url"] == "https://www.google.com/maps/place/?q=place_id:ChIJtarget"
        assert entry["domain"] == "google.com"
        assert entry["place_id"] == "ChIJtarget"

    @pytest.mark.asyncio
    async def test_competitor_call_writes_source_with_known_name(self):
        class MockCtx:
            def __init__(self):
                self.state = {
                    "_target_place_id": "ChIJtarget",
                    "places_by_id": {
                        "ChIJcomp": {
                            "google_place_id": "ChIJcomp",
                            "name": "Competitor",
                        }
                    },
                }

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            await get_google_reviews("ChIJcomp", tool_context=ctx)

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        entry = ctx.state[source_keys[0]]
        assert entry["provider"] == "google_reviews"
        assert entry["title"] == "Google Reviews - Competitor"
        assert entry["place_id"] == "ChIJcomp"

    @pytest.mark.asyncio
    async def test_no_known_place_still_writes_generic_source(self):
        class MockCtx:
            def __init__(self):
                self.state = {}

        ctx = MockCtx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(APIFY_DATASET_RESPONSE))

        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            await get_google_reviews("ChIJunknown", tool_context=ctx)

        source_keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(source_keys) == 1
        assert ctx.state[source_keys[0]]["title"] == "Google Reviews"
        assert ctx.state[source_keys[0]]["place_id"] == "ChIJunknown"
