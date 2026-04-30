"""Invariant tests for the specialist catalog.

The catalog is the single source of truth; these tests keep the derived
views aligned with it. If these fail after a specialist change, fix the
catalog entry, not the derived view.
"""
from __future__ import annotations

from superextra_agent.specialist_catalog import (
    AUTHOR_TO_OUTPUT_KEY,
    OUTPUT_KEY_TO_LABEL,
    ROLE_TITLES,
    SPECIALIST_OUTPUT_KEYS,
    SPECIALIST_RESULT_KEYS,
    SPECIALISTS,
)


def test_output_keys_are_unique():
    keys = [s.output_key for s in SPECIALISTS]
    assert len(keys) == len(set(keys))


def test_names_are_unique():
    names = [s.name for s in SPECIALISTS]
    assert len(names) == len(set(names))


def test_author_to_output_key_covers_every_specialist():
    assert set(AUTHOR_TO_OUTPUT_KEY) == {s.name for s in SPECIALISTS}


def test_output_key_to_label_covers_every_specialist():
    assert set(OUTPUT_KEY_TO_LABEL) == {s.output_key for s in SPECIALISTS}


def test_specialist_output_keys_cover_every_specialist():
    assert set(SPECIALIST_OUTPUT_KEYS) == {s.name for s in SPECIALISTS}


def test_role_titles_cover_every_specialist():
    expected = {(s.instruction_name or s.name) for s in SPECIALISTS}
    assert set(ROLE_TITLES) == expected


def test_specialist_result_keys_cover_every_specialist_output():
    assert set(SPECIALIST_RESULT_KEYS) == {s.output_key for s in SPECIALISTS}


def test_thinking_level_is_valid():
    assert all(s.thinking in {"high", "medium"} for s in SPECIALISTS)
