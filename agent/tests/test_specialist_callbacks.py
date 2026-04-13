"""Tests for specialist skip/brief callbacks in specialists.py."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from superextra_agent.specialists import (
    _make_skip_callback,
    set_specialist_briefs,
    VALID_BRIEF_KEYS,
)


class FakeCallbackContext:
    """Minimal callback_context with state dict."""
    def __init__(self, state=None):
        self.state = state or {}


def test_skip_callback_no_brief_returns_not_relevant():
    cb = _make_skip_callback("market_landscape")
    ctx = FakeCallbackContext(state={"specialist_briefs": {}})
    result = cb(callback_context=ctx)
    assert result is not None
    assert result.parts[0].text == "NOT_RELEVANT"


def test_skip_callback_with_brief_returns_none():
    cb = _make_skip_callback("market_landscape")
    ctx = FakeCallbackContext(
        state={"specialist_briefs": {"market_landscape": "Research local burger market"}}
    )
    result = cb(callback_context=ctx)
    assert result is None


def test_skip_callback_no_briefs_key_returns_not_relevant():
    cb = _make_skip_callback("menu_pricing")
    ctx = FakeCallbackContext(state={})
    result = cb(callback_context=ctx)
    assert result is not None
    assert "NOT_RELEVANT" in result.parts[0].text


@pytest.mark.asyncio
async def test_set_specialist_briefs_stores_valid_keys():
    tool_context = MagicMock()
    tool_context.state = {}

    result = await set_specialist_briefs(
        {"market_landscape": "brief1", "menu_pricing": "brief2"},
        tool_context,
    )
    assert "market_landscape" in tool_context.state["specialist_briefs"]
    assert "menu_pricing" in tool_context.state["specialist_briefs"]
    assert "market_landscape" in result
    assert "menu_pricing" in result


@pytest.mark.asyncio
async def test_set_specialist_briefs_filters_invalid_keys(caplog):
    tool_context = MagicMock()
    tool_context.state = {}

    with caplog.at_level(logging.WARNING):
        result = await set_specialist_briefs(
            {
                "market_landscape": "valid brief",
                "nonexistent_specialist": "should be filtered",
                "also_invalid": "nope",
            },
            tool_context,
        )
    stored = tool_context.state["specialist_briefs"]
    assert "market_landscape" in stored
    assert "nonexistent_specialist" not in stored
    assert "also_invalid" not in stored
    assert "Unknown" in caplog.text or "ignored" in caplog.text.lower()


@pytest.mark.asyncio
async def test_set_specialist_briefs_all_invalid():
    tool_context = MagicMock()
    tool_context.state = {}

    result = await set_specialist_briefs(
        {"fake_1": "a", "fake_2": "b"},
        tool_context,
    )
    assert tool_context.state["specialist_briefs"] == {}
