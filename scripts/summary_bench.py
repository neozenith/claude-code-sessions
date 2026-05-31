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

import argparse
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "tmp" / "summary_bench"

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


# ---------------------------------------------------------------------------
# CLI (Layer 3 — manifest)
# ---------------------------------------------------------------------------

_RUN_COMMAND = "uv run scripts/summary_bench.py run --id"


def _sorted(perms: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    if sort == "name":
        return sorted(perms, key=lambda p: p["permutation_id"])
    return sorted(perms, key=lambda p: p["sort_key"])  # cheapest (smallest) first


def cmd_manifest(args: argparse.Namespace) -> None:
    """List permutations with status; filter, sort, and optionally emit commands."""
    perms = all_permutations(args.results_dir)
    total = len(perms)
    total_done = sum(1 for p in perms if p["done"])

    if args.missing:
        perms = [p for p in perms if not p["done"]]
    if args.done:
        perms = [p for p in perms if p["done"]]
    perms = _sorted(perms, args.sort)
    if args.limit is not None:
        perms = perms[: args.limit]

    if args.commands:
        for p in perms:
            print(f"{_RUN_COMMAND} {p['permutation_id']}")
        return

    print(f"=== Manifest ({total_done}/{total} done) ===")
    for p in perms:
        marker = "DONE" if p["done"] else "MISS"
        print(f"  [{marker}] {p['permutation_id']:<26} {p['label']}")


def _help(parser: argparse.ArgumentParser):  # type: ignore[no-untyped-def]
    def _print_help(_: argparse.Namespace) -> None:
        parser.print_help()

    return _print_help


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="summary_bench", description="G10 summarisation benchmark sweep (manifest pattern)."
    )
    parser.set_defaults(func=_help(parser))
    sub = parser.add_subparsers(dest="command", required=False)

    manifest = sub.add_parser("manifest", help="List permutations with done/missing status")
    manifest.add_argument("--missing", action="store_true", help="Only incomplete permutations")
    manifest.add_argument("--done", action="store_true", help="Only completed permutations")
    manifest.add_argument("--commands", action="store_true", help="Emit one runnable command per cell")
    manifest.add_argument("--sort", choices=["size", "name"], default="size", help="Sort order")
    manifest.add_argument("--limit", type=int, default=None, help="Limit to first N after filtering")
    manifest.add_argument(
        "--results-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="Per-permutation result dir"
    )
    manifest.set_defaults(func=cmd_manifest)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
