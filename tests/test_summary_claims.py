"""CR5 L1: list-valued lens extraction (tasks/patterns/decisions_values as 0..N claims).

The abstractive path forced exactly one string per lens; the extractive path parses
each lens as a JSON array of atomic claims, where an empty list is a valid result.
"""

from __future__ import annotations

import pytest

from claude_code_sessions.database.sqlite.summary_json import (
    LENS_LIST_KEYS,
    parse_lens_lists,
)


def test_parses_lists_of_varying_length() -> None:
    raw = (
        '{"tasks": ["add an n_ctx flag", "fix the overflow"], '
        '"patterns": ["tiered match cascade"], '
        '"decisions_values": [], '
        '"learnings": ["verify n_ctx before a long run", "read the source not the binary"]}'
    )
    out = parse_lens_lists(raw)
    assert out["tasks"] == ["add an n_ctx flag", "fix the overflow"]  # many
    assert out["patterns"] == ["tiered match cascade"]  # one
    assert out["decisions_values"] == []  # empty list is valid
    assert out["learnings"] == [  # the 4th lens — process/skill improvements
        "verify n_ctx before a long run",
        "read the source not the binary",
    ]


def test_all_empty_lists_is_valid() -> None:
    out = parse_lens_lists(
        '{"tasks": [], "patterns": [], "decisions_values": [], "learnings": []}'
    )
    assert all(out[k] == [] for k in LENS_LIST_KEYS)


def test_tolerates_think_trace_and_prose_wrapping() -> None:
    raw = (
        "<think>the user is benchmarking summarisers</think>\n"
        'Here is the JSON:\n```json\n'
        '{"tasks": ["benchmark summariser strategies"], "patterns": [], '
        '"decisions_values": ["values reproducibility over speed"], "learnings": []}\n```\n'
    )
    out = parse_lens_lists(raw)
    assert out["tasks"] == ["benchmark summariser strategies"]
    assert out["decisions_values"] == ["values reproducibility over speed"]


def test_missing_lens_key_raises() -> None:
    with pytest.raises(KeyError):
        parse_lens_lists('{"tasks": [], "patterns": []}')  # decisions_values missing


def test_non_array_lens_value_raises() -> None:
    # A bare string where an array is required must fail loud, not be coerced.
    with pytest.raises(ValueError, match="array"):
        parse_lens_lists(
            '{"tasks": "one task", "patterns": [], "decisions_values": [], "learnings": []}'
        )


def test_no_json_object_raises() -> None:
    with pytest.raises(ValueError, match="no balanced JSON object"):
        parse_lens_lists("I cannot help with that.")
