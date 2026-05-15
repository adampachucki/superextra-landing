"""Tests for web content fetching tools in web_tools.py."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from superextra_agent import web_tools
from superextra_agent.web_tools import (
    MAX_CONTENT_LENGTH,
    clear_fetch_cache_for_run,
    fetch_web_content,
    fetch_web_content_batch,
    read_web_pages,
    set_fetch_run_id,
)


@pytest.fixture(autouse=True)
def mock_emit_cloud_log():
    """Silence Cloud Logging in tests — emit_cloud_log otherwise tries to
    auth + write per-fetch. Tests that need to assert on log calls receive
    this fixture by name and inspect `.call_args_list`.
    """
    with patch("superextra_agent.web_tools.emit_cloud_log") as mock:
        yield mock


def _mock_response(text, status_code=200, headers=None):
    resp = AsyncMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    return resp


def _log_kwargs(mock_emit, event="fetch_url", index=-1):
    """Return kwargs of the Nth (default last) emit_cloud_log call for `event`."""
    matches = [c for c in mock_emit.call_args_list if c.args[0] == event]
    return matches[index].kwargs if matches else {}


def test_tool_docstrings_describe_source_reading_workflow():
    read_doc = " ".join((read_web_pages.__doc__ or "").split())
    fetch_doc = " ".join((fetch_web_content.__doc__ or "").split())
    batch_doc = " ".join((fetch_web_content_batch.__doc__ or "").split())

    assert "Explicit structured reader for concrete public URLs" in read_doc
    assert "fetched-page source capture" in read_doc
    assert "Prefer this before raw Markdown fallback tools" in read_doc
    assert "Raw-Markdown fallback, not the normal page reader" in fetch_doc
    assert "Do not use this as the first read" in fetch_doc
    assert "Raw-Markdown fallback for multiple URLs" in batch_doc
    assert "prefer URL Context or `read_web_pages` first" in batch_doc


def test_source_reading_timeouts_are_short_bounded_attempts():
    assert web_tools.TIMEOUT_S == 15.0
    assert web_tools.URL_CONTEXT_TIMEOUT_S == 15.0
    assert web_tools.URL_CONTEXT_HTTP_TIMEOUT_MS == 12_000
    assert web_tools.VERTEX_UNWRAP_TIMEOUT_S == 5.0


class TestReadWebPages:
    def test_url_context_client_uses_cloud_platform_scoped_credentials(self, monkeypatch):
        web_tools._url_context_client = None
        credentials = object()
        client = object()
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-a")
        monkeypatch.delenv("GOOGLE_CLOUD_QUOTA_PROJECT", raising=False)

        try:
            with patch(
                "superextra_agent.web_tools.google_auth_default",
                return_value=(credentials, "project-from-auth"),
            ) as auth_default, patch(
                "superextra_agent.web_tools.Client",
                return_value=client,
            ) as client_ctor:
                result = web_tools._get_url_context_client()
        finally:
            web_tools._url_context_client = None

        assert result is client
        auth_default.assert_called_once_with(
            scopes=[web_tools.CLOUD_PLATFORM_SCOPE],
            quota_project_id="project-a",
        )
        kwargs = client_ctor.call_args.kwargs
        assert kwargs["credentials"] is credentials
        assert kwargs["project"] == "project-a"
        assert kwargs["location"] == "global"

    @pytest.mark.asyncio
    async def test_reads_pages_with_url_context(self, mock_emit_cloud_log):
        expected = {
            "status": "success",
            "model": "gemini-3.1-pro-preview",
            "urls": ["https://example.com/menu"],
            "retrieved": [
                {
                    "retrieved_url": "https://example.com/menu",
                    "retrieval_status": "URL_RETRIEVAL_STATUS_SUCCESS",
                }
            ],
            "results": [
                {
                    "status": "success",
                    "url": "https://example.com/menu",
                    "retrieved_url": "https://example.com/menu",
                    "title": "Menu",
                    "evidence_summary": "Lunch is served daily.",
                    "specific_facts": ["Lunch daily"],
                    "supporting_details": [],
                    "limits": "",
                }
            ],
            "sources": [
                {
                    "url": "https://example.com/menu",
                    "title": "Menu",
                    "domain": "example.com",
                    "provider": "fetched_page",
                }
            ],
        }

        with patch(
            "superextra_agent.web_tools._read_web_pages_sync",
            return_value=expected,
        ) as read_sync:
            result = await read_web_pages(
                ["https://example.com/menu#lunch"],
                evidence_goal="Extract menu evidence",
            )

        assert result == expected
        read_sync.assert_called_once_with(
            ["https://example.com/menu"],
            "Extract menu evidence",
        )
        kw = _log_kwargs(mock_emit_cloud_log, event="read_web_pages")
        assert kw["status"] == "success"
        assert kw["url_count"] == 1
        assert kw["retrieved_count"] == 1
        assert kw["cached"] is False

    @pytest.mark.asyncio
    async def test_rejects_invalid_urls(self):
        result = await read_web_pages(["file:///etc/passwd"])

        assert result["status"] == "error"
        assert "valid http(s)" in result["error_message"]

    @pytest.mark.asyncio
    async def test_caches_same_run_reads(self):
        expected = {
            "status": "success",
            "model": "gemini-3.1-pro-preview",
            "urls": ["https://example.com/menu"],
            "results": [],
            "sources": [{"url": "https://example.com/menu", "title": "Menu"}],
        }

        set_fetch_run_id("run-read-cache")
        try:
            with patch(
                "superextra_agent.web_tools._read_web_pages_sync",
                return_value=expected,
            ) as read_sync:
                first = await read_web_pages(["https://example.com/menu"], "menu")
                second = await read_web_pages(["https://example.com/menu"], "menu")
        finally:
            clear_fetch_cache_for_run("run-read-cache")

        assert first.get("cached") is None
        assert second["cached"] is True
        assert read_sync.call_count == 1

    @pytest.mark.asyncio
    async def test_exception_returns_error_without_private_reason(self, mock_emit_cloud_log):
        with patch(
            "superextra_agent.web_tools._read_web_pages_sync",
            side_effect=RuntimeError("boom"),
        ):
            result = await read_web_pages(["https://example.com/menu"])

        assert result["status"] == "error"
        assert "URL Context read failed" in result["error_message"]
        assert "_error_reason" not in result
        kw = _log_kwargs(mock_emit_cloud_log, event="read_web_pages")
        assert kw["error_reason"] == "exception"
        assert kw["error_message"] == "URL Context read failed: boom"

    @pytest.mark.asyncio
    async def test_strips_private_usage_metadata_after_logging(self, mock_emit_cloud_log):
        expected = {
            "status": "success",
            "model": "gemini-3.1-pro-preview",
            "urls": ["https://example.com/menu"],
            "results": [],
            "sources": [{"url": "https://example.com/menu", "title": "Menu"}],
            "_usage_metadata": {
                "prompt_token_count": 12,
                "tool_use_prompt_token_count": 8,
                "total_token_count": 20,
            },
        }

        with patch(
            "superextra_agent.web_tools._read_web_pages_sync",
            return_value=expected,
        ):
            result = await read_web_pages(["https://example.com/menu"])

        assert "_usage_metadata" not in result
        kw = _log_kwargs(mock_emit_cloud_log, event="read_web_pages")
        assert kw["prompt_token_count"] == 12
        assert kw["tool_use_prompt_token_count"] == 8
        assert kw["total_token_count"] == 20

    def test_url_context_sync_parses_model_response(self):
        response = SimpleNamespace(
            text=(
                '{"results":[{"url":"https://example.com/menu",'
                '"retrieved_url":"https://example.com/menu",'
                '"title":"Menu","evidence_summary":"Lunch is daily.",'
                '"specific_facts":["Lunch daily"],"supporting_details":[],'
                '"limits":""}],"overall_limits":""}'
            ),
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://example.com/menu",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
                            )
                        ]
                    )
                )
            ],
        )
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_kwargs: response)
        )

        with patch("superextra_agent.web_tools._get_url_context_client", return_value=client):
            result = web_tools._read_web_pages_sync(
                ["https://example.com/menu"],
                "menu facts",
            )

        assert result["status"] == "success"
        assert result["results"][0]["retrieval_status"].endswith("SUCCESS")
        assert result["sources"] == [
            {
                "url": "https://example.com/menu",
                "title": "Menu",
                "domain": "example.com",
                "provider": "fetched_page",
            }
        ]

    def test_url_context_sync_keeps_only_successful_partial_sources(self):
        response = SimpleNamespace(
            text=(
                '{"results":['
                '{"url":"https://example.com/menu","retrieved_url":"https://example.com/menu",'
                '"title":"Menu","evidence_summary":"Lunch is daily.",'
                '"specific_facts":["Lunch daily"],"supporting_details":[],"limits":""},'
                '{"url":"https://example.com/private","retrieved_url":"https://example.com/private",'
                '"title":"Private","evidence_summary":"","specific_facts":[],'
                '"supporting_details":[],"limits":"Could not retrieve."}'
                '],"overall_limits":"One URL could not be retrieved."}'
            ),
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://example.com/menu",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
                            ),
                            SimpleNamespace(
                                retrieved_url="https://example.com/private",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_UNSAFE",
                            ),
                        ]
                    )
                )
            ],
        )
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_kwargs: response)
        )

        with patch("superextra_agent.web_tools._get_url_context_client", return_value=client):
            result = web_tools._read_web_pages_sync(
                ["https://example.com/menu", "https://example.com/private"],
                "menu facts",
            )

        assert result["status"] == "success"
        assert [item["status"] for item in result["results"]] == ["success", "error"]
        assert result["sources"] == [
            {
                "url": "https://example.com/menu",
                "title": "Menu",
                "domain": "example.com",
                "provider": "fetched_page",
            }
        ]

    def test_url_context_sync_rejects_failed_retrieval_status(self):
        response = SimpleNamespace(
            text=(
                '{"results":[{"url":"https://example.com/private",'
                '"retrieved_url":"https://example.com/private",'
                '"title":"Private","evidence_summary":"No access.",'
                '"specific_facts":[],"supporting_details":[],'
                '"limits":"Could not retrieve."}],"overall_limits":""}'
            ),
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://example.com/private",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_UNSAFE",
                            )
                        ]
                    )
                )
            ],
        )
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_kwargs: response)
        )

        with patch("superextra_agent.web_tools._get_url_context_client", return_value=client):
            result = web_tools._read_web_pages_sync(
                ["https://example.com/private"],
                "owner facts",
            )

        assert result["status"] == "error"
        assert result["retrieved"][0]["retrieval_status"].endswith("UNSAFE")
        assert result["results"][0]["status"] == "error"
        assert "sources" not in result

    def test_url_context_sync_requires_retrieval_metadata_for_sources(self):
        response = SimpleNamespace(
            text="plain model answer, no URL Context metadata",
            candidates=[],
        )
        client = SimpleNamespace(
            models=SimpleNamespace(generate_content=lambda **_kwargs: response)
        )

        with patch("superextra_agent.web_tools._get_url_context_client", return_value=client):
            result = web_tools._read_web_pages_sync(
                ["https://example.com/menu"],
                "menu facts",
            )

        assert result["status"] == "error"
        assert result["retrieved"] == []
        assert "sources" not in result


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


class TestFetchUrlLogging:
    """Each fetch attempt emits one structured `fetch_url` Cloud Logging
    entry. These tests assert the entry shape across success and error
    paths so per-URL diagnostics stay reliable across refactors.
    """

    @pytest.mark.asyncio
    async def test_success_logs_status_and_content_chars(self, mock_emit_cloud_log):
        body = "# Title\n\n" + "Real paragraph that crosses the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://example.com/article")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["status"] == "success"
        assert kw["error_reason"] is None
        assert kw["content_chars"] == len(body)
        assert kw["url"] == "https://example.com/article"
        assert kw["original_url"] is None
        assert kw["cached"] is False
        assert kw["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_fragment_strip_does_not_set_original_url(self, mock_emit_cloud_log):
        """original_url is reserved for vertex unwrap rewrites only. Fragment
        stripping also changes the URL but is internal — must not leak into
        the log as a different `original_url`.
        """
        body = "# Title\n\n" + "Real paragraph that crosses the thin-content threshold. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://example.com/article#section")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["url"] == "https://example.com/article"
        assert kw["original_url"] is None

    @pytest.mark.asyncio
    async def test_upstream_http_code_extracted_by_regex(self, mock_emit_cloud_log):
        """Any 3-digit HTTP code Jina forwards should map to upstream_http_<code>,
        not just the previously-enumerated ones.
        """
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(
            "Warning: Target URL returned error 429: Too Many Requests"
        ))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://rate-limited.example/page")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["error_reason"] == "upstream_http_429"

    @pytest.mark.asyncio
    async def test_network_error_logs_network_error_reason(self, mock_emit_cloud_log):
        """httpx.RequestError (non-timeout) maps to a specific tag, not the
        catch-all `exception`.
        """
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("boom"))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://example.com/page")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["error_reason"] == "network_error"

    @pytest.mark.asyncio
    async def test_http_error_logs_http_status_reason(self, mock_emit_cloud_log):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("nope", status_code=404))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://example.com/missing")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["status"] == "error"
        assert kw["error_reason"] == "http_404"

    @pytest.mark.asyncio
    async def test_timeout_logs_timeout_reason(self, mock_emit_cloud_log):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("boom"))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://example.com/slow")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["error_reason"] == "timeout"
        assert kw["error_message"] == "Timeout fetching https://example.com/slow"

    @pytest.mark.asyncio
    async def test_domain_root_logs_domain_root_reason(self, mock_emit_cloud_log):
        # Bare domain — no Jina call expected, error_reason is domain_root.
        await fetch_web_content("https://example.com")
        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["status"] == "error"
        assert kw["error_reason"] == "domain_root"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("body,expected_reason", [
        ("Warning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\n", "upstream_http_403"),
        ("Warning: This page maybe requiring CAPTCHA", "upstream_captcha"),
        ("Just a moment...\n\nChecking your browser", "cloudflare_interstitial"),
        ("Title: x\n\n(Note: The provided HTML contains an iframe and only the title was extracted)", "iframe_spa"),
        ("\n".join(["Home", "About", "Contact", "* Login"]), "thin_content"),
    ])
    async def test_block_paths_log_specific_reasons(self, body, expected_reason, mock_emit_cloud_log):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content("https://blocked.example/page")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["error_reason"] == expected_reason

    @pytest.mark.asyncio
    async def test_vertex_unwrap_success_logs_original_url(self, mock_emit_cloud_log):
        redirect_resp = _mock_response("", status_code=302, headers={"Location": "https://trojmiasto.pl/article-n1.html"})
        article_body = "# Article\n\n" + "Real paragraph crossing the thin-content threshold easily. " * 5
        article_resp = _mock_response(article_body)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[redirect_resp, article_resp])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content(
                "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZxyz"
            )

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["status"] == "success"
        assert kw["url"] == "https://trojmiasto.pl/article-n1.html"
        assert kw["original_url"] == "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZxyz"

    @pytest.mark.asyncio
    async def test_vertex_unwrap_miss_overrides_other_error_reason(self, mock_emit_cloud_log):
        """When unwrap fails to return a Location, the input URL is sent to
        Jina unchanged. That fetch will produce some other error (thin
        content, http_xxx, etc.) — but the root cause is the unwrap miss
        and that's what we log.
        """
        # No Location header → unwrap returns the original URL.
        no_loc = _mock_response("", status_code=200, headers={})
        # Jina then returns junk that trips the iframe / SPA detector.
        junk = _mock_response("Title: x\n\n(Note: The provided HTML contains an iframe and only the title was extracted)")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[no_loc, junk])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            await fetch_web_content(
                "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZmiss"
            )

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["status"] == "error"
        # Root-cause tag, not the derived iframe_spa tag from the Jina body.
        assert kw["error_reason"] == "vertex_unwrap_miss"

    @pytest.mark.asyncio
    async def test_cache_hit_logs_cached_true(self, mock_emit_cloud_log):
        body = "# t\n\n" + "Real article paragraph crossing the thin-content threshold. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        set_fetch_run_id("run-log")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                await fetch_web_content("https://example.com/cache-hit")
                await fetch_web_content("https://example.com/cache-hit")
        finally:
            clear_fetch_cache_for_run("run-log")

        calls = [c for c in mock_emit_cloud_log.call_args_list if c.args[0] == "fetch_url"]
        assert len(calls) == 2
        assert calls[0].kwargs["cached"] is False
        assert calls[1].kwargs["cached"] is True

    @pytest.mark.asyncio
    async def test_internal_error_reason_not_returned_to_caller(self, mock_emit_cloud_log):
        """`_error_reason` is for the log only — the dict returned to the
        model must not carry implementation tags."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("nope", status_code=500))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/server-err")

        assert result["status"] == "error"
        assert "_error_reason" not in result

    @pytest.mark.asyncio
    async def test_run_id_included_in_log(self, mock_emit_cloud_log):
        body = "# t\n\n" + "Real article paragraph crossing the thin-content threshold. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        set_fetch_run_id("run-id-marker")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                await fetch_web_content("https://example.com/run-id-test")
        finally:
            clear_fetch_cache_for_run("run-id-marker")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["run_id"] == "run-id-marker"


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
        assert result["success_count"] == 3
        assert result["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_all_failed_batch_returns_error_status(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response("missing", status_code=404))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content_batch([
                "https://a.example/x",
                "https://b.example/y",
            ])

        assert result["status"] == "error"
        assert result["error_message"] == "All 2 sources failed to fetch"
        assert result["success_count"] == 0
        assert result["failed_count"] == 2
        assert [item["status"] for item in result["results"]] == ["error", "error"]

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
