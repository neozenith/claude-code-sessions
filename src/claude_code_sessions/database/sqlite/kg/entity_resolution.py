"""Entity-resolution phase — collapse synonyms into canonical clusters.

Uses ``muninn_extract_er(vec_table, name_col, k, dist_threshold, jw_weight,
borderline_delta, eb_threshold_or_null, type_filter, type_filter_col)`` —
sqlite-muninn's all-in-one ER pipeline that does HNSW blocking →
Jaro-Winkler + cosine scoring → Leiden clustering → edge-betweenness
cleanup, returning a JSON cluster map.

Outputs:
  - ``entity_clusters(name, canonical)`` — synonym → canonical mapping
  - ``nodes(node_id, name, entity_type, mention_count)`` — canonical entities
  - ``edges(src, dst, rel_type, weight)`` — coalesced canonical relations

This phase is non-incremental: it ALWAYS rebuilds nodes/edges from
scratch when run, because ER is a global optimization. It is only
*invoked* when entity_embeddings has produced new vectors, so the
no-op case is "skip the rebuild altogether."
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time

log = logging.getLogger(__name__)


_DEFAULT_K = 10
_DEFAULT_DIST_THRESHOLD = 0.15
_DEFAULT_JW_WEIGHT = 0.3
_DEFAULT_BORDERLINE_DELTA = 0.0


def _has_new_entities(conn: sqlite3.Connection) -> bool:
    """True if entity_vec_map has rows whose names are missing from entity_clusters."""
    cluster_count = int(conn.execute("SELECT count(*) FROM entity_clusters").fetchone()[0])
    name_count = int(conn.execute("SELECT count(*) FROM entity_vec_map").fetchone()[0])
    return cluster_count < name_count


def sync_entity_clusters(conn: sqlite3.Connection) -> tuple[int, int]:
    """Run muninn_extract_er and rebuild nodes/edges.

    Returns ``(num_nodes, num_edges)``.
    """
    if not _has_new_entities(conn):
        log.info("  entity-resolution: clusters already up to date")
        return (
            int(conn.execute("SELECT count(*) FROM nodes").fetchone()[0]),
            int(conn.execute("SELECT count(*) FROM edges").fetchone()[0]),
        )

    t0 = time.monotonic()

    # Drop the rebuildable tables (entity_clusters / nodes / edges /
    # _match_edges). entity_vec_map and entities_vec are upstream and
    # preserved so re-running the ER doesn't force a full re-embed.
    conn.execute("DROP TABLE IF EXISTS _match_edges")
    conn.execute("DELETE FROM entity_clusters")
    conn.execute("DELETE FROM nodes")
    conn.execute("DELETE FROM edges")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('nodes', 'edge')")

    # Bridge schema: muninn_extract_er expects a ``temp.entities`` view-like
    # table with (entity_id, name, source) columns. Build it from
    # entity_vec_map joined to the dominant entity_type per name.
    conn.execute("DROP TABLE IF EXISTS temp.entities")
    conn.execute("CREATE TEMP TABLE entities(entity_id TEXT, name TEXT, source TEXT)")
    conn.execute(
        """
        INSERT INTO temp.entities(entity_id, name, source)
        SELECT m.name, m.name, COALESCE(t.entity_type, '')
        FROM entity_vec_map m
        LEFT JOIN (
            SELECT name, entity_type
            FROM main.entities
            GROUP BY name
        ) t ON t.name = m.name
        """
    )

    log.info(
        "  entity-resolution: muninn_extract_er(k=%d, dist=%.2f, jw=%.2f)",
        _DEFAULT_K,
        _DEFAULT_DIST_THRESHOLD,
        _DEFAULT_JW_WEIGHT,
    )
    result_row = conn.execute(
        "SELECT muninn_extract_er(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "entities_vec",
            "name",
            _DEFAULT_K,
            _DEFAULT_DIST_THRESHOLD,
            _DEFAULT_JW_WEIGHT,
            _DEFAULT_BORDERLINE_DELTA,
            None,
            None,
            "diff_type",
        ),
    ).fetchone()
    if result_row is None or result_row[0] is None:
        raise RuntimeError("muninn_extract_er returned NULL")

    conn.execute("DROP TABLE IF EXISTS temp.entities")

    parsed = json.loads(result_row[0])
    clusters: dict[str, int] = parsed.get("clusters", {})
    if not clusters:
        log.warning("  entity-resolution: muninn_extract_er produced 0 clusters")

    # Group cluster members and pick the highest-mention name as canonical.
    name_to_count: dict[str, int] = {
        str(r[0]): int(r[1])
        for r in conn.execute(
            "SELECT name, count(*) FROM entities GROUP BY name"
        ).fetchall()
    }
    name_to_type: dict[str, str | None] = {
        str(r[0]): (r[1] if r[1] else None)
        for r in conn.execute(
            "SELECT name, entity_type FROM entities GROUP BY name"
        ).fetchall()
    }

    members_by_cluster: dict[int, list[str]] = {}
    for name, cluster_id in clusters.items():
        members_by_cluster.setdefault(int(cluster_id), []).append(str(name))

    name_to_canonical: dict[str, str] = {}
    for members in members_by_cluster.values():
        canonical = max(members, key=lambda n: name_to_count.get(n, 0))
        for member in members:
            name_to_canonical[member] = canonical
    # Singletons: any entity name not in the cluster map maps to itself.
    for name in name_to_count:
        name_to_canonical.setdefault(name, name)

    log.info(
        "  entity-resolution: %d entities → %d clusters",
        len(name_to_canonical),
        len(members_by_cluster) or len(name_to_canonical),
    )

    conn.executemany(
        "INSERT INTO entity_clusters (name, canonical) VALUES (?, ?)",
        list(name_to_canonical.items()),
    )

    # Build nodes from canonical roll-up.
    canonical_stats: dict[str, dict[str, str | int | None]] = {}
    for name, count in name_to_count.items():
        canonical = name_to_canonical[name]
        slot_default: dict[str, str | int | None] = {
            "entity_type": name_to_type.get(canonical) or name_to_type.get(name),
            "mention_count": 0,
        }
        slot = canonical_stats.setdefault(canonical, slot_default)
        slot["mention_count"] = int(slot.get("mention_count", 0) or 0) + count

    for canonical in sorted(canonical_stats):
        stats = canonical_stats[canonical]
        conn.execute(
            "INSERT OR IGNORE INTO nodes (name, entity_type, mention_count) "
            "VALUES (?, ?, ?)",
            (canonical, stats.get("entity_type"), stats.get("mention_count", 0)),
        )
    num_nodes = int(conn.execute("SELECT count(*) FROM nodes").fetchone()[0])
    log.info("  entity-resolution: %d canonical nodes", num_nodes)

    # Coalesce relations into edges keyed on canonical names.
    edge_agg: dict[tuple[str, str, str], float] = {}
    for src, dst, rel_type, weight in conn.execute(
        "SELECT src, dst, rel_type, weight FROM relations"
    ).fetchall():
        c_src = name_to_canonical.get(str(src), str(src))
        c_dst = name_to_canonical.get(str(dst), str(dst))
        if c_src == c_dst:
            continue
        key = (c_src, c_dst, str(rel_type or ""))
        edge_agg[key] = edge_agg.get(key, 0.0) + float(weight or 0.0)

    if edge_agg:
        conn.executemany(
            "INSERT OR IGNORE INTO edges (src, dst, rel_type, weight) VALUES (?, ?, ?, ?)",
            [(s, d, rt, w) for (s, d, rt), w in edge_agg.items()],
        )
    num_edges = int(conn.execute("SELECT count(*) FROM edges").fetchone()[0])
    log.info("  entity-resolution: %d coalesced edges", num_edges)

    conn.commit()
    log.info(
        "  entity-resolution: complete in %.1f s",
        time.monotonic() - t0,
    )
    return num_nodes, num_edges
