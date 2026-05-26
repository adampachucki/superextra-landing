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

EVENT_TTL_DAYS = 180


class TimelineOwnershipLost(Exception):
    """The session no longer owns this run, so the timeline write must stop."""


# ── TurnSummaryBuilder ───────────────────────────────────────────────────────


class TurnSummaryBuilder:
    def __init__(self, *, started_at_ms: int):
        self.started_at_ms = started_at_ms
        self.detail_dedupe: set[tuple[str, str, str]] = set()

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

    def build_summary(self) -> dict[str, Any]:
        finished_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return {
            "startedAtMs": self.started_at_ms,
            "finishedAtMs": finished_at_ms,
            "elapsedMs": max(0, finished_at_ms - self.started_at_ms),
        }


# ── TimelineWriter ───────────────────────────────────────────────────────────


def _timeline_write_logic(
    txn: firestore.Transaction,
    session_ref: firestore.DocumentReference,
    event_ref: firestore.DocumentReference,
    expected_run_id: str,
    doc: dict[str, Any],
) -> None:
    snap = session_ref.get(transaction=txn)
    data = snap.to_dict() or {}
    if data.get("currentRunId") != expected_run_id or data.get("status") != "running":
        raise TimelineOwnershipLost()
    txn.set(event_ref, doc)


_timeline_write_txn = firestore.transactional(_timeline_write_logic)


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
            next_seq = self._seq_in_attempt + 1
            doc = {
                "userId": self._user_id,
                "runId": self._run_id,
                "attempt": self._attempt,
                "seqInAttempt": next_seq,
                "type": "timeline",
                "data": data,
                "ts": firestore.SERVER_TIMESTAMP,
                "expiresAt": datetime.now(timezone.utc) + timedelta(days=EVENT_TTL_DAYS),
            }
            session_ref = self._fs.collection("sessions").document(self._sid)
            event_ref = session_ref.collection("events").document()
            try:
                await asyncio.to_thread(
                    _timeline_write_txn,
                    self._fs.transaction(),
                    session_ref,
                    event_ref,
                    self._run_id,
                    doc,
                )
            except TimelineOwnershipLost:
                self.closed = True
                raise
            self._seq_in_attempt = next_seq
            return doc

    async def close(self) -> None:
        async with self._lock:
            self.closed = True
