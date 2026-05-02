"""KG payload builder — what the cytoscape page reads.

Mirrors the contract at ``viz/server/kg.py`` so the typed frontend client
in this repo can be reused. Only the entity-resolved (``er``) graph is
exposed by this project — the base graph is intentionally out of scope.

The seed-and-expand mechanism: pick the top-N seed nodes by a centrality
metric over the FILTERED graph, then BFS-expand from those seeds through
the undirected edge view up to ``max_depth`` hops (0 = unlimited).

Filtering by ``days`` / ``project`` walks the chain
events → event_message_chunks → entities → entity_clusters
to compute the set of canonical entity names attributable to chunks
within the time window / project, then restricts the node and edge sets
to that subgraph before seed-and-expand runs. Centrality is recomputed
on the filtered subgraph so node sizes reflect the visible structure.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict, deque
from typing import Literal

from pydantic import BaseModel

from claude_code_sessions.database.sqlite.filters import (
    days_clause,
    project_clause,
)

log = logging.getLogger(__name__)


SeedMetric = Literal["degree", "node_betweenness", "edge_betweenness"]
VALID_SEED_METRICS: tuple[SeedMetric, ...] = ("degree", "node_betweenness", "edge_betweenness")

# Entity names that collide with JavaScript Object.prototype property
# lookups and crash cytoscape's internal node map (it treats node ids
# as object keys). We filter these from the payload entirely — they
# are noise extracted by NER from prose discussions of programming
# language internals and not interesting as graph nodes.
_FORBIDDEN_NODE_IDS: frozenset[str] = frozenset(
    {
        "constructor",
        "__proto__",
        "__defineGetter__",
        "__defineSetter__",
        "__lookupGetter__",
        "__lookupSetter__",
        "hasOwnProperty",
        "isPrototypeOf",
        "propertyIsEnumerable",
        "toLocaleString",
        "toString",
        "valueOf",
    }
)

DEFAULT_RESOLUTION = 0.25
DEFAULT_TOP_N = 50
DEFAULT_SEED_METRIC: SeedMetric = "edge_betweenness"
DEFAULT_MAX_DEPTH = 0
DEFAULT_MIN_DEGREE = 1


class KGNode(BaseModel):
    id: str
    label: str
    entity_type: str | None = None
    community_id: int | None = None
    mention_count: int | None = None
    node_betweenness: float | None = None


class KGEdge(BaseModel):
    source: str
    target: str
    rel_type: str | None = None
    weight: float | None = None
    edge_betweenness: float | None = None


class KGCommunity(BaseModel):
    id: int
    label: str | None = None
    member_count: int
    node_ids: list[str]


class KGPayload(BaseModel):
    table_id: str
    resolution: float
    seed_metric: SeedMetric
    max_depth: int
    min_degree: int
    node_count: int
    edge_count: int
    community_count: int
    total_node_count: int
    total_edge_count: int
    nodes: list[KGNode]
    edges: list[KGEdge]
    communities: list[KGCommunity]
    # Reflect the active filter back to the client so it can render
    # banners / breadcrumbs without round-tripping the URL state.
    filtered_days: int | None = None
    filtered_project: str | None = None
    filtered_node_count: int | None = None  # nodes after time/project filter, before seed-expand


class KGDataMissing(RuntimeError):
    """The KG tables exist but contain no data — the pipeline has not run yet."""


def _table_has_rows(conn: sqlite3.Connection, table: str) -> bool:
    try:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]) > 0
    except sqlite3.OperationalError:
        return False


def _available_resolutions(conn: sqlite3.Connection) -> list[float]:
    try:
        rows = conn.execute(
            "SELECT DISTINCT resolution FROM leiden_communities ORDER BY resolution"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [float(r[0]) for r in rows]


def _pick_resolution(conn: sqlite3.Connection, requested: float | None) -> float:
    available = _available_resolutions(conn)
    if not available:
        raise KGDataMissing(
            "leiden_communities is empty — run the KG pipeline (server start runs it; "
            "ensure new chunks have been embedded)."
        )
    if requested is None:
        return DEFAULT_RESOLUTION if DEFAULT_RESOLUTION in available else available[0]
    if requested not in available:
        raise ValueError(f"resolution {requested} not in {available}")
    return requested


def _load_nodes(conn: sqlite3.Connection, resolution: float) -> dict[str, KGNode]:
    """Map node name → KGNode with community_id populated for `resolution`."""
    community_map: dict[str, int] = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            "SELECT node, community_id FROM leiden_communities WHERE resolution = ?",
            (resolution,),
        ).fetchall()
    }
    nodes: dict[str, KGNode] = {}
    for row in conn.execute(
        "SELECT name, entity_type, mention_count FROM nodes"
    ).fetchall():
        name = str(row[0])
        if name in _FORBIDDEN_NODE_IDS:
            continue
        nodes[name] = KGNode(
            id=name,
            label=name,
            entity_type=row[1],
            mention_count=int(row[2]) if row[2] is not None else None,
            community_id=community_map.get(name),
        )
    return nodes


def _load_edges(conn: sqlite3.Connection) -> list[KGEdge]:
    edges = []
    for r in conn.execute("SELECT src, dst, rel_type, weight FROM edges").fetchall():
        src = str(r[0])
        dst = str(r[1])
        if src in _FORBIDDEN_NODE_IDS or dst in _FORBIDDEN_NODE_IDS:
            continue
        edges.append(
            KGEdge(
                source=src,
                target=dst,
                rel_type=r[2],
                weight=float(r[3]) if r[3] is not None else None,
            )
        )
    return edges


def _compute_node_betweenness(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute(
        "SELECT node, centrality FROM graph_node_betweenness "
        "WHERE edge_table = 'edges' AND src_col = 'src' AND dst_col = 'dst' "
        "  AND direction = 'both'"
    ).fetchall()
    return {str(r[0]): float(r[1]) for r in rows}


def _compute_edge_betweenness(conn: sqlite3.Connection) -> dict[tuple[str, str], float]:
    rows = conn.execute(
        "SELECT src, dst, centrality FROM graph_edge_betweenness "
        "WHERE edge_table = 'edges' AND src_col = 'src' AND dst_col = 'dst' "
        "  AND direction = 'both'"
    ).fetchall()
    out: dict[tuple[str, str], float] = {}
    for src, dst, centrality in rows:
        # Symmetrize so lookup works regardless of edge direction.
        out[(str(src), str(dst))] = float(centrality)
        out[(str(dst), str(src))] = float(centrality)
    return out


def _build_communities(
    nodes: dict[str, KGNode],
    labels: dict[int, str],
) -> list[KGCommunity]:
    members: dict[int, list[str]] = defaultdict(list)
    for node in nodes.values():
        if node.community_id is not None:
            members[node.community_id].append(node.id)
    out: list[KGCommunity] = []
    for cid, node_ids in sorted(members.items()):
        out.append(
            KGCommunity(
                id=cid,
                label=labels.get(cid),
                member_count=len(node_ids),
                node_ids=node_ids,
            )
        )
    return out


def _allowed_canonicals(
    conn: sqlite3.Connection,
    *,
    days: int | None,
    project: str | None,
) -> set[str] | None:
    """Resolve the global filters to a set of allowed canonical names.

    Returns ``None`` when no filter is active — callers treat that as
    "include every node". When at least one of ``days`` / ``project`` is
    set, walks events → chunks → entities → entity_clusters to find the
    canonical names attributable to chunks inside the time window /
    project, and returns that set.
    """
    has_days = days is not None and days > 0
    has_project = bool(project)
    if not has_days and not has_project:
        return None

    days_part = days_clause(days, "e.timestamp")
    project_part = project_clause(project, "e.project_id")
    filter_clauses = " ".join(p for p in (days_part, project_part) if p)

    sql = f"""
        SELECT DISTINCT ec.canonical
        FROM entities ent
        JOIN event_message_chunks emc ON emc.chunk_id = ent.chunk_id
        JOIN events e ON e.id = emc.event_id
        LEFT JOIN entity_clusters ec ON ec.name = ent.name
        WHERE 1=1 {filter_clauses}
    """
    rows = conn.execute(sql).fetchall()
    out: set[str] = set()
    for r in rows:
        # entity_clusters.canonical is NULL for unresolved entities; in
        # that case the canonical IS the raw entity name (singletons).
        if r[0] is not None:
            out.add(str(r[0]))
    # Also include singletons (entities with no entity_clusters row at
    # all) by re-walking via raw entity name.
    raw_sql = f"""
        SELECT DISTINCT ent.name
        FROM entities ent
        JOIN event_message_chunks emc ON emc.chunk_id = ent.chunk_id
        JOIN events e ON e.id = emc.event_id
        WHERE 1=1 {filter_clauses}
    """
    raw_rows = conn.execute(raw_sql).fetchall()
    cluster_map: dict[str, str] = {
        str(row[0]): str(row[1])
        for row in conn.execute("SELECT name, canonical FROM entity_clusters").fetchall()
    }
    for r in raw_rows:
        name = str(r[0])
        out.add(cluster_map.get(name, name))
    return out


def _seed_score(
    metric: SeedMetric,
    name: str,
    degree: dict[str, int],
    node_bc: dict[str, float],
    edge_bc_per_node: dict[str, float],
) -> float:
    if metric == "degree":
        return float(degree.get(name, 0))
    if metric == "node_betweenness":
        return node_bc.get(name, 0.0)
    return edge_bc_per_node.get(name, 0.0)


def load_kg_er(
    conn: sqlite3.Connection,
    *,
    resolution: float | None = None,
    top_n: int = DEFAULT_TOP_N,
    seed_metric: SeedMetric = DEFAULT_SEED_METRIC,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_degree: int = DEFAULT_MIN_DEGREE,
    days: int | None = None,
    project: str | None = None,
) -> KGPayload:
    """Build the entity-resolved KG payload for cytoscape consumption.

    Applies optional ``days`` (look-back window) and ``project`` filters
    *before* seed-and-expand, so the seeds and expansion run on the
    subgraph the user actually cares about.
    """
    if seed_metric not in VALID_SEED_METRICS:
        raise ValueError(f"seed_metric must be one of {VALID_SEED_METRICS}, got {seed_metric!r}")
    if max_depth < 0:
        raise ValueError(f"max_depth must be >= 0, got {max_depth}")
    if min_degree < 0:
        raise ValueError(f"min_degree must be >= 0, got {min_degree}")
    if top_n <= 0:
        raise ValueError(f"top_n must be > 0, got {top_n}")

    if not _table_has_rows(conn, "nodes"):
        raise KGDataMissing(
            "nodes table is empty — run the KG pipeline (server start populates it)."
        )

    chosen_resolution = _pick_resolution(conn, resolution)
    nodes_by_name = _load_nodes(conn, chosen_resolution)
    edges = _load_edges(conn)

    total_node_count = len(nodes_by_name)
    total_edge_count = len(edges)

    # ── Apply global filters (time / project) ─────────────────────────
    # The allow-set is derived from chunks → entities → canonical, so a
    # canonical only survives if at least one of its raw mentions came
    # from a chunk inside the filter window.
    allowed = _allowed_canonicals(conn, days=days, project=project)
    if allowed is not None:
        nodes_by_name = {name: node for name, node in nodes_by_name.items() if name in allowed}
        edges = [e for e in edges if e.source in nodes_by_name and e.target in nodes_by_name]
    filtered_node_count = len(nodes_by_name) if allowed is not None else None

    # Centrality on the FULL graph.
    node_bc = _compute_node_betweenness(conn)
    edge_bc = _compute_edge_betweenness(conn)
    for name, node in nodes_by_name.items():
        node.node_betweenness = node_bc.get(name)
    for edge in edges:
        edge.edge_betweenness = edge_bc.get((edge.source, edge.target))

    # Adjacency + per-node degree (undirected).
    adj: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        adj[e.source].add(e.target)
        adj[e.target].add(e.source)
    degree: dict[str, int] = {name: len(adj[name]) for name in nodes_by_name}

    # Edge-betweenness summed per node (used as a node-level seed metric).
    edge_bc_per_node: dict[str, float] = defaultdict(float)
    for e in edges:
        bc = e.edge_betweenness or 0.0
        edge_bc_per_node[e.source] += bc
        edge_bc_per_node[e.target] += bc

    # Pick top-N seeds.
    candidate_names = list(nodes_by_name.keys())
    candidate_names.sort(
        key=lambda n: _seed_score(seed_metric, n, degree, node_bc, edge_bc_per_node),
        reverse=True,
    )
    seeds = candidate_names[:top_n]

    # BFS-expand from the seeds.
    visited: set[str] = set(seeds)
    if max_depth == 0:
        # Unlimited — flood every component containing a seed.
        queue: deque[str] = deque(seeds)
        while queue:
            cur = queue.popleft()
            for nbr in adj[cur]:
                if nbr not in visited:
                    visited.add(nbr)
                    queue.append(nbr)
    else:
        depth: dict[str, int] = dict.fromkeys(seeds, 0)
        queue = deque(seeds)
        while queue:
            cur = queue.popleft()
            d = depth[cur]
            if d >= max_depth:
                continue
            for nbr in adj[cur]:
                if nbr not in visited:
                    visited.add(nbr)
                    depth[nbr] = d + 1
                    queue.append(nbr)

    # min_degree filter.
    if min_degree > 0:
        visited = {n for n in visited if degree.get(n, 0) >= min_degree}

    selected_nodes = [nodes_by_name[n] for n in visited if n in nodes_by_name]
    selected_node_ids = {n.id for n in selected_nodes}
    selected_edges = [
        e for e in edges
        if e.source in selected_node_ids and e.target in selected_node_ids
    ]

    # Restrict communities to the selected node set; preserve ordering by id.
    label_rows = conn.execute(
        "SELECT community_id, label FROM community_labels WHERE resolution = ?",
        (chosen_resolution,),
    ).fetchall()
    labels = {int(r[0]): str(r[1]) for r in label_rows if r[1] is not None}
    selected_subset = {n.id: n for n in selected_nodes}
    communities = _build_communities(selected_subset, labels)

    return KGPayload(
        table_id="er",
        resolution=chosen_resolution,
        seed_metric=seed_metric,
        max_depth=max_depth,
        min_degree=min_degree,
        node_count=len(selected_nodes),
        edge_count=len(selected_edges),
        community_count=len(communities),
        total_node_count=total_node_count,
        total_edge_count=total_edge_count,
        nodes=selected_nodes,
        edges=selected_edges,
        communities=communities,
        filtered_days=days,
        filtered_project=project,
        filtered_node_count=filtered_node_count,
    )
