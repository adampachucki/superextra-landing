from types import SimpleNamespace

from evals.parse_events import parse_run


def _event(
    *,
    author="market_landscape",
    function_calls=None,
    function_responses=None,
    state_delta=None,
    grounding_chunks=None,
):
    parts = []
    for name, args in function_calls or []:
        parts.append(
            SimpleNamespace(
                function_call=SimpleNamespace(name=name, args=args),
                function_response=None,
            )
        )
    for name, response in function_responses or []:
        parts.append(
            SimpleNamespace(
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
        content=SimpleNamespace(parts=parts),
        actions=SimpleNamespace(state_delta=state_delta or {}),
        grounding_metadata=grounding_metadata,
        usage_metadata=None,
    )


def test_parse_run_keeps_source_drawer_as_provenance():
    source = {
        "url": "https://example.com/source",
        "title": "Source",
        "domain": "example.com",
    }
    provider = {
        "provider": "google_maps",
        "place_id": "ChIJtarget",
        "url": "https://maps.google.com/?cid=target",
        "title": "Google Maps - Target",
    }

    parsed = parse_run(
        [
            _event(
                grounding_chunks=[
                    {
                        "uri": "https://search.example/snippet",
                        "title": "Snippet source",
                        "domain": "search.example",
                    }
                ],
            ),
            _event(
                function_responses=[
                    (
                        "search_public_web",
                        {
                            "status": "success",
                            "sources": [
                                {
                                    "url": "https://search.example/tool",
                                    "title": "Tool source",
                                    "domain": "search.example",
                                }
                            ],
                        },
                    ),
                    (
                        "read_discovered_sources",
                        {"status": "success", "sources": [source]},
                    )
                ],
                state_delta={"_tool_src_google_maps_abc": provider},
            ),
        ]
    )

    assert parsed["drawer_sources"] == [
        {
            "url": "https://search.example/snippet",
            "domain": "search.example",
            "title": "Snippet source",
            "provider": "grounding",
            "kind": "grounding",
        },
        {
            "url": "https://search.example/tool",
            "domain": "search.example",
            "title": "Tool source",
            "provider": "public_search",
            "kind": "grounding",
        },
        {**provider, "kind": "provider", "domain": "maps.google.com"},
    ]
    assert "evidence_memo" not in parsed


def test_parse_run_builds_specialist_read_funnel_from_read_discovered_sources():
    url = "https://example.com/source"

    parsed = parse_run(
        [
            _event(
                author="market_landscape",
                grounding_chunks=[
                    {"uri": url, "title": "Source", "domain": "example.com"}
                ],
            ),
            _event(
                author="market_landscape",
                function_calls=[("read_discovered_sources", {"urls": [url]})],
                function_responses=[
                    (
                        "read_discovered_sources",
                        {
                            "status": "success",
                            "results": [
                                {
                                    "status": "success",
                                    "url": url,
                                    "content": "# Source\n\nText",
                                }
                            ],
                            "sources": [
                                {
                                    "url": url,
                                    "title": "Source",
                                    "domain": "example.com",
                                }
                            ],
                            "requested_count": 1,
                            "valid_url_count": 1,
                            "available_count": 1,
                            "attempted_count": 1,
                            "success_count": 1,
                            "failed_count": 0,
                        },
                    )
                ],
                state_delta={"market_result": "Market report"},
            ),
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["specialist_output_count"] == 1
    assert funnel["grounding_entry_url_count"] == 1
    assert funnel["captured_source_url_count"] == 1
    assert funnel["specialist_read_tool_call_count"] == 1
    assert funnel["specialist_read_call_count"] == 1
    assert funnel["specialist_read_effective_call_count"] == 1
    assert funnel["specialist_read_noop_call_count"] == 0
    assert funnel["specialist_read_requested_url_count"] == 1
    assert funnel["specialist_read_attempted_url_count"] == 1
    assert funnel["specialist_read_successful_url_count"] == 1
    assert funnel["specialist_read_returned_source_urls"] == [url]
    assert funnel["grounding_urls_attempted_by_specialists_count"] == 1
    assert funnel["captured_urls_not_attempted"] == []
    assert len(funnel["specialists"]) == 1
    assert funnel["specialists"][0]["key"] == "market_landscape"
    assert funnel["specialists"][0]["read_tool_call_count"] == 1
    assert funnel["specialists"][0]["read_call_count"] == 1
    assert funnel["specialists"][0]["noop_read_call_count"] == 0
    assert funnel["specialists"][0]["successful_urls"] == [url]


def test_parse_run_tracks_auto_appended_omitted_and_failed_reads():
    read = "https://example.com/read"
    failed = "https://example.com/blocked"
    omitted = "https://example.com/omitted"

    parsed = parse_run(
        [
            _event(
                author="guest_intelligence",
                grounding_chunks=[
                    {"uri": read, "title": "Read", "domain": "example.com"},
                    {"uri": failed, "title": "Blocked", "domain": "example.com"},
                    {"uri": omitted, "title": "Omitted", "domain": "example.com"},
                ],
            ),
            _event(
                author="guest_intelligence",
                function_calls=[("read_discovered_sources", {"urls": []})],
                function_responses=[
                    (
                        "read_discovered_sources",
                        {
                            "status": "success",
                            "results": [
                                {
                                    "status": "success",
                                    "url": read,
                                    "content": "# Read\n\nText",
                                },
                                {
                                    "status": "error",
                                    "url": failed,
                                    "error_message": "upstream HTTP 403",
                                },
                            ],
                            "sources": [
                                {
                                    "url": read,
                                    "title": "Read",
                                    "domain": "example.com",
                                }
                            ],
                            "requested_count": 0,
                            "attempted_count": 2,
                            "success_count": 1,
                            "failed_count": 1,
                            "auto_appended_urls": [read, failed],
                            "auto_appended_count": 2,
                            "omitted_urls": [omitted],
                            "omitted_count": 1,
                        },
                    )
                ],
            ),
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["specialist_read_auto_appended_url_count"] == 2
    assert funnel["specialist_read_omitted_url_count"] == 1
    assert funnel["specialist_read_failed_sources"] == [
        {
            "url": failed,
            "reason": "upstream HTTP 403",
            "reason_bucket": "http_403",
        }
    ]
    assert funnel["specialist_read_failure_reason_counts"] == {"http_403": 1}
    assert funnel["grounding_urls_not_attempted"] == [omitted]


def test_parse_run_uses_requested_url_for_resolved_reader_attempts():
    requested = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
    resolved = "https://example.com/article"

    parsed = parse_run(
        [
            _event(
                author="market_landscape",
                grounding_chunks=[
                    {
                        "uri": requested,
                        "title": "Article",
                        "domain": "example.com",
                    }
                ],
            ),
            _event(
                author="market_landscape",
                function_calls=[("read_discovered_sources", {"urls": [requested]})],
                function_responses=[
                    (
                        "read_discovered_sources",
                        {
                            "status": "success",
                            "results": [
                                {
                                    "status": "success",
                                    "requested_url": requested,
                                    "url": resolved,
                                    "content": "# Article\n\nText",
                                }
                            ],
                            "sources": [
                                {
                                    "url": resolved,
                                    "title": "Article",
                                    "domain": "example.com",
                                }
                            ],
                            "attempted_count": 1,
                            "success_count": 1,
                        },
                    )
                ],
            ),
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["grounding_urls_attempted_by_specialists_count"] == 1
    assert funnel["specialist_read_successful_urls"] == [resolved]
    assert funnel["specialist_read_returned_source_urls"] == [resolved]
    assert funnel["specialist_read_attempted_urls_not_captured"] == []


def test_parse_run_counts_specialists_without_reads():
    parsed = parse_run(
        [
            _event(
                author="market_landscape",
                grounding_chunks=[
                    {"uri": "https://example.com/a", "title": "A", "domain": "example.com"}
                ],
                state_delta={"market_result": "Market report"},
            )
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["specialist_read_call_count"] == 0
    assert funnel["grounding_urls_not_attempted"] == ["https://example.com/a"]
    row = next(row for row in funnel["specialists"] if row["key"] == "market_landscape")
    assert row["grounding_url_count"] == 1
    assert row["read_call_count"] == 0


def test_parse_run_separates_noop_read_calls_from_effective_read_calls():
    parsed = parse_run(
        [
            _event(
                author="market_landscape",
                function_calls=[("read_discovered_sources", {"urls": []})],
                function_responses=[
                    (
                        "read_discovered_sources",
                        {
                            "status": "success",
                            "requested_count": 0,
                            "valid_url_count": 0,
                            "available_count": 0,
                            "attempted_count": 0,
                            "success_count": 0,
                            "failed_count": 0,
                            "skipped_count": 0,
                            "auto_appended_count": 0,
                            "rejected_count": 0,
                            "invalid_count": 0,
                            "omitted_count": 0,
                        },
                    )
                ],
            )
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["specialist_read_tool_call_count"] == 1
    assert funnel["specialist_read_call_count"] == 0
    assert funnel["specialist_read_effective_call_count"] == 0
    assert funnel["specialist_read_noop_call_count"] == 1
    row = next(row for row in funnel["specialists"] if row["key"] == "market_landscape")
    assert row["read_tool_call_count"] == 1
    assert row["read_call_count"] == 0
    assert row["noop_read_call_count"] == 1


def test_parse_run_does_not_count_skipped_only_read_as_effective():
    url = "https://example.com/already-read"

    parsed = parse_run(
        [
            _event(
                author="market_landscape",
                function_calls=[("read_discovered_sources", {"urls": [url]})],
                function_responses=[
                    (
                        "read_discovered_sources",
                        {
                            "status": "success",
                            "requested_count": 1,
                            "valid_url_count": 0,
                            "available_count": 1,
                            "attempted_count": 0,
                            "success_count": 0,
                            "failed_count": 0,
                            "skipped_count": 1,
                            "auto_appended_count": 0,
                            "rejected_count": 0,
                            "invalid_count": 0,
                            "omitted_count": 0,
                            "skipped_urls": [url],
                        },
                    )
                ],
            )
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["specialist_read_tool_call_count"] == 1
    assert funnel["specialist_read_call_count"] == 0
    assert funnel["specialist_read_effective_call_count"] == 0
    assert funnel["specialist_read_noop_call_count"] == 0
    assert funnel["specialist_read_skipped_url_count"] == 1
    row = next(row for row in funnel["specialists"] if row["key"] == "market_landscape")
    assert row["read_tool_call_count"] == 1
    assert row["read_call_count"] == 0
    assert row["noop_read_call_count"] == 0
    assert row["skipped_url_count"] == 1


def test_parse_run_excludes_non_specialist_grounding_from_read_funnel():
    lead_url = "https://example.com/lead"
    specialist_url = "https://example.com/specialist"

    parsed = parse_run(
        [
            _event(
                author="research_lead",
                grounding_chunks=[
                    {"uri": lead_url, "title": "Lead", "domain": "example.com"}
                ],
            ),
            _event(
                author="market_landscape",
                grounding_chunks=[
                    {
                        "uri": specialist_url,
                        "title": "Specialist",
                        "domain": "example.com",
                    }
                ],
                state_delta={"market_result": "Market report"},
            ),
        ]
    )

    assert [source["url"] for source in parsed["drawer_sources"]] == [
        lead_url,
        specialist_url,
    ]
    funnel = parsed["source_funnel"]
    assert funnel["grounding_entry_url_count"] == 1
    assert funnel["captured_source_url_count"] == 1
    assert funnel["grounding_urls_not_attempted"] == [specialist_url]
    assert lead_url not in funnel["grounding_urls_not_attempted"]
