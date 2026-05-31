"""Correctness tests for the re-grounding merger (G5).

Re-grounding folds a bounded sample of raw source excerpts into the merge
prompt so higher tiers stay faithful (Ou & Lapata, ACL 2025). Tests drive the
public ``merge`` with a recording fake engine and assert on the prompt.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from claude_code_sessions.database.sqlite.merge import (
    ExcerptCandidate,
    SourceExcerpts,
    Summary,
    SummaryMergerReGround,
    select_excerpts,
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


def test_reground_includes_excerpts_in_prompt() -> None:
    """Re-ground merge folds the supplied source excerpts into the prompt
    alongside the child summaries."""
    children = [Summary("CT1", "CP1", "CD1"), Summary("CT2", "CP2", "CD2")]
    excerpts = SourceExcerpts(["EXCERPT_MARKER_ONE", "EXCERPT_MARKER_TWO"])
    engine = RecordingEngine(
        json.dumps({"task_summary": "m", "patterns": "m", "decisions_values": "m"})
    )

    merger = SummaryMergerReGround()
    assert merger.name == "reground"
    assert merger.child_mode == "child_rollups"
    assert merger.wants_excerpts is True

    result = merger.merge(engine, "model-a", children, excerpts)

    assert isinstance(result, Summary)
    prompt = engine.calls[0][1]
    assert "CT1" in prompt and "CT2" in prompt  # child summaries present
    assert "EXCERPT_MARKER_ONE" in prompt and "EXCERPT_MARKER_TWO" in prompt  # re-grounded


def test_excerpt_selection_bounded_and_deterministic() -> None:
    """`select_excerpts` returns at most K, the top-K by (recency, then length),
    and the same inputs always yield the same selection (ADR5.1)."""
    candidates = [
        ExcerptCandidate("2026-01-05T00:00:00Z", "B_newest_longer"),  # newest, len 15
        ExcerptCandidate("2026-01-05T00:00:00Z", "A_newest_short"),  # newest, len 14
        ExcerptCandidate("2026-01-03T00:00:00Z", "mid"),
        ExcerptCandidate("2026-01-01T00:00:00Z", "old_oldest"),
    ]

    result = select_excerpts(candidates, 3)
    assert len(result.excerpts) == 3
    # recency primary; same-timestamp ties broken by longer text first.
    assert result.excerpts == ["B_newest_longer", "A_newest_short", "mid"]
    # the oldest is dropped by the K cap.
    assert "old_oldest" not in result.excerpts
    # deterministic on a second call.
    assert select_excerpts(candidates, 3).excerpts == result.excerpts


def test_reground_driver_supplies_excerpts(tmp_path: Path) -> None:
    """Driven by `roll_up_scopes`, the reground merger re-grounds in the scope's
    human-prompt excerpts — proving the driver gathers and supplies them."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)

    pid = "-Users-dev-clients-acme-app"
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": "/Users/dev/clients/acme/app"}]}),
        encoding="utf-8",
    )
    resolver = ProjectResolver(tmp_path / "projects")

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
           VALUES ('user', 'human', 'DRIVER_EXCERPT_MARKER', '2026-01-01T00:01:00Z', 's1', ?, ?, 1, '')""",
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

    engine = RecordingEngine(
        json.dumps({"task_summary": "m", "patterns": "m", "decisions_values": "m"})
    )
    roll_up_scopes(conn, engine, "reground", "model-a", "day", resolver=resolver)

    assert any("DRIVER_EXCERPT_MARKER" in prompt for _model, prompt in engine.calls)
