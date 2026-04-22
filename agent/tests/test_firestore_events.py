"""Unit tests for the ADK-event → Firestore event mapper.

Uses synthesised `SimpleNamespace` events to exercise every mapping rule from
the spike-results taxonomy (docs/pipeline-decoupling-spike-results.md §B).
Parity with today's `parseADKStream` (functions/utils.js:200-678) is verified
by asserting the mapper emits the same `type` + key payload shape for each
canonical trigger; exact state-tracking/aggregation is left to the frontend.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from superextra_agent.firestore_events import (
    AUTHOR_TO_OUTPUT_KEY,
    TOOL_LABELS,
    extract_sources_from_grounding,
    map_event,
)


# ── Builders ───────────────────────────────────────────────────────────────


def _event(
    *,
    author: str | None = None,
    text: str | None = None,
    function_call: tuple[str, dict[str, Any]] | None = None,
    function_response: tuple[str, dict[str, Any]] | None = None,
    state_delta: dict[str, Any] | None = None,
    grounding_chunks: list[dict[str, Any]] | None = None,
    is_final: bool = False,
    event_id: str = "evt-1",
) -> SimpleNamespace:
    parts: list[SimpleNamespace] = []
    if text is not None:
        parts.append(SimpleNamespace(text=text, function_call=None, function_response=None))
    if function_call is not None:
        name, args = function_call
        parts.append(
            SimpleNamespace(
                text=None,
                function_call=SimpleNamespace(name=name, args=args),
                function_response=None,
            )
        )
    if function_response is not None:
        name, response = function_response
        parts.append(
            SimpleNamespace(
                text=None,
                function_call=None,
                function_response=SimpleNamespace(name=name, response=response),
            )
        )

    content = SimpleNamespace(parts=parts or None)
    actions = SimpleNamespace(state_delta=state_delta or None)

    grounding_metadata = None
    if grounding_chunks is not None:
        gchunks = [
            SimpleNamespace(
                web=SimpleNamespace(
                    uri=c.get("uri"),
                    title=c.get("title"),
                    domain=c.get("domain"),
                )
            )
            for c in grounding_chunks
        ]
        grounding_metadata = SimpleNamespace(grounding_chunks=gchunks)

    return SimpleNamespace(
        author=author,
        id=event_id,
        content=content,
        actions=actions,
        grounding_metadata=grounding_metadata,
        is_final_response=lambda: is_final,
    )


# ── Router ─────────────────────────────────────────────────────────────────


def test_router_transfer_to_agent_emits_nothing():
    ev = _event(
        author="router",
        function_call=("transfer_to_agent", {"agent_name": "research_pipeline"}),
    )
    assert map_event(ev) is None


def test_router_final_text_reply_becomes_complete():
    ev = _event(
        author="router",
        text="Could you clarify which restaurant you're asking about?",
        is_final=True,
    )
    emission = map_event(ev)
    assert emission is not None
    assert emission["type"] == "complete"
    assert emission["data"]["reply"].startswith("Could you clarify")
    assert emission["data"]["sources"] == []


def test_router_non_final_text_is_dropped():
    ev = _event(author="router", text="internal deliberation", is_final=False)
    assert map_event(ev) is None


# ── Context enricher ───────────────────────────────────────────────────────


def test_enricher_places_tool_call_emits_running_activity():
    ev = _event(
        author="context_enricher",
        function_call=("get_restaurant_details", {"place_id": "ChIJxxxx"}),
    )
    emission = map_event(ev)
    assert emission == {
        "type": "activity",
        "data": {
            "category": "data",
            "id": "data-primary",
            "status": "running",
            "label": TOOL_LABELS["get_restaurant_details"],
            "agent": "context_enricher",
        },
    }


def test_enricher_nearby_search_uses_shared_activity_id():
    ev = _event(
        author="context_enricher",
        function_call=("find_nearby_restaurants", {"latitude": 52.5, "longitude": 13.4}),
    )
    emission = map_event(ev)
    assert emission["data"]["id"] == "data-check"


def test_enricher_places_context_delta_emits_context_complete():
    ev = _event(
        author="context_enricher",
        is_final=True,
        state_delta={"places_context": "Display Name: Umami\n1,234 reviews"},
    )
    emission = map_event(ev)
    assert emission == {
        "type": "progress",
        "data": {
            "stage": "context",
            "status": "complete",
            "label": "Place data gathered",
        },
    }


# ── Research orchestrator ──────────────────────────────────────────────────


def test_orchestrator_briefs_unpacks_specialists():
    ev = _event(
        author="research_orchestrator",
        function_call=(
            "set_specialist_briefs",
            {
                "briefs": {
                    "review_analyst": "Pull reviews",
                    "guest_intelligence": "Sentiment",
                }
            },
        ),
    )
    emission = map_event(ev)
    assert emission is not None
    assert emission["type"] == "activity"
    assert emission["data"]["category"] == "analyze"
    assert emission["data"]["id"] == "orchestrator-briefs"
    assert emission["data"]["agent"] == "research_orchestrator"
    assert emission["data"]["specialists"] == ["guest_intelligence", "review_analyst"]


def test_orchestrator_research_plan_delta_emits_planning_complete():
    ev = _event(
        author="research_orchestrator",
        is_final=True,
        state_delta={"research_plan": "Step 1..."},
    )
    emission = map_event(ev)
    assert emission["type"] == "progress"
    assert emission["data"]["stage"] == "planning"
    assert emission["data"]["status"] == "complete"


# ── Specialists ─────────────────────────────────────────────────────────────


def test_specialist_google_search_emits_search_activity_with_query_detail():
    long_q = "x" * 150  # >100 chars so truncation kicks in
    ev = _event(
        author="marketing_digital",
        function_call=("google_search", {"query": long_q}),
    )
    emission = map_event(ev)
    assert emission["type"] == "activity"
    data = emission["data"]
    assert data["category"] == "search"
    assert data["agent"] == "marketing_digital"
    assert data["label"] == TOOL_LABELS["google_search"]
    assert data["detail"].endswith("…")
    assert len(data["detail"]) == 98  # 97 chars + 1-char ellipsis


def test_specialist_short_query_is_not_truncated():
    ev = _event(
        author="marketing_digital",
        function_call=("google_search", {"query": "coffee Berlin"}),
    )
    emission = map_event(ev)
    assert emission["data"]["detail"] == "coffee Berlin"


def test_specialist_fetch_web_content_is_search_category():
    ev = _event(
        author="location_traffic",
        function_call=("fetch_web_content", {"url": "https://example.com"}),
    )
    emission = map_event(ev)
    assert emission["data"]["category"] == "search"
    assert emission["data"]["detail"] == "https://example.com"


def test_specialist_tripadvisor_tool_is_data_category():
    ev = _event(
        author="review_analyst",
        function_call=("find_tripadvisor_restaurant", {"query": "Umami Berlin"}),
    )
    emission = map_event(ev)
    assert emission["data"]["category"] == "data"
    assert emission["data"]["agent"] == "review_analyst"


def test_specialist_final_with_output_key_emits_analyze_complete():
    """Without grounding metadata, sources[] is empty — the markdown-link
    fallback was removed after the deadness test showed it contributed
    zero URLs across three live runs."""
    ev = _event(
        author="guest_intelligence",
        is_final=True,
        state_delta={"guest_result": "Analysis: sentiment is mixed.\n\n[Link](https://example.com)"},
    )
    emission = map_event(ev)
    assert emission["type"] == "activity"
    assert emission["data"]["category"] == "analyze"
    assert emission["data"]["id"] == f"analyze-guest_intelligence"
    assert emission["data"]["status"] == "complete"
    assert emission["data"]["label"] == "Guest Intelligence"
    assert emission["data"]["sources"] == []


def test_specialist_final_uses_grounding_chunks():
    """Sources come from grounding_metadata, which the in-process Runner
    exposes directly on the event."""
    ev = _event(
        author="review_analyst",
        is_final=True,
        state_delta={"review_result": "Some analysis text."},
        grounding_chunks=[
            {"uri": "https://ta.com/r/1", "title": "Review 1", "domain": "tripadvisor.com"},
        ],
    )
    emission = map_event(ev)
    assert emission["data"]["sources"] == [
        {"title": "Review 1", "url": "https://ta.com/r/1", "domain": "tripadvisor.com"}
    ]


def test_specialist_final_not_relevant_is_skipped():
    """Specialists that had no brief return the literal 'NOT_RELEVANT' text
    via `_make_skip_callback` — we must not emit a completion for them."""
    ev = _event(
        author="operations",
        is_final=True,
        state_delta={"ops_result": "NOT_RELEVANT"},
    )
    assert map_event(ev) is None


def test_specialist_final_with_no_matching_output_key_is_skipped():
    ev = _event(author="operations", is_final=True, state_delta={"other_key": "x"})
    assert map_event(ev) is None


def test_every_specialist_author_has_output_key_mapping():
    """Guard: if we add a new specialist without wiring AUTHOR_TO_OUTPUT_KEY,
    the mapper silently drops its completion. Fail loud instead."""
    from superextra_agent.firestore_events import SPECIALIST_AUTHORS

    missing = SPECIALIST_AUTHORS - AUTHOR_TO_OUTPUT_KEY.keys()
    assert missing == set(), f"specialists missing output_key mapping: {missing}"


# ── Synthesizer ────────────────────────────────────────────────────────────


def test_synthesizer_final_report_emits_complete():
    """Synth sources come from grounding metadata only. Markdown links in
    the reply text are no longer extracted — the deadness test showed the
    fallback contributed zero URLs across three live runs."""
    ev = _event(
        author="synthesizer",
        is_final=True,
        state_delta={
            "final_report": "# Report\n\nBody...\n\n[Docs](https://example.com/doc)"
        },
    )
    emission = map_event(ev)
    assert emission["type"] == "complete"
    assert emission["data"]["reply"].startswith("# Report")
    assert emission["data"]["sources"] == []


def test_synthesizer_no_final_report_no_text_is_skipped():
    ev = _event(author="synthesizer", is_final=True, state_delta={})
    assert map_event(ev) is None


def test_synthesizer_text_only_final_emits_complete():
    """Intermittent live-run failure mode (P1 in
    docs/pipeline-decoupling-implementation-review-2026-04-21.md): the final
    synthesizer event carries text parts but no state_delta.final_report.
    Before the P1 fix, the mapper returned None here → no complete event →
    worker sanity gate flipped to status=error/empty_or_malformed_reply.
    Post-fix, the text parts are promoted to the complete event's reply."""
    ev = _event(
        author="synthesizer",
        is_final=True,
        text="# Report\n\nSummary of findings.",
        state_delta={},
    )
    emission = map_event(ev)
    assert emission is not None, "text-only final must promote to complete"
    assert emission["type"] == "complete"
    assert emission["data"]["reply"].startswith("# Report")


def test_synthesizer_prefers_final_report_over_text_parts():
    """When both are present, state_delta.final_report wins (preserves the
    current format-normalization semantics for the default path)."""
    ev = _event(
        author="synthesizer",
        is_final=True,
        text="Raw unpolished draft.",
        state_delta={"final_report": "# Polished Report\n\nBody."},
    )
    emission = map_event(ev)
    assert emission["data"]["reply"] == "# Polished Report\n\nBody."


def test_synthesizer_sources_come_from_grounding():
    """Synth sources are harvested from grounding metadata exclusively."""
    ev = _event(
        author="synthesizer",
        is_final=True,
        text="See [A](https://a.com) and [B](https://b.com).",
        state_delta={},
        grounding_chunks=[
            {"uri": "https://a.com", "title": "A"},
            {"uri": "https://c.com", "title": "C"},
        ],
    )
    emission = map_event(ev)
    urls = {s["url"] for s in emission["data"]["sources"]}
    assert urls == {"https://a.com", "https://c.com"}


def test_synthesizer_whitespace_only_final_report_falls_back_to_text():
    """`_has_state_delta` filters empty-string/None already, but a
    whitespace-only value still passes — so the widened mapper should treat
    it as missing and fall through to the text-parts branch."""
    ev = _event(
        author="synthesizer",
        is_final=True,
        text="Actual reply text.",
        state_delta={"final_report": "   "},
    )
    emission = map_event(ev)
    assert emission["data"]["reply"] == "Actual reply text."


def test_follow_up_final_report_emits_complete():
    # Follow-up turns go through the `follow_up` LlmAgent (see agent.py:278),
    # which shares `output_key="final_report"` with synthesizer. The mapper
    # must dispatch `author="follow_up"` to the same handler — without this,
    # every follow-up turn's terminal event is dropped and the worker flips
    # the session to status=error via the empty-reply sanity gate.
    ev = _event(
        author="follow_up",
        is_final=True,
        state_delta={
            "final_report": "Your previous question was about service issues."
        },
    )
    emission = map_event(ev)
    assert emission is not None, "follow_up terminal must not be dropped"
    assert emission["type"] == "complete"
    assert emission["data"]["reply"].startswith("Your previous question")
    assert emission["data"]["sources"] == []


def test_follow_up_no_final_report_no_text_is_skipped():
    ev = _event(author="follow_up", is_final=True, state_delta={})
    assert map_event(ev) is None


def test_follow_up_text_only_final_emits_complete():
    """Follow-up shares the synthesizer's mapper branch — the text-only
    fallback applies to follow-up turns too."""
    ev = _event(
        author="follow_up",
        is_final=True,
        text="Based on the prior report, pricing clusters around PLN 35-45.",
        state_delta={},
    )
    emission = map_event(ev)
    assert emission is not None
    assert emission["type"] == "complete"
    assert emission["data"]["reply"].startswith("Based on the prior report")


# ── Source harvesting ──────────────────────────────────────────────────────


def test_extract_sources_from_grounding_handles_missing_fields():
    ev = _event(grounding_chunks=[{"uri": "https://a.com"}])
    # title falls back to uri; domain omitted when absent
    assert extract_sources_from_grounding(ev) == [{"title": "https://a.com", "url": "https://a.com"}]


def test_extract_sources_from_grounding_skips_chunks_without_uri():
    ev = _event(grounding_chunks=[{"title": "no uri"}, {"uri": "https://a.com"}])
    assert extract_sources_from_grounding(ev) == [
        {"title": "https://a.com", "url": "https://a.com"}
    ]


def test_unknown_author_is_skipped():
    ev = _event(author="mystery_agent", text="hello")
    assert map_event(ev) is None


# ── Parity sanity check with spike fixture (metadata-level) ────────────────


def test_fixture_coverage_smoke():
    """For each author seen in the taxonomy dump, at least one mapping rule
    should exist. Uses the counts in `adk_event_taxonomy_dump.json` as the
    source of truth."""
    import json
    from pathlib import Path

    fx = json.loads(
        (
            Path(__file__).resolve().parent.parent.parent
            / "spikes"
            / "adk_event_taxonomy_dump.json"
        ).read_text()
    )
    observed_authors = set(fx["authors"].keys())
    known = {
        "router",
        "context_enricher",
        "research_orchestrator",
        "synthesizer",
    } | set(AUTHOR_TO_OUTPUT_KEY.keys())
    missing = observed_authors - known
    assert missing == set(), f"authors not handled by mapper: {missing}"
