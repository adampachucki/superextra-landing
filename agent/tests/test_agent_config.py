"""Tests for top-level agent configuration."""

from google.adk.tools import google_search

from superextra_agent.agent import follow_up, report_writer, research_lead, research_pipeline
from superextra_agent.specialists import (
    MEDIUM_THINKING_CONFIG,
    MODEL_GEMINI,
    _on_model_error,
)
from superextra_agent.web_tools import fetch_web_content


def test_follow_up_uses_tool_compatible_model_config():
    """Follow-up keeps both web tools on the Gemini model family that supports them."""
    assert follow_up.model is MODEL_GEMINI
    assert follow_up.generate_content_config is MEDIUM_THINKING_CONFIG
    assert google_search in follow_up.tools
    assert fetch_web_content in follow_up.tools
    assert follow_up.on_model_error_callback is _on_model_error


def test_research_pipeline_ends_with_report_writer():
    assert [agent.name for agent in research_pipeline.sub_agents] == [
        "context_enricher",
        "research_lead",
        "report_writer",
    ]
    assert research_lead.output_key == "writer_brief"
    assert report_writer.output_key == "final_report"
    assert getattr(report_writer.model, "model", None) == "gemini-3.1-pro-preview"
    assert report_writer.tools == []
