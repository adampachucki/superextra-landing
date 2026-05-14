"""Small helpers for correlating ADK callbacks with Superextra runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CorrelationFields:
    sid: str | None = None
    adk_session_id: str | None = None
    run_id: str | None = None
    turn_idx: int | None = None
    root_invocation_id: str | None = None
    invocation_id: str | None = None
    parent_invocation_id: str | None = None
    agent: str | None = None
    tool: str | None = None

    def log_session_id(self) -> str:
        return self.adk_session_id or self.sid or "unknown-session"

    def as_log_fields(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "sid": self.sid,
                "adk_session_id": self.adk_session_id,
                "run_id": self.run_id,
                "turn_idx": self.turn_idx,
                "root_invocation_id": self.root_invocation_id,
                "invocation_id": self.invocation_id,
                "parent_invocation_id": self.parent_invocation_id,
                "agent": self.agent,
                "tool": self.tool,
            }.items()
            if value is not None
        }


def is_nested_invocation(context: Any) -> bool:
    """True for AgentTool child runners.

    AgentTool constructs child runners with InMemorySessionService. Top-level
    Agent Engine calls use the managed session service.
    """
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    svc = getattr(context, "session_service", None)
    return isinstance(svc, InMemorySessionService)


def invocation_context(context: Any) -> Any:
    return getattr(context, "_invocation_context", None) or context


def normalize_firestore_sid(session_id: str | None) -> str | None:
    if not isinstance(session_id, str) or not session_id:
        return None
    return session_id.removeprefix("se-")


def session_state(context: Any) -> dict[str, Any]:
    session = getattr(invocation_context(context), "session", None)
    state = getattr(session, "state", None) or {}
    return state if isinstance(state, dict) else {}


def run_id_from_context(context: Any) -> str | None:
    run_id = session_state(context).get("runId")
    return run_id if isinstance(run_id, str) and run_id else None


def turn_idx_from_context(context: Any) -> int | None:
    turn_idx = session_state(context).get("turnIdx")
    return turn_idx if isinstance(turn_idx, int) else None


def agent_name_from_context(context: Any) -> str | None:
    if isinstance(getattr(context, "agent_name", None), str):
        return context.agent_name
    agent = getattr(invocation_context(context), "agent", None)
    name = getattr(agent, "name", None)
    return name if isinstance(name, str) else None


def build_correlation(
    context: Any,
    *,
    root: CorrelationFields | None = None,
    agent: str | None = None,
    tool: str | None = None,
) -> CorrelationFields:
    inv_ctx = invocation_context(context)
    session = getattr(inv_ctx, "session", None)
    adk_session_id = getattr(session, "id", None)
    invocation_id = getattr(context, "invocation_id", None) or getattr(
        inv_ctx, "invocation_id", None
    )
    root_invocation_id = root.root_invocation_id if root else invocation_id
    parent_invocation_id = (
        root.invocation_id
        if root and invocation_id and invocation_id != root.invocation_id
        else None
    )
    run_id = run_id_from_context(context)
    turn_idx = turn_idx_from_context(context)
    if root is not None:
        run_id = root.run_id or run_id
        turn_idx = root.turn_idx or turn_idx

    return CorrelationFields(
        sid=root.sid if root else normalize_firestore_sid(adk_session_id),
        adk_session_id=root.adk_session_id if root else adk_session_id,
        run_id=run_id,
        turn_idx=turn_idx,
        root_invocation_id=root_invocation_id,
        invocation_id=invocation_id,
        parent_invocation_id=parent_invocation_id,
        agent=agent or agent_name_from_context(context),
        tool=tool,
    )


def build_run_correlation(
    run: Any,
    *,
    invocation_id: str | None = None,
    agent: str | None = None,
    tool: str | None = None,
) -> CorrelationFields:
    root_invocation_id = getattr(run, "invocation_id", None)
    current_invocation_id = invocation_id or root_invocation_id
    parent_invocation_id = (
        root_invocation_id
        if invocation_id and invocation_id != root_invocation_id
        else None
    )
    return CorrelationFields(
        sid=getattr(run, "sid", None),
        run_id=getattr(run, "run_id", None),
        turn_idx=getattr(run, "turn_idx", None),
        root_invocation_id=root_invocation_id,
        invocation_id=current_invocation_id,
        parent_invocation_id=parent_invocation_id,
        agent=agent,
        tool=tool,
    )


def annotate_current_span(correlation: CorrelationFields) -> None:
    try:
        from opentelemetry import trace
    except Exception:
        return

    try:
        span = trace.get_current_span()
        if not span or not span.is_recording():
            return
        for key, value in correlation.as_log_fields().items():
            span.set_attribute(f"superextra.{key}", value)
    except Exception:
        return
