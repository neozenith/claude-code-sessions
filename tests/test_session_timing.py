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


def test_idle_between_turns(tmp_path: Path) -> None:
    """When the assistant ends its turn at t0 and the human's next prompt
    arrives at t0+30s, that turn's idle_ms is ~30000."""
    session_id = "sess-idle"
    base = datetime(2025, 1, 1, tzinfo=UTC)

    def ts(sec: int) -> str:
        return base.replace(second=sec).isoformat().replace("+00:00", "Z")

    rows = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": ts(0),
            "sessionId": session_id,
            "message": {"role": "user", "content": "first prompt"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req_idle",
            "timestamp": ts(5),  # assistant ends its turn at t=5s
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 50},
                "content": [{"type": "text", "text": "answer"}],
            },
        },
        {
            "uuid": "u1",
            "parentUuid": "a1",
            "type": "user",
            "timestamp": ts(35),  # human replies 30s later
            "sessionId": session_id,
            "message": {"role": "user", "content": "second prompt"},
        },
    ]

    db = _ingest(tmp_path, rows, session_id=session_id)
    turns = db.get_session_metrics("-Users-test-proj", session_id)

    idles = [t["idle_ms"] for t in turns if t.get("idle_ms") is not None]
    assert any(abs(i - 30_000) <= 50 for i in idles), f"expected ~30000 idle, got {idles}"


def test_active_time_per_turn(tmp_path: Path) -> None:
    """active_ms for a turn = the human prompt → that turn's assistant
    end-of-turn head (8s of 'working' here)."""
    session_id = "sess-active"
    base = datetime(2025, 1, 1, tzinfo=UTC)

    def ts(sec: int) -> str:
        return base.replace(second=sec).isoformat().replace("+00:00", "Z")

    rows = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": ts(0),
            "sessionId": session_id,
            "message": {"role": "user", "content": "do the work"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req_active",
            "timestamp": ts(8),  # assistant finishes 8s after the prompt
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 50},
                "content": [{"type": "text", "text": "answer"}],
            },
        },
    ]

    db = _ingest(tmp_path, rows, session_id=session_id)
    turns = db.get_session_metrics("-Users-test-proj", session_id)

    assert turns, "expected at least one turn"
    assert turns[0]["active_ms"] == pytest.approx(8000, abs=50)


def _assistant_turn(uuid: str, parent: str, req: str, sec: int, session_id: str, out: int) -> dict:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return {
        "uuid": uuid,
        "parentUuid": parent,
        "type": "assistant",
        "requestId": req,
        "timestamp": base.replace(second=sec).isoformat().replace("+00:00", "Z"),
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-5-20250929",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": out},
            "content": [{"type": "text", "text": "answer"}],
        },
    }


def _human(uuid: str, parent: str | None, sec: int, session_id: str) -> dict:
    base = datetime(2025, 1, 1, tzinfo=UTC)
    return {
        "uuid": uuid,
        "parentUuid": parent,
        "type": "user",
        "timestamp": base.replace(second=sec).isoformat().replace("+00:00", "Z"),
        "sessionId": session_id,
        "message": {"role": "user", "content": "prompt"},
    }


def test_too_fast_flag(tmp_path: Path) -> None:
    """A 1s reply after a 2,000-token response is too_fast (1s < 2000/8=250s);
    a 1s reply after a 50-token response is not (below the 200-token floor)."""
    session_id = "sess-fast"
    rows = [
        _human("u0", None, 0, session_id),
        _assistant_turn("a1", "u0", "req1", 1, session_id, out=2000),
        _human("u1", "a1", 2, session_id),  # 1s after a1's 2000-token response
        _assistant_turn("a2", "u1", "req2", 3, session_id, out=50),
        _human("u2", "a2", 4, session_id),  # 1s after a2's 50-token response
    ]

    db = _ingest(tmp_path, rows, session_id=session_id)
    turns = db.get_session_metrics("-Users-test-proj", session_id)

    assert len(turns) == 2, f"expected 2 turns, got {turns}"
    assert turns[0]["too_fast"] is True  # 2000 tokens, replied in 1s
    assert turns[1]["too_fast"] is False  # 50 tokens — below the floor
