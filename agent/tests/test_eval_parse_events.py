from types import SimpleNamespace

from evals.parse_events import parse_run


def _event(
    *,
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
        author="evidence_adjudicator",
        content=SimpleNamespace(parts=parts),
        actions=SimpleNamespace(state_delta=state_delta or {}),
        grounding_metadata=grounding_metadata,
        usage_metadata=None,
    )


def test_parse_run_captures_evidence_memo_and_verified_sources():
    source = {
        "url": "https://example.com/source",
        "title": "Source",
        "domain": "example.com",
        "provider": "fetched_page",
    }

    parsed = parse_run([
        _event(
            function_calls=[
                ("read_adjudicator_sources", {"urls": ["https://example.com/source"]})
            ],
            function_responses=[
                (
                    "read_adjudicator_sources",
                    {"status": "success", "sources": [source]},
                )
            ],
            state_delta={
                "evidence_memo": (
                    '{"confirmed_claims":[{"evidence":[{"url":"https://example.com/source",'
                    '"title":"Source","domain":"example.com","provider":"fetched_page"}]}]}'
                )
            },
            grounding_chunks=[
                {
                    "uri": "https://search.example/snippet",
                    "title": "Snippet source",
                    "domain": "search.example",
                }
            ],
        )
    ])

    assert "confirmed_claims" in parsed["evidence_memo"]
    assert parsed["fetched_urls"] == ["https://example.com/source"]
    assert parsed["grounding_entries"][0]["url"] == "https://search.example/snippet"
    assert parsed["drawer_sources"] == [{**source, "kind": "fetched"}]


def test_parse_run_excludes_unadjudicated_read_sources_from_drawer():
    source = {
        "url": "https://example.com/read-only",
        "title": "Read only",
        "domain": "example.com",
        "provider": "fetched_page",
    }

    parsed = parse_run([
        _event(
            function_responses=[
                (
                    "read_adjudicator_sources",
                    {"status": "success", "sources": [source]},
                )
            ],
            state_delta={"evidence_memo": '{"confirmed_claims":[]}'},
        )
    ])

    assert parsed["drawer_sources"] == []
    assert parsed["source_funnel"]["reader_returned_source_urls"] == [
        "https://example.com/read-only"
    ]


def test_parse_run_excludes_memo_sources_not_returned_by_reader():
    parsed = parse_run(
        [
            _event(
                function_responses=[
                    (
                        "read_adjudicator_sources",
                        {
                            "status": "success",
                            "sources": [{"url": "https://EXAMPLE.com/read/"}],
                        },
                    )
                ],
                state_delta={
                    "evidence_memo": (
                        '{"confirmed_claims":[{"evidence":['
                        '{"url":"https://example.com/read","title":"Read"},'
                        '{"url":"https://example.com/unread","title":"Unread"}'
                        "]}]}"
                    )
                },
            )
        ]
    )

    assert [source["url"] for source in parsed["drawer_sources"]] == [
        "https://example.com/read"
    ]


def test_parse_run_skips_adjudicated_provider_sources_without_url():
    parsed = parse_run(
        [
            _event(
                state_delta={
                    "evidence_memo": (
                        '{"confirmed_claims":[{"evidence":[{"title":"Google Reviews",'
                        '"provider_refs":["Google Reviews place_id:abc"]}]}],'
                        '"verified_sources":[{"title":"Provider",'
                        '"supports_claim_ids":["claim-1"]}]}'
                    )
                }
            )
        ]
    )

    assert parsed["drawer_sources"] == []


def test_parse_run_filters_vertex_redirect_drawer_sources_like_runtime():
    parsed = parse_run(
        [
            _event(
                state_delta={
                    "evidence_memo": (
                        '{"confirmed_claims":[{"evidence":[{"url":'
                        '"https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc",'
                        '"title":"Redirect"}]}]}'
                    )
                },
            )
        ]
    )

    assert parsed["drawer_sources"] == []


def test_parse_run_keeps_place_scoped_provider_sources_with_same_url():
    url = "https://maps.google.com/?cid=1"
    parsed = parse_run(
        [
            _event(
                state_delta={
                    "_tool_src_google_maps_a": {
                        "url": url,
                        "title": "Place A",
                        "provider": "google_maps",
                        "place_id": "place-a",
                    },
                    "_tool_src_google_maps_b": {
                        "url": url,
                        "title": "Place B",
                        "provider": "google_maps",
                        "place_id": "place-b",
                    },
                },
            )
        ]
    )

    assert [source["title"] for source in parsed["drawer_sources"]] == [
        "Place A",
        "Place B",
    ]


def test_parse_run_builds_source_funnel_from_dynamic_packets():
    report = """Specialist report.

### **Validation Packet**

```json
{
  "claims_for_validation": [
    {
      "id": "claim-1",
      "claim": "Claim",
      "source_urls": ["https://example.com/source#section", "https://example.com/other"],
      "provider_refs": ["Google Reviews place_id:abc"]
    }
  ],
  "candidate_sources": [
    {
      "url": "https://example.com/source",
      "title": "Source",
      "priority": "high"
    }
  ]
}
```
"""
    memo = """```json
{
  "confirmed_claims": [
    {
      "id": "claim-1",
      "evidence": [
        {"url": "https://example.com/source", "title": "Source"}
      ]
    }
  ],
  "verified_sources": [
    {
      "url": "https://example.com/source",
      "supports_claim_ids": ["claim-1"]
    }
  ]
}
```"""

    parsed = parse_run(
        [
            _event(state_delta={"dynamic_result_1": report}),
            _event(
                function_calls=[
                    (
                        "read_adjudicator_sources",
                        {"urls": ["https://example.com/source#section"]},
                    )
                ],
                function_responses=[
                    (
                        "read_adjudicator_sources",
                        {
                            "status": "success",
                            "results": [
                                {"status": "success", "url": "https://example.com/source"}
                            ],
                            "sources": [{"url": "https://example.com/source"}],
                            "attempted_count": 1,
                            "success_count": 1,
                            "failed_count": 0,
                        },
                    )
                ],
                state_delta={"evidence_memo": memo},
            ),
        ]
    )

    assert "dynamic_result_1" in parsed["specialist_outputs"]
    assert parsed["source_funnel"] == {
        "specialist_output_count": 1,
        "validation_packet_count": 1,
        "claim_count": 1,
        "packet_candidate_url_count": 1,
        "packet_claim_source_url_count": 2,
        "packet_url_count": 2,
        "packet_provider_ref_count": 1,
        "reader_requested_url_count": 1,
        "packet_urls_passed_to_reader_count": 1,
        "reader_urls_not_in_packets": [],
        "packet_urls_not_passed": ["https://example.com/other"],
        "packet_urls_attempted_by_reader_count": 1,
        "reader_attempted_urls_not_in_packets": [],
        "packet_urls_not_attempted": ["https://example.com/other"],
        "grounding_entry_url_count": 0,
        "reader_attempted_url_count": 1,
        "reader_attempted_unique_url_count": 1,
        "reader_successful_url_count": 1,
        "reader_failed_url_count": 0,
        "reader_skipped_url_count": 0,
        "reader_rejected_url_count": 0,
        "reader_invalid_url_count": 0,
        "reader_returned_source_url_count": 1,
        "verified_supporting_url_count": 1,
        "read_verified_supporting_url_count": 1,
        "reader_successful_urls": ["https://example.com/source"],
        "reader_failed_sources": [],
        "reader_failure_reason_counts": {},
        "reader_returned_source_urls": ["https://example.com/source"],
        "verified_supporting_urls": ["https://example.com/source"],
        "read_verified_supporting_urls": ["https://example.com/source"],
        "specialists": [
            {
                "key": "dynamic_result_1",
                "label": "Dynamic Research 1",
                "validation_packet_count": 1,
                "claim_count": 1,
                "candidate_url_count": 1,
                "claim_source_url_count": 2,
                "url_count": 2,
                "provider_ref_count": 1,
            }
        ],
    }


def test_parse_run_keeps_read_success_separate_from_verified_support():
    report = """Specialist report.

### Validation Packet

```json
{
  "claims_for_validation": [
    {
      "id": "claim-1",
      "claim": "Claim",
      "source_urls": ["https://example.com/source"]
    }
  ],
  "candidate_sources": [
    {
      "url": "https://example.com/source",
      "title": "Source",
      "priority": "high"
    }
  ]
}
```
"""
    memo = """```json
{
  "confirmed_claims": [],
  "unsupported_claims": [
    {
      "id": "claim-1",
      "claim": "Claim",
      "reason": "The source was read but did not support the claim."
    }
  ],
  "verified_sources": []
}
```"""

    parsed = parse_run(
        [
            _event(state_delta={"dynamic_result_1": report}),
            _event(
                function_calls=[
                    ("read_adjudicator_sources", {"urls": ["https://example.com/source"]})
                ],
                function_responses=[
                    (
                        "read_adjudicator_sources",
                        {
                            "status": "success",
                            "results": [
                                {"status": "success", "url": "https://example.com/source"}
                            ],
                            "sources": [{"url": "https://example.com/source"}],
                            "attempted_count": 1,
                            "success_count": 1,
                            "failed_count": 0,
                        },
                    )
                ],
                state_delta={"evidence_memo": memo},
            ),
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["reader_successful_url_count"] == 1
    assert funnel["reader_returned_source_url_count"] == 1
    assert funnel["verified_supporting_url_count"] == 0
    assert funnel["read_verified_supporting_url_count"] == 0
    assert funnel["reader_returned_source_urls"] == ["https://example.com/source"]
    assert funnel["verified_supporting_urls"] == []


def test_parse_run_reports_reader_failure_reasons():
    parsed = parse_run(
        [
            _event(
                function_responses=[
                    (
                        "read_adjudicator_sources",
                        {
                            "status": "success",
                            "results": [
                                {
                                    "status": "error",
                                    "url": "https://example.com/slow",
                                    "error_message": "Timeout fetching https://example.com/slow",
                                },
                                {
                                    "status": "error",
                                    "url": "https://example.com/root",
                                    "error_message": (
                                        "https://example.com/root is a domain root, "
                                        "not an article"
                                    ),
                                },
                                {
                                    "status": "error",
                                    "url": "https://example.com/adblock",
                                    "error_message": (
                                        "Could not read https://example.com/adblock: "
                                        "page is blocked by an adblock wall"
                                    ),
                                },
                                {
                                    "status": "error",
                                    "url": "https://example.com/billing",
                                    "error_message": (
                                        "Jina Reader account balance is insufficient; "
                                        "recharge JINA_API_KEY before running source reads"
                                    ),
                                },
                            ],
                            "attempted_count": 4,
                            "success_count": 0,
                            "failed_count": 4,
                        },
                    )
                ],
            )
        ]
    )

    funnel = parsed["source_funnel"]
    assert funnel["reader_failed_sources"] == [
        {
            "url": "https://example.com/slow",
            "reason": "Timeout fetching https://example.com/slow",
            "reason_bucket": "timeout",
        },
        {
            "url": "https://example.com/root",
            "reason": "https://example.com/root is a domain root, not an article",
            "reason_bucket": "domain_root",
        },
        {
            "url": "https://example.com/adblock",
            "reason": (
                "Could not read https://example.com/adblock: "
                "page is blocked by an adblock wall"
            ),
            "reason_bucket": "adblock",
        },
        {
            "url": "https://example.com/billing",
            "reason": (
                "Jina Reader account balance is insufficient; recharge "
                "JINA_API_KEY before running source reads"
            ),
            "reason_bucket": "jina_billing",
        },
    ]
    assert funnel["reader_failure_reason_counts"] == {
        "adblock": 1,
        "domain_root": 1,
        "jina_billing": 1,
        "timeout": 1,
    }
