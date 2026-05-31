"""Correctness tests for the flat merger (G6).

Flat re-summarises every descendant ``session_summaries`` row under a scope
directly (no intermediate child-rollup tier), so an ancestor's ``child_count``
counts descendant *sessions*, not child *scopes*. Tests drive the real
``roll_up_scopes`` with a recording fake engine over a tiny fixture cache.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from claude_code_sessions.database.sqlite.merge import SummaryMergerFlat, get_merger
from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.database.sqlite.summaries import roll_up_scopes
from claude_code_sessions.project_resolver import ProjectResolver


class RecordingEngine:
    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[tuple[str, str]] = []

    def summarise(self, model: str, prompt: str) -> str:
        self.calls.append((model, prompt))
        return self._output


def _seed_depth3_two_sessions(conn: sqlite3.Connection, tmp_path: Path) -> ProjectResolver:
    """One depth-3 project (clients/acme/app) with two summarised sessions."""
    pid = "-Users-dev-clients-acme-app"
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": "/Users/dev/clients/acme/app"}]}),
        encoding="utf-8",
    )
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at, project_id, session_id, file_type)
           VALUES ('f', 0, 0, 0, '2026-01-01T00:00:00Z', ?, 's1', 'main_session')""",
        (pid,),
    )
    sf = cur.lastrowid
    for sid, ch in [("s1", "h1"), ("s2", "h2")]:
        conn.execute(
            """INSERT INTO events
                   (event_type, msg_kind, message_content, timestamp, session_id, project_id,
                    source_file_id, line_number, raw_json)
               VALUES ('user', 'human', ?, '2026-01-01T00:01:00Z', ?, ?, ?, 1, '')""",
            (f"text {sid}", sid, pid, sf),
        )
        conn.execute(
            """INSERT INTO session_summaries
                   (project_id, session_id, model, content_hash, task_summary, patterns,
                    decisions_values, generated_at, human_event_count)
               VALUES (?, ?, 'model-a', ?, 'CT', 'CP', 'CD', '2026-01-01T00:00:00Z', 1)""",
            (pid, sid, ch),
        )
    conn.commit()
    return ProjectResolver(tmp_path / "projects")


def test_flat_builds_from_raw_descendant_sessions(tmp_path: Path) -> None:
    """Flat builds an ancestor scope directly from raw descendant session
    summaries — its child_count is the descendant session count (2), not the
    single child scope a child-rollup strategy would see."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    resolver = _seed_depth3_two_sessions(conn, tmp_path)

    engine = RecordingEngine(
        json.dumps({"task_summary": "FLAT_task", "patterns": "FLAT_pat", "decisions_values": "FLAT_dec"})
    )
    roll_up_scopes(conn, engine, "flat", "model-a", "day", resolver=resolver)

    clients = conn.execute(
        "SELECT * FROM rollup_summaries WHERE scope_path = 'clients'"
    ).fetchone()
    assert clients is not None
    assert clients["strategy"] == "flat"
    assert clients["child_count"] == 2  # two descendant sessions, not one child scope
    assert clients["task_summary"] == "FLAT_task"  # synthesised by the flat merger


def _seed_project_sessions(
    conn: sqlite3.Connection, projects_dir: Path, pid: str, project_path: str, session_ids: list[str]
) -> None:
    pdir = projects_dir / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}),
        encoding="utf-8",
    )
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at, project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"f-{pid}", pid, session_ids[0]),
    )
    sf = cur.lastrowid
    for sid in session_ids:
        conn.execute(
            """INSERT INTO events
                   (event_type, msg_kind, message_content, timestamp, session_id, project_id,
                    source_file_id, line_number, raw_json)
               VALUES ('user', 'human', ?, '2026-01-01T00:01:00Z', ?, ?, ?, 1, '')""",
            (f"text {sid}", sid, pid, sf),
        )
        conn.execute(
            """INSERT INTO session_summaries
                   (project_id, session_id, model, content_hash, task_summary, patterns,
                    decisions_values, generated_at, human_event_count)
               VALUES (?, ?, 'model-a', ?, 'CT', 'CP', 'CD', '2026-01-01T00:00:00Z', 1)""",
            (pid, sid, f"{pid}-{sid}"),
        )


def test_flat_child_count_is_descendant_sessions(tmp_path: Path) -> None:
    """A flat ancestor's child_count is the total descendant sessions (3 here),
    not the number of direct child scopes (2)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    projects = tmp_path / "projects"
    _seed_project_sessions(conn, projects, "-Users-dev-clients-acme", "/Users/dev/clients/acme", ["a1", "a2"])
    _seed_project_sessions(conn, projects, "-Users-dev-clients-beta", "/Users/dev/clients/beta", ["b1"])
    conn.commit()
    resolver = ProjectResolver(projects)

    engine = RecordingEngine(
        json.dumps({"task_summary": "m", "patterns": "m", "decisions_values": "m"})
    )
    roll_up_scopes(conn, engine, "flat", "model-a", "day", resolver=resolver)

    clients = conn.execute("SELECT * FROM rollup_summaries WHERE scope_path = 'clients'").fetchone()
    assert clients["child_count"] == 3  # a1 + a2 + b1, not the 2 child scopes


def test_flat_flag_drives_raw_session_path(tmp_path: Path) -> None:
    """`get_merger('flat')` is SummaryMergerFlat; the driver writes strategy='flat'
    rows via the raw-session path (an intermediate scope with one child scope
    still counts its 2 descendant sessions, proving raw-session gathering)."""
    assert isinstance(get_merger("flat"), SummaryMergerFlat)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    resolver = _seed_depth3_two_sessions(conn, tmp_path)  # clients/acme/app with s1, s2

    engine = RecordingEngine(
        json.dumps({"task_summary": "m", "patterns": "m", "decisions_values": "m"})
    )
    roll_up_scopes(conn, engine, "flat", "model-a", "day", resolver=resolver)

    rows = conn.execute("SELECT scope_path, strategy, child_count FROM rollup_summaries").fetchall()
    assert rows
    assert all(r["strategy"] == "flat" for r in rows)
    # clients/acme has exactly one child scope (clients/acme/app) but 2 descendant
    # sessions — child_count=2 proves the raw-session path, not child-rollup gathering.
    mid = conn.execute(
        "SELECT child_count FROM rollup_summaries WHERE scope_path = 'clients/acme'"
    ).fetchone()
    assert mid["child_count"] == 2
