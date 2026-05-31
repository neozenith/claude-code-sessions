"""Tests for per-session human-prompt summarisation (G2).

These tests build a *tiny* in-memory fixture cache (never the real ~2 GB DB)
and drive ``summarise_session`` with an injected fake ``SummaryEngine`` — a
real class implementing the protocol, returning canned output instead of
calling the live ``muninn_chat`` GGUF. That keeps the test deterministic and
fast while still exercising the real summarisation code path.
"""

from __future__ import annotations

import json
import sqlite3

from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.database.sqlite.summaries import summarise_session


class FakeEngine:
    """A real ``SummaryEngine`` returning canned text and recording calls.

    Recording ``(model, prompt)`` lets later tickets assert *what* reached the
    engine (T2.2: human-only) and *how often* (T2.3: zero calls on a cache hit).
    """

    def __init__(self, output: str) -> None:
        self._output = output
        self.calls: list[tuple[str, str]] = []

    def summarise(self, model: str, prompt: str) -> str:
        self.calls.append((model, prompt))
        return self._output


def _make_cache() -> sqlite3.Connection:
    """A throwaway in-memory cache carrying the production schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def _seed_human_events(
    conn: sqlite3.Connection,
    project_id: str,
    session_id: str,
    texts: list[str],
) -> None:
    """Insert one ``msg_kind='human'`` event per text, plus its source file."""
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"/fixture/{session_id}.jsonl", project_id, session_id),
    )
    source_file_id = cur.lastrowid
    for i, text in enumerate(texts, start=1):
        conn.execute(
            """INSERT INTO events
                   (event_type, msg_kind, message_content, timestamp,
                    session_id, project_id, source_file_id, line_number, raw_json)
               VALUES ('user', 'human', ?, ?, ?, ?, ?, ?, '')""",
            (text, f"2026-01-01T00:0{i}:00Z", session_id, project_id, source_file_id, i),
        )
    conn.commit()


def _seed_event(
    conn: sqlite3.Connection,
    project_id: str,
    session_id: str,
    msg_kind: str,
    content: str,
    line_number: int,
    source_file_id: int,
) -> None:
    conn.execute(
        """INSERT INTO events
               (event_type, msg_kind, message_content, timestamp,
                session_id, project_id, source_file_id, line_number, raw_json)
           VALUES ('user', ?, ?, ?, ?, ?, ?, ?, '')""",
        (msg_kind, content, f"2026-01-01T00:0{line_number}:00Z", session_id,
         project_id, source_file_id, line_number),
    )


def _seed_source_file(conn: sqlite3.Connection, project_id: str, session_id: str) -> int:
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"/fixture/{session_id}.jsonl", project_id, session_id),
    )
    return int(cur.lastrowid or 0)


def test_summarise_session_writes_one_three_lens_row() -> None:
    """A developer's typed prompts become one stored 3-lens session summary."""
    conn = _make_cache()
    project_id = "-Users-dev-play-foo"
    session_id = "sess-1"
    _seed_human_events(
        conn,
        project_id,
        session_id,
        ["Build a hierarchical summariser over human prompts.", "Make the engine pluggable."],
    )

    engine = FakeEngine(
        json.dumps(
            {
                "task_summary": "Build a hierarchical prompt summariser",
                "patterns": "Pluggable engine; content-hash guard",
                "decisions_values": "Local-only inference; fail-loud",
            }
        )
    )

    summarise_session(conn, project_id, session_id, engine, "test-model")

    rows = conn.execute("SELECT * FROM session_summaries").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["task_summary"] == "Build a hierarchical prompt summariser"
    assert row["patterns"] == "Pluggable engine; content-hash guard"
    assert row["decisions_values"] == "Local-only inference; fail-loud"
    assert row["model"] == "test-model"
    assert row["human_event_count"] == 2
    assert len(engine.calls) == 1


def test_only_human_kind_text_is_summarised() -> None:
    """Only ``msg_kind='human'`` text reaches the engine (ADR2.2).

    A session mixes human prompts with the excluded kinds (``user_text``,
    ``assistant``, ``tool``, ``subagent-*``). The prompt the engine receives
    must carry the human markers and none of the excluded-kind markers.
    """
    conn = _make_cache()
    project_id = "-Users-dev-play-foo"
    session_id = "sess-mixed"
    sf = _seed_source_file(conn, project_id, session_id)
    _seed_event(conn, project_id, session_id, "human", "HUMAN_ONE wants a summariser", 1, sf)
    _seed_event(conn, project_id, session_id, "user_text", "USERTEXT_pasted_log_noise", 2, sf)
    _seed_event(conn, project_id, session_id, "assistant", "ASSISTANT_reply_text", 3, sf)
    _seed_event(conn, project_id, session_id, "tool", "TOOL_result_blob", 4, sf)
    _seed_event(conn, project_id, session_id, "subagent-human", "SUBAGENT_sidechain_text", 5, sf)
    _seed_event(conn, project_id, session_id, "human", "HUMAN_TWO refine the engine", 6, sf)
    conn.commit()

    engine = FakeEngine(
        json.dumps({"task_summary": "t", "patterns": "p", "decisions_values": "d"})
    )

    summarise_session(conn, project_id, session_id, engine, "test-model")

    assert len(engine.calls) == 1
    prompt = engine.calls[0][1]
    assert "HUMAN_ONE" in prompt
    assert "HUMAN_TWO" in prompt
    excluded_markers = (
        "USERTEXT_pasted_log_noise",
        "ASSISTANT_reply_text",
        "TOOL_result_blob",
        "SUBAGENT_sidechain_text",
    )
    for excluded in excluded_markers:
        assert excluded not in prompt

    row = conn.execute("SELECT human_event_count FROM session_summaries").fetchone()
    assert row["human_event_count"] == 2
