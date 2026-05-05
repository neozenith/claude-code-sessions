"""Entity-embeddings phase — embed unique entity names into HNSW.

Uses ``muninn_embed()`` with the same NomicEmbed GGUF that
``embeddings.sync_embeddings()`` uses for chunks. The HNSW virtual table
``entities_vec`` is created here at runtime (it requires the
``sqlite-muninn`` extension to be loaded first, so it can't live in the
static ``SCHEMA_SQL``).

Incremental: only entity names not yet present in ``entity_vec_map`` are
embedded. Re-running with no new entities is a no-op.
"""

from __future__ import annotations

import logging
import sqlite3
import time

from claude_code_sessions.database.sqlite.embeddings import (
    GGUF_EMBEDDING_DIM,
    GGUF_MODEL_NAME,
)

log = logging.getLogger(__name__)


def _ensure_entities_vec(conn: sqlite3.Connection) -> None:
    """Create the HNSW virtual table for entity embeddings if missing."""
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS entities_vec USING hnsw_index("
        f"  dimensions={GGUF_EMBEDDING_DIM}, metric='cosine', m=16, ef_construction=200"
        f")"
    )


def sync_entity_embeddings(conn: sqlite3.Connection) -> int:
    """Embed every entity name not already in ``entity_vec_map``.

    Returns the count of newly inserted vectors.
    """
    _ensure_entities_vec(conn)

    new_names = [
        str(r[0])
        for r in conn.execute(
            """
            SELECT DISTINCT name FROM entities
            WHERE name NOT IN (SELECT name FROM entity_vec_map)
            ORDER BY name
            """
        ).fetchall()
    ]
    if not new_names:
        log.info("  entity-embeddings: all %d entity names already embedded", _name_count(conn))
        return 0

    log.info("  entity-embeddings: embedding %d new entity names", len(new_names))
    t0 = time.monotonic()

    max_rowid_row = conn.execute("SELECT COALESCE(MAX(rowid), 0) FROM entity_vec_map").fetchone()
    max_rowid = int(max_rowid_row[0]) if max_rowid_row else 0
    inserted = 0

    for offset, name in enumerate(new_names, start=1):
        rowid = max_rowid + offset
        vec_row = conn.execute("SELECT muninn_embed(?, ?)", (GGUF_MODEL_NAME, name)).fetchone()
        if vec_row is None or vec_row[0] is None:
            raise RuntimeError(f"muninn_embed returned NULL for entity name {name!r}")
        conn.execute(
            "INSERT INTO entities_vec (rowid, vector) VALUES (?, ?)",
            (rowid, vec_row[0]),
        )
        conn.execute(
            "INSERT INTO entity_vec_map (rowid, name) VALUES (?, ?)",
            (rowid, name),
        )
        inserted += 1
        if offset % 200 == 0:
            conn.commit()

    conn.commit()
    log.info(
        "  entity-embeddings: inserted %d vectors in %.1f s (total %d)",
        inserted,
        time.monotonic() - t0,
        _name_count(conn),
    )
    return inserted


def _name_count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT count(*) FROM entity_vec_map").fetchone()[0])
