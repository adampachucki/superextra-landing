"""Tests for _embed_chart_images callback in agent.py."""

import base64
import logging
from types import SimpleNamespace

from google.genai import types

from superextra_agent.agent import _embed_chart_images, MAX_IMAGE_BYTES, _build_fallback_report
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
    picks it up so Phase 2 rate queries can filter load-test sids."""
    token = worker_sid.set("sid-test-123")
    try:
        resp = _make_llm_response([types.Part(text="ok")])
        with caplog.at_level(logging.INFO, logger="superextra_agent.agent"):
            _embed_chart_images(callback_context=None, llm_response=resp)
    finally:
        worker_sid.reset(token)
    record = next(r for r in caplog.records if getattr(r, "event", None) == "synth_outcome")
    assert record.sid == "sid-test-123"


def test_fallback_banner_is_neutral():
    """User-facing banner must not leak the internal error_code."""
    report = _build_fallback_report({"market_result": "x"}, "MALFORMED_FUNCTION_CALL")
    assert "Charts couldn't be generated" in report
    assert "MALFORMED_FUNCTION_CALL" not in report


def test_empty_response_triggers_fallback(caplog):
    """A response with no content falls back to a text-only report from
    specialist state and emits synth_outcome/empty_response.
    See docs/pipeline-decoupling-implementation-review-2026-04-21.md P1."""
    resp = _make_llm_response(None)
    ctx = SimpleNamespace(state={"market_result": "Market text."})
    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        result = _embed_chart_images(callback_context=ctx, llm_response=resp)
    assert "Market Landscape" in result.content.parts[0].text
    assert _outcome_reason(caplog.records) == "empty_response"


def test_no_images_unchanged(caplog):
    """Pure success path emits synth_outcome/ok — the denominator signal."""
    resp = _make_llm_response([types.Part(text="Just text, no images.")])
    with caplog.at_level(logging.INFO, logger="superextra_agent.agent"):
        result = _embed_chart_images(callback_context=None, llm_response=resp)
    assert result.content.parts[0].text == "Just text, no images."
    assert _outcome_reason(caplog.records) == "ok"


def test_valid_image_replacement():
    image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    parts = [
        types.Part(
            inline_data=types.Blob(
                mime_type="image/png",
                data=image_data,
            )
        ),
        types.Part(text="Here is the chart: ![Chart](code_execution_image_1_123.png)"),
    ]
    resp = _make_llm_response(parts)
    result = _embed_chart_images(callback_context=None, llm_response=resp)

    # The text part should now contain a base64 data URI
    text_parts = [p for p in result.content.parts if p.text]
    assert len(text_parts) == 1
    assert "data:image/png;base64," in text_parts[0].text
    # The inline_data part should be removed (replaced via text ref)
    inline_parts = [p for p in result.content.parts if p.inline_data]
    assert len(inline_parts) == 0


def test_bogus_image_index_unchanged():
    image_data = b"\x89PNG" + b"\x00" * 50
    parts = [
        types.Part(
            inline_data=types.Blob(
                mime_type="image/png",
                data=image_data,
            )
        ),
        types.Part(text="![Chart](code_execution_image_999_bogus.png)"),
    ]
    resp = _make_llm_response(parts)
    result = _embed_chart_images(callback_context=None, llm_response=resp)

    # Reference with index 999 should be left unchanged in text
    text_parts = [p for p in result.content.parts if p.text]
    assert any("code_execution_image_999" in p.text for p in text_parts)


def test_oversized_image_skipped(caplog):
    oversized_data = b"\x00" * (MAX_IMAGE_BYTES + 1)
    parts = [
        types.Part(
            inline_data=types.Blob(
                mime_type="image/png",
                data=oversized_data,
            )
        ),
        types.Part(text="![Chart](code_execution_image_1_123.png)"),
    ]
    resp = _make_llm_response(parts)
    with caplog.at_level(logging.WARNING):
        result = _embed_chart_images(callback_context=None, llm_response=resp)

    # No images collected, so the response should be returned unchanged
    # (the function returns early when images list is empty)
    assert result is resp
    assert "oversized" in caplog.text.lower() or "Skipping" in caplog.text


def test_empty_parts_triggers_fallback():
    """An LlmResponse with content but empty parts also falls back.
    Same branch as test_empty_response_triggers_fallback, different shape."""
    resp = _make_llm_response([])
    ctx = SimpleNamespace(state={"pricing_result": "Pricing text."})
    result = _embed_chart_images(callback_context=ctx, llm_response=resp)
    assert "Menu & Pricing" in result.content.parts[0].text


def test_parts_without_text_triggers_fallback(caplog):
    """Parts exist but carry no usable text — emits synth_outcome/no_text_parts."""
    resp = _make_llm_response([types.Part(text="   ")])
    ctx = SimpleNamespace(state={"market_result": "Market text."})
    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        result = _embed_chart_images(callback_context=ctx, llm_response=resp)
    assert "Market Landscape" in result.content.parts[0].text
    assert _outcome_reason(caplog.records) == "no_text_parts"


def test_error_code_triggers_fallback_with_state_outputs(caplog):
    """MALFORMED_FUNCTION_CALL builds a text-only report from specialist state
    and emits synth_outcome/MALFORMED_FUNCTION_CALL."""
    resp = _make_llm_response(None)
    resp.error_code = "MALFORMED_FUNCTION_CALL"
    resp.error_message = "Malformed function call"
    state = {
        "market_result": "Market landscape report text.",
        "pricing_result": "Pricing report text.",
        "guest_result": "Agent did not produce output.",  # filtered out
    }
    ctx = SimpleNamespace(state=state)

    with caplog.at_level(logging.WARNING, logger="superextra_agent.agent"):
        result = _embed_chart_images(callback_context=ctx, llm_response=resp)

    text = result.content.parts[0].text
    assert "Market Landscape" in text and "Market landscape report text." in text
    assert "Menu & Pricing" in text and "Pricing report text." in text
    # Filtered-out default-sentinel outputs must not appear as sections
    assert "Guest Intelligence" not in text
    assert _outcome_reason(caplog.records) == "MALFORMED_FUNCTION_CALL"


def test_error_code_with_empty_state_returns_guidance():
    resp = _make_llm_response(None)
    resp.error_code = "MALFORMED_FUNCTION_CALL"
    ctx = SimpleNamespace(state={})

    result = _embed_chart_images(callback_context=ctx, llm_response=resp)

    text = result.content.parts[0].text
    assert "No specialist outputs" in text or "rephrasing" in text


def test_build_fallback_report_shape():
    state = {
        "market_result": "A",
        "ops_result": "B",
        "dynamic_result_2": "C",
    }
    report = _build_fallback_report(state, "MALFORMED_FUNCTION_CALL")
    # Sections appear in the canonical order, not alphabetical / insertion order
    assert report.index("Market Landscape") < report.index("Operations") < report.index("Gap Research")
