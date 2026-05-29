"""Tests for source URL canonicalization in web_tools."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from superextra_agent.web_tools import (
    _canonical_source_url,
    _is_http_url,
    _is_vertex_redirect,
    _strip_fragment,
    resolve_source_display_url,
)

VERTEX_REDIRECT = (
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQabc"
)


def test_is_vertex_redirect_matches_only_exact_host_and_path():
    assert _is_vertex_redirect(VERTEX_REDIRECT)
    # Substring in path/query must NOT match — that would turn the unwrap
    # into an SSRF-shaped GET on an attacker-controlled URL.
    assert not _is_vertex_redirect(
        "https://attacker.example/p?ref=vertexaisearch.cloud.google.com/grounding-api-redirect/X"
    )
    assert not _is_vertex_redirect("https://example.com/article")
    assert not _is_vertex_redirect("not a url")


def test_strip_fragment_drops_only_the_fragment():
    assert _strip_fragment("https://x.com/a#frag") == "https://x.com/a"
    assert _strip_fragment("https://x.com/a") == "https://x.com/a"
    assert _strip_fragment("https://x.com/a?q=1#f") == "https://x.com/a?q=1"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com/a", True),
        ("http://example.com", True),
        ("ftp://example.com", False),
        ("/relative/path", False),
        ("not a url", False),
    ],
)
def test_is_http_url(url, expected):
    assert _is_http_url(url) is expected


def test_canonical_source_url_strips_fragment_and_validates():
    assert _canonical_source_url("https://x.com/a#f") == "https://x.com/a"
    assert _canonical_source_url("  https://x.com/a  ") == "https://x.com/a"
    assert _canonical_source_url("") is None
    assert _canonical_source_url("/relative") is None
    assert _canonical_source_url(None) is None
    assert _canonical_source_url(123) is None


@pytest.mark.asyncio
async def test_resolve_source_display_url_unwraps_vertex_redirect():
    redirect_resp = MagicMock()
    redirect_resp.headers = {"Location": "https://trojmiasto.pl/article-n123.html"}
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=redirect_resp)

    with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
        result = await resolve_source_display_url(VERTEX_REDIRECT)

    assert result == "https://trojmiasto.pl/article-n123.html"
    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_resolve_source_display_url_passes_through_plain_url():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock()
    with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
        result = await resolve_source_display_url("https://example.com/a#f")

    assert result == "https://example.com/a"
    # No redirect GET for a non-Vertex URL.
    assert mock_client.get.call_count == 0


@pytest.mark.asyncio
async def test_resolve_source_display_url_falls_back_on_unwrap_failure():
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=RuntimeError("network down"))
    with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
        result = await resolve_source_display_url(VERTEX_REDIRECT)

    # Falls back to the original redirect URL rather than raising.
    assert result == VERTEX_REDIRECT


@pytest.mark.asyncio
async def test_resolve_source_display_url_returns_none_for_invalid_input():
    assert await resolve_source_display_url("") is None
    assert await resolve_source_display_url(None) is None
    assert await resolve_source_display_url("/relative") is None
