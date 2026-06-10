"""CR6 L2b — name each surfaced cluster by its common thread (LLM, bounded + cached).

After :func:`claim_clustering.cluster_claims` builds the global taxonomy, every surfaced
cluster gets a short human-readable **name** synthesised from its member claim texts — the
"common thread" the user asked for. This is the only LLM call at the rollup tier, and it is
bounded (one call per *surfaced cluster*, globally, cached by a hash of the member texts —
NOT one per scope×bucket cell).

Audit trail: a name is generated *from* the cluster's member claims, and those claims are
recoverable via ``claim_cluster_membership`` (``layer``, ``cluster_id`` → every
``claim_id``). So each name is always attributable to the exact claims that formed it.

Fail-loud: a naming/parse failure raises (no silent "use the first claim"), consistent with
the project's no-graceful-degradation rule.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import UTC, datetime
from typing import Protocol

from claude_code_sessions.database.sqlite.claim_clustering import ensure_clustering_schema
from claude_code_sessions.database.sqlite.summaries import (
    CLUSTER_NAME_GBNF,
    CLUSTER_NAME_MAX_TOKENS,
)
from claude_code_sessions.database.sqlite.summary_json import LENS_LIST_KEYS, parse_cluster_name

log = logging.getLogger(__name__)

# Cap on member claim texts fed into one naming prompt — a cluster can have hundreds of
# members; the common thread is evident from a representative sample and the cap bounds the
# prompt size. Most-frequent/longest-first selection happens in the caller's query.
_MAX_MEMBERS_IN_PROMPT = 40

_NAME_PROMPT_HEADER = (
    "These short claims about a developer's coding sessions were grouped together because "
    "they are semantically similar (lens: {lens}). In ≤8 words, name the single common "
    "thread that unites them — a concise, specific label a developer would recognise. "
    'Reply with a JSON object: {{"name": "<the label>"}}.\n\nClaims:\n'
)


class ClusterNamer(Protocol):
    """Text-completion backend yielding the ``{"name": ...}`` JSON (CR6 L2b)."""

    def name(self, model: str, prompt: str) -> str: ...


class MuninnClusterNamer:
    """Production :class:`ClusterNamer` — drives ``muninn_chat`` with the name grammar."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def name(self, model: str, prompt: str) -> str:
        row = self._conn.execute(
            "SELECT muninn_chat(?, ?, ?, ?)",
            (model, prompt, CLUSTER_NAME_GBNF, CLUSTER_NAME_MAX_TOKENS),
        ).fetchone()
        return str(row[0]) if row is not None and row[0] is not None else ""


def _member_texts(
    conn: sqlite3.Connection, model: str, lens: str, layer: int, cluster_id: int
) -> list[str]:
    """The distinct member claim texts of a cluster at a layer, frequency-ranked (the most
    common claims most define the thread), capped for the prompt."""
    rows = conn.execute(
        """SELECT sc.claim AS claim, COUNT(*) AS n
           FROM claim_cluster_membership m
           JOIN session_claims sc
             ON sc.rowid = m.claim_id AND sc.model = m.model AND sc.lens = m.lens
           WHERE m.model = ? AND m.lens = ? AND m.layer = ? AND m.cluster_id = ?
           GROUP BY sc.claim
           ORDER BY n DESC, sc.claim
           LIMIT ?""",
        (model, lens, layer, cluster_id, _MAX_MEMBERS_IN_PROMPT),
    ).fetchall()
    return [str(r["claim"]) for r in rows]


def _name_source_hash(texts: list[str]) -> str:
    """Stable hash of a cluster's member texts → re-name only when membership changes."""
    digest = hashlib.sha256()
    for text in sorted(texts):
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def name_clusters(conn: sqlite3.Connection, model: str, namer: ClusterNamer) -> int:
    """Name every surfaced cluster for ``model`` (the fine + coarse layers in
    ``claim_cluster_meta``), skipping noise (-1) and clusters whose members are unchanged
    since their last naming (``name_source_hash`` cache hit). Returns names (re)generated.

    Fail-loud: a parse/empty failure on any cluster propagates (the run records it like an
    L1 failure upstream); a cluster name is never silently blanked."""
    ensure_clustering_schema(conn)
    named = 0
    for lens in LENS_LIST_KEYS:
        meta = conn.execute(
            "SELECT fine_layer, coarse_layer FROM claim_cluster_meta WHERE model = ? AND lens = ?",
            (model, lens),
        ).fetchone()
        if meta is None:
            continue
        surfaced = {int(meta["fine_layer"]), int(meta["coarse_layer"])}
        for layer in sorted(surfaced):
            clusters = conn.execute(
                """SELECT cluster_id, name, name_source_hash FROM claim_clusters
                   WHERE model = ? AND lens = ? AND layer = ? AND cluster_id >= 0""",
                (model, lens, layer),
            ).fetchall()
            for c in clusters:
                texts = _member_texts(conn, model, lens, layer, int(c["cluster_id"]))
                if not texts:
                    continue
                source_hash = _name_source_hash(texts)
                if c["name"] is not None and c["name_source_hash"] == source_hash:
                    continue  # cache hit — members unchanged since last naming
                prompt = _NAME_PROMPT_HEADER.format(lens=lens) + "\n".join(
                    f"- {t}" for t in texts
                )
                name = parse_cluster_name(namer.name(model, prompt))
                conn.execute(
                    """UPDATE claim_clusters SET name = ?, name_source_hash = ?, generated_at = ?
                       WHERE model = ? AND lens = ? AND layer = ? AND cluster_id = ?""",
                    (name, source_hash, datetime.now(UTC).isoformat(),
                     model, lens, layer, int(c["cluster_id"])),
                )
                named += 1
        log.info("  named clusters for lens=%s (model=%s)", lens, model)
    conn.commit()
    return named
