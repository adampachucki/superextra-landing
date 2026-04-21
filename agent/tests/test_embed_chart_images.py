"""Tests for _embed_chart_images callback in agent.py."""

import base64
import logging
from types import SimpleNamespace

from google.genai import types

from superextra_agent.agent import _embed_chart_images, MAX_IMAGE_BYTES, _build_fallback_report


def _make_llm_response(parts):
    """Build a minimal LlmResponse-like object with .content.parts."""

    class FakeLlmResponse:
        def __init__(self, parts):
            self.content = types.Content(role="model", parts=parts) if parts is not None else None

    return FakeLlmResponse(parts)


def test_empty_response_triggers_fallback():
    """A response with no content (not just no parts) now falls back to a
    text-only report from specialist state. Previously this path returned the
    empty response unchanged — leading to `empty_or_malformed_reply` in the
    worker. See docs/pipeline-decoupling-implementation-review-2026-04-21.md P1."""
    resp = _make_llm_response(None)
    ctx = SimpleNamespace(state={"market_result": "Market text."})
    result = _embed_chart_images(callback_context=ctx, llm_response=resp)
    text = result.content.parts[0].text
    assert "empty_response" in text
    assert "Market Landscape" in text


def test_no_images_unchanged():
    resp = _make_llm_response([types.Part(text="Just text, no images.")])
    result = _embed_chart_images(callback_context=None, llm_response=resp)
    assert result.content.parts[0].text == "Just text, no images."


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
    """An LlmResponse with content but an empty parts list also now falls
    back to a specialist-state report. Same motivation as
    test_empty_response_triggers_fallback."""
    resp = _make_llm_response([])
    ctx = SimpleNamespace(state={"pricing_result": "Pricing text."})
    result = _embed_chart_images(callback_context=ctx, llm_response=resp)
    text = result.content.parts[0].text
    assert "empty_response" in text
    assert "Menu & Pricing" in text


def test_parts_without_text_triggers_fallback():
    """A response whose parts exist but carry no usable text (all None /
    whitespace) also falls back — mirrors the 'final event with no usable
    text' failure mode that produced empty_or_malformed_reply in live runs."""
    resp = _make_llm_response([types.Part(text="   ")])
    ctx = SimpleNamespace(state={"market_result": "Market text."})
    result = _embed_chart_images(callback_context=ctx, llm_response=resp)
    text = result.content.parts[0].text
    assert "no_text_parts" in text
    assert "Market Landscape" in text


def test_error_code_triggers_fallback_with_state_outputs():
    """When Gemini emits MALFORMED_FUNCTION_CALL (e.g. during code_execution),
    the callback should build a text-only report from specialist outputs in state
    so final_report is always populated."""
    resp = _make_llm_response(None)
    resp.error_code = "MALFORMED_FUNCTION_CALL"
    resp.error_message = "Malformed function call"
    state = {
        "market_result": "Market landscape report text.",
        "pricing_result": "Pricing report text.",
        "guest_result": "Agent did not produce output.",  # filtered out
    }
    ctx = SimpleNamespace(state=state)

    result = _embed_chart_images(callback_context=ctx, llm_response=resp)

    text = result.content.parts[0].text
    assert "MALFORMED_FUNCTION_CALL" in text
    assert "Market Landscape" in text and "Market landscape report text." in text
    assert "Menu & Pricing" in text and "Pricing report text." in text
    # Filtered-out default-sentinel outputs must not appear as sections
    assert "Guest Intelligence" not in text


def test_error_code_with_empty_state_returns_guidance():
    resp = _make_llm_response(None)
    resp.error_code = "MALFORMED_FUNCTION_CALL"
    ctx = SimpleNamespace(state={})

    result = _embed_chart_images(callback_context=ctx, llm_response=resp)

    text = result.content.parts[0].text
    assert "MALFORMED_FUNCTION_CALL" in text
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
