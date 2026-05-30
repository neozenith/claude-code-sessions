"""Tests for the context-window utilization map (G2).

``context_window(model_id)`` resolves a model id to its advertised
context-window size via a curated substring map, returning ``None`` for
unknown / synthetic models. These are pure-function unit tests — no cache,
no fixtures.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from claude_code_sessions.database import SQLiteDatabase
from claude_code_sessions.database.sqlite.pricing import (
    CONTEXT_WINDOWS,
    context_ratio,
    context_window,
)


@pytest.mark.parametrize(
    "model_id",
    [
        "claude-opus-4-7-20260115",
        "claude-opus-4-6-20251101",
        "claude-opus-4-8",
        "claude-sonnet-4-6-20251201",
    ],
)
def test_window_1m_models(model_id: str) -> None:
    """The 1M-window models (opus 4.6/4.7/4.8, sonnet 4.6) resolve to 1_000_000."""
    assert context_window(model_id) == 1_000_000


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("claude-opus-4-5-20250805", 200_000),
        ("claude-sonnet-4-5-20250929", 200_000),
        ("claude-haiku-4-5-20251001", 200_000),
        ("<synthetic>", None),
        ("", None),
        (None, None),
        ("gpt-4o", None),
        ("model.gguf", None),
    ],
)
def test_window_200k_and_unknown(model_id: str | None, expected: int | None) -> None:
    """Standard 200k models resolve to 200_000; synthetic / empty / unrecognized
    ids resolve to None (window — and therefore ratio — undefined)."""
    assert context_window(model_id) == expected


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("qwen2.5-coder-7b-instruct", 32_768),
        ("devstral-small-2505", 256_000),
    ],
)
def test_window_local_models(model_id: str, expected: int) -> None:
    """Curated local-model windows (native defaults): qwen2.5-coder 32k,
    devstral-small 256k. Required by the G2 success measure."""
    assert context_window(model_id) == expected


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("claude-sonnet-4-6", 1_000_000),
        ("claude-sonnet-4-5-20250929", 200_000),
    ],
)
def test_window_real_ids_resolve(model_id: str, expected: int) -> None:
    """The real curated ids resolve to their windows (regression guard)."""
    assert context_window(model_id) == expected


def test_window_longest_key_first_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """When one window key is a superstring of another (the spec's hypothetical
    ``opus-4-50`` vs existing ``opus-4-5``), the longer, more specific key must
    win. With naive insertion-order iteration the shorter ``opus-4-5`` (200k)
    shadows it; longest-key-first resolves it correctly.

    Uses a real injected map entry (not a mock) so the collision actually
    exists at lookup time, then tears it down automatically."""
    monkeypatch.setitem(CONTEXT_WINDOWS, "opus-4-50", 2_000_000)
    assert context_window("claude-opus-4-50-20270101") == 2_000_000


@pytest.mark.parametrize(
    "tokens,window,expected",
    [
        (40_000, 200_000, 0.2),
        (150_000, 200_000, 0.75),
        (0, 200_000, 0.0),
        (1_000_000, 1_000_000, 1.0),
        (50_000, None, None),  # unknown window → ratio undefined
        (50_000, 0, None),  # zero window is falsy → undefined, no ZeroDivisionError
    ],
)
def test_context_ratio(tokens: int, window: int | None, expected: float | None) -> None:
    """context_ratio is the raw fraction tokens/window, or None when the window
    is unknown — a quantitative measure with no categorical zone labeling."""
    assert context_ratio(tokens, window) == expected


def _ingest_one_response(tmp_path: Path, *, model: str, usage: dict[str, int]) -> SQLiteDatabase:
    """Ingest a session of one user prompt + one single-block assistant
    response (which is its own head) carrying ``usage``, into a fresh cache."""
    session_id = "sess-ctx"
    base = datetime(2025, 1, 1, tzinfo=UTC)
    rows = [
        {
            "uuid": "u0",
            "parentUuid": None,
            "type": "user",
            "timestamp": base.replace(second=0).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {"role": "user", "content": "hi"},
        },
        {
            "uuid": "a1",
            "parentUuid": "u0",
            "type": "assistant",
            "requestId": "req_ctx",
            "timestamp": base.replace(second=1).isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {
                "role": "assistant",
                "model": model,
                "stop_reason": "end_turn",
                "usage": usage,
                "content": [{"type": "text", "text": "hello"}],
            },
        },
    ]
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


def test_event_context_fields_after_ingest(tmp_path: Path) -> None:
    """After ingestion, an assistant head carries context_tokens (live
    occupancy = input + cache_read + cache_creation) and context_ratio
    (occupancy / model window) on a known-window model."""
    db = _ingest_one_response(
        tmp_path,
        model="claude-sonnet-4-5-20250929",  # 200k window
        usage={
            "input_tokens": 6,
            "output_tokens": 20,
            "cache_read_input_tokens": 180_000,
            "cache_creation_input_tokens": 0,
        },
    )

    events = db.get_session_events("-Users-test-proj", "sess-ctx")
    head = next(e for e in events if e["event_type"] == "assistant")

    assert head["context_tokens"] == 180_006
    assert head["context_ratio"] == pytest.approx(180_006 / 200_000)
    assert head["context_window"] == 200_000
