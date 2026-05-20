"""Tests for specialist construction callbacks in specialists.py."""

from google.adk.tools import google_search, url_context

from superextra_agent.specialists import ALL_SPECIALISTS, CONTINUATION_SPECIALISTS
from superextra_agent.agent import _skip_enricher_if_cached
from superextra_agent.specialist_catalog import SPECIALISTS

_SPECIALISTS_WITH_CUSTOM_TOOLS = {"review_analyst", "social_analyst"}
NATIVE_INITIAL_SPECIALISTS = {
    specialist.name
    for specialist in SPECIALISTS
    if specialist.name not in _SPECIALISTS_WITH_CUSTOM_TOOLS
}


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


def test_first_turn_public_web_specialists_use_native_search_and_url_context():
    specialists = [
        agent for agent in ALL_SPECIALISTS if agent.name in NATIVE_INITIAL_SPECIALISTS
    ]

    assert {agent.name for agent in specialists} == NATIVE_INITIAL_SPECIALISTS
    for specialist in specialists:
        assert _tool_names(specialist.tools) == [
            "google_search",
            "url_context",
        ]


def test_first_turn_specialists_do_not_expose_raw_fetch_tools():
    forbidden = {
        "search_web",
        "search_public_web",
        "fetch_web_content",
        "fetch_web_content_batch",
        "read_public_page",
        "read_public_pages",
    }

    for specialist in ALL_SPECIALISTS:
        assert forbidden.isdisjoint(_tool_names(specialist.tools))


def test_first_turn_public_web_specialists_do_not_use_custom_reader():
    for specialist in ALL_SPECIALISTS:
        if specialist.name == "review_analyst":
            continue
        assert "search_public_web" not in _tool_names(specialist.tools)


def test_continuation_public_web_specialists_use_native_search_and_url_context():
    specialists = [
        agent for agent in CONTINUATION_SPECIALISTS if agent.name in NATIVE_INITIAL_SPECIALISTS
    ]

    assert {agent.name for agent in specialists} == NATIVE_INITIAL_SPECIALISTS
    for specialist in specialists:
        assert specialist.tools == [google_search, url_context]


def test_social_analyst_has_tripadvisor_resolver_in_both_turns():
    """social_analyst must reach TripAdvisor via the verified resolver, not by
    guessing URLs or relying on google_search alone (A/B-tested: search-only
    discovery times out >70% of the time, resolver hits 90%+)."""
    for specialists in (ALL_SPECIALISTS, CONTINUATION_SPECIALISTS):
        social = next(s for s in specialists if s.name == "social_analyst")
        names = _tool_names(social.tools)
        assert "find_tripadvisor_restaurant" in names
        assert "fetch_tripadvisor_page" in names


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
