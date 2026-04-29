"""Tests for specialist construction callbacks in specialists.py."""

from superextra_agent.specialists import ALL_SPECIALISTS
from superextra_agent.agent import _skip_enricher_if_cached


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
