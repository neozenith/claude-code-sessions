"""CR5 extractive set-union — end-to-end experiment runner + results report.

Runs the real pipeline over a bounded real slice and gathers the CR5.5 results:
  L1: extract_session_claims over N real sessions (list-valued, n_ctx=65536);
  L2: set_union_rollup at day/week/month with the real muninn_embed cosine dedup tier;
  Report: L1 stats, dedup compression (raw claims -> clusters), LLM-call budget,
          and the salience ranking (top claims by COUNT) at root + project scope.

Run (bounded slice so it finishes fast):
  uv run --frozen scripts/run_claims_experiment.py --model Qwen3.5-2B --limit 12
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from claude_code_sessions.config import PROJECTS_PATH
from claude_code_sessions.database.sqlite.claims import (
    MuninnClaimsEngine,
    ensure_claims_schema,
    extract_session_claims,
    set_union_rollup,
)
from claude_code_sessions.project_resolver import ProjectResolver
from claude_code_sessions.summarise_cli import (
    _embed,
    _open_chat_connection,
    bench_session_keys,
    gguf_path,
    make_embed_cosine,
)

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT = PROJECT_ROOT / "docs" / "plans" / "summariser-CR5-RESULTS.md"
LENSES = ("tasks", "patterns", "decisions_values")


def main() -> None:
    ap = argparse.ArgumentParser(description="CR5 extractive set-union experiment")
    ap.add_argument("--model", default="Qwen3.5-2B")
    ap.add_argument("--scope", default="play/claude-code-sessions")
    ap.add_argument("--since", default=None, help="ISO date floor (default: 7 days ago)")
    ap.add_argument("--limit", type=int, default=12, help="max sessions (bounds runtime)")
    ap.add_argument("--n-ctx", type=int, default=65536)
    ap.add_argument("--cosine-threshold", type=float, default=0.86)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    since = args.since or (datetime.now(UTC) - timedelta(days=7)).date().isoformat()
    conn = _open_chat_connection(args.model, gguf_path(args.model), n_ctx=args.n_ctx)
    ensure_claims_schema(conn)
    resolver = ProjectResolver(PROJECTS_PATH)
    keys = bench_session_keys(conn, resolver, (args.scope,), since=since)[: args.limit]
    log.info("L1: extracting claims from %d sessions (%s since %s)", len(keys), args.scope, since)

    engine = MuninnClaimsEngine(conn)
    n_ok = n_fail = total_claims = 0
    fails: list[str] = []
    for pid, sid in keys:
        try:
            total_claims += extract_session_claims(conn, pid, sid, engine, args.model)
            n_ok += 1
        except (ValueError, KeyError) as exc:  # non-JSON / missing lens — record as data
            n_fail += 1
            fails.append(f"{sid[:8]}: {exc}")

    # Per-lens L1 claim counts.
    per_lens = {
        lens: conn.execute(
            "SELECT COUNT(*) FROM session_claims WHERE model=? AND lens=?", (args.model, lens)
        ).fetchone()[0]
        for lens in LENSES
    }

    # Real embedding fn for the cosine dedup tier (registers nomic-embed once).
    make_embed_cosine(conn)
    embed = lambda t: _embed(conn, t)  # noqa: E731

    grains = ("day", "week", "month")
    rollup_written = {g: set_union_rollup(conn, args.model, g, resolver, embed=embed,
                                          cosine_threshold=args.cosine_threshold) for g in grains}

    _write_report(conn, args, since, n_ok, n_fail, total_claims, per_lens, fails, rollup_written)
    conn.close()


def _top_claims(conn, model, scope, grain, lens, k=8):  # type: ignore[no-untyped-def]
    return conn.execute(
        """SELECT claim, count FROM rollup_claims
           WHERE model=? AND scope_path=? AND time_granularity=? AND lens=?
           ORDER BY count DESC, claim_index ASC LIMIT ?""",
        (model, scope, grain, lens, k),
    ).fetchall()


def _write_report(conn, args, since, n_ok, n_fail, total_claims, per_lens, fails, rollup_written):  # type: ignore[no-untyped-def]
    raw = conn.execute(
        "SELECT COUNT(*) FROM session_claims WHERE model=?", (args.model,)
    ).fetchone()[0]
    clustered_month = conn.execute(
        """SELECT COUNT(*) FROM rollup_claims
           WHERE model=? AND scope_path=? AND time_granularity='month'""",
        (args.model, args.scope),
    ).fetchone()[0]
    lines = [
        "# CR5 Extractive Set-Union — Experiment Results",
        "",
        f"Model **{args.model}** @ n_ctx={args.n_ctx}; scope `{args.scope}`; since {since}; "
        f"limit {args.limit}. Generated {datetime.now(UTC).isoformat()}.",
        "",
        "## L1 — session claim extraction",
        f"- sessions extracted: **{n_ok}** ok, {n_fail} failed (LLM calls = {n_ok + n_fail})",
        f"- total claims: **{total_claims}**  (~{total_claims / max(n_ok, 1):.1f}/session)",
        f"- per lens: tasks={per_lens['tasks']}, patterns={per_lens['patterns']}, "
        f"decisions_values={per_lens['decisions_values']}",
        "",
        "## L2 — set-union dedup (NO LLM calls; exact + embedding-cosine only)",
        f"- raw L1 claims: **{raw}** → project-scope month clusters: **{clustered_month}** "
        f"(dedup compression at one scope)",
        "- rows written: " + ", ".join(f"{g}={n}" for g, n in rollup_written.items()),
        "",
        "## Salience — top claims by COUNT (the signal abstractive merging discards)",
    ]
    for scope_label, scope in (("ROOT (all)", ""), (f"`{args.scope}`", args.scope)):
        lines.append(f"\n### {scope_label} — month grain")
        for lens in LENSES:
            top = _top_claims(conn, args.model, scope, "month", lens)
            lines.append(f"\n**{lens}**")
            if not top:
                lines.append("- (none)")
            for r in top:
                lines.append(f"- ({r['count']}×) {r['claim']}")
    if fails:
        lines += ["", "## L1 extraction failures (recorded as data)", *[f"- {f}" for f in fails]]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    log.info("wrote %s", REPORT)


if __name__ == "__main__":
    main()
