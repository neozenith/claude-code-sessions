"""Tests for response-level token accounting (G1).

A single model response (one ``requestId``) is logged as N content-block
events that each repeat the same request-level usage. Naive per-event
``SUM(output_tokens)`` therefore over-counts by a factor of N. The
ingestion pass must mark one **head** per ``requestId`` and zero the
duplicated usage on the non-head continuation blocks, so every existing
``SUM()`` becomes correct without query rewrites.

These tests drive that behavior through the public query interface
(``get_session_usage``) against a real SQLite fixture cache — no mocks,
the system boundary is the on-disk JSONL fixture which is real and
written per-test into ``tmp_path``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_code_sessions.database import SQLiteDatabase


def _assistant_block(
    *,
    request_id: str,
    uuid: str,
    parent_uuid: str | None,
    session_id: str,
    timestamp: str,
    output_tokens: int,
    stop_reason: str | None,
    content: list[dict[str, Any]],
) -> dict[str, Any]:
    """One content-block event of an assistant response.

    Mirrors the real JSONL shape: ``requestId`` is top-level, ``usage``
    and ``stop_reason`` live inside ``message``, and every block of the
    same response repeats the identical request-level ``usage``.
    """
    return {
        "uuid": uuid,
        "parentUuid": parent_uuid,
        "type": "assistant",
        "requestId": request_id,
        "timestamp": timestamp,
        "sessionId": session_id,
        "message": {
            "role": "assistant",
            "model": "claude-sonnet-4-5-20250929",
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": 50,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": 10,
                "cache_creation_input_tokens": 5,
            },
            "content": content,
        },
    }


def _build_cache(tmp_path: Path, rows: list[dict[str, Any]], *, session_id: str) -> SQLiteDatabase:
    """Write ``rows`` as a JSONL session file and ingest it into a fresh cache."""
    projects = tmp_path / "projects"
    project_dir = projects / "-Users-test-proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f"{session_id}.jsonl"
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
    return db


def test_multiblock_response_counted_once(tmp_path: Path) -> None:
    """A response logged as 3 blocks each repeating output_tokens=100
    contributes 100 — not 300 — to the session's total output tokens."""
    session_id = "sess-dedup"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    ts = lambda i: base.replace(second=i).isoformat().replace("+00:00", "Z")  # noqa: E731
    request_id = "req_multiblock"
    rows = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": ts(0),
            "sessionId": session_id,
            "message": {"role": "user", "content": "do the thing"},
        },
        _assistant_block(
            request_id=request_id,
            uuid="a1",
            parent_uuid="u0",
            session_id=session_id,
            timestamp=ts(1),
            output_tokens=100,
            stop_reason=None,
            content=[{"type": "thinking", "thinking": "hmm"}],
        ),
        _assistant_block(
            request_id=request_id,
            uuid="a2",
            parent_uuid="a1",
            session_id=session_id,
            timestamp=ts(2),
            output_tokens=100,
            stop_reason=None,
            content=[{"type": "text", "text": "here you go"}],
        ),
        _assistant_block(
            request_id=request_id,
            uuid="a3",
            parent_uuid="a2",
            session_id=session_id,
            timestamp=ts(3),
            output_tokens=100,
            stop_reason="tool_use",
            content=[{"type": "tool_use", "name": "Read", "input": {}}],
        ),
    ]

    db = _build_cache(tmp_path, rows, session_id=session_id)
    usage = db.get_session_usage()

    total_output = sum(row["total_output_tokens"] for row in usage if row["session_id"] == session_id)
    assert total_output == 100, f"expected deduped 100, got {total_output} from {usage}"
