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
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import sqlite_muninn

from claude_code_sessions.config import CACHE_DB_PATH, PROJECTS_PATH
from claude_code_sessions.database.sqlite.embeddings import (
    EMBED_MAX_CHARS,
)
from claude_code_sessions.database.sqlite.embeddings import (
    GGUF_MODEL_NAME as EMBED_MODEL_NAME,
)
from claude_code_sessions.database.sqlite.embeddings import (
    ensure_model_downloaded as ensure_embed_model_downloaded,
)
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
DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs" / "plans" / "summariser-G10-REPORT.md"

# Where GGUF chat models are searched, in priority order (CR1). The cache dir is
# canonical; the sqlite-vector-graph models dir is an opportunistic fallback.
MODELS_DIRS: tuple[Path, ...] = (
    Path.home() / ".claude" / "cache" / "models",
    Path.home() / "play" / "sqlite-vector-graph" / "models",
)

# Known model inventory: model_id → (gguf filename, family, approx params in
# billions). The inventory subcommand lists all of these; the sweep itself runs
# only BENCH_MODELS below.
MODEL_REGISTRY: dict[str, tuple[str, str, float]] = {
    "gemma-4-E2B": ("gemma-4-E2B-it-Q4_K_M.gguf", "gemma", 2.0),
    "gemma-4-E4B": ("gemma-4-E4B-it-Q4_K_M.gguf", "gemma", 4.0),
    "Qwen3.5-0.8B": ("Qwen3.5-0.8B-Q4_K_M.gguf", "qwen", 0.8),
    "Qwen3.5-2B": ("Qwen3.5-2B-Q4_K_M.gguf", "qwen", 2.0),
    "Qwen3.5-4B": ("Qwen3.5-4B-Q4_K_M.gguf", "qwen", 4.0),
    "Qwen3.5-9B": ("Qwen3.5-9B-Q4_K_M.gguf", "qwen", 9.0),
    "Mistral-7B": ("Mistral-7B-Instruct-v0.3-Q4_K_M.gguf", "mistral", 7.0),
    "Llama-3.1-8B": ("Llama-3.1-8B-Instruct-Q4_K_M.gguf", "llama", 8.0),
}

# The two models the ADR3.2 follow-up runs on (2026-06-01): Qwen3.5-2B (≈2× the
# throughput) and Llama-3.1-8B (128k context — needed so reground survives the
# bigger monthly / client-domain buckets without overflow / CR3 batching).
BENCH_MODELS: tuple[str, ...] = ("Qwen3.5-2B", "Llama-3.1-8B")

# Merge strategies swept (G4/G5/G6). The follow-up focuses on flat vs reground at
# the deep/coarse levels; strict stays in as the compounding-drift reference.
STRATEGIES: tuple[str, ...] = ("strict", "reground", "flat")

# day → week → month: the coarse-grain axis the ADR3.2 regime test exercises.
GRAINS: tuple[str, ...] = ("day", "week", "month")

# Six real projects across THREE domains, including a depth-3 client branch
# (clients/<client>/<project>) so the trie tests multi-height domain refinement:
# 6 project scopes + sub-domains (clients/nine, clients/carto) + domains
# (play, work, clients) + root. A session is in-scope iff one of these is in its
# inclusive ancestor chain (G1 authoritative resolution).
BENCH_SCOPES: tuple[str, ...] = (
    "play/claude-code-sessions",
    "play/sqlite-vector-graph",
    "work/agent-capabilities",
    "work/rapid-whitelabelling",
    "clients/nine/agt-nam-self-service-agent",
    "clients/carto/carto-ada-gap-analysis",
)

# Default window in days. The ADR3.2 follow-up overrides with --since 2025-11-01
# (~7 months) to capture clients/nine's engagement (ended 2026-01-21).
BENCH_SINCE_DAYS = 7


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
# Sweeps {model × strategy × grain} over the REAL ingested dogfood corpus (no
# fabricated gold). Each generated summary is scored by *source grounding*: its
# ROUGE-L/BLEU/F1 overlap against the actual human-prompt text it derives from —
# the corpus itself is the reference. Two grounding scores per cell:
#   * session grounding — a session summary vs that session's real human prompts
#     (screens the MODEL's extraction faithfulness, ADR10.1);
#   * rollup grounding  — a scope's rolled-up summary vs the concatenated real
#     source beneath that scope (screens the STRATEGY's drift up the hierarchy —
#     exactly what reground/G5 exists to prevent).
# Completion is tracked by result-file existence (manifest pattern). It calls the
# real summarise_session / roll_up_scopes — no reimplementation, no stub at the
# generation seam: the only boundary is muninn_chat (the GGUF itself). The human
# taste verdict over the rollups in the UI stays the binding gate (T10.7).
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


def permutation_id(model_id: str, strategy: str, grain: str) -> str:
    """Deterministic slug for a sweep cell (valid filename + CLI arg)."""
    return f"{model_id}__{strategy}__{grain}"


def check_status(results_dir: Path, perm_id: str) -> bool:
    """A permutation is done when its result file exists."""
    return (results_dir / f"{perm_id}.json").exists()


def bench_permutations(results_dir: Path) -> list[dict[str, Any]]:
    """The model × strategy × grain grid with completion + GGUF availability.

    ``sort_key`` orders smallest-model-first (least work). A cell whose GGUF is
    absent is flagged ``available=False`` (and logged once per model by the
    manifest), never silently dropped (ADR10.2)."""
    perms: list[dict[str, Any]] = []
    for model_id in BENCH_MODELS:
        _filename, family, billions = MODEL_REGISTRY[model_id]
        available = _gguf_available(model_id)
        for strategy in STRATEGIES:
            for grain in GRAINS:
                pid = permutation_id(model_id, strategy, grain)
                perms.append(
                    {
                        "permutation_id": pid,
                        "model": model_id,
                        "family": family,
                        "strategy": strategy,
                        "grain": grain,
                        "sort_key": (billions, model_id, strategy, grain),
                        "label": f"{model_id} / {strategy} / {grain}",
                        "done": check_status(results_dir, pid),
                        "available": available,
                    }
                )
    return perms


def _lens_text(lenses: dict[str, str] | sqlite3.Row) -> str:
    return " ".join(str(lenses[k]) for k in ("task_summary", "patterns", "decisions_values"))


def bench_session_keys(
    conn: sqlite3.Connection,
    resolver: ProjectResolver,
    scopes: tuple[str, ...],
    since: str | None = None,
) -> list[tuple[str, str]]:
    """Every ingested ``(project_id, session_id)`` whose scope falls under one of
    ``scopes`` — the real corpus the sweep runs over, de-duplicated and ordered.
    With ``since`` (ISO timestamp), only sessions with a human event at or after
    it are kept (the last-week window).

    Membership is by G1's authoritative ancestor chain (``scope in
    ancestor_scopes``), never a dash-split of the encoded id. Projects that can't
    be resolved are skipped (they can't be placed in the hierarchy)."""
    keys: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    if since is None:
        rows = conn.execute(
            """SELECT DISTINCT project_id, session_id FROM events
               WHERE session_id IS NOT NULL ORDER BY project_id, session_id"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT DISTINCT project_id, session_id FROM events
               WHERE session_id IS NOT NULL AND msg_kind = 'human' AND timestamp >= ?
               ORDER BY project_id, session_id""",
            (since,),
        ).fetchall()
    for project_id, session_id in rows:
        try:
            chain = set(ancestor_scopes(resolver, project_id))
        except KeyError:
            continue
        if chain & set(scopes) and (project_id, session_id) not in seen:
            seen.add((project_id, session_id))
            keys.append((project_id, session_id))
    return keys


def _session_source_text(conn: sqlite3.Connection, project_id: str, session_id: str) -> str:
    """A session's real human-prompt text, chronological — the grounding reference."""
    rows = conn.execute(
        """SELECT message_content FROM events
           WHERE project_id = ? AND session_id = ? AND msg_kind = 'human'
                 AND message_content IS NOT NULL
           ORDER BY timestamp, line_number""",
        (project_id, session_id),
    ).fetchall()
    return "\n".join(str(r[0]) for r in rows)


# Every metric score_summary emits, averaged across a permutation's rows.
_SCORE_METRICS = (
    "rouge_l",
    "bleu",
    "f1",
    "compression_ratio",
    "rouge_l_ceiling",
    "rouge_l_normalised",
    "lead_combined",
    "embed_cosine",
)


# Cap on how many EMBED_MAX_CHARS-sized chunks of a (possibly huge) reference we
# mean-pool into one embedding — bounds the cosine cost while staying representative.
_MAX_EMBED_CHUNKS = 8


def _embed(conn: sqlite3.Connection, text: str) -> Any:
    """A unit-norm embedding of ``text`` — mean-pooled over up to _MAX_EMBED_CHUNKS
    EMBED_MAX_CHARS-sized pieces (muninn_embed returns L2-normalised float32)."""
    pieces = [text[i : i + EMBED_MAX_CHARS] for i in range(0, len(text), EMBED_MAX_CHARS)]
    pieces = pieces[:_MAX_EMBED_CHUNKS] or [""]
    vecs = [
        np.frombuffer(
            conn.execute("SELECT muninn_embed(?, ?)", (EMBED_MODEL_NAME, p)).fetchone()[0],
            dtype=np.float32,
        )
        for p in pieces
    ]
    pooled = np.mean(vecs, axis=0)
    norm = float(np.linalg.norm(pooled))
    return pooled / norm if norm else pooled


def make_embed_cosine(conn: sqlite3.Connection) -> Callable[[str, str], float]:
    """Register the local embedder on ``conn`` and return a ``(candidate,
    reference) -> cosine`` function (CR4.3). Semantic grounding: unlike BLEU it
    credits paraphrase — high cosine with low BLEU = strong abstractive grounding
    (SCORING.md §4). Fail-loud: if the embedder can't load, this raises."""
    row = conn.execute(
        "SELECT name FROM temp.muninn_models WHERE name = ?", (EMBED_MODEL_NAME,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO temp.muninn_models(name, model) SELECT ?, muninn_embed_model(?)",
            (EMBED_MODEL_NAME, str(ensure_embed_model_downloaded())),
        )

    def _cosine(candidate: str, reference: str) -> float:
        return round(float(_embed(conn, candidate) @ _embed(conn, reference)), 4)

    return _cosine


def _mean_scores(scores: list[dict[str, float]]) -> dict[str, float]:
    if not scores:
        return dict.fromkeys(_SCORE_METRICS, 0.0)
    return {
        m: round(sum(s.get(m, 0.0) for s in scores) / len(scores), 4) for m in _SCORE_METRICS
    }


def run_permutation(
    conn: sqlite3.Connection,
    model_id: str,
    strategy: str,
    grain: str,
    *,
    resolver: ProjectResolver,
    session_keys: list[tuple[str, str]],
    embed_cosine: Callable[[str, str], float],
) -> dict[str, Any]:
    """Run one real permutation over ``session_keys`` and score by source grounding.

    Reuses the production path (`summarise_session` / `roll_up_scopes`); the only
    external boundary is ``muninn_chat`` (the registered GGUF on ``conn``). There
    is no fabricated gold: every score is the generated summary's overlap against
    the *real* human-prompt text it derives from. Two scores —
      * session grounding — a session summary vs its own prompts (screens model);
      * rollup grounding — a scope's rollup vs the concatenated real source under
        that scope at this grain (screens the strategy's drift up the hierarchy).
    Model-boundary failures (context overflow, non-JSON) are recorded as data."""
    engine = MuninnSummaryEngine(conn)
    # Per-session real source + ancestor chain (grounding reference + scope map).
    sources: dict[tuple[str, str], str] = {}
    chains: dict[tuple[str, str], set[str]] = {}
    for pid, sid in session_keys:
        try:
            chains[(pid, sid)] = set(ancestor_scopes(resolver, pid))
        except KeyError:
            continue  # unresolvable project — can't place it in the hierarchy
        sources[(pid, sid)] = _session_source_text(conn, pid, sid)

    # --- session grounding: each summary vs its own real human prompts ---
    session_scores: list[dict[str, float]] = []
    errors: list[str] = []
    for pid, sid in session_keys:
        if (pid, sid) not in chains:
            continue
        try:
            summarise_session(conn, pid, sid, engine, model_id)
        except (sqlite3.OperationalError, ValueError) as exc:
            errors.append(f"extract {sid[:8]}: {exc}")
            continue
        row = conn.execute(
            """SELECT task_summary, patterns, decisions_values FROM session_summaries
               WHERE project_id = ? AND session_id = ? AND model = ?""",
            (pid, sid, model_id),
        ).fetchone()
        src = sources.get((pid, sid), "")
        if row is None or not src.strip():
            continue  # no human prompts (T2.5) — nothing real to ground against
        cand = _lens_text(row)
        score = score_summary(cand, src)
        score["embed_cosine"] = embed_cosine(cand, src)
        session_scores.append(score)

    # --- rollups (strategy × grain) over the just-written session summaries ---
    rollup_rows = 0
    rollup_error: str | None = None
    try:
        rollup_rows = roll_up_scopes(conn, engine, strategy, model_id, grain, resolver=resolver)
    except (sqlite3.OperationalError, ValueError) as exc:
        rollup_error = str(exc)

    # --- rollup grounding: each scope's rolled-up summary (this grain) vs the
    #     concatenated real source beneath it (the STRATEGY discriminator) ---
    by_scope: dict[str, list[str]] = {}
    for r in conn.execute(
        """SELECT scope_path, task_summary, patterns, decisions_values
           FROM rollup_summaries
           WHERE strategy = ? AND model = ? AND time_granularity = ?""",
        (strategy, model_id, grain),
    ).fetchall():
        by_scope.setdefault(r["scope_path"], []).append(_lens_text(r))
    rollup_scores: list[dict[str, float]] = []
    for scope_path, texts in by_scope.items():
        ref = "\n".join(
            sources[k]
            for k in session_keys
            if k in chains and scope_path in chains[k] and sources.get(k, "").strip()
        )
        if ref.strip():
            cand = " ".join(texts)
            score = score_summary(cand, ref)
            score["embed_cosine"] = embed_cosine(cand, ref)
            rollup_scores.append(score)

    sess = _mean_scores(session_scores)
    roll = _mean_scores(rollup_scores)
    status = "ok" if rollup_error is None and not errors else "error"
    record: dict[str, Any] = {
        "permutation_id": permutation_id(model_id, strategy, grain),
        "model": model_id,
        "strategy": strategy,
        "grain": grain,
        "status": status,
        "n_sessions_scored": len(session_scores),
        "n_rollups_scored": len(rollup_scores),
        "rollup_rows": rollup_rows,
        "rollup_error": rollup_error,
        "extract_errors": errors,
    }
    for metric in _SCORE_METRICS:
        record[f"session_{metric}"] = sess[metric]
        record[f"rollup_{metric}"] = roll[metric]
    return record


def save_result(results_dir: Path, perm_id: str, record: dict[str, Any]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / f"{perm_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def _combined(record: dict[str, Any]) -> float:
    """Rank by the STRATEGY discriminator — rollup grounding (how well a rollup
    stays anchored to real source up the hierarchy), the axis the T10.7 verdict
    judges. A cell that produced **no** scorable rollup has no strategy signal and
    scores 0.0 — never the session score (which is identical across a model's
    cells, so falling back to it would let a zero-output error cell rank first)."""
    if not record.get("n_rollups_scored", 0):
        return 0.0
    return (
        float(record.get("rollup_rouge_l", 0.0))
        + float(record.get("rollup_bleu", 0.0))
        + float(record.get("rollup_f1", 0.0))
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
    for model_id in BENCH_MODELS:
        if not _gguf_available(model_id):
            log.warning("skipping %s: no GGUF build on disk (run `models` to see paths)", model_id)

    print(f"=== Manifest ({total_done}/{total} done) ===")
    for p in perms:
        mark = "DONE" if p["done"] else ("MISS" if p["available"] else "NOGG")
        print(f"  [{mark}] {p['permutation_id']:<28} {p['label']}")


def cmd_run(args: argparse.Namespace) -> None:
    """Run + source-ground-score one permutation for real over the dogfood corpus."""
    perms = {p["permutation_id"]: p for p in bench_permutations(args.results_dir)}
    if args.id not in perms:  # fail loud — never run an unknown cell
        raise SystemExit(f"unknown permutation id: {args.id!r} (see `manifest`)")
    perm = perms[args.id]
    if not perm["available"]:
        raise SystemExit(f"no GGUF on disk for model {perm['model']!r} (see `models`)")
    if perm["done"] and not args.force:
        log.info("skip (already done): %s — pass --force to re-run", args.id)
        return

    model_id, strategy, grain = perm["model"], perm["strategy"], perm["grain"]
    scopes = tuple(args.scope) if args.scope else BENCH_SCOPES
    since = args.since or (datetime.now(UTC) - timedelta(days=args.since_days)).date().isoformat()
    conn = _open_chat_connection(model_id, gguf_path(model_id))
    try:
        resolver = ProjectResolver(PROJECTS_PATH)
        session_keys = bench_session_keys(conn, resolver, scopes, since=since)
        if not session_keys:
            raise SystemExit(
                f"no sessions under {scopes} since {since} (nothing to summarise)"
            )
        log.info(
            "run %s: %d real sessions under %s since %s",
            args.id, len(session_keys), ", ".join(scopes), since,
        )
        t0 = time.monotonic()
        record = run_permutation(
            conn, model_id, strategy, grain, resolver=resolver, session_keys=session_keys,
            embed_cosine=make_embed_cosine(conn),
        )
        record["seconds"] = round(time.monotonic() - t0, 2)
        record["scopes"] = list(scopes)
        save_result(args.results_dir, args.id, record)
        log.info(
            "scored %s [%s]: session(r/b/f)=%.3f/%.3f/%.3f rollup(r/b/f)=%.3f/%.3f/%.3f "
            "(%d sess, %d rollups scored, %.0fs)",
            args.id,
            record["status"],
            record["session_rouge_l"],
            record["session_bleu"],
            record["session_f1"],
            record["rollup_rouge_l"],
            record["rollup_bleu"],
            record["rollup_f1"],
            record["n_sessions_scored"],
            record["n_rollups_scored"],
            record["seconds"],
        )
        if record["status"] != "ok":
            log.warning("  %s rollup_error=%s", args.id, record.get("rollup_error"))
    finally:
        conn.close()


def cmd_report(args: argparse.Namespace) -> None:
    """One results table per model — strategies × grain × grounding score × speed."""
    ranked = rank_results(args.results_dir)
    lines = [
        "# G10 Benchmark Report",
        "",
        "Scoped real sweep: the four benchmark projects (two `play`, two `work`), last week,",
        "two fastest models. The model is held constant per table so the **strategies** can be",
        "compared head-to-head on source grounding and speed.",
        "",
        "Every score is **source grounding** — the rolled-up summary's ROUGE-L/BLEU/F1 overlap",
        "against the *real* source beneath its scope (the corpus is the reference, no fabricated",
        "gold). Columns (see [SCORING.md](./summariser-SCORING.md)):",
        "",
        "- **roll r/b/f** — the lexical triple (relative screen).",
        "- **comp** — compression ratio (summary tokens / source tokens); the recall ceiling.",
        "- **norm** — ROUGE-L as a fraction of its compression-bounded ceiling (achievable %).",
        "- **lead** — combined score of a verbatim first-N-token extract (the extractive ceiling);",
        "  a good *abstractive* summary sits below it — that gap is abstraction the lexical",
        "  metrics can't credit.",
        "- **cos** — embedding cosine (summary vs source, local nomic-embed). Credits paraphrase:",
        "  **high cos with low BLEU = strong *abstractive* grounding** — what lexical misses.",
        "",
        "Absolutes are low by construction; *relative* ordering ranks. The binding PROCEED/ABANDON",
        "call is the human taste review of the rollups in the UI (T10.7).",
    ]

    def _triple(r: dict[str, Any], prefix: str) -> str:
        vals = (float(r.get(f"{prefix}_{m}", 0.0)) for m in ("rouge_l", "bleu", "f1"))
        return "/".join(f"{v:.3f}" for v in vals)

    def _best(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Highest combined among the ok cells (only fall back to error cells if
        none are ok) — a clean cell always beats a partial/zero error cell."""
        pool = [r for r in rows if r.get("status") == "ok"] or rows
        return max(pool, key=lambda r: r["combined"], default=None)

    models = [m for m in BENCH_MODELS if any(r.get("model") == m for r in ranked)]
    models += [m for m in {r.get("model") for r in ranked} if m and m not in models]
    for model_id in models:
        rows = sorted(
            (r for r in ranked if r.get("model") == model_id),
            key=lambda r: (r.get("strategy", ""), r.get("grain", "")),
        )
        best = _best(rows)
        lines += [
            "",
            f"## {model_id}",
            "",
            "| strategy | grain | n | roll r/b/f | comp | norm | lead | cos | combined | sec | "
            "status |",
            "|----------|-------|--:|------------|-----:|-----:|-----:|----:|---------:|----:|"
            "--------|",
        ]
        for r in rows:
            star = " ⭐" if r is best else ""
            lines.append(
                f"| {r.get('strategy', '')}{star} | {r.get('grain', '')} | "
                f"{r.get('n_rollups_scored', 0)} | {_triple(r, 'rollup')} | "
                f"{float(r.get('rollup_compression_ratio', 0.0)):.3f} | "
                f"{float(r.get('rollup_rouge_l_normalised', 0.0)):.3f} | "
                f"{float(r.get('rollup_lead_combined', 0.0)):.3f} | "
                f"{float(r.get('rollup_embed_cosine', 0.0)):.3f} | {r['combined']:.3f} | "
                f"{r.get('seconds', 0):.0f} | {r.get('status', 'ok')} |"
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

    lines += ["", "## Best strategy per model (automated screen, ok cells only)", ""]
    for model_id in models:
        rows = [r for r in ranked if r.get("model") == model_id]
        best = _best(rows)
        if best:
            lines.append(
                f"- **{model_id}**: `{best.get('strategy')}` "
                f"(grain {best.get('grain')}, combined {best['combined']:.3f})"
            )
    lines += [
        "",
        "<!-- PROCEED/ABANDON pending the binding human taste review (T10.7) of the rollups in "
        "the G8/G9 UI. The reference metrics above rank and surface; they do not decide. -->",
        "",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote benchmark report: %s (%d cells)", args.output, len(ranked))


def dump_summaries_md(conn: sqlite3.Connection, model_id: str) -> tuple[str, int]:
    """All of ``model_id``'s rollup summaries as markdown, grouped strategy→grain→scope."""
    rows = conn.execute(
        """SELECT strategy, time_granularity AS grain, scope_path, time_bucket,
                  task_summary, patterns, decisions_values
           FROM rollup_summaries WHERE model = ?
           ORDER BY strategy, time_granularity, scope_path, time_bucket""",
        (model_id,),
    ).fetchall()
    out = [f"# Rollup summaries — {model_id}", "", f"{len(rows)} summaries.", ""]
    cur: tuple[str, str] | None = None
    for r in rows:
        head = (r["strategy"], r["grain"])
        if head != cur:
            cur = head
            out += ["", f"## {r['strategy']} · {r['grain']}", ""]
        out += [
            f"### `{r['scope_path'] or '(all)'}` — {r['time_bucket']}",
            f"- **task_summary:** {r['task_summary']}",
            f"- **patterns:** {r['patterns']}",
            f"- **decisions_values:** {r['decisions_values']}",
            "",
        ]
    return "\n".join(out), len(rows)


def cmd_dump(args: argparse.Namespace) -> None:
    """Write every rollup summary per model to markdown (one file per model)."""
    conn = sqlite3.connect(f"file:{CACHE_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        models = [args.model] if args.model else list(BENCH_MODELS)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for model_id in models:
            md, n = dump_summaries_md(conn, model_id)
            out = args.output_dir / f"summaries_{model_id}.md"
            out.write_text(md, encoding="utf-8")
            log.info("wrote %s (%d summaries)", out, n)
    finally:
        conn.close()


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

    run_p = sub.add_parser("run", help="Run + source-ground-score one permutation (real model)")
    run_p.add_argument("--id", required=True, help="Permutation id model__strategy__grain")
    run_p.add_argument("--force", action="store_true", help="Re-run even if already done")
    run_p.add_argument(
        "--scope",
        nargs="+",
        default=None,
        help="Override the corpus scope_path(s) (default: the four benchmark projects).",
    )
    run_p.add_argument(
        "--since", default=None, help="ISO date floor for sessions (default: last BENCH_SINCE_DAYS)"
    )
    run_p.add_argument(
        "--since-days", type=int, default=BENCH_SINCE_DAYS, help="Window in days when --since unset"
    )
    run_p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    run_p.set_defaults(func=cmd_run)

    report_p = sub.add_parser("report", help="Per-model strategy×speed results table")
    report_p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    report_p.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    report_p.set_defaults(func=cmd_report)

    dump_p = sub.add_parser("dump", help="Write every rollup summary per model to markdown")
    dump_p.add_argument("--model", default=None, help="One model (default: all BENCH_MODELS)")
    dump_p.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    dump_p.set_defaults(func=cmd_dump)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
