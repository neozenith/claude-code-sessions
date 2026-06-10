"""CR6 EVoC clustering — replaces the CR5 greedy-cosine L2 reduce.

The CR5 reduce (:func:`claims.dedup_claims`, now archived) merged claims with a
single-pass greedy cosine pass — order-dependent single-linkage with no global view of
the embedding manifold (over-merges ``A~B~C`` chains, leaves near-dupes split). This
module replaces that with **EVoC** density-based hierarchical clustering over claim
embeddings, run **globally per ``(model, lens)``** so a cluster is a *stable semantic
concept* (the same at root and at a leaf project).

Pipeline (drives off the existing ``session_claims`` L1 rows):

* **L1.5** :func:`sync_claim_embeddings` — fill ``session_claims.embedding`` (incremental,
  ``muninn_embed``), the input to clustering.
* **L2a** :func:`cluster_claims` — per ``(model, lens)``: EVoC over the *distinct claim
  concepts* → ``claim_clusters`` (the full layer stack, with derived parent links) +
  ``claim_cluster_membership`` (every ``claim_id`` → cluster at every layer = the audit
  trail) + ``claim_cluster_meta`` (which two layers the UI surfaces).
* **L2b** :func:`name_clusters` (in :mod:`claim_naming`) — LLM "common-thread" name per
  surfaced cluster.
* **L3** :func:`cluster_rollup` — per scope×bucket×lens: exact-normalised leaf claims
  (still verbatim/grounded), each **tagged with its fine-layer cluster_id**, into
  ``rollup_clusters``. The backend assembles coarse→fine→leaf from this + the global
  ``claim_clusters`` taxonomy.

EVoC merely *groups* the leaf claims under named parents; it never rewrites them, so the
CR5 grounding + associativity properties survive. The only LLM cost is the bounded global
naming pass (L2b), not a per-merge-node call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import numpy as np

from claude_code_sessions.database.sqlite.embeddings import GGUF_EMBEDDING_DIM
from claude_code_sessions.database.sqlite.summaries import _resolve_scopes
from claude_code_sessions.database.sqlite.summary_json import LENS_LIST_KEYS
from claude_code_sessions.database.sqlite.time_buckets import bucket_expr
from claude_code_sessions.project_resolver import ProjectResolver

log = logging.getLogger(__name__)

# A text -> raw float32 vector blob (exactly what ``muninn_embed`` returns). Injected so
# clustering is unit-testable with deterministic vectors and no GGUF load.
EmbedFn = Callable[[str], bytes]


class Clusterer(Protocol):
    """The subset of EVoC's fitted interface this module relies on (so tests can inject a
    deterministic fake instead of running the real numba-backed clusterer)."""

    cluster_layers_: list[Any]
    membership_strength_layers_: list[Any]
    persistence_scores_: list[float]

    def fit_predict(self, X: Any) -> Any: ...


# --- EVoC parameters (tunable; clustering quality lives here) ----------------
EVOC_BASE_MIN_CLUSTER_SIZE = 5
EVOC_MIN_SAMPLES = 5
EVOC_N_NEIGHBORS = 15
EVOC_MAX_LAYERS = 10
# Deterministic so reindexes + tests reproduce the same taxonomy (EVoC is stochastic
# otherwise — node embedding + label propagation use RNG).
EVOC_RANDOM_STATE = 42
# How many hierarchy levels the explorer surfaces by default. Written as a knob so a
# future "give me more depth" needs no re-cluster (the full stack is already persisted).
SURFACED_LAYERS = 2


def viable_n() -> int:
    """Minimum distinct concepts for EVoC to form a kNN graph + a density estimate.
    Below this clustering is mathematically undefined → singleton identity layering
    (:func:`cluster_claims`). NOT graceful degradation: it's the defined boundary result,
    surfaced via ``claim_cluster_meta.used_singleton``."""
    return max(EVOC_N_NEIGHBORS + 1, 2 * EVOC_BASE_MIN_CLUSTER_SIZE)


def default_clusterer_factory() -> Clusterer:
    """Construct a fresh, deterministically-seeded EVoC. Imported lazily so importing this
    module (e.g. for the schema) doesn't pull numba/matplotlib until a cluster run."""
    from evoc import EVoC

    return cast(
        "Clusterer",
        EVoC(
            random_state=EVOC_RANDOM_STATE,
            base_min_cluster_size=EVOC_BASE_MIN_CLUSTER_SIZE,
            min_samples=EVOC_MIN_SAMPLES,
            n_neighbors=EVOC_N_NEIGHBORS,
            max_layers=EVOC_MAX_LAYERS,
        ),
    )


# --- Schema (additive; idempotent — like the CR5 claims tables) --------------
CLUSTERING_SCHEMA_SQL = """
-- The global semantic taxonomy: one row per (model, lens, layer, cluster_id). The FULL
-- EVoC layer stack is persisted so surfaced depth is a config knob, not a rebuild.
CREATE TABLE IF NOT EXISTS claim_clusters (
    model TEXT NOT NULL,
    lens TEXT NOT NULL,
    layer INTEGER NOT NULL,            -- 0 = finest (most clusters) … coarser as it grows
    cluster_id INTEGER NOT NULL,       -- EVoC label within (model,lens,layer); -1 = noise
    parent_cluster_id INTEGER,         -- plurality parent in layer+1 (coarser); NULL at top/noise
    name TEXT,                         -- LLM common-thread name; NULL until named (deep layers)
    member_claim_count INTEGER NOT NULL,
    name_source_hash TEXT,             -- hash of member texts → re-name only when members change
    generated_at TEXT NOT NULL,
    PRIMARY KEY (model, lens, layer, cluster_id)
);
CREATE INDEX IF NOT EXISTS idx_claim_clusters_lens ON claim_clusters(model, lens, layer);

-- The audit trail: every claim instance → its cluster at every layer. Keyed on
-- session_claims.rowid so a cluster name is always attributable to the exact claims.
CREATE TABLE IF NOT EXISTS claim_cluster_membership (
    model TEXT NOT NULL,
    lens TEXT NOT NULL,
    claim_id INTEGER NOT NULL,         -- session_claims.rowid
    layer INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL,
    membership_strength REAL NOT NULL,
    PRIMARY KEY (model, lens, claim_id, layer)
);
CREATE INDEX IF NOT EXISTS idx_ccm_cluster
    ON claim_cluster_membership(model, lens, layer, cluster_id);

-- Which two layers the explorer surfaces (coarse + fine), per (model, lens). The single
-- source of truth so the rollup + read path never recompute the selection.
CREATE TABLE IF NOT EXISTS claim_cluster_meta (
    model TEXT NOT NULL,
    lens TEXT NOT NULL,
    n_layers INTEGER NOT NULL,
    fine_layer INTEGER NOT NULL,
    coarse_layer INTEGER NOT NULL,
    used_singleton INTEGER NOT NULL,   -- 1 = below viable_n(), each concept its own cluster
    n_concepts INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (model, lens)
);

-- L3 leaf rollup (replaces rollup_claims as the read source): the exact-normalised leaf
-- claims per scope×bucket×lens, each TAGGED with its fine-layer cluster_id. Cluster nodes
-- + salience are assembled at read time by grouping on cluster_id and joining the global
-- claim_clusters names. Verbatim claims survive as the tree's leaves (grounding).
CREATE TABLE IF NOT EXISTS rollup_clusters (
    model TEXT NOT NULL,
    scope_path TEXT NOT NULL,
    scope_depth INTEGER NOT NULL,
    time_granularity TEXT NOT NULL,
    time_bucket TEXT NOT NULL,
    lens TEXT NOT NULL,
    cluster_id INTEGER NOT NULL,       -- fine-layer cluster (-1 = unclustered/noise)
    claim_index INTEGER NOT NULL,      -- rank of the leaf claim within (lens, scope, bucket)
    claim TEXT NOT NULL,
    count INTEGER NOT NULL,            -- distinct sessions expressing this leaf claim
    source_session_ids TEXT NOT NULL,  -- JSON array, provenance / json_each reverse-lookup
    source_hash TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    PRIMARY KEY (model, scope_path, time_granularity, time_bucket, lens, claim_index)
);
CREATE INDEX IF NOT EXISTS idx_rollup_clusters_scope
    ON rollup_clusters(model, scope_path, lens);
"""


def ensure_clustering_schema(conn: sqlite3.Connection) -> None:
    """Create the CR6 clustering tables if absent (idempotent, non-destructive)."""
    conn.executescript(CLUSTERING_SCHEMA_SQL)


# --- L1.5: claim embedding ---------------------------------------------------

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Casefold + whitespace-collapse — the concept key (identical claims share a vector
    and a leaf row). Mirrors the exact tier the archived ``dedup_claims`` used."""
    return _WS.sub(" ", text.strip().casefold())


def _decode_vec(blob: bytes) -> np.ndarray:
    """Decode a ``muninn_embed`` blob to a float32 vector, validating dimensionality."""
    vec = np.frombuffer(blob, dtype=np.float32)
    if vec.shape[0] != GGUF_EMBEDDING_DIM:
        raise ValueError(
            f"claim embedding has dim {vec.shape[0]}, expected {GGUF_EMBEDDING_DIM} "
            "(model/dim mismatch — rebuild embeddings)"
        )
    return vec


def sync_claim_embeddings(conn: sqlite3.Connection, model: str, embed: EmbedFn) -> int:
    """Fill ``session_claims.embedding`` for this model's rows that lack it (incremental,
    mirrors ``embeddings.sync_embeddings``). Returns the number embedded.

    Embeds the *distinct* normalised claim texts once and writes the shared vector to
    every instance row of that concept — identical claims need one ``muninn_embed`` call,
    not one per session."""
    rows = conn.execute(
        "SELECT rowid, claim FROM session_claims WHERE model = ? AND embedding IS NULL",
        (model,),
    ).fetchall()
    if not rows:
        return 0
    by_concept: dict[str, list[int]] = defaultdict(list)
    repr_text: dict[str, str] = {}
    for rowid, claim in rows:
        key = _normalize(str(claim))
        if not key:
            continue
        by_concept[key].append(int(rowid))
        repr_text.setdefault(key, str(claim))
    log.info("  embedding %d claim concepts (%d rows) for model=%s",
             len(by_concept), len(rows), model)
    written = 0
    for key, rowids in by_concept.items():
        blob = embed(repr_text[key])
        _decode_vec(blob)  # fail-loud on a dim mismatch before persisting
        conn.executemany(
            "UPDATE session_claims SET embedding = ? WHERE rowid = ?",
            [(blob, rid) for rid in rowids],
        )
        written += len(rowids)
    conn.commit()
    return written


# --- L2a: EVoC clustering ----------------------------------------------------


def select_layers(n_layers: int, persistence: list[float]) -> tuple[int, int]:
    """Choose the (coarse, fine) layer indices the explorer surfaces.

    EVoC orders ``cluster_layers_`` finest→coarsest (index 0 = most clusters). ``fine`` =
    the best-persistence layer (EVoC's own ``labels_``); ``coarse`` = the next coarser
    layer (``fine + 1``) so the two are consecutive and ``parent_cluster_id`` (plurality in
    ``layer+1``) connects them directly. Degenerates to a single level when EVoC emits one
    layer."""
    if n_layers <= 1:
        return (0, 0)
    fine = int(np.argmax(persistence)) if persistence else 0
    if fine >= n_layers - 1:  # best is the coarsest → step down so a coarser parent exists
        fine = n_layers - 2
    return (fine + 1, fine)


def _plurality_parents(
    labels_fine: np.ndarray, labels_coarse: np.ndarray
) -> dict[int, int | None]:
    """Map each fine-layer cluster to its parent coarse-layer cluster by plurality vote of
    the points it contains. EVoC layers are *separate* clusterings (not strictly nested),
    so this imposes a clean tree. Noise (-1) maps to no parent."""
    votes: dict[int, Counter[int]] = defaultdict(Counter)
    for fine, coarse in zip(labels_fine.tolist(), labels_coarse.tolist(), strict=True):
        if fine == -1:
            continue
        votes[fine][int(coarse)] += 1
    parents: dict[int, int | None] = {}
    for fine_id, counter in votes.items():
        # most_common is deterministic on count; break ties on smallest coarse id.
        best = min(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        parents[fine_id] = best if best != -1 else None
    return parents


def _clear_clustering(conn: sqlite3.Connection, model: str) -> None:
    for table in ("claim_clusters", "claim_cluster_membership", "claim_cluster_meta"):
        conn.execute(f"DELETE FROM {table} WHERE model = ?", (model,))  # noqa: S608 — fixed names


def cluster_claims(
    conn: sqlite3.Connection,
    model: str,
    *,
    clusterer_factory: Callable[[], Clusterer] = default_clusterer_factory,
) -> dict[str, dict[str, Any]]:
    """Cluster a model's claims globally per lens (full rebuild).

    For each lens: gather the *distinct* claim concepts (one embedding each), run EVoC,
    persist the full layer stack (:data:`claim_clusters`), every claim instance's
    membership at every layer (:data:`claim_cluster_membership`, the audit trail) and the
    surfaced-layer selection (:data:`claim_cluster_meta`). Below :func:`viable_n` concepts
    EVoC can't run, so each concept becomes its own singleton cluster in a single layer.

    Requires :func:`sync_claim_embeddings` to have run (raises if a concept lacks a vector).
    Returns per-lens stats for progress/diagnostics."""
    ensure_clustering_schema(conn)
    _clear_clustering(conn, model)
    now = datetime.now(UTC).isoformat()
    stats: dict[str, dict[str, Any]] = {}

    for lens in LENS_LIST_KEYS:
        rows = conn.execute(
            "SELECT rowid, claim, embedding FROM session_claims WHERE model = ? AND lens = ?",
            (model, lens),
        ).fetchall()
        # Group instance rows into distinct concepts; carry every claim_id for the audit.
        concept_ids: dict[str, list[int]] = defaultdict(list)
        concept_vec: dict[str, np.ndarray] = {}
        for rowid, claim, emb in rows:
            key = _normalize(str(claim))
            if not key:
                continue
            concept_ids[key].append(int(rowid))
            if key not in concept_vec:
                if emb is None:
                    raise ValueError(
                        f"claim {rowid} (lens={lens}) has no embedding — run "
                        "sync_claim_embeddings before cluster_claims"
                    )
                concept_vec[key] = _decode_vec(emb)
        concepts = list(concept_ids.keys())
        n = len(concepts)
        if n == 0:
            continue

        if n < viable_n():
            # Defined boundary: each concept is its own singleton cluster, one layer.
            layers = [np.arange(n, dtype=np.int64)]
            strengths = [np.ones(n, dtype=np.float64)]
            persistence = [0.0]
            used_singleton = True
        else:
            X = np.vstack([concept_vec[c] for c in concepts]).astype(np.float32)
            clusterer = clusterer_factory()
            clusterer.fit_predict(X)
            layers = [np.asarray(c) for c in clusterer.cluster_layers_]
            strengths = [np.asarray(s) for s in clusterer.membership_strength_layers_]
            persistence = [float(p) for p in clusterer.persistence_scores_]
            used_singleton = False
        n_layers = len(layers)
        coarse_layer, fine_layer = select_layers(n_layers, persistence)

        # claim_clusters: member counts per (layer, cluster) + plurality parent links.
        for layer_idx, labels in enumerate(layers):
            parents = (
                _plurality_parents(labels, layers[layer_idx + 1])
                if layer_idx + 1 < n_layers
                else {}
            )
            counts = Counter(int(label) for label in labels.tolist())
            for cluster_id, member_count in counts.items():
                conn.execute(
                    """INSERT INTO claim_clusters
                           (model, lens, layer, cluster_id, parent_cluster_id, name,
                            member_claim_count, name_source_hash, generated_at)
                       VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?)""",
                    (model, lens, layer_idx, cluster_id,
                     parents.get(cluster_id), member_count, now),
                )
            # claim_cluster_membership: expand each concept's label to all its claim_ids.
            for concept_idx, concept in enumerate(concepts):
                cluster_id = int(labels[concept_idx])
                strength = float(strengths[layer_idx][concept_idx])
                conn.executemany(
                    """INSERT OR REPLACE INTO claim_cluster_membership
                           (model, lens, claim_id, layer, cluster_id, membership_strength)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    [(model, lens, cid, layer_idx, cluster_id, strength)
                     for cid in concept_ids[concept]],
                )

        conn.execute(
            """INSERT OR REPLACE INTO claim_cluster_meta
                   (model, lens, n_layers, fine_layer, coarse_layer, used_singleton,
                    n_concepts, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (model, lens, n_layers, fine_layer, coarse_layer, int(used_singleton), n, now),
        )
        stats[lens] = {
            "n_concepts": n, "n_layers": n_layers, "used_singleton": used_singleton,
            "fine_layer": fine_layer, "coarse_layer": coarse_layer,
            "n_fine_clusters": int(len({int(x) for x in layers[fine_layer].tolist()})),
        }
        log.info("  clustered lens=%s: %d concepts → %d layers (fine=%d, singleton=%s)",
                 lens, n, n_layers, fine_layer, used_singleton)
    conn.commit()
    return stats


# --- L3: leaf rollup tagged by fine cluster ----------------------------------


def _fine_cluster_map(conn: sqlite3.Connection, model: str) -> dict[tuple[str, str], int]:
    """``(lens, normalised_claim) -> fine-layer cluster_id`` for tagging leaf rollup rows.
    Joins membership at each lens's surfaced fine layer (from ``claim_cluster_meta``)."""
    rows = conn.execute(
        """SELECT sc.lens AS lens, sc.claim AS claim, m.cluster_id AS cluster_id
           FROM session_claims sc
           JOIN claim_cluster_meta cm ON cm.model = sc.model AND cm.lens = sc.lens
           JOIN claim_cluster_membership m
             ON m.model = sc.model AND m.lens = sc.lens
            AND m.claim_id = sc.rowid AND m.layer = cm.fine_layer
           WHERE sc.model = ?""",
        (model,),
    ).fetchall()
    return {(str(r["lens"]), _normalize(str(r["claim"]))): int(r["cluster_id"]) for r in rows}


class _Leaf:
    """A leaf claim concept at a scope×bucket: representative text, distinct sessions, and
    its fine cluster tag."""

    __slots__ = ("claim", "sessions", "cluster_id")

    def __init__(self, claim: str, cluster_id: int) -> None:
        self.claim = claim
        self.sessions: set[str] = set()
        self.cluster_id = cluster_id

    @property
    def count(self) -> int:
        return len(self.sessions)


def cluster_rollup(
    conn: sqlite3.Connection,
    model: str,
    granularity: str,
    resolver: ProjectResolver,
) -> int:
    """L3 leaf rollup: per scope×bucket×lens, the exact-normalised leaf claims (verbatim),
    each tagged with its fine-layer ``cluster_id``, into ``rollup_clusters``. Full rebuild
    for ``(model, granularity)``. Returns rows written.

    Associative: each scope unions ALL descendant sessions directly. Salience COUNT = the
    distinct sessions expressing a leaf. The semantic *grouping* lives in the cluster tag
    (assembled into coarse→fine nodes at read time); the leaf itself is never rewritten."""
    ensure_clustering_schema(conn)
    conn.execute(
        "DELETE FROM rollup_clusters WHERE model = ? AND time_granularity = ?",
        (model, granularity),
    )
    fine_map = _fine_cluster_map(conn, model)
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
        """,  # noqa: S608 — bucket_sql is a fixed, validated grain expression
        (model,),
    ).fetchall()

    # (scope, bucket, lens) -> {normalised claim -> _Leaf}
    groups: dict[tuple[str, str, str], dict[str, _Leaf]] = defaultdict(dict)
    src: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for r in rows:
        resolved = _resolve_scopes(resolver, r["project_id"])
        if resolved is None:
            continue
        _leaf, ancestors = resolved
        bucket = str(r["bucket"])
        lens = str(r["lens"])
        claim = str(r["claim"])
        key = _normalize(claim)
        if not key:
            continue
        cluster_id = fine_map.get((lens, key), -1)  # -1 = unclustered (no taxonomy yet)
        for scope in ancestors:
            leaves = groups[(scope, bucket, lens)]
            leaf = leaves.get(key)
            if leaf is None:
                leaf = _Leaf(claim, cluster_id)
                leaves[key] = leaf
            leaf.sessions.add(str(r["session_id"]))
            src[(scope, bucket)].add((str(r["session_id"]), str(r["content_hash"])))

    now = datetime.now(UTC).isoformat()
    written = 0
    for (scope, bucket, lens), leaves in groups.items():
        ranked = sorted(leaves.values(), key=lambda v: (-v.count, v.claim))
        source_hash = hashlib.sha256(
            "\x00".join(f"{sid}:{h}" for sid, h in sorted(src[(scope, bucket)])).encode()
        ).hexdigest()
        depth = 0 if scope == "" else scope.count("/") + 1
        for idx, leaf in enumerate(ranked):
            conn.execute(
                """INSERT OR REPLACE INTO rollup_clusters
                       (model, scope_path, scope_depth, time_granularity, time_bucket,
                        lens, cluster_id, claim_index, claim, count,
                        source_session_ids, source_hash, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (model, scope, depth, granularity, bucket, lens, leaf.cluster_id, idx,
                 leaf.claim, leaf.count, json.dumps(sorted(leaf.sessions)), source_hash, now),
            )
            written += 1
    conn.commit()
    return written


# --- read side: assemble the coarse→fine→leaf tree ---------------------------

# A read-side cluster node. A node carries EITHER ``children`` (a coarse node, whose
# children are fine nodes) OR ``members`` (a fine / single-level node, whose members are
# the verbatim leaf claims) — never both. ``count`` is distinct sessions (salience).
ClusterNode = dict[str, Any]
LeafClaim = dict[str, Any]  # {"claim": str, "count": int, "sessions": list[str]}

UNCLUSTERED_ID = -1
UNCLUSTERED_NAME = "Unclustered"


def _cluster_name(cid: int, names: dict[int, str | None]) -> str:
    """Display name for a cluster id — its LLM name, or a stable fallback before naming
    has run / for the noise bucket (display-only; naming failures raise upstream)."""
    if cid == UNCLUSTERED_ID:
        return UNCLUSTERED_NAME
    return names.get(cid) or f"Cluster {cid}"


def assemble_cluster_tree(
    leaves: list[LeafClaim],
    *,
    fine_layer: int,
    coarse_layer: int,
    fine_clusters: dict[int, dict[str, Any]],
    coarse_names: dict[int, str | None],
) -> list[ClusterNode]:
    """Assemble leaf claims (each tagged ``cluster_id`` = its fine cluster) into the
    coarse→fine→leaf tree the explorer renders.

    ``fine_clusters[cid] = {"name", "parent"}`` (parent = coarse cluster id, may be None);
    ``coarse_names[cid] = name``. When ``fine_layer == coarse_layer`` (single EVoC layer or
    the singleton boundary) the tree degenerates to one level: fine nodes carry members
    directly. Noise / parentless fine clusters fold under an "Unclustered" node."""
    fine_names = {cid: meta.get("name") for cid, meta in fine_clusters.items()}
    fine_nodes: dict[int, ClusterNode] = {}
    for leaf in leaves:
        fcid = int(leaf["cluster_id"])
        node = fine_nodes.get(fcid)
        if node is None:
            node = {"cluster_id": fcid, "layer": fine_layer,
                    "name": _cluster_name(fcid, fine_names),
                    "members": [], "_sessions": set()}
            fine_nodes[fcid] = node
        node["members"].append(
            {"claim": leaf["claim"], "count": leaf["count"], "sessions": leaf["sessions"]}
        )
        node["_sessions"].update(leaf["sessions"])
    for node in fine_nodes.values():
        node["members"].sort(key=lambda m: (-m["count"], m["claim"]))

    def _finalize(node: ClusterNode) -> ClusterNode:
        sessions = node.pop("_sessions")
        node["count"] = len(sessions)
        node["sessions"] = sorted(sessions)
        return node

    if fine_layer == coarse_layer:  # single level — fine nodes are the top nodes
        tops = [_finalize(n) for n in fine_nodes.values()]
        tops.sort(key=lambda n: (-n["count"], n["name"]))
        return tops

    coarse_nodes: dict[int, ClusterNode] = {}
    for fcid, fnode in fine_nodes.items():
        parent = fine_clusters.get(fcid, {}).get("parent")
        ccid = parent if (parent is not None and fcid != UNCLUSTERED_ID) else UNCLUSTERED_ID
        cnode = coarse_nodes.get(ccid)
        if cnode is None:
            cnode = {"cluster_id": ccid, "layer": coarse_layer,
                     "name": _cluster_name(ccid, coarse_names),
                     "children": [], "_sessions": set()}
            coarse_nodes[ccid] = cnode
        cnode["_sessions"].update(fnode["_sessions"])
        cnode["children"].append(_finalize(fnode))
    tops = []
    for cnode in coarse_nodes.values():
        cnode["children"].sort(key=lambda n: (-n["count"], n["name"]))
        tops.append(_finalize(cnode))
    tops.sort(key=lambda n: (-n["count"], n["name"]))
    return tops
