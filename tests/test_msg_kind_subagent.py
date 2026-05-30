"""Tests for subagent message-kind prefixing (G3).

When an event belongs to a subagent context, its derived ``msg_kind`` is
prefixed with ``subagent-`` so the dashboard can distinguish subagent
activity from main-thread activity. These are pure-function unit tests.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_code_sessions.database import SQLiteDatabase
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


def test_subagent_file_events_all_prefixed(tmp_path: Path) -> None:
    """After ingesting a subagent file (file_type='subagent'), every event
    carries a subagent-* kind — no bare 'human'/'user_text' remains."""
    session_id = "sub-sess"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        {
            "uuid": "su0",
            "parentUuid": None,
            "type": "user",
            "isSidechain": True,
            "timestamp": base.replace(second=0).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {"role": "user", "content": "do a subtask"},
        },
        {
            "uuid": "sa1",
            "parentUuid": "su0",
            "type": "assistant",
            "isSidechain": True,
            "requestId": "req_sub",
            "timestamp": base.replace(second=1).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 10},
                "content": [{"type": "text", "text": "working on it"}],
            },
        },
    ]
    projects = tmp_path / "projects"
    project_dir = projects / "-Users-test-proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f"{session_id}.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    db = SQLiteDatabase(
        local_projects_path=projects,
        home_projects_path=projects,
        db_path=tmp_path / "cache.db",
    )
    db.cache.ingest_file(
        {
            "filepath": str(jsonl),
            "project_id": "-Users-test-proj",
            "file_type": "subagent",
            "session_id": session_id,
            "mtime": jsonl.stat().st_mtime,
            "size_bytes": jsonl.stat().st_size,
        }
    )

    events = db.get_session_events("-Users-test-proj", session_id)
    kinds = [e["message_kind"] for e in events]
    assert kinds, "expected ingested events"
    assert all(k.startswith("subagent-") for k in kinds), f"unprefixed kinds present: {kinds}"
    assert "subagent-human" in kinds  # the user prompt, formerly bare 'human'


def test_main_session_human_unprefixed(tmp_path: Path) -> None:
    """A non-sidechain human prompt in a main_session file stays bare 'human'
    — the subagent prefix must not leak onto main-thread events."""
    session_id = "main-sess"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        {
            "uuid": "mu0",
            "parentUuid": None,
            "type": "user",
            "timestamp": base.replace(second=0).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {"role": "user", "content": "hello from the main thread"},
        },
    ]
    projects = tmp_path / "projects"
    project_dir = projects / "-Users-test-proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f"{session_id}.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    db = SQLiteDatabase(
        local_projects_path=projects,
        home_projects_path=projects,
        db_path=tmp_path / "cache.db",
    )
    db.cache.ingest_file(
        {
            "filepath": str(jsonl),
            "project_id": "-Users-test-proj",
            "file_type": "main_session",
            "session_id": session_id,
            "mtime": jsonl.stat().st_mtime,
            "size_bytes": jsonl.stat().st_size,
        }
    )

    events = db.get_session_events("-Users-test-proj", session_id)
    human = next(e for e in events if e["event_type"] == "user")
    assert human["message_kind"] == "human"
