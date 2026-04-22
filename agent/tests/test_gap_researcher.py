"""Tests for gap researcher instruction provider and the run/skip gate."""

from google.genai import types

from superextra_agent.specialists import (
    _gap_researcher_instruction,
    _should_run_gap_researcher,
    _GAP_RESEARCHER_KEYS,
)


class MockCtx:
    def __init__(self, state=None):
        self.state = state or {}


class TestGapResearcherInstruction:
    def test_injects_all_keys(self):
        state = {k: f"value_for_{k}" for k in _GAP_RESEARCHER_KEYS}
        ctx = MockCtx(state=state)

        result = _gap_researcher_instruction(ctx)

        for key in _GAP_RESEARCHER_KEYS:
            assert f"value_for_{key}" in result

    def test_defaults_for_missing_keys(self):
        ctx = MockCtx(state={})

        result = _gap_researcher_instruction(ctx)

        assert "Agent did not produce output." in result


class TestShouldRunGapResearcher:
    def test_skips_when_no_specialists_assigned(self):
        """No orchestrator briefs = nothing to analyze = skip."""
        ctx = MockCtx(state={})
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert result.parts[0].text == "No specialist outputs to analyze."

    def test_skips_when_all_assigned_specialists_succeeded(self):
        """Real outputs from every brief-assigned specialist → skip."""
        ctx = MockCtx(state={
            "specialist_briefs": {
                "market_landscape": "look at market",
                "menu_pricing": "look at pricing",
            },
            "market_result": "# Market\nSome real findings.",
            "pricing_result": "# Pricing\nMore real findings.",
        })
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert "no gaps to research" in result.parts[0].text.lower()

    def test_runs_when_an_assigned_specialist_errored(self):
        """Any `Research unavailable: …` for an assigned specialist → run."""
        ctx = MockCtx(state={
            "specialist_briefs": {
                "market_landscape": "look at market",
                "menu_pricing": "look at pricing",
            },
            "market_result": "# Market\nSome real findings.",
            "pricing_result": "Research unavailable: TimeoutError",
        })
        result = _should_run_gap_researcher(ctx)
        assert result is None  # None means "proceed to the LLM call"

    def test_runs_when_assigned_specialist_state_is_missing(self):
        """Assigned but nothing in state — crashed silently before
        `_on_model_error` could write a fallback → run gap research."""
        ctx = MockCtx(state={
            "specialist_briefs": {
                "market_landscape": "look at market",
            },
            # market_result intentionally absent.
        })
        result = _should_run_gap_researcher(ctx)
        assert result is None

    def test_unassigned_specialists_do_not_count_as_failures(self):
        """`NOT_RELEVANT` from an unassigned specialist is not a failure —
        the orchestrator just didn't ask. Only assigned specialists matter."""
        ctx = MockCtx(state={
            "specialist_briefs": {
                "market_landscape": "look at market",
            },
            "market_result": "# Market\nReal findings.",
            "pricing_result": "NOT_RELEVANT",  # never assigned; ignore
        })
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert "no gaps to research" in result.parts[0].text.lower()

    def test_unknown_brief_keys_are_ignored(self):
        """Brief keys outside `_SPECIALIST_OUTPUT_KEYS` (e.g. the dynamic
        researcher's brief shape) shouldn't force a run on their own."""
        ctx = MockCtx(state={
            "specialist_briefs": {
                "dynamic_researcher_1": "some extra angle",  # valid, mapped
                "market_landscape": "look at market",
            },
            "market_result": "# Market\nReal findings.",
            "dynamic_result_1": "# Dynamic\nMore real findings.",
        })
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert "no gaps to research" in result.parts[0].text.lower()
