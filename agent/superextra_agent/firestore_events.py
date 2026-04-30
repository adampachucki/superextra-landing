"""Map ADK Runner events into the simplified activity-timeline contract."""

from __future__ import annotations

import asyncio
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


def _iter_function_calls(event: Any) -> list[tuple[int, str, dict[str, Any]]]:
    out: list[tuple[int, str, dict[str, Any]]] = []
    for idx, part in enumerate(_iter_parts(event)):
        fc = _get(part, "function_call")
        if not fc:
            continue
        name = _get(fc, "name")
        if not isinstance(name, str) or not name:
            continue
        args = _get(fc, "args") or {}
        out.append((idx, name, args if isinstance(args, dict) else {}))
    return out


def _iter_function_responses(event: Any) -> list[tuple[int, str, dict[str, Any]]]:
    out: list[tuple[int, str, dict[str, Any]]] = []
    for idx, part in enumerate(_iter_parts(event)):
        fr = _get(part, "function_response")
        if not fr:
            continue
        name = _get(fr, "name")
        if not isinstance(name, str) or not name:
            continue
        response = _get(fr, "response") or {}
        out.append((idx, name, response if isinstance(response, dict) else {}))
    return out


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

    if author == "router":
        complete = _map_router_complete(event)
        if complete is not None:
            mapping["complete"] = complete
        return mapping

    if author in SPECIALIST_AUTHORS:
        output_key = AUTHOR_TO_OUTPUT_KEY.get(author)
        if output_key and _has_state_delta(event, output_key):
            mapping["grounding_sources"] = extract_sources_from_grounding(event)

    if author in ("research_lead", "follow_up"):
        complete = _map_final_complete(event)
        if complete is not None:
            mapping["complete"] = complete

    return mapping


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


def _map_router_complete(event: Any) -> dict[str, Any] | None:
    for _, name, _args in _iter_function_calls(event):
        if name == "transfer_to_agent":
            return None
    if not _is_final(event):
        return None
    text = _collect_text(event).strip()
    if not text:
        return None
    return {"reply": text, "sources": []}


def _map_final_complete(event: Any) -> dict[str, Any] | None:
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
