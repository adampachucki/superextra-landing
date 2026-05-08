"""Per-invocation accumulator for `FirestoreProgressPlugin`.

Holds the mutable state for one run: ``final_reply``, ``final_sources``,
``specialist_sources``, ``specialist_sources_seen``, ``mapping_state``,
``timeline_builder``, ``timeline_writer``, ``title_task``, and the
heartbeat task.

Concurrency discipline (load-bearing): accumulator mutations on
``GearRunState`` and on ``TurnSummaryBuilder`` are synchronous and
``await``-free. ``observe_typed_pill`` follows the same pattern for its dedupe
decision, then awaits only the ``TimelineWriter`` write. ``TimelineWriter`` owns
its own internal lock for Firestore writes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from .firestore_events import map_event
from .notes import TITLE_TIMEOUT_S
from .timeline import TimelineWriter, TurnSummaryBuilder

log = logging.getLogger(__name__)


@dataclass
class GearRunState:
    """All per-invocation mutable state for one root-runner invocation
    inside Vertex AI Agent Engine. Constructed in `before_run_callback`
    and torn down in `after_run_callback`."""

    # Identity
    sid: str
    invocation_id: str  # debug-only; not used as a Firestore fence key
    run_id: str
    turn_idx: int
    user_id: str
    query_text: str  # raw user message — needed for title generation

    # Sub-objects (constructed in __post_init__ to keep dataclass init clean)
    timeline_builder: TurnSummaryBuilder = field(init=False)
    timeline_writer: TimelineWriter = field(init=False)

    # Mutable accumulators
    final_reply: str | None = None
    final_sources: list[dict[str, Any]] = field(default_factory=list)
    specialist_sources: list[dict[str, Any]] = field(default_factory=list)
    specialist_sources_seen: set[str] = field(default_factory=set)
    mapping_state: dict[str, Any] = field(default_factory=lambda: {"place_names": {}})
    title_task: asyncio.Task[Any] | None = None
    partial_thought_pending: bool = False

    # Lifecycle
    heartbeat_task: asyncio.Task[Any] | None = None

    # Wired up by FirestoreProgressPlugin (so this dataclass stays decoupled
    # from the Firestore client construction path).
    fs: firestore.Client | None = None

    def __post_init__(self) -> None:
        # `fs` is required in practice (the plugin always passes it). Earlier
        # versions had a defensive `raise RuntimeError(...)` here; dropped per
        # the lean covenant — no verified failure mode, and a downstream
        # AttributeError from a Firestore call surfaces the bug just as well.
        started_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.timeline_builder = TurnSummaryBuilder(started_at_ms=started_at_ms)
        # `attempt=1` here mirrors agentStream's :appendEvent stateDelta —
        # GEAR doesn't do the multi-attempt takeover dance the legacy
        # worker uses; one attempt per turn.
        self.timeline_writer = TimelineWriter(
            fs=self.fs,
            sid=self.sid,
            user_id=self.user_id,
            run_id=self.run_id,
            attempt=1,
        )

    # ── Per-event observation ────────────────────────────────────────────────

    def observe_event(self, event: Any) -> list[dict[str, Any]]:
        """Mutate accumulator from one ADK event. Returns the list of
        timeline-event dicts the caller should feed to
        ``timeline_writer.write_timeline(...)``.

        Sync + await-free by design: the caller can run this from
        ``on_event_callback`` without worrying about another coroutine
        interleaving partial mutations.
        """
        mapped = map_event(event, self.mapping_state)

        # Filter detail events through accept_detail for dedupe.
        events_to_write: list[dict[str, Any]] = []
        for ev in mapped.get("timeline_events") or []:
            if ev.get("kind") == "detail" and not self.timeline_builder.accept_detail(
                ev
            ):
                continue
            events_to_write.append(ev)

        # Drain grounding_sources from the mapper.
        for entry in mapped.get("grounding_sources") or []:
            self._merge_source(entry)

        # Drain `_tool_src_*` keys from the event state_delta. Each tool
        # call writes a UNIQUE state key so parallel tool calls all survive
        # in one event's stateDelta.
        sd = (event.actions.state_delta if getattr(event, "actions", None) else None) or {}
        if isinstance(sd, dict):
            for key, value in sd.items():
                if key.startswith("_tool_src_"):
                    self._merge_source(value)

        # Capture final reply + sources on first `complete` event.
        if mapped.get("complete") is not None and self.final_reply is None:
            self._capture_final(mapped["complete"])

        return events_to_write

    async def observe_typed_pill(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Write one timeline event from a typed ADK hook.

        The dedupe decision stays synchronous, matching ``observe_event``. Only
        the Firestore timeline write awaits.
        """
        if event.get("kind") == "detail" and not self.timeline_builder.accept_detail(
            event
        ):
            return None
        return await self.timeline_writer.write_timeline(event)

    def _merge_source(self, entry: Any) -> None:
        if not isinstance(entry, dict):
            return
        url = entry.get("url")
        if not url or url in self.specialist_sources_seen:
            return
        self.specialist_sources_seen.add(url)
        self.specialist_sources.append(entry)

    def _capture_final(self, complete: dict[str, Any]) -> None:
        reply = complete.get("reply")
        if not isinstance(reply, str):
            return
        self.final_reply = reply
        mapper_sources = complete.get("sources") or []
        # Dedup across mapper-extracted + specialist-accumulated.
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for s in list(mapper_sources) + list(self.specialist_sources):
            url = s.get("url") if isinstance(s, dict) else None
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(s)
        self.final_sources = merged

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def stop_heartbeat(self) -> None:
        """Cancel the heartbeat task with a 1s timeout. Called FIRST in
        ``after_run`` so a late tick can't clobber the terminal write with
        a fresh ``lastHeartbeat``.
        """
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await asyncio.wait_for(self.heartbeat_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def finalize(self) -> tuple[dict[str, Any], dict[str, Any], str]:
        """Build ``(session_terminal_update, turn_terminal_update, status)``
        from accumulated state.

        Sequence:

          1. Close ``timeline_writer`` after all thought and tool-detail
             rows observed during event mapping have been queued.
          2. Await ``title_task`` with bounded ``TITLE_TIMEOUT_S``.
             ``asyncio.wait_for`` cancels-on-timeout so no straggler
             concern.
          3. Empty-reply sanity check. Whitespace-only ``final_reply``
             returns the error payload, NOT a complete payload.
          4. Build the two payloads from now-stable state.
        """
        await self.timeline_writer.close()

        title: str | None = None
        if self.title_task is not None:
            try:
                title = await asyncio.wait_for(self.title_task, timeout=TITLE_TIMEOUT_S)
            except (asyncio.TimeoutError, Exception):
                # `Exception` does NOT catch `CancelledError` (BaseException
                # subclass); explicitly NOT catching it here lets outer
                # cancellation propagate through finalize() instead of
                # being swallowed by the title-task wrapper.
                title = None

        if not self.final_reply or not self.final_reply.strip():
            return (
                {
                    "status": "error",
                    "error": "empty_or_malformed_reply",
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                {
                    "status": "error",
                    "error": "empty_or_malformed_reply",
                    "completedAt": firestore.SERVER_TIMESTAMP,
                },
                "error",
            )

        session_update: dict[str, Any] = {
            "status": "complete",
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }
        if title is not None:
            session_update["title"] = title

        turn_update: dict[str, Any] = {
            "status": "complete",
            "reply": self.final_reply,
            "sources": self.final_sources,
            "turnSummary": self.timeline_builder.build_summary(),
            "completedAt": firestore.SERVER_TIMESTAMP,
        }
        return session_update, turn_update, "complete"
