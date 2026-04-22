"""Tests for _synth_fallback_callback in agent.py.

Phase 2 moved chart generation out of the synth's LLM call — the synth is now
a plain text-generating agent. This callback only runs when the model returns
an error_code, an empty response, or no usable text; it stitches a fallback
report from specialist outputs in state so `final_report` is always populated.
"""

import logging
from types import SimpleNamespace

from google.genai import types

from superextra_agent.agent import _synth_fallback_callback, _build_fallback_report
from superextra_agent.log_ctx import worker_sid


def _make_llm_response(parts):
    """Build a minimal LlmResponse-like object with .content.parts."""

    class FakeLlmResponse:
        def __init__(self, parts):
            self.content = types.Content(role="model", parts=parts) if parts is not None else None

    return FakeLlmResponse(parts)


def _outcome_reason(records) -> str | None:
    """Return the `reason` from the single synth_outcome record, or None."""
    for r in records:
        if getattr(r, "event", None) == "synth_outcome":
            return getattr(r, "reason", None)
    return None


def test_synth_outcome_carries_sid_from_worker_context(caplog):
    """Worker sets worker_sid contextvar at /run entry; the synth callback
    picks it up so rate queries can filter load-test sids."""
    token = worker_sid.set("sid-test-123")
    try:
        resp = _make_llm_response([types.Part(text="ok")])
        with caplog.at_level(logging.INFO, logger="superextra_agent.agent"):
            _synth_fallback_callback(callback_context=None, llm_response=resp)
    finally:
        worker_sid.reset(token)
    record = next(r for r in caplog.records if getattr(r, "event", None) == "synth_outcome")
    assert record.sid == "sid-test-123"


def test_fallback_banner_is_neutral():
    """User-facing banner must not leak the internal error_code."""
    report = _build_fallback_report({"market_result": "x"}, "MALFORMED_FUNCTION_CALL")
    assert "didn't produce a response" in report
    assert "MALFORMED_FUNCTION_CALL" not in report


def test_empty_response_triggers_fallback(caplog):
    """A response with no content falls back to a text-only report from
    specialist state and emits synth_outcome/empty_response."""
    resp = _make_llm_response(None)
    ctx = SimpleNamespace(state={"market_result": "Market text."})
    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        result = _synth_fallback_callback(callback_context=ctx, llm_response=resp)
    assert "Market Landscape" in result.content.parts[0].text
    assert _outcome_reason(caplog.records) == "empty_response"


def test_normal_response_passes_through_unchanged(caplog):
    """Pure success path emits synth_outcome/ok and returns the response
    unchanged. Chart fences (if any) stay in the text."""
    resp = _make_llm_response([
        types.Part(text='Summary.\n\n```chart\n{"type":"bar","data":[]}\n```'),
    ])
    with caplog.at_level(logging.INFO, logger="superextra_agent.agent"):
        result = _synth_fallback_callback(callback_context=None, llm_response=resp)
    assert result is resp
    assert "```chart" in result.content.parts[0].text
    assert _outcome_reason(caplog.records) == "ok"


def test_empty_parts_triggers_fallback():
    """An LlmResponse with content but empty parts also falls back."""
    resp = _make_llm_response([])
    ctx = SimpleNamespace(state={"pricing_result": "Pricing text."})
    result = _synth_fallback_callback(callback_context=ctx, llm_response=resp)
    assert "Menu & Pricing" in result.content.parts[0].text


def test_parts_without_text_triggers_fallback(caplog):
    """Parts exist but carry no usable text — emits synth_outcome/no_text_parts."""
    resp = _make_llm_response([types.Part(text="   ")])
    ctx = SimpleNamespace(state={"market_result": "Market text."})
    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        result = _synth_fallback_callback(callback_context=ctx, llm_response=resp)
    assert "Market Landscape" in result.content.parts[0].text
    assert _outcome_reason(caplog.records) == "no_text_parts"


def test_error_code_triggers_fallback_with_state_outputs(caplog):
    """A model error_code (e.g. legacy MALFORMED_FUNCTION_CALL) builds a
    text-only report from specialist state. Post-Phase-2 this branch is
    rarely reached since the synth no longer uses tools, but the guard
    stays as defense-in-depth for any other terminal model error."""
    resp = _make_llm_response(None)
    resp.error_code = "SAFETY"
    resp.error_message = "content blocked"
    state = {
        "market_result": "Market landscape report text.",
        "pricing_result": "Pricing report text.",
        "guest_result": "Agent did not produce output.",  # filtered out
    }
    ctx = SimpleNamespace(state=state)

    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        result = _synth_fallback_callback(callback_context=ctx, llm_response=resp)

    text = result.content.parts[0].text
    assert "Market Landscape" in text and "Market landscape report text." in text
    assert "Menu & Pricing" in text and "Pricing report text." in text
    assert "Guest Intelligence" not in text
    assert _outcome_reason(caplog.records) == "SAFETY"


def test_error_code_with_empty_state_returns_guidance():
    resp = _make_llm_response(None)
    resp.error_code = "SAFETY"
    ctx = SimpleNamespace(state={})

    result = _synth_fallback_callback(callback_context=ctx, llm_response=resp)

    text = result.content.parts[0].text
    assert "No specialist outputs" in text or "rephrasing" in text


def test_build_fallback_report_shape():
    state = {
        "market_result": "A",
        "ops_result": "B",
        "gap_research_result": "C",
    }
    report = _build_fallback_report(state, "empty_response")
    # Sections appear in the canonical order, not alphabetical / insertion order
    assert report.index("Market Landscape") < report.index("Operations") < report.index("Gap Research")
