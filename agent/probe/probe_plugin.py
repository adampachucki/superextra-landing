"""Probe plugin — writes Firestore docs on every callback so the harness
can verify ADK lifecycle behaviour under deployed Agent Runtime.

Signatures verified empirically against google-adk==1.28.0 (see
docs/gear-probe-log-2026-04-26.md). Run-level + on_event use
`invocation_context: InvocationContext`. Agent-level uses
`callback_context: CallbackContext`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.plugins.base_plugin import BasePlugin
from google.cloud import firestore
from typing_extensions import override

log = logging.getLogger(__name__)


class ProbePlugin(BasePlugin):
    """Writes Firestore docs at: before_run, on_event (load-bearing),
    after_run, after_agent (supplementary).

    Production-intended metadata mechanism: runId/attempt/turnIdx are
    stored in `session.state` at create_session() time and read here from
    `invocation_context.session.state`. Failure to read them = Test 4
    fail; we explicitly do NOT fall back to message-text encoding.
    """

    def __init__(self, project: str) -> None:
        super().__init__(name="probe_plugin")
        # firestore.Client picks up project from ADC if omitted, but be
        # explicit so the deployed runtime hits the right project.
        self._project = project
        self._fs: firestore.Client | None = None

    def _client(self) -> firestore.Client:
        # Lazy init — Agent Runtime constructs the plugin once at startup
        # but the Firestore client should be created inside the request
        # context to pick up per-request creds cleanly.
        if self._fs is None:
            self._fs = firestore.Client(project=self._project)
        return self._fs

    def _meta(self, ctx: InvocationContext | CallbackContext) -> tuple[str, dict[str, Any]]:
        """Return (sid, metadata-dict). sid comes from session.id;
        runId/attempt/turnIdx come from session.state set at
        create_session() time. userId from invocation_context.user_id.
        invocation_id from invocation_context.invocation_id — added 2026-04-26
        for R3.1 doc isolation between turns within the same session."""
        sid = ctx.session.id if ctx.session else "no-session"
        state = (ctx.session.state if ctx.session else None) or {}
        meta = {
            "runId": state.get("runId", "missing"),
            "attempt": state.get("attempt", "missing"),
            "turnIdx": state.get("turnIdx", "missing"),
            "userId": getattr(ctx, "user_id", None) or "missing",
            "invocation_id": getattr(ctx, "invocation_id", None) or "missing",
        }
        return sid, meta

    async def _write(self, sid: str, kind: str, extra: dict[str, Any]) -> None:
        # Diagnostic: print to stderr so it surfaces in any log surface
        # Agent Runtime exposes. No try/except — if Firestore write fails,
        # the exception propagates and we see it in stream_query response.
        import sys
        print(f"[probe_plugin] FIRING kind={kind} sid={sid} extra={extra}", file=sys.stderr, flush=True)
        doc = {
            "sid": sid,
            "kind": kind,
            "ts": firestore.SERVER_TIMESTAMP,
            **extra,
        }
        ref = (
            self._client()
            .collection("probe_runs")
            .document(sid)
            .collection("events")
            .document()
        )
        await asyncio.to_thread(ref.set, doc)
        print(f"[probe_plugin] WROTE kind={kind} sid={sid}", file=sys.stderr, flush=True)

    @override
    async def before_run_callback(self, *, invocation_context: InvocationContext):
        sid, meta = self._meta(invocation_context)
        await self._write(sid, "before_run", meta)
        return None

    @override
    async def after_run_callback(self, *, invocation_context: InvocationContext) -> None:
        sid, meta = self._meta(invocation_context)
        await self._write(sid, "after_run", meta)

    @override
    async def on_event_callback(
        self, *, invocation_context: InvocationContext, event: Event
    ):
        """Load-bearing — production FirestoreProgressPlugin will iterate
        real ADK Event objects through this hook."""
        sid, meta = self._meta(invocation_context)
        is_final = False
        try:
            is_final = bool(event.is_final_response())
        except Exception:
            pass
        await self._write(
            sid,
            "event",
            {
                **meta,
                "event_author": getattr(event, "author", None),
                "event_id": getattr(event, "id", None),
                "is_final": is_final,
            },
        )
        return None

    @override
    async def after_agent_callback(
        self, *, agent: BaseAgent, callback_context: CallbackContext
    ):
        """Supplementary — confirms agent-level callbacks work, parallels
        the production ChatLoggerPlugin pattern."""
        sid, meta = self._meta(callback_context)
        await self._write(sid, "agent_event", {**meta, "agent": agent.name})
        return None
