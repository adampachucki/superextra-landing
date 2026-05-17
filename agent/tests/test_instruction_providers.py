"""Tests for instruction provider functions in agent.py."""

from google.genai import types

from superextra_agent.agent import (
    _CONTINUATION_NOTES_KEY,
    _continue_research_instruction,
    _format_specialist_reports,
    _record_continuation_notes,
    _report_writer_instruction,
    _research_lead_instruction,
    _router_instruction,
)
from superextra_agent.specialists import _make_instruction


class MockCtx:
    def __init__(self, state=None):
        self.state = state or {}


class MockCallbackCtx:
    def __init__(self, state=None, user_text=""):
        self.state = state or {}
        self.user_content = types.Content(
            role="user",
            parts=[types.Part(text=user_text)],
        )


class TestResearchLeadInstruction:
    def test_injects_places_context(self):
        result = _research_lead_instruction(
            MockCtx(state={"places_context": "Restaurant XYZ data here"})
        )

        assert "Restaurant XYZ data here" in result
        assert "## Market Source Profiles" in result

    def test_appends_existing_results_on_follow_up(self):
        result = _research_lead_instruction(
            MockCtx(
                state={
                    "places_context": "Restaurant data",
                    "market_result": "Market findings here",
                    "pricing_result": "Pricing findings here",
                }
            )
        )

        assert "Existing research from prior turn" in result
        assert "Market Landscape" in result
        assert "Menu & Pricing" in result
        assert "Prior research plan" not in result

    def test_sufficiency_check_requires_read_or_qualified_evidence(self):
        result = _research_lead_instruction(
            MockCtx(state={"places_context": "Restaurant data"})
        )

        assert "Did specialists read material public pages" in result
        assert "read page content, structured provider data, or clearly labeled search/grounding-only signals" in result
        assert "If no dynamic researcher has been used, run one" in result


class TestReportWriterInstruction:
    def test_injects_places_context_and_specialist_reports_only(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "places_context": "Restaurant XYZ data",
                    "writer_brief": "Focus on demand and pricing links.",
                    "research_coverage": "Lead thinks demand is most important.",
                    "evidence_memo": "Old memo should not be injected.",
                    "market_result": "Market demand is weekday-heavy.",
                    "pricing_result": "Average entree price is 21 USD.",
                }
            )
        )

        assert "Restaurant XYZ data" in result
        assert "Focus on demand and pricing links." not in result
        assert "Lead thinks demand is most important." not in result
        assert "Old memo should not be injected." not in result
        assert "Market demand is weekday-heavy." in result
        assert "Average entree price is 21 USD." in result
        assert "### Market Landscape" in result
        assert "### Menu & Pricing" in result
        assert "Treat the specialist reports as the research material" in result
        assert "Do not cite unread pages as evidence" in result

    def test_defaults_when_state_empty(self):
        result = _report_writer_instruction(MockCtx(state={}))

        assert "No restaurant data available." in result
        assert "No specialist reports available." in result
        assert "No adjudicated evidence memo available." not in result

    def test_handles_curly_braces_in_injected_material(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "places_context": "Context with {braces}",
                    "market_result": "Source note: `{city: 'Warsaw'}`",
                }
            )
        )

        assert "{braces}" in result
        assert "{city: 'Warsaw'}" in result

    def test_chart_json_braces_are_escaped_for_format(self):
        result = _report_writer_instruction(MockCtx(state={"market_result": "Report"}))

        assert '```chart\n{"type":"bar"' in result

    def test_retention_contract_preserves_all_findings(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "market_result": "Zolza closed. Matcha Ma opened.",
                    "dynamic_result_1": "Nam-Viet remains operational nearby.",
                    "dynamic_result_2": "Filmor has a visible launch signal.",
                    "dynamic_result_3": "Brassica has weak closure evidence.",
                }
            )
        )

        assert "The customer expects deep research, not a compressed summary" in result
        assert "Err on the side of a long, detailed report" in result
        assert "especially its `Writer Material` section, as must-carry research material" in result
        assert "Search or grounding-only signals are weaker context" in result
        assert "Do not reproduce internal evidence-note scaffolding" in result
        assert "Do not collapse several concrete findings" in result
        assert "2-4 suggested follow-up research prompts" in result
        assert "Zolza closed" in result
        assert "Nam-Viet remains operational nearby" in result
        assert "Filmor has a visible launch signal" in result
        assert "Brassica has weak closure evidence" in result

    def test_strips_legacy_validation_packets_from_writer_input(self):
        result = _report_writer_instruction(
            MockCtx(
                state={
                    "market_result": (
                        "Market finding.\n\n"
                        "## Writer Material\n\n"
                        "- Preserve this caveat.\n\n"
                        "### Validation Packet:\n\n"
                        "```json\n"
                        '{"claims_for_validation":[],"candidate_sources":[]}\n'
                        "```"
                    )
                }
            )
        )

        assert "Market finding" in result
        assert "Preserve this caveat" in result
        assert "claims_for_validation" not in result
        assert "candidate_sources" not in result

    def test_specialist_formatter_always_strips_legacy_packets(self):
        result = _format_specialist_reports(
            {
                "market_result": (
                    "Market finding.\n\n"
                    "### **Validation Packet:**\n\n"
                    "```json\n"
                    '{"claims_for_validation":[]}\n'
                    "```"
                )
            }
        )

        assert "Market finding" in result
        assert "claims_for_validation" not in result


class TestMakeInstruction:
    def test_returns_provider_that_injects_places_context(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Competitor data for area"}))

        assert "Competitor data for area" in result
        assert "## Market Source Profiles" not in result

    def test_review_analyst_disclaims_web_fetch_tools(self):
        provider = _make_instruction("review_analyst")

        result = provider(
            MockCtx(
                state={
                    "places_context": "Target data",
                    "places_by_id": {
                        "ChIJtarget": {
                            "google_place_id": "ChIJtarget",
                            "name": "Target",
                        }
                    },
                }
            )
        )

        assert "You do not have `google_search` or page-fetch tools" in result
        assert "ChIJtarget" in result
        assert "For each requested place" in result
        assert "In `Evidence Notes`, cite provider data" in result
        assert "Do not invent URLs" in result

    def test_specialists_have_source_reading_workflow(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "## Search And Source Reading" in result
        assert "Search snippets and search-result source pills are not the same as reading a page" in result
        assert "Use `search_public_web` for public web source discovery" in result
        assert "Use `read_discovered_sources` after `search_public_web`" in result
        assert "Completion gate: if your report uses public web/search evidence" in result
        assert "pass `[]` when the sources came from your latest search" in result
        assert "Treat URLs supplied in the brief as source metadata" in result
        assert "Treat page reads as evidence" in result
        assert "Do not say \"Sources read\"" in result
        assert "call `read_discovered_sources([])` during your research" in result
        assert "Search and grounding sources may still appear as source pills" in result
        assert "proof that a page was read" in result
        assert "### Evidence Notes" in result
        assert "Validation Packet" not in result
        assert "claims_for_validation" not in result

    def test_specialists_surface_writer_material_and_evidence_notes(self):
        provider = _make_instruction("market_landscape")

        result = provider(MockCtx(state={"places_context": "Target data"}))

        assert "Surface all useful material you find" in result
        assert "meaningful evidence limits" in result
        assert "`Writer Material` section" in result
        assert "Include an `Evidence Notes` section" in result
        assert "implications for the target venue" in result


class TestContinueResearchInstruction:
    def test_injects_prior_report(self):
        result = _continue_research_instruction(
            MockCtx(
                state={
                    "final_report": "## Market Report\nKey findings here.",
                    "places_context": "Restaurant XYZ data",
                    "places_by_id": {
                        "ChIJcomp": {
                            "google_place_id": "ChIJcomp",
                            "name": "Competitor A",
                            "lat": 1.0,
                            "lng": 2.0,
                        }
                    },
                    "market_result": "Market specialist notes",
                    "research_coverage": "Coverage notes and source gaps",
                    "continuation_notes": "Turn 2 found competitor A started brunch.",
                }
            )
        )

        assert "## Market Report" in result
        assert "Restaurant XYZ data" in result
        assert "Market specialist notes" in result
        assert "Coverage notes and source gaps" in result
        assert "competitor A started brunch" in result
        assert "Market Landscape" in result
        assert "Competitor A" in result
        assert "Google Place ID: ChIJcomp" in result

    def test_defaults_when_state_empty(self):
        result = _continue_research_instruction(MockCtx(state={}))

        assert "No prior report available." in result
        assert "No specialist notes available." in result
        assert "No research coverage notes available." in result
        assert "No continuation notes yet." in result
        assert "No restaurant data available." in result

    def test_strips_legacy_validation_packets_from_continuation_input(self):
        result = _continue_research_instruction(
            MockCtx(
                state={
                    "final_report": "Existing report",
                    "market_result": (
                        "Market finding.\n\n"
                        "### Validation Packet\n\n"
                        "```json\n"
                        '{"claims_for_validation":[],"candidate_sources":[]}\n'
                        "```"
                    ),
                }
            )
        )

        assert "Market finding" in result
        assert "claims_for_validation" not in result
        assert "candidate_sources" not in result


class TestRecordContinuationNotes:
    def test_records_reply_in_session_state(self):
        ctx = MockCallbackCtx(
            state={
                "continue_research_reply": "Competitor A added brunch on weekends.",
                "turnIdx": 2,
            },
            user_text="Can you check competitor A brunch?",
        )

        _record_continuation_notes(callback_context=ctx)

        notes = ctx.state[_CONTINUATION_NOTES_KEY]
        assert "Turn 2" in notes
        assert "competitor A brunch" in notes
        assert "Competitor A added brunch" in notes

    def test_no_reply_means_no_state_delta(self):
        ctx = MockCallbackCtx(state={}, user_text="Question")

        _record_continuation_notes(callback_context=ctx)

        assert _CONTINUATION_NOTES_KEY not in ctx.state


class TestRouterInstruction:
    def test_report_delivered_note(self):
        result = _router_instruction(MockCtx(state={"final_report": "Some report content"}))

        assert "report has already been delivered" in result
        assert "continue_research" in result

    def test_no_report_note(self):
        result = _router_instruction(MockCtx(state={}))

        assert "No research has been done yet" in result
