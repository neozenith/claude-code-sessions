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
import json
import logging
import time
from pathlib import Path
from typing import Any

from claude_code_sessions.database.sqlite.summaries import score_summary

log = logging.getLogger("summary_bench")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "tmp" / "summary_bench"
DEFAULT_REFERENCES_DIR = PROJECT_ROOT / "data" / "summary_bench" / "references"

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


def _gguf_available(family: str, size: str) -> bool:
    """GGUF-availability seam (ADR10.2). The real sweep checks for a registered
    build of ``family``×``size``; tests stub it. Defaults optimistic (True) so the
    registry is the full grid unless a build is known-missing — a missing build is
    logged and excluded from runnable cells, never silently dropped."""
    return True


def available_gguf_cells() -> set[tuple[str, str]]:
    """The ``(family, size)`` cells that have a registered GGUF build."""
    return {(f, s) for f in FAMILIES for s, _b in SIZES if _gguf_available(f, s)}


def all_permutations(results_dir: Path) -> list[dict[str, Any]]:
    """The full strategy×family×size cross-product with completion + availability.

    Every cell is enumerated (never dropped). Each carries the manifest-required
    fields — ``permutation_id``, ``sort_key`` (size-ascending = cheapest first),
    ``label``, ``done`` — plus ``available`` (its GGUF build exists). Cells whose
    build is missing are flagged unavailable and logged once per family×size
    (no silent caps, ADR10.2); the runnable set excludes them.
    """
    available = available_gguf_cells()
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
                        "available": (family, size) in available,
                    }
                )
    for family, size in sorted({(f, s) for f in FAMILIES for s, _b in SIZES} - available):
        log.warning("skipping %s %s: no registered GGUF build", family, size)
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
        # Runnable-missing: not done AND has a GGUF build (skipped cells are logged
        # by all_permutations, never silently included as runnable).
        perms = [p for p in perms if not p["done"] and p["available"]]
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


# ---------------------------------------------------------------------------
# Execution lifecycle (Layer 4 — run one permutation)
# ---------------------------------------------------------------------------


def _load_reference_text(references_dir: Path) -> str:
    """The concatenated gold three-lens text — the scoring target (ADR10.1)."""
    parts: list[str] = []
    for ref_file in sorted(references_dir.glob("*.json")):
        gold = json.loads(ref_file.read_text(encoding="utf-8")).get("gold", {})
        parts.append(
            " ".join(str(gold.get(k, "")) for k in ("task_summary", "patterns", "decisions_values"))
        )
    return "\n".join(parts)


def _generate_candidate(perm: dict[str, Any], references_dir: Path) -> tuple[str, float]:
    """The model-generation seam: produce a candidate summary + elapsed seconds.

    The real sweep registers the GGUF for ``perm``'s family×size in
    ``temp.muninn_chat_models`` and runs ``summarise_session`` + ``roll_up_scopes``
    (via ``perm['strategy']``) over the reference sessions. That requires the model
    artifacts, so it fails loud here; the benchmark tests stub this one seam while
    the scorer runs real (ADR10.1, T10.4 contract).
    """
    raise NotImplementedError(
        "model-generation requires the GGUF artifacts for "
        f"{perm['family']} {perm['size']}; register it in temp.muninn_chat_models "
        "and run the pipeline. Tests stub this seam."
    )


def save_result(results_dir: Path, perm_id: str, record: dict[str, Any]) -> None:
    """Write a permutation's result row; its existence marks the cell done."""
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{perm_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def cmd_run(args: argparse.Namespace) -> None:
    """Generate a candidate for one permutation, score it, and write the result row."""
    perms = {p["permutation_id"]: p for p in all_permutations(args.results_dir)}
    if args.id not in perms:  # fail loud — never run an unknown cell
        raise SystemExit(f"unknown permutation id: {args.id!r}")
    perm = perms[args.id]

    t0 = time.monotonic()
    candidate, gen_seconds = _generate_candidate(perm, args.references_dir)
    scores = score_summary(candidate, _load_reference_text(args.references_dir))
    record: dict[str, Any] = {
        "permutation_id": args.id,
        "strategy": perm["strategy"],
        "family": perm["family"],
        "size": perm["size"],
        "seconds": gen_seconds,
        "wall_seconds": time.monotonic() - t0,
        **scores,
    }
    save_result(args.results_dir, args.id, record)


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

    run = sub.add_parser("run", help="Run one permutation: generate, score, write result")
    run.add_argument("--id", required=True, help="Permutation id (see manifest)")
    run.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run.add_argument("--references-dir", type=Path, default=DEFAULT_REFERENCES_DIR)
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
