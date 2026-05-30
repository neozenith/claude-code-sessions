"""Tests for the cross-session performance summary endpoint (G6 / T6.2).

``GET /api/performance`` returns per-model TPS rows and a context-ratio
histogram (no zone labels — per the G2 ADR), honoring the global
``days``/``project`` filters. Driven via TestClient against a fixture-backed
app with two projects on different models.
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


def _session_rows(session_id: str, model: str) -> list[dict[str, Any]]:
    base = datetime(2025, 1, 1, tzinfo=UTC)

    def ts(sec: int) -> str:
        return base.replace(second=sec).isoformat().replace("+00:00", "Z")

    return [
        {
            "uuid": f"{session_id}-u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": ts(0),
            "sessionId": session_id,
            "message": {"role": "user", "content": "go"},
        },
        {
            "uuid": f"{session_id}-a1",
            "parentUuid": f"{session_id}-u0",
            "type": "assistant",
            "requestId": f"{session_id}-req",
            "timestamp": ts(2),
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": model,
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 200},
                "content": [{"type": "text", "text": "answer"}],
            },
        },
        {
            "uuid": f"{session_id}-u1",
            "parentUuid": f"{session_id}-a1",
            "type": "user",
            "timestamp": ts(20),
            "sessionId": session_id,
            "message": {"role": "user", "content": "next"},
        },
    ]


def _two_project_db(tmp_path: Path) -> SQLiteDatabase:
    projects = tmp_path / "projects"
    db = SQLiteDatabase(
        local_projects_path=projects,
        home_projects_path=projects,
        db_path=tmp_path / "cache.db",
    )
    specs = [
        ("-Users-test-projA", "sessA", "claude-sonnet-4-5-20250929"),
        ("-Users-test-projB", "sessB", "claude-opus-4-7-20260115"),
    ]
    for project_id, session_id, model in specs:
        pdir = projects / project_id
        pdir.mkdir(parents=True, exist_ok=True)
        jsonl = pdir / f"{session_id}.jsonl"
        jsonl.write_text(
            "\n".join(json.dumps(r) for r in _session_rows(session_id, model)),
            encoding="utf-8",
        )
        db.cache.ingest_file(
            {
                "filepath": str(jsonl),
                "project_id": project_id,
                "file_type": "main_session",
                "session_id": session_id,
                "mtime": jsonl.stat().st_mtime,
                "size_bytes": jsonl.stat().st_size,
            }
        )
    return db


def test_performance_summary_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint returns by_model + ratio_histogram, and a project filter
    narrows by_model to that project's model only."""
    monkeypatch.setattr(app.state, "db", _two_project_db(tmp_path))
    client = TestClient(app)

    full = client.get("/api/performance")
    assert full.status_code == 200
    data = full.json()
    assert {"by_model", "ratio_histogram"} <= set(data)
    assert len(data["by_model"]) == 2  # sonnet + opus
    row = data["by_model"][0]
    assert {"model_id", "avg_tps", "median_tps", "response_count",
            "total_idle_ms", "total_active_ms"} <= set(row)
    assert data["ratio_histogram"], "expected ratio histogram bins"

    scoped = client.get("/api/performance?project=-Users-test-projA")
    assert scoped.status_code == 200
    models = [r["model_id"] for r in scoped.json()["by_model"]]
    assert len(models) == 1 and "sonnet" in models[0]


def test_sessions_list_has_perf_columns(tmp_path: Path) -> None:
    """get_sessions_list rows carry the precomputed timing/throughput rollups
    (avg_tps, total_idle_ms, total_active_ms, peak_context_ratio)."""
    session_id = "sess-perf"
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
            "message": {"role": "user", "content": "go"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req1",
            "timestamp": ts(2),  # duration = 2s → tps = 200/2 = 100
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",  # 200k window
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 200_000,  # context_tokens=200k → ratio=1.0
                    "output_tokens": 200,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
                "content": [{"type": "text", "text": "answer"}],
            },
        },
        {
            "uuid": "u1",
            "parentUuid": "a1",
            "type": "user",
            "timestamp": ts(22),  # idle = 20s; active = u0→a1 = 2s
            "sessionId": session_id,
            "message": {"role": "user", "content": "next"},
        },
    ]
    projects = tmp_path / "projects"
    pdir = projects / "-Users-test-proj"
    pdir.mkdir(parents=True, exist_ok=True)
    jsonl = pdir / f"{session_id}.jsonl"
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
    db.cache.rebuild_aggregates()  # populates the sessions table + timing rollups

    sessions = db.get_sessions_list()
    row = next(s for s in sessions if s["session_id"] == session_id)
    assert {"avg_tps", "total_idle_ms", "total_active_ms", "peak_context_ratio"} <= set(row)
    assert row["avg_tps"] == pytest.approx(100.0, abs=1.0)
    assert row["total_idle_ms"] == pytest.approx(20_000, abs=50)
    assert row["total_active_ms"] == pytest.approx(2_000, abs=50)
    assert row["peak_context_ratio"] == pytest.approx(1.0, abs=0.001)
