"""Tests for specialist construction callbacks in specialists.py."""

from superextra_agent.specialists import ALL_SPECIALISTS, CONTINUATION_SPECIALISTS
from superextra_agent.agent import _skip_enricher_if_cached
from superextra_agent.web_tools import read_discovered_sources, search_public_web


class FakeCallbackContext:
    """Minimal callback_context with state dict."""
    def __init__(self, state=None):
        self.state = state or {}


def _tool_names(tools):
    return [getattr(tool, "name", getattr(tool, "__name__", "")) for tool in tools]


def test_specialists_accept_agenttool_request_context():
    """AgentTool sends the brief as the user message, so specialists must keep
    normal conversation contents enabled and avoid skip callbacks."""
    assert ALL_SPECIALISTS
    for specialist in ALL_SPECIALISTS:
        assert specialist.include_contents == "default"
        assert specialist.before_agent_callback is None


def test_web_research_specialists_use_search_and_captured_reader():
    for specialist in ALL_SPECIALISTS:
        if specialist.name == "review_analyst":
            continue
        assert specialist.tools == [search_public_web, read_discovered_sources]


def test_first_turn_specialists_do_not_expose_raw_fetch_tools():
    forbidden = {
        "search_web",
        "search_and_read_public_pages",
        "fetch_web_content",
        "fetch_web_content_batch",
        "read_public_page",
        "read_public_pages",
    }

    for specialist in ALL_SPECIALISTS:
        assert forbidden.isdisjoint(_tool_names(specialist.tools))


def test_continuation_dynamic_researcher_uses_search_and_captured_reader():
    continuation = next(
        agent for agent in CONTINUATION_SPECIALISTS if agent.name == "dynamic_researcher_1"
    )

    assert continuation.tools == [search_public_web, read_discovered_sources]


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
