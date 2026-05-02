"""Community-detection phase — Leiden communities at multiple resolutions.

Uses sqlite-muninn's ``graph_leiden`` virtual-table module. The community
membership is queried via SELECT against ``graph_leiden`` with the edge
table parameters embedded as WHERE-clause column filters (this is the
sqlite-muninn convention for table-valued functions).

The graph is built off the canonical ``edges`` table. Multi-resolution
output gives the cytoscape page coarse / medium / fine views with one
SQL pass per resolution.
"""

from __future__ import annotations

import logging
import sqlite3
import time

from claude_code_sessions.database.sqlite.kg.runtime import LEIDEN_RESOLUTIONS

log = logging.getLogger(__name__)


def sync_communities(conn: sqlite3.Connection) -> int:
    """Recompute Leiden communities at every configured resolution.

    Returns total assignment rows written across all resolutions.
    """
    edge_count = int(conn.execute("SELECT count(*) FROM edges").fetchone()[0])
    if edge_count == 0:
        log.info("  communities: edges table empty — nothing to cluster")
        conn.execute("DELETE FROM leiden_communities")
        conn.commit()
        return 0

    have_resolutions = {
        float(r[0])
        for r in conn.execute(
            "SELECT DISTINCT resolution FROM leiden_communities"
        ).fetchall()
    }
    expected_resolutions = set(LEIDEN_RESOLUTIONS)
    nodes_now = int(conn.execute("SELECT count(*) FROM nodes").fetchone()[0])

    # If every resolution is already populated AND the graph hasn't changed
    # (membership row count == node count × resolution count), skip.
    if have_resolutions >= expected_resolutions:
        existing_total = int(
            conn.execute("SELECT count(*) FROM leiden_communities").fetchone()[0]
        )
        if existing_total >= nodes_now * len(LEIDEN_RESOLUTIONS):
            log.info(
                "  communities: %d resolutions already current — skip",
                len(have_resolutions),
            )
            return 0

    conn.execute("DELETE FROM leiden_communities")
    t0 = time.monotonic()
    total = 0
    for resolution in LEIDEN_RESOLUTIONS:
        rows = conn.execute(
            """
            SELECT node, community_id, modularity
            FROM graph_leiden
            WHERE edge_table = 'edges'
              AND src_col = 'src'
              AND dst_col = 'dst'
              AND direction = 'both'
              AND resolution = ?
            """,
            (resolution,),
        ).fetchall()

        if not rows:
            log.warning("  communities: resolution=%.2f produced 0 rows", resolution)
            continue

        n_communities = len({int(r[1]) for r in rows})
        modularity = float(rows[0][2]) if rows[0][2] is not None else 0.0
        conn.executemany(
            "INSERT INTO leiden_communities (node, resolution, community_id, modularity) "
            "VALUES (?, ?, ?, ?)",
            [(str(r[0]), float(resolution), int(r[1]), float(r[2] or 0.0)) for r in rows],
        )
        total += len(rows)
        log.info(
            "  communities: resolution=%.2f — %d nodes → %d communities (Q=%.4f)",
            resolution,
            len(rows),
            n_communities,
            modularity,
        )

    conn.commit()
    log.info(
        "  communities: %d total assignments across %d resolutions in %.1f s",
        total,
        len(LEIDEN_RESOLUTIONS),
        time.monotonic() - t0,
    )
    return total
