"""Tests for the G10 benchmark folded into summarise_cli (CR1).

The headline test runs the **real** `run_permutation` orchestration
(`summarise_session` → source-grounded score → `roll_up_scopes` → rollup score)
against a tiny fixture cache, faking only the `muninn_chat` SQL function — the
genuine GGUF boundary. There is no fabricated gold: every score is the generated
summary's overlap against the *real* human-prompt text it derives from.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from claude_code_sessions import summarise_cli as bench
from claude_code_sessions.database.sqlite.schema import SCHEMA_SQL
from claude_code_sessions.project_resolver import ProjectResolver

# A real dogfood project path so the default BENCH_SCOPES ("play/claude-code-sessions")
# matches the seeded sessions' resolved scope chain.
DOGFOOD_PID = "-Users-dev-play-claude-code-sessions"
DOGFOOD_PATH = "/Users/dev/play/claude-code-sessions"


def _cache() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def _index(tmp_path: Path, pid: str, project_path: str) -> None:
    pdir = tmp_path / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "sessions-index.json").write_text(
        json.dumps({"version": 1, "entries": [{"projectPath": project_path}]}), encoding="utf-8"
    )


def _seed_session(conn: sqlite3.Connection, pid: str, sid: str, human_text: str) -> None:
    cur = conn.execute(
        """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
           VALUES (?, 0, 0, 0, '2026-01-01T00:00:00Z', ?, ?, 'main_session')""",
        (f"f-{sid}", pid, sid),
    )
    sf = cur.lastrowid
    conn.execute(
        """INSERT INTO events
               (event_type, msg_kind, message_content, timestamp, session_id, project_id,
                source_file_id, line_number, raw_json)
           VALUES ('user', 'human', ?, '2026-01-01T00:01:00Z', ?, ?, ?, 1, '')""",
        (human_text, sid, pid, sf),
    )
    conn.commit()


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


def test_manifest_grid_is_models_x_strategies_x_grains(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    done = bench.permutation_id("Qwen3.5-2B", "strict", "day")
    (results / f"{done}.json").write_text("{}", encoding="utf-8")

    by_id = {p["permutation_id"]: p for p in bench.bench_permutations(results)}
    assert len(by_id) == len(bench.BENCH_MODELS) * len(bench.STRATEGIES) * len(bench.GRAINS)
    assert by_id[done]["done"] is True
    assert by_id[done]["grain"] == "day"
    assert by_id[bench.permutation_id("Llama-3.1-8B", "flat", "month")]["done"] is False


def test_bench_session_keys_selects_only_in_scope_sessions(tmp_path: Path) -> None:
    """Only sessions whose resolved scope chain includes a BENCH_SCOPE are picked."""
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    other_pid = "-Users-dev-work-onyx-secret"
    _index(tmp_path, other_pid, "/Users/dev/work/onyx/secret")
    _seed_session(conn, DOGFOOD_PID, "s1", "in scope")
    _seed_session(conn, other_pid, "s2", "out of scope")

    resolver = ProjectResolver(tmp_path / "projects")
    keys = bench.bench_session_keys(conn, resolver, ("play/claude-code-sessions",))
    assert keys == [(DOGFOOD_PID, "s1")]


def test_run_permutation_is_source_grounded(tmp_path: Path) -> None:
    """run_permutation summarises a real session, scores the summary against that
    session's REAL human prompt (no gold), rolls up, and scores the rollup against
    the same real source — only muninn_chat is faked (the GGUF boundary)."""
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    _seed_session(conn, DOGFOOD_PID, "s1", "build a hierarchical summariser with pluggable mergers")

    # Fake GGUF: return a summary whose words are all drawn from the real source,
    # so source-grounding (BLEU precision) is high and non-zero.
    summary = {
        "task_summary": "build a hierarchical summariser",
        "patterns": "pluggable mergers",
        "decisions_values": "summariser mergers",
    }
    # muninn_chat is now the 4-arg form (model, prompt, grammar, max_tokens);
    # the fake ignores the grammar/cap and returns canned JSON (variadic narg=-1).
    conn.create_function("muninn_chat", -1, lambda *a: json.dumps(summary))
    resolver = ProjectResolver(tmp_path / "projects")

    record = bench.run_permutation(
        conn, "gemma-4-E2B", "strict", "day", resolver=resolver,
        session_keys=[(DOGFOOD_PID, "s1")], embed_cosine=lambda _c, _r: 0.5,
    )

    assert record["permutation_id"] == "gemma-4-E2B__strict__day"
    assert record["grain"] == "day"
    assert record["status"] == "ok"
    assert record["n_sessions_scored"] == 1
    assert record["rollup_embed_cosine"] == 0.5  # the injected cosine flows through
    assert record["session_bleu"] > 0  # summary words really appear in the source
    assert record["n_rollups_scored"] >= 1  # leaf + ancestor scopes scored for real
    assert record["rollup_bleu"] > 0
    # The session summary was actually written for this model.
    assert conn.execute(
        "SELECT COUNT(*) FROM session_summaries WHERE model = 'gemma-4-E2B'"
    ).fetchone()[0] == 1


def test_run_permutation_records_rollup_failure_as_data(tmp_path: Path) -> None:
    """A reground merge that exceeds context (modelled by muninn_chat raising on the
    excerpt-laden prompt) is recorded as a first-class failure, not a crash: the
    session still scores, the rollup error is captured, status is 'error'."""
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    _seed_session(conn, DOGFOOD_PID, "s1", "build a hierarchical summariser")
    ok = {"task_summary": "build a summariser", "patterns": "p", "decisions_values": "d"}

    def chat(*a: object) -> str:
        prompt = str(a[1])
        if "raw source excerpts" in prompt:  # the reground merge folds these in
            raise sqlite3.OperationalError("muninn_chat: prompt exceeds context")
        return json.dumps(ok)

    conn.create_function("muninn_chat", -1, chat)
    resolver = ProjectResolver(tmp_path / "projects")

    record = bench.run_permutation(
        conn, "gemma-4-E2B", "reground", "day",
        resolver=resolver, session_keys=[(DOGFOOD_PID, "s1")], embed_cosine=lambda _c, _r: 0.5,
    )

    assert record["n_sessions_scored"] == 1  # extraction still happened and scored
    assert record["status"] == "error"
    assert record["rollup_error"]  # sqlite re-wraps the message; just assert captured


def test_run_permutation_records_non_json_extraction_as_data(tmp_path: Path) -> None:
    """A model that emits no JSON object is recorded per-cell (extract_errors),
    not raised — the sweep keeps going and the report can surface it."""
    conn = _cache()
    _index(tmp_path, DOGFOOD_PID, DOGFOOD_PATH)
    _seed_session(conn, DOGFOOD_PID, "s1", "build a summariser")

    conn.create_function("muninn_chat", -1, lambda *a: "I cannot help with that.")
    resolver = ProjectResolver(tmp_path / "projects")

    record = bench.run_permutation(
        conn, "Qwen3.5-2B", "strict", "day",
        resolver=resolver, session_keys=[(DOGFOOD_PID, "s1")], embed_cosine=lambda _c, _r: 0.5,
    )

    assert record["n_sessions_scored"] == 0  # nothing scorable — extraction failed to parse
    assert record["status"] == "error"
    assert record["extract_errors"]  # the non-JSON failure is recorded


def test_report_ranks_by_rollup_grounding(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    for pid, roll in [("a__strict__day", 0.9), ("b__flat__day", 0.2)]:
        (results / f"{pid}.json").write_text(
            json.dumps(
                {
                    "permutation_id": pid,
                    "n_rollups_scored": 1,
                    "rollup_rouge_l": roll,
                    "rollup_bleu": roll,
                    "rollup_f1": roll,
                }
            ),
            encoding="utf-8",
        )
    ranked = bench.rank_results(results)
    assert [r["permutation_id"] for r in ranked] == ["a__strict__day", "b__flat__day"]
