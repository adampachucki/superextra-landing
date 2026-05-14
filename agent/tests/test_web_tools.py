"""Tests for web content fetching tools in web_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent.web_tools import (
    MAX_CONTENT_LENGTH,
    fetch_web_content,
    fetch_web_content_batch,
)


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

        call_args = mock_client.get.call_args
        assert call_args[0][0] == "https://r.jina.ai/https://example.com/article"
        # readerlm-v2 is the central behavior — every fetch must request it.
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("X-Respond-With") == "readerlm-v2"
        assert headers.get("Authorization", "").startswith("Bearer ")

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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body,expected", [
        ("Warning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\n", "HTTP 403"),
        ("Warning: Target URL returned error 451: Unavailable", "HTTP 451"),
        ("Warning: This page maybe requiring CAPTCHA", "CAPTCHA"),
        ("Just a moment...\n\nChecking your browser", "Cloudflare"),
        ("Title: x\n\n(Note: The provided HTML contains an iframe and only the title was extracted)", "iframe / SPA"),
    ])
    async def test_jina_forwarded_blocks_become_errors(self, body, expected):
        """Jina returns upstream blocks as 200-OK markdown — flip to errors."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://blocked.example/page")

        assert result["status"] == "error"
        assert expected in result["error_message"]


class TestFetchWebContentBatch:
    @pytest.mark.asyncio
    async def test_batch_fetches_all(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("page content"))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content_batch([
                "https://a.example",
                "https://b.example",
                "https://c.example",
            ])

        assert result["status"] == "success"
        assert len(result["results"]) == 3
        assert all(r["status"] == "success" for r in result["results"])

    @pytest.mark.asyncio
    async def test_empty_batch_errors(self):
        result = await fetch_web_content_batch([])
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_oversized_batch_rejected(self):
        """Cap protects against confused-model fanout: 50 LM calls × ~25s each."""
        result = await fetch_web_content_batch([f"https://x{i}.example" for i in range(11)])
        assert result["status"] == "error"
        assert "max" in result["error_message"].lower()
