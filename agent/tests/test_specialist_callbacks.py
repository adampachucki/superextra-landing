"""Tests for specialist construction callbacks in specialists.py."""

from google.adk.tools import google_search, url_context

from superextra_agent.specialists import ALL_SPECIALISTS, CONTINUATION_SPECIALISTS
from superextra_agent.agent import _skip_enricher_if_cached
from superextra_agent.specialist_catalog import SPECIALISTS

_SPECIALISTS_WITH_CUSTOM_TOOLS = {
    "review_analyst",
    "social_analyst",
}
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


def test_social_analyst_uses_serpapi_for_discovery_in_both_turns():
    """social_analyst's discovery backend is SerpAPI (A/B-tested 2026-05-21:
    Gemini google_search times out 8/10 on TripAdvisor; SerpAPI engine=google
    hits 10/10 across TA + IG + FB). One unified search backend, no per-
    platform resolvers. Native google_search is intentionally excluded for
    this specialist."""
    for specialists in (ALL_SPECIALISTS, CONTINUATION_SPECIALISTS):
        social = next(s for s in specialists if s.name == "social_analyst")
        names = _tool_names(social.tools)
        assert "search_serpapi" in names
        assert "fetch_tripadvisor_page" in names
        assert "fetch_facebook_page" in names
        assert "fetch_instagram_profile" in names
        # Native search is unreliable for TripAdvisor; SerpAPI replaces it here.
        assert "google_search" not in names
        # fetch_tiktok_video was dropped — discovery for per-video URLs is
        # unreliable on both backends; tool itself was removed.
        assert "fetch_tiktok_video" not in names


def test_review_analyst_uses_serpapi_for_tripadvisor_discovery():
    """review_analyst's TA discovery unified on SerpAPI: search_serpapi finds
    the venue's Restaurant_Review URL, get_tripadvisor_reviews(url) pulls
    reviews. find_tripadvisor_restaurant was deleted along with its name/coord
    verification machinery — the model handles candidate fit via snippets."""
    for specialists in (ALL_SPECIALISTS, CONTINUATION_SPECIALISTS):
        review = next(s for s in specialists if s.name == "review_analyst")
        names = _tool_names(review.tools)
        assert "search_serpapi" in names
        assert "get_tripadvisor_reviews" in names
        assert "get_google_reviews" in names
        assert "find_tripadvisor_restaurant" not in names
        assert "google_search" not in names


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
