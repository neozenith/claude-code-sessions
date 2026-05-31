"""Tests for the G10 benchmark folded into summarise_cli (CR1).

The headline test runs the **real** `run_permutation` orchestration
(`summarise_session` → score → `roll_up_scopes`) against a tiny fixture cache,
faking only the `muninn_chat` SQL function — the genuine GGUF boundary. This is
the corrected tracer the original plan lacked: it exercises the production code
path, not a stubbed generation seam.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from claude_code_sessions import summarise_cli as bench
from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.project_resolver import ProjectResolver


def _cache() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def test_gguf_path_and_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Inventory marks a model downloaded iff its GGUF is in a search dir."""
    models = tmp_path / "models"
    models.mkdir()
    (models / "gemma-4-E2B-it-Q4_K_M.gguf").write_bytes(b"x")  # only this one present
    monkeypatch.setattr(bench, "MODELS_DIRS", (models,))

    assert bench.gguf_path("gemma-4-E2B") == models / "gemma-4-E2B-it-Q4_K_M.gguf"
    assert bench.gguf_path("Qwen3.5-2B") is None
    inv = {m["model"]: m["downloaded"] for m in bench.model_inventory()}
    assert inv["gemma-4-E2B"] is True
    assert inv["Qwen3.5-2B"] is False


def test_manifest_marks_done_and_missing(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    done = bench.permutation_id("gemma-4-E2B", "strict")
    (results / f"{done}.json").write_text("{}", encoding="utf-8")

    by_id = {p["permutation_id"]: p for p in bench.bench_permutations(results)}
    assert len(by_id) == len(bench.MODEL_REGISTRY) * len(bench.STRATEGIES)
    assert by_id[done]["done"] is True
    assert by_id[bench.permutation_id("Qwen3.5-2B", "flat")]["done"] is False


def _seed_session(
    conn: sqlite3.Connection, tmp_path: Path, pid: str, project_path: str, sid: str
) -> None:
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}), encoding="utf-8"
    )
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
           VALUES ('f', 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (pid, sid),
    )
    sf = cur.lastrowid
    conn.execute(
        """INSERT INTO events
               (event_type, msg_kind, message_content, timestamp, session_id, project_id,
                source_file_id, line_number, raw_json)
           VALUES ('user', 'human', 'build a hierarchical summariser',
                   '2026-01-01T00:01:00Z', ?, ?, ?, 1, '')""",
        (sid, pid, sf),
    )
    conn.commit()


def test_run_permutation_scores_real_orchestration(tmp_path: Path) -> None:
    """run_permutation summarises the reference session, scores it vs gold, and
    rolls up — only muninn_chat is faked (the GGUF boundary)."""
    conn = _cache()
    pid = "-Users-dev-clients-acme-app"
    _seed_session(conn, tmp_path, pid, "/Users/dev/clients/acme/app", "s1")

    gold = {
        "task_summary": "build a summariser",
        "patterns": "pluggable",
        "decisions_values": "local",
    }
    # Fake the GGUF: return canned JSON equal to gold → identical text scores 1.0.
    conn.create_function("muninn_chat", 2, lambda _m, _p: json.dumps(gold))

    references = [{"project_id": pid, "session_id": "s1", "gold": gold}]
    resolver = ProjectResolver(tmp_path / "projects")

    record = bench.run_permutation(
        conn, "gemma-4-E2B", "strict", references, grain="day", resolver=resolver
    )

    assert record["permutation_id"] == bench.permutation_id("gemma-4-E2B", "strict")
    assert record["model"] == "gemma-4-E2B"
    assert record["strategy"] == "strict"
    assert record["n_scored"] == 1
    assert record["rollup_rows"] >= 1  # the leaf + ancestors were rolled up for real
    # Candidate == gold → perfect overlap.
    assert record["rouge_l"] == 1.0
    assert record["bleu"] == 1.0
    assert record["f1"] == 1.0
    # The session summary was actually written for this model.
    assert conn.execute(
        "SELECT COUNT(*) FROM session_summaries WHERE model = 'gemma-4-E2B'"
    ).fetchone()[0] == 1


def test_report_ranks_by_combined_score(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    for pid, r in [("a__strict", 0.9), ("b__flat", 0.2)]:
        (results / f"{pid}.json").write_text(
            json.dumps({"permutation_id": pid, "rouge_l": r, "bleu": r, "f1": r}), encoding="utf-8"
        )
    ranked = bench.rank_results(results)
    assert [r["permutation_id"] for r in ranked] == ["a__strict", "b__flat"]


def test_run_permutation_records_rollup_failure_as_data(tmp_path: Path) -> None:
    """A reground merge that exceeds context (modelled by muninn_chat raising on the
    excerpt-laden prompt) is recorded as a first-class failure, not a crash: the
    extraction still scores, the rollup error is captured, status is 'error'."""
    conn = _cache()
    pid = "-Users-dev-clients-acme-app"
    _seed_session(conn, tmp_path, pid, "/Users/dev/clients/acme/app", "s1")
    gold = {"task_summary": "t", "patterns": "p", "decisions_values": "d"}

    def chat(_m: str, prompt: str) -> str:
        # The reground merge folds in raw excerpts — emulate the real context wall.
        if "raw source excerpts" in prompt:
            raise sqlite3.OperationalError("muninn_chat: prompt exceeds context")
        return json.dumps(gold)

    conn.create_function("muninn_chat", 2, chat)
    references = [{"project_id": pid, "session_id": "s1", "gold": gold}]
    resolver = ProjectResolver(tmp_path / "projects")

    record = bench.run_permutation(
        conn, "gemma-4-E2B", "reground", references, grain="day", resolver=resolver
    )

    assert record["n_scored"] == 1  # extraction still happened and scored
    assert record["status"] == "error"
    # The merge failure is recorded as data (sqlite re-wraps the callback's
    # message, so assert it was captured — not its exact C-boundary wording).
    assert record["rollup_error"]
    assert record["rollup_rows"] == 0


def test_run_permutation_records_non_json_extraction_as_data(tmp_path: Path) -> None:
    """A model that emits no JSON object is recorded per-cell (extract_errors),
    not raised — the sweep keeps going and the report can surface it."""
    conn = _cache()
    pid = "-Users-dev-clients-acme-app"
    _seed_session(conn, tmp_path, pid, "/Users/dev/clients/acme/app", "s1")
    gold = {"task_summary": "t", "patterns": "p", "decisions_values": "d"}

    conn.create_function("muninn_chat", 2, lambda _m, _p: "I cannot help with that.")
    references = [{"project_id": pid, "session_id": "s1", "gold": gold}]
    resolver = ProjectResolver(tmp_path / "projects")

    record = bench.run_permutation(
        conn, "Qwen3.5-2B", "strict", references, grain="day", resolver=resolver
    )

    assert record["n_scored"] == 0  # nothing scorable — extraction failed to parse
    assert record["status"] == "error"
    assert record["extract_errors"]  # the non-JSON failure is recorded
