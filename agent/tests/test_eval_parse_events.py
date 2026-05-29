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


def test_parse_run_builds_drawer_from_grounding_and_provider_pills():
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
            _event(state_delta={"_tool_src_google_maps_abc": provider}),
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
        {**provider, "kind": "provider", "domain": "maps.google.com"},
    ]


def test_parse_run_collects_dispatch_tokens_and_outputs():
    parsed = parse_run(
        [
            _event(
                author="research_lead",
                function_calls=[("market_landscape", {})],
            ),
            _event(
                author="market_landscape",
                state_delta={"market_result": "findings"},
            ),
        ]
    )

    assert parsed["specialists_dispatched"] == ["market_landscape"]
    assert parsed["specialist_outputs"] == {"market_result": "findings"}
    assert parsed["tool_call_counts"] == {"market_landscape": 1}
    assert parsed["final_outcome"] == "unknown"
