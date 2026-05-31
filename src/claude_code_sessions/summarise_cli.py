"""Manual, ingest-decoupled summarisation runners + CLI (G2, ADR2.4).

Summarisation never runs inside the wave/ingest auto-update. Instead this
module exposes :func:`summarise_sessions` — a standalone runner that iterates
the sessions ingested *to date* and summarises the not-yet-current ones — and a
thin ``argparse`` CLI that wires it to the production ``muninn_chat`` engine:

    uv run -m claude_code_sessions.summarise_cli sessions --model M [--scope S]

Each tier can therefore be bound to its own external cadence (cron, manual)
without coupling to the last ingest moment, and the same call surface is shared
with the G10 benchmark.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import sqlite_muninn

from claude_code_sessions.config import CACHE_DB_PATH, PROJECTS_PATH
from claude_code_sessions.database.sqlite.kg.runtime import ensure_chat_model_downloaded
from claude_code_sessions.database.sqlite.summaries import (
    MuninnSummaryEngine,
    SummaryEngine,
    roll_up_scopes,
    score_summary,
    summarise_session,
)
from claude_code_sessions.project_resolver import ProjectResolver, ancestor_scopes

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "tmp" / "summary_bench"
DEFAULT_REFERENCES_DIR = PROJECT_ROOT / "data" / "summary_bench" / "references"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs" / "plans" / "summariser-G10-REPORT.md"

# Where GGUF chat models are searched, in priority order (CR1). The cache dir is
# canonical; the sqlite-vector-graph models dir is an opportunistic fallback.
MODELS_DIRS: tuple[Path, ...] = (
    Path.home() / ".claude" / "cache" / "models",
    Path.home() / "play" / "sqlite-vector-graph" / "models",
)

# Desired benchmark model inventory: model_id → (gguf filename, family,
# approximate parameter size in billions). Edit this to grow the grid (CR1).
MODEL_REGISTRY: dict[str, tuple[str, str, float]] = {
    "gemma-4-E2B": ("gemma-4-E2B-it-Q4_K_M.gguf", "gemma", 2.0),
    "gemma-4-E4B": ("gemma-4-E4B-it-Q4_K_M.gguf", "gemma", 4.0),
    "Qwen3.5-0.8B": ("Qwen3.5-0.8B-Q4_K_M.gguf", "qwen", 0.8),
    "Qwen3.5-2B": ("Qwen3.5-2B-Q4_K_M.gguf", "qwen", 2.0),
    "Qwen3.5-4B": ("Qwen3.5-4B-Q4_K_M.gguf", "qwen", 4.0),
}

# Merge strategies swept against each model (G4/G5/G6 registry flags).
STRATEGIES: tuple[str, ...] = ("strict", "reground", "flat")


def _iter_session_keys(
    conn: sqlite3.Connection,
    scope: str | None,
    resolver: ProjectResolver | None,
) -> Iterator[tuple[str, str]]:
    """Yield ``(project_id, session_id)`` for every ingested session, optionally
    restricted to a ``scope_path`` subtree.

    A session belongs to scope ``S`` iff ``S`` is in its project's inclusive
    ancestor chain (so ``''`` matches all, an exact scope matches itself, and a
    parent scope matches its whole subtree). Resolution is via G1's authoritative
    path — never a dash-split of the encoded id.
    """
    rows = conn.execute(
        """SELECT DISTINCT project_id, session_id
           FROM events
           WHERE session_id IS NOT NULL
           ORDER BY project_id, session_id"""
    ).fetchall()
    for project_id, session_id in rows:
        if scope is None:
            yield project_id, session_id
        else:
            assert resolver is not None  # guaranteed by summarise_sessions
            if scope in ancestor_scopes(resolver, project_id):
                yield project_id, session_id


def summarise_sessions(
    conn: sqlite3.Connection,
    engine: SummaryEngine,
    model: str,
    scope: str | None = None,
    resolver: ProjectResolver | None = None,
) -> int:
    """Summarise every ingested session (optionally within ``scope``) for ``model``.

    Delegates each session to :func:`summarise_session`, whose content-hash guard
    makes already-current sessions zero-cost — so a cron-triggered run only does
    work for the not-yet-current sessions and needs no fresh ingest. Returns the
    number of sessions visited.
    """
    if scope is not None and resolver is None:
        # Fail loud: scope filtering is meaningless without a resolver to place
        # each project in the hierarchy. Never silently summarise everything.
        raise ValueError("scope filtering requires a ProjectResolver")
    visited = 0
    for project_id, session_id in _iter_session_keys(conn, scope, resolver):
        summarise_session(conn, project_id, session_id, engine, model)
        visited += 1
    return visited


# ---------------------------------------------------------------------------
# G10 benchmark (CR1) — self-contained, reuses the production summariser path.
#
# Sweeps {model × strategy}, scores each model's session extraction against a
# curated gold set with the deterministic ROUGE-L/BLEU/F1 scorer, and tracks
# completion by result-file existence (manifest pattern). It calls the real
# summarise_session / roll_up_scopes — no parallel reimplementation, no stub at
# the generation seam: the only boundary is muninn_chat (the GGUF itself).
# ---------------------------------------------------------------------------


def gguf_path(model_id: str) -> Path | None:
    """Resolve a model_id to an on-disk GGUF, searching MODELS_DIRS in order.

    Returns ``None`` when no build is present (the inventory/manifest reports it
    missing rather than pretending it exists)."""
    spec = MODEL_REGISTRY.get(model_id)
    if spec is None:
        return None
    filename = spec[0]
    for directory in MODELS_DIRS:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def _gguf_available(model_id: str) -> bool:
    return gguf_path(model_id) is not None


def model_inventory() -> list[dict[str, Any]]:
    """Every desired model with its downloaded status (CR1.1)."""
    inventory: list[dict[str, Any]] = []
    for model_id, (filename, family, billions) in MODEL_REGISTRY.items():
        path = gguf_path(model_id)
        inventory.append(
            {
                "model": model_id,
                "family": family,
                "billions": billions,
                "gguf": filename,
                "downloaded": path is not None,
                "path": str(path) if path is not None else None,
            }
        )
    return inventory


def permutation_id(model_id: str, strategy: str) -> str:
    """Deterministic slug for a sweep cell (valid filename + CLI arg)."""
    return f"{model_id}__{strategy}"


def check_status(results_dir: Path, perm_id: str) -> bool:
    """A permutation is done when its result file exists."""
    return (results_dir / f"{perm_id}.json").exists()


def bench_permutations(results_dir: Path) -> list[dict[str, Any]]:
    """The model × strategy grid with completion + GGUF availability.

    ``sort_key`` orders smallest-model-first (least work). A cell whose GGUF is
    absent is flagged ``available=False`` (and logged once per model by the
    manifest), never silently dropped (ADR10.2)."""
    perms: list[dict[str, Any]] = []
    for model_id, (_filename, family, billions) in MODEL_REGISTRY.items():
        available = _gguf_available(model_id)
        for strategy in STRATEGIES:
            pid = permutation_id(model_id, strategy)
            perms.append(
                {
                    "permutation_id": pid,
                    "model": model_id,
                    "family": family,
                    "strategy": strategy,
                    "sort_key": (billions, model_id, strategy),
                    "label": f"{model_id} / {strategy}",
                    "done": check_status(results_dir, pid),
                    "available": available,
                }
            )
    return perms


def load_references(references_dir: Path) -> list[dict[str, Any]]:
    """Load the curated gold reference set (CR1.3).

    Each ``*.json`` is ``{project_id, session_id, gold:{task_summary, patterns,
    decisions_values}}`` — a real session plus its hand-curated 3-lens gold."""
    refs: list[dict[str, Any]] = []
    for ref_file in sorted(references_dir.glob("*.json")):
        refs.append(json.loads(ref_file.read_text(encoding="utf-8")))
    return refs


def _lens_text(lenses: dict[str, str] | sqlite3.Row) -> str:
    return " ".join(str(lenses[k]) for k in ("task_summary", "patterns", "decisions_values"))


def run_permutation(
    conn: sqlite3.Connection,
    model_id: str,
    strategy: str,
    references: list[dict[str, Any]],
    *,
    grain: str,
    resolver: ProjectResolver,
) -> dict[str, Any]:
    """Run one real permutation: summarise the reference sessions with ``model_id``,
    score each extraction against its gold, and roll up via ``strategy``.

    Reuses the production path (`summarise_session` / `roll_up_scopes`); the only
    external boundary is ``muninn_chat`` (the registered GGUF on ``conn``). The
    automated score screens the *model* (extraction quality, ADR10.1); the
    *strategy*'s rollups are produced for the human review (T10.7)."""
    engine = MuninnSummaryEngine(conn)
    scores: list[dict[str, float]] = []
    errors: list[str] = []
    for ref in references:
        pid, sid = ref["project_id"], ref["session_id"]
        try:
            summarise_session(conn, pid, sid, engine, model_id)
        except (sqlite3.OperationalError, ValueError) as exc:
            # A real model-boundary outcome (context overflow, non-JSON reply)
            # is benchmark data, not a crash — record it and keep sweeping.
            errors.append(f"extract {sid[:8]}: {exc}")
            continue
        row = conn.execute(
            """SELECT task_summary, patterns, decisions_values FROM session_summaries
               WHERE project_id = ? AND session_id = ? AND model = ?""",
            (pid, sid, model_id),
        ).fetchone()
        if row is None:  # session had no human prompts (T2.5) — not scorable
            continue
        scores.append(score_summary(_lens_text(row), _lens_text(ref["gold"])))

    # The rollup is where reground folds excerpts in and can exceed context, or a
    # model can emit non-JSON. That failure is the strategy's empirical cost (G10)
    # — record it as a first-class result rather than aborting the whole sweep.
    rollup_rows = 0
    rollup_error: str | None = None
    try:
        rollup_rows = roll_up_scopes(conn, engine, strategy, model_id, grain, resolver=resolver)
    except (sqlite3.OperationalError, ValueError) as exc:
        rollup_error = str(exc)

    n = len(scores)

    def _mean(metric: str) -> float:
        return round(sum(s[metric] for s in scores) / n, 4) if n else 0.0

    status = "ok" if rollup_error is None and not errors else "error"
    return {
        "permutation_id": permutation_id(model_id, strategy),
        "model": model_id,
        "strategy": strategy,
        "grain": grain,
        "status": status,
        "n_scored": n,
        "rollup_rows": rollup_rows,
        "rollup_error": rollup_error,
        "extract_errors": errors,
        "rouge_l": _mean("rouge_l"),
        "bleu": _mean("bleu"),
        "f1": _mean("f1"),
    }


def save_result(results_dir: Path, perm_id: str, record: dict[str, Any]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{perm_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def _combined(record: dict[str, Any]) -> float:
    return (
        float(record.get("rouge_l", 0.0))
        + float(record.get("bleu", 0.0))
        + float(record.get("f1", 0.0))
    ) / 3


def rank_results(results_dir: Path) -> list[dict[str, Any]]:
    """All result rows, ranked highest-combined-score first (ties by id)."""
    rows: list[dict[str, Any]] = []
    for result_file in sorted(results_dir.glob("*.json")):
        record = json.loads(result_file.read_text(encoding="utf-8"))
        record["combined"] = _combined(record)
        rows.append(record)
    rows.sort(key=lambda r: (-r["combined"], r["permutation_id"]))
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _help(p: argparse.ArgumentParser):  # type: ignore[no-untyped-def]
    """Return a handler that prints help for parser ``p`` (the default func)."""

    def _print_help(_: argparse.Namespace) -> None:
        p.print_help()

    return _print_help


def _open_chat_connection(model: str, model_path: Path | None = None) -> sqlite3.Connection:
    """Open the cache with ``sqlite-muninn`` loaded and ``model`` registered as a
    chat model, so :class:`MuninnSummaryEngine` can call ``muninn_chat``.

    ``model_path`` is the GGUF to register under the name ``model``; when omitted
    it falls back to the KG default chat model (``ensure_chat_model_downloaded``).
    The benchmark passes the registry-resolved path for a specific model id."""
    conn = sqlite3.connect(str(CACHE_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_muninn.load(conn)
    conn.enable_load_extension(False)
    path = model_path if model_path is not None else ensure_chat_model_downloaded()
    try:
        conn.execute(
            "INSERT INTO temp.muninn_chat_models(name, model) SELECT ?, muninn_chat_model(?)",
            (model, str(path)),
        )
    except sqlite3.OperationalError as exc:
        if "already loaded" not in str(exc).lower():
            raise
    return conn


def cmd_sessions(args: argparse.Namespace) -> None:
    conn = _open_chat_connection(args.model)
    try:
        engine = MuninnSummaryEngine(conn)
        resolver = ProjectResolver(PROJECTS_PATH) if args.scope is not None else None
        visited = summarise_sessions(conn, engine, args.model, scope=args.scope, resolver=resolver)
        log.info("summarise sessions: visited %d session(s) for model %s", visited, args.model)
    finally:
        conn.close()


def cmd_rollup(args: argparse.Namespace) -> None:
    conn = _open_chat_connection(args.model)
    try:
        engine = MuninnSummaryEngine(conn)
        resolver = ProjectResolver(PROJECTS_PATH)
        written = roll_up_scopes(
            conn,
            engine,
            args.strategy,
            args.model,
            args.grain,
            level=args.level,
            resolver=resolver,
        )
        log.info(
            "rollup: wrote %d row(s) for strategy=%s model=%s level=%s grain=%s",
            written,
            args.strategy,
            args.model,
            args.level,
            args.grain,
        )
    finally:
        conn.close()


def cmd_models(args: argparse.Namespace) -> None:
    """Inventory: which desired GGUFs are downloaded vs missing (CR1.1)."""
    inventory = model_inventory()
    have = sum(1 for m in inventory if m["downloaded"])
    print(f"=== Model inventory ({have}/{len(inventory)} downloaded) ===")
    for m in inventory:
        mark = "OK  " if m["downloaded"] else "MISS"
        where = m["path"] or f"(not found in {', '.join(str(d) for d in MODELS_DIRS)})"
        print(f"  [{mark}] {m['model']:<14} {m['family']:<6} ~{m['billions']}B  {where}")


def cmd_manifest(args: argparse.Namespace) -> None:
    """List sweep permutations with done/missing status (manifest pattern, CR1.2)."""
    perms = bench_permutations(args.results_dir)
    total = len(perms)
    total_done = sum(1 for p in perms if p["done"])

    if args.missing:
        # Runnable-missing: not done AND its GGUF is on disk.
        perms = [p for p in perms if not p["done"] and p["available"]]
    if args.done:
        perms = [p for p in perms if p["done"]]
    if args.sort == "name":
        perms = sorted(perms, key=lambda p: p["permutation_id"])
    else:
        perms = sorted(perms, key=lambda p: p["sort_key"])  # cheapest (smallest) first
    if args.limit is not None:
        perms = perms[: args.limit]

    if args.commands:
        suffix = " --force" if args.force else ""
        base = "uv run -m claude_code_sessions.summarise_cli run --id"
        for p in perms:
            print(f"{base} {p['permutation_id']}{suffix}")
        return

    # Log skipped (no-GGUF) models once — never silently dropped (ADR10.2).
    for model_id in MODEL_REGISTRY:
        if not _gguf_available(model_id):
            log.warning("skipping %s: no GGUF build on disk (run `models` to see paths)", model_id)

    print(f"=== Manifest ({total_done}/{total} done) ===")
    for p in perms:
        mark = "DONE" if p["done"] else ("MISS" if p["available"] else "NOGG")
        print(f"  [{mark}] {p['permutation_id']:<28} {p['label']}")


def cmd_run(args: argparse.Namespace) -> None:
    """Run + score one permutation for real (CR1.4)."""
    perms = {p["permutation_id"]: p for p in bench_permutations(args.results_dir)}
    if args.id not in perms:  # fail loud — never run an unknown cell
        raise SystemExit(f"unknown permutation id: {args.id!r} (see `manifest`)")
    perm = perms[args.id]
    if not perm["available"]:
        raise SystemExit(f"no GGUF on disk for model {perm['model']!r} (see `models`)")
    if perm["done"] and not args.force:
        log.info("skip (already done): %s — pass --force to re-run", args.id)
        return

    references = load_references(args.references_dir)
    if not references:
        raise SystemExit(f"no reference set found in {args.references_dir} (see CR1.3)")

    model_id, strategy = perm["model"], perm["strategy"]
    conn = _open_chat_connection(model_id, gguf_path(model_id))
    try:
        resolver = ProjectResolver(PROJECTS_PATH)
        t0 = time.monotonic()
        record = run_permutation(
            conn, model_id, strategy, references, grain=args.grain, resolver=resolver
        )
        record["seconds"] = round(time.monotonic() - t0, 2)
        save_result(args.results_dir, args.id, record)
        log.info(
            "scored %s [%s]: rouge_l=%.3f bleu=%.3f f1=%.3f (%d sessions, %d rollups, %.1fs)",
            args.id,
            record["status"],
            record["rouge_l"],
            record["bleu"],
            record["f1"],
            record["n_scored"],
            record["rollup_rows"],
            record["seconds"],
        )
        if record["status"] != "ok":
            log.warning("  %s rollup_error=%s", args.id, record.get("rollup_error"))
    finally:
        conn.close()


def cmd_report(args: argparse.Namespace) -> None:
    """Rank result rows into the benchmark report (CR1.5)."""
    ranked = rank_results(args.results_dir)
    lines = [
        "# G10 Benchmark Report",
        "",
        "Permutations ranked by the automated screen — mean(ROUGE-L, BLEU, F1) of each",
        "model's session extraction against the curated gold set. The metric *screens",
        "the model*; merge-strategy faithfulness is the human's call (T10.7) reading the",
        "rollups in the G8/G9 UI. These numbers rank and surface; they do not decide.",
        "",
        "| Rank | Permutation | model | strategy | n | ROUGE-L | BLEU | F1 | Combined | "
        "status | sec |",
        "|------|-------------|-------|----------|--:|--------:|-----:|---:|---------:|"
        "--------|----:|",
    ]
    for i, r in enumerate(ranked, start=1):
        marker = "  — review candidate" if i == 1 else ""
        status = r.get("status", "ok")
        lines.append(
            f"| {i} | `{r['permutation_id']}`{marker} | {r.get('model', '')} | "
            f"{r.get('strategy', '')} | {r.get('n_scored', 0)} | "
            f"{float(r.get('rouge_l', 0.0)):.3f} | {float(r.get('bleu', 0.0)):.3f} | "
            f"{float(r.get('f1', 0.0)):.3f} | {r['combined']:.3f} | {status} | "
            f"{r.get('seconds', 0)} |"
        )

    # Surface every model-boundary failure verbatim — these ARE the G10 findings
    # for a strategy that won't fit (reground) on a given model, not noise to hide.
    failures = [
        (r["permutation_id"], r.get("rollup_error"), r.get("extract_errors") or [])
        for r in ranked
        if r.get("rollup_error") or r.get("extract_errors")
    ]
    if failures:
        lines += ["", "## Strategy failures (empirical cost)", ""]
        for pid, rollup_err, extract_errs in failures:
            if rollup_err:
                lines.append(f"- `{pid}` — rollup failed: {rollup_err}")
            for err in extract_errs:
                lines.append(f"- `{pid}` — {err}")

    top = ranked[0]["permutation_id"] if ranked else "(no results yet)"
    lines += [
        "",
        "## Recommendation",
        "",
        f"Top automated candidate: `{top}`.",
        "",
        "<!-- PROCEED/ABANDON pending the binding human taste review (T10.7) of the top "
        "survivors via the G8/G9 UI. The reference metrics above do not decide. -->",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote benchmark report: %s (%d permutations)", args.output, len(ranked))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="summarise_cli",
        description="Manual, ingest-decoupled summarisation runners + G10 benchmark (G2/G3/G10).",
    )
    parser.set_defaults(func=_help(parser))
    sub = parser.add_subparsers(dest="command", required=False)

    sessions_p = sub.add_parser(
        "sessions", help="Summarise sessions ingested to date (content-hash guarded)"
    )
    sessions_p.add_argument(
        "--model", required=True, help="Chat model name (provenance + registration)"
    )
    sessions_p.add_argument(
        "--scope", default=None, help="Restrict to a scope_path subtree, e.g. 'clients/acme'"
    )
    sessions_p.set_defaults(func=cmd_sessions)

    rollup_p = sub.add_parser(
        "rollup", help="Roll up one level band at one grain off existing session_summaries"
    )
    rollup_p.add_argument("--strategy", required=True, help="Merge strategy flag (registry key)")
    rollup_p.add_argument(
        "--model", required=True, help="Summariser model name (provenance + scope)"
    )
    rollup_p.add_argument(
        "--level", default=None, help="Level band to roll up: 'leaf' or 'root' (default: all tiers)"
    )
    rollup_p.add_argument(
        "--grain", default="day", choices=["day", "week", "month"], help="Time granularity"
    )
    rollup_p.set_defaults(func=cmd_rollup)

    # --- G10 benchmark subcommands (CR1) -----------------------------------
    models_p = sub.add_parser("models", help="Inventory: which desired GGUFs are downloaded")
    models_p.set_defaults(func=cmd_models)

    manifest_p = sub.add_parser("manifest", help="List sweep permutations with done/missing status")
    manifest_p.add_argument("--missing", action="store_true", help="Only runnable incomplete cells")
    manifest_p.add_argument("--done", action="store_true", help="Only completed cells")
    manifest_p.add_argument(
        "--commands", action="store_true", help="Emit one `run` command per cell"
    )
    manifest_p.add_argument("--force", action="store_true", help="With --commands: append --force")
    manifest_p.add_argument("--sort", choices=["size", "name"], default="size", help="Sort order")
    manifest_p.add_argument(
        "--limit", type=int, default=None, help="Limit to first N after filtering"
    )
    manifest_p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    manifest_p.set_defaults(func=cmd_manifest)

    run_p = sub.add_parser("run", help="Run + score one permutation (real model)")
    run_p.add_argument("--id", required=True, help="Permutation id (see `manifest`)")
    run_p.add_argument("--force", action="store_true", help="Re-run even if already done")
    run_p.add_argument("--grain", default="day", choices=["day", "week", "month"])
    run_p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run_p.add_argument("--references-dir", type=Path, default=DEFAULT_REFERENCES_DIR)
    run_p.set_defaults(func=cmd_run)

    report_p = sub.add_parser("report", help="Rank result rows into the benchmark report")
    report_p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    report_p.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    report_p.set_defaults(func=cmd_report)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
