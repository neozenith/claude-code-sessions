"""Tests for subagent message-kind prefixing (G3).

When an event belongs to a subagent context, its derived ``msg_kind`` is
prefixed with ``subagent-`` so the dashboard can distinguish subagent
activity from main-thread activity. These are pure-function unit tests.
"""

from __future__ import annotations

import pytest

from claude_code_sessions.database.sqlite.pricing import message_kind


@pytest.mark.parametrize(
    "event_type,is_meta,content,base",
    [
        ("user", False, "hi", "human"),
        ("assistant", False, [{"type": "tool_use", "name": "Read"}], "tool_use"),
        ("assistant", False, [{"type": "thinking", "thinking": "…"}], "thinking"),
    ],
)
def test_subagent_prefix_applied(
    event_type: str, is_meta: bool, content: object, base: str
) -> None:
    """is_subagent=True prefixes the base kind; is_subagent=False leaves it bare."""
    assert message_kind(event_type, is_meta, content, is_subagent=False) == base
    assert message_kind(event_type, is_meta, content, is_subagent=True) == f"subagent-{base}"
