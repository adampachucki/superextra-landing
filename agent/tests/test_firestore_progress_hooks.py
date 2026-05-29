from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.cloud import firestore
from google.adk.models.llm_response import LlmResponse
from superextra_agent import firestore_progress
from superextra_agent.firestore_progress import FirestoreProgressPlugin
from superextra_agent.gear_run_state import GearRunState
from superextra_agent.timeline import TimelineOwnershipLost


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
    plugin._states_by_run_id["run-test"] = state
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


def _session_snapshot(plugin: FirestoreProgressPlugin, data: dict):
    snap = MagicMock()
    snap.exists = True
    snap.to_dict.return_value = data
    doc = MagicMock()
    doc.get.return_value = snap
    collection = MagicMock()
    collection.document.return_value = doc
    plugin._fs.collection.return_value = collection


def test_active_stage_updates_are_model_scoped():
    assert "before_agent_callback" not in FirestoreProgressPlugin.__dict__


@pytest.mark.asyncio
async def test_before_model_writes_active_stage(monkeypatch):
    plugin, _state = _make_plugin_state()
    updates: list[dict] = []
    cloud_logs: list[tuple[str, dict]] = []

    async def _fenced(_fs, _state, update):
        updates.append(update)

    def _emit(event: str, **fields):
        cloud_logs.append((event, fields))

    monkeypatch.setattr(firestore_progress, "fenced_session_update", _fenced)
    monkeypatch.setattr(firestore_progress, "emit_cloud_log", _emit)

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
        }
    ]
    assert cloud_logs[0][0] == "active_stage"
    assert cloud_logs[0][1]["sid"] == "sid-test"
    assert cloud_logs[0][1]["run_id"] == "run-test"
    assert cloud_logs[0][1]["turn_idx"] == 1
    assert cloud_logs[0][1]["root_invocation_id"] == "inv-parent"
    assert cloud_logs[0][1]["invocation_id"] == "inv-parent"


@pytest.mark.asyncio
async def test_before_model_stops_when_run_no_longer_owns_session():
    plugin, state = _make_plugin_state()
    _session_snapshot(plugin, {"status": "error", "currentRunId": None})
    callback_context = SimpleNamespace(
        invocation_id="inv-parent",
        agent_name="report_writer",
        session=SimpleNamespace(id="se-sid-test", state={"runId": "run-test"}),
    )
    llm_request = SimpleNamespace(model="gemini-3.1-pro")

    result = await plugin.before_model_callback(
        callback_context=callback_context,
        llm_request=llm_request,
    )

    assert isinstance(result, LlmResponse)
    assert state.cancelled is True


@pytest.mark.asyncio
async def test_after_run_finalize_logs_use_shared_correlation(monkeypatch):
    plugin, state = _make_plugin_state()
    state.final_reply = "Final answer"
    cloud_logs: list[tuple[str, dict]] = []
    terminal_updates: list[dict] = []

    async def _fenced(_fs, _state, session_update, _turn_update):
        terminal_updates.append(session_update)
        return None

    def _emit(event: str, **fields):
        cloud_logs.append((event, fields))

    monkeypatch.setattr(firestore_progress, "fenced_session_and_turn_update", _fenced)
    monkeypatch.setattr(firestore_progress, "emit_cloud_log", _emit)

    await plugin.after_run_callback(
        invocation_context=SimpleNamespace(
            invocation_id="inv-parent",
            session_service=object(),
        )
    )

    emitted = {event: fields for event, fields in cloud_logs}
    assert emitted["finalize_start"]["sid"] == "sid-test"
    assert emitted["finalize_start"]["run_id"] == "run-test"
    assert emitted["finalize_start"]["turn_idx"] == 1
    assert emitted["finalize_start"]["root_invocation_id"] == "inv-parent"
    assert emitted["finalize_start"]["invocation_id"] == "inv-parent"
    assert emitted["finalize_success"]["root_invocation_id"] == "inv-parent"
    assert emitted["finalize_success"]["invocation_id"] == "inv-parent"
    assert terminal_updates[0]["activeAgent"] == firestore.DELETE_FIELD
    assert terminal_updates[0]["activeStage"] == firestore.DELETE_FIELD
    assert terminal_updates[0]["activeStageStartedAt"] == firestore.DELETE_FIELD
    assert terminal_updates[0]["activeModel"] == firestore.DELETE_FIELD
    assert terminal_updates[0]["activeInvocationId"] == firestore.DELETE_FIELD


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
async def test_before_tool_returns_cancelled_result_when_run_no_longer_owns_session():
    plugin, state = _make_plugin_state()
    _session_snapshot(plugin, {"status": "error", "currentRunId": None})

    result = await plugin.before_tool_callback(
        tool=_tool("google_search"),
        tool_args={"query": "pizza Gdynia"},
        tool_context=_tool_context(call_id="call-search"),
    )

    assert result == {"status": "cancelled", "error": "user_cancelled"}
    assert state.cancelled is True
    state.timeline_writer.write_timeline.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_event_stops_when_timeline_writer_loses_ownership(monkeypatch):
    plugin, state = _make_plugin_state()
    state.observe_event = MagicMock(return_value=[{"kind": "detail", "text": "late"}])
    state.timeline_writer.write_timeline.side_effect = TimelineOwnershipLost()
    fenced_session_update = AsyncMock()
    monkeypatch.setattr(
        firestore_progress, "fenced_session_update", fenced_session_update
    )
    invocation_context = SimpleNamespace(
        invocation_id="inv-parent",
        agent_name="research_lead",
        session=SimpleNamespace(id="se-sid-test", state={"runId": "run-test"}),
    )

    await plugin.on_event_callback(
        invocation_context=invocation_context, event=SimpleNamespace(partial=False)
    )

    assert state.cancelled is True
    state.timeline_writer.write_timeline.assert_awaited_once()
    fenced_session_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_error_writes_warning():
    plugin, state = _make_plugin_state()

    await plugin.on_tool_error_callback(
        tool=_tool("fetch_tripadvisor_page"),
        tool_args={"url": "https://example.invalid"},
        tool_context=_tool_context(call_id="call-fetch"),
        error=RuntimeError("boom"),
    )

    state.timeline_writer.write_timeline.assert_awaited_once_with(
        {
            "kind": "detail",
            "id": "tool:response:call-fetch:fetch_tripadvisor_page",
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
        tool=_tool("fetch_tripadvisor_page"),
        tool_args={"url": "https://example.invalid"},
        tool_context=context,
        error=RuntimeError("boom"),
    )
    await plugin.after_tool_callback(
        tool=_tool("fetch_tripadvisor_page"),
        tool_args={"url": "https://example.invalid"},
        tool_context=context,
        result={"error": "Tool fetch_tripadvisor_page failed: RuntimeError"},
    )

    assert state.timeline_writer.write_timeline.await_count == 1
