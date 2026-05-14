"""Tests for web content fetching tools in web_tools.py."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch

from superextra_agent import web_tools
from superextra_agent.web_tools import (
    MAX_CONTENT_LENGTH,
    clear_fetch_cache_for_run,
    fetch_web_content,
    fetch_web_content_batch,
    set_fetch_run_id,
)


def _mock_response(text, status_code=200, headers=None):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    return resp


class TestFetchWebContent:
    @pytest.mark.asyncio
    async def test_fetch_success(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response("# Article Title\n\n" + "Real article paragraph. " * 20)
        )

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
        mock_client.get = AsyncMock(
            return_value=_mock_response("# Title\n\n" + "Paragraph content. " * 20)
        )

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            await fetch_web_content("https://example.com/page")

        headers = mock_client.get.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-key-123"

    @pytest.mark.asyncio
    async def test_content_truncation(self):
        long_content = "x" * (MAX_CONTENT_LENGTH + 1000)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(long_content))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/long")

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
            result = await fetch_web_content("https://example.com/page")

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

    @pytest.mark.asyncio
    async def test_thin_content_becomes_error(self):
        """Short content with no paragraph-shaped lines is rejected — navigation
        lists, paywall stubs, and section-index pages don't look like articles.
        """
        thin_body = "\n".join(["Home", "About", "Contact", "* Login", "* Sign up"])
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(thin_body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/section-index")

        assert result["status"] == "error"
        assert "too thin" in result["error_message"]

    @pytest.mark.asyncio
    async def test_short_real_article_with_long_paragraph_passes(self):
        """A short body that contains at least one long paragraph line should
        not trip the thin-content guard.
        """
        long_paragraph = (
            "This is a single paragraph line that intentionally crosses the 120-character "
            "threshold the thin-content guard uses to recognise real article body content."
        )
        assert len(long_paragraph) >= 120
        body = "# Headline\n\n" + long_paragraph
        assert len(body) < 800
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/short")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "https://kulinaria.trojmiasto.pl",  # no path
            "https://kulinaria.trojmiasto.pl/",  # bare slash — model can't sidestep with a trailing slash
        ],
    )
    async def test_bare_domain_rejected(self, url):
        """Reject homepages early with a steering message; don't burn a Jina
        call on a URL with no article path. Both "" and "/" paths must be
        rejected so the model can't bypass by adding a slash.
        """
        mock_client = AsyncMock()
        mock_client.get = AsyncMock()  # should not be called

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content(url)

        assert result["status"] == "error"
        assert "domain root" in result["error_message"]
        assert mock_client.get.call_count == 0

    @pytest.mark.asyncio
    async def test_vertex_grounding_redirect_is_unwrapped(self):
        """Vertex grounding URLs get resolved to the real article URL via a
        `follow_redirects=False` GET (reading the Location header) before
        Jina sees them. Without this, Jina fetches the redirect page itself.
        """
        redirect_resp = _mock_response(
            "", status_code=302,
            headers={"Location": "https://trojmiasto.pl/article-n123.html"},
        )
        article_body = "# Article\n\n" + "Real article paragraph that is long enough to clear the thin-content threshold and look like a body. " * 5
        article_resp = _mock_response(article_body)
        mock_client = AsyncMock()
        # Single mock.get serves both the redirect unwrap and the Jina fetch;
        # call order: 1) unwrap, 2) Jina fetch.
        mock_client.get = AsyncMock(side_effect=[redirect_resp, article_resp])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content(
                "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQabc"
            )

        assert result["status"] == "success"
        # Reported URL is the unwrapped one, not the redirect token.
        assert result["url"] == "https://trojmiasto.pl/article-n123.html"
        # Jina was hit with the unwrapped URL.
        jina_call_url = mock_client.get.call_args_list[1][0][0]
        assert "trojmiasto.pl/article-n123" in jina_call_url
        assert "grounding-api-redirect" not in jina_call_url

    @pytest.mark.asyncio
    async def test_url_with_vertex_substring_is_not_unwrapped(self):
        """Vertex detection must be an exact parsed-URL check, not a substring
        match. An attacker-controlled URL that merely embeds the redirect
        prefix in its path/query/fragment must not trigger the unwrap GET.
        """
        body = "# Title\n\n" + "Real paragraph content crossing the thin-content threshold. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content(
                "https://attacker.example/p?ref=vertexaisearch.cloud.google.com/grounding-api-redirect/X"
            )

        assert result["status"] == "success"
        # Only the Jina fetch happened — no unwrap GET on the path.
        assert mock_client.get.call_count == 1
        jina_url = mock_client.get.call_args_list[0][0][0]
        assert jina_url.startswith("https://r.jina.ai/https://attacker.example/")

    @pytest.mark.asyncio
    async def test_url_fragment_is_stripped_before_cache(self):
        """Fragments aren't sent to origin, so `page#a` and `page#b` must
        collapse to one cache key — otherwise refetches with different
        fragments miss the cache and burn a Jina call each time.
        """
        body = "# t\n\n" + "Real article paragraph crossing the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        set_fetch_run_id("run-frag")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                first = await fetch_web_content("https://example.com/article#one")
                second = await fetch_web_content("https://example.com/article#two")
        finally:
            clear_fetch_cache_for_run("run-frag")

        assert first["status"] == "success"
        # No fragment in the reported URL.
        assert first["url"] == "https://example.com/article"
        assert second["cached"] is True
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_vertex_unwrap_failure_falls_back_to_original_url(self):
        """If the redirect doesn't return a Location, pass the original URL
        through to Jina — its own thin/error detection handles the bad result.
        """
        no_loc = _mock_response("", status_code=200, headers={})
        article_body = "Title: x\n\n(Note: The provided HTML contains an iframe and only the title was extracted)"
        article_resp = _mock_response(article_body)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[no_loc, article_resp])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content(
                "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZabc"
            )

        assert result["status"] == "error"
        assert "iframe / SPA" in result["error_message"]


class TestFetchCache:
    @pytest.mark.asyncio
    async def test_second_fetch_in_same_run_returns_cached(self):
        body = "# Title\n\n" + "Real paragraph that crosses the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        set_fetch_run_id("run-1")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                first = await fetch_web_content("https://example.com/cache-me")
                second = await fetch_web_content("https://example.com/cache-me")
        finally:
            clear_fetch_cache_for_run("run-1")

        assert first["status"] == "success"
        assert first.get("cached") is None
        assert second["status"] == "success"
        assert second["cached"] is True
        # Jina hit exactly once.
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_does_not_persist_across_runs(self):
        body = "# Title\n\n" + "Real paragraph that crosses the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            set_fetch_run_id("run-A")
            await fetch_web_content("https://example.com/cross-run")
            clear_fetch_cache_for_run("run-A")

            set_fetch_run_id("run-B")
            try:
                second = await fetch_web_content("https://example.com/cross-run")
            finally:
                clear_fetch_cache_for_run("run-B")

        # New run → fresh fetch, no cached marker.
        assert second.get("cached") is None
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_failed_fetch_is_cached_within_run(self):
        """Within a run, errors are cached too. The diagnosed dance was the
        model refetching the same URL after a thin/blocked response — if
        errors aren't cached, the retry loop survives.
        """
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("nope", status_code=500))

        set_fetch_run_id("run-fail")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                first = await fetch_web_content("https://example.com/flaky")
                second = await fetch_web_content("https://example.com/flaky")
        finally:
            clear_fetch_cache_for_run("run-fail")

        assert first["status"] == "error"
        assert second["status"] == "error"
        assert second["cached"] is True
        assert second["error_message"] == first["error_message"]
        # Jina hit exactly once — the second call is served from cache.
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_bare_domain_reject_is_cached(self):
        """Domain-root rejections cache too, so a retried bare-domain fetch
        within the same run returns the steering message instantly without
        another reject path-resolve.
        """
        set_fetch_run_id("run-bare")
        try:
            first = await fetch_web_content("https://example.com")
            second = await fetch_web_content("https://example.com")
        finally:
            clear_fetch_cache_for_run("run-bare")

        assert first["status"] == "error"
        assert "domain root" in first["error_message"]
        assert second["cached"] is True
        assert second["error_message"] == first["error_message"]

    @pytest.mark.asyncio
    async def test_cache_evicts_oldest_when_full(self):
        """Bounded cache size guards against runs whose after_run_callback
        doesn't fire (ADK 1.28.0 calls it post-iteration, not from a finally,
        so cancelled/aborted runs can skip cleanup). FIFO eviction keeps the
        cache bounded regardless of cleanup hygiene.
        """
        body = "# t\n\n" + "Real article paragraph crossing the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        original_max = web_tools._FETCH_CACHE_MAX_SIZE
        web_tools._FETCH_CACHE_MAX_SIZE = 3
        set_fetch_run_id("run-cap")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                await fetch_web_content("https://example.com/a")
                await fetch_web_content("https://example.com/b")
                await fetch_web_content("https://example.com/c")
                # Inserting a 4th entry must evict the oldest ("/a").
                await fetch_web_content("https://example.com/d")
                # Refetching "/a" now misses the cache → goes back to Jina.
                await fetch_web_content("https://example.com/a")
                # "/b", "/c", "/d" remain → those refetches stay cached.
                await fetch_web_content("https://example.com/d")
        finally:
            web_tools._FETCH_CACHE_MAX_SIZE = original_max
            clear_fetch_cache_for_run("run-cap")

        # 4 distinct successful fetches + 1 re-fetch of the evicted "/a" = 5.
        assert mock_client.get.call_count == 5

    @pytest.mark.asyncio
    async def test_no_run_id_disables_cache(self):
        """Tools called outside a bound run context (tests, ad-hoc scripts)
        bypass the cache entirely — no run id, no per-run scope.
        """
        body = "# Title\n\n" + "Real paragraph that crosses the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            first = await fetch_web_content("https://example.com/no-context")
            second = await fetch_web_content("https://example.com/no-context")

        assert first["status"] == "success"
        assert second["status"] == "success"
        assert second.get("cached") is None
        assert mock_client.get.call_count == 2


class TestFetchWebContentBatch:
    @pytest.mark.asyncio
    async def test_batch_fetches_all(self):
        body = "# x\n\n" + "Real paragraph crossing the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content_batch([
                "https://a.example/x",
                "https://b.example/y",
                "https://c.example/z",
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
        result = await fetch_web_content_batch([f"https://x{i}.example/p" for i in range(11)])
        assert result["status"] == "error"
        assert "max" in result["error_message"].lower()
