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


# NOTE: the abstractive `/api/summaries/scope` scope-explorer route was retired when
# the Summaries page was consolidated into the Claims Explorer (CR5). Its db method
# (`get_rollup_summary`) is retained (frozen, ADR3.2) but no longer HTTP-surfaced, so
# the former route tests were removed. The shared children/of-project resolvers now
# live under `/api/claims/scope/*` (see test_claims_api.py).


def _add_project_with_event(db: SQLiteDatabase, tmp_path: Path, pid: str, project_path: str) -> None:
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}),
        encoding="utf-8",
    )
    conn = db.cache.conn
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at, project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, 's', 'main_session')""",
        (f"f-{pid}", pid),
    )
    sf = cur.lastrowid
    conn.execute(
        """INSERT INTO events
               (event_type, msg_kind, message_content, timestamp, session_id, project_id,
                source_file_id, line_number, raw_json)
           VALUES ('user', 'human', 't', '2026-01-01T00:01:00Z', 's', ?, ?, 1, '')""",
        (pid, sf),
    )
    conn.commit()


def test_scope_children_returns_next_trie_level(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Children listing returns only the immediate next trie level, and a project
    filter narrows the set."""
    projects = tmp_path / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    db = SQLiteDatabase(
        local_projects_path=projects, home_projects_path=projects, db_path=tmp_path / "cache.db"
    )
    _add_project_with_event(db, tmp_path, "-Users-dev-clients-acme-app", "/Users/dev/clients/acme/app")
    _add_project_with_event(db, tmp_path, "-Users-dev-clients-beta", "/Users/dev/clients/beta")
    _add_project_with_event(db, tmp_path, "-Users-dev-play-foo", "/Users/dev/play/foo")
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    # Immediate children of 'clients' — not the depth-3 grandchild clients/acme/app.
    resp = client.get("/api/claims/scope/children", params={"path": "clients"})
    assert resp.status_code == 200
    assert {c["scope_path"] for c in resp.json()} == {"clients/acme", "clients/beta"}

    # Project filter narrows the root's children to just that project's domain.
    resp2 = client.get(
        "/api/claims/scope/children",
        params={"path": "", "project": "-Users-dev-play-foo"},
    )
    assert resp2.status_code == 200
    assert {c["scope_path"] for c in resp2.json()} == {"play"}


def test_variants_lists_available_strategy_model_pairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/summaries/variants lists exactly the distinct (strategy, model)
    pairs present in the roll-up table."""
    db = _fixture_db(tmp_path)
    _seed_rollup(db, "play/foo", strategy="strict", model="model-a")
    _seed_rollup(db, "clients/acme", strategy="reground", model="model-b")
    monkeypatch.setattr(app.state, "db", db)
    client = TestClient(app)

    resp = client.get("/api/summaries/variants")
    assert resp.status_code == 200
    pairs = {(v["strategy"], v["model"]) for v in resp.json()}
    assert pairs == {("strict", "model-a"), ("reground", "model-b")}
