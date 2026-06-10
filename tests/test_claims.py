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
    FAILURE_CATEGORIES,
    _split_for_retry,
    categorise_claim_failure,
    ensure_claims_schema,
    extract_session_claims,
    rollup_failures,
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


# NOTE: the L2 reducer moved from greedy-cosine dedup (dedup_claims / set_union_rollup,
# archived under tmp/archived/) to EVoC clustering — see tests/test_claim_clustering.py for
# cluster_claims / cluster_rollup coverage. This file keeps the still-current L1 extraction
# + parallel failure-stream tests.


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


# --- failure taxonomy (CR5 distillation) ----------------------------------


def test_categorise_claim_failure_taxonomy() -> None:
    # Truncation: started the object, never closed (the dominant mode).
    assert (
        categorise_claim_failure(
            "no balanced JSON object found in model output", '{"tasks": ["a", "b'
        )
        == "truncated_json"
    )
    # No JSON at all (refusal / empty) → distinct from truncation.
    assert (
        categorise_claim_failure("no balanced JSON object found in model output", "I cannot help")
        == "empty_or_refusal"
    )
    assert categorise_claim_failure("no balanced JSON object found", "") == "empty_or_refusal"
    # Missing a lens key vs a non-array lens value.
    assert (
        categorise_claim_failure("\"model output JSON missing lens keys ['learnings']\"", "{...}")
        == "missing_lens_key"
    )
    assert (
        categorise_claim_failure("lens 'tasks' must be a JSON array of claims, got str", "{...}")
        == "non_array_lens"
    )
    # A bare json syntax error mid-stream.
    assert (
        categorise_claim_failure("Expecting ',' delimiter: line 1", '{"tasks": ["a" "b"]}')
        == "malformed_json"
    )
    # Everything maps to a known category.
    assert categorise_claim_failure("some brand new error", "weird") in FAILURE_CATEGORIES


class _PromptKeyedEngine:
    """Truncates (returns an unbalanced object) when the prompt carries MORE than one of
    the marker texts; returns valid per-text JSON for a single marker — exercising the
    split-and-union recovery on an over-long (output-truncated) session."""

    MARKERS = ("AAA", "BBB", "CCC", "DDD")

    def extract(self, model: str, prompt: str) -> str:
        present = [m for m in self.MARKERS if m in prompt]
        if len(present) > 1:
            return '{"tasks": ["' + present[0] + '", "trunc'  # cut off → no balanced JSON
        claim = present[0] if present else "none"
        return json.dumps(
            {"tasks": [claim], "patterns": [], "decisions_values": [], "learnings": []}
        )


def test_split_for_retry_by_count_and_within_single_prompt() -> None:
    # Multi-prompt: split by count.
    assert _split_for_retry(["a", "b", "c", "d"]) == (["a", "b"], ["c", "d"])
    # Single over-long prompt (> _MIN_SPLIT_CHARS): split internally at a newline
    # near the midpoint so each half is independently extractable.
    big = "first half of the prompt\n" + "x" * 500 + "\nsecond half of the prompt"
    halves = _split_for_retry([big])
    assert halves is not None
    left, right = halves
    assert len(left) == 1 and len(right) == 1
    assert left[0] and right[0] and left[0] != right[0]  # both non-empty, distinct
    # Too small to usefully split → genuine failure (None).
    assert _split_for_retry(["tiny"]) is None


def test_categorise_context_overflow() -> None:
    assert (
        categorise_claim_failure("muninn_chat: prompt decode failed (rc=-3)", "")
        == "context_overflow"
    )


class _DecodeOverflowEngine:
    """Raises a muninn decode error (as an over-long prompt does) when the prompt carries
    >1 marker; returns valid JSON for a single marker — exercises decode-error→split."""

    MARKERS = ("AAA", "BBB", "CCC", "DDD")

    def extract(self, model: str, prompt: str) -> str:
        present = [m for m in self.MARKERS if m in prompt]
        if len(present) > 1:
            raise sqlite3.OperationalError("muninn_chat: prompt decode failed (rc=-3)")
        claim = present[0] if present else "none"
        return json.dumps(
            {"tasks": [claim], "patterns": [], "decisions_values": [], "learnings": []}
        )


def test_decode_overflow_routes_to_split_and_union() -> None:
    conn = _cache()
    _seed_session(conn, DOGFOOD_PID, "s1", ["AAA", "BBB", "CCC", "DDD"])
    # The full prompt raises a decode error (overflow); the fallback splits until each
    # chunk fits, then unions — recovering the session instead of crashing the run.
    n = extract_session_claims(conn, DOGFOOD_PID, "s1", _DecodeOverflowEngine(), "M")
    assert n == 4
    tasks = {
        r["claim"]
        for r in conn.execute(
            "SELECT claim FROM session_claims WHERE model='M' AND lens='tasks'"
        ).fetchall()
    }
    assert tasks == {"AAA", "BBB", "CCC", "DDD"}
    assert conn.execute("SELECT COUNT(*) FROM session_claim_failures").fetchone()[0] == 0


class _LockedEngine:
    def extract(self, model: str, prompt: str) -> str:
        raise sqlite3.OperationalError("database is locked")


def test_non_decode_operational_error_is_not_swallowed() -> None:
    # A real DB error (not a decode failure) must propagate, never be mistaken for an
    # over-long prompt and silently split/retried.
    conn = _cache()
    _seed_session(conn, DOGFOOD_PID, "s1", ["only one prompt here"])
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        extract_session_claims(conn, DOGFOOD_PID, "s1", _LockedEngine(), "M")


def test_split_and_union_recovers_truncated_session() -> None:
    conn = _cache()
    _seed_session(conn, DOGFOOD_PID, "s1", ["AAA", "BBB", "CCC", "DDD"])
    # The full 4-prompt call truncates; the fallback halves until each fits, then unions.
    n = extract_session_claims(conn, DOGFOOD_PID, "s1", _PromptKeyedEngine(), "M")
    assert n == 4  # one task per text, recovered via split-and-union
    tasks = {
        r["claim"]
        for r in conn.execute(
            "SELECT claim FROM session_claims WHERE model='M' AND lens='tasks'"
        ).fetchall()
    }
    assert tasks == {"AAA", "BBB", "CCC", "DDD"}
    # No failure recorded — the session was recovered, not lost.
    n_failures = conn.execute(
        "SELECT COUNT(*) FROM session_claim_failures WHERE session_id='s1'"
    ).fetchone()[0]
    assert n_failures == 0


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
    ok = json.dumps(
        {"tasks": ["do the thing"], "patterns": [], "decisions_values": [], "learnings": []}
    )
    extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine(ok), "M")
    assert conn.execute(
        "SELECT COUNT(*) FROM session_claim_failures WHERE session_id='s1'"
    ).fetchone()[0] == 0
    n_claims = conn.execute(
        "SELECT COUNT(*) FROM session_claims WHERE session_id='s1'"
    ).fetchone()[0]
    assert n_claims == 1  # the retry succeeded and wrote claims


def test_rollup_failures_clears_resolved_failures(tmp_path: Path) -> None:
    """A fixed failure must drop the scope's rollup failure count to 0 — not strand a
    phantom count. Regression for the INSERT-OR-REPLACE-without-delete staleness bug."""
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    _seed_session(conn, DOGFOOD_PID, "s1", ["one"])
    resolver = ProjectResolver(tmp_path / "projects")
    # 1) fail s1 → rollup records the failure.
    with pytest.raises(ValueError):
        extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine("garbage out"), "M")
    rollup_failures(conn, "M", "month", resolver)
    assert conn.execute("SELECT COUNT(*) FROM rollup_claim_failures WHERE model='M'").fetchone()[
        0
    ] > 0
    # 2) resolve s1 (valid extraction clears its failure row), then re-roll-up.
    ok = json.dumps(
        {"tasks": ["fixed it"], "patterns": [], "decisions_values": [], "learnings": []}
    )
    extract_session_claims(conn, DOGFOOD_PID, "s1", _FakeEngine(ok), "M")
    rollup_failures(conn, "M", "month", resolver)
    # The stale rollup failure rows are gone — not left as phantom counts.
    assert conn.execute("SELECT COUNT(*) FROM rollup_claim_failures WHERE model='M'").fetchone()[
        0
    ] == 0


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
