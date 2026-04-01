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

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.tools.tool_context import ToolContext

import os as _os

# Cloud Run containers have a read-only filesystem except /tmp
_default_logs = Path(__file__).parent.parent / "logs"
LOGS_DIR = Path("/tmp/agent_logs") if _os.environ.get("K_SERVICE") else _default_logs

logger = logging.getLogger(__name__)


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


class ChatLoggerPlugin(BasePlugin):
    """Logs every chat event to per-session JSONL files in agent/logs/."""

    def __init__(self, *, name: str = "chat_logger"):
        super().__init__(name)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        # track model/tool call start times for duration logging
        self._model_starts: dict[str, float] = {}  # invocation_id -> time
        self._tool_starts: dict[str, float] = {}  # function_call_id -> time

    def _log_file(self, session_id: str) -> Path:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return LOGS_DIR / f"{date}_{session_id}.jsonl"

    def _write(self, session_id: str, entry: dict) -> None:
        entry.setdefault("ts", _now())
        try:
            with self._log_file(session_id).open("a") as f:
                f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Failed to write chat log")

    def _session_id(self, ctx: InvocationContext) -> str:
        return ctx.session.id

    # ── lifecycle ──

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext) -> types.Content | None:
        sid = self._session_id(invocation_context)
        self._write(sid, {
            "event": "invocation_start",
            "invocation_id": invocation_context.invocation_id,
            "user_id": invocation_context.user_id,
            "agent": getattr(invocation_context.agent, "name", None),
        })
        return None

    @override
    async def on_user_message_callback(self, *, invocation_context: InvocationContext, user_message: types.Content) -> types.Content | None:
        sid = self._session_id(invocation_context)
        self._write(sid, {
            "event": "user_message",
            "invocation_id": invocation_context.invocation_id,
            "content": _serialize_content(user_message),
        })
        return None

    @override
    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        sid = self._session_id(invocation_context)
        self._write(sid, {
            "event": "invocation_end",
            "invocation_id": invocation_context.invocation_id,
        })

    # ── agent ──

    @override
    async def before_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> types.Content | None:
        sid = callback_context.session.id
        self._write(sid, {
            "event": "agent_start",
            "invocation_id": callback_context.invocation_id,
            "agent": callback_context.agent_name,
        })
        return None

    @override
    async def after_agent_callback(self, *, agent: BaseAgent, callback_context: CallbackContext) -> types.Content | None:
        sid = callback_context.session.id
        self._write(sid, {
            "event": "agent_end",
            "invocation_id": callback_context.invocation_id,
            "agent": callback_context.agent_name,
        })
        return None

    # ── model ──

    @override
    async def before_model_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
        sid = callback_context.session.id
        inv = callback_context.invocation_id
        self._model_starts[inv] = time.monotonic()
        self._write(sid, {
            "event": "model_request",
            "invocation_id": inv,
            "agent": callback_context.agent_name,
            "model": llm_request.model,
            "content_count": len(llm_request.contents),
            "tools": list(llm_request.tools_dict.keys()) if llm_request.tools_dict else [],
        })
        return None

    @override
    async def after_model_callback(self, *, callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
        sid = callback_context.session.id
        inv = callback_context.invocation_id
        duration = None
        if inv in self._model_starts:
            duration = round(time.monotonic() - self._model_starts.pop(inv), 2)

        entry: dict[str, Any] = {
            "event": "model_response",
            "invocation_id": inv,
            "agent": callback_context.agent_name,
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

        # log text preview (first 500 chars) and function calls
        if llm_response.content and llm_response.content.parts:
            for part in llm_response.content.parts:
                if part.text:
                    entry["text_preview"] = part.text[:500]
                if part.function_call:
                    entry.setdefault("function_calls", []).append(part.function_call.name)

        # Capture grounding sources from google_search into session state
        gm = llm_response.grounding_metadata
        if gm:
            print(f"GROUNDING_DEBUG agent={callback_context.agent_name} has_chunks={bool(gm.grounding_chunks)} chunks_count={len(gm.grounding_chunks) if gm.grounding_chunks else 0}", flush=True)
        else:
            print(f"GROUNDING_DEBUG agent={callback_context.agent_name} grounding_metadata=None", flush=True)
        if gm and gm.grounding_chunks:
            existing = list(callback_context.state.get("_sources", []))
            seen = {s["url"] for s in existing}
            added = 0
            for chunk in gm.grounding_chunks:
                if chunk.web and chunk.web.uri and chunk.web.uri not in seen:
                    existing.append({"title": chunk.web.title or "", "url": chunk.web.uri})
                    seen.add(chunk.web.uri)
                    added += 1
            if added:
                callback_context.state["_sources"] = existing
                entry["sources_added"] = added

        self._write(sid, entry)
        return None

    @override
    async def on_model_error_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest, error: Exception) -> LlmResponse | None:
        sid = callback_context.session.id
        inv = callback_context.invocation_id
        duration = None
        if inv in self._model_starts:
            duration = round(time.monotonic() - self._model_starts.pop(inv), 2)

        self._write(sid, {
            "event": "model_error",
            "invocation_id": inv,
            "agent": callback_context.agent_name,
            "model": llm_request.model,
            "duration_s": duration,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        })
        return None

    # ── tools ──

    @override
    async def before_tool_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext) -> dict | None:
        call_id = tool_context.function_call_id or ""
        self._tool_starts[call_id] = time.monotonic()
        sid = tool_context.session.id
        self._write(sid, {
            "event": "tool_call",
            "invocation_id": tool_context.invocation_id,
            "agent": tool_context.agent_name,
            "tool": tool.name,
            "call_id": call_id,
            "args": _safe(tool_args),
        })
        return None

    @override
    async def after_tool_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, result: dict) -> dict | None:
        call_id = tool_context.function_call_id or ""
        duration = None
        if call_id in self._tool_starts:
            duration = round(time.monotonic() - self._tool_starts.pop(call_id), 2)

        sid = tool_context.session.id
        self._write(sid, {
            "event": "tool_result",
            "invocation_id": tool_context.invocation_id,
            "agent": tool_context.agent_name,
            "tool": tool.name,
            "call_id": call_id,
            "duration_s": duration,
            "result_preview": str(_safe(result))[:1000],
        })
        return None

    @override
    async def on_tool_error_callback(self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext, error: Exception) -> dict | None:
        call_id = tool_context.function_call_id or ""
        duration = None
        if call_id in self._tool_starts:
            duration = round(time.monotonic() - self._tool_starts.pop(call_id), 2)

        sid = tool_context.session.id
        self._write(sid, {
            "event": "tool_error",
            "invocation_id": tool_context.invocation_id,
            "agent": tool_context.agent_name,
            "tool": tool.name,
            "call_id": call_id,
            "duration_s": duration,
            "args": _safe(tool_args),
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
        })
        return None

    # ── events ──

    @override
    async def on_event_callback(self, *, invocation_context: InvocationContext, event: Event) -> Event | None:
        sid = self._session_id(invocation_context)
        entry: dict[str, Any] = {
            "event": "adk_event",
            "invocation_id": invocation_context.invocation_id,
            "event_id": event.id,
            "author": event.author,
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

        self._write(sid, entry)
        return None
