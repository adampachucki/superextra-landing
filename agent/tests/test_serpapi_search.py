"""Tests for SerpAPI-backed search tool in serpapi_search.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.serpapi_search import search_serpapi


def _mock_response(json_data, status_code=200):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


SAMPLE_SERPAPI_RESPONSE = {
    "organic_results": [
        {
            "position": 1,
            "title": "Monsun Gdynia — Restaurant Reviews & Photos",
            "link": "https://www.tripadvisor.com/Restaurant_Review-g274726-d24912952-Reviews-Monsun-Gdynia.html",
            "snippet": "Monsun is a Chinese restaurant in Gdynia...",
        },
        {
            "position": 2,
            "title": "Monsun Gdynia (@monsun.gdynia) • Instagram",
            "link": "https://www.instagram.com/monsun.gdynia/",
            "snippet": "4,694 followers...",
        },
    ],
}


class TestSearchSerpapi:
    @pytest.mark.asyncio
    async def test_success_returns_results(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(SAMPLE_SERPAPI_RESPONSE))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            result = await search_serpapi("Monsun Gdynia")

        assert result["status"] == "success"
        assert result["query"] == "Monsun Gdynia"
        assert len(result["results"]) == 2
        first = result["results"][0]
        assert first["url"].startswith("https://www.tripadvisor.com/")
        assert first["domain"] == "tripadvisor.com"
        assert "Monsun" in first["title"]
        assert first["position"] == 1

    @pytest.mark.asyncio
    async def test_sends_correct_query_and_params(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(SAMPLE_SERPAPI_RESPONSE))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            await search_serpapi("Monsun Gdynia instagram", location="Gdynia, Poland")

        call_params = mock_client.get.call_args.kwargs.get("params") or mock_client.get.call_args[1]["params"]
        assert call_params["engine"] == "google"
        assert call_params["q"] == "Monsun Gdynia instagram"
        assert call_params["location"] == "Gdynia, Poland"
        assert "api_key" in call_params

    @pytest.mark.asyncio
    async def test_omits_location_when_not_provided(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(SAMPLE_SERPAPI_RESPONSE))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            await search_serpapi("Monsun Gdynia")

        params = mock_client.get.call_args.kwargs.get("params") or mock_client.get.call_args[1]["params"]
        assert "location" not in params

    @pytest.mark.asyncio
    async def test_http_error_returns_error_envelope(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({}, status_code=429))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            result = await search_serpapi("anything")

        assert result["status"] == "error"
        assert "429" in result["error_message"]

    @pytest.mark.asyncio
    async def test_timeout_returns_error_envelope(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            result = await search_serpapi("anything")

        assert result["status"] == "error"
        assert "timed out" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_empty_organic_results_returns_empty_list(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({"organic_results": []}))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            result = await search_serpapi("obscure venue")

        assert result["status"] == "success"
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_skips_results_with_no_link(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response({
            "organic_results": [
                {"position": 1, "title": "no link here", "snippet": "..."},
                {"position": 2, "title": "Valid", "link": "https://example.com/a",
                 "snippet": "..."},
            ],
        }))

        with patch("superextra_agent.serpapi_search._get_client", return_value=mock_client):
            result = await search_serpapi("x")

        assert len(result["results"]) == 1
        assert result["results"][0]["url"] == "https://example.com/a"

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        with patch.dict("os.environ", {}, clear=True), \
             patch("superextra_agent.serpapi_search._get_client",
                   side_effect=AssertionError("unexpected HTTP call")), \
             patch("superextra_agent.secrets._get_client",
                   side_effect=RuntimeError("sm unreachable in test")):
            result = await search_serpapi("anything")

        assert result["status"] == "error"
        assert "SERPAPI_API_KEY" in result["error_message"]
