"""Tests for response duration + throughput (G4) and turn timing (G5).

``response_duration_ms`` is stamped on each response head in the per-file
post-pass (``_annotate_responses``) as the delta from the triggering
(preceding) event to the head's timestamp, since the JSONL has no
per-assistant ``durationMs``. TPS is derived in the query layer as
``output_tokens / (response_duration_ms / 1000)``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from claude_code_sessions.database import SQLiteDatabase


def _ingest(tmp_path: Path, rows: list[dict[str, Any]], *, session_id: str) -> SQLiteDatabase:
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
    return db


def test_response_tps(tmp_path: Path) -> None:
    """A response whose head lands 2s after its triggering event, with
    output_tokens=200, reports response_duration_ms≈2000 and tps≈100."""
    session_id = "sess-tps"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": base.replace(second=0).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {"role": "user", "content": "go"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req_tps",
            "timestamp": base.replace(second=2).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 200},
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]

    db = _ingest(tmp_path, rows, session_id=session_id)
    head = next(
        e for e in db.get_session_events("-Users-test-proj", session_id)
        if e["event_type"] == "assistant"
    )

    assert head["response_duration_ms"] == 2000
    assert head["tps"] == pytest.approx(100.0)


def test_tps_none_when_no_duration(tmp_path: Path) -> None:
    """A response whose head shares its triggering event's timestamp has
    response_duration_ms=0; tps is None, never a divide-by-zero."""
    session_id = "sess-instant"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    same = base.replace(second=5).isoformat().replace("+00:00", "Z")
    rows = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": same,
            "sessionId": session_id,
            "message": {"role": "user", "content": "go"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req_instant",
            "timestamp": same,  # same instant as the trigger → zero duration
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 200},
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]

    db = _ingest(tmp_path, rows, session_id=session_id)
    head = next(
        e for e in db.get_session_events("-Users-test-proj", session_id)
        if e["event_type"] == "assistant"
    )

    assert head["response_duration_ms"] == 0
    assert head["tps"] is None
