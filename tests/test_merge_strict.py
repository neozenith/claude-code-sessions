"""Correctness tests for the strict bottom-up merger (G4).

The merger is exercised through its public ``merge`` with a recording fake
engine (a real class, not a mock) so the assertions are about observable
behaviour: what the synthesised ``Summary`` contains and what text reaches the
engine prompt.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from claude_code_sessions.database.sqlite.merge import (
    SourceExcerpts,
    Summary,
    SummaryMergerStrict,
)
from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.database.sqlite.summaries import roll_up_scopes
from claude_code_sessions.project_resolver import ProjectResolver


class RecordingEngine:
    """A real ``SummaryEngine`` returning canned text and recording its prompt."""

    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[tuple[str, str]] = []

    def summarise(self, model: str, prompt: str) -> str:
        self.calls.append((model, prompt))
        return self._output


def test_strict_merge_synthesises_children() -> None:
    """Strict merge synthesises one summary from two child summaries; the prompt
    carries the children's lens text and no raw source excerpts."""
    children = [
        Summary("CHILD_A_task", "CHILD_A_pat", "CHILD_A_dec"),
        Summary("CHILD_B_task", "CHILD_B_pat", "CHILD_B_dec"),
    ]
    engine = RecordingEngine(
        json.dumps(
            {"task_summary": "MERGED_task", "patterns": "MERGED_pat", "decisions_values": "MERGED_dec"}
        )
    )

    merger = SummaryMergerStrict()
    assert merger.name == "strict"
    assert merger.child_mode == "child_rollups"
    assert merger.wants_excerpts is False

    result = merger.merge(engine, "model-a", children, None)

    assert isinstance(result, Summary)
    assert result.task_summary == "MERGED_task"
    assert result.patterns == "MERGED_pat"
    assert result.decisions_values == "MERGED_dec"

    assert len(engine.calls) == 1
    prompt = engine.calls[0][1]
    for marker in (
        "CHILD_A_task",
        "CHILD_A_pat",
        "CHILD_A_dec",
        "CHILD_B_task",
        "CHILD_B_pat",
        "CHILD_B_dec",
    ):
        assert marker in prompt


def _seed_leaf_session_summary(conn: sqlite3.Connection, tmp_path: Path) -> ProjectResolver:
    """A one-project, one-session fixture cache + resolver for driver tests."""
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
    conn.execute(
        """INSERT INTO events
               (event_type, msg_kind, message_content, timestamp, session_id, project_id,
                source_file_id, line_number, raw_json)
           VALUES ('user', 'human', 't', '2026-01-01T00:01:00Z', 's1', ?, ?, 1, '')""",
        (pid, sf),
    )
    conn.execute(
        """INSERT INTO session_summaries
               (project_id, session_id, model, content_hash, task_summary, patterns,
                decisions_values, generated_at, human_event_count)
           VALUES (?, 's1', 'model-a', 'h', 'CT', 'CP', 'CD', '2026-01-01T00:00:00Z', 1)""",
        (pid,),
    )
    conn.commit()
    return ProjectResolver(tmp_path / "projects")


def test_strict_flag_drives_rollup(tmp_path: Path) -> None:
    """`strategy='strict'` selects SummaryMergerStrict; the driver writes rows
    carrying strategy='strict' whose content came from the strict merger."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    resolver = _seed_leaf_session_summary(conn, tmp_path)

    engine = RecordingEngine(
        json.dumps(
            {"task_summary": "STRICT_task", "patterns": "STRICT_pat", "decisions_values": "STRICT_dec"}
        )
    )
    roll_up_scopes(conn, engine, "strict", "model-a", "day", resolver=resolver)

    leaf = conn.execute(
        "SELECT * FROM rollup_summaries WHERE scope_path = 'clients/acme/app'"
    ).fetchone()
    assert leaf["strategy"] == "strict"
    assert leaf["task_summary"] == "STRICT_task"  # parsed from the strict merger's engine reply


def test_strict_ignores_excerpts() -> None:
    """Supplying excerpts produces the same prompt as None — strict never reads
    source text (summary-only contract)."""
    children = [Summary("a", "b", "c"), Summary("d", "e", "f")]
    merger = SummaryMergerStrict()
    assert merger.wants_excerpts is False

    reply = json.dumps({"task_summary": "x", "patterns": "y", "decisions_values": "z"})
    e_none = RecordingEngine(reply)
    merger.merge(e_none, "model-a", children, None)
    e_excerpts = RecordingEngine(reply)
    merger.merge(e_excerpts, "model-a", children, SourceExcerpts(["RAW_EXCERPT_ONE", "RAW_EXCERPT_TWO"]))

    assert e_none.calls[0][1] == e_excerpts.calls[0][1]
    assert "RAW_EXCERPT_ONE" not in e_excerpts.calls[0][1]
