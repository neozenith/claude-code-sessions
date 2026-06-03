"""CR5 claims API — explorer rollups, session claims, reverse provenance, coverage.

Real SQLiteDatabase seeded through the real claims path (extract → set_union →
failures), only the model boundary faked, then driven via FastAPI TestClient.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.database import SQLiteDatabase
from claude_code_sessions.database.sqlite.claims import (
    ensure_claims_schema,
    extract_session_claims,
    rollup_failures,
    set_union_rollup,
)
from claude_code_sessions.main import app
from claude_code_sessions.project_resolver import ProjectResolver

PID = "-Users-dev-play-claude-code-sessions"
PPATH = "/Users/dev/play/claude-code-sessions"
SCOPE = "play/claude-code-sessions"
MONTH = "2026-01-01"


class _FakeEngine:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def extract(self, model: str, prompt: str) -> str:
        return self.reply


def _seed(conn: sqlite3.Connection, sid: str, texts: list[str]) -> None:
    cur = conn.execute(
        """INSERT INTO source_files (filepath, mtime, size_bytes, line_count, last_ingested_at,
               project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"f-{sid}", PID, sid),
    )
    sf = cur.lastrowid
    for i, text in enumerate(texts):
        conn.execute(
            """INSERT INTO events (event_type, msg_kind, message_content, timestamp, session_id,
                   project_id, source_file_id, line_number, raw_json)
               VALUES ('user', 'human', ?, ?, ?, ?, ?, ?, '')""",
            (text, f"2026-01-15T00:0{i}:00Z", sid, PID, sf, i + 1),
        )
    conn.commit()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    projects = tmp_path / "projects"
    (projects / PID).mkdir(parents=True)
    (projects / PID / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": PPATH}]}), encoding="utf-8"
    )
    db = SQLiteDatabase(
        local_projects_path=projects, home_projects_path=projects, db_path=tmp_path / "cache.db"
    )
    conn = db.cache.conn
    ensure_claims_schema(conn)
    _seed(conn, "good1", ["a"])
    _seed(conn, "good2", ["b"])
    _seed(conn, "bad1", ["c"])
    ok1 = json.dumps({"tasks": ["refactor makefile", "add tests"], "patterns": [],
                      "decisions_values": [], "learnings": []})
    ok2 = json.dumps({"tasks": ["refactor makefile"], "patterns": [], "decisions_values": [],
                      "learnings": []})
    extract_session_claims(conn, PID, "good1", _FakeEngine(ok1), "M")
    extract_session_claims(conn, PID, "good2", _FakeEngine(ok2), "M")
    with pytest.raises(ValueError):
        extract_session_claims(conn, PID, "bad1", _FakeEngine("not json"), "M")
    resolver = ProjectResolver(projects)
    set_union_rollup(conn, "M", "month", resolver)
    rollup_failures(conn, "M", "month", resolver)
    monkeypatch.setattr(app.state, "db", db)
    return TestClient(app)


def test_claim_rollup_ranks_by_count(client: TestClient) -> None:
    resp = client.get("/api/claims/scope", params={"path": SCOPE, "grain": "month",
                                                    "bucket": MONTH, "model": "M"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "summarised"
    tasks = {c["claim"]: c["count"] for c in body["lenses"]["tasks"]}
    assert tasks["refactor makefile"] == 2  # salience across both sessions
    assert tasks["add tests"] == 1
    assert body["failure_count"] == 1  # the parallel failure stream surfaces here


def test_session_claims_and_memberships(client: TestClient) -> None:
    claims = client.get(f"/api/claims/session/{PID}/good1", params={"model": "M"}).json()
    assert "refactor makefile" in claims["lenses"]["tasks"]
    mem = client.get(f"/api/claims/session/{PID}/good1/memberships", params={"model": "M"}).json()
    scopes = {m["scope_path"] for m in mem}
    assert SCOPE in scopes and "" in scopes  # contributes to project AND root rollups


def test_coverage_counts(client: TestClient) -> None:
    cov = client.get("/api/claims/coverage", params={"model": "M"}).json()
    assert cov["overall"]["summarised"] == 2
    assert cov["overall"]["failed"] == 1
    assert cov["overall"]["total"] == 3
    assert cov["overall"]["pending"] == 0


def test_bad_session_records_failure_payload(client: TestClient) -> None:
    body = client.get(f"/api/claims/session/{PID}/bad1", params={"model": "M"}).json()
    assert body["failure"] is not None
    assert "no balanced JSON" in body["failure"]["reason"]


def test_models_detail_lists_data_model(client: TestClient) -> None:
    detail = client.get("/api/claims/models/detail").json()
    by_model = {d["model"]: d["has_claims"] for d in detail}
    assert by_model.get("M") is True  # the seeded model has claim data


def test_coverage_pivot_marks_done_and_pending(client: TestClient) -> None:
    piv = client.get("/api/claims/coverage-pivot", params={"model": "M", "grain": "month"}).json()
    assert SCOPE in piv["scopes"] and "" in piv["scopes"]  # project + root rows
    assert MONTH in piv["buckets"]
    by_key = {(c["scope_path"], c["bucket"]): c for c in piv["cells"]}
    assert by_key[(SCOPE, MONTH)]["status"] == "done"  # has committed claims
    assert by_key[(SCOPE, MONTH)]["claims"] > 0


def test_coverage_rows_carry_domain(client: TestClient) -> None:
    cov = client.get("/api/claims/coverage", params={"model": "M"}).json()
    row = next(p for p in cov["projects"] if p["project_id"] == PID)
    assert row["domain"] == "play"  # derived from resolved scope play/claude-code-sessions
    assert row["scope_path"] == SCOPE


def test_coverage_scoped_by_page_filter(client: TestClient) -> None:
    # In-scope: the explorer's current scope (project's own path) includes the project.
    inn = client.get("/api/claims/coverage", params={"model": "M", "scope": SCOPE}).json()
    assert any(p["project_id"] == PID for p in inn["projects"])
    # Out-of-scope: a sibling domain excludes it entirely (page filter drives the table).
    out = client.get("/api/claims/coverage", params={"model": "M", "scope": "work"}).json()
    assert out["projects"] == []


def test_coverage_pivot_scoped_to_subtree(client: TestClient) -> None:
    # Root: full trie incl. root, domain and project scopes.
    root = client.get("/api/claims/coverage-pivot", params={"model": "M", "grain": "month"}).json()
    assert {"", "play", SCOPE} <= set(root["scopes"])
    # Scoped to the project: only that leaf scope (subtree of itself).
    leaf = client.get(
        "/api/claims/coverage-pivot", params={"model": "M", "grain": "month", "scope": SCOPE}
    ).json()
    assert leaf["scopes"] == [SCOPE]
    # Sibling domain: the play sessions are outside it → empty.
    work = client.get(
        "/api/claims/coverage-pivot", params={"model": "M", "grain": "month", "scope": "work"}
    ).json()
    assert work["scopes"] == []


def test_scope_of_project_resolves_scope_for_hard_pin(client: TestClient) -> None:
    """The global Project filter hard-pin resolves a project_id to its scope_path."""
    resp = client.get("/api/claims/scope/of-project", params={"project_id": PID})
    assert resp.status_code == 200
    assert resp.json()["scope_path"] == SCOPE


# --- windowed cross-bucket aggregate + days filter (the "show all claims" default) ---


def _seed_at(conn: sqlite3.Connection, sid: str, text: str, ts: str) -> None:
    cur = conn.execute(
        """INSERT INTO source_files (filepath, mtime, size_bytes, line_count, last_ingested_at,
               project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"f-{sid}", PID, sid),
    )
    sf = cur.lastrowid
    conn.execute(
        """INSERT INTO events (event_type, msg_kind, message_content, timestamp, session_id,
               project_id, source_file_id, line_number, raw_json)
           VALUES ('user', 'human', ?, ?, ?, ?, ?, 1, '')""",
        (text, ts, sid, PID, sf),
    )
    conn.commit()


@pytest.fixture
def two_month_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str, str]:
    """A DB with the SAME claim raised in a recent month and an old month, so the
    set-union aggregate spans buckets and the days window can exclude the old one.
    Timestamps are relative to *now* so the window assertions are date-stable."""
    now = datetime.now(UTC)
    recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old = (now - timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent_bucket = (now - timedelta(days=1)).strftime("%Y-%m-01")

    projects = tmp_path / "projects"
    (projects / PID).mkdir(parents=True)
    (projects / PID / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": PPATH}]}), encoding="utf-8"
    )
    db = SQLiteDatabase(
        local_projects_path=projects, home_projects_path=projects, db_path=tmp_path / "cache.db"
    )
    conn = db.cache.conn
    ensure_claims_schema(conn)
    _seed_at(conn, "recent1", "shared task", recent)
    _seed_at(conn, "old1", "shared task", old)
    shared = json.dumps({"tasks": ["shared task"], "patterns": [], "decisions_values": [],
                         "learnings": []})
    extract_session_claims(conn, PID, "recent1", _FakeEngine(shared), "M")
    extract_session_claims(conn, PID, "old1", _FakeEngine(shared), "M")
    set_union_rollup(conn, "M", "month", ProjectResolver(projects))
    monkeypatch.setattr(app.state, "db", db)
    return TestClient(app), recent_bucket, SCOPE


def test_rollup_aggregates_all_buckets_when_no_bucket(
    two_month_db: tuple[TestClient, str, str],
) -> None:
    client, _recent_bucket, scope = two_month_db
    # No bucket, no window → all claims at this grain, unioned across BOTH months.
    body = client.get(
        "/api/claims/scope", params={"path": scope, "grain": "month", "bucket": "", "model": "M"}
    ).json()
    tasks = {c["claim"]: c["count"] for c in body["lenses"]["tasks"]}
    assert tasks["shared task"] == 2  # recent1 + old1 unioned across buckets


def test_days_window_excludes_old_bucket_in_aggregate(
    two_month_db: tuple[TestClient, str, str],
) -> None:
    client, _recent_bucket, scope = two_month_db
    # Last 30 days → only the recent month contributes → count drops to 1.
    body = client.get(
        "/api/claims/scope",
        params={"path": scope, "grain": "month", "bucket": "", "model": "M", "days": 30},
    ).json()
    tasks = {c["claim"]: c["count"] for c in body["lenses"]["tasks"]}
    assert tasks["shared task"] == 1  # old month is outside the window


def test_explicit_bucket_drilldown_ignores_window(
    two_month_db: tuple[TestClient, str, str],
) -> None:
    client, recent_bucket, scope = two_month_db
    # A specific bucket is a deliberate drill-down: it returns that bucket regardless
    # of the days window.
    body = client.get(
        "/api/claims/scope",
        params={"path": scope, "grain": "month", "bucket": recent_bucket, "model": "M", "days": 1},
    ).json()
    assert body["status"] == "summarised"
    assert any(c["claim"] == "shared task" for c in body["lenses"]["tasks"])


def test_buckets_selector_respects_days_window(
    two_month_db: tuple[TestClient, str, str],
) -> None:
    client, recent_bucket, scope = two_month_db
    all_buckets = client.get(
        "/api/claims/buckets", params={"path": scope, "grain": "month", "model": "M"}
    ).json()
    assert len(all_buckets) == 2  # both months present without a window
    windowed = client.get(
        "/api/claims/buckets", params={"path": scope, "grain": "month", "model": "M", "days": 30}
    ).json()
    assert [b["bucket"] for b in windowed] == [recent_bucket]  # old month filtered out


def test_coverage_respects_days_window(
    two_month_db: tuple[TestClient, str, str],
) -> None:
    client, _recent_bucket, _scope = two_month_db
    full = client.get("/api/claims/coverage", params={"model": "M"}).json()
    assert full["overall"]["total"] == 2 and full["overall"]["summarised"] == 2
    windowed = client.get("/api/claims/coverage", params={"model": "M", "days": 30}).json()
    # Only the recent session's activity falls in the window.
    assert windowed["overall"]["total"] == 1 and windowed["overall"]["summarised"] == 1


# --- variable mixed-depth hierarchy within ONE domain (play flat leaf + deep branch) ---


@pytest.fixture
def mixed_depth_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A `play` domain that is variable-depth: a flat depth-2 leaf (`play/proj-a`)
    AND a depth-3 sub-branch (`play/gh-webpages/proj-b`). Both raise the SAME claim,
    so the `play` roll-up must union across depths while `play/gh-webpages` holds
    only its child. Mirrors the real shape after adding play/gh-webpages/<project>."""
    projects = tmp_path / "projects"
    specs = {
        "-Users-dev-play-proj-a": "/Users/dev/play/proj-a",
        "-Users-dev-play-gh-webpages-proj-b": "/Users/dev/play/gh-webpages/proj-b",
    }
    for pid, ppath in specs.items():
        (projects / pid).mkdir(parents=True)
        (projects / pid / "sessions-index.json").write_text(
            json.dumps({"version": 1, "entries": [{"projectPath": ppath}]}), encoding="utf-8"
        )
    db = SQLiteDatabase(
        local_projects_path=projects, home_projects_path=projects, db_path=tmp_path / "cache.db"
    )
    conn = db.cache.conn
    ensure_claims_schema(conn)
    shared = json.dumps({"tasks": ["shared task"], "patterns": [], "decisions_values": [],
                         "learnings": []})
    for pid, sid in [("-Users-dev-play-proj-a", "a1"),
                     ("-Users-dev-play-gh-webpages-proj-b", "b1")]:
        cur = conn.execute(
            """INSERT INTO source_files (filepath, mtime, size_bytes, line_count,
                   last_ingested_at, project_id, session_id, file_type)
               VALUES (?, 0, 0, 0, '2026-05-01T00:00:00Z', ?, ?, 'main_session')""",
            (f"f-{sid}", pid, sid),
        )
        conn.execute(
            """INSERT INTO events (event_type, msg_kind, message_content, timestamp,
                   session_id, project_id, source_file_id, line_number, raw_json)
               VALUES ('user', 'human', 't', '2026-05-15T00:00:00Z', ?, ?, ?, 1, '')""",
            (sid, pid, cur.lastrowid),
        )
        conn.commit()
        extract_session_claims(conn, pid, sid, _FakeEngine(shared), "M")
    set_union_rollup(conn, "M", "month", ProjectResolver(projects))
    monkeypatch.setattr(app.state, "db", db)
    return TestClient(app)


def test_deep_project_resolves_to_full_depth_scope(mixed_depth_db: TestClient) -> None:
    scope = mixed_depth_db.get(
        "/api/claims/scope/of-project", params={"project_id": "-Users-dev-play-gh-webpages-proj-b"}
    ).json()
    assert scope["scope_path"] == "play/gh-webpages/proj-b"  # depth-3, not flattened
    assert scope["ancestor_scopes"] == ["", "play", "play/gh-webpages", "play/gh-webpages/proj-b"]


def test_children_of_domain_mix_leaf_and_subdomain(mixed_depth_db: TestClient) -> None:
    # `play` has BOTH a leaf project and a sub-domain as immediate children.
    play_children = {
        c["scope_path"]
        for c in mixed_depth_db.get("/api/claims/scope/children", params={"path": "play"}).json()
    }
    assert play_children == {"play/proj-a", "play/gh-webpages"}
    # …and the sub-domain has its own deeper child.
    sub = {
        c["scope_path"]
        for c in mixed_depth_db.get(
            "/api/claims/scope/children", params={"path": "play/gh-webpages"}
        ).json()
    }
    assert sub == {"play/gh-webpages/proj-b"}


def test_rollup_unions_across_depths_at_domain_scope(mixed_depth_db: TestClient) -> None:
    # The domain roll-up unions the flat leaf AND the deep-branch project.
    play = mixed_depth_db.get(
        "/api/claims/scope", params={"path": "play", "grain": "month", "bucket": "", "model": "M"}
    ).json()
    assert {c["claim"]: c["count"] for c in play["lenses"]["tasks"]}["shared task"] == 2
    # The intermediate sub-domain scope aggregates only its descendant.
    sub = mixed_depth_db.get(
        "/api/claims/scope",
        params={"path": "play/gh-webpages", "grain": "month", "bucket": "", "model": "M"},
    ).json()
    assert {c["claim"]: c["count"] for c in sub["lenses"]["tasks"]}["shared task"] == 1


def test_coverage_pivot_includes_intermediate_subdomain_scope(mixed_depth_db: TestClient) -> None:
    piv = mixed_depth_db.get(
        "/api/claims/coverage-pivot", params={"model": "M", "grain": "month"}
    ).json()
    # The variable-depth trie surfaces root, domain, sub-domain, and both leaves.
    assert {"", "play", "play/gh-webpages", "play/proj-a", "play/gh-webpages/proj-b"} <= set(
        piv["scopes"]
    )
