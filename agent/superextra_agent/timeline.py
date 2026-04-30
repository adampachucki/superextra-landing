"""TurnSummaryBuilder + TimelineWriter for `FirestoreProgressPlugin`.

These two classes own the per-turn UI-progress accumulator (which
``notes`` to surface, which ``sources`` were touched, which ``venues``
were resolved) and the Firestore writer that lands live timeline events
(``sessions/{sid}/events`` subcollection).

Mutation discipline (load-bearing): every method on
``TurnSummaryBuilder`` is **synchronous and ``await``-free**. Concurrent
note-task coroutines call only these synchronous methods between their
own awaits, so a control-yield can never interleave a partial mutation.
``TimelineWriter`` owns its own ``asyncio.Lock`` to serialise its
Firestore writes. Together this gives the plugin its no-extra-lock
concurrency guarantee.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from .firestore_events import extract_sources_from_grounding, write_event_doc


# ── Event-walking helpers ────────────────────────────────────────────────────


def _iter_parts(event: Any) -> list[Any]:
    content = getattr(event, "content", None)
    return list(getattr(content, "parts", None) or [])


def _iter_function_calls(event: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for part in _iter_parts(event):
        fc = getattr(part, "function_call", None)
        if not fc or not getattr(fc, "name", None):
            continue
        args = getattr(fc, "args", None) or {}
        out.append((fc.name, args if isinstance(args, dict) else {}))
    return out


def _iter_function_responses(event: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for part in _iter_parts(event):
        fr = getattr(part, "function_response", None)
        if not fr or not getattr(fr, "name", None):
            continue
        response = getattr(fr, "response", None) or {}
        out.append((fr.name, response if isinstance(response, dict) else {}))
    return out


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _normalize_url(url: str) -> str:
    return url.strip()


# ── TurnSummaryBuilder ───────────────────────────────────────────────────────


class TurnSummaryBuilder:
    def __init__(self, *, started_at_ms: int):
        self.started_at_ms = started_at_ms
        self.web_queries: set[str] = set()
        self.sources: set[str] = set()
        self.venues: set[str] = set()
        self.platforms: set[str] = set()
        self.detail_dedupe: set[tuple[str, str, str]] = set()
        self.notes: list[dict[str, Any]] = []
        self.pending_research_fallback: dict[str, Any] | None = None
        self.context_note_emitted = False
        self.research_placeholder_emitted = False
        self.research_note_emitted = False

    def observe_event(self, event: Any, state: dict[str, Any]) -> None:
        for name, args in _iter_function_calls(event):
            if name == "google_search":
                query = args.get("query")
                if isinstance(query, str) and query.strip():
                    self.web_queries.add(_normalize_query(query))
            elif name == "fetch_web_content":
                url = args.get("url")
                if isinstance(url, str) and url.strip():
                    self.sources.add(_normalize_url(url))
            elif name == "get_google_reviews":
                place_id = args.get("place_id")
                if isinstance(place_id, str) and place_id.strip():
                    self.venues.add(place_id.strip())
                    self.sources.add(
                        _normalize_url(
                            f"https://www.google.com/maps/place/?q=place_id:{place_id.strip()}"
                        )
                    )
            elif name == "get_restaurant_details":
                place_id = args.get("place_id")
                if isinstance(place_id, str) and place_id.strip():
                    self.venues.add(place_id.strip())
            elif name == "get_batch_restaurant_details":
                place_ids = args.get("place_ids")
                if isinstance(place_ids, list):
                    for place_id in place_ids:
                        if isinstance(place_id, str) and place_id.strip():
                            self.venues.add(place_id.strip())

        for source in extract_sources_from_grounding(event):
            url = source.get("url")
            if isinstance(url, str) and url.strip():
                self.sources.add(_normalize_url(url))

        sd = (event.actions.state_delta if getattr(event, "actions", None) else None) or {}
        if isinstance(sd, dict):
            for key, value in sd.items():
                if key.startswith("_place_name_") and isinstance(value, str) and value.strip():
                    self.venues.add(value.strip().lower())

        for name, response in _iter_function_responses(event):
            status = str(response.get("status") or "").strip().lower()
            if name in ("search_restaurants", "find_nearby_restaurants") and status == "success":
                results = response.get("results")
                if isinstance(results, list):
                    for result in results:
                        if not isinstance(result, dict):
                            continue
                        rid = result.get("id")
                        if isinstance(rid, str) and rid.strip():
                            self.venues.add(rid.strip())
                        display_name = (
                            (result.get("displayName") or {})
                            if isinstance(result.get("displayName"), dict)
                            else {}
                        )
                        text = display_name.get("text")
                        if isinstance(text, str) and text.strip():
                            self.venues.add(text.strip().lower())
            elif name == "find_tripadvisor_restaurant" and status == "success":
                # Only accumulate on a verified match. Unverified/error responses
                # now strip these fields, but gate explicitly in case the tool
                # ever returns a partial payload on a non-success path.
                trip_link = response.get("tripadvisor_link")
                if isinstance(trip_link, str) and trip_link.strip():
                    self.sources.add(_normalize_url(trip_link))
                venue_name = response.get("name")
                if isinstance(venue_name, str) and venue_name.strip():
                    self.venues.add(venue_name.strip().lower())
            elif name == "get_restaurant_details" and status == "success":
                place = response.get("place")
                if isinstance(place, dict):
                    display_name = place.get("displayName")
                    if isinstance(display_name, dict):
                        text = display_name.get("text")
                        if isinstance(text, str) and text.strip():
                            self.venues.add(text.strip().lower())

    def accept_detail(self, event: dict[str, Any]) -> bool:
        key = (
            str(event.get("group") or ""),
            str(event.get("family") or ""),
            str(event.get("text") or ""),
        )
        if key in self.detail_dedupe:
            return False
        self.detail_dedupe.add(key)
        family = event.get("family")
        if isinstance(family, str) and family and family != "Warnings":
            self.platforms.add(family)
        return True

    def counts_snapshot(self) -> dict[str, int]:
        return {
            "webQueries": len(self.web_queries),
            "sources": len(self.sources),
            "venues": len(self.venues),
            "platforms": len(self.platforms),
        }

    def add_note(
        self,
        *,
        milestone: str,
        text: str,
        note_source: str,
        counts: dict[str, int] | None = None,
        live_only: bool = False,
    ) -> dict[str, Any] | None:
        if milestone == "context_start" and self.context_note_emitted:
            return None
        if milestone == "research_placeholder" and self.research_placeholder_emitted:
            return None
        if milestone == "research_result" and self.research_note_emitted:
            return None

        snapshot = counts or self.counts_snapshot()
        note = {
            "milestone": milestone,
            "text": text,
            "noteSource": note_source,
            "counts": snapshot,
            "liveOnly": live_only,
        }
        self.notes.append(note)
        if milestone == "context_start":
            self.context_note_emitted = True
        elif milestone == "research_placeholder":
            self.research_placeholder_emitted = True
        elif milestone == "research_result":
            self.research_note_emitted = True
            self.pending_research_fallback = None
        return {
            "kind": "note",
            "id": f"note:{milestone}:{len(self.notes)}",
            "text": text,
            "noteSource": note_source,
            "counts": snapshot,
        }

    def finalize_notes(self) -> list[dict[str, Any]]:
        if (
            self.pending_research_fallback
            and not self.research_note_emitted
            and not self.research_placeholder_emitted
        ):
            fallback = self.pending_research_fallback
            self.notes.append(
                {
                    "milestone": "research_result",
                    "text": fallback["text"],
                    "noteSource": "deterministic",
                    "counts": fallback["counts"],
                    "liveOnly": False,
                }
            )
            self.research_note_emitted = True

        notes = list(self.notes)
        if self.research_note_emitted:
            notes = [
                n
                for n in notes
                if n["milestone"] != "research_placeholder" or not n.get("liveOnly")
            ]
        kept = []
        for note in notes:
            kept.append(
                {
                    "text": note["text"],
                    "noteSource": note["noteSource"],
                    "counts": note["counts"],
                }
            )
        return kept[:4]

    def build_summary(self) -> dict[str, Any]:
        finished_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return {
            "startedAtMs": self.started_at_ms,
            "finishedAtMs": finished_at_ms,
            "elapsedMs": max(0, finished_at_ms - self.started_at_ms),
            "notes": self.finalize_notes(),
            "finalCounts": self.counts_snapshot(),
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
            return await write_event_doc(
                fs=self._fs,
                sid=self._sid,
                user_id=self._user_id,
                run_id=self._run_id,
                attempt=self._attempt,
                seq_in_attempt=self._seq_in_attempt,
                event_type="timeline",
                data=data,
            )

    async def close(self) -> None:
        async with self._lock:
            self.closed = True

    @property
    def seq_in_attempt(self) -> int:
        return self._seq_in_attempt
