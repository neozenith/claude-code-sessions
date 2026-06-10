"""CR5 driver: extract claims across ALL projects/domains for a time window, then
roll up every grain and print the failure-mode breakdown.

This is the iteration engine for "clean runs": the content-hash guard makes
already-extracted sessions no-ops, so the first run does the work and subsequent
runs only re-process the failures — fast to iterate on as fixes land.

    uv run -m scripts.claims_run --model Qwen3.5-2B --since 2026-04-04
    uv run -m scripts.claims_run --report-only      # just print the current failure breakdown
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from claude_code_sessions.config import PROJECTS_PATH
from claude_code_sessions.database.sqlite.claims import (
    FAILURE_CATEGORIES,
    MuninnClaimsEngine,
    categorise_claim_failure,
    ensure_claims_schema,
    extract_session_claims,
)
from claude_code_sessions.project_resolver import ProjectResolver
from claude_code_sessions.summarise_cli import (
    DEFAULT_N_CTX,
    _open_chat_connection,
    bench_session_keys,
    cluster_and_name_pipeline,
    gguf_path,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("claims_run")


def _default_since() -> str:
    return (datetime.now(UTC) - timedelta(days=62)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _print_failure_breakdown(conn: sqlite3.Connection, model: str) -> int:
    rows = conn.execute(
        "SELECT project_id, session_id, reason, raw_excerpt FROM session_claim_failures "
        "WHERE model = ?",
        (model,),
    ).fetchall()
    by_cat: dict[str, list[Any]] = {c: [] for c in FAILURE_CATEGORIES}
    for r in rows:
        by_cat[categorise_claim_failure(r["reason"], r["raw_excerpt"])].append(r)
    total = len(rows)
    log.info("──────── failure breakdown (%s): %d total ────────", model, total)
    for cat in FAILURE_CATEGORIES:
        items = by_cat[cat]
        if not items:
            continue
        sample = items[0]
        log.info("  %-18s %3d   e.g. %s", cat, len(items), sample["reason"][:70])
        log.info("      tail: …%s", sample["raw_excerpt"][-90:].replace("\n", " "))
        log.info("      sessions: %s", ", ".join(r["session_id"][:8] for r in items[:8]))
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="Qwen3.5-2B")
    ap.add_argument("--since", default=_default_since(), help="ISO ts; default ~2mo ago")
    ap.add_argument("--limit", type=int, default=None, help="cap sessions (debugging)")
    ap.add_argument("--report-only", action="store_true", help="skip extraction; print failures")
    ap.add_argument(
        "--retry-failures",
        action="store_true",
        help="re-extract ONLY currently-recorded failures (any age); mops up stale rows",
    )
    ap.add_argument(
        "--rollup-only",
        action="store_true",
        help="skip extraction; just rebuild all-grain roll-ups (clears stale rollup rows)",
    )
    args = ap.parse_args()

    path = gguf_path(args.model)
    if path is None:
        raise SystemExit(f"no GGUF on disk for model {args.model!r}")

    conn = _open_chat_connection(args.model, path, n_ctx=DEFAULT_N_CTX)
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_claims_schema(conn)
    resolver = ProjectResolver(PROJECTS_PATH)

    if args.report_only:
        _print_failure_breakdown(conn, args.model)
        conn.close()
        return

    ok = failed = 0
    if not args.rollup_only:
        if args.retry_failures:
            keys = [
                (r["project_id"], r["session_id"])
                for r in conn.execute(
                    "SELECT project_id, session_id FROM session_claim_failures WHERE model = ?",
                    (args.model,),
                ).fetchall()
            ]
            log.info("retrying %d recorded failures (any age)", len(keys))
        else:
            keys = bench_session_keys(conn, resolver, ("",), since=args.since)
            log.info("extracting %d sessions (all scopes) since %s", len(keys), args.since)
        if args.limit:
            keys = keys[: args.limit]

        engine = MuninnClaimsEngine(conn)
        ok = failed = 0
        for i, (pid, sid) in enumerate(keys, 1):
            try:
                extract_session_claims(conn, pid, sid, engine, args.model)
                ok += 1
            except (ValueError, KeyError):
                failed += 1  # recorded to the parallel failure stream
            if i % 20 == 0 or i == len(keys):
                log.info("  %d/%d sessions (ok=%d failed=%d)", i, len(keys), ok, failed)

    log.info("clustering + naming + rolling up all grains (CR6)")
    written = cluster_and_name_pipeline(
        conn, args.model, resolver, progress=lambda **kw: log.info("  %s", kw)
    )
    log.info("  wrote %d leaf rollup rows across all grains", written)

    if not args.rollup_only:
        log.info("extraction done — ok=%d failed=%d", ok, failed)
    _print_failure_breakdown(conn, args.model)
    conn.close()


if __name__ == "__main__":
    main()
