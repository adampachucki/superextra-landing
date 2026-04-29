from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from superextra_agent import chat_logger
from superextra_agent.chat_logger import ChatLoggerPlugin


def _parent_invocation(*, sid: str = "se-parent", run_id: str = "run-1"):
    return SimpleNamespace(
        invocation_id="inv-parent",
        user_id="user-test",
        agent=SimpleNamespace(name="router"),
        session=SimpleNamespace(id=sid, state={"runId": run_id}),
        session_service=object(),
    )


def _child_invocation(*, run_id: str = "run-1"):
    return SimpleNamespace(
        invocation_id="inv-child",
        user_id="user-test",
        agent=SimpleNamespace(name="market_landscape"),
        session=SimpleNamespace(id="child-session", state={"runId": run_id}),
        session_service=InMemorySessionService(),
    )


def _log_entries(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.asyncio
async def test_agenttool_child_events_write_to_parent_session_log(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    plugin = ChatLoggerPlugin()

    parent = _parent_invocation()
    await plugin.before_run_callback(invocation_context=parent)

    child = _child_invocation()
    event = SimpleNamespace(
        id="evt-1",
        author="market_landscape",
        branch=None,
        is_final_response=lambda: False,
        error_code=None,
        error_message=None,
        usage_metadata=None,
        content=None,
        actions=None,
    )
    await plugin.on_event_callback(invocation_context=child, event=event)

    parent_files = list(tmp_path.glob("*_se-parent.jsonl"))
    child_files = list(tmp_path.glob("*_child-session.jsonl"))
    assert len(parent_files) == 1
    assert child_files == []
    assert [entry["event"] for entry in _log_entries(parent_files[0])] == [
        "invocation_start",
        "adk_event",
    ]


@pytest.mark.asyncio
async def test_agenttool_child_model_callbacks_write_to_parent_session_log(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    plugin = ChatLoggerPlugin()

    parent = _parent_invocation()
    await plugin.before_run_callback(invocation_context=parent)

    child = _child_invocation()
    callback_context = SimpleNamespace(
        _invocation_context=child,
        session=child.session,
        invocation_id=child.invocation_id,
        agent_name="market_landscape",
    )
    llm_request = SimpleNamespace(
        model="gemini-test",
        contents=[],
        tools_dict={},
    )
    await plugin.before_model_callback(
        callback_context=callback_context, llm_request=llm_request
    )

    parent_file = next(tmp_path.glob("*_se-parent.jsonl"))
    child_files = list(tmp_path.glob("*_child-session.jsonl"))
    assert child_files == []
    assert [entry["event"] for entry in _log_entries(parent_file)] == [
        "invocation_start",
        "model_request",
    ]
