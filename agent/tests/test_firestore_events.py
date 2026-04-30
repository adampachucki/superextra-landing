from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from superextra_agent.firestore_events import extract_sources_from_grounding, map_event


def _event(
    *,
    author: str | None = None,
    texts: list[str] | None = None,
    function_calls: list[tuple[str, dict[str, Any]]] | None = None,
    function_responses: list[tuple[str, dict[str, Any]]] | None = None,
    state_delta: dict[str, Any] | None = None,
    grounding_chunks: list[dict[str, Any]] | None = None,
    is_final: bool = False,
    event_id: str = "evt-1",
) -> SimpleNamespace:
    parts: list[SimpleNamespace] = []
    for text in texts or []:
        parts.append(SimpleNamespace(text=text, function_call=None, function_response=None))
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
    if grounding_chunks is not None:
        grounding_metadata = SimpleNamespace(
            grounding_chunks=[
                SimpleNamespace(
                    web=SimpleNamespace(
                        uri=chunk.get("uri"),
                        title=chunk.get("title"),
                        domain=chunk.get("domain"),
                    )
                )
                for chunk in grounding_chunks
            ]
        )

    return SimpleNamespace(
        author=author,
        id=event_id,
        content=SimpleNamespace(parts=parts),
        actions=SimpleNamespace(state_delta=state_delta or None),
        grounding_metadata=grounding_metadata,
        is_final_response=lambda: is_final,
    )


def test_router_transfer_is_ignored():
    ev = _event(author="router", function_calls=[("transfer_to_agent", {"agent_name": "research"})])
    mapped = map_event(ev, {})
    assert mapped["complete"] is None
    assert mapped["timeline_events"] == []


def test_router_text_reply_becomes_complete():
    ev = _event(author="router", texts=["Need clarification"], is_final=True)
    mapped = map_event(ev, {})
    assert mapped["complete"] == {"reply": "Need clarification", "sources": []}


def test_narrate_function_call_emits_note_before_specialist_details():
    """research_lead's `narrate(text)` arrives as a function-call sibling of
    real specialist tool calls in the same Event. `map_event` should turn it
    into a note timeline row with id derived from the part index, so the
    note's seqInAttempt is strictly less than any specialist tool-response
    that follows from the same model turn."""
    ev = _event(
        author="research_lead",
        function_calls=[
            ("narrate", {"text": "Pulling Google reviews for Maple & Ash and Bavette's now."}),
            ("review_analyst", {"request": "..."}),
            ("guest_intelligence", {"request": "..."}),
        ],
        event_id="evt-narrate",
    )
    rows = map_event(ev, {})["timeline_events"]
    assert rows[0] == {
        "kind": "note",
        "id": "narrate:evt-narrate:0",
        "text": "Pulling Google reviews for Maple & Ash and Bavette's now.",
    }
    # Specialist function-calls don't produce detail rows on their own (they
    # produce them via responses), so we only assert the note itself here.


def test_narrate_with_empty_text_is_dropped():
    ev = _event(
        author="research_lead",
        function_calls=[("narrate", {"text": "   "})],
        event_id="evt-empty",
    )
    rows = map_event(ev, {})["timeline_events"]
    assert rows == []


def test_narrate_with_non_string_text_is_dropped():
    ev = _event(
        author="research_lead",
        function_calls=[("narrate", {"text": 123})],
        event_id="evt-nonstr",
    )
    rows = map_event(ev, {})["timeline_events"]
    assert rows == []


def test_multi_call_event_emits_multiple_detail_rows_in_order():
    ev = _event(
        author="review_analyst",
        function_calls=[
            ("google_search", {"query": "best burgers berlin"}),
            ("fetch_web_content", {"url": "https://example.com/menu"}),
            ("find_tripadvisor_restaurant", {"name": "Goldies", "area": "Berlin"}),
        ],
        event_id="evt-multi",
    )
    mapped = map_event(ev, {})
    rows = mapped["timeline_events"]
    assert [row["family"] for row in rows] == [
        "Searching the web",
        "Public sources",
        "TripAdvisor",
    ]
    assert rows[0]["text"] == "best burgers berlin"


def test_google_maps_response_uses_place_name():
    ev = _event(
        author="context_enricher",
        function_responses=[
            (
                "get_restaurant_details",
                {
                    "status": "success",
                    "place": {"displayName": {"text": "Umami Berlin"}},
                },
            )
        ],
    )
    mapped = map_event(ev, {})
    assert mapped["timeline_events"][0]["text"] == "Profile for Umami Berlin"


def test_tripadvisor_unverified_becomes_warning():
    """Unverified status (coord check failed or no coords available) renders
    as a timeline warning row. On unverified the tool strips `name`, so the
    mapper falls back to 'the venue'."""
    ev = _event(
        author="review_analyst",
        function_responses=[
            (
                "find_tripadvisor_restaurant",
                {"status": "unverified", "error_message": "coords didn't match"},
            )
        ],
    )
    mapped = map_event(ev, {})
    assert mapped["timeline_events"][0]["family"] == "Warnings"
    assert "not verified" in mapped["timeline_events"][0]["text"].lower()
    assert "the venue" in mapped["timeline_events"][0]["text"].lower()


def test_google_reviews_uses_saved_place_name():
    state = {"place_names": {}}
    map_event(
        _event(author="context_enricher", state_delta={"_place_name_abc123": "Noma"}),
        state,
    )
    ev = _event(
        author="review_analyst",
        function_responses=[
            ("get_google_reviews", {"status": "success", "place_id": "abc123", "total_fetched": 12})
        ],
    )
    mapped = map_event(ev, state)
    assert mapped["timeline_events"][0]["text"] == "12 reviews for Noma"


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


def test_research_lead_complete_uses_grounding_sources():
    ev = _event(
        author="research_lead",
        is_final=True,
        state_delta={"final_report": "# Report"},
        grounding_chunks=[{"uri": "https://a.example", "title": "A", "domain": "a.example"}],
    )
    mapped = map_event(ev, {})
    assert mapped["complete"] == {
        "reply": "# Report",
        "sources": [{"title": "A", "url": "https://a.example", "domain": "a.example"}],
    }


def test_research_lead_empty_final_report_does_not_complete():
    ev = _event(
        author="research_lead",
        is_final=True,
        state_delta={"final_report": "   "},
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
