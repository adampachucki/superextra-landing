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


def test_plan_and_research_milestones_are_exposed():
    plan = map_event(
        _event(
            author="research_orchestrator",
            is_final=True,
            state_delta={"research_plan": "Check menus, reviews, delivery coverage."},
        ),
        {},
    )
    assert plan["milestones"]["plan_ready_text"] == "Check menus, reviews, delivery coverage."

    research = map_event(
        _event(
            author="guest_intelligence",
            is_final=True,
            state_delta={"guest_result": "Guests praise speed and consistency."},
            grounding_chunks=[{"uri": "https://maps.example/review", "title": "Review"}],
        ),
        {},
    )
    assert research["milestones"]["research_result_text"] == "Guests praise speed and consistency."
    assert research["grounding_sources"] == [{"title": "Review", "url": "https://maps.example/review"}]


def test_research_started_fires_on_specialist_detail_rows():
    ev = _event(
        author="review_analyst",
        function_calls=[("google_search", {"query": "tripadvisor goldies berlin"})],
    )
    mapped = map_event(ev, {})
    assert mapped["milestones"]["research_started"] is True


def test_drafting_state_delta_emits_drafting_event():
    ev = _event(author="synthesizer", state_delta={"_drafting_started": True}, event_id="evt-draft")
    mapped = map_event(ev, {})
    assert mapped["milestones"]["drafting_started"] is True
    assert mapped["timeline_events"][-1]["kind"] == "drafting"


def test_synth_complete_uses_grounding_sources():
    ev = _event(
        author="synthesizer",
        is_final=True,
        state_delta={"final_report": "# Report"},
        grounding_chunks=[{"uri": "https://a.example", "title": "A", "domain": "a.example"}],
    )
    mapped = map_event(ev, {})
    assert mapped["complete"] == {
        "reply": "# Report",
        "sources": [{"title": "A", "url": "https://a.example", "domain": "a.example"}],
    }


def test_followup_complete_reads_final_report_followup_key():
    """The follow-up agent writes to `final_report_followup`, not `final_report`.
    Mapper must pick up the follow-up reply without falling back to
    `final_report` (which still holds the original synthesizer report)."""
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
