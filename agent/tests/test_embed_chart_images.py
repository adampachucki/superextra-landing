"""Tests for _embed_chart_images callback in agent.py."""

import base64
import logging

from google.genai import types

from superextra_agent.agent import _embed_chart_images, MAX_IMAGE_BYTES


def _make_llm_response(parts):
    """Build a minimal LlmResponse-like object with .content.parts."""

    class FakeLlmResponse:
        def __init__(self, parts):
            self.content = types.Content(role="model", parts=parts) if parts is not None else None

    return FakeLlmResponse(parts)


def test_empty_response_unchanged():
    resp = _make_llm_response(None)
    result = _embed_chart_images(callback_context=None, llm_response=resp)
    assert result.content is None


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


def test_empty_parts_unchanged():
    resp = _make_llm_response([])
    result = _embed_chart_images(callback_context=None, llm_response=resp)
    assert result is resp
