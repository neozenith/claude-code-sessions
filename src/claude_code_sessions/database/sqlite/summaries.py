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
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, datetime
from math import exp, log
from typing import Protocol

from claude_code_sessions.database.sqlite.merge import (
    ExcerptCandidate,
    Summary,
    SummaryMerger,
    get_merger,
    select_excerpts,
)
from claude_code_sessions.database.sqlite.summary_json import parse_lenses
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
    "score_summary",
    "summarise_session",
]

# Note: ``log`` is ``math.log`` in this module (BLEU), so the logger is ``logger``.
logger = logging.getLogger(__name__)


def _resolve_scopes(resolver: ProjectResolver, project_id: str) -> tuple[str, list[str]] | None:
    """A project's ``(scope_path, ancestor chain)``, or ``None`` if it can't be
    resolved to a real path.

    Some encoded ``project_id`` values in the cache don't map to a resolvable
    filesystem path (e.g. odd nested-skill encodings); such a project belongs to
    *no* scope, so the roll-up driver and excerpt gatherer skip it rather than
    crash on a ``KeyError`` from ``scope_path_of`` (CR1 — surfaced by a live run)."""
    try:
        return scope_path_of(resolver, project_id), ancestor_scopes(resolver, project_id)
    except KeyError:
        return None


class SummaryEngine(Protocol):
    """A pluggable text-completion backend, parameterised by model name.

    ``model`` selects the GGUF (its family + parameter size); ``prompt`` is the
    fully-built 3-lens extraction prompt. The return is the model's raw text,
    which ``summarise_session`` parses into the three lenses.
    """

    def summarise(self, model: str, prompt: str) -> str: ...


# GBNF grammar forcing the 3-lens object, and an output-token cap. Dialed in by
# CR2 — see examples/muninn/FINDINGS.md for the evidence and the three gotchas
# (single-line root or segfault; exclude control chars; bound each string's
# length or a verbose model truncates mid-string past max_tokens). The grammar
# also suppresses the <think> preamble: a grammar-constrained decode must match
# `root` from the first token, so no per-model /no_think flag is needed.
_LENS_MAX = 300
THREE_LENS_GBNF = (
    r'root ::= "{" ws "\"task_summary\"" ws ":" ws string ws "," ws '
    r'"\"patterns\"" ws ":" ws string ws "," ws '
    r'"\"decisions_values\"" ws ":" ws string ws "}"'
    "\n"
    r'string ::= "\"" ( [^"\\\x00-\x1F] | "\\" ["\\/bfnrt] ){0,' + str(_LENS_MAX) + r'} "\""'
    "\n"
    r"ws ::= [ \t\n]*"
)
SUMMARY_MAX_TOKENS = 512

# CR5 extractive L1 grammar: each lens is a JSON ARRAY of 0..N short atomic claims
# (empty array valid). Same three gotchas as the single-string grammar — root on one
# line, no control chars in strings, bounded claim length so a verbose model can't
# truncate mid-claim past max_tokens. Four lenses (tasks / patterns / decisions_values
# / learnings); keep in sync with summary_json.LENS_LIST_KEYS.
_CLAIM_MAX = 200
CLAIM_LENS_GBNF = (
    r'root ::= "{" ws "\"tasks\"" ws ":" ws arr ws "," ws '
    r'"\"patterns\"" ws ":" ws arr ws "," ws '
    r'"\"decisions_values\"" ws ":" ws arr ws "," ws '
    r'"\"learnings\"" ws ":" ws arr ws "}"'
    "\n"
    r'arr ::= "[" ws ( string ( ws "," ws string )* )? ws "]"'
    "\n"
    r'string ::= "\"" ( [^"\\\x00-\x1F] | "\\" ["\\/bfnrt] ){0,' + str(_CLAIM_MAX) + r'} "\""'
    "\n"
    r"ws ::= [ \t\n]*"
)


class MuninnSummaryEngine:
    """Production :class:`SummaryEngine` backed by ``sqlite-muninn`` (ADR2.1).

    Drives the in-repo local chat model via the 4-arg
    ``muninn_chat(model, prompt, grammar, max_tokens)`` SQL function — the
    grammar (:data:`THREE_LENS_GBNF`) constrains output to the 3-lens JSON object
    and suppresses ``<think>`` runaway; ``max_tokens`` bounds generation time
    (CR2). No external API, key, or network call: the project's 100%-local,
    fail-loud invariant is preserved.

    The system instruction is folded into the single ``prompt`` string by
    :func:`summarise_session` / the mergers, so the call stays one positional
    prompt plus the fixed grammar + cap.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def summarise(self, model: str, prompt: str) -> str:
        row = self._conn.execute(
            "SELECT muninn_chat(?, ?, ?, ?)",
            (model, prompt, THREE_LENS_GBNF, SUMMARY_MAX_TOKENS),
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
    f"Keep EACH value concise and self-contained: at most {_LENS_MAX} characters "
    "(~40 words), one or two complete sentences. Lead with the most important "
    "point and finish cleanly — a hard limit truncates anything longer "
    "mid-sentence, so never exceed it and do not trail off. Prefer dense, "
    "specific word choice over filler.\n\n"
    "Human prompts:\n"
)


def _gather_human_text(conn: sqlite3.Connection, project_id: str, session_id: str) -> list[str]:
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
    lenses = parse_lenses(raw)
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
            lenses[_LENSES[0]],
            lenses[_LENSES[1]],
            lenses[_LENSES[2]],
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


# Cap on re-grounding source excerpts per merge (ADR5.1) — bounds prompt size
# at the largest top-tier scopes.
_EXCERPT_K = 20


def _gather_excerpt_candidates(
    conn: sqlite3.Connection,
    resolver: ProjectResolver,
    scope: str,
    granularity: str,
    bucket: str,
) -> list[ExcerptCandidate]:
    """Human-prompt excerpts under ``scope``'s subtree within ``bucket``.

    A project belongs to ``scope`` when ``scope`` is in its ancestor chain
    (so the root ``''`` sees every prompt). Used only by ``wants_excerpts``
    mergers (re-grounding); ``select_excerpts`` then bounds the sample.
    """
    grain_expr = bucket_expr(granularity, "timestamp")
    rows = conn.execute(
        f"""SELECT project_id, timestamp, message_content
            FROM events
            WHERE msg_kind = 'human' AND message_content IS NOT NULL
              AND timestamp IS NOT NULL AND {grain_expr} = ?""",
        (bucket,),
    ).fetchall()
    candidates: list[ExcerptCandidate] = []
    for row in rows:
        resolved = _resolve_scopes(resolver, row["project_id"])
        if resolved is None:
            continue  # unresolvable project — belongs to no scope
        _scope_path, ancestors = resolved
        if scope in ancestors:
            candidates.append(ExcerptCandidate(str(row["timestamp"]), str(row["message_content"])))
    return candidates


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


def _write_scope_bucket(
    conn: sqlite3.Connection,
    merger: SummaryMerger,
    engine: SummaryEngine,
    strategy: str,
    model: str,
    granularity: str,
    scope: str,
    bucket: str,
    children: list[Summary],
    child_keys: list[tuple[str, str]],
    resolver: ProjectResolver,
) -> bool:
    """Merge one ``(scope, bucket)`` group and upsert its rollup row.

    Shared by both child-gathering modes. Applies the ADR3.3 freshness guard
    (skip when the source_hash is unchanged) and supplies excerpts only to
    re-grounding mergers. Returns True if a row was written.
    """
    if not children:
        return False
    source_hash = _rollup_source_hash(strategy, model, child_keys)

    # Freshness guard (ADR3.3): a matching source_hash means nothing this
    # (strategy, model) depends on changed — skip the merge, leaving the row
    # (and its generated_at) intact. Deepest-first, a re-merged child below
    # already carries a new source_hash so its parent's hash flips too — the
    # re-computation cascades up only as far as a change reaches.
    existing = conn.execute(
        """SELECT source_hash FROM rollup_summaries
           WHERE strategy = ? AND model = ? AND scope_path = ?
             AND time_granularity = ? AND time_bucket = ?""",
        (strategy, model, scope, granularity, bucket),
    ).fetchone()
    if existing is not None and existing["source_hash"] == source_hash:
        return False

    # Re-grounding mergers (wants_excerpts) get a bounded source sample for this
    # scope+bucket; summary-only mergers get None.
    excerpts = (
        select_excerpts(
            _gather_excerpt_candidates(conn, resolver, scope, granularity, bucket),
            _EXCERPT_K,
        )
        if merger.wants_excerpts
        else None
    )
    merged = merger.merge(engine, model, children, excerpts)
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
    return True


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

    Two child-gathering modes (set by the merger):

    * ``child_rollups`` (strict/reground) — a **leaf** scope merges its projects'
      ``session_summaries``; an **ancestor** merges its direct child scopes'
      rollups (written first by the deepest-first order), so ``child_count``
      counts direct child scopes plus any sessions sitting exactly at the scope.
    * ``raw_sessions`` (flat) — every scope merges *all* descendant
      ``session_summaries`` under its prefix directly, no child-rollup tier, so
      ``child_count`` counts descendant sessions.

    Buckets are anchored to each session's *activity* timestamp from ``events``.
    The root ``''`` is the all-domains node. Returns the number of rows written.
    """
    merger = get_merger(strategy)
    if resolver is None:
        # A scope is the project's resolved path; without a resolver we cannot
        # place a session in the trie. Fail loud rather than fabricate a scope.
        raise ValueError("roll_up_scopes requires a ProjectResolver")

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
    # included). Precompute each session's ancestor set + bucket once.
    all_scopes: set[str] = {""}
    own_sessions: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    session_entries: list[tuple[sqlite3.Row, set[str], str]] = []
    for row in session_rows:
        resolved = _resolve_scopes(resolver, row["project_id"])
        if resolved is None:
            # Unresolvable project — can't place it in the trie; skip (not an error).
            logger.warning("roll-up: skipping unresolvable project %s", row["project_id"])
            continue
        leaf, ancestors_list = resolved
        ancestors = set(ancestors_list)
        all_scopes |= ancestors
        bucket = str(row["bucket"])
        own_sessions[(leaf, bucket)].append(row)
        session_entries.append((row, ancestors, bucket))

    # Scopes a project sits exactly at — the 'leaf' band (ADR3.4).
    leaf_scopes = {sc for (sc, _bucket) in own_sessions}

    def _sessions_to_children(
        rows: list[sqlite3.Row],
    ) -> tuple[list[Summary], list[tuple[str, str]]]:
        children = [Summary(m["task_summary"], m["patterns"], m["decisions_values"]) for m in rows]
        return children, [(m["session_id"], m["content_hash"]) for m in rows]

    written = 0
    for scope in sorted(all_scopes, key=_scope_depth, reverse=True):
        # One level band per invocation (ADR3.4): level=None walks every tier.
        if level is not None and not _scope_in_band(scope, level, leaf_scopes):
            continue

        # Build {bucket: (children, child_keys)} for this scope per the mode.
        payload: dict[str, tuple[list[Summary], list[tuple[str, str]]]] = {}
        if merger.child_mode == "raw_sessions":
            # Flat: all descendant sessions under this scope, no child rollups.
            descendants: dict[str, list[sqlite3.Row]] = defaultdict(list)
            for row, ancestors, bucket in session_entries:
                if scope in ancestors:
                    descendants[bucket].append(row)
            for bucket, rows in descendants.items():
                payload[bucket] = _sessions_to_children(rows)
        else:
            # child_rollups: own sessions here + direct child-scope rollups
            # (written earlier by the deepest-first walk).
            child_scopes = [c for c in all_scopes if c != "" and _parent_scope(c) == scope]
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
                children, child_keys = _sessions_to_children(own_sessions.get((scope, bucket), []))
                rollups = child_rollups.get(bucket, [])
                children += [
                    Summary(r["task_summary"], r["patterns"], r["decisions_values"])
                    for r in rollups
                ]
                child_keys += [(r["scope_path"], r["source_hash"]) for r in rollups]
                payload[bucket] = (children, child_keys)

        for bucket, (children, child_keys) in payload.items():
            if _write_scope_bucket(
                conn,
                merger,
                engine,
                strategy,
                model,
                granularity,
                scope,
                bucket,
                children,
                child_keys,
                resolver,
            ):
                written += 1
    conn.commit()
    return written


# ---------------------------------------------------------------------------
# Benchmark reference scorer (G10) — deterministic, fully-local ROUGE-L/BLEU/F1
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lower-case word tokens — the unit all three metrics score over."""
    return re.findall(r"\w+", text.lower())


def _lcs_length(a: list[str], b: list[str]) -> int:
    """Length of the longest common subsequence of two token lists."""
    prev = [0] * (len(b) + 1)
    for token_a in a:
        curr = [0] * (len(b) + 1)
        for j, token_b in enumerate(b, start=1):
            curr[j] = prev[j - 1] + 1 if token_a == token_b else max(prev[j], curr[j - 1])
        prev = curr
    return prev[len(b)]


def _f_measure(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def _rouge_l(cand: list[str], ref: list[str]) -> float:
    if not cand or not ref:
        return 0.0
    lcs = _lcs_length(cand, ref)
    return _f_measure(lcs / len(cand), lcs / len(ref))


def _token_f1(cand: list[str], ref: list[str]) -> float:
    if not cand or not ref:
        return 0.0
    cand_counts, ref_counts = Counter(cand), Counter(ref)
    overlap = sum((cand_counts & ref_counts).values())
    return _f_measure(overlap / len(cand), overlap / len(ref))


def _ngram_counts(tokens: list[str], n: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _bleu(cand: list[str], ref: list[str], max_n: int = 4) -> float:
    """BLEU with the geometric mean of modified n-gram precisions + brevity
    penalty. No smoothing: a zero at any order yields 0 (so disjoint → 0)."""
    if not cand or not ref:
        return 0.0
    orders = min(max_n, len(cand))
    log_precisions: list[float] = []
    for n in range(1, orders + 1):
        cand_ngrams = _ngram_counts(cand, n)
        ref_ngrams = _ngram_counts(ref, n)
        total = sum(cand_ngrams.values())
        overlap = sum((cand_ngrams & ref_ngrams).values())
        if overlap == 0 or total == 0:
            return 0.0
        log_precisions.append(log(overlap / total))
    geo_mean = exp(sum(log_precisions) / len(log_precisions))
    brevity = 1.0 if len(cand) >= len(ref) else exp(1 - len(ref) / len(cand))
    return brevity * geo_mean


def _combined3(cand: list[str], ref: list[str]) -> float:
    """Mean of the three lexical metrics — used to score the anchor baselines."""
    return (_rouge_l(cand, ref) + _bleu(cand, ref) + _token_f1(cand, ref)) / 3


def score_summary(candidate: str, reference: str) -> dict[str, float]:
    """Deterministic lexical score of ``candidate`` against ``reference``, plus the
    context needed to *locate* it on the bad→good→great band (CR4, SCORING.md).

    Lexical (relative screen, [0,1]): ``rouge_l`` / ``bleu`` / ``f1``.
    Context:
      * ``compression_ratio`` = len(cand)/len(ref) — how much was distilled away.
      * ``rouge_l_ceiling`` = 2·cr/(1+cr) — the *theoretical max* ROUGE-L f-measure
        at this compression (a length-``k`` subsequence has precision 1, recall cr).
      * ``rouge_l_normalised`` = rouge_l / ceiling — "% of the achievable headroom".
      * ``lead_combined`` — the combined score of the first ``k`` source tokens (a
        verbatim extractive baseline). Against the *full source* this is also ≈ the
        oracle extractive ceiling (any verbatim span scores near-maximally), so a
        good *abstractive* summary is expected to sit BELOW it — that gap is the
        abstraction the lexical metrics can't credit (use embedding cosine for it).
    """
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    n_cand, n_ref = len(cand_tokens), len(ref_tokens)
    rouge_l = _rouge_l(cand_tokens, ref_tokens)
    cr = n_cand / n_ref if n_ref else 0.0
    ceiling = 2 * cr / (1 + cr) if cr > 0 else 0.0
    lead = ref_tokens[:n_cand]
    return {
        "rouge_l": rouge_l,
        "bleu": _bleu(cand_tokens, ref_tokens),
        "f1": _token_f1(cand_tokens, ref_tokens),
        "compression_ratio": round(cr, 4),
        "rouge_l_ceiling": round(ceiling, 4),
        "rouge_l_normalised": round(rouge_l / ceiling, 4) if ceiling > 0 else 0.0,
        "lead_combined": round(_combined3(lead, ref_tokens), 4),
    }
