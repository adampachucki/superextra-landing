"""Tests for web content fetching tools in web_tools.py."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from superextra_agent import web_tools
from superextra_agent.web_tools import (
    ADJUDICATOR_READ_CONCURRENCY,
    ADJUDICATOR_READ_RESULT_STATE_KEY,
    ADJUDICATOR_READ_STATE_KEY,
    MAX_BATCH,
    MAX_CONTENT_LENGTH,
    _read_adjudicator_pages,
    clear_fetch_cache_for_run,
    collect_adjudicator_packet_claims,
    fetch_web_content,
    fetch_web_content_batch,
    read_adjudicator_sources,
    read_public_page,
    read_public_pages,
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


def _validation_packet_for_urls(urls: list[str]) -> str:
    sources = ",".join(f'{{"url":"{url}","priority":"high"}}' for url in urls)
    source_urls = ",".join(f'"{url}"' for url in urls)
    return (
        "Finding.\n\n"
        "### Validation Packet\n\n"
        "```json\n"
        "{"
        f'"claims_for_validation":[{{"id":"claim-1","claim":"Claim","source_urls":[{source_urls}]}}],'
        f'"candidate_sources":[{sources}]'
        "}\n"
        "```"
    )


def _state_with_packet_urls(urls: list[str]) -> dict:
    return {"market_result": _validation_packet_for_urls(urls)}


@pytest.mark.parametrize(
    "heading",
    [
        "### **Validation Packet**",
        "### Validation Packet:",
        "### **Validation Packet:**",
    ],
)
def test_collect_adjudicator_packet_claims_accepts_packet_heading_variants(heading):
    packet = _validation_packet_for_urls(["https://example.com/source"]).replace(
        "### Validation Packet", heading
    )

    claims = collect_adjudicator_packet_claims({"market_result": packet})

    assert claims[0]["source_urls"] == ["https://example.com/source"]


def test_tool_docstrings_describe_source_reading_workflow():
    read_doc = " ".join((read_web_pages.__doc__ or "").split())
    fetch_doc = " ".join((fetch_web_content.__doc__ or "").split())
    batch_doc = " ".join((fetch_web_content_batch.__doc__ or "").split())
    read_public_doc = " ".join((read_public_page.__doc__ or "").split())
    read_public_batch_doc = " ".join((read_public_pages.__doc__ or "").split())
    adjudicator_doc = " ".join((read_adjudicator_sources.__doc__ or "").split())

    assert "Explicit structured reader for concrete public URLs" in read_doc
    assert "fetched-page source capture" in read_doc
    assert "Prefer this before raw Markdown fallback tools" in read_doc
    assert "Raw-Markdown fallback, not the normal page reader" in fetch_doc
    assert "Do not use this as the first read" in fetch_doc
    assert "Raw-Markdown fallback for multiple URLs" in batch_doc
    assert "prefer URL Context or `read_web_pages` first" in batch_doc
    assert "Primary page reader for concrete URLs discovered by search tools" in read_public_doc
    assert "Batch page reader for concrete URLs discovered by search tools" in read_public_batch_doc
    assert "Evidence Adjudicator's source queue" in adjudicator_doc
    assert "not a search tool" in adjudicator_doc


def test_source_reading_timeouts_are_short_bounded_attempts():
    assert web_tools.TIMEOUT_S == 15.0
    assert web_tools.JINA_READERLM_TIMEOUT_S == 8.0
    assert web_tools.URL_CONTEXT_MODEL == "gemini-3-flash-preview"
    assert web_tools.URL_CONTEXT_TIMEOUT_S == 27.0
    assert web_tools.URL_CONTEXT_HTTP_TIMEOUT_MS == 25_000
    assert web_tools.VERTEX_UNWRAP_TIMEOUT_S == 5.0


@pytest.mark.asyncio
async def test_read_public_page_wraps_jina_fetch_with_source():
    with patch(
        "superextra_agent.web_tools.fetch_web_content",
        AsyncMock(
            return_value={
                "status": "success",
                "url": "https://example.com/menu",
                "content": "Title: Lunch Menu\n\n# Menu\n\nLunch is daily.",
            }
        ),
    ):
        result = await read_public_page("https://example.com/menu")

    assert result["sources"] == [
        {
            "url": "https://example.com/menu",
            "title": "Lunch Menu",
            "domain": "example.com",
            "provider": "fetched_page",
        }
    ]


@pytest.mark.asyncio
async def test_read_public_pages_collects_successful_sources():
    with patch(
        "superextra_agent.web_tools.fetch_web_content_batch",
        AsyncMock(
            return_value={
                "status": "success",
                "results": [
                    {
                        "status": "success",
                        "url": "https://example.com/a",
                        "content": "# Page A\n\nText",
                    },
                    {
                        "status": "error",
                        "url": "https://example.com/b",
                        "error_message": "blocked",
                    },
                ],
                "success_count": 1,
                "failed_count": 1,
            }
        ),
    ):
        result = await read_public_pages(["https://example.com/a", "https://example.com/b"])

    assert result["sources"] == [
        {
            "url": "https://example.com/a",
            "title": "Page A",
            "domain": "example.com",
            "provider": "fetched_page",
        }
    ]


@pytest.mark.asyncio
async def test_read_adjudicator_pages_reads_above_public_batch_cap():
    urls = [f"https://example.com/{i}" for i in range(MAX_BATCH + 2)]

    async def fetch(
        url,
        *,
        allow_readerlm,
        allow_domain_root=False,
        allow_proxy_fallback=False,
    ):
        return {
            "status": "success",
            "url": url,
            "content": f"Title: {url.rsplit('/', 1)[-1]}\n\nText",
        }

    with patch("superextra_agent.web_tools._fetch_web_content", fetch):
        result = await _read_adjudicator_pages(urls)

    assert result["status"] == "success"
    assert result["success_count"] == len(urls)
    assert result["failed_count"] == 0
    assert [item["url"] for item in result["results"]] == urls
    assert [source["url"] for source in result["sources"]] == urls


@pytest.mark.asyncio
async def test_read_adjudicator_pages_allows_restaurant_homepage_roots():
    url = "https://restaurant.example/"

    async def fetch(
        url,
        *,
        allow_readerlm,
        allow_domain_root=False,
        allow_proxy_fallback=False,
    ):
        assert allow_domain_root is True
        assert allow_proxy_fallback is True
        return {
            "status": "success",
            "url": url,
            "content": "Title: Restaurant\n\nMenu item " * 80,
        }

    with patch("superextra_agent.web_tools._fetch_web_content", fetch):
        result = await _read_adjudicator_pages([url])

    assert result["status"] == "success"
    assert result["success_count"] == 1
    assert result["sources"][0]["url"] == url


@pytest.mark.asyncio
async def test_read_adjudicator_pages_preserves_requested_url_after_unwrap():
    requested = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    resolved = "https://example.com/article"

    async def fetch(
        url,
        *,
        allow_readerlm,
        allow_domain_root=False,
        allow_proxy_fallback=False,
    ):
        return {
            "status": "success",
            "url": resolved,
            "content": "Title: Article\n\nText",
        }

    with patch("superextra_agent.web_tools._fetch_web_content", fetch):
        result = await _read_adjudicator_pages([requested])

    assert result["results"][0]["url"] == resolved
    assert result["results"][0]["requested_url"] == requested
    assert result["sources"][0]["url"] == resolved


@pytest.mark.asyncio
async def test_read_adjudicator_sources_attempts_all_eligible_urls():
    urls = [f"https://example.com/{i}" for i in range(ADJUDICATOR_READ_CONCURRENCY + 2)]
    run_id = "run-captured-eligible"
    tool_context = SimpleNamespace(state=_state_with_packet_urls(urls))
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, urls)
    read_result = {
        "status": "success",
        "results": [
            {"status": "success", "url": url, "content": "# Source\n\nText"}
            for url in urls
        ],
        "sources": [
            {
                "url": url,
                "title": "Source",
                "domain": "example.com",
                "provider": "fetched_page",
            }
            for url in urls
        ],
        "success_count": len(urls),
        "failed_count": 0,
    }

    with patch(
        "superextra_agent.web_tools._read_adjudicator_pages",
        AsyncMock(return_value=read_result),
    ) as read_pages:
        try:
            result = await read_adjudicator_sources(urls, tool_context=tool_context)
        finally:
            clear_fetch_cache_for_run(run_id)

    read_pages.assert_awaited_once_with(urls)
    assert result["status"] == "success"
    assert result["attempted_count"] == len(urls)
    assert result["skipped_urls"] == []
    assert tool_context.state[ADJUDICATOR_READ_STATE_KEY] == urls
    assert tool_context.state[ADJUDICATOR_READ_RESULT_STATE_KEY] == {
        "status": "success",
        "requested_count": len(urls),
        "attempted_count": len(urls),
        "successful_count": len(urls),
        "failed_count": 0,
        "sources": read_result["sources"],
        "failed_sources": [],
        "skipped_urls": [],
        "skipped_count": 0,
        "auto_appended_urls": [],
        "auto_appended_count": 0,
        "rejected_urls": [],
        "rejected_count": 0,
        "invalid_urls": [],
        "invalid_count": 0,
        "error_message": None,
    }


@pytest.mark.asyncio
async def test_read_adjudicator_sources_reports_invalid_input():
    tool_context = SimpleNamespace(state={})

    with patch("superextra_agent.web_tools._read_adjudicator_pages", AsyncMock()) as read_pages:
        result = await read_adjudicator_sources(
            ["not-a-url", "ftp://example.com/file"], tool_context=tool_context
        )

    read_pages.assert_not_awaited()
    assert result["status"] == "error"
    assert result["attempted_count"] == 0
    assert result["invalid_count"] == 2
    assert result["error_message"] == "No valid new adjudicator URLs to read"


def test_collect_adjudicator_packet_claims_extracts_specialist_claims():
    state = {
        "market_result": (
            "Finding.\n\n"
            "### Validation Packet\n\n"
            "```json\n"
            "{"
            '"claims_for_validation":['
            '{"id":"claim-1","claim":"Target opened in May 2026",'
            '"source_urls":["https://example.com/open#details"],'
            '"provider_refs":["Google Places: target"]}'
            "],"
            '"candidate_sources":[{"url":"https://example.com/open"}]'
            "}\n"
            "```"
        )
    }

    claims = collect_adjudicator_packet_claims(state)

    assert claims == [
        {
            "id": "claim-1",
            "claim": "Target opened in May 2026",
            "specialists": ["market_result"],
            "specialist_label": "Market Landscape",
            "source_urls": ["https://example.com/open"],
            "provider_refs": ["Google Places: target"],
        }
    ]


@pytest.mark.asyncio
async def test_read_adjudicator_sources_does_not_unwrap_during_queue_filtering():
    urls = [
        f"https://vertexaisearch.cloud.google.com/grounding-api-redirect/{i}"
        for i in range(ADJUDICATOR_READ_CONCURRENCY + 2)
    ]
    run_id = "run-captured-redirects"
    tool_context = SimpleNamespace(state=_state_with_packet_urls(urls))
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, urls)

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(return_value={"status": "success", "results": [], "sources": []}),
        ) as read_pages, patch(
            "superextra_agent.web_tools._unwrap_vertex_redirect",
            AsyncMock(side_effect=AssertionError("wrapper should not unwrap over-limit URLs")),
        ) as unwrap:
            result = await read_adjudicator_sources(urls, tool_context=tool_context)
    finally:
        clear_fetch_cache_for_run(run_id)

    read_pages.assert_awaited_once_with(urls)
    unwrap.assert_not_awaited()
    assert result["attempted_count"] == len(urls)
    assert result["skipped_count"] == 0


@pytest.mark.asyncio
async def test_read_adjudicator_sources_rejects_unknown_urls():
    allowed = "https://example.com/allowed"
    extra = "https://example.com/packet-only"
    run_id = "run-reject-packet-only"
    tool_context = SimpleNamespace(state=_state_with_packet_urls([allowed, extra]))
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, [allowed])

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(return_value={"status": "success", "results": [], "sources": []}),
        ) as read_pages:
            result = await read_adjudicator_sources(
                [extra, allowed], tool_context=tool_context
            )
    finally:
        clear_fetch_cache_for_run(run_id)

    read_pages.assert_awaited_once_with([allowed])
    assert result["status"] == "success"
    assert result["attempted_count"] == 1
    assert result["rejected_count"] == 1
    assert result["rejected_urls"] == [extra]


@pytest.mark.asyncio
async def test_read_adjudicator_sources_ignores_packet_urls_and_appends_captured_urls():
    run_id = "run-auto-append"
    packet_url = "https://example.com/requested"
    omitted_packet_url = "https://example.com/omitted-packet"
    grounding_url = "https://example.com/grounded"
    tool_context = SimpleNamespace(
        state=_state_with_packet_urls([packet_url, omitted_packet_url])
    )
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(
        run_id,
        [{"url": grounding_url, "title": "Grounded"}],
    )

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(return_value={"status": "success", "results": [], "sources": []}),
        ) as read_pages:
            result = await read_adjudicator_sources(
                [packet_url], tool_context=tool_context
            )
    finally:
        clear_fetch_cache_for_run(run_id)

    read_pages.assert_awaited_once_with([grounding_url])
    assert result["attempted_count"] == 1
    assert result["rejected_urls"] == [packet_url]
    assert result["auto_appended_urls"] == [grounding_url]
    assert tool_context.state[ADJUDICATOR_READ_STATE_KEY] == [
        grounding_url,
    ]


@pytest.mark.asyncio
async def test_read_adjudicator_sources_can_read_allowed_queue_from_empty_request():
    run_id = "run-empty-request"
    packet_url = "https://example.com/packet"
    grounding_url = "https://example.com/grounding"
    tool_context = SimpleNamespace(state=_state_with_packet_urls([packet_url]))
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, [grounding_url])

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(return_value={"status": "success", "results": [], "sources": []}),
        ) as read_pages:
            result = await read_adjudicator_sources([], tool_context=tool_context)
    finally:
        clear_fetch_cache_for_run(run_id)

    read_pages.assert_awaited_once_with([grounding_url])
    assert result["status"] == "success"
    assert result["requested_count"] == 0
    assert result["attempted_count"] == 1
    assert result["valid_url_count"] == 0
    assert result["auto_appended_urls"] == [grounding_url]


@pytest.mark.asyncio
async def test_read_adjudicator_sources_keeps_read_success_for_title_mismatch():
    url = "https://example.com/expected-article"
    run_id = "run-title-mismatch"
    packet = (
        "Finding.\n\n"
        "### Validation Packet\n\n"
        "```json\n"
        "{"
        '"claims_for_validation":[{"id":"claim-1","claim":"Claim","source_urls":["https://example.com/expected-article"]}],'
        '"candidate_sources":[{"url":"https://example.com/expected-article","title":"Expected Restaurant Closure"}]'
        "}\n"
        "```"
    )
    tool_context = SimpleNamespace(
        state={"market_result": packet}
    )
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, [url])

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(
                return_value={
                    "status": "success",
                    "results": [
                        {
                            "status": "success",
                            "url": url,
                            "content": "Title: Unrelated Election Deadlines\n\nText",
                        }
                    ],
                    "sources": [
                        {
                            "url": url,
                            "title": "Unrelated Election Deadlines",
                            "domain": "example.com",
                            "provider": "fetched_page",
                        }
                    ],
                    "success_count": 1,
                    "failed_count": 0,
                }
            ),
        ):
            result = await read_adjudicator_sources([url], tool_context=tool_context)
    finally:
        clear_fetch_cache_for_run(run_id)

    assert result["status"] == "success"
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert result["sources"] == [
        {
            "url": url,
            "title": "Unrelated Election Deadlines",
            "domain": "example.com",
            "provider": "fetched_page",
        }
    ]
    compact = tool_context.state[ADJUDICATOR_READ_RESULT_STATE_KEY]
    assert compact["successful_count"] == 1
    assert compact["sources"][0]["url"] == url
    assert compact["failed_sources"] == []


@pytest.mark.asyncio
async def test_read_adjudicator_sources_keeps_read_success_for_slug_title_mismatch():
    url = "https://example.com/Trojmiasto-zegna-kolejne-restauracje-i-kawiarnie-n202753.html"
    run_id = "run-slug-title-mismatch"
    packet = (
        "Finding.\n\n"
        "### Validation Packet\n\n"
        "```json\n"
        "{"
        '"claims_for_validation":[{"id":"claim-1","claim":"Claim","source_urls":["'
        + url
        + '"]}],'
        '"candidate_sources":[]'
        "}\n"
        "```"
    )
    tool_context = SimpleNamespace(
        state={"market_result": packet}
    )
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, [url])

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(
                return_value={
                    "status": "success",
                    "results": [
                        {
                            "status": "success",
                            "url": url,
                            "content": "Title: Wody Polskie przenoszą się do Trytona\n\nText",
                        }
                    ],
                    "sources": [
                        {
                            "url": url,
                            "title": "Wody Polskie przenoszą się do Trytona",
                            "domain": "example.com",
                            "provider": "fetched_page",
                        }
                    ],
                    "success_count": 1,
                    "failed_count": 0,
                }
            ),
        ):
            result = await read_adjudicator_sources([url], tool_context=tool_context)
    finally:
        clear_fetch_cache_for_run(run_id)

    assert result["status"] == "success"
    assert result["success_count"] == 1
    assert result["failed_count"] == 0
    assert result["sources"] == [
        {
            "url": url,
            "title": "Wody Polskie przenoszą się do Trytona",
            "domain": "example.com",
            "provider": "fetched_page",
        }
    ]


@pytest.mark.asyncio
async def test_read_adjudicator_sources_requires_packet_state():
    with patch("superextra_agent.web_tools._read_adjudicator_pages", AsyncMock()) as read_pages:
        result = await read_adjudicator_sources(["https://example.com/arbitrary"])

    read_pages.assert_not_awaited()
    assert result["status"] == "error"
    assert result["attempted_count"] == 0
    assert result["error_message"] == "Run state is required to read adjudicator sources"


@pytest.mark.asyncio
async def test_read_adjudicator_sources_dedupes_across_followup_calls():
    run_id = "run-dedupe-captured"
    tool_context = SimpleNamespace(
        state=_state_with_packet_urls(
            [
                "https://example.com/a",
                "https://example.com/new",
            ]
        )
    )
    first_urls = ["https://example.com/a", "https://example.com/new"]
    set_fetch_run_id(run_id)
    web_tools.record_adjudicator_source_candidates(run_id, first_urls)

    try:
        with patch(
            "superextra_agent.web_tools._read_adjudicator_pages",
            AsyncMock(
                return_value={
                    "status": "success",
                    "results": [
                        {
                            "status": "success",
                            "url": "https://example.com/a",
                            "content": "# A\n\nText",
                        },
                        {
                            "status": "success",
                            "url": "https://example.com/new",
                            "content": "# New\n\nText",
                        }
                    ],
                    "sources": [
                        {
                            "url": "https://example.com/a",
                            "title": "A",
                            "domain": "example.com",
                            "provider": "fetched_page",
                        },
                        {
                            "url": "https://example.com/new",
                            "title": "New",
                            "domain": "example.com",
                            "provider": "fetched_page",
                        }
                    ],
                    "success_count": 2,
                    "failed_count": 0,
                }
            ),
        ) as read_pages:
            first = await read_adjudicator_sources(first_urls, tool_context=tool_context)

        read_pages.assert_awaited_once_with(["https://example.com/a", "https://example.com/new"])
        assert first["attempted_count"] == 2

        with patch("superextra_agent.web_tools._read_adjudicator_pages", AsyncMock()) as read_pages:
            second = await read_adjudicator_sources(
                ["https://example.com/a", "https://example.com/new"],
                tool_context=tool_context,
            )
    finally:
        clear_fetch_cache_for_run(run_id)

    read_pages.assert_not_awaited()
    assert second["status"] == "success"
    assert second["attempted_count"] == 0
    assert second["skipped_urls"] == ["https://example.com/a", "https://example.com/new"]
    assert tool_context.state[ADJUDICATOR_READ_RESULT_STATE_KEY] == {
        "status": "success",
        "requested_count": 4,
        "attempted_count": 2,
        "successful_count": 2,
        "failed_count": 0,
        "sources": [
            {
                "url": "https://example.com/a",
                "title": "A",
                "domain": "example.com",
                "provider": "fetched_page",
            },
            {
                "url": "https://example.com/new",
                "title": "New",
                "domain": "example.com",
                "provider": "fetched_page",
            },
        ],
        "failed_sources": [],
        "skipped_urls": ["https://example.com/a", "https://example.com/new"],
        "skipped_count": 2,
        "auto_appended_urls": [],
        "auto_appended_count": 0,
        "rejected_urls": [],
        "rejected_count": 0,
        "invalid_urls": [],
        "invalid_count": 0,
        "error_message": None,
    }


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
    async def test_failed_read_cache_reused_across_goals(self):
        set_fetch_run_id("run-read-error-cache")
        try:
            with patch(
                "superextra_agent.web_tools._read_web_pages_sync",
                side_effect=RuntimeError("boom"),
            ) as read_sync:
                first = await read_web_pages(["https://example.com/menu"], "lead goal")
                second = await read_web_pages(
                    ["https://example.com/menu"],
                    "specialist follow-up goal",
                )
        finally:
            clear_fetch_cache_for_run("run-read-error-cache")

        assert first["status"] == "error"
        assert second["status"] == "error"
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

    def test_url_context_sync_uses_metadata_url_over_model_returned_url(self):
        response = SimpleNamespace(
            text=(
                '{"results":[{"url":"https://example.com/menu",'
                '"retrieved_url":"https://fabricated.example/page",'
                '"title":"Fabricated","evidence_summary":"Lunch is daily.",'
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
        assert result["sources"] == [
            {
                "url": "https://example.com/menu",
                "title": "Fabricated",
                "domain": "example.com",
                "provider": "fetched_page",
            }
        ]
        assert result["results"][0]["retrieved_url"] == "https://example.com/menu"

    def test_url_context_sync_rejects_explicit_model_url_without_metadata_match(self):
        response = SimpleNamespace(
            text=(
                '{"results":['
                '{"url":"https://fabricated.example/page",'
                '"retrieved_url":"https://fabricated.example/page",'
                '"title":"Fabricated","evidence_summary":"Fake",'
                '"specific_facts":["Fake"],"supporting_details":[],"limits":""},'
                '{"url":"https://example.com/a","retrieved_url":"https://example.com/a",'
                '"title":"A","evidence_summary":"A summary",'
                '"specific_facts":["A fact"],"supporting_details":[],"limits":""}'
                '],"overall_limits":""}'
            ),
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://example.com/b",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
                            ),
                            SimpleNamespace(
                                retrieved_url="https://example.com/a",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
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
                ["https://example.com/a", "https://example.com/b"],
                "menu facts",
            )

        assert result["status"] == "success"
        assert result["results"][0]["status"] == "error"
        assert result["results"][0]["retrieval_status"] == ""
        assert "_url_from_fallback" not in result["results"][0]
        assert result["sources"] == [
            {
                "url": "https://example.com/a",
                "title": "A",
                "domain": "example.com",
                "provider": "fetched_page",
            }
        ]

    def test_url_context_sync_allows_positional_metadata_when_model_omits_url(self):
        response = SimpleNamespace(
            text=(
                '{"results":[{"title":"Menu","evidence_summary":"Lunch is daily.",'
                '"specific_facts":["Lunch daily"],"supporting_details":[],"limits":""}],'
                '"overall_limits":""}'
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
        assert result["results"][0]["retrieved_url"] == "https://example.com/menu"
        assert "_url_from_fallback" not in result["results"][0]

    def test_url_context_sync_allows_positional_metadata_when_model_returns_empty_url(self):
        response = SimpleNamespace(
            text=(
                '{"results":['
                '{"url":"","retrieved_url":"","title":"A","evidence_summary":"A summary",'
                '"specific_facts":[],"supporting_details":[],"limits":""},'
                '{"url":"","retrieved_url":"","title":"B","evidence_summary":"B summary",'
                '"specific_facts":[],"supporting_details":[],"limits":""}'
                '],"overall_limits":""}'
            ),
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://example.com/a",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
                            ),
                            SimpleNamespace(
                                retrieved_url="https://example.com/b",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
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
                ["https://example.com/a", "https://example.com/b"],
                "menu facts",
            )

        assert result["status"] == "success"
        assert [source["url"] for source in result["sources"]] == [
            "https://example.com/a",
            "https://example.com/b",
        ]

    def test_url_context_sync_uses_positional_metadata_when_retrieved_url_empty(self):
        response = SimpleNamespace(
            text=(
                '{"results":[{"url":"https://example.com/a","retrieved_url":"",'
                '"title":"A","evidence_summary":"A summary",'
                '"specific_facts":[],"supporting_details":[],"limits":""}],'
                '"overall_limits":""}'
            ),
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://cdn.example.com/a",
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
                ["https://example.com/a"],
                "menu facts",
            )

        assert result["status"] == "success"
        assert result["results"][0]["retrieved_url"] == "https://cdn.example.com/a"
        assert result["sources"][0]["url"] == "https://cdn.example.com/a"

    def test_url_context_sync_unstructured_fallback_keeps_all_successful_metadata(self):
        response = SimpleNamespace(
            text="Unstructured combined evidence text.",
            candidates=[
                SimpleNamespace(
                    url_context_metadata=SimpleNamespace(
                        url_metadata=[
                            SimpleNamespace(
                                retrieved_url="https://example.com/a",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
                            ),
                            SimpleNamespace(
                                retrieved_url="https://example.com/b",
                                url_retrieval_status="URL_RETRIEVAL_STATUS_SUCCESS",
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
                ["https://example.com/a", "https://example.com/b"],
                "menu facts",
            )

        assert result["status"] == "success"
        assert [source["url"] for source in result["sources"]] == [
            "https://example.com/a",
            "https://example.com/b",
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

    def test_url_context_sync_rejects_structured_result_without_metadata(self):
        response = SimpleNamespace(
            text=(
                '{"results":[{"url":"https://example.com/menu",'
                '"retrieved_url":"https://example.com/menu",'
                '"title":"Menu","evidence_summary":"Lunch is daily.",'
                '"specific_facts":["Lunch daily"],"supporting_details":[],'
                '"limits":""}],"overall_limits":""}'
            ),
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
        assert result["results"][0]["status"] == "error"
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
        # Fast plain Reader is the normal path; readerlm-v2 is only a fallback
        # for thin/noisy extraction.
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Accept") == "text/markdown"
        assert "X-Respond-With" not in headers
        assert headers.get("Authorization") == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_readerlm_fallback_uses_api_key(self, mock_emit_cloud_log):
        thin = "\n".join(["Home", "About", "Contact"])
        rich = "# Title\n\n" + "Paragraph content. " * 20
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[_mock_response(thin), _mock_response(rich)])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await fetch_web_content("https://example.com/page")

        assert result["status"] == "success"
        assert mock_client.get.call_count == 2
        plain_headers = mock_client.get.call_args_list[0].kwargs.get("headers", {})
        assert "X-Respond-With" not in plain_headers
        assert plain_headers.get("Authorization") == "Bearer test-key-123"
        readerlm_headers = mock_client.get.call_args_list[1].kwargs.get("headers", {})
        assert readerlm_headers.get("X-Respond-With") == "readerlm-v2"
        assert readerlm_headers.get("Authorization") == "Bearer test-key-123"

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["reader_mode"] == "readerlm-v2"
        assert kw["fallback_reason"] == "thin_content"

    @pytest.mark.asyncio
    async def test_consent_noise_uses_readerlm_fallback(self, mock_emit_cloud_log):
        noisy = (
            "Title: Monsun\n\n# Monsun Gdynia\n\n"
            "Cenimy prywatność użytkowników. Wraz z naszymi 1722 partnerami używamy plików cookie.\n\n"
            + "Navigation item. " * 200
        )
        clean = "# Monsun Gdynia\n\n" + "Clean listing paragraph with address and menu details. " * 40
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[_mock_response(noisy), _mock_response(clean)])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await fetch_web_content("https://www.trojmiasto.pl/Monsun-o96445.html")

        assert result["status"] == "success"
        assert result["content"] == clean
        assert mock_client.get.call_count == 2

        readerlm_headers = mock_client.get.call_args_list[1].kwargs.get("headers", {})
        assert readerlm_headers.get("X-Respond-With") == "readerlm-v2"
        assert readerlm_headers.get("Authorization") == "Bearer test-key-123"

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["reader_mode"] == "readerlm-v2"
        assert kw["fallback_reason"] == "consent_noise"
        assert kw["fallback_status"] is None

    @pytest.mark.asyncio
    async def test_consent_noise_keeps_plain_when_readerlm_is_worse(self, mock_emit_cloud_log):
        noisy = (
            "Title: Listing\n\n# Listing\n\n"
            "Ta strona korzysta z ciasteczek. Dalsze korzystanie ze strony oznacza, że zgadzasz się.\n\n"
            + "Usable public listing detail. " * 80
        )
        thin = "Title: Listing\n\nHome\nAbout\nContact"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[_mock_response(noisy), _mock_response(thin)])

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await fetch_web_content("https://example.com/listing")

        assert result["status"] == "success"
        assert result["content"] == noisy
        assert mock_client.get.call_count == 2

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["reader_mode"] == "plain"
        assert kw["fallback_reason"] == "consent_noise"
        assert kw["fallback_status"] == "error"
        assert kw["fallback_error_reason"] == "thin_content"

    @pytest.mark.asyncio
    async def test_login_gate_does_not_use_readerlm_fallback(self, mock_emit_cloud_log):
        login = (
            "Title: X\n\n# X\n\nDon’t miss what’s happening\n"
            "People on X are the first to know. Log in Sign up"
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(login))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await fetch_web_content("https://x.com/example/status/1")

        assert result["status"] == "error"
        assert "login" in result["error_message"]
        assert mock_client.get.call_count == 1

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["error_reason"] == "login_required"
        assert kw["fallback_reason"] is None

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
    async def test_jina_billing_error_is_specific(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(
                "InsufficientBalanceError: Account balance not enough to run this query",
                status_code=402,
            )
        )

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
            result = await fetch_web_content("https://example.com/page")

        assert result["status"] == "error"
        assert "account balance is insufficient" in result["error_message"]

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
        ("Wyłącz AdBlocka/uBlocka, aby czytać artykuły", "adblock"),
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
    async def test_public_fetch_does_not_proxy_fallback_for_upstream_403(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            return_value=_mock_response(
                "Warning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\n"
            )
        )

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await fetch_web_content("https://blocked.example/page")

        assert result["status"] == "error"
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_adjudicator_reader_uses_proxy_fallback_for_upstream_403(
        self, mock_emit_cloud_log
    ):
        blocked = "Warning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\n"
        content = "# Menu\n\n" + "Chinese Wok menu and delivery details. " * 30
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[_mock_response(blocked), _mock_response(content)]
        )

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await _read_adjudicator_pages(
                ["https://www.pyszne.pl/menu/chinese-wok"]
            )

        assert result["status"] == "success"
        assert result["success_count"] == 1
        assert mock_client.get.call_count == 2
        proxy_headers = mock_client.get.call_args_list[1].kwargs.get("headers", {})
        assert proxy_headers["X-Proxy"] == "auto"
        assert proxy_headers["Authorization"] == "Bearer test-key-123"

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["reader_mode"] == "plain_proxy"
        assert kw["fallback_reason"] == "upstream_http_403"

    @pytest.mark.asyncio
    async def test_adjudicator_proxy_fallback_keeps_original_error_when_blocked(
        self, mock_emit_cloud_log
    ):
        blocked = "Warning: Target URL returned error 403: Forbidden\n\nMarkdown Content:\n"
        still_blocked = "Just a moment...\n\nChecking your browser"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[_mock_response(blocked), _mock_response(still_blocked)]
        )

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await _read_adjudicator_pages(["https://blocked.example/page"])

        assert result["status"] == "error"
        assert result["results"][0]["error_message"].endswith("upstream HTTP 403")

        kw = _log_kwargs(mock_emit_cloud_log)
        assert kw["reader_mode"] == "plain"
        assert kw["fallback_reason"] == "upstream_http_403"
        assert kw["fallback_error_reason"] == "cloudflare_interstitial"

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
        mock_client.get = AsyncMock(side_effect=[no_loc, article_resp, article_resp])

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
    async def test_deep_read_reuses_fast_cache_without_repeating_plain_fetch(self):
        noisy = (
            "Title: Listing\n\n# Listing\n\n"
            "Ta strona korzysta z ciasteczek. Dalsze korzystanie ze strony oznacza, że zgadzasz się.\n\n"
            + "Usable public listing detail. " * 80
        )
        clean = "# Listing\n\n" + "Clean listing paragraph with concrete details. " * 80
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=[_mock_response(noisy), _mock_response(clean)])

        set_fetch_run_id("run-fast-then-deep")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
                 patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
                batch = await fetch_web_content_batch(["https://example.com/listing"])
                deep = await fetch_web_content("https://example.com/listing")
        finally:
            clear_fetch_cache_for_run("run-fast-then-deep")

        assert batch["status"] == "success"
        assert batch["results"][0]["content"] == noisy
        assert deep["status"] == "success"
        assert deep["content"] == clean
        assert mock_client.get.call_count == 2
        assert "X-Respond-With" not in mock_client.get.call_args_list[0].kwargs["headers"]
        assert mock_client.get.call_args_list[1].kwargs["headers"]["X-Respond-With"] == "readerlm-v2"

    @pytest.mark.asyncio
    async def test_batch_read_reuses_plain_pass_from_prior_deep_read(self):
        body = "# Title\n\n" + "Real paragraph that crosses the thin-content threshold easily. " * 5
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(body))

        set_fetch_run_id("run-deep-then-fast")
        try:
            with patch("superextra_agent.web_tools._get_client", return_value=mock_client):
                deep = await fetch_web_content("https://example.com/article")
                batch = await fetch_web_content_batch(["https://example.com/article"])
        finally:
            clear_fetch_cache_for_run("run-deep-then-fast")

        assert deep["status"] == "success"
        assert batch["status"] == "success"
        assert batch["results"][0]["cached"] is True
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
        assert kw["reader_mode"] == "plain"
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
        ("Wyłącz AdBlocka/uBlocka, aby czytać artykuły", "adblock_wall"),
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
    async def test_batch_does_not_use_readerlm_fallback_for_noisy_success(self):
        noisy = (
            "Title: Listing\n\n# Listing\n\n"
            "Cenimy prywatność użytkowników. Wraz z naszymi 1722 partnerami używamy plików cookie.\n\n"
            + "Usable public listing detail. " * 80
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=_mock_response(noisy))

        with patch("superextra_agent.web_tools._get_client", return_value=mock_client), \
             patch.dict("os.environ", {"JINA_API_KEY": "test-key-123"}):
            result = await fetch_web_content_batch(["https://example.com/listing"])

        assert result["status"] == "success"
        assert result["results"][0]["content"] == noisy
        assert mock_client.get.call_count == 1
        headers = mock_client.get.call_args.kwargs.get("headers", {})
        assert "X-Respond-With" not in headers
        assert headers.get("Authorization") == "Bearer test-key-123"

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
