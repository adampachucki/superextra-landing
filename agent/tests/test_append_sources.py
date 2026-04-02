"""Tests for _append_sources callback in specialists.py."""

from google.adk.models import LlmResponse
from google.genai import types

from superextra_agent.specialists import _append_sources


def _make_response(text="Some analysis.", chunks=None):
    """Helper to build an LlmResponse with optional grounding chunks."""
    content = types.Content(parts=[types.Part(text=text)]) if text is not None else None
    grounding_metadata = None
    if chunks is not None:
        grounding_metadata = types.GroundingMetadata(grounding_chunks=chunks)
    return LlmResponse(content=content, grounding_metadata=grounding_metadata)


def _make_chunk(uri, title=None, domain=None):
    """Helper to build a GroundingChunk with a web source."""
    return types.GroundingChunk(
        web=types.GroundingChunkWeb(uri=uri, title=title, domain=domain)
    )


class TestAppendSources:
    def test_grounding_chunks_appended(self):
        """Response with grounding_chunks gets a ## Sources section appended."""
        chunks = [_make_chunk("https://example.com/article", title="Example Article", domain="example.com")]
        resp = _make_response("Some analysis.", chunks)

        result = _append_sources(callback_context=None, llm_response=resp)

        assert "## Sources" in result.content.parts[0].text
        assert "- [Example Article](https://example.com/article){example.com}" in result.content.parts[0].text

    def test_multiple_urls_deduped(self):
        """Multiple URLs are all included; duplicates by URI are removed."""
        chunks = [
            _make_chunk("https://a.com/1", title="Article A", domain="a.com"),
            _make_chunk("https://b.com/2", title="Article B", domain="b.com"),
            _make_chunk("https://a.com/1", title="Article A Dup", domain="a.com"),
        ]
        resp = _make_response("Analysis text.", chunks)

        result = _append_sources(callback_context=None, llm_response=resp)

        text = result.content.parts[0].text
        assert text.count("https://a.com/1") == 1
        assert "https://b.com/2" in text
        assert "Article A Dup" not in text

    def test_url_without_domain(self):
        """URL without domain omits the {domain} suffix."""
        chunks = [_make_chunk("https://example.com/page", title="Page", domain=None)]
        resp = _make_response("Text.", chunks)

        result = _append_sources(callback_context=None, llm_response=resp)

        text = result.content.parts[0].text
        assert "- [Page](https://example.com/page)" in text
        assert "{" not in text.split("## Sources")[1]

    def test_no_grounding_metadata(self):
        """No grounding_metadata → response unchanged."""
        resp = _make_response("Unchanged text.")

        result = _append_sources(callback_context=None, llm_response=resp)

        assert result.content.parts[0].text == "Unchanged text."

    def test_empty_grounding_chunks(self):
        """Empty grounding_chunks list → response unchanged."""
        resp = _make_response("Unchanged text.", chunks=[])

        result = _append_sources(callback_context=None, llm_response=resp)

        assert result.content.parts[0].text == "Unchanged text."

    def test_no_text_parts(self):
        """Response with no text parts → response unchanged (no crash)."""
        content = types.Content(parts=[types.Part(text=None)])
        grounding_metadata = types.GroundingMetadata(
            grounding_chunks=[_make_chunk("https://example.com", title="Ex", domain="example.com")]
        )
        resp = LlmResponse(content=content, grounding_metadata=grounding_metadata)

        result = _append_sources(callback_context=None, llm_response=resp)

        # Should not crash; no text parts means nothing gets appended
        assert result is resp
