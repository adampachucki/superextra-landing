"""Tests for specialist error callbacks in specialists.py."""

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from superextra_agent.specialists import _on_model_error, _on_tool_error


class TestOnModelError:
    def test_returns_llm_response_with_error_type(self):
        """Should return a valid LlmResponse with the exception type name."""
        result = _on_model_error(None, None, ValueError("test error"))
        assert isinstance(result, LlmResponse)
        assert result.content is not None
        assert len(result.content.parts) == 1
        assert "ValueError" in result.content.parts[0].text

    def test_returns_llm_response_for_timeout(self):
        """Should handle timeout errors gracefully."""
        result = _on_model_error(None, None, TimeoutError("deadline exceeded"))
        assert isinstance(result, LlmResponse)
        assert "TimeoutError" in result.content.parts[0].text


class TestOnToolError:
    def test_returns_dict_with_error_info(self):
        """Should return a dict with error information."""

        class FakeTool:
            name = "google_search"

        result = _on_tool_error(FakeTool(), {}, None, RuntimeError("search failed"))
        assert isinstance(result, dict)
        assert "error" in result
        assert "google_search" in result["error"]
        assert "RuntimeError" in result["error"]
