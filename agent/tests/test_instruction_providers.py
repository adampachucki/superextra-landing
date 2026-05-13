"""Tests for instruction provider functions in agent.py."""

from superextra_agent.agent import (
    _follow_up_instruction,
    _report_writer_instruction,
    _research_lead_instruction,
    _router_instruction,
)
from superextra_agent.specialists import _make_instruction


class MockCtx:
    def __init__(self, state=None):
        self.state = state or {}


class TestResearchLeadInstruction:
    def test_injects_places_context(self):
        ctx = MockCtx(state={"places_context": "Restaurant XYZ data here"})

        result = _research_lead_instruction(ctx)

        assert "Restaurant XYZ data here" in result
        assert "## Market Source Profiles" in result

    def test_default_when_missing(self):
        ctx = MockCtx(state={})

        result = _research_lead_instruction(ctx)

        assert "No Google Places data available." in result

    def test_appends_existing_results_on_follow_up(self):
        ctx = MockCtx(state={
            "places_context": "Restaurant data",
            "market_result": "Market findings here",
            "pricing_result": "Pricing findings here",
        })

        result = _research_lead_instruction(ctx)

        assert "Existing research from prior turn" in result
        assert "Market Landscape" in result
        assert "Menu & Pricing" in result
        assert "Prior research plan" not in result

    def test_no_follow_up_note_when_no_results(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "Existing research from prior turn" not in result

    def test_ignores_default_specialist_output(self):
        ctx = MockCtx(state={
            "places_context": "Data",
            "market_result": "Agent did not produce output.",
        })

        result = _research_lead_instruction(ctx)

        assert "Existing research from prior turn" not in result

    def test_does_not_include_final_report_chart_contract(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "```chart" not in result

    def test_writer_brief_is_not_a_findings_filter(self):
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _research_lead_instruction(ctx)

        assert "writer brief is a routing note, not a findings note" in result
        assert "Do not list discovered entities" in result
        assert "Do not decide which specialist findings matter most" in result


class TestReportWriterInstruction:
    def test_injects_writer_brief_and_specialist_reports(self):
        ctx = MockCtx(state={
            "places_context": "Restaurant XYZ data",
            "writer_brief": "Focus on demand and pricing links.",
            "market_result": "Market demand is weekday-heavy.",
            "pricing_result": "Average entree price is 21 USD.",
        })

        result = _report_writer_instruction(ctx)

        assert "Restaurant XYZ data" in result
        assert "Focus on demand and pricing links." in result
        assert "Market demand is weekday-heavy." in result
        assert "Average entree price is 21 USD." in result
        assert "### Market Landscape" in result
        assert "### Menu & Pricing" in result

    def test_defaults_when_state_empty(self):
        ctx = MockCtx(state={})

        result = _report_writer_instruction(ctx)

        assert "No restaurant data available." in result
        assert "No writer brief available." in result
        assert "No specialist reports available." in result

    def test_handles_curly_braces_in_injected_material(self):
        ctx = MockCtx(state={
            "places_context": "Context with {braces}",
            "writer_brief": "Brief includes {scope}",
            "market_result": "Source note: `{city: 'Warsaw'}`",
        })

        result = _report_writer_instruction(ctx)

        assert "{braces}" in result
        assert "{scope}" in result
        assert "{city: 'Warsaw'}" in result

    def test_chart_json_braces_are_escaped_for_format(self):
        ctx = MockCtx(state={"writer_brief": "Brief", "market_result": "Report"})

        result = _report_writer_instruction(ctx)

        assert '```chart\n{"type":"bar"' in result

    def test_retention_contract_preserves_all_findings(self):
        ctx = MockCtx(state={
            "writer_brief": "Focus on openings.",
            "market_result": "Zołza closed. Matcha Ma opened.",
            "dynamic_result_1": "Nam-Viet remains operational nearby.",
        })

        result = _report_writer_instruction(ctx)

        assert "If the writer brief omits a finding" in result
        assert "Err on the side of showing too much useful evidence" in result
        assert "Complete Findings Ledger" in result
        assert "Do not collapse several concrete findings" in result
        assert "Do not omit evidence to make room for follow-up questions" in result
        assert "Zołza closed" in result
        assert "Nam-Viet remains operational nearby" in result


class TestMakeInstruction:
    def test_returns_provider_that_injects_places_context(self):
        provider = _make_instruction("market_landscape")

        ctx = MockCtx(state={"places_context": "Competitor data for area"})
        result = provider(ctx)

        assert "Competitor data for area" in result
        assert "## Market Source Profiles" not in result

    def test_provider_uses_default_when_missing(self):
        provider = _make_instruction("market_landscape")

        ctx = MockCtx(state={})
        result = provider(ctx)

        assert "No Google Places data available." in result

    def test_review_analyst_does_not_inherit_web_fetch_instructions(self):
        provider = _make_instruction("review_analyst")

        ctx = MockCtx(
            state={"places_context": "Target data", "_target_place_id": "ChIJtarget"}
        )
        result = provider(ctx)

        assert "You do not have `google_search`" in result
        assert "fetch_web_content" not in result
        assert "## Market Source Profiles" not in result
        assert "Pyszne.pl" not in result
        assert "ChIJtarget" in result


class TestFollowUpInstruction:
    def test_injects_prior_report(self):
        ctx = MockCtx(state={
            "final_report": "## Market Report\nKey findings here.",
            "places_context": "Restaurant XYZ data",
            "market_result": "Market specialist notes",
        })

        result = _follow_up_instruction(ctx)

        assert "## Market Report" in result
        assert "Restaurant XYZ data" in result
        assert "Market specialist notes" in result
        assert "Market Landscape" in result

    def test_defaults_when_state_empty(self):
        ctx = MockCtx(state={})

        result = _follow_up_instruction(ctx)

        assert "No prior report available." in result
        assert "No specialist notes available." in result
        assert "No restaurant data available." in result
        assert "No research plan available." not in result

    def test_handles_curly_braces_in_report(self):
        ctx = MockCtx(state={
            "final_report": "Code: `plt.bar(x, y, color={0: 'red'})`",
            "places_context": "Data with {braces}",
        })

        result = _follow_up_instruction(ctx)

        assert "color={0: 'red'}" in result
        assert "{braces}" in result


class TestRouterInstruction:
    def test_report_delivered_note(self):
        ctx = MockCtx(state={"final_report": "Some report content"})

        result = _router_instruction(ctx)

        assert "report has already been delivered" in result
        assert "narrow same-target or same-area detail" in result

    def test_no_report_note(self):
        ctx = MockCtx(state={})

        result = _router_instruction(ctx)

        assert "No research has been done yet" in result
