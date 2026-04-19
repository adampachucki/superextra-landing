"""Reference skeleton for Phase 2's ADK-event → Firestore-event mapper.

NOT production — scaffolding showing the dispatch shape. Copy to
`agent/superextra_agent/firestore_events.py` during Phase 2 and fill in TODOs.

Based on spike B event taxonomy (see
spikes/adk_event_taxonomy_dump.json for 27 real events to test against and
docs/pipeline-decoupling-spike-results.md §B for the full mapping rules).

Pattern: every ADK `Event` from `Runner.run_async` flows through `map_and_write_event`.
The mapper decides what (if anything) to emit to Firestore — the browser-facing
progress stream. Each emitted event doc has shape:

    { userId, runId, attempt, seqInAttempt, type, data, ts, expiresAt }

where `type` is one of: 'progress' | 'activity' | 'token' | 'complete' | 'error'
(matching `src/lib/sse-client.ts` callback shapes — UI tree doesn't change).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from google.adk.events.event import Event
from google.cloud import firestore

log = logging.getLogger(__name__)

# Specialist author → UI activity-category mapping
_SPECIALIST_AUTHORS = {
    "market_landscape", "menu_pricing", "revenue_sales", "guest_intelligence",
    "location_traffic", "operations", "marketing_digital", "review_analyst",
    "dynamic_researcher_1", "gap_researcher",
}

# Specialist output_key → display label
_OUTPUT_KEY_TO_LABEL = {
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

# Author → state_delta key that signals that author's completion
_AUTHOR_TO_OUTPUT_KEY = {
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

# Markdown link extraction for source harvesting (matches functions/utils.js regex)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)(?:\{([^}]*)\})?")

# Tool-call labels (mirror TOOL_LABELS in functions/utils.js)
_TOOL_LABELS = {
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

EVENT_TTL_DAYS = 30


async def map_and_write_event(
    *,
    fs: firestore.Client,
    sid: str,
    user_id: str,
    run_id: str,
    attempt: int,
    seq_in_attempt: int,
    event: Event,
) -> None:
    """Dispatch an ADK Event to zero-or-more Firestore event writes.

    Each emitted doc gets (userId, runId, attempt, seqInAttempt, type, data, ts, expiresAt).
    Multiple emissions from one ADK event (e.g. specialist completion → activity + read events
    for sources) share the same (attempt, seqInAttempt) base but extend with sub-seq? TODO:
    decide if that's needed. For MVP, emit at most one doc per ADK event.
    """
    emission = _map_event(event)
    if emission is None:
        return

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
    # firestore sync client — offload to thread
    import asyncio
    await asyncio.to_thread(ref.set, doc)


# ── Dispatcher ──────────────────────────────────────────────────────────────

def _map_event(event: Event) -> dict | None:
    """Return {'type': ..., 'data': ...} or None if nothing to emit.

    Rules table from spike-results doc §B:
      - Router's transfer_to_agent        → optional progress event
      - Enricher Places tool calls        → activity.data
      - Enricher's places_context final   → progress 'context done'
      - Orchestrator's set_specialist_briefs → activity.analyze per specialist
      - Orchestrator's research_plan final → progress 'planning done'
      - Specialist function_calls         → activity.search
      - Specialist grounding_metadata     → activity.read (one per source)
      - Specialist output_key final       → activity.analyze complete
      - Specialist final + no state_delta → skip (NOT_RELEVANT)
      - Synthesizer final_report         → complete
    """
    author = event.author

    # 1. Router / agent transfer events
    if author == "router":
        fc = _first_function_call(event)
        if fc and fc.name == "transfer_to_agent":
            return None  # UI doesn't need explicit router events
        if event.is_final_response():
            # Router final text = "I need clarification" — surface as a complete
            text = _collect_text(event)
            if text:
                return {"type": "complete", "data": {"reply": text, "sources": []}}
        return None

    # 2. Context enricher
    if author == "context_enricher":
        fc = _first_function_call(event)
        if fc:
            return {"type": "activity", "data": {
                "category": "data",
                "id": _activity_id_for_tool(fc.name),
                "status": "running",
                "label": _TOOL_LABELS.get(fc.name, fc.name),
                "agent": author,
            }}
        if _has_state_delta(event, "places_context"):
            return {"type": "progress", "data": {"stage": "context", "status": "complete", "label": "Gathering data — Done"}}
        return None

    # 3. Research orchestrator
    if author == "research_orchestrator":
        fc = _first_function_call(event)
        if fc and fc.name == "set_specialist_briefs":
            # Emit pending activities for each briefed specialist
            # TODO: unpack fc.args['briefs'] dict — keys are specialist names
            return {"type": "activity", "data": {
                "category": "analyze",
                "id": "orchestrator-briefs",
                "status": "running",
                "label": "Assigning specialists",
                "agent": author,
            }}
        if _has_state_delta(event, "research_plan"):
            return {"type": "progress", "data": {"stage": "planning", "status": "complete", "label": "Planning — Done"}}
        return None

    # 4. Specialists (incl. gap_researcher, dynamic_researcher_1)
    if author in _SPECIALIST_AUTHORS:
        fc = _first_function_call(event)
        if fc:
            return {"type": "activity", "data": {
                "category": "search" if fc.name == "google_search" else "data",
                "id": f"{author}-{fc.name}-{event.id}",
                "status": "running",
                "label": _TOOL_LABELS.get(fc.name, fc.name),
                "agent": author,
            }}
        if event.is_final_response():
            output_key = _AUTHOR_TO_OUTPUT_KEY.get(author)
            if output_key and _has_state_delta(event, output_key):
                # TODO: extract sources from state_delta[output_key] text via _MD_LINK_RE
                return {"type": "activity", "data": {
                    "category": "analyze",
                    "id": f"analyze-{author}",
                    "status": "complete",
                    "label": _OUTPUT_KEY_TO_LABEL.get(output_key, author),
                    "agent": author,
                    "detail": _text_excerpt(event, max_len=200),
                }}
            # No state_delta — NOT_RELEVANT skip; emit nothing
            return None
        return None

    # 5. Synthesizer final
    if author == "synthesizer":
        if event.is_final_response() and _has_state_delta(event, "final_report"):
            text = event.actions.state_delta["final_report"]
            sources = _extract_sources(text)
            return {"type": "complete", "data": {"reply": text, "sources": sources}}
        return None

    # 6. Unknown author — log once and skip
    log.warning("unmapped event author=%s", author)
    return None


# ── Helpers ─────────────────────────────────────────────────────────────────

def _first_function_call(event: Event) -> Any | None:
    if not event.content or not event.content.parts:
        return None
    for part in event.content.parts:
        if getattr(part, "function_call", None):
            return part.function_call
    return None


def _has_state_delta(event: Event, key: str) -> bool:
    return bool(
        event.actions
        and event.actions.state_delta
        and key in event.actions.state_delta
        and event.actions.state_delta[key]
        and event.actions.state_delta[key] != "NOT_RELEVANT"
    )


def _collect_text(event: Event) -> str:
    if not event.content or not event.content.parts:
        return ""
    return "".join(p.text for p in event.content.parts if getattr(p, "text", None))


def _text_excerpt(event: Event, max_len: int = 200) -> str:
    txt = _collect_text(event)
    return txt[:max_len] + ("…" if len(txt) > max_len else "")


def _activity_id_for_tool(name: str) -> str:
    return {
        "get_restaurant_details": "data-primary",
        "find_nearby_restaurants": "data-check",
        "search_restaurants": "data-check",
    }.get(name, f"data-{name}")


def _extract_sources(text: str) -> list[dict]:
    """Parse markdown links from specialist output. Mirrors extractSourcesFromText
    in functions/utils.js:1-80. Use seen-set to dedupe."""
    seen: set[str] = set()
    out: list[dict] = []
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
