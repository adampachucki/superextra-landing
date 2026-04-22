"""Map ADK Runner events to Firestore event docs.

The worker calls `map_and_write_event(...)` on every event yielded from
`runner.run_async()`. The mapper is stateless — it decides _what_ (if
anything) to emit for a single event and returns a doc shape the UI already
understands (progress / activity / complete / error).

See `docs/pipeline-decoupling-spike-results.md` §B for the source-of-truth
taxonomy (27 captured events covering every author + state-delta key we
actually see in the pipeline).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

log = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

EVENT_TTL_DAYS = 30

# Specialist agent authors (incl. gap_researcher which behaves like one).
SPECIALIST_AUTHORS: set[str] = {
    "market_landscape",
    "menu_pricing",
    "revenue_sales",
    "guest_intelligence",
    "location_traffic",
    "operations",
    "marketing_digital",
    "review_analyst",
    "dynamic_researcher_1",
    "gap_researcher",
}

# Author → state_delta key that signals their final output.
AUTHOR_TO_OUTPUT_KEY: dict[str, str] = {
    "market_landscape": "market_result",
    "menu_pricing": "pricing_result",
    "revenue_sales": "revenue_result",
    "guest_intelligence": "guest_result",
    "location_traffic": "location_result",
    "operations": "ops_result",
    "marketing_digital": "marketing_result",
    "review_analyst": "review_result",
    "dynamic_researcher_1": "dynamic_result_1",
    "gap_researcher": "dynamic_result_2",
}

OUTPUT_KEY_TO_LABEL: dict[str, str] = {
    "market_result": "Market Landscape",
    "pricing_result": "Menu & Pricing",
    "revenue_result": "Revenue & Sales",
    "guest_result": "Guest Intelligence",
    "location_result": "Location & Traffic",
    "ops_result": "Operations",
    "marketing_result": "Marketing & Digital",
    "review_result": "Review Analysis",
    "dynamic_result_1": "Dynamic Research",
    "dynamic_result_2": "Gap Research",
}

# Tool name → UI label (mirrors `TOOL_LABELS` / `PLACES_TOOL_LABELS` in
# `functions/utils.js`).
TOOL_LABELS: dict[str, str] = {
    "google_search": "Searching the web",
    "fetch_web_content": "Reading source",
    "get_restaurant_details": "Loading place details",
    "find_nearby_restaurants": "Checking nearby places",
    "search_restaurants": "Searching nearby places",
    "find_tripadvisor_restaurant": "Looking up TripAdvisor profile",
    "get_tripadvisor_reviews": "Fetching TripAdvisor reviews",
    "get_google_reviews": "Fetching Google reviews",
    "set_specialist_briefs": "Assigning specialists",
}

# Markdown link with optional {domain} suffix. Used by
# `extract_sources_from_text` as a rare fallback for specialists that
# embed citations inline in prose; grounding metadata is the primary path.
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)(?:\{([^}]*)\})?")


# ── Public: write a single ADK event to Firestore ──────────────────────────


async def map_and_write_event(
    *,
    fs: firestore.Client,
    sid: str,
    user_id: str,
    run_id: str,
    attempt: int,
    seq_in_attempt: int,
    event: Any,
) -> dict | None:
    """Dispatch an ADK Event to zero-or-one Firestore event writes.

    Returns the doc that was written (for logging) or None if the event was
    not mapped. Firestore writes are offloaded to a thread so we don't block
    the runner's async loop.
    """
    emission = map_event(event)
    if emission is None:
        return None

    doc = {
        "userId": user_id,
        "runId": run_id,
        "attempt": attempt,
        "seqInAttempt": seq_in_attempt,
        "type": emission["type"],
        "data": emission["data"],
        "ts": firestore.SERVER_TIMESTAMP,
        "expiresAt": datetime.now(timezone.utc) + timedelta(days=EVENT_TTL_DAYS),
    }
    ref = fs.collection("sessions").document(sid).collection("events").document()
    await asyncio.to_thread(ref.set, doc)
    return doc


# ── Pure mapping (testable) ─────────────────────────────────────────────────


def map_event(event: Any) -> dict | None:
    """Return `{"type": ..., "data": ...}` for an ADK Event, or None to skip.

    See the rules table in `docs/pipeline-decoupling-spike-results.md` §B.
    """
    author = _get(event, "author")

    if author == "router":
        return _map_router(event)

    if author == "context_enricher":
        return _map_enricher(event)

    if author == "research_orchestrator":
        return _map_orchestrator(event)

    if author in SPECIALIST_AUTHORS:
        return _map_specialist(event, author)

    # Both synthesizer (turn 1) and follow_up (turn N+1) emit the terminal
    # `final_report` state_delta; they share `output_key="final_report"` in
    # `agent.py`. Without this second branch, follow-up turns' terminal
    # events get dropped by the mapper, the worker's terminal-promotion logic
    # (which keys on `emitted["type"] == "complete"`) never fires, and the
    # reply-sanity gate flips the session to status=error.
    if author in ("synthesizer", "follow_up"):
        return _map_synthesizer(event)

    log.debug("unmapped event author=%s", author)
    return None


# ── Per-author handlers ─────────────────────────────────────────────────────


def _map_router(event: Any) -> dict | None:
    fc = _first_function_call(event)
    if fc and getattr(fc, "name", None) == "transfer_to_agent":
        # Internal routing — UI doesn't need it.
        return None
    if _is_final(event):
        text = _collect_text(event)
        if text:
            # Router produced a terminal reply (usually a clarification).
            return {"type": "complete", "data": {"reply": text, "sources": []}}
    return None


def _map_enricher(event: Any) -> dict | None:
    fc = _first_function_call(event)
    if fc:
        name = getattr(fc, "name", "") or ""
        return {
            "type": "activity",
            "data": {
                "category": "data",
                "id": _activity_id_for_tool(name),
                "status": "running",
                "label": TOOL_LABELS.get(name, name),
                "agent": "context_enricher",
            },
        }
    if _has_state_delta(event, "places_context"):
        return {
            "type": "progress",
            "data": {
                "stage": "context",
                "status": "complete",
                "label": "Place data gathered",
            },
        }
    return None


def _map_orchestrator(event: Any) -> dict | None:
    fc = _first_function_call(event)
    if fc and getattr(fc, "name", None) == "set_specialist_briefs":
        # Unpack the brief keys so the UI can render pending activity entries
        # for exactly the specialists that are about to run.
        args = getattr(fc, "args", None) or {}
        briefs = args.get("briefs") if isinstance(args, dict) else None
        specialists = sorted(briefs.keys()) if isinstance(briefs, dict) else []
        return {
            "type": "activity",
            "data": {
                "category": "analyze",
                "id": "orchestrator-briefs",
                "status": "running",
                "label": "Assigning specialists",
                "agent": "research_orchestrator",
                "specialists": specialists,
            },
        }
    if _has_state_delta(event, "research_plan"):
        return {
            "type": "progress",
            "data": {
                "stage": "planning",
                "status": "complete",
                "label": "Research planned",
            },
        }
    return None


def _map_specialist(event: Any, author: str) -> dict | None:
    fc = _first_function_call(event)
    if fc:
        name = getattr(fc, "name", "") or ""
        category = "search" if name in ("google_search", "fetch_web_content") else "data"
        label = TOOL_LABELS.get(name, name)
        # Specialist-level tool calls often include a query/URL in args —
        # surface a short version of it as detail so the UI can display
        # "Searching: <query>" instead of the generic label.
        args = getattr(fc, "args", None) or {}
        detail: str | None = None
        if isinstance(args, dict):
            raw = args.get("query") or args.get("url")
            if isinstance(raw, str):
                detail = raw if len(raw) <= 100 else raw[:97] + "…"
        data = {
            "category": category,
            "id": f"{author}-{name}-{_event_id(event)}",
            "status": "running",
            "label": label,
            "agent": author,
        }
        if detail:
            data["detail"] = detail
        return {"type": "activity", "data": data}

    if _is_final(event):
        output_key = AUTHOR_TO_OUTPUT_KEY.get(author)
        if output_key and _has_state_delta(event, output_key):
            text = _state_delta(event).get(output_key) or ""
            # Grounding metadata is the primary source — the in-process Runner
            # exposes it directly on the event. Markdown-link extraction
            # remains as a fallback for rare cases where a specialist embeds
            # citations inline in its prose instead of via grounded search.
            sources = extract_sources_from_grounding(event)
            if not sources:
                sources = extract_sources_from_text(text if isinstance(text, str) else "")
            return {
                "type": "activity",
                "data": {
                    "category": "analyze",
                    "id": f"analyze-{author}",
                    "status": "complete",
                    "label": OUTPUT_KEY_TO_LABEL.get(output_key, author),
                    "agent": author,
                    "sources": sources,
                },
            }
        # NOT_RELEVANT or otherwise no output — skip silently.
        return None
    return None


def _map_synthesizer(event: Any) -> dict | None:
    # Only the final event promotes to a terminal reply.
    if not _is_final(event):
        return None

    # Preferred source: `state_delta.final_report`. Both synthesizer and
    # follow_up agents are configured with `output_key="final_report"`, and
    # the state_delta path preserves today's format-normalization semantics.
    reply: str | None = None
    if _has_state_delta(event, "final_report"):
        candidate = _state_delta(event).get("final_report")
        if isinstance(candidate, str) and candidate.strip():
            reply = candidate

    # Fallback: the final event carried text parts but no state_delta. Seen
    # intermittently in live runs — the LLM emits the final model response as
    # content.parts[*].text without the state_delta write that output_key
    # usually performs. Without this branch the mapper returns None, no
    # complete event is written, and the worker sanity gate flips the
    # session to `status='error' / empty_or_malformed_reply`.
    if reply is None:
        parts_text = _collect_text(event).strip()
        if parts_text:
            reply = parts_text

    if not reply:
        return None

    # Harvest sources from grounding metadata first (in-process Runner
    # exposes it on the synth event), then fall back to markdown links in
    # the reply text. Both paths dedupe by URL internally; merging is safe.
    sources = extract_sources_from_grounding(event)
    text_sources = extract_sources_from_text(reply)
    seen = {s["url"] for s in sources}
    for s in text_sources:
        if s["url"] not in seen:
            sources.append(s)
            seen.add(s["url"])

    return {
        "type": "complete",
        "data": {"reply": reply, "sources": sources},
    }


# ── Source harvesting ───────────────────────────────────────────────────────


def extract_sources_from_grounding(event: Any) -> list[dict]:
    """Pull sources from `event.grounding_metadata.grounding_chunks` (Gemini
    grounded-search metadata). Dedupes by URL."""
    gm = _get(event, "grounding_metadata")
    if not gm:
        return []
    chunks = _get(gm, "grounding_chunks") or []
    out: list[dict] = []
    seen: set[str] = set()
    for chunk in chunks:
        web = _get(chunk, "web")
        if not web:
            continue
        uri = _get(web, "uri")
        if not uri or uri in seen:
            continue
        seen.add(uri)
        entry: dict[str, Any] = {
            "title": _get(web, "title") or uri,
            "url": uri,
        }
        domain = _get(web, "domain")
        if domain:
            entry["domain"] = domain
        out.append(entry)
    return out


def extract_sources_from_text(text: str) -> list[dict]:
    """Parse markdown links from specialist output. Mirrors
    `extractSourcesFromText` in `functions/utils.js`. Dedupes by URL."""
    out: list[dict] = []
    seen: set[str] = set()
    if not text:
        return out
    for m in _MD_LINK_RE.finditer(text):
        title, url, domain = m.group(1), m.group(2), m.group(3)
        if url in seen:
            continue
        seen.add(url)
        entry: dict[str, Any] = {"title": title or url, "url": url}
        if domain:
            entry["domain"] = domain
        out.append(entry)
    return out


# ── Internal helpers ────────────────────────────────────────────────────────


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Attribute access that also handles dict-shaped inputs (useful in tests
    where events are synthesised as SimpleNamespace / dict)."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _is_final(event: Any) -> bool:
    fn = getattr(event, "is_final_response", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            return False
    # Fallback for dict-shaped fixtures.
    return bool(_get(event, "is_final"))


def _event_id(event: Any) -> str:
    return str(_get(event, "id") or "")


def _first_function_call(event: Any) -> Any | None:
    content = _get(event, "content")
    parts = _get(content, "parts") if content else None
    if not parts:
        return None
    for part in parts:
        fc = _get(part, "function_call")
        if fc:
            return fc
    return None


def _state_delta(event: Any) -> dict:
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
    # Specialists that skip return the literal "NOT_RELEVANT" — don't treat
    # that as a real completion event.
    if isinstance(value, str) and value.strip() == "NOT_RELEVANT":
        return False
    return True


def _collect_text(event: Any) -> str:
    content = _get(event, "content")
    parts = _get(content, "parts") if content else None
    if not parts:
        return ""
    chunks: list[str] = []
    for p in parts:
        t = _get(p, "text")
        if t:
            chunks.append(t)
    return "".join(chunks)


def _activity_id_for_tool(name: str) -> str:
    return {
        "get_restaurant_details": "data-primary",
        "find_nearby_restaurants": "data-check",
        "search_restaurants": "data-check",
    }.get(name, f"data-{name}")
