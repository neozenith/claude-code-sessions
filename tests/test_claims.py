"""CR5 extractive set-union: L1 claim extraction + L2 set-union rollup.

Real behaviour against an in-memory cache; only the model boundary (the GGUF) is a
canned fake, exactly like the abstractive bench tests.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from claude_code_sessions.database.sqlite.claims import (
    dedup_claims,
    ensure_claims_schema,
    extract_session_claims,
    rollup_failures,
    set_union_rollup,
)
from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.project_resolver import ProjectResolver

DOGFOOD_PID = "-Users-dev-play-claude-code-sessions"
DOGFOOD_PATH = "/Users/dev/play/claude-code-sessions"


def _cache() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    ensure_claims_schema(conn)
    return conn


def _index(tmp_path: Path, pid: str, project_path: str) -> None:
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}), encoding="utf-8"
    )


def _seed_session(conn: sqlite3.Connection, pid: str, sid: str, texts: list[str]) -> None:
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"f-{sid}", pid, sid),
    )
    sf = cur.lastrowid
    for i, text in enumerate(texts):
        conn.execute(
            """INSERT INTO events
                   (event_type, msg_kind, message_content, timestamp, session_id,
                    project_id, source_file_id, line_number, raw_json)
               VALUES ('user', 'human', ?, ?, ?, ?, ?, ?, '')""",
            (text, f"2026-01-15T00:0{i}:00Z", sid, pid, sf, i + 1),
        )
    conn.commit()


class _FakeEngine:
    """Canned ClaimsEngine — returns fixed list-JSON regardless of prompt."""

    def __init__(self, reply: str) -> None:
        self.reply = reply

    def extract(self, model: str, prompt: str) -> str:
        return self.reply


# --- dedup (pure) ---------------------------------------------------------


def test_dedup_exact_counts_distinct_sessions() -> None:
    clusters = dedup_claims(
        [("Refactor app.py", "s1"), ("refactor app.py", "s2"), ("Refactor app.py", "s1")]
    )
    assert len(clusters) == 1
    assert clusters[0].count == 2  # distinct sessions s1,s2 (the repeat from s1 doesn't double)
    assert clusters[0].sessions == {"s1", "s2"}


def test_dedup_cosine_merges_paraphrases() -> None:
    emb = {"add a flag": [1.0, 0.0], "add an option": [0.99, 0.14], "delete the cache": [0.0, 1.0]}
    clusters = dedup_claims(
        [("add a flag", "s1"), ("add an option", "s2"), ("delete the cache", "s3")],
        embed=lambda t: emb[t],
        cosine_threshold=0.9,
    )
    assert len(clusters) == 2  # the two paraphrases merged, 'delete' stayed separate
    assert clusters[0].count == 2 and clusters[0].sessions == {"s1", "s2"}


# --- L1 extraction --------------------------------------------------------


def test_extract_writes_one_row_per_claim_empty_lens_no_rows() -> None:
    conn = _cache()
    _seed_session(conn, DOGFOOD_PID, "s1", ["build a thing"])
    reply = json.dumps(
        {"tasks": ["build a thing", "wire the cli"], "patterns": ["pluggable engine"],
         "decisions_values": [], "learnings": []}
    )
    n = extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine(reply), "M")
    assert n == 3  # 2 tasks + 1 pattern + 0 decisions
    lenses = [
        r["lens"]
        for r in conn.execute("SELECT lens FROM session_claims WHERE model='M'").fetchall()
    ]
    assert lenses.count("tasks") == 2
    assert lenses.count("patterns") == 1
    assert "decisions_values" not in lenses  # empty lens writes NO rows
    # content-hash guard: re-running unchanged session is a no-op
    assert extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine(reply), "M") == 0


# --- L2 set-union rollup --------------------------------------------------


def test_set_union_rollup_counts_and_provenance(tmp_path: Path) -> None:
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    _seed_session(conn, DOGFOOD_PID, "s1", ["one"])
    _seed_session(conn, DOGFOOD_PID, "s2", ["two"])
    extract_session_claims(
        conn, DOGFOOD_PID, "s1",
        _FakeEngine(json.dumps({"tasks": ["refactor makefile", "add tests"], "patterns": [],
                                "decisions_values": [], "learnings": []})), "M",
    )
    extract_session_claims(
        conn, DOGFOOD_PID, "s2",
        _FakeEngine(json.dumps({"tasks": ["refactor makefile"], "patterns": [],
                                "decisions_values": [], "learnings": []})), "M",
    )
    resolver = ProjectResolver(tmp_path / "projects")
    written = set_union_rollup(conn, "M", "month", resolver)
    assert written > 0

    proj = conn.execute(
        """SELECT claim, count, source_session_ids FROM rollup_claims
           WHERE model='M' AND scope_path='play/claude-code-sessions' AND lens='tasks'""",
    ).fetchall()
    counts = {r["claim"]: r["count"] for r in proj}
    assert counts["refactor makefile"] == 2  # both sessions → salience 2
    assert counts["add tests"] == 1
    prov_json = next(r["source_session_ids"] for r in proj if r["claim"] == "refactor makefile")
    assert set(json.loads(prov_json)) == {"s1", "s2"}
    # the union propagates to the root scope too
    root = conn.execute(
        """SELECT count FROM rollup_claims WHERE model='M' AND scope_path='' AND lens='tasks'
           AND claim='refactor makefile'"""
    ).fetchone()
    assert root["count"] == 2


# --- failure stream (parallel) --------------------------------------------


def test_l1_failure_recorded_as_data_and_reraised() -> None:
    conn = _cache()
    _seed_session(conn, DOGFOOD_PID, "s1", ["hi there"])
    with pytest.raises(ValueError, match="no balanced JSON"):
        extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine("no json at all"), "M")
    row = conn.execute(
        "SELECT reason, raw_excerpt FROM session_claim_failures WHERE session_id='s1' AND model='M'"
    ).fetchone()
    assert row is not None  # recorded, not silently lost
    assert "no balanced JSON" in row["reason"]
    n_claims = conn.execute(
        "SELECT COUNT(*) FROM session_claims WHERE session_id='s1'"
    ).fetchone()[0]
    assert n_claims == 0  # failure wrote no claims


def test_success_clears_prior_failure() -> None:
    conn = _cache()
    _seed_session(conn, DOGFOOD_PID, "s1", ["hi there"])
    with pytest.raises(ValueError):
        extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine("nope"), "M")
    ok = json.dumps({"tasks": ["do the thing"], "patterns": [], "decisions_values": [], "learnings": []})
    extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine(ok), "M")
    assert conn.execute(
        "SELECT COUNT(*) FROM session_claim_failures WHERE session_id='s1'"
    ).fetchone()[0] == 0
    n_claims = conn.execute(
        "SELECT COUNT(*) FROM session_claims WHERE session_id='s1'"
    ).fetchone()[0]
    assert n_claims == 1  # the retry succeeded and wrote claims


def test_rollup_failures_counts_per_scope(tmp_path: Path) -> None:
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    _seed_session(conn, DOGFOOD_PID, "s1", ["one"])
    _seed_session(conn, DOGFOOD_PID, "s2", ["two"])
    for sid in ("s1", "s2"):
        with pytest.raises(ValueError):
            extract_session_claims(conn, DOGFOOD_PID, sid, _FakeEngine("garbage out"), "M")
    resolver = ProjectResolver(tmp_path / "projects")
    assert rollup_failures(conn, "M", "month", resolver) > 0
    proj = conn.execute(
        """SELECT failure_count, source_session_ids FROM rollup_claim_failures
           WHERE model='M' AND scope_path='play/claude-code-sessions'"""
    ).fetchone()
    assert proj["failure_count"] == 2
    assert set(json.loads(proj["source_session_ids"])) == {"s1", "s2"}
    root = conn.execute(
        "SELECT failure_count FROM rollup_claim_failures WHERE model='M' AND scope_path=''"
    ).fetchone()
    assert root["failure_count"] == 2
