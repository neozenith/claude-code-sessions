"""CR5/CR6 extractive summariser — L1 claim extraction + the parallel failure stream.

The abstractive path (``summaries.py`` + ``merge.py``) rewrites child summaries into
new prose at every tier, which drifts and forces exactly one item per lens. This
module is the **extractive** alternative:

* **L1** (``extract_session_claims``) — each session's human prompts → four LISTS of
  atomic claims (``tasks`` / ``patterns`` / ``decisions_values`` / ``learnings``), 0..N
  each (empty is valid), one row per claim in ``session_claims``.
* **Failure stream** (``rollup_failures``) — L1 parse failures are recorded as
  first-class data and rolled up per scope×grain, parallel to the claims roll-up.

The **L2 reduce** lives in ``claim_clustering.py`` now (CR6 EVoC clustering →
``rollup_clusters``); the original CR5 ``set_union_rollup`` greedy-cosine reducer is
retired — see the note above ``rollup_failures`` and ``tmp/archived/``.

Built additively beside the abstractive tables — nothing here mutates them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol

from claude_code_sessions.database.sqlite.summaries import (
    CLAIM_LENS_GBNF,
    CLAIM_LENS_MAX_TOKENS,
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
            (model, prompt, CLAIM_LENS_GBNF, CLAIM_LENS_MAX_TOKENS),
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else ""


def _content_hash(human_texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in human_texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


# Failure taxonomy (CR5 distillation). A fixed, ordered set of categories so the
# failure stream's freeform exception strings roll up into systematic modes the
# operator can act on — rather than counting one-off messages. Derived purely from the
# recorded ``reason`` + ``raw_excerpt`` (no schema change; classifies existing rows too).
FAILURE_CATEGORIES = (
    "truncated_json",  # well-formed prefix cut off mid-structure → output cap too small
    "malformed_json",  # JSON syntax error mid-stream (often truncation-adjacent)
    "missing_lens_key",  # parsed object lacks one of the four lens keys
    "non_array_lens",  # a lens value was a string/obj, not the required array
    "empty_or_refusal",  # model emitted nothing parseable / a prose refusal, no JSON
    "context_overflow",  # muninn_chat decode failure (prompt too long / model ctx limit)
    "other",  # uncategorised — a new mode worth a human look
)


def _is_decode_error(exc: Exception) -> bool:
    """True for a ``muninn_chat`` decode failure (e.g. ``prompt decode failed (rc=-3)``)
    — distinct from a real DB error like ``database is locked``. Used to route an
    over-long prompt into the split-and-union retry instead of crashing the run."""
    msg = str(exc).lower()
    return "muninn_chat" in msg or "decode failed" in msg


def categorise_claim_failure(reason: str, raw_excerpt: str) -> str:
    """Map a recorded failure (``reason`` exception string + ``raw_excerpt``) to one of
    :data:`FAILURE_CATEGORIES`. Pure + deterministic so it classifies historical rows.

    The discriminator between *truncation* and *no output* is the excerpt: a balanced
    open brace with array content that never closes is truncation (the dominant mode,
    fixed by a larger output cap / split-and-union); an empty/short non-JSON excerpt is
    an empty response or refusal."""
    r = reason.lower()
    if "muninn_chat" in r or "decode failed" in r:
        return "context_overflow"
    if "must be a json array" in r:
        return "non_array_lens"
    if "missing lens keys" in r:
        return "missing_lens_key"
    excerpt = raw_excerpt.strip()
    if "no balanced json object found" in r:
        # Truncation vs genuinely-no-JSON: did the model start emitting the object?
        if "{" in excerpt and ('"' in excerpt or "[" in excerpt):
            return "truncated_json"
        return "empty_or_refusal"
    # json.JSONDecodeError messages (a ValueError subclass).
    if any(
        s in r
        for s in ("expecting", "unterminated", "delimiter", "invalid control", "extra data")
    ):
        return "truncated_json" if "unterminated" in r else "malformed_json"
    if not excerpt:
        return "empty_or_refusal"
    return "other"


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


def _clear_session_claims(
    conn: sqlite3.Connection, project_id: str, session_id: str, model: str
) -> None:
    conn.execute(
        "DELETE FROM session_claims WHERE project_id = ? AND session_id = ? AND model = ?",
        (project_id, session_id, model),
    )


# Below this prompt size a parse failure is treated as a *genuine* failure, not
# truncation — there's nothing left to usefully split, so we stop and record it.
_MIN_SPLIT_CHARS = 400


def _split_for_retry(texts: list[str]) -> tuple[list[str], list[str]] | None:
    """Halve a batch for the truncation retry, returning ``None`` when it can't be
    split usefully (→ a genuine, non-truncation failure).

    Two cases: a multi-prompt session splits **by prompt count**; a single over-long
    prompt splits **internally** at a newline near its midpoint (so each half is
    independently extractable). The single-prompt case is essential — splitting only by
    count bottoms out at one dense prompt that alone overflows the cap, which is exactly
    the residual failure mode the count-split couldn't fix."""
    if len(texts) > 1:
        mid = len(texts) // 2
        return texts[:mid], texts[mid:]
    text = texts[0]
    if len(text) < _MIN_SPLIT_CHARS:
        return None
    mid = len(text) // 2
    cut = text.find("\n", mid)  # prefer a line boundary at/after the midpoint
    if cut == -1 or cut >= len(text) - 1:
        cut = text.rfind("\n", 0, mid)  # else the last boundary before it
    if cut <= 0:
        cut = mid  # no newline at all — hard split (rare; a single huge line)
    left, right = text[:cut].strip(), text[cut:].strip()
    if not left or not right:
        return None
    return [left], [right]


def _extract_lens_lists(
    engine: ClaimsEngine, model: str, texts: list[str]
) -> dict[str, list[str]]:
    """Extract claim lists for ``texts``, splitting on parse failure.

    Two failure modes route to the same split-and-union recovery: **output truncation**
    (the GBNF grammar guarantees a well-formed *prefix*, so hitting the token cap leaves
    an unbalanced object ``parse_lens_lists`` rejects) and **input overflow** (a prompt
    too long for n_ctx → ``muninn_chat`` decode failure). Because extractive claims
    compose by **set-union**, a session's claims equal the union of its sub-batches' — so
    we halve (:func:`_split_for_retry`) and union, recursing until the input is too small
    to split (then a still-failing extract is a *genuine* failure that propagates). A
    non-decode ``OperationalError`` (e.g. a locked DB) is re-raised untouched."""
    prompt = _CLAIMS_PROMPT_HEADER + "\n\n".join(texts)
    try:
        return parse_lens_lists(engine.extract(model, prompt))
    except (ValueError, KeyError, sqlite3.OperationalError) as exc:
        if isinstance(exc, sqlite3.OperationalError) and not _is_decode_error(exc):
            raise  # a real DB error, not an over-long-prompt decode failure
        halves = _split_for_retry(texts)
        if halves is None:
            raise  # cannot split further — a real failure, not truncation/overflow
        left = _extract_lens_lists(engine, model, halves[0])
        right = _extract_lens_lists(engine, model, halves[1])
        return {k: [*left.get(k, []), *right.get(k, [])] for k in LENS_LIST_KEYS}


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
    raw = ""  # may stay empty if the extract itself fails (decode/overflow, no output)
    try:
        raw = engine.extract(model, prompt)
        lens_lists = parse_lens_lists(raw)
    except (ValueError, KeyError, sqlite3.OperationalError) as exc:
        # Two recoverable modes: output truncation (parse error on a claim-dense session)
        # and input overflow (muninn decode failure when the prompt exceeds n_ctx). Both
        # retry via split-and-union — a session's claims are the set-union of its
        # sub-batches'. A non-decode OperationalError (e.g. a locked DB) is re-raised.
        # The original top-level ``raw`` is recorded on a hard failure (its tail makes the
        # mode diagnosable; empty when the extract never returned).
        if isinstance(exc, sqlite3.OperationalError) and not _is_decode_error(exc):
            raise
        halves = _split_for_retry(human_texts)
        if halves is None:
            _record_failure(conn, project_id, session_id, model, str(exc), raw, content_hash)
            _clear_session_claims(conn, project_id, session_id, model)
            conn.commit()
            raise
        try:
            left = _extract_lens_lists(engine, model, halves[0])
            right = _extract_lens_lists(engine, model, halves[1])
            lens_lists = {k: [*left.get(k, []), *right.get(k, [])] for k in LENS_LIST_KEYS}
        except (ValueError, KeyError, sqlite3.OperationalError) as split_exc:
            if isinstance(split_exc, sqlite3.OperationalError) and not _is_decode_error(split_exc):
                raise
            _record_failure(
                conn, project_id, session_id, model, str(split_exc), raw, content_hash
            )
            _clear_session_claims(conn, project_id, session_id, model)
            conn.commit()
            raise

    # Success — clear any prior failure row + stale claims, then insert fresh claims.
    conn.execute(
        "DELETE FROM session_claim_failures WHERE project_id = ? AND session_id = ? AND model = ?",
        (project_id, session_id, model),
    )
    _clear_session_claims(conn, project_id, session_id, model)
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


# --- L2: the set-union/greedy-cosine reducer is RETIRED (CR6) --------------
#
# ``dedup_claims`` + ``set_union_rollup`` (exact-normalised grouping + a single-pass GREEDY
# cosine merge → ``rollup_claims``) are replaced by EVoC hierarchical clustering in
# ``claim_clustering.py`` (``cluster_claims`` + ``cluster_rollup`` → ``rollup_clusters``).
# The exact-normalised tier survives as the leaf dedup in ``cluster_rollup``; the greedy
# cosine tier — which over-merged ``A~B~C`` chains and split near-dupes — is gone. The old
# code is archived verbatim at ``tmp/archived/database/sqlite/claims_greedy_cosine.py``.
# ``extract_session_claims`` (L1) and ``rollup_failures`` (the parallel failure stream)
# below are unchanged.


def rollup_failures(
    conn: sqlite3.Connection,
    model: str,
    granularity: str,
    resolver: ProjectResolver,
) -> int:
    """Roll up the failure stream parallel to claims: failed-session COUNT per
    scope×grain×bucket, with provenance. Returns rows written to rollup_claim_failures.

    Full rebuild for ``(model, granularity)``: stale rows are deleted first, so once a
    session's failure is fixed (its row cleared from ``session_claim_failures``) the
    scope/bucket failure count drops to 0 instead of stranding a phantom count.
    """
    ensure_claims_schema(conn)
    conn.execute(
        "DELETE FROM rollup_claim_failures WHERE model = ? AND time_granularity = ?",
        (model, granularity),
    )
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
