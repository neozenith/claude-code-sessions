"""Tests for the per-session turn-metrics HTTP endpoint (G6 / T6.1).

``GET /api/sessions/{projectId}/{sessionId}/metrics`` returns a per-turn
breakdown (idle/active/tps/too_fast) plus a session summary, backed by
``SQLiteDatabase.get_session_metrics``. Driven via FastAPI's TestClient
against a fixture-backed app (``app.state.db`` swapped to a tmp cache).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.database import SQLiteDatabase
from claude_code_sessions.main import app


def _fixture_db(tmp_path: Path, session_id: str) -> SQLiteDatabase:
    base = datetime(2025, 1, 1, tzinfo=UTC)

    def ts(sec: int) -> str:
        return base.replace(second=sec).isoformat().replace("+00:00", "Z")

    rows: list[dict[str, Any]] = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": ts(0),
            "sessionId": session_id,
            "message": {"role": "user", "content": "go"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req1",
            "timestamp": ts(2),
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 200},
                "content": [{"type": "text", "text": "answer"}],
            },
        },
        {
            "uuid": "u1",
            "parentUuid": "a1",
            "type": "user",
            "timestamp": ts(32),
            "sessionId": session_id,
            "message": {"role": "user", "content": "next"},
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
    return db


def test_session_metrics_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint returns 200 with a per-turn list and a session summary."""
    session_id = "sess-api"
    monkeypatch.setattr(app.state, "db", _fixture_db(tmp_path, session_id))
    client = TestClient(app)

    resp = client.get(f"/api/sessions/-Users-test-proj/{session_id}/metrics")
    assert resp.status_code == 200
    data = resp.json()

    assert set(data) >= {"turns", "summary"}
    assert len(data["turns"]) == 1
    turn = data["turns"][0]
    assert {"idle_ms", "active_ms", "tps", "too_fast"} <= set(turn)
    assert turn["idle_ms"] == 30_000  # a1(2s) → u1(32s)
    assert {"turn_count", "total_idle_ms", "total_active_ms"} <= set(data["summary"])
    assert data["summary"]["turn_count"] == 1
