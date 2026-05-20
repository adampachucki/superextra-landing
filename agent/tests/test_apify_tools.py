"""Tests for Apify-backed tools in apify_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.apify_tools import (
    fetch_facebook_page,
    fetch_facebook_posts,
    fetch_instagram_profile,
    fetch_tiktok_video,
    fetch_tripadvisor_page,
    get_google_reviews,
)


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


# ── social_analyst platform fetchers ─────────────────────────────────────────


class _Ctx:
    def __init__(self):
        self.state = {}


class TestFetchTripadvisorPage:
    @pytest.mark.asyncio
    async def test_success_trims_and_writes_source(self):
        items = [{
            "name": "Resaturacja Moon",
            "address": "ul. Slaska 27, Gdynia",
            "rating": 4.1,
            "rawRanking": 3.30,
            "numberOfReviews": 95,
            "cuisines": ["Polish", "Eastern European"],
            "photos": ["url1", "url2"],  # should be dropped
            "image": "img-url",            # should be dropped
        }]
        ctx = _Ctx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(items))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_tripadvisor_page("https://www.tripadvisor.com/r/x", tool_context=ctx)
        assert result["status"] == "success"
        assert result["url"] == "https://www.tripadvisor.com/r/x"
        item = result["items"][0]
        assert item["name"] == "Resaturacja Moon"
        assert item["rating"] == 4.1
        assert item["numberOfReviews"] == 95
        assert "photos" not in item
        assert "image" not in item
        # Source pill
        keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert len(keys) == 1
        assert ctx.state[keys[0]]["provider"] == "tripadvisor"
        assert ctx.state[keys[0]]["domain"] == "tripadvisor.com"

    @pytest.mark.asyncio
    async def test_http_error_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response({}, status_code=500))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_tripadvisor_page("https://x.example", tool_context=_Ctx())
        assert result["status"] == "error"
        assert "500" in result["error_message"]

    @pytest.mark.asyncio
    async def test_empty_items_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response([]))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_tripadvisor_page("https://x.example", tool_context=_Ctx())
        assert result["status"] == "error"
        assert "No TripAdvisor" in result["error_message"]


class TestFetchFacebookPage:
    @pytest.mark.asyncio
    async def test_success_keeps_ad_signals(self):
        items = [{
            "title": "Monsun Gdynia",
            "pageId": "61557910206363",
            "likes": 728,
            "followers": 728,
            "address": "Świętojańska 69b, Gdynia",
            "ad_status": "active",            # MUST be kept (marketing_brand needs it)
            "pageAdLibrary": {"id": "abc"},  # MUST be kept
            "profilePhoto": "url",            # should be dropped
        }]
        ctx = _Ctx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(items))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_facebook_page("https://www.facebook.com/p/x", tool_context=ctx)
        assert result["status"] == "success"
        item = result["items"][0]
        assert item["likes"] == 728
        assert item["ad_status"] == "active"
        assert item["pageAdLibrary"] == {"id": "abc"}
        assert "profilePhoto" not in item
        keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert ctx.state[keys[0]]["provider"] == "facebook"

    @pytest.mark.asyncio
    async def test_http_error_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response({}, status_code=403))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_facebook_page("https://x.example", tool_context=_Ctx())
        assert result["status"] == "error"
        assert "403" in result["error_message"]


class TestFetchFacebookPosts:
    @pytest.mark.asyncio
    async def test_success_trims_posts(self):
        items = [
            {"text": "Post one", "time": "2026-05-15", "likes": 50, "comments": 5, "shares": 2,
             "postUrl": "https://facebook.com/p1", "attachments": ["full-array"]},
            {"text": "Post two", "time": "2026-05-14", "likes": 30, "comments": 3, "shares": 1,
             "postUrl": "https://facebook.com/p2"},
        ]
        ctx = _Ctx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(items))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_facebook_posts("https://www.facebook.com/p/x", tool_context=ctx)
        assert result["status"] == "success"
        assert len(result["items"]) == 2
        assert result["items"][0]["text"] == "Post one"
        assert result["items"][0]["likes"] == 50
        assert "attachments" not in result["items"][0]
        keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        # Both fetch_facebook_page and fetch_facebook_posts emit provider="facebook"
        # so they share the same pill on the same page URL (avoids dedup collision).
        assert ctx.state[keys[0]]["provider"] == "facebook"


class TestFetchInstagramProfile:
    @pytest.mark.asyncio
    async def test_success_caps_latest_posts_at_five(self):
        items = [{
            "username": "monsun.gdynia",
            "biography": "NEW WAVE CHINESE",
            "followersCount": 4694,
            "postsCount": 93,
            "isBusinessAccount": True,
            "businessCategoryName": "Chinese Restaurant",
            "url": "https://www.instagram.com/monsun.gdynia",
            "profilePicUrlHD": "url",  # should be dropped
            "relatedProfiles": [{"x": 1}],  # should be dropped
            "latestPosts": [
                {"caption": f"post {i}", "takenAtTimestamp": 1700000000 + i,
                 "likesCount": 100 + i, "commentsCount": i, "shortCode": f"sc{i}",
                 "url": f"https://www.instagram.com/p/sc{i}/",
                 "displayUrl": "drop-me", "images": ["drop", "me"]}
                for i in range(12)
            ],
        }]
        ctx = _Ctx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(items))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_instagram_profile("https://www.instagram.com/monsun.gdynia/", tool_context=ctx)
        assert result["status"] == "success"
        item = result["items"][0]
        assert item["followersCount"] == 4694
        assert item["isBusinessAccount"] is True
        assert "profilePicUrlHD" not in item
        assert "relatedProfiles" not in item
        # latestPosts capped at 5 and trimmed
        assert len(item["latestPosts"]) == 5
        first = item["latestPosts"][0]
        assert first["caption"] == "post 0"
        assert first["shortCode"] == "sc0"
        assert first["url"] == "https://www.instagram.com/p/sc0/"
        assert "displayUrl" not in first
        assert "images" not in first
        keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert ctx.state[keys[0]]["provider"] == "instagram"

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_instagram_profile("https://x.example", tool_context=_Ctx())
        assert result["status"] == "error"
        assert "timed out" in result["error_message"]


class TestFetchTiktokVideo:
    @pytest.mark.asyncio
    async def test_success_trims_nested_meta(self):
        items = [{
            "text": "Restaurant review",
            "playCount": 41100,
            "diggCount": 803,
            "shareCount": 244,
            "commentCount": 9,
            "hashtags": [{"name": "food"}],
            "createTimeISO": "2024-04-17T15:24:25.000Z",
            "webVideoUrl": "https://www.tiktok.com/@x/video/y",
            "authorMeta": {"id": "uid", "name": "x", "verified": False, "extra": "drop"},
            "musicMeta": {"musicName": "song", "musicAuthor": "artist", "playUrl": "drop"},
            "videoMeta": {"duration": 60, "format": "mp4", "coverUrl": "drop"},
            "mediaUrls": ["drop"],  # should be dropped
        }]
        ctx = _Ctx()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=_mock_response(items))
        with patch("superextra_agent.apify_tools._get_client", return_value=mock_client), \
             patch("superextra_agent.apify_tools._get_api_key", return_value="test-token"):
            result = await fetch_tiktok_video("https://www.tiktok.com/@x/video/y", tool_context=ctx)
        assert result["status"] == "success"
        item = result["items"][0]
        assert item["playCount"] == 41100
        assert item["authorMeta"] == {"id": "uid", "name": "x", "verified": False}
        assert item["musicMeta"] == {"musicName": "song", "musicAuthor": "artist"}
        assert item["videoMeta"] == {"duration": 60, "format": "mp4"}
        assert "mediaUrls" not in item
        keys = [k for k in ctx.state if k.startswith("_tool_src_")]
        assert ctx.state[keys[0]]["provider"] == "tiktok"
