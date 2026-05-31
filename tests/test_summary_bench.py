"""Tests for the G10 benchmark sweep registry (scripts/summary_bench.py).

The script is standalone (run via ``uv run scripts/summary_bench.py``), so we
load it from its file path rather than as a package import.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_BENCH_PATH = Path(__file__).resolve().parent.parent / "scripts" / "summary_bench.py"
_spec = importlib.util.spec_from_file_location("summary_bench", _BENCH_PATH)
assert _spec is not None and _spec.loader is not None
summary_bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(summary_bench)


def test_registry_enumerates_and_marks_status(tmp_path: Path) -> None:
    """The registry is the strategy×family×size cross-product; `done` is set by
    file-existence in the results dir."""
    results = tmp_path / "results"
    results.mkdir()

    done_id = summary_bench.permutation_id("strict", "gemma", "2b")
    (results / f"{done_id}.json").write_text("{}", encoding="utf-8")

    perms = summary_bench.all_permutations(results)
    by_id = {p["permutation_id"]: p for p in perms}

    # 3 strategies × 3 families × 3 sizes = 27 cells.
    assert len(perms) == 27
    assert by_id[done_id]["done"] is True
    assert by_id[summary_bench.permutation_id("flat", "kimi", "9b")]["done"] is False

    expected_ids = {
        summary_bench.permutation_id(s, f, z)
        for s in ("strict", "reground", "flat")
        for f in ("gemma", "qwen", "kimi")
        for z in ("2b", "4b", "9b")
    }
    assert set(by_id) == expected_ids

    # Each cell carries the manifest-required fields.
    sample = by_id[done_id]
    assert {"permutation_id", "sort_key", "label", "done"} <= set(sample)


def test_manifest_missing_lists_incomplete(tmp_path: Path, capsys) -> None:
    """`manifest --missing --commands` emits only the absent cells as
    `run --id …` lines, cheapest-first by size."""
    results = tmp_path / "results"
    results.mkdir()
    done_ids = [
        summary_bench.permutation_id("strict", "gemma", "2b"),
        summary_bench.permutation_id("flat", "qwen", "4b"),
    ]
    for pid in done_ids:
        (results / f"{pid}.json").write_text("{}", encoding="utf-8")

    summary_bench.main(["manifest", "--missing", "--commands", "--results-dir", str(results)])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]

    assert lines  # something was emitted
    assert all(ln.startswith("uv run scripts/summary_bench.py run --id ") for ln in lines)
    printed_ids = [ln.rsplit(" ", 1)[1] for ln in lines]

    # The two completed cells are excluded; 27 - 2 = 25 remain.
    assert len(printed_ids) == 25
    for pid in done_ids:
        assert pid not in printed_ids

    # Cheapest-first: parameter sizes are non-decreasing down the list.
    sizes = [int(pid.rsplit("_", 1)[1].rstrip("b")) for pid in printed_ids]
    assert sizes == sorted(sizes)


def test_run_writes_result_row(tmp_path: Path, monkeypatch) -> None:
    """`run --id <perm>` (model-generation seam stubbed) scores the candidate
    with the real scorer and writes a JSON result row, marking the cell done."""
    import json

    results = tmp_path / "results"
    refs = tmp_path / "refs"
    refs.mkdir()
    (refs / "r1.json").write_text(
        json.dumps(
            {
                "gold": {
                    "task_summary": "build a summariser",
                    "patterns": "pluggable engine",
                    "decisions_values": "local only",
                }
            }
        ),
        encoding="utf-8",
    )

    # Stub ONLY the model-generation seam (the GGUF boundary); the scorer is real.
    monkeypatch.setattr(
        summary_bench,
        "_generate_candidate",
        lambda perm, references_dir: ("build a summariser pluggable engine local only", 0.05),
    )

    pid = summary_bench.permutation_id("strict", "gemma", "2b")
    summary_bench.main(
        ["run", "--id", pid, "--results-dir", str(results), "--references-dir", str(refs)]
    )

    out = results / f"{pid}.json"
    assert out.exists()
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["permutation_id"] == pid
    assert {"rouge_l", "bleu", "f1"} <= set(record)
    assert summary_bench.check_status(results, pid) is True


def test_no_gguf_cells_are_logged_not_dropped(tmp_path: Path, monkeypatch, capsys, caplog) -> None:
    """A family×size with no GGUF build is logged and excluded from the runnable
    set, but still enumerated by the registry (no silent caps)."""
    import logging

    results = tmp_path / "results"
    results.mkdir()
    # Stub the GGUF-availability seam: kimi 9b has no build.
    monkeypatch.setattr(
        summary_bench, "_gguf_available", lambda family, size: not (family == "kimi" and size == "9b")
    )

    with caplog.at_level(logging.WARNING, logger="summary_bench"):
        summary_bench.main(["manifest", "--missing", "--commands", "--results-dir", str(results)])

    # Skip log names the skipped cell...
    assert "kimi" in caplog.text and "9b" in caplog.text
    # ...the runnable --missing commands exclude it...
    assert "kimi_9b" not in capsys.readouterr().out
    # ...but the registry still lists the cells, flagged unavailable (not dropped).
    kimi9b = [p for p in summary_bench.all_permutations(results) if p["family"] == "kimi" and p["size"] == "9b"]
    assert len(kimi9b) == 3
    assert all(p["available"] is False for p in kimi9b)


def test_report_ranks_by_score(tmp_path: Path) -> None:
    """`report` orders permutations highest-combined-score first and marks the
    top cell as the human-review candidate."""
    import json

    results = tmp_path / "results"
    results.mkdir()

    def _write(pid: str, r: float, b: float, f: float) -> None:
        (results / f"{pid}.json").write_text(
            json.dumps({"permutation_id": pid, "rouge_l": r, "bleu": b, "f1": f}),
            encoding="utf-8",
        )

    _write("strict_gemma_2b", 0.9, 0.9, 0.9)  # highest
    _write("flat_qwen_4b", 0.5, 0.5, 0.5)
    _write("reground_kimi_9b", 0.1, 0.1, 0.1)  # lowest

    out = tmp_path / "report.md"
    summary_bench.main(["report", "--results-dir", str(results), "--output", str(out)])
    text = out.read_text(encoding="utf-8")

    # Ranked highest-first.
    assert text.index("strict_gemma_2b") < text.index("flat_qwen_4b") < text.index("reground_kimi_9b")

    # Top cell is named as the review candidate.
    candidate_line = next(ln for ln in text.splitlines() if "review candidate" in ln)
    assert "strict_gemma_2b" in candidate_line
