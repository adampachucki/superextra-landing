"""Chat logging plugin — writes structured JSONL logs per session for debugging."""

from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from google.genai import types
from pydantic import BaseModel
from typing_extensions import override

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.events.event import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool

from .cloud_logging import emit_cloud_log
from .correlation import (
    CorrelationFields,
    annotate_current_span,
    build_correlation,
    is_nested_invocation,
    run_id_from_context,
)

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.tool_context import ToolContext

import os as _os

# Cloud Run containers have a read-only filesystem except /tmp
_default_logs = Path(__file__).parent.parent / "logs"
LOGS_DIR = Path("/tmp/agent_logs") if _os.environ.get("K_SERVICE") else _default_logs

logger = logging.getLogger(__name__)

_CLOUD_EVENTS = {
    "invocation_start",
    "invocation_end",
    "agent_start",
    "agent_end",
    "model_request",
    "model_response",
    "model_error",
    "tool_call",
    "tool_result",
    "tool_error",
    "adk_event",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_safe(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, BaseModel):
        try:
            return obj.model_dump(mode="json", exclude_none=True)
        except Exception:
            return str(obj)
    if isinstance(obj, bytes):
        return f"<bytes:{len(obj)}>"
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


def _serialize_content(content: types.Content | None) -> dict | None:
    if content is None:
        return None
    parts = []
    for part in content.parts or []:
        d: dict[str, Any] = {}
        if part.text:
            d["text"] = part.text
        if part.function_call:
            d["function_call"] = {
                "name": part.function_call.name,
                "args": part.function_call.args,
            }
        if part.function_response:
            d["function_response"] = {
                "name": part.function_response.name,
                "response": _safe(part.function_response.response),
            }
        if d:
            parts.append(d)
    return {"role": content.role, "parts": parts}


def _summarize_tool_result(result: Any) -> dict[str, Any]:
    safe = _safe(result)
    if not isinstance(safe, dict):
        return {"type": type(result).__name__}

    summary: dict[str, Any] = {
        "keys": sorted(str(k) for k in safe.keys())[:30],
    }
    status = safe.get("status")
    if isinstance(status, str):
        summary["status"] = status
    for key in ("results", "reviews", "places", "sources"):
        value = safe.get(key)
        if isinstance(value, list):
            summary[f"{key}_count"] = len(value)
    for key in ("total_fetched", "fetched_reviews", "source_count"):
        value = safe.get(key)
        if isinstance(value, (int, float)):
            summary[key] = value
    return summary


def _truncate(text: Any, limit: int = 500) -> str | None:
    if text is None:
        return None
    value = str(text)
    return value if len(value) <= limit else value[: limit - 3] + "..."


def _cloud_payload(entry: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "ts",
        "sid",
        "adk_session_id",
        "run_id",
        "turn_idx",
        "root_invocation_id",
        "invocation_id",
        "parent_invocation_id",
        "user_id",
        "agent",
        "model",
        "tool",
        "call_id",
        "duration_s",
        "content_count",
        "tokens",
        "finish_reason",
        "error_code",
        "error_type",
        "branch",
        "event_id",
        "is_final",
        "state_delta_keys",
        "part_types",
        "result_summary",
    }
    payload = {k: v for k, v in entry.items() if k in allowed and v is not None}

    if "tools" in entry:
        tools = entry.get("tools") or []
        payload["tool_def_count"] = len(tools) if isinstance(tools, list) else 0
        payload["tool_defs"] = tools[:30] if isinstance(tools, list) else []

    if "function_calls" in entry:
        calls = entry.get("function_calls") or []
        names: list[str] = []
        if isinstance(calls, list):
            for call in calls:
                if isinstance(call, dict) and isinstance(call.get("name"), str):
                    names.append(call["name"])
                elif isinstance(call, str):
                    names.append(call)
        payload["function_call_count"] = len(names)
        payload["function_call_names"] = names[:30]

    args = entry.get("args")
    if isinstance(args, dict):
        payload["arg_keys"] = sorted(str(k) for k in args.keys())[:30]

    if entry.get("text_preview") is not None:
        payload["text_preview_chars"] = len(str(entry["text_preview"]))

    if entry.get("error") is not None:
        payload["error"] = _truncate(entry["error"])
    if entry.get("error_message") is not None:
        payload["error_message"] = _truncate(entry["error_message"])

    return payload


class ChatLoggerPlugin(BasePlugin):
    """Logs every chat event to per-session JSONL files in agent/logs/."""

    def __init__(self, *, name: str = "chat_logger"):
        super().__init__(name)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        # track model/tool call start times for duration logging
        self._model_starts: dict[str, float] = {}  # invocation_id -> time
        self._tool_starts: dict[str, float] = {}  # function_call_id -> time
        self._root_by_run_id: dict[str, CorrelationFields] = {}
        self._run_id_by_root_invocation: dict[str, str] = {}

    def _log_file(self, session_id: str) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return LOGS_DIR / f"{date}_{session_id}.jsonl"

    def _correlation_for_invocation(
        self,
        ctx: InvocationContext,
        *,
        agent: str | None = None,
        tool: str | None = None,
    ) -> CorrelationFields:
        run_id = run_id_from_context(ctx)
        root = self._root_by_run_id.get(run_id) if run_id else None
        return build_correlation(ctx, root=root, agent=agent, tool=tool)

    def _correlation_for_context(
        self,
        ctx: CallbackContext | ToolContext,
        *,
        agent: str | None = None,
        tool: str | None = None,
    ) -> CorrelationFields:
        inv_ctx = getattr(ctx, "_invocation_context", None)
        if inv_ctx is not None:
            return self._correlation_for_invocation(inv_ctx, agent=agent, tool=tool)
        return build_correlation(ctx, agent=agent, tool=tool)

    def _write(self, correlation: CorrelationFields, entry: dict) -> None:
        entry.setdefault("ts", _now())
        for key, value in correlation.as_log_fields().items():
            entry.setdefault(key, value)
        if entry.get("event") in _CLOUD_EVENTS:
            severity = (
                "ERROR"
                if entry.get("event") in {"model_error", "tool_error"}
                else "INFO"
            )
            annotate_current_span(correlation)
            emit_cloud_log(
                str(entry["event"]), severity=severity, **_cloud_payload(entry)
            )
        try:
            with self._log_file(correlation.log_session_id()).open("a") as f:
                f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Failed to write chat log")

    def _run_id(self, ctx: InvocationContext) -> str | None:
        return run_id_from_context(ctx)

    # ── lifecycle ──

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext) -> types.Content | None:
        if is_nested_invocation(invocation_context):
            # AgentTool child runner — parent invocation already logged
            # invocation_start. Avoid duplicate lifecycle markers.
            return None
        correlation = self._correlation_for_invocation(invocation_context)
        run_id = self._run_id(invocation_context)
        if run_id:
            self._root_by_run_id[run_id] = correlation
            self._run_id_by_root_invocation[invocation_context.invocation_id] = run_id
        self._write(
            correlation,
            {
                "event": "invocation_start",
                "user_id": invocation_context.user_id,
            },
        )
        return None

    @override
    async def on_user_message_callback(self, *, invocation_context: InvocationContext, user_message: types.Content) -> types.Content | None:
        correlation = self._correlation_for_invocation(invocation_context)
        self._write(
            correlation,
            {
                "event": "user_message",
                "content": _serialize_content(user_message),
            },
        )
        return None

    @override
    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        if is_nested_invocation(invocation_context):
            return None
        correlation = self._correlation_for_invocation(invocation_context)
        self._write(correlation, {"event": "invocation_end"})
        run_id = self._run_id_by_root_invocation.pop(
            invocation_context.invocation_id, None
        )
        if run_id:
            self._root_by_run_id.pop(run_id, None)

    # ── agent ──

    @override
    async def before_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> types.Content | None:
        correlation = self._correlation_for_context(
            callback_context, agent=callback_context.agent_name
        )
        self._write(correlation, {"event": "agent_start"})
        return None

    @override
    async def after_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> types.Content | None:
        correlation = self._correlation_for_context(
            callback_context, agent=callback_context.agent_name
        )
        self._write(correlation, {"event": "agent_end"})
        return None

    # ── model ──

    @override
    async def before_model_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
        correlation = self._correlation_for_context(
            callback_context, agent=callback_context.agent_name
        )
        inv = callback_context.invocation_id
        self._model_starts[inv] = time.monotonic()
        self._write(
            correlation,
            {
                "event": "model_request",
                "model": llm_request.model,
                "content_count": len(llm_request.contents),
                "tools": list(llm_request.tools_dict.keys())
                if llm_request.tools_dict
                else [],
            },
        )
        return None

    @override
    async def after_model_callback(self, *, callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
        correlation = self._correlation_for_context(
            callback_context, agent=callback_context.agent_name
        )
        inv = callback_context.invocation_id
        duration = None
        if inv in self._model_starts:
            duration = round(time.monotonic() - self._model_starts.pop(inv), 2)

        entry: dict[str, Any] = {
            "event": "model_response",
            "duration_s": duration,
        }

        if llm_response.error_code:
            entry["error_code"] = llm_response.error_code
            entry["error_message"] = llm_response.error_message

        if llm_response.usage_metadata:
            entry["tokens"] = {
                "prompt": llm_response.usage_metadata.prompt_token_count,
                "candidates": llm_response.usage_metadata.candidates_token_count,
                "total": llm_response.usage_metadata.total_token_count,
            }

        fr = getattr(llm_response, "finish_reason", None)
        if fr is not None:
            entry["finish_reason"] = str(fr)

        # log text preview (first 500 chars), function calls (with args), and part types
        if llm_response.content and llm_response.content.parts:
            part_types: list[str] = []
            for part in llm_response.content.parts:
                if part.text:
                    entry["text_preview"] = part.text[:500]
                    part_types.append(
                        "thought" if getattr(part, "thought", False) else "text"
                    )
                if part.function_call:
                    fc_entry: dict[str, Any] = {
                        "name": part.function_call.name,
                        "args": _safe(part.function_call.args),
                    }
                    entry.setdefault("function_calls", []).append(fc_entry)
                    part_types.append("function_call")
            entry["part_types"] = part_types

        self._write(correlation, entry)
        return None

    @override
    async def on_model_error_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest, error: Exception) -> LlmResponse | None:
        correlation = self._correlation_for_context(
            callback_context, agent=callback_context.agent_name
        )
        inv = callback_context.invocation_id
        duration = None
        if inv in self._model_starts:
            duration = round(time.monotonic() - self._model_starts.pop(inv), 2)

        self._write(
            correlation,
            {
                "event": "model_error",
                "model": llm_request.model,
                "duration_s": duration,
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        return None

    # ── tools ──

    @override
    async def before_tool_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext) -> dict | None:
        call_id = tool_context.function_call_id or ""
        self._tool_starts[call_id] = time.monotonic()
        correlation = self._correlation_for_context(
            tool_context, agent=tool_context.agent_name, tool=tool.name
        )
        self._write(
            correlation,
            {
                "event": "tool_call",
                "call_id": call_id,
                "args": _safe(tool_args),
            },
        )
        return None

    @override
    async def after_tool_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, result: dict) -> dict | None:
        call_id = tool_context.function_call_id or ""
        duration = None
        if call_id in self._tool_starts:
            duration = round(time.monotonic() - self._tool_starts.pop(call_id), 2)

        correlation = self._correlation_for_context(
            tool_context, agent=tool_context.agent_name, tool=tool.name
        )
        self._write(
            correlation,
            {
                "event": "tool_result",
                "call_id": call_id,
                "duration_s": duration,
                "result_summary": _summarize_tool_result(result),
                "result_preview": str(_safe(result))[:1000],
            },
        )
        return None

    @override
    async def on_tool_error_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, error: Exception) -> dict | None:
        call_id = tool_context.function_call_id or ""
        duration = None
        if call_id in self._tool_starts:
            duration = round(time.monotonic() - self._tool_starts.pop(call_id), 2)

        correlation = self._correlation_for_context(
            tool_context, agent=tool_context.agent_name, tool=tool.name
        )
        self._write(
            correlation,
            {
                "event": "tool_error",
                "call_id": call_id,
                "duration_s": duration,
                "args": _safe(tool_args),
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        return None

    # ── events ──

    @override
    async def on_event_callback(self, *, invocation_context: InvocationContext, event: Event) -> Event | None:
        correlation = self._correlation_for_invocation(
            invocation_context, agent=event.author
        )
        entry: dict[str, Any] = {
            "event": "adk_event",
            "event_id": event.id,
            "branch": event.branch,
            "is_final": event.is_final_response(),
        }

        if event.error_code:
            entry["error_code"] = event.error_code
            entry["error_message"] = event.error_message

        if event.usage_metadata:
            entry["tokens"] = {
                "prompt": event.usage_metadata.prompt_token_count,
                "candidates": event.usage_metadata.candidates_token_count,
                "total": event.usage_metadata.total_token_count,
            }

        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    entry["text_preview"] = part.text[:500]
                if part.function_call:
                    entry.setdefault("function_calls", []).append(part.function_call.name)

        if event.actions and event.actions.state_delta:
            entry["state_delta_keys"] = list(event.actions.state_delta.keys())

        self._write(correlation, entry)
        return None
