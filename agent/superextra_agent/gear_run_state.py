"""Per-invocation accumulator for the GEAR `FirestoreProgressPlugin`.

Replaces the nine local variables that today's `worker_main.py` keeps in
its event loop scope (`final_reply`, `final_sources`, `specialist_sources`,
`specialist_sources_seen`, `mapping_state`, `timeline_builder`,
`timeline_writer`, `note_tasks`, `title_task`) — plus the heartbeat task —
with a single object owned by the plugin's per-invocation map.

Concurrency discipline (load-bearing — plan §"No per-run lock"): every
mutation method on `GearRunState` and on `TurnSummaryBuilder` is
synchronous and `await`-free. Once a mutation starts there are no
suspension points until it returns, so concurrent coroutines (e.g.
overlapping note tasks) cannot interleave a partial mutation.
`TimelineWriter` owns its own internal lock for its Firestore writes.
**Any future mutator added here must stay sync and await-free**, or this
safety property breaks.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from .firestore_events import map_event
from .notes import (
    NOTE_TIMEOUT_S,
    TITLE_TIMEOUT_S,
    _deterministic_note,
    _emit_note_task,
)
from .timeline import TimelineWriter, TurnSummaryBuilder

log = logging.getLogger(__name__)

# Notes themselves time out at NOTE_TIMEOUT_S; the drain wait gives any
# in-flight LLM call its full budget before we cancel and gather.
NOTE_TASK_DRAIN_TIMEOUT_S = NOTE_TIMEOUT_S


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
    query_text: str  # raw user message — needed for note-task LLM prompts

    # Sub-objects (constructed in __post_init__ to keep dataclass init clean)
    timeline_builder: TurnSummaryBuilder = field(init=False)
    timeline_writer: TimelineWriter = field(init=False)

    # Mutable accumulators (mirror worker_main.py:646-661)
    final_reply: str | None = None
    final_sources: list[dict[str, Any]] = field(default_factory=list)
    specialist_sources: list[dict[str, Any]] = field(default_factory=list)
    specialist_sources_seen: set[str] = field(default_factory=set)
    mapping_state: dict[str, Any] = field(default_factory=lambda: {"place_names": {}})
    note_tasks: list[asyncio.Task[Any]] = field(default_factory=list)
    title_task: asyncio.Task[Any] | None = None
    seq: int = 0

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
        ``timeline_writer.write_timeline(...)``. Mirrors
        ``worker_main.py:670-771``.

        Sync + await-free by design (plan §"No per-run lock"): the caller
        can run this from `on_event_callback` without worrying about
        another coroutine interleaving partial mutations.
        """
        mapped = map_event(event, self.mapping_state)
        self.timeline_builder.observe_event(event, self.mapping_state)

        # Filter timeline events: detail events go through accept_detail
        # for dedupe; drafting events are emitted at most once per turn.
        events_to_write: list[dict[str, Any]] = []
        for ev in mapped.get("timeline_events") or []:
            kind = ev.get("kind")
            if kind == "detail" and not self.timeline_builder.accept_detail(ev):
                continue
            if kind == "drafting" and not self.timeline_builder.mark_drafting():
                continue
            events_to_write.append(ev)

        # Drain grounding_sources from the mapper.
        for entry in mapped.get("grounding_sources") or []:
            self._merge_source(entry)

        # Drain `_tool_src_*` keys from the event state_delta. Each tool
        # call writes a UNIQUE state key so parallel tool calls all survive
        # in one event's stateDelta. Mirrors worker_main.py:693-696.
        sd = (event.actions.state_delta if getattr(event, "actions", None) else None) or {}
        if isinstance(sd, dict):
            for key, value in sd.items():
                if key.startswith("_tool_src_"):
                    self._merge_source(value)

        # Milestones → notes (deterministic now, LLM-backed via note tasks).
        events_to_write.extend(self._maybe_emit_notes(mapped.get("milestones") or {}))

        # Capture final reply + sources on first `complete` event.
        if mapped.get("complete") is not None and self.final_reply is None:
            self._capture_final(mapped["complete"])

        self.seq += 1
        return events_to_write

    def _merge_source(self, entry: Any) -> None:
        if not isinstance(entry, dict):
            return
        url = entry.get("url")
        if not url or url in self.specialist_sources_seen:
            return
        self.specialist_sources_seen.add(url)
        self.specialist_sources.append(entry)

    def _maybe_emit_notes(self, milestones: dict[str, Any]) -> list[dict[str, Any]]:
        """Mirrors worker_main.py:698-754. Returns deterministic notes the
        caller must write to the timeline. LLM-backed notes are spawned
        as ``asyncio.Task`` and tracked on ``self.note_tasks`` for drain
        in ``finalize()``.
        """
        extras: list[dict[str, Any]] = []

        if milestones.get("context_started") and not self.timeline_builder.context_note_emitted:
            note = self.timeline_builder.add_note(
                milestone="context_start",
                text=_deterministic_note("context_start"),
                note_source="deterministic",
            )
            if note is not None:
                extras.append(note)

        if (
            milestones.get("plan_ready_text")
            and not self.timeline_builder.plan_note_emitted
            and self.timeline_builder.pending_plan_fallback is None
        ):
            counts_snapshot = self.timeline_builder.counts_snapshot()
            self.timeline_builder.pending_plan_fallback = {
                "text": _deterministic_note("plan_ready"),
                "counts": counts_snapshot,
            }
            self.note_tasks.append(
                asyncio.create_task(
                    _emit_note_task(
                        writer=self.timeline_writer,
                        builder=self.timeline_builder,
                        milestone="plan_ready",
                        query_text=self.query_text,
                        input_text=str(milestones["plan_ready_text"])[:1500],
                        counts_snapshot=counts_snapshot,
                    )
                )
            )

        if milestones.get("research_started") and not self.timeline_builder.research_placeholder_emitted:
            note = self.timeline_builder.add_note(
                milestone="research_placeholder",
                text=_deterministic_note("research_placeholder"),
                note_source="deterministic",
                live_only=True,
            )
            if note is not None:
                extras.append(note)

        if (
            milestones.get("research_result_text")
            and not self.timeline_builder.research_note_emitted
            and self.timeline_builder.pending_research_fallback is None
        ):
            counts_snapshot = self.timeline_builder.counts_snapshot()
            self.timeline_builder.pending_research_fallback = {
                "text": _deterministic_note("research_result"),
                "counts": counts_snapshot,
            }
            self.note_tasks.append(
                asyncio.create_task(
                    _emit_note_task(
                        writer=self.timeline_writer,
                        builder=self.timeline_builder,
                        milestone="research_result",
                        query_text=self.query_text,
                        input_text=str(milestones["research_result_text"])[:1500],
                        counts_snapshot=counts_snapshot,
                    )
                )
            )

        return extras

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
        `after_run` so a late tick can't clobber the terminal write with
        a fresh ``lastHeartbeat``. Mirrors ``worker_main.py:454``
        ``_cancel_heartbeat``.
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

        Sequence (plan §4.1, with v3.8 close-order swap and v3.9 gather-all):

          1. Bounded-wait note tasks for ``NOTE_TASK_DRAIN_TIMEOUT_S``,
             then **cancel stragglers** (``asyncio.wait`` does NOT cancel
             pending — only returns sets), then **gather all** with
             ``return_exceptions=True`` so a raised note-task exception
             doesn't sit unretrieved on the task and trigger asyncio's
             "exception was never retrieved" log at GC.
          2. Close ``timeline_writer`` AFTER notes are settled. If we
             closed first, a note task that resumes from its await would
             mutate ``timeline_builder`` but its ``write_timeline`` call
             would silently no-op against the closed writer — turnSummary
             would contain a note the live UI never saw. Close-after-drain
             keeps the live timeline and summary in sync.
          3. Await ``title_task`` with bounded ``TITLE_TIMEOUT_S``. (Note:
             ``asyncio.wait_for`` cancels-on-timeout so no straggler
             concern there.)
          4. Empty-reply sanity check (mirrors
             ``worker_main.py:1292``). Whitespace-only ``final_reply``
             returns the error payload, NOT a complete payload.
          5. Build the two payloads from now-stable state.
        """
        if self.note_tasks:
            _done, pending = await asyncio.wait(
                self.note_tasks, timeout=NOTE_TASK_DRAIN_TIMEOUT_S
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(*self.note_tasks, return_exceptions=True)

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

        # All background mutators of timeline_builder are now done or
        # cancelled. Safe to read.
        if not self.final_reply or not self.final_reply.strip():
            return (
                {
                    "status": "error",
                    "error": "empty_or_malformed_reply",
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                {"status": "error", "error": "empty_or_malformed_reply"},
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
