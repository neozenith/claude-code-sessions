"""Tests for the summaries query API (G7).

Driven via FastAPI's TestClient against a fixture-backed app — ``app.state.db``
is swapped to a tmp-cache ``SQLiteDatabase`` seeded directly with summary rows
(summarisation is a manual, ingest-decoupled pass, so the real cache has none).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.database import SQLiteDatabase
from claude_code_sessions.main import app


def _fixture_db(tmp_path: Path) -> SQLiteDatabase:
    projects = tmp_path / "projects"
    (projects / "-Users-test-proj").mkdir(parents=True, exist_ok=True)
    return SQLiteDatabase(
        local_projects_path=projects,
        home_projects_path=projects,
        db_path=tmp_path / "cache.db",
    )


def _seed_session_summary(db: SQLiteDatabase, project_id: str, session_id: str, model: str) -> None:
    db.cache.conn.execute(
        """INSERT INTO session_summaries
               (project_id, session_id, model, content_hash, task_summary, patterns,
                decisions_values, generated_at, human_event_count)
           VALUES (?, ?, ?, 'h', 'TASK_LENS', 'PATTERN_LENS', 'DECISION_LENS', '2026-01-01T00:00:00Z', 2)""",
        (project_id, session_id, model),
    )
    db.cache.conn.commit()


def test_session_summary_returns_three_lenses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/summaries/session/{pid}/{sid}?model= returns 200 with the three
    lenses for a summarised session."""
    db = _fixture_db(tmp_path)
    _seed_session_summary(db, "-Users-test-proj", "sess-1", "model-a")
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    resp = client.get("/api/summaries/session/-Users-test-proj/sess-1", params={"model": "model-a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "summarised"
    assert data["lenses"]["task_summary"] == "TASK_LENS"
    assert data["lenses"]["patterns"] == "PATTERN_LENS"
    assert data["lenses"]["decisions_values"] == "DECISION_LENS"
