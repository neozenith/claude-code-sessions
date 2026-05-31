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
