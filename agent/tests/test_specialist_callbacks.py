"""Tests for specialist construction callbacks in specialists.py."""

from google.adk.tools import google_search, url_context

from superextra_agent.search_tools import search_and_read_public_pages, search_web
from superextra_agent.specialists import ALL_SPECIALISTS, CONTINUATION_SPECIALISTS
from superextra_agent.agent import _skip_enricher_if_cached
from superextra_agent.web_tools import (
    fetch_web_content,
    fetch_web_content_batch,
    read_public_page,
    read_public_pages,
    read_web_pages,
)


class FakeCallbackContext:
    """Minimal callback_context with state dict."""
    def __init__(self, state=None):
        self.state = state or {}


def test_specialists_accept_agenttool_request_context():
    """AgentTool sends the brief as the user message, so specialists must keep
    normal conversation contents enabled and avoid skip callbacks."""
    assert ALL_SPECIALISTS
    for specialist in ALL_SPECIALISTS:
        assert specialist.include_contents == "default"
        assert specialist.before_agent_callback is None


def test_web_research_specialists_have_search_and_page_reading_tools():
    for specialist in ALL_SPECIALISTS:
        if specialist.name in ("review_analyst", "dynamic_researcher_1"):
            continue
        assert google_search in specialist.tools
        assert url_context in specialist.tools
        assert read_web_pages in specialist.tools
        assert fetch_web_content in specialist.tools
        assert fetch_web_content_batch in specialist.tools


def test_pilot_dynamic_researcher_uses_serpapi_and_jina_only():
    pilot = next(agent for agent in ALL_SPECIALISTS if agent.name == "dynamic_researcher_1")

    assert pilot.tools == [search_and_read_public_pages, read_public_page, read_public_pages]
    assert search_and_read_public_pages in pilot.tools
    assert search_web not in pilot.tools
    assert google_search not in pilot.tools
    assert url_context not in pilot.tools
    assert read_web_pages not in pilot.tools
    assert fetch_web_content not in pilot.tools
    assert fetch_web_content_batch not in pilot.tools


def test_continuation_dynamic_researcher_keeps_existing_web_surface():
    continuation = next(
        agent for agent in CONTINUATION_SPECIALISTS if agent.name == "dynamic_researcher_1"
    )

    assert google_search in continuation.tools
    assert url_context in continuation.tools
    assert read_web_pages in continuation.tools
    assert fetch_web_content in continuation.tools
    assert fetch_web_content_batch in continuation.tools
    assert search_web not in continuation.tools


def test_skip_enricher_returns_cached_context():
    """Enricher skips and returns cached places_context when it exists."""
    ctx = FakeCallbackContext(state={"places_context": "Cached restaurant data"})
    result = _skip_enricher_if_cached(callback_context=ctx)
    assert result is not None
    assert result.parts[0].text == "Cached restaurant data"


def test_skip_enricher_runs_when_no_cache():
    """Enricher runs normally when no places_context in state."""
    ctx = FakeCallbackContext(state={})
    result = _skip_enricher_if_cached(callback_context=ctx)
    assert result is None
