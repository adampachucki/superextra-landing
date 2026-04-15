"""Tests for instruction provider functions in agent.py."""

from superextra_agent.agent import (
    _orchestrator_instruction,
    _synthesizer_instruction,
    _follow_up_instruction,
    _router_instruction,
    _SYNTHESIZER_KEYS,
    _SPECIALIST_RESULT_KEYS,
)
from superextra_agent.specialists import _make_instruction


class MockCtx:
    def __init__(self, state=None):
        self.state = state or {}


class TestOrchestratorInstruction:
    def test_injects_places_context(self):
        """places_context from state is injected into the template."""
        ctx = MockCtx(state={"places_context": "Restaurant XYZ data here"})

        result = _orchestrator_instruction(ctx)

        assert "Restaurant XYZ data here" in result

    def test_default_when_missing(self):
        """Uses default text when places_context is not in state."""
        ctx = MockCtx(state={})

        result = _orchestrator_instruction(ctx)

        assert "No Google Places data available." in result

    def test_appends_existing_results_on_follow_up(self):
        """Existing specialist results are noted for follow-up turns."""
        ctx = MockCtx(state={
            "places_context": "Restaurant data",
            "market_result": "Market findings here",
            "pricing_result": "Pricing findings here",
            "research_plan": "Prior plan summary",
        })

        result = _orchestrator_instruction(ctx)

        assert "Existing research from prior turn" in result
        assert "Market Landscape" in result
        assert "Menu & Pricing" in result
        assert "Prior plan summary" in result

    def test_no_follow_up_note_when_no_results(self):
        """No follow-up section when no specialist results exist."""
        ctx = MockCtx(state={"places_context": "Restaurant data"})

        result = _orchestrator_instruction(ctx)

        assert "Existing research from prior turn" not in result

    def test_ignores_default_specialist_output(self):
        """Specialist outputs with default value are not listed as existing."""
        ctx = MockCtx(state={
            "places_context": "Data",
            "market_result": "Agent did not produce output.",
        })

        result = _orchestrator_instruction(ctx)

        assert "Existing research from prior turn" not in result


class TestSynthesizerInstruction:
    def test_injects_all_keys(self):
        """All 11 keys from state are injected into the template."""
        state = {k: f"value_for_{k}" for k in _SYNTHESIZER_KEYS}
        ctx = MockCtx(state=state)

        result = _synthesizer_instruction(ctx)

        for key in _SYNTHESIZER_KEYS:
            assert f"value_for_{key}" in result

    def test_default_for_missing_keys(self):
        """Missing keys get 'Agent did not produce output.' default."""
        ctx = MockCtx(state={})

        result = _synthesizer_instruction(ctx)

        assert "Agent did not produce output." in result


class TestMakeInstruction:
    def test_returns_provider_that_injects_places_context(self):
        """_make_instruction returns a callable that injects places_context."""
        provider = _make_instruction("market_landscape")

        ctx = MockCtx(state={"places_context": "Competitor data for area"})
        result = provider(ctx)

        assert "Competitor data for area" in result

    def test_provider_uses_default_when_missing(self):
        """Provider uses default when places_context is not in state."""
        provider = _make_instruction("market_landscape")

        ctx = MockCtx(state={})
        result = provider(ctx)

        assert "No Google Places data available." in result


class TestFollowUpInstruction:
    def test_injects_prior_report(self):
        """Prior final_report is injected into follow-up instructions."""
        ctx = MockCtx(state={
            "final_report": "## Market Report\nKey findings here.",
            "places_context": "Restaurant XYZ data",
            "research_plan": "Plan summary",
        })

        result = _follow_up_instruction(ctx)

        assert "## Market Report" in result
        assert "Restaurant XYZ data" in result
        assert "Plan summary" in result

    def test_defaults_when_state_empty(self):
        """Uses defaults when no prior state exists."""
        ctx = MockCtx(state={})

        result = _follow_up_instruction(ctx)

        assert "No prior report available." in result
        assert "No restaurant data available." in result
        assert "No research plan available." in result

    def test_handles_curly_braces_in_report(self):
        """LLM output with curly braces doesn't crash the provider."""
        ctx = MockCtx(state={
            "final_report": "Code: `plt.bar(x, y, color={0: 'red'})`",
            "places_context": "Data with {braces}",
            "research_plan": "Plan",
        })

        result = _follow_up_instruction(ctx)

        assert "color={0: 'red'}" in result
        assert "{braces}" in result


class TestRouterInstruction:
    def test_report_delivered_note(self):
        """Appends 'report delivered' when final_report exists in state."""
        ctx = MockCtx(state={"final_report": "Some report content"})

        result = _router_instruction(ctx)

        assert "report has already been delivered" in result

    def test_no_report_note(self):
        """Appends 'no research' when state is empty."""
        ctx = MockCtx(state={})

        result = _router_instruction(ctx)

        assert "No research has been done yet" in result
