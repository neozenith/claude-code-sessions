"""Per-session human-prompt summarisation (G2).

Extracts, per session, a structured 3-lens view of the developer's typed
prompts — *what task* (with ubiquitous language), *which patterns*, and *which
decisions/values* — through a model-pluggable :class:`SummaryEngine`.

The engine is an injection seam: the production backend (T2.6) calls
``sqlite-muninn``'s ``muninn_chat(model, prompt)``, while tests inject a fake
returning canned output. ``summarise_session`` owns prompt construction,
output parsing, and the upsert; the engine owns only "text in → text out".
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol

from claude_code_sessions.database.sqlite.merge import Summary, get_merger
from claude_code_sessions.database.sqlite.time_buckets import bucket_expr
from claude_code_sessions.project_resolver import (
    ProjectResolver,
    ancestor_scopes,
    scope_path_of,
)

__all__ = [
    "MuninnSummaryEngine",
    "SummaryEngine",
    "roll_up_scopes",
    "summarise_session",
]


class SummaryEngine(Protocol):
    """A pluggable text-completion backend, parameterised by model name.

    ``model`` selects the GGUF (its family + parameter size); ``prompt`` is the
    fully-built 3-lens extraction prompt. The return is the model's raw text,
    which ``summarise_session`` parses into the three lenses.
    """

    def summarise(self, model: str, prompt: str) -> str: ...


class MuninnSummaryEngine:
    """Production :class:`SummaryEngine` backed by ``sqlite-muninn`` (ADR2.1).

    Drives the in-repo local chat model via the 2-arg ``muninn_chat(model,
    prompt)`` SQL function — the same engine the KG community-naming pass uses
    (``kg/community_naming.py``). No external API, key, or network call: the
    project's 100%-local, fail-loud invariant is preserved.

    A third ``muninn_chat`` argument is interpreted by llama.cpp as a GBNF
    grammar, so the system instruction is folded into the single ``prompt``
    string by :func:`summarise_session` rather than passed separately.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def summarise(self, model: str, prompt: str) -> str:
        row = self._conn.execute(
            "SELECT muninn_chat(?, ?)",
            (model, prompt),
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else ""


# The three lenses the extraction must yield, in schema-column order.
_LENSES = ("task_summary", "patterns", "decisions_values")

_PROMPT_HEADER = (
    "You are summarising a software developer's typed prompts from one coding "
    "session. Read the prompts below and reply with a single JSON object with "
    "exactly these keys:\n"
    '  "task_summary": what task is being achieved, naming the specific '
    "systems and their ubiquitous language;\n"
    '  "patterns": which architectural patterns are used or reused;\n'
    '  "decisions_values": which decisions and values are expressed.\n\n'
    "Human prompts:\n"
)


def _gather_human_text(
    conn: sqlite3.Connection, project_id: str, session_id: str
) -> list[str]:
    """The session's ``msg_kind='human'`` prompt texts, in chronological order."""
    rows = conn.execute(
        """SELECT message_content
           FROM events
           WHERE project_id = ? AND session_id = ? AND msg_kind = 'human'
           ORDER BY timestamp, line_number""",
        (project_id, session_id),
    ).fetchall()
    return [str(r[0]) for r in rows if r[0] is not None]


def _build_prompt(human_texts: list[str]) -> str:
    return _PROMPT_HEADER + "\n\n".join(human_texts)


def _content_hash(human_texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in human_texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def summarise_session(
    conn: sqlite3.Connection,
    project_id: str,
    session_id: str,
    engine: SummaryEngine,
    model: str,
) -> None:
    """Summarise one session's human prompts into a ``session_summaries`` row.

    Gathers the ``msg_kind='human'`` text for ``(project_id, session_id)``,
    calls ``engine`` once with ``model`` and the 3-lens prompt, parses the
    JSON reply, and upserts exactly one row keyed by ``(project_id,
    session_id, model)``.
    """
    human_texts = _gather_human_text(conn, project_id, session_id)

    # A session with no typed prompts has nothing to summarise (T2.5):
    # no engine call, no row. There is no human intent to extract.
    if not human_texts:
        return

    content_hash = _content_hash(human_texts)

    # Content-hash freshness guard (ADR2.3): an unchanged session under the
    # same model is a cache hit — skip the engine entirely so an incremental
    # run does zero work for untouched sessions. A different model has no row
    # here, so it falls through as a cache miss and writes its own row.
    existing = conn.execute(
        """SELECT content_hash FROM session_summaries
           WHERE project_id = ? AND session_id = ? AND model = ?""",
        (project_id, session_id, model),
    ).fetchone()
    if existing is not None and existing[0] == content_hash:
        return

    prompt = _build_prompt(human_texts)
    raw = engine.summarise(model, prompt)
    parsed = json.loads(raw)
    conn.execute(
        """INSERT OR REPLACE INTO session_summaries
               (project_id, session_id, model, content_hash,
                task_summary, patterns, decisions_values,
                generated_at, human_event_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            session_id,
            model,
            content_hash,
            parsed[_LENSES[0]],
            parsed[_LENSES[1]],
            parsed[_LENSES[2]],
            datetime.now(UTC).isoformat(),
            len(human_texts),
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Roll-up driver (G3)
# ---------------------------------------------------------------------------

def _rollup_source_hash(strategy: str, model: str, child_keys: list[tuple[str, str]]) -> str:
    """Freshness hash over (strategy, model, sorted child id+content-hash pairs).

    Scoping by ``strategy`` and ``model`` (ADR3.3) means a different permutation
    over the same source text yields a distinct hash — never a false skip.
    """
    digest = hashlib.sha256()
    digest.update(strategy.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(model.encode("utf-8"))
    digest.update(b"\x00")
    for child_id, child_hash in sorted(child_keys):
        digest.update(child_id.encode("utf-8"))
        digest.update(b"=")
        digest.update(child_hash.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _scope_depth(scope: str) -> int:
    """Trie depth: 0 for the root scope ``''``, else the segment count."""
    return 0 if scope == "" else len(scope.split("/"))


def _parent_scope(scope: str) -> str:
    """The scope one level up; a depth-1 scope's parent is the root ``''``."""
    return scope.rsplit("/", 1)[0] if "/" in scope else ""


def _scope_in_band(scope: str, level: str, leaf_scopes: set[str]) -> bool:
    """Whether ``scope`` belongs to the requested ``level`` band (ADR3.4).

    ``'leaf'`` = a project-leaf scope (a project sits exactly there); ``'root'``
    = the all-domains node. An unknown band fails loud rather than silently
    rolling up the wrong tier.
    """
    if level == "leaf":
        return scope in leaf_scopes
    if level == "root":
        return scope == ""
    raise ValueError(f"Unknown level band {level!r}. Known bands: 'leaf', 'root'.")


def roll_up_scopes(
    conn: sqlite3.Connection,
    engine: SummaryEngine,
    strategy: str,
    model: str,
    granularity: str,
    level: str | None = None,
    resolver: ProjectResolver | None = None,
) -> int:
    """Walk the variable-depth scope trie deepest-first for one ``(strategy, model)``.

    A **leaf** scope merges its projects' ``session_summaries`` (for ``model``),
    bucketed by each session's *activity* timestamp from ``events``. An
    **ancestor** scope merges its direct child scopes' rollups at the same bucket
    — children are written first because the walk is deepest-first, so an
    ancestor's ``child_count`` counts its direct child scopes (and any sessions
    sitting exactly at that scope), not transitive sessions. The root ``''`` is
    the all-domains node. Returns the number of rollup rows written.
    """
    merger = get_merger(strategy)
    if resolver is None:
        # A scope is the project's resolved path; without a resolver we cannot
        # place a session in the trie. Fail loud rather than fabricate a scope.
        raise ValueError("roll_up_scopes requires a ProjectResolver")
    if merger.child_mode == "raw_sessions":
        # The flat strategy (G6) re-summarises raw descendant sessions per scope
        # rather than merging child rollups — implemented with the flat merger.
        raise NotImplementedError("child_mode='raw_sessions' is implemented by the flat merger (G6)")

    grain_expr = bucket_expr(granularity, "e.timestamp")
    session_rows = conn.execute(
        f"""
        SELECT ss.project_id        AS project_id,
               ss.session_id        AS session_id,
               ss.content_hash      AS content_hash,
               ss.task_summary      AS task_summary,
               ss.patterns          AS patterns,
               ss.decisions_values  AS decisions_values,
               {grain_expr}         AS bucket
        FROM session_summaries ss
        JOIN events e
          ON e.project_id = ss.project_id AND e.session_id = ss.session_id
        WHERE ss.model = ? AND e.timestamp IS NOT NULL
        GROUP BY ss.project_id, ss.session_id
        """,
        (model,),
    ).fetchall()

    # The scope trie is the union of every project's ancestor chain (root
    # included). Sessions sitting exactly at a scope are its leaf contribution.
    all_scopes: set[str] = {""}
    own_sessions: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in session_rows:
        project_id = row["project_id"]
        for ancestor in ancestor_scopes(resolver, project_id):
            all_scopes.add(ancestor)
        leaf = scope_path_of(resolver, project_id)
        own_sessions[(leaf, str(row["bucket"]))].append(row)

    # Scopes a project sits exactly at — the 'leaf' band (ADR3.4).
    leaf_scopes = {sc for (sc, _bucket) in own_sessions}

    written = 0
    for scope in sorted(all_scopes, key=_scope_depth, reverse=True):
        # One level band per invocation (ADR3.4): a cadence trigger rolls up one
        # tier off whatever the tier below has produced to date, leaving the
        # other tiers untouched. level=None walks every tier.
        if level is not None and not _scope_in_band(scope, level, leaf_scopes):
            continue
        child_scopes = [c for c in all_scopes if c != "" and _parent_scope(c) == scope]

        # Child-scope rollups were written on earlier (deeper) iterations.
        child_rollups: dict[str, list[sqlite3.Row]] = defaultdict(list)
        if child_scopes:
            placeholders = ",".join("?" * len(child_scopes))
            for r in conn.execute(
                f"""SELECT scope_path, time_bucket, task_summary, patterns,
                           decisions_values, source_hash
                    FROM rollup_summaries
                    WHERE strategy = ? AND model = ? AND time_granularity = ?
                      AND scope_path IN ({placeholders})""",
                (strategy, model, granularity, *child_scopes),
            ).fetchall():
                child_rollups[str(r["time_bucket"])].append(r)

        buckets = {b for (sc, b) in own_sessions if sc == scope} | set(child_rollups)
        for bucket in buckets:
            sessions = own_sessions.get((scope, bucket), [])
            rollups = child_rollups.get(bucket, [])
            children = [
                Summary(m["task_summary"], m["patterns"], m["decisions_values"]) for m in sessions
            ] + [Summary(r["task_summary"], r["patterns"], r["decisions_values"]) for r in rollups]
            if not children:
                continue
            child_keys = [(m["session_id"], m["content_hash"]) for m in sessions] + [
                (r["scope_path"], r["source_hash"]) for r in rollups
            ]
            source_hash = _rollup_source_hash(strategy, model, child_keys)

            # Freshness guard (ADR3.3): a row with the same source_hash means
            # nothing this (strategy, model) depends on changed — skip the merge
            # entirely, leaving the existing row (and its generated_at) intact.
            # Because the walk is deepest-first, a re-merged child below already
            # carries a new source_hash, so its parent's hash flips too — the
            # re-computation cascades up only as far as a change reaches.
            existing = conn.execute(
                """SELECT source_hash FROM rollup_summaries
                   WHERE strategy = ? AND model = ? AND scope_path = ?
                     AND time_granularity = ? AND time_bucket = ?""",
                (strategy, model, scope, granularity, bucket),
            ).fetchone()
            if existing is not None and existing["source_hash"] == source_hash:
                continue

            merged = merger.merge(engine, model, children, None)
            conn.execute(
                """INSERT OR REPLACE INTO rollup_summaries
                       (strategy, model, scope_path, scope_depth,
                        time_granularity, time_bucket,
                        task_summary, patterns, decisions_values,
                        child_count, source_hash, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    strategy,
                    model,
                    scope,
                    _scope_depth(scope),
                    granularity,
                    bucket,
                    merged.task_summary,
                    merged.patterns,
                    merged.decisions_values,
                    len(children),
                    source_hash,
                    datetime.now(UTC).isoformat(),
                ),
            )
            written += 1
    conn.commit()
    return written
