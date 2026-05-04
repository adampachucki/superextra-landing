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
