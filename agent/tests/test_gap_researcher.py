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

    def test_inserted_placeholder_like_text_stays_verbatim(self):
        """Guards against the chained-`.replace()` regression. `.format()`
        does NOT re-scan values for placeholders, so a specialist output
        containing `{review_result}` renders as literal text, not a second
        substitution round."""
        state = {k: "ignored" for k in _GAP_RESEARCHER_KEYS}
        state["market_result"] = "literal token {review_result}"
        state["review_result"] = "REVIEW"
        ctx = MockCtx(state=state)

        result = _gap_researcher_instruction(ctx)

        assert "literal token {review_result}" in result


class TestShouldRunGapResearcher:
    def test_skips_when_no_specialists_assigned(self):
        """No specialist outputs = nothing to analyze = skip."""
        ctx = MockCtx(state={})
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert result.parts[0].text == "No specialist outputs to analyze."

    def test_skips_when_specialist_outputs_succeeded(self):
        """Real outputs from called specialists → skip."""
        ctx = MockCtx(state={
            "market_result": "# Market\nSome real findings.",
            "pricing_result": "# Pricing\nMore real findings.",
        })
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert "no gaps to research" in result.parts[0].text.lower()

    def test_runs_when_a_called_specialist_errored(self):
        """Any `Research unavailable: …` for a called specialist → run."""
        ctx = MockCtx(state={
            "market_result": "# Market\nSome real findings.",
            "pricing_result": "Research unavailable: TimeoutError",
        })
        result = _should_run_gap_researcher(ctx)
        assert result is None  # None means "proceed to the LLM call"

    def test_missing_uncalled_specialists_do_not_count_as_failures(self):
        """There is no second dispatch registry under AgentTool. Missing
        output keys mean the specialist was not called, not that it failed."""
        ctx = MockCtx(state={
            "market_result": "# Market\nReal findings.",
            # pricing_result intentionally absent.
        })
        result = _should_run_gap_researcher(ctx)
        assert isinstance(result, types.Content)
        assert "no gaps to research" in result.parts[0].text.lower()
