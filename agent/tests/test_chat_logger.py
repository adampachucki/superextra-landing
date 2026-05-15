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
        session=SimpleNamespace(id=sid, state={"runId": run_id, "turnIdx": 2}),
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
    child_event = _log_entries(parent_files[0])[1]
    assert child_event["sid"] == "parent"
    assert child_event["run_id"] == "run-1"
    assert child_event["turn_idx"] == 2
    assert child_event["root_invocation_id"] == "inv-parent"
    assert child_event["parent_invocation_id"] == "inv-parent"
    assert child_event["invocation_id"] == "inv-child"


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


@pytest.mark.asyncio
async def test_model_request_logs_native_built_in_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    cloud_logs: list[tuple[str, dict]] = []

    def _emit(event: str, **fields):
        cloud_logs.append((event, fields))

    monkeypatch.setattr(chat_logger, "emit_cloud_log", _emit)
    plugin = ChatLoggerPlugin()

    ctx = SimpleNamespace(
        invocation_id="inv-parent",
        agent_name="market_landscape",
        session=SimpleNamespace(id="se-parent", state={"runId": "run-1", "turnIdx": 1}),
    )
    llm_request = SimpleNamespace(
        model="gemini-test",
        contents=[],
        config=SimpleNamespace(
            tool_config=SimpleNamespace(
                include_server_side_tool_invocations=True,
                retrieval_config=SimpleNamespace(lat_lng=SimpleNamespace()),
                function_calling_config=SimpleNamespace(mode="AUTO"),
            ),
            tools=[
                SimpleNamespace(
                    google_search=SimpleNamespace(),
                    url_context=SimpleNamespace(),
                    function_declarations=[SimpleNamespace(name="read_web_pages")],
                )
            ]
        ),
        tools_dict={"read_web_pages": object(), "fetch_web_content": object()},
    )

    await plugin.before_model_callback(callback_context=ctx, llm_request=llm_request)

    entry = _log_entries(next(tmp_path.glob("*_se-parent.jsonl")))[0]
    assert entry["tools"] == [
        "google_search",
        "url_context",
        "read_web_pages",
        "fetch_web_content",
    ]
    assert entry["tool_config"] == {
        "include_server_side_tool_invocations": True,
        "has_retrieval_config": True,
        "has_retrieval_geo_bias": True,
        "function_calling_mode": "AUTO",
    }

    model_request = next(fields for event, fields in cloud_logs if event == "model_request")
    assert model_request["tool_defs"] == entry["tools"]
    assert model_request["tool_def_count"] == 4
    assert model_request["include_server_side_tool_invocations"] is True
    assert model_request["has_retrieval_geo_bias"] is True


@pytest.mark.asyncio
async def test_model_response_cloud_log_is_metadata_rich_without_payloads(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    cloud_logs: list[tuple[str, dict]] = []

    def _emit(event: str, **fields):
        cloud_logs.append((event, fields))

    monkeypatch.setattr(chat_logger, "emit_cloud_log", _emit)
    plugin = ChatLoggerPlugin()

    ctx = SimpleNamespace(
        invocation_id="inv-parent",
        agent_name="report_writer",
        session=SimpleNamespace(id="se-parent", state={"runId": "run-1", "turnIdx": 1}),
    )
    response = SimpleNamespace(
        error_code=None,
        error_message=None,
        usage_metadata=SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=40,
            thoughts_token_count=7,
            tool_use_prompt_token_count=33,
            cached_content_token_count=None,
            total_token_count=140,
            traffic_type="ON_DEMAND",
        ),
        finish_reason="STOP",
        content=SimpleNamespace(
            parts=[
                SimpleNamespace(
                    text="Detailed final report with venue-specific implications.",
                    function_call=None,
                ),
                SimpleNamespace(
                    text=None,
                    function_call=None,
                    tool_call=SimpleNamespace(tool_type="GOOGLE_SEARCH", id="tool-1"),
                    tool_response=SimpleNamespace(tool_type="GOOGLE_SEARCH", id="tool-1"),
                ),
                SimpleNamespace(
                    text=None,
                    function_call=SimpleNamespace(
                        name="lookup_source",
                        args={"url": "https://example.com/source"},
                    ),
                ),
            ]
        ),
    )

    await plugin.after_model_callback(callback_context=ctx, llm_response=response)

    assert cloud_logs[0][0] == "model_response"
    logged = cloud_logs[0][1]
    assert logged["sid"] == "parent"
    assert logged["adk_session_id"] == "se-parent"
    assert logged["run_id"] == "run-1"
    assert logged["turn_idx"] == 1
    assert logged["tokens"] == {
        "prompt": 100,
        "candidates": 40,
        "thoughts": 7,
        "tool_use_prompt": 33,
        "cached_content": None,
        "total": 140,
    }
    assert logged["thought_tokens"] == 7
    assert logged["tool_use_prompt_tokens"] == 33
    assert logged["server_side_tool_use"] is True
    assert logged["server_side_tool_part_count"] == 2
    assert logged["server_side_tool_types"] == ["GOOGLE_SEARCH", "GOOGLE_SEARCH"]
    assert logged["traffic_type"] == "ON_DEMAND"
    assert logged["text_preview_chars"] == len(
        "Detailed final report with venue-specific implications."
    )
    assert logged["function_call_count"] == 1
    assert logged["function_call_names"] == ["lookup_source"]
    assert "text_preview" not in logged
    assert "function_calls" not in logged
    assert "llm_response_dump" not in logged


@pytest.mark.asyncio
async def test_tool_lifecycle_cloud_log_uses_sanitized_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_logger, "LOGS_DIR", tmp_path)
    cloud_logs: list[tuple[str, dict]] = []

    def _emit(event: str, **fields):
        cloud_logs.append((event, fields))

    monkeypatch.setattr(chat_logger, "emit_cloud_log", _emit)
    plugin = ChatLoggerPlugin()

    parent = _parent_invocation()
    await plugin.before_run_callback(invocation_context=parent)
    child = _child_invocation()
    tool_context = SimpleNamespace(
        _invocation_context=child,
        session=child.session,
        invocation_id=child.invocation_id,
        agent_name="review_analyst",
        function_call_id="call-1",
    )
    tool = SimpleNamespace(name="get_google_reviews")

    await plugin.before_tool_callback(
        tool=tool,
        tool_args={"place_id": "abc", "limit": 200},
        tool_context=tool_context,
    )
    await plugin.after_tool_callback(
        tool=tool,
        tool_args={"place_id": "abc", "limit": 200},
        tool_context=tool_context,
        result={"status": "success", "reviews": [{"rating": 5}], "total_fetched": 1},
    )

    events = [event for event, _fields in cloud_logs]
    assert "tool_call" in events
    assert "tool_result" in events

    tool_call = next(fields for event, fields in cloud_logs if event == "tool_call")
    assert tool_call["sid"] == "parent"
    assert tool_call["root_invocation_id"] == "inv-parent"
    assert tool_call["parent_invocation_id"] == "inv-parent"
    assert tool_call["tool"] == "get_google_reviews"
    assert tool_call["arg_keys"] == ["limit", "place_id"]
    assert "args" not in tool_call

    tool_result = next(fields for event, fields in cloud_logs if event == "tool_result")
    assert tool_result["result_summary"]["status"] == "success"
    assert tool_result["result_summary"]["reviews_count"] == 1
    assert "result_preview" not in tool_result
