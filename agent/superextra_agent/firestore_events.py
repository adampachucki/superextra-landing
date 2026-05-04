"""Map ADK Runner events into the simplified activity-timeline contract."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from google.cloud import firestore

from .specialist_catalog import AUTHOR_TO_OUTPUT_KEY, SPECIALISTS

EVENT_TTL_DAYS = 3

SPECIALIST_AUTHORS: set[str] = {s.name for s in SPECIALISTS}

TIMELINE_FAMILIES = (
    "Searching the web",
    "Google Maps",
    "TripAdvisor",
    "Google reviews",
    "Public sources",
    "Warnings",
)


def _place_name(state: dict[str, Any] | None, place_id: str | None) -> str | None:
    if not state or not place_id:
        return None
    place_names = state.get("place_names")
    if not isinstance(place_names, dict):
        return None
    name = place_names.get(place_id)
    return name if isinstance(name, str) and name.strip() else None


def _detail(kind_id: str, group: str, family: str, text: str) -> dict[str, Any]:
    return {
        "kind": "detail",
        "id": kind_id,
        "group": group,
        "family": family,
        "text": text,
    }


def _normalize_space(text: str) -> str:
    return " ".join(text.split())


def _short_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.replace("www.", "")
        path = parsed.path.rstrip("/")
        label = host + (path or "")
        return label[:117] + "..." if len(label) > 120 else label
    except Exception:
        text = url.strip()
        return text[:117] + "..." if len(text) > 120 else text


def _iter_parts(event: Any) -> list[Any]:
    content = _get(event, "content")
    parts = _get(content, "parts") if content else None
    return list(parts or [])


async def write_event_doc(
    *,
    fs: firestore.Client,
    sid: str,
    user_id: str,
    run_id: str,
    attempt: int,
    seq_in_attempt: int,
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    doc = {
        "userId": user_id,
        "runId": run_id,
        "attempt": attempt,
        "seqInAttempt": seq_in_attempt,
        "type": event_type,
        "data": data,
        "ts": firestore.SERVER_TIMESTAMP,
        "expiresAt": datetime.now(timezone.utc) + timedelta(days=EVENT_TTL_DAYS),
    }
    ref = fs.collection("sessions").document(sid).collection("events").document()
    await asyncio.to_thread(ref.set, doc)
    return doc


def map_event(event: Any, state: dict[str, Any] | None = None) -> dict[str, Any]:
    author = _get(event, "author")
    mapping: dict[str, Any] = {
        "timeline_events": [],
        "complete": None,
        "grounding_sources": [],
    }

    _ingest_place_names(event, state)

    # Surface Gemini thought-summary parts (`include_thoughts=True`) as
    # `kind: 'thought'` timeline rows so the activity panel can render the
    # model's own narration of what it's doing. Each ADK event with thought
    # parts produces one timeline row keyed by `(author, event_id)` so the
    # client doesn't dedupe across genuine multi-thought events.
    thought_text = _collect_thought_text(event)
    if thought_text:
        mapping["timeline_events"].append(
            {
                "kind": "thought",
                "id": f"thought:{author or 'unknown'}:{_get(event, 'id') or ''}",
                "author": author,
                "text": thought_text,
            }
        )

    # Surface Gemini built-in Google Search queries (grounding_metadata's
    # web_search_queries) as `Searching the web` detail rows. The native
    # grounding path doesn't emit `function_call(name='google_search')`,
    # so without this branch the searches Gemini ran inline stay invisible.
    event_id = _get(event, "id") or ""
    for idx, query in enumerate(_extract_search_queries(event)):
        mapping["timeline_events"].append(
            _detail(
                f"search:{event_id}:{idx}",
                "search",
                "Searching the web",
                query,
            )
        )

    if author in SPECIALIST_AUTHORS:
        output_key = AUTHOR_TO_OUTPUT_KEY.get(author)
        if output_key and _has_state_delta(event, output_key):
            mapping["grounding_sources"] = extract_sources_from_grounding(event)

    if author in ("router", "research_lead", "follow_up"):
        complete = _map_complete(event)
        if complete is not None:
            mapping["complete"] = complete

    return mapping


def _collect_thought_text(event: Any) -> str:
    """Concatenate text from parts where `part.thought` is True.

    Internal tool identifiers (`get_restaurant_details`, `search_restaurants`,
    …) sometimes leak into Gemini's thought summaries even after the prompt
    nudge. Replace them with user-facing labels so the activity panel never
    surfaces internal names.
    """
    pieces: list[str] = []
    for part in _iter_parts(event):
        if not _get(part, "thought"):
            continue
        text = _get(part, "text")
        if isinstance(text, str) and text.strip():
            pieces.append(text)
    joined = "".join(pieces).strip()
    return _strip_tool_names(joined)


# Map internal function-tool identifiers to user-facing labels. Specialist
# AgentTool names are derived from `SPECIALISTS` below so the scrubber follows
# the canonical specialist roster automatically.
_FUNCTION_TOOL_LABELS: dict[str, str] = {
    "search_restaurants": "Google Maps search",
    "find_nearby_restaurants": "nearby Google Maps lookup",
    "get_restaurant_details": "venue lookup",
    "get_batch_restaurant_details": "batch venue lookup",
    "find_tripadvisor_restaurant": "TripAdvisor match",
    "get_tripadvisor_reviews": "TripAdvisor reviews",
    "get_google_reviews": "Google reviews",
    "google_search": "Google search",
    "fetch_web_content": "page fetch",
    "narrate": "narration",
}
_SPECIALIST_TOOL_LABELS: dict[str, str] = {s.name: s.label for s in SPECIALISTS}
_TOOL_LABELS: dict[str, str] = {**_FUNCTION_TOOL_LABELS, **_SPECIALIST_TOOL_LABELS}

_BARE_TOOL_LABELS: dict[str, str] = {
    name: label
    for name, label in _TOOL_LABELS.items()
    if "_" in name or name in _FUNCTION_TOOL_LABELS
}
_BACKTICKED_TOOL_NAME_RE = re.compile(
    r"`(" + "|".join(re.escape(name) for name in _TOOL_LABELS) + r")`"
)
_BARE_TOOL_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _BARE_TOOL_LABELS) + r")\b"
)


def _strip_tool_names(text: str) -> str:
    """Replace internal tool identifiers with user-facing labels.

    Backticked identifiers are always scrubbed. Bare identifiers are scrubbed
    only when they are unlikely to be normal prose; this avoids rewriting text
    like "restaurant operations" while still catching names such as
    `review_analyst`.
    """
    stripped = _BACKTICKED_TOOL_NAME_RE.sub(lambda m: _TOOL_LABELS[m.group(1)], text)
    return _BARE_TOOL_NAME_RE.sub(lambda m: _BARE_TOOL_LABELS[m.group(1)], stripped)


def _extract_search_queries(event: Any) -> list[str]:
    """List the queries Gemini ran via built-in Google Search grounding.

    Lives on `event.grounding_metadata.web_search_queries`. Returns an
    empty list when no grounding metadata is attached or no queries were
    issued. De-dupes within a single event so a model that lists the
    same query twice doesn't render two adjacent rows.
    """
    gm = _get(event, "grounding_metadata")
    if not gm:
        return []
    queries = _get(gm, "web_search_queries") or []
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        if not isinstance(q, str):
            continue
        cleaned = q.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def extract_sources_from_grounding(event: Any) -> list[dict[str, Any]]:
    gm = _get(event, "grounding_metadata")
    if not gm:
        return []
    chunks = _get(gm, "grounding_chunks") or []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        web = _get(chunk, "web")
        if not web:
            continue
        uri = _get(web, "uri")
        if not isinstance(uri, str) or not uri or uri in seen:
            continue
        seen.add(uri)
        entry: dict[str, Any] = {"title": _get(web, "title") or uri, "url": uri}
        domain = _get(web, "domain")
        if domain:
            entry["domain"] = domain
        out.append(entry)
    return out


def _map_complete(event: Any) -> dict[str, Any] | None:
    if not _is_final(event):
        return None

    reply: str | None = None
    # `final_report_followup` is the follow-up agent's output_key (kept
    # distinct so a follow-up reply doesn't clobber the original report
    # in session state). `final_report` is the research lead's. Each event
    # carries at most one of them in its state delta — same turn, same
    # author — so checking both is collision-free.
    for key in ("final_report_followup", "final_report"):
        if _has_state_delta(event, key):
            candidate = _state_delta(event).get(key)
            if isinstance(candidate, str) and candidate.strip():
                reply = candidate
                break

    if reply is None:
        text = _collect_text(event).strip()
        if text:
            reply = text

    if not reply:
        return None

    return {"reply": reply, "sources": extract_sources_from_grounding(event)}


def _tool_row_id(*, call_id: str | None, phase: str, name: str) -> str:
    return f"tool:{phase}:{call_id or 'unknown'}:{name}"


def map_tool_call(
    name: str,
    args: dict[str, Any],
    state: dict[str, Any] | None,
    call_id: str | None,
) -> dict[str, Any] | None:
    row_id = _tool_row_id(call_id=call_id, phase="call", name=name)
    if name == "narrate":
        text = args.get("text")
        if isinstance(text, str) and text.strip():
            return {
                "kind": "note",
                "id": row_id,
                "text": text.strip(),
            }
        return None
    if name == "google_search":
        query = _normalize_space(str(args.get("query") or "")).strip()
        if query:
            return _detail(row_id, "search", "Searching the web", query)
        return None
    if name == "fetch_web_content":
        url = str(args.get("url") or "").strip()
        if url:
            return _detail(row_id, "source", "Public sources", _short_url(url))
        return None
    if name == "search_restaurants":
        query = _normalize_space(str(args.get("query") or "")).strip()
        if query:
            return _detail(row_id, "platform", "Google Maps", query)
        return _detail(row_id, "platform", "Google Maps", "Searching places")
    if name == "find_tripadvisor_restaurant":
        place = _normalize_space(str(args.get("name") or "")).strip()
        return _detail(
            row_id,
            "platform",
            "TripAdvisor",
            f"Matching {place}" if place else "Matching venue",
        )
    if name == "get_google_reviews":
        place_id = str(args.get("place_id") or "").strip()
        place = _place_name(state, place_id)
        return _detail(
            row_id,
            "platform",
            "Google reviews",
            f"Checking {place}" if place else "Checking reviews",
        )
    if name == "get_tripadvisor_reviews":
        return _detail(row_id, "platform", "TripAdvisor", "Reading reviews")
    return None


def map_tool_result(
    name: str,
    response: dict[str, Any],
    state: dict[str, Any] | None,
    call_id: str | None,
) -> list[dict[str, Any]]:
    row_id = _tool_row_id(call_id=call_id, phase="response", name=name)
    rows: list[dict[str, Any]] = []
    status = str(response.get("status") or "").strip().lower()

    if name == "get_restaurant_details" and status == "success":
        place = response.get("place") if isinstance(response.get("place"), dict) else {}
        display_name = _get(place.get("displayName") if isinstance(place, dict) else None, "text")
        if isinstance(display_name, str) and display_name.strip():
            rows.append(_detail(row_id, "platform", "Google Maps", f"Profile for {display_name.strip()}"))
        return rows

    if name == "get_batch_restaurant_details" and status == "success":
        places = response.get("places")
        if isinstance(places, list):
            rows.append(
                _detail(row_id, "platform", "Google Maps", f"{len(places)} place profiles")
            )
        return rows

    if name in ("find_nearby_restaurants", "search_restaurants") and status == "success":
        results = response.get("results")
        if isinstance(results, list):
            label = "nearby places" if name == "find_nearby_restaurants" else "place matches"
            rows.append(_detail(row_id, "platform", "Google Maps", f"{len(results)} {label}"))
        return rows

    if name == "find_tripadvisor_restaurant":
        display_name = str(response.get("name") or "").strip() or str(response.get("title") or "").strip()
        if status == "unverified":
            rows.append(
                _detail(
                    row_id,
                    "warning",
                    "Warnings",
                    f"TripAdvisor match not verified for {display_name or 'the venue'}",
                )
            )
            return rows
        if status == "success":
            rows.append(
                _detail(
                    row_id,
                    "platform",
                    "TripAdvisor",
                    f"Matched {display_name}" if display_name else "Matched venue",
                )
            )
        elif status == "error":
            rows.append(
                _detail(row_id, "warning", "Warnings", "TripAdvisor lookup failed")
            )
        return rows

    if name == "get_tripadvisor_reviews":
        if status == "success":
            count = int(response.get("fetched_reviews") or 0)
            rows.append(
                _detail(row_id, "platform", "TripAdvisor", f"{count} reviews loaded")
            )
        elif status == "error":
            rows.append(
                _detail(row_id, "warning", "Warnings", "TripAdvisor reviews unavailable")
            )
        return rows

    if name == "get_google_reviews":
        place_id = str(response.get("place_id") or "").strip()
        place = _place_name(state, place_id)
        if status == "success":
            count = int(response.get("total_fetched") or 0)
            label = f"{count} reviews for {place}" if place else f"{count} Google reviews"
            rows.append(_detail(row_id, "platform", "Google reviews", label))
        elif status == "error":
            rows.append(
                _detail(
                    row_id,
                    "warning",
                    "Warnings",
                    f"Google reviews unavailable for {place}" if place else "Google reviews unavailable",
                )
            )
        return rows

    if name == "fetch_web_content" and status == "error":
        rows.append(_detail(row_id, "warning", "Warnings", "Source fetch failed"))

    return rows


def map_tool_error(
    name: str,
    args: dict[str, Any],
    state: dict[str, Any] | None,
    call_id: str | None,
) -> list[dict[str, Any]]:
    synthetic_response = dict(args)
    synthetic_response["status"] = "error"
    return map_tool_result(name, synthetic_response, state, call_id)


def _ingest_place_names(event: Any, state: dict[str, Any] | None) -> None:
    if state is None:
        return
    place_names = state.setdefault("place_names", {})
    if not isinstance(place_names, dict):
        return
    for key, value in _state_delta(event).items():
        if not key.startswith("_place_name_"):
            continue
        if isinstance(value, str) and value.strip():
            place_names[key.removeprefix("_place_name_")] = value.strip()


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _state_delta(event: Any) -> dict[str, Any]:
    actions = _get(event, "actions")
    sd = _get(actions, "state_delta") if actions else None
    return sd if isinstance(sd, dict) else {}


def _has_state_delta(event: Any, key: str) -> bool:
    sd = _state_delta(event)
    if key not in sd:
        return False
    value = sd[key]
    if not value:
        return False
    return True


def _collect_text(event: Any) -> str:
    chunks: list[str] = []
    for part in _iter_parts(event):
        text = _get(part, "text")
        if text:
            chunks.append(text)
    return "".join(chunks)


def _is_final(event: Any) -> bool:
    fn = getattr(event, "is_final_response", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return False
    return bool(_get(event, "is_final"))
