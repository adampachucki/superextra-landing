"""Invariant tests for the specialist catalog.

The catalog is the single source of truth; these tests keep the various
derived views aligned with it. If these fail after a specialist change,
fix the catalog entry — don't patch the derived view.
"""
from __future__ import annotations

from superextra_agent.specialist_catalog import (
    AUTHOR_TO_OUTPUT_KEY,
    FALLBACK_SECTIONS,
    ORCHESTRATOR_SPECIALISTS,
    OUTPUT_KEY_TO_LABEL,
    ROLE_TITLES,
    SPECIALIST_OUTPUT_KEYS,
    SPECIALIST_RESULT_KEYS,
    SPECIALISTS,
)


def test_output_keys_are_unique():
    """No two specialists share an output_key — would collide in state."""
    keys = [s.output_key for s in SPECIALISTS]
    assert len(keys) == len(set(keys))


def test_names_are_unique():
    names = [s.name for s in SPECIALISTS]
    assert len(names) == len(set(names))


def test_orchestrator_specialists_exclude_gap_researcher():
    """Gap researcher runs as a distinct phase; the orchestrator can't
    call it as a specialist tool."""
    assert all(s.name != "gap_researcher" for s in ORCHESTRATOR_SPECIALISTS)


def test_gap_researcher_is_in_full_catalog():
    """But the gap researcher IS part of the overall catalog — it emits
    events and has an output_key like the others."""
    gap = next((s for s in SPECIALISTS if s.name == "gap_researcher"), None)
    assert gap is not None
    assert gap.output_key == "gap_research_result"
    assert gap.dispatchable is False


def test_author_to_output_key_covers_every_specialist():
    assert set(AUTHOR_TO_OUTPUT_KEY) == {s.name for s in SPECIALISTS}


def test_output_key_to_label_covers_every_specialist():
    assert set(OUTPUT_KEY_TO_LABEL) == {s.output_key for s in SPECIALISTS}


def test_specialist_output_keys_is_orchestrator_specialists_only():
    """Used by the gap-gate to inspect orchestrator-callable specialists only."""
    assert set(SPECIALIST_OUTPUT_KEYS) == {s.name for s in ORCHESTRATOR_SPECIALISTS}


def test_role_titles_cover_orchestrator_specialists():
    """Every orchestrator-callable specialist (via its instruction_name) must have a
    role_title so specialist_base.md's `{role_title}` placeholder resolves."""
    expected = {(s.instruction_name or s.name) for s in ORCHESTRATOR_SPECIALISTS}
    assert set(ROLE_TITLES) == expected


def test_specialist_result_keys_excludes_gap():
    """Orchestrator-prompt lookup: prior-turn detection is based on Phase 1
    specialist outputs, not gap research."""
    assert set(SPECIALIST_RESULT_KEYS) == {s.output_key for s in ORCHESTRATOR_SPECIALISTS}


def test_fallback_sections_include_gap_research():
    """The synth fallback report stitches every specialist output, including
    gap research — the user sees all collected signal."""
    section_keys = [k for k, _ in FALLBACK_SECTIONS]
    assert "gap_research_result" in section_keys
    assert section_keys == [s.output_key for s in SPECIALISTS]


def test_thinking_level_is_valid():
    """Guard against typos — only 'high' and 'medium' are mapped."""
    assert all(s.thinking in {"high", "medium"} for s in SPECIALISTS)


def test_orchestrator_specialists_are_dispatchable():
    assert all(s.dispatchable for s in ORCHESTRATOR_SPECIALISTS)
