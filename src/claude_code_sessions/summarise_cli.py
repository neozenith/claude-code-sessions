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
import logging
import sqlite3
from collections.abc import Iterator

import sqlite_muninn

from claude_code_sessions.config import CACHE_DB_PATH, PROJECTS_PATH
from claude_code_sessions.database.sqlite.kg.runtime import ensure_chat_model_downloaded
from claude_code_sessions.database.sqlite.summaries import (
    MuninnSummaryEngine,
    SummaryEngine,
    summarise_session,
)
from claude_code_sessions.project_resolver import ProjectResolver, ancestor_scopes

log = logging.getLogger(__name__)


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
# CLI
# ---------------------------------------------------------------------------


def _help(p: argparse.ArgumentParser):  # type: ignore[no-untyped-def]
    """Return a handler that prints help for parser ``p`` (the default func)."""

    def _print_help(_: argparse.Namespace) -> None:
        p.print_help()

    return _print_help


def _open_chat_connection(model: str) -> sqlite3.Connection:
    """Open the cache with ``sqlite-muninn`` loaded and ``model`` registered as a
    chat model, so :class:`MuninnSummaryEngine` can call ``muninn_chat``."""
    conn = sqlite3.connect(str(CACHE_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_muninn.load(conn)
    conn.enable_load_extension(False)
    model_path = ensure_chat_model_downloaded()
    try:
        conn.execute(
            "INSERT INTO temp.muninn_chat_models(name, model) SELECT ?, muninn_chat_model(?)",
            (model, str(model_path)),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="summarise_cli",
        description="Manual, ingest-decoupled summarisation runners (G2).",
    )
    parser.set_defaults(func=_help(parser))
    sub = parser.add_subparsers(dest="command", required=False)

    sessions_p = sub.add_parser(
        "sessions", help="Summarise sessions ingested to date (content-hash guarded)"
    )
    sessions_p.add_argument("--model", required=True, help="Chat model name (provenance + registration)")
    sessions_p.add_argument(
        "--scope", default=None, help="Restrict to a scope_path subtree, e.g. 'clients/acme'"
    )
    sessions_p.set_defaults(func=cmd_sessions)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
