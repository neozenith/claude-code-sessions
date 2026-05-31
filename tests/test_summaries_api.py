"""Tests for the summaries query API (G7).

Driven via FastAPI's TestClient against a fixture-backed app — ``app.state.db``
is swapped to a tmp-cache ``SQLiteDatabase`` seeded directly with summary rows
(summarisation is a manual, ingest-decoupled pass, so the real cache has none).
"""

from __future__ import annotations

import json
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


def _fixture_db_with_project(tmp_path: Path, pid: str, project_path: str) -> SQLiteDatabase:
    """A fixture DB whose projects dir makes ``scope_path_of(pid)`` a valid scope."""
    projects = tmp_path / "projects"
    pdir = projects / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}),
        encoding="utf-8",
    )
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


def _seed_rollup(
    db: SQLiteDatabase,
    scope_path: str,
    *,
    strategy: str = "stub",
    model: str = "model-a",
    grain: str = "day",
    bucket: str = "2026-01-01",
) -> None:
    depth = 0 if scope_path == "" else len(scope_path.split("/"))
    db.cache.conn.execute(
        """INSERT INTO rollup_summaries
               (strategy, model, scope_path, scope_depth, time_granularity, time_bucket,
                task_summary, patterns, decisions_values, child_count, source_hash, generated_at)
           VALUES (?, ?, ?, ?, ?, ?, 'RT', 'RP', 'RD', 3, 'sh', '2026-01-01T00:00:00Z')""",
        (strategy, model, scope_path, depth, grain, bucket),
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


def test_scope_summary_returns_rollup_for_grain_and_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/summaries/scope returns the rollup matching path+grain+bucket."""
    db = _fixture_db(tmp_path)
    _seed_rollup(db, "clients/acme/app", strategy="stub", model="model-a")
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    resp = client.get(
        "/api/summaries/scope",
        params={
            "path": "clients/acme/app",
            "grain": "day",
            "bucket": "2026-01-01",
            "strategy": "stub",
            "model": "model-a",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "summarised"
    assert data["scope_path"] == "clients/acme/app"
    assert data["scope_depth"] == 3
    assert data["strategy"] == "stub"
    assert data["lenses"]["task_summary"] == "RT"
    assert data["child_count"] == 3


def test_scope_summary_selects_matching_strategy_model_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When variants coexist for one scope/grain/bucket, the requested
    strategy+model selects the right row (ADR7.2)."""
    db = _fixture_db(tmp_path)
    _seed_rollup(db, "play/foo", strategy="strict", model="model-a")
    _seed_rollup(db, "play/foo", strategy="reground", model="model-b")
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    for strat, mdl in [("strict", "model-a"), ("reground", "model-b")]:
        resp = client.get(
            "/api/summaries/scope",
            params={"path": "play/foo", "grain": "day", "bucket": "2026-01-01", "strategy": strat, "model": mdl},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "summarised"
        assert data["strategy"] == strat
        assert data["model"] == mdl


def test_unsummarised_scope_returns_not_summarised_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid scope (a real ancestor_scopes path) with no rollup row returns
    200 {status:"not_summarised"} — not a fabricated summary (ADR7.1)."""
    db = _fixture_db_with_project(tmp_path, "-Users-dev-play-foo", "/Users/dev/play/foo")
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    resp = client.get(
        "/api/summaries/scope",
        params={"path": "play/foo", "grain": "day", "bucket": "2026-01-01", "strategy": "strict", "model": "model-a"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "not_summarised"}


def test_unknown_scope_returns_404(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scope_path absent from the G1 hierarchy (and with no rollup) returns 404
    — distinguishing 'missing' from 'not yet computed' (ADR7.1)."""
    db = _fixture_db(tmp_path)  # an unresolvable project dir, no rollups
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    resp = client.get(
        "/api/summaries/scope",
        params={
            "path": "no-such-domain/nope",
            "grain": "day",
            "bucket": "2026-01-01",
            "strategy": "strict",
            "model": "model-a",
        },
    )
    assert resp.status_code == 404
