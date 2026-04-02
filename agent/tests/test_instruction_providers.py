"""Tests for instruction provider functions in agent.py."""

from superextra_agent.agent import (
    _planner_instruction,
    _synthesizer_instruction,
    _executor_instruction,
    _SYNTHESIZER_KEYS,
)
from superextra_agent.specialists import _make_instruction


class MockCtx:
    def __init__(self, state=None):
        self.state = state or {}


class TestPlannerInstruction:
    def test_injects_places_context(self):
        """places_context from state is injected into the template."""
        ctx = MockCtx(state={"places_context": "Restaurant XYZ data here"})

        result = _planner_instruction(ctx)

        assert "Restaurant XYZ data here" in result

    def test_default_when_missing(self):
        """Uses default text when places_context is not in state."""
        ctx = MockCtx(state={})

        result = _planner_instruction(ctx)

        assert "No Google Places data available." in result


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


class TestExecutorInstruction:
    def test_injects_scope_plan_and_places_context(self):
        """Both scope_plan and places_context are injected."""
        ctx = MockCtx(state={
            "scope_plan": "Research plan: analyze market",
            "places_context": "Places data for Sushi Bar"
        })

        result = _executor_instruction(ctx)

        assert "Research plan: analyze market" in result
        assert "Places data for Sushi Bar" in result

    def test_defaults_when_missing(self):
        """Uses defaults when state keys are missing."""
        ctx = MockCtx(state={})

        result = _executor_instruction(ctx)

        assert "No research plan available." in result
        assert "No Google Places data available." in result


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
