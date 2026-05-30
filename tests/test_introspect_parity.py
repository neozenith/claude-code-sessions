"""Parity test: the standalone introspect script's ingestion pipeline must
produce byte-identical ``events`` rows to the backend ``CacheManager``.

The introspect script (``.claude/skills/introspect/scripts/introspect_sessions.py``)
keeps its OWN copies of the schema, pricing, and CacheManager because it is a
standalone PEP-723 script that cannot import the package. This test guards
against drift: both ingest the SAME JSONL fixture into two separate caches and
the per-event response/context/timing columns must agree row-for-row.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_code_sessions.database.sqlite import schema as backend_schema
from claude_code_sessions.database.sqlite.cache import CacheManager as BackendCacheManager

# ---------------------------------------------------------------------------
# Load the standalone introspect script as a module (it cannot be imported as
# a package member — it's a PEP-723 single-file script).
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)
_INTROSPECT_PATH = (
    _REPO_ROOT / ".claude" / "skills" / "introspect" / "scripts" / "introspect_sessions.py"
)


def _load_introspect() -> Any:
    spec = importlib.util.spec_from_file_location("introspect_sessions", _INTROSPECT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass processing (which looks the module up
    # in sys.modules by __module__) succeeds during module load.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


introspect = _load_introspect()


# ---------------------------------------------------------------------------
# Shared fixture: one JSONL with a user prompt, a multi-block assistant
# response (2 blocks sharing one requestId), and a following user prompt.
# ---------------------------------------------------------------------------
_MODEL = "claude-sonnet-4-5-20250929"
_REQUEST_ID = "req_abc123"
_USAGE = {
    "input_tokens": 1000,
    "output_tokens": 500,
    "cache_read_input_tokens": 200,
    "cache_creation_input_tokens": 100,
    "cache_creation": {"ephemeral_5m_input_tokens": 50},
}


def _write_fixture(path: Path) -> None:
    lines: list[dict[str, Any]] = [
        {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "sessionId": "sess-1",
            "timestamp": "2026-05-01T10:00:00.000Z",
            "message": {"role": "user", "content": "Please do the thing."},
        },
        # Multi-block assistant response — block 1 (thinking), repeats usage.
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "sessionId": "sess-1",
            "requestId": _REQUEST_ID,
            "timestamp": "2026-05-01T10:00:05.000Z",
            "message": {
                "role": "assistant",
                "model": _MODEL,
                "stop_reason": None,
                "content": [{"type": "text", "text": "Working on it."}],
                "usage": _USAGE,
            },
        },
        # Block 2 (head) — same requestId, repeats usage, final stop_reason.
        {
            "type": "assistant",
            "uuid": "a2",
            "parentUuid": "a1",
            "sessionId": "sess-1",
            "requestId": _REQUEST_ID,
            "timestamp": "2026-05-01T10:00:08.000Z",
            "message": {
                "role": "assistant",
                "model": _MODEL,
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Done."}],
                "usage": _USAGE,
            },
        },
        {
            "type": "user",
            "uuid": "u2",
            "parentUuid": "a2",
            "sessionId": "sess-1",
            "timestamp": "2026-05-01T10:01:00.000Z",
            "message": {"role": "user", "content": "Thanks, next thing."},
        },
    ]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


_QUERY_COLS = (
    "is_response_head, output_tokens, context_tokens, context_window, "
    "context_ratio, msg_kind, response_duration_ms"
)


def _query_events(db_path: Path) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"SELECT {_QUERY_COLS} FROM events ORDER BY line_number").fetchall()
    finally:
        conn.close()
    return rows


def _ingest_backend(db_path: Path, jsonl: Path, *, file_type: str) -> None:
    cache = BackendCacheManager(db_path=db_path)
    cache.init_schema()
    cache.ingest_file(
        {
            "filepath": str(jsonl),
            "project_id": "proj-1",
            "session_id": "sess-1",
            "file_type": file_type,
            "mtime": jsonl.stat().st_mtime,
            "size_bytes": jsonl.stat().st_size,
        }
    )
    cache.rebuild_aggregates()
    cache.close()


def _ingest_introspect(db_path: Path, jsonl: Path, *, file_type: str) -> None:
    cache = introspect.CacheManager(db_path=db_path)
    cache.init_schema()
    cache.ingest_file(
        {
            "filepath": str(jsonl),
            "project_id": "proj-1",
            "session_id": "sess-1",
            "file_type": file_type,
            "mtime": jsonl.stat().st_mtime,
            "size_bytes": jsonl.stat().st_size,
        }
    )
    cache.rebuild_aggregates()
    cache.close()


@pytest.mark.parametrize("file_type", ["main_session", "subagent"])
def test_backend_and_introspect_agree(tmp_path: Path, file_type: str) -> None:
    # Same fixture, two separate caches.
    jsonl = tmp_path / "session.jsonl"
    _write_fixture(jsonl)

    backend_db = tmp_path / f"backend_{file_type}.db"
    introspect_db = tmp_path / f"introspect_{file_type}.db"

    _ingest_backend(backend_db, jsonl, file_type=file_type)
    _ingest_introspect(introspect_db, jsonl, file_type=file_type)

    backend_rows = _query_events(backend_db)
    introspect_rows = _query_events(introspect_db)

    assert backend_rows == introspect_rows, (
        f"events parity mismatch for file_type={file_type}:\n"
        f"  backend={backend_rows}\n  introspect={introspect_rows}"
    )

    # Sanity: the multi-block response was deduped to exactly one head with usage.
    heads_with_output = [r for r in backend_rows if r[0] == 1 and r[1] > 0]
    assert len(heads_with_output) == 1

    # SCHEMA_VERSION must agree between both modules, and equal the backend const.
    assert backend_schema.SCHEMA_VERSION == introspect.SCHEMA_VERSION
    assert introspect.SCHEMA_VERSION == backend_schema.SCHEMA_VERSION
