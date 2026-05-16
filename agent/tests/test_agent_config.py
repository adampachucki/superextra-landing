"""Tests for top-level agent configuration."""

from google.adk.tools import google_search

from superextra_agent.agent import (
    app,
    continue_research,
    evidence_adjudicator,
    report_writer,
    research_lead,
    research_pipeline,
    _record_continuation_notes,
    _record_evidence_adjudicator_fallback,
)
from superextra_agent.chat_logger import ChatLoggerPlugin
from superextra_agent.firestore_progress import FirestoreProgressPlugin
from superextra_agent.specialist_catalog import SPECIALISTS
from superextra_agent.specialists import (
    CONTINUATION_SPECIALISTS,
    MEDIUM_THINKING_CONFIG,
    MODEL_GEMINI,
    _on_model_error,
)
from superextra_agent.web_tools import (
    fetch_web_content,
    read_adjudicator_sources,
    read_web_pages,
)


def _tool_names(tools):
    return [getattr(tool, "name", getattr(tool, "__name__", "")) for tool in tools]


def test_continue_research_uses_tool_compatible_model_config():
    """Continuation keeps focused helpers and observable direct tools."""
    assert continue_research.model is MODEL_GEMINI
    assert continue_research.generate_content_config is MEDIUM_THINKING_CONFIG
    assert google_search not in continue_research.tools
    assert read_web_pages in continue_research.tools
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


def test_research_pipeline_validates_evidence_before_report_writer():
    assert [agent.name for agent in research_pipeline.sub_agents] == [
        "context_enricher",
        "research_lead",
        "evidence_adjudicator",
        "report_writer",
    ]
    assert research_lead.output_key == "research_coverage"
    assert google_search in research_lead.tools
    assert "url_context" not in _tool_names(research_lead.tools)
    assert "read_web_pages" not in _tool_names(research_lead.tools)
    assert "fetch_web_content" not in _tool_names(research_lead.tools)
    assert "fetch_web_content_batch" not in _tool_names(research_lead.tools)
    assert "search_and_read_public_pages" not in _tool_names(research_lead.tools)
    assert evidence_adjudicator.output_key == "evidence_memo"
    assert evidence_adjudicator.tools == [read_adjudicator_sources]
    assert evidence_adjudicator.after_agent_callback is _record_evidence_adjudicator_fallback
    assert "google_search" not in _tool_names(evidence_adjudicator.tools)
    assert "url_context" not in _tool_names(evidence_adjudicator.tools)
    assert "read_web_pages" not in _tool_names(evidence_adjudicator.tools)
    assert "fetch_web_content" not in _tool_names(evidence_adjudicator.tools)
    assert "fetch_web_content_batch" not in _tool_names(evidence_adjudicator.tools)
    assert "search_and_read_public_pages" not in _tool_names(evidence_adjudicator.tools)
    assert report_writer.output_key == "final_report"
    assert getattr(report_writer.model, "model", None) == "gemini-3.1-pro-preview"
    assert report_writer.tools == []


def test_app_plugins_keep_firestore_progress_last():
    plugin_types = [type(plugin) for plugin in app.plugins]

    assert plugin_types == [
        ChatLoggerPlugin,
        FirestoreProgressPlugin,
    ]
