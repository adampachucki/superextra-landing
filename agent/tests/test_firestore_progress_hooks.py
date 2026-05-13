from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.cloud import firestore

from superextra_agent import firestore_progress
from superextra_agent.firestore_progress import FirestoreProgressPlugin
from superextra_agent.gear_run_state import GearRunState


def _make_plugin_state() -> tuple[FirestoreProgressPlugin, GearRunState]:
    plugin = FirestoreProgressPlugin(project="superextra-site")
    plugin._fs = MagicMock()
    state = GearRunState(
        sid="sid-test",
        invocation_id="inv-parent",
        run_id="run-test",
        turn_idx=1,
        user_id="user-test",
        query_text="What about reviews?",
        fs=MagicMock(),
    )
    state.timeline_writer.write_timeline = AsyncMock(return_value=None)
    plugin._states["inv-parent"] = state
    return plugin, state


def _tool(name: str):
    return SimpleNamespace(name=name)


def _tool_context(*, invocation_id: str = "inv-parent", call_id: str = "call-1"):
    return SimpleNamespace(
        invocation_id=invocation_id,
        function_call_id=call_id,
        agent_name="research_lead",
        session=SimpleNamespace(id="se-sid-test", state={"runId": "run-test"}),
    )


@pytest.mark.asyncio
async def test_before_model_writes_active_stage(monkeypatch):
    plugin, _state = _make_plugin_state()
    updates: list[dict] = []

    async def _fenced(_fs, _state, update):
        updates.append(update)

    monkeypatch.setattr(firestore_progress, "fenced_session_update", _fenced)

    callback_context = SimpleNamespace(
        invocation_id="inv-parent",
        agent_name="report_writer",
        session=SimpleNamespace(id="se-sid-test", state={"runId": "run-test"}),
    )
    llm_request = SimpleNamespace(model="gemini-3.1-pro")

    await plugin.before_model_callback(
        callback_context=callback_context,
        llm_request=llm_request,
    )

    assert updates == [
        {
            "activeAgent": "report_writer",
            "activeStage": "writing_final_report",
            "activeStageStartedAt": firestore.SERVER_TIMESTAMP,
            "activeModel": "gemini-3.1-pro",
            "activeInvocationId": "inv-parent",
        }
    ]


@pytest.mark.asyncio
async def test_before_tool_google_search_writes_search_pill():
    plugin, state = _make_plugin_state()

    await plugin.before_tool_callback(
        tool=_tool("google_search"),
        tool_args={"query": "pizza Gdynia"},
        tool_context=_tool_context(call_id="call-search"),
    )

    state.timeline_writer.write_timeline.assert_awaited_once_with(
        {
            "kind": "detail",
            "id": "tool:call:call-search:google_search",
            "group": "search",
            "family": "Searching the web",
            "text": "pizza Gdynia",
        }
    )


@pytest.mark.asyncio
async def test_tool_error_fetch_web_content_writes_warning():
    plugin, state = _make_plugin_state()

    await plugin.on_tool_error_callback(
        tool=_tool("fetch_web_content"),
        tool_args={"url": "https://example.invalid"},
        tool_context=_tool_context(call_id="call-fetch"),
        error=RuntimeError("boom"),
    )

    state.timeline_writer.write_timeline.assert_awaited_once_with(
        {
            "kind": "detail",
            "id": "tool:response:call-fetch:fetch_web_content",
            "group": "warning",
            "family": "Warnings",
            "text": "Source fetch failed",
        }
    )


@pytest.mark.asyncio
async def test_nested_tool_context_routes_by_run_id():
    plugin, state = _make_plugin_state()

    await plugin.before_tool_callback(
        tool=_tool("google_search"),
        tool_args={"query": "coffee Gdynia"},
        tool_context=_tool_context(invocation_id="inv-child", call_id="call-child"),
    )

    state.timeline_writer.write_timeline.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_error_agent_level_fallback_does_not_duplicate_pill():
    plugin, state = _make_plugin_state()
    context = _tool_context(call_id="call-fetch")

    await plugin.on_tool_error_callback(
        tool=_tool("fetch_web_content"),
        tool_args={"url": "https://example.invalid"},
        tool_context=context,
        error=RuntimeError("boom"),
    )
    await plugin.after_tool_callback(
        tool=_tool("fetch_web_content"),
        tool_args={"url": "https://example.invalid"},
        tool_context=context,
        result={"error": "Tool fetch_web_content failed: RuntimeError"},
    )

    assert state.timeline_writer.write_timeline.await_count == 1
