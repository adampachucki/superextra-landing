"""TurnSummaryBuilder + TimelineWriter for `FirestoreProgressPlugin`.

`TurnSummaryBuilder` keeps the small persisted turn footer and detail-row
dedupe. `TimelineWriter` serializes live timeline writes into
``sessions/{sid}/events``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

EVENT_TTL_DAYS = 3


# ── TurnSummaryBuilder ───────────────────────────────────────────────────────


class TurnSummaryBuilder:
    def __init__(self, *, started_at_ms: int):
        self.started_at_ms = started_at_ms
        self.detail_dedupe: set[tuple[str, str, str]] = set()
        self.first_event_ms: int | None = None
        self.first_thought_ms: int | None = None
        self.timeline_events = 0
        self.thought_events = 0
        self.detail_events = 0
        self.warning_events = 0
        self.model_calls = 0
        self.tool_calls = 0
        self.tool_results = 0
        self.tool_errors = 0
        self.agents_seen: set[str] = set()
        self.models_used: set[str] = set()
        self.tools_used: set[str] = set()

    def accept_detail(self, event: dict[str, Any]) -> bool:
        key = (
            str(event.get("group") or ""),
            str(event.get("family") or ""),
            str(event.get("text") or ""),
        )
        if key in self.detail_dedupe:
            return False
        self.detail_dedupe.add(key)
        return True

    def record_timeline_event(self, event: dict[str, Any]) -> None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        self.first_event_ms = self.first_event_ms or now_ms
        self.timeline_events += 1

        kind = event.get("kind")
        if kind == "thought":
            self.thought_events += 1
            self.first_thought_ms = self.first_thought_ms or now_ms
            author = event.get("author")
            if isinstance(author, str) and author:
                self.agents_seen.add(author)
        elif kind == "detail":
            self.detail_events += 1
            if event.get("group") == "warning":
                self.warning_events += 1

    def record_model_call(self, *, agent: str | None, model: str | None) -> None:
        self.model_calls += 1
        if agent:
            self.agents_seen.add(agent)
        if model:
            self.models_used.add(model)

    def record_tool_call(self, *, agent: str | None, tool: str | None) -> None:
        self.tool_calls += 1
        if agent:
            self.agents_seen.add(agent)
        if tool:
            self.tools_used.add(tool)

    def record_tool_result(self, *, error: bool = False) -> None:
        if error:
            self.tool_errors += 1
        else:
            self.tool_results += 1

    def build_summary(self, *, source_count: int = 0) -> dict[str, Any]:
        finished_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        diagnostics: dict[str, Any] = {
            "timelineEvents": self.timeline_events,
            "thoughts": self.thought_events,
            "details": self.detail_events,
            "warnings": self.warning_events,
            "modelCalls": self.model_calls,
            "toolCalls": self.tool_calls,
            "toolResults": self.tool_results,
            "toolErrors": self.tool_errors,
            "sourceCount": source_count,
            "agents": sorted(self.agents_seen),
            "models": sorted(self.models_used),
            "tools": sorted(self.tools_used),
        }
        if self.first_event_ms is not None:
            diagnostics["msToFirstEvent"] = max(
                0, self.first_event_ms - self.started_at_ms
            )
        if self.first_thought_ms is not None:
            diagnostics["msToFirstThought"] = max(
                0, self.first_thought_ms - self.started_at_ms
            )
        return {
            "startedAtMs": self.started_at_ms,
            "finishedAtMs": finished_at_ms,
            "elapsedMs": max(0, finished_at_ms - self.started_at_ms),
            "diagnostics": diagnostics,
        }


# ── TimelineWriter ───────────────────────────────────────────────────────────


class TimelineWriter:
    def __init__(
        self,
        *,
        fs: firestore.Client,
        sid: str,
        user_id: str,
        run_id: str,
        attempt: int,
    ):
        self._fs = fs
        self._sid = sid
        self._user_id = user_id
        self._run_id = run_id
        self._attempt = attempt
        self._seq_in_attempt = 0
        self._lock = asyncio.Lock()
        self.closed = False

    async def write_timeline(self, data: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            if self.closed:
                return None
            self._seq_in_attempt += 1
            doc = {
                "userId": self._user_id,
                "runId": self._run_id,
                "attempt": self._attempt,
                "seqInAttempt": self._seq_in_attempt,
                "type": "timeline",
                "data": data,
                "ts": firestore.SERVER_TIMESTAMP,
                "expiresAt": datetime.now(timezone.utc) + timedelta(days=EVENT_TTL_DAYS),
            }
            ref = (
                self._fs.collection("sessions")
                .document(self._sid)
                .collection("events")
                .document()
            )
            await asyncio.to_thread(ref.set, doc)
            return doc

    async def close(self) -> None:
        async with self._lock:
            self.closed = True
