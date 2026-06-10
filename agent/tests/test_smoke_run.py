"""Tests for the pure pass/fail predicate in scripts/smoke_run.py."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "smoke_run", Path(__file__).resolve().parents[1] / "scripts" / "smoke_run.py"
)
smoke_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke_run)


def _good_turn() -> dict:
    return {
        "status": "complete",
        "reply": "x" * 2000,
        "turnSummary": {"headline": "h"},
        "sources": [{"url": "https://example.com"}],
        "error": None,
    }


class TestEvaluate:
    def test_passes_on_complete_turn_with_events(self):
        ok, problems = smoke_run.evaluate(_good_turn(), event_count=12)
        assert ok and problems == []

    def test_fails_on_error_status(self):
        turn = _good_turn() | {"status": "error", "error": "boom"}
        ok, problems = smoke_run.evaluate(turn, event_count=12)
        assert not ok
        assert any("boom" in p for p in problems)

    def test_fails_on_short_reply(self):
        ok, problems = smoke_run.evaluate(_good_turn() | {"reply": "short"}, 12)
        assert not ok
        assert any("reply too short" in p for p in problems)

    def test_fails_on_missing_summary_sources_events(self):
        turn = _good_turn() | {"turnSummary": None, "sources": []}
        ok, problems = smoke_run.evaluate(turn, event_count=0)
        assert not ok
        assert len(problems) == 3
