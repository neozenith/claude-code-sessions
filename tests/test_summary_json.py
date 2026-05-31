"""Tests for robust 3-lens JSON extraction from real model output (CR1)."""

from __future__ import annotations

import json

import pytest

from claude_code_sessions.database.sqlite.summary_json import parse_lenses

_GOOD = {"task_summary": "build X", "patterns": "pluggable", "decisions_values": "local-only"}


def test_parses_a_bare_json_object() -> None:
    assert parse_lenses(json.dumps(_GOOD)) == _GOOD


def test_extracts_object_from_think_wrapped_output() -> None:
    """Qwen-style reasoning before the JSON must not break parsing."""
    raw = f"<think>\nThe user wants three lenses.\n</think>\n{json.dumps(_GOOD)}\n"
    assert parse_lenses(raw) == _GOOD


def test_extracts_object_from_fenced_block_with_prose() -> None:
    raw = f"Here is the summary:\n```json\n{json.dumps(_GOOD)}\n```\nDone."
    assert parse_lenses(raw) == _GOOD


def test_fails_loud_when_no_json_object() -> None:
    with pytest.raises(ValueError):
        parse_lenses("I could not produce a summary.")


def test_fails_loud_when_lens_keys_missing() -> None:
    with pytest.raises(KeyError):
        parse_lenses(json.dumps({"task_summary": "x", "patterns": "y"}))
