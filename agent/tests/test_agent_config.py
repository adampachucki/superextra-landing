"""Tests for top-level agent configuration."""

from google.adk.tools import google_search

from superextra_agent.agent import (
    continue_research,
    report_writer,
    research_lead,
    research_pipeline,
    _record_continuation_notes,
)
from superextra_agent.specialist_catalog import SPECIALISTS
from superextra_agent.specialists import (
    CONTINUATION_SPECIALISTS,
    MEDIUM_THINKING_CONFIG,
    MODEL_GEMINI,
    _on_model_error,
)
from superextra_agent.web_tools import fetch_web_content


def test_continue_research_uses_tool_compatible_model_config():
    """Continuation keeps focused source-check tools on the compatible model family."""
    assert continue_research.model is MODEL_GEMINI
    assert continue_research.generate_content_config is MEDIUM_THINKING_CONFIG
    assert google_search in continue_research.tools
    assert fetch_web_content in continue_research.tools
    assert any(
        getattr(tool, "name", "") == "market_landscape" for tool in continue_research.tools
    )
    assert any(
        getattr(tool, "name", "") == "dynamic_researcher_1"
        for tool in continue_research.tools
    )
    helper_agents = [
        getattr(tool, "agent", None)
        for tool in continue_research.tools
        if getattr(tool, "name", "") in {agent.name for agent in CONTINUATION_SPECIALISTS}
    ]
    assert helper_agents
    assert all(agent.output_key is None for agent in helper_agents)
    assert continue_research.on_model_error_callback is _on_model_error
    assert continue_research.after_agent_callback is _record_continuation_notes


def test_continuation_specialists_are_all_non_durable():
    expected_names = {specialist.name for specialist in SPECIALISTS}

    assert {agent.name for agent in CONTINUATION_SPECIALISTS} == expected_names
    assert all(agent.output_key is None for agent in CONTINUATION_SPECIALISTS)


def test_research_pipeline_ends_with_report_writer():
    assert [agent.name for agent in research_pipeline.sub_agents] == [
        "context_enricher",
        "research_lead",
        "report_writer",
    ]
    assert research_lead.output_key == "research_coverage"
    assert report_writer.output_key == "final_report"
    assert getattr(report_writer.model, "model", None) == "gemini-3.1-pro-preview"
    assert report_writer.tools == []
