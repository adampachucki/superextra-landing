"""Tests for web content fetching tools in web_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.web_tools import fetch_web_content, MAX_CONTENT_LENGTH


def _mock_response(text, status_code=200):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


class TestFetchWebContent:
    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("# Article Title\n\nSome content."))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/article")

        assert result["status"] == "success"
        assert result["url"] == "https://example.com/article"
        assert "Article Title" in result["content"]

        # Verify correct Jina URL was called
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "https://r.jina.ai/https://example.com/article"

    @pytest.mark.asyncio
    async def test_fetch_with_api_key(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("content"))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            await fetch_web_content("https://example.com")

        headers = mock_client.get.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-key-123"

    @pytest.mark.asyncio
    async def test_fetch_without_api_key(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("content"))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {}, clear=True):
            await fetch_web_content("https://example.com")

        headers = mock_client.get.call_args.kwargs.get("headers", {})
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_content_truncation(self):
        long_content = "x" * (MAX_CONTENT_LENGTH + 1000)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(long_content))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com")

        assert result["status"] == "success"
        assert result["content"].endswith("[Content truncated]")
        assert len(result["content"]) < len(long_content)

    @pytest.mark.asyncio
    async def test_fetch_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("Not found", status_code=404))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/missing")

        assert result["status"] == "error"
        assert "404" in result["error_message"]

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com")

        assert result["status"] == "error"
        assert "Timeout" in result["error_message"]
