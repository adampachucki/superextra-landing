from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from superextra_agent.firestore_events import (
    extract_sources_from_grounding,
    map_event,
    map_tool_call,
    map_tool_result,
)


def _event(
    *,
    author: str | None = None,
    texts: list[str] | None = None,
    thoughts: list[str] | None = None,
    function_calls: list[tuple[str, dict[str, Any]]] | None = None,
    function_responses: list[tuple[str, dict[str, Any]]] | None = None,
    state_delta: dict[str, Any] | None = None,
    grounding_chunks: list[dict[str, Any]] | None = None,
    web_search_queries: list[str] | None = None,
    is_final: bool = False,
    event_id: str = "evt-1",
) -> SimpleNamespace:
    parts: list[SimpleNamespace] = []
    for thought in thoughts or []:
        parts.append(
            SimpleNamespace(text=thought, thought=True, function_call=None, function_response=None)
        )
    for text in texts or []:
        parts.append(
            SimpleNamespace(text=text, thought=False, function_call=None, function_response=None)
        )
    for name, args in function_calls or []:
        parts.append(
            SimpleNamespace(
                text=None,
                function_call=SimpleNamespace(name=name, args=args),
                function_response=None,
            )
        )
    for name, response in function_responses or []:
        parts.append(
            SimpleNamespace(
                text=None,
                function_call=None,
                function_response=SimpleNamespace(name=name, response=response),
            )
        )

    grounding_metadata = None
    if grounding_chunks is not None or web_search_queries is not None:
        grounding_metadata = SimpleNamespace(
            grounding_chunks=[
                SimpleNamespace(
                    web=SimpleNamespace(
                        uri=chunk.get("uri"),
                        title=chunk.get("title"),
                        domain=chunk.get("domain"),
                    )
                )
                for chunk in (grounding_chunks or [])
            ],
            web_search_queries=list(web_search_queries or []),
        )

    return SimpleNamespace(
        author=author,
        id=event_id,
        content=SimpleNamespace(parts=parts),
        actions=SimpleNamespace(state_delta=state_delta or None),
        grounding_metadata=grounding_metadata,
        is_final_response=lambda: is_final,
    )


def test_thought_parts_become_thought_timeline_row():
    ev = _event(
        author="research_lead",
        thoughts=["**Planning Research**\n\nI'll start by checking platform reviews."],
        event_id="evt-thought-1",
    )
    rows = map_event(ev, {})["timeline_events"]
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "thought"
    assert row["author"] == "research_lead"
    assert row["text"].startswith("**Planning Research**")
    assert row["id"] == "thought:research_lead:evt-thought-1"


def test_event_without_thought_parts_emits_no_thought_row():
    ev = _event(author="research_lead", texts=["final answer"])
    rows = map_event(ev, {})["timeline_events"]
    assert all(row.get("kind") != "thought" for row in rows)


def test_thought_with_blank_text_is_ignored():
    ev = _event(author="research_lead", thoughts=["   \n  "])
    rows = map_event(ev, {})["timeline_events"]
    assert all(row.get("kind") != "thought" for row in rows)


def test_thought_text_normalizes_escaped_newlines():
    ev = _event(
        author="research_lead",
        thoughts=["**Planning**\n\n\\n\\n\n\nFirst paragraph.\\n\\nSecond paragraph."],
    )
    rows = map_event(ev, {})["timeline_events"]
    text = next(r["text"] for r in rows if r["kind"] == "thought")
    assert "\\n" not in text
    assert text == "**Planning**\n\nFirst paragraph.\n\nSecond paragraph."


def test_thought_text_strips_bare_and_backticked_tool_names():
    ev = _event(
        author="research_lead",
        thoughts=[
            "I'll call `get_restaurant_details` to fetch the venue, then "
            "search_restaurants for nearby competitors and finally "
            "get_tripadvisor_reviews for sentiment."
        ],
    )
    rows = map_event(ev, {})["timeline_events"]
    text = next(r["text"] for r in rows if r["kind"] == "thought")
    # No internal identifier leaks
    assert "get_restaurant_details" not in text
    assert "search_restaurants" not in text
    assert "get_tripadvisor_reviews" not in text
    # User-facing labels appear instead
    assert "venue lookup" in text
    assert "Google Maps search" in text
    assert "TripAdvisor reviews" in text


def test_thought_text_strips_specialist_tool_names_without_rewriting_common_prose():
    ev = _event(
        author="research_lead",
        thoughts=[
            "Use review_analyst for hard numbers, then `dynamic_researcher_1` "
            "for niche sources. Restaurant operations should stay normal prose, "
            "but `operations` is a tool label."
        ],
    )
    rows = map_event(ev, {})["timeline_events"]
    text = next(r["text"] for r in rows if r["kind"] == "thought")
    assert "review_analyst" not in text
    assert "dynamic_researcher_1" not in text
    assert "`operations`" not in text
    assert "Review Analysis" in text
    assert "Dynamic Research" in text
    assert "Restaurant operations" in text
    assert "Operations is a tool label" in text


def test_thought_text_strips_provider_tool_aliases():
    ev = _event(
        author="dynamic_researcher_1",
        thoughts=[
            "Use `google:search` first, then `default_api:page fetch` for the "
            "source. If needed, default_api:fetch_web_content can read another page."
        ],
    )
    rows = map_event(ev, {})["timeline_events"]
    text = next(r["text"] for r in rows if r["kind"] == "thought")
    assert "google:search" not in text
    assert "default_api:page fetch" not in text
    assert "default_api:fetch_web_content" not in text
    assert "Google search" in text
    assert text.count("page fetch") == 2


def test_grounding_search_queries_become_searching_the_web_rows():
    ev = _event(
        author="research_lead",
        web_search_queries=[
            "warsaw neapolitan pizza market 2026",
            "mokotów dining trends",
        ],
        event_id="evt-search",
    )
    rows = map_event(ev, {})["timeline_events"]
    search_rows = [r for r in rows if r["kind"] == "detail" and r["family"] == "Searching the web"]
    assert len(search_rows) == 2
    assert search_rows[0]["text"] == "warsaw neapolitan pizza market 2026"
    assert search_rows[1]["text"] == "mokotów dining trends"
    # IDs are unique across the two rows
    assert search_rows[0]["id"] != search_rows[1]["id"]


def test_grounding_search_queries_dedupe_within_event():
    ev = _event(
        author="research_lead",
        web_search_queries=["warsaw pizza", "warsaw pizza", "  ", "warsaw pasta"],
    )
    rows = map_event(ev, {})["timeline_events"]
    search_rows = [r for r in rows if r["kind"] == "detail" and r["family"] == "Searching the web"]
    assert [r["text"] for r in search_rows] == ["warsaw pizza", "warsaw pasta"]


def test_event_without_grounding_emits_no_search_rows():
    ev = _event(author="research_lead", texts=["plain text"])
    rows = map_event(ev, {})["timeline_events"]
    assert all(r.get("family") != "Searching the web" for r in rows)


def test_router_transfer_is_ignored():
    ev = _event(author="router", function_calls=[("transfer_to_agent", {"agent_name": "research"})])
    mapped = map_event(ev, {})
    assert mapped["complete"] is None
    assert mapped["timeline_events"] == []


def test_router_text_reply_becomes_complete():
    ev = _event(author="router", texts=["Need clarification"], is_final=True)
    mapped = map_event(ev, {})
    assert mapped["complete"] == {"reply": "Need clarification", "sources": []}


def test_map_event_ignores_tool_parts_after_typed_hook_migration():
    ev = _event(
        author="research_lead",
        function_calls=[
            ("google_search", {"query": "best burgers berlin"}),
        ],
        function_responses=[
            ("get_restaurant_details", {"status": "success", "place": {"displayName": {"text": "Umami"}}})
        ],
    )
    assert map_event(ev, {})["timeline_events"] == []


def test_compaction_event_emits_no_timeline_rows():
    ev = SimpleNamespace(
        author="research_lead",
        id="evt-compaction",
        content=None,
        actions=SimpleNamespace(
            state_delta=None,
            compaction=SimpleNamespace(history_events_count=42),
        ),
        grounding_metadata=None,
        is_final_response=lambda: False,
    )
    assert map_event(ev, {}) == {
        "timeline_events": [],
        "complete": None,
        "grounding_sources": [],
    }


def test_multi_tool_call_emits_multiple_detail_rows_in_order():
    rows = [
        map_tool_call("google_search", {"query": "best burgers berlin"}, {}, "call-1"),
        map_tool_call("fetch_web_content", {"url": "https://example.com/menu"}, {}, "call-2"),
        map_tool_call("find_tripadvisor_restaurant", {"name": "Goldies", "area": "Berlin"}, {}, "call-3"),
    ]
    assert [row["family"] for row in rows] == [
        "Searching the web",
        "Public sources",
        "TripAdvisor",
    ]
    assert rows[0]["text"] == "best burgers berlin"


def test_google_maps_response_uses_place_name():
    rows = map_tool_result(
        "get_restaurant_details",
        {"status": "success", "place": {"displayName": {"text": "Umami Berlin"}}},
        {},
        "call-1",
    )
    assert rows[0]["text"] == "Profile for Umami Berlin"


def test_tripadvisor_unverified_becomes_warning():
    """Unverified status (coord check failed or no coords available) renders
    as a timeline warning row. On unverified the tool strips `name`, so the
    mapper falls back to 'the venue'."""
    rows = map_tool_result(
        "find_tripadvisor_restaurant",
        {"status": "unverified", "error_message": "coords didn't match"},
        {},
        "call-1",
    )
    assert rows[0]["family"] == "Warnings"
    assert "not verified" in rows[0]["text"].lower()
    assert "the venue" in rows[0]["text"].lower()


def test_google_reviews_uses_saved_place_name():
    state = {"place_names": {}}
    map_event(
        _event(author="context_enricher", state_delta={"_place_name_abc123": "Noma"}),
        state,
    )
    rows = map_tool_result(
        "get_google_reviews",
        {"status": "success", "place_id": "abc123", "total_fetched": 12},
        state,
        "call-1",
    )
    assert rows[0]["text"] == "12 reviews for Noma"


def test_specialist_grounding_sources_are_exposed():
    research = map_event(
        _event(
            author="guest_intelligence",
            is_final=True,
            state_delta={"guest_result": "Guests praise speed and consistency."},
            grounding_chunks=[{"uri": "https://maps.example/review", "title": "Review"}],
        ),
        {},
    )
    assert research["grounding_sources"] == [{"title": "Review", "url": "https://maps.example/review"}]


def test_report_writer_complete_uses_grounding_sources():
    ev = _event(
        author="report_writer",
        is_final=True,
        state_delta={"final_report": "# Report"},
        grounding_chunks=[{"uri": "https://a.example", "title": "A", "domain": "a.example"}],
    )
    mapped = map_event(ev, {})
    assert mapped["complete"] == {
        "reply": "# Report",
        "sources": [{"title": "A", "url": "https://a.example", "domain": "a.example"}],
    }


def test_report_writer_empty_final_report_does_not_complete():
    ev = _event(
        author="report_writer",
        is_final=True,
        state_delta={"final_report": "   "},
    )
    mapped = map_event(ev, {})
    assert mapped["complete"] is None


def test_research_lead_writer_brief_does_not_complete():
    ev = _event(
        author="research_lead",
        is_final=True,
        state_delta={"writer_brief": "Scope, specialists, and source gaps."},
    )
    mapped = map_event(ev, {})
    assert mapped["complete"] is None


def test_followup_complete_reads_final_report_followup_key():
    """The follow-up agent writes to `final_report_followup`, not `final_report`.
    Mapper must pick up the follow-up reply without falling back to
    `final_report` (which still holds the original research report)."""
    ev = _event(
        author="follow_up",
        is_final=True,
        state_delta={
            "final_report_followup": "Short follow-up answer.",
            # `final_report` is untouched — still holds the prior research.
            # Mapper must NOT pick this up for the follow-up event.
            "final_report": "# Original full research report",
        },
    )
    mapped = map_event(ev, {})
    assert mapped["complete"] == {
        "reply": "Short follow-up answer.",
        "sources": [],
    }


def test_extract_sources_from_grounding_dedupes_urls():
    ev = _event(
        grounding_chunks=[
            {"uri": "https://a.example", "title": "A"},
            {"uri": "https://a.example", "title": "A dup"},
            {"uri": "https://b.example"},
        ]
    )
    assert extract_sources_from_grounding(ev) == [
        {"title": "A", "url": "https://a.example"},
        {"title": "https://b.example", "url": "https://b.example"},
    ]
