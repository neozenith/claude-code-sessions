"""CR5 extractive set-union summariser — L1 claim extraction + L2 set-union rollup.

The abstractive path (``summaries.py`` + ``merge.py``) rewrites child summaries into
new prose at every tier, which drifts and forces exactly one item per lens. This
module is the **extractive** alternative:

* **L1** (``extract_session_claims``) — each session's human prompts → three LISTS of
  atomic claims (``tasks`` / ``patterns`` / ``decisions_values``), 0..N each (empty is
  valid), one row per claim in ``session_claims``.
* **L2+** (``set_union_rollup``) — every coarser scope×grain is the **union** of its
  descendants' claims, deduped (tiered: exact → embedding-cosine), with a **COUNT**
  per cluster (salience = how many sessions expressed it) and provenance. No
  re-summarisation; union is associative so it is correct at any depth.

Built additively beside the abstractive tables — nothing here mutates them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from claude_code_sessions.database.sqlite.summaries import (
    CLAIM_LENS_GBNF,
    SUMMARY_MAX_TOKENS,
    _gather_human_text,
    _resolve_scopes,
)
from claude_code_sessions.database.sqlite.summary_json import LENS_LIST_KEYS, parse_lens_lists
from claude_code_sessions.database.sqlite.time_buckets import bucket_expr
from claude_code_sessions.project_resolver import ProjectResolver

log = logging.getLogger(__name__)

# Additive tables (no SCHEMA_VERSION bump — these are NEW tables, created idempotently
# so the experiment runs against the existing cache without a destructive reingest).
CLAIMS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS session_claims (
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    model TEXT NOT NULL,
    lens TEXT NOT NULL,
    claim_index INTEGER NOT NULL,
    claim TEXT NOT NULL,
    embedding BLOB,
    content_hash TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, session_id, model, lens, claim_index)
);
CREATE INDEX IF NOT EXISTS idx_session_claims_model ON session_claims(model, lens);

CREATE TABLE IF NOT EXISTS rollup_claims (
    strategy TEXT NOT NULL,
    model TEXT NOT NULL,
    scope_path TEXT NOT NULL,
    scope_depth INTEGER NOT NULL,
    time_granularity TEXT NOT NULL,
    time_bucket TEXT NOT NULL,
    lens TEXT NOT NULL,
    claim_index INTEGER NOT NULL,
    claim TEXT NOT NULL,
    count INTEGER NOT NULL,
    source_session_ids TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (strategy, model, scope_path, time_granularity, time_bucket, lens, claim_index)
);
CREATE INDEX IF NOT EXISTS idx_rollup_claims_scope ON rollup_claims(model, scope_path, lens);

-- Parallel FAILURE stream: an L1 parse failure is first-class data (not silently
-- dropped), so the operator can later triage "correct failure" (genuinely empty
-- session) vs "refine the prompt". One row per failed (session, model).
CREATE TABLE IF NOT EXISTS session_claim_failures (
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    model TEXT NOT NULL,
    reason TEXT NOT NULL,
    raw_excerpt TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, session_id, model)
);
CREATE INDEX IF NOT EXISTS idx_session_claim_failures_model ON session_claim_failures(model);

-- Failure roll-up (parallel to rollup_claims): failed-session COUNT per scope×grain.
CREATE TABLE IF NOT EXISTS rollup_claim_failures (
    model TEXT NOT NULL,
    scope_path TEXT NOT NULL,
    scope_depth INTEGER NOT NULL,
    time_granularity TEXT NOT NULL,
    time_bucket TEXT NOT NULL,
    failure_count INTEGER NOT NULL,
    source_session_ids TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (model, scope_path, time_granularity, time_bucket)
);
CREATE INDEX IF NOT EXISTS idx_rollup_claim_failures_scope
    ON rollup_claim_failures(model, scope_path);
"""


def ensure_claims_schema(conn: sqlite3.Connection) -> None:
    """Create the claims tables if absent (idempotent, non-destructive)."""
    conn.executescript(CLAIMS_SCHEMA_SQL)


# --- L1: session claim extraction -----------------------------------------

_CLAIMS_PROMPT_HEADER = (
    "You are extracting structured signals from a software developer's typed prompts "
    "in one coding session. Reply with a single JSON object with exactly these keys, "
    "each a JSON ARRAY of short, atomic, self-contained items (one clause each). An "
    "EMPTY array is correct when the session has none of that kind — do NOT invent:\n"
    '  "tasks": the distinct task(s) being attempted, naming specific systems/files;\n'
    '  "decisions_values": value judgements the developer expresses — especially when '
    "they explain THE WHY (valuing one thing over another), often in reply to a "
    "question; capture the trade-off, not just the choice;\n"
    '  "patterns": software/architectural patterns at play, even if unnamed — describe '
    "the category of the approach;\n"
    '  "learnings": what to carry forward to improve PROCESS and SKILL and to '
    "systematically reduce failure modes — lessons, gotchas, things that wasted time or "
    "should be done differently next time (not the task itself, the meta-lesson).\n"
    "Each item: at most ~160 characters, dense and specific. Prefer several precise "
    "items over one vague sentence; prefer an empty array over filler.\n\n"
    "Human prompts:\n"
)


class ClaimsEngine(Protocol):
    """Text-completion backend that yields the 3-lens LIST JSON (CR5 L1)."""

    def extract(self, model: str, prompt: str) -> str: ...


class MuninnClaimsEngine:
    """Production :class:`ClaimsEngine` — drives ``muninn_chat`` with the list grammar."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def extract(self, model: str, prompt: str) -> str:
        row = self._conn.execute(
            "SELECT muninn_chat(?, ?, ?, ?)",
            (model, prompt, CLAIM_LENS_GBNF, SUMMARY_MAX_TOKENS),
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else ""


def _content_hash(human_texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in human_texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _record_failure(
    conn: sqlite3.Connection,
    project_id: str,
    session_id: str,
    model: str,
    reason: str,
    raw: str,
    content_hash: str,
) -> None:
    """Record an L1 parse failure into the parallel failure stream (bounded excerpt)."""
    conn.execute(
        """INSERT OR REPLACE INTO session_claim_failures
               (project_id, session_id, model, reason, raw_excerpt, content_hash, generated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project_id, session_id, model, reason, raw[:2000], content_hash,
         datetime.now(UTC).isoformat()),
    )


def extract_session_claims(
    conn: sqlite3.Connection,
    project_id: str,
    session_id: str,
    engine: ClaimsEngine,
    model: str,
) -> int:
    """Extract one session's human prompts into ``session_claims`` rows (one per claim).

    Content-hash guarded (ADR2.3): unchanged session under the same model is a no-op.
    A lens with no claims simply writes no rows for that lens (empty list = no rows).
    Returns the number of claim rows written (0 if cache-hit or no human text).
    """
    human_texts = _gather_human_text(conn, project_id, session_id)
    if not human_texts:
        return 0
    content_hash = _content_hash(human_texts)

    existing = conn.execute(
        """SELECT content_hash FROM session_claims
           WHERE project_id = ? AND session_id = ? AND model = ? LIMIT 1""",
        (project_id, session_id, model),
    ).fetchone()
    if existing is not None and existing[0] == content_hash:
        return 0  # cache hit — claims already current for this content+model

    prompt = _CLAIMS_PROMPT_HEADER + "\n\n".join(human_texts)
    raw = engine.extract(model, prompt)
    try:
        lens_lists = parse_lens_lists(raw)
    except (ValueError, KeyError) as exc:
        # Record the failure as a first-class parallel-stream row (not silent loss),
        # clear any stale claims, then re-raise so the caller still counts it.
        _record_failure(conn, project_id, session_id, model, str(exc), raw, content_hash)
        conn.execute(
            "DELETE FROM session_claims WHERE project_id = ? AND session_id = ? AND model = ?",
            (project_id, session_id, model),
        )
        conn.commit()
        raise

    # Success — clear any prior failure row + stale claims, then insert fresh claims.
    conn.execute(
        "DELETE FROM session_claim_failures WHERE project_id = ? AND session_id = ? AND model = ?",
        (project_id, session_id, model),
    )
    conn.execute(
        "DELETE FROM session_claims WHERE project_id = ? AND session_id = ? AND model = ?",
        (project_id, session_id, model),
    )
    now = datetime.now(UTC).isoformat()
    written = 0
    for lens in LENS_LIST_KEYS:
        for idx, claim in enumerate(lens_lists[lens]):
            text = claim.strip()
            if not text:
                continue  # skip blank claims — an empty lens contributes no rows
            conn.execute(
                """INSERT OR REPLACE INTO session_claims
                       (project_id, session_id, model, lens, claim_index, claim,
                        embedding, content_hash, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)""",
                (project_id, session_id, model, lens, idx, text, content_hash, now),
            )
            written += 1
    conn.commit()
    return written


# --- L2: set-union rollup with tiered dedup --------------------------------

EmbedFn = Callable[[str], Sequence[float]]
_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Casefold + whitespace-collapse — the key for the cheap exact-match tier."""
    return _WS.sub(" ", text.strip().casefold())


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class ClaimCluster:
    """A deduped claim: a representative text, its salience COUNT (distinct sessions),
    and the provenance session ids."""

    __slots__ = ("claim", "sessions")

    def __init__(self, claim: str) -> None:
        self.claim = claim
        self.sessions: set[str] = set()

    @property
    def count(self) -> int:
        return len(self.sessions)


def dedup_claims(
    items: list[tuple[str, str]],
    embed: EmbedFn | None = None,
    cosine_threshold: float = 0.86,
) -> list[ClaimCluster]:
    """Set-union dedup of ``(claim_text, session_id)`` pairs into ranked clusters.

    Tiered cascade (cheap → expensive), mirroring ``muninn_extract_er``'s philosophy:
      1. **exact** — casefold/whitespace-normalised identical claims merge for free;
      2. **cosine** — if ``embed`` is given, near-duplicate exact-groups whose
         embeddings exceed ``cosine_threshold`` merge (greedy, popular anchors first).
    COUNT is the number of **distinct sessions** expressing the cluster (salience),
    not raw occurrences. Returns clusters sorted by count desc, then claim text.
    (An optional LLM-judge tier for the borderline band is a future enhancement.)
    """
    # Tier 1 — exact-normalised grouping. Representative = first-seen original text.
    by_norm: dict[str, ClaimCluster] = {}
    for claim, session_id in items:
        key = _normalize(claim)
        if not key:
            continue
        cluster = by_norm.get(key)
        if cluster is None:
            cluster = ClaimCluster(claim)
            by_norm[key] = cluster
        cluster.sessions.add(session_id)
    clusters = list(by_norm.values())

    # Tier 2 — embedding-cosine merge of near-duplicate exact-groups.
    if embed is not None and len(clusters) > 1:
        clusters.sort(key=lambda c: (-c.count, c.claim))  # popular claims anchor
        vectors = {c.claim: embed(c.claim) for c in clusters}
        merged: list[ClaimCluster] = []
        for cluster in clusters:
            vec = vectors[cluster.claim]
            target = next(
                (m for m in merged if _cosine(vectors[m.claim], vec) >= cosine_threshold),
                None,
            )
            if target is None:
                merged.append(cluster)
            else:
                target.sessions |= cluster.sessions
        clusters = merged

    clusters.sort(key=lambda c: (-c.count, c.claim))
    return clusters


def set_union_rollup(
    conn: sqlite3.Connection,
    model: str,
    granularity: str,
    resolver: ProjectResolver,
    *,
    strategy: str = "setunion",
    embed: EmbedFn | None = None,
    cosine_threshold: float = 0.86,
    top_n: int | None = None,
) -> int:
    """L2+ extractive rollup: union descendant ``session_claims`` at every scope×bucket,
    dedup+count per lens, write ``rollup_claims``. Returns rows written.

    Associative union → each scope unions ALL descendant sessions directly (no tiered
    child-rollup walk needed). Bucketed on each session's earliest event timestamp.
    """
    ensure_claims_schema(conn)
    bucket_sql = bucket_expr(granularity, "MIN(e.timestamp)")
    rows = conn.execute(
        f"""
        SELECT sc.project_id AS project_id, sc.session_id AS session_id,
               sc.lens AS lens, sc.claim AS claim, sc.content_hash AS content_hash,
               {bucket_sql} AS bucket
        FROM session_claims sc
        JOIN events e ON e.project_id = sc.project_id AND e.session_id = sc.session_id
        WHERE sc.model = ? AND e.timestamp IS NOT NULL
        GROUP BY sc.project_id, sc.session_id, sc.lens, sc.claim
        """,
        (model,),
    ).fetchall()

    # Group claims under every ancestor scope × bucket × lens; track contributing
    # (session_id, content_hash) for the freshness source_hash.
    # key (scope, bucket, lens) -> [(claim, session_id)]
    groups: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
    # key (scope, bucket) -> {(session_id, content_hash)}
    src: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for r in rows:
        resolved = _resolve_scopes(resolver, r["project_id"])
        if resolved is None:
            continue
        _leaf, ancestors = resolved
        bucket = str(r["bucket"])
        for scope in ancestors:
            groups[(scope, bucket, str(r["lens"]))].append((str(r["claim"]), str(r["session_id"])))
            src[(scope, bucket)].add((str(r["session_id"]), str(r["content_hash"])))

    now = datetime.now(UTC).isoformat()
    written = 0
    for (scope, bucket, lens), items in groups.items():
        clusters = dedup_claims(items, embed=embed, cosine_threshold=cosine_threshold)
        if top_n is not None:
            clusters = clusters[:top_n]
        source_hash = hashlib.sha256(
            "\x00".join(f"{sid}:{h}" for sid, h in sorted(src[(scope, bucket)])).encode()
        ).hexdigest()
        depth = 0 if scope == "" else scope.count("/") + 1
        for idx, cluster in enumerate(clusters):
            conn.execute(
                """INSERT OR REPLACE INTO rollup_claims
                       (strategy, model, scope_path, scope_depth, time_granularity,
                        time_bucket, lens, claim_index, claim, count,
                        source_session_ids, source_hash, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    strategy, model, scope, depth, granularity, bucket, lens, idx,
                    cluster.claim, cluster.count,
                    json.dumps(sorted(cluster.sessions)), source_hash, now,
                ),
            )
            written += 1
    conn.commit()
    return written


def rollup_failures(
    conn: sqlite3.Connection,
    model: str,
    granularity: str,
    resolver: ProjectResolver,
) -> int:
    """Roll up the failure stream parallel to claims: failed-session COUNT per
    scope×grain×bucket, with provenance. Returns rows written to rollup_claim_failures.
    """
    ensure_claims_schema(conn)
    bucket_sql = bucket_expr(granularity, "MIN(e.timestamp)")
    rows = conn.execute(
        f"""
        SELECT scf.project_id AS pid, scf.session_id AS sid, {bucket_sql} AS bucket
        FROM session_claim_failures scf
        JOIN events e ON e.project_id = scf.project_id AND e.session_id = scf.session_id
        WHERE scf.model = ? AND e.timestamp IS NOT NULL
        GROUP BY scf.project_id, scf.session_id
        """,
        (model,),
    ).fetchall()
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)  # (scope, bucket) -> {session_id}
    for r in rows:
        resolved = _resolve_scopes(resolver, r["pid"])
        if resolved is None:
            continue
        _leaf, ancestors = resolved
        bucket = str(r["bucket"])
        for scope in ancestors:
            groups[(scope, bucket)].add(str(r["sid"]))

    now = datetime.now(UTC).isoformat()
    written = 0
    for (scope, bucket), sids in groups.items():
        depth = 0 if scope == "" else scope.count("/") + 1
        conn.execute(
            """INSERT OR REPLACE INTO rollup_claim_failures
                   (model, scope_path, scope_depth, time_granularity, time_bucket,
                    failure_count, source_session_ids, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (model, scope, depth, granularity, bucket, len(sids), json.dumps(sorted(sids)), now),
        )
        written += 1
    conn.commit()
    return written
