"""Tests for gap researcher instruction provider and skip callback."""

from superextra_agent.specialists import (
    _gap_researcher_instruction,
    _skip_if_no_outputs,
    _GAP_RESEARCHER_KEYS,
)
from google.genai import types


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


class TestSkipIfNoOutputs:
    def test_skips_when_no_outputs(self):
        ctx = MockCtx(state={})

        result = _skip_if_no_outputs(ctx)

        assert isinstance(result, types.Content)
        assert result.parts[0].text == "No specialist outputs to analyze."

    def test_proceeds_when_outputs_exist(self):
        ctx = MockCtx(state={"market_result": "Some real findings here"})

        result = _skip_if_no_outputs(ctx)

        assert result is None
