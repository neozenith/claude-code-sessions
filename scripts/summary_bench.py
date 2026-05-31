#!/usr/bin/env python3
"""
G10 summarisation benchmark sweep — manifest pattern.

Sweeps the summarisation pipeline across {merge strategy × model family ×
parameter size}, screens it with the deterministic ROUGE-L/BLEU/F1 scorer
(`score_summary`), and tracks per-permutation completion by result-file
existence so the sweep is resumable.

This adopts the project's cloud-enabled-manifest pattern
(`.claude/rules/python/helper_scripts/cloud_enabled_manifest_pattern.md`):
a permutation registry (Layer 1) with file-existence status (Layer 2). The
`manifest`/`run` CLI (Layer 3/4) and report land in later G10 tickets.

Usage:
    uv run scripts/summary_bench.py manifest [--missing] [--commands]
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# The three merge strategies (G4/G5/G6), each a registry flag.
STRATEGIES: tuple[str, ...] = ("strict", "reground", "flat")

# Model families and approximate parameter buckets (ADR10.2). The size's
# billions value is the primary scaling dimension → cheapest (smallest) first.
FAMILIES: tuple[str, ...] = ("gemma", "qwen", "kimi")
SIZES: tuple[tuple[str, int], ...] = (("2b", 2), ("4b", 4), ("9b", 9))


def permutation_id(strategy: str, family: str, size: str) -> str:
    """Deterministic slug for a sweep cell — valid as a filename and CLI arg."""
    return f"{strategy}_{family}_{size}"


def check_status(results_dir: Path, perm_id: str) -> bool:
    """A permutation is done when its result file exists (Layer 2)."""
    return (results_dir / f"{perm_id}.json").exists()


def all_permutations(results_dir: Path) -> list[dict[str, Any]]:
    """The full strategy×family×size cross-product with completion status.

    Each cell carries the manifest-required fields: ``permutation_id``,
    ``sort_key`` (size-ascending = cheapest first), ``label``, and ``done``.
    """
    perms: list[dict[str, Any]] = []
    for strategy in STRATEGIES:
        for family in FAMILIES:
            for size, billions in SIZES:
                pid = permutation_id(strategy, family, size)
                perms.append(
                    {
                        "permutation_id": pid,
                        "strategy": strategy,
                        "family": family,
                        "size": size,
                        # Primary dimension = parameter size (run smallest first).
                        "sort_key": (billions, strategy, family),
                        "label": f"{strategy} / {family} / {size}",
                        "category": strategy,
                        "done": check_status(results_dir, pid),
                    }
                )
    return perms
