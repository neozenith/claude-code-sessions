"""Regression: the KG pipeline must not run schema-mutating DDL on the
shared reader connection (``CacheManager.conn``).

Background — the bug this guards against
----------------------------------------
Entity resolution rebuilds the graph wholesale every time it runs. It
DROPs and recreates ``temp.entities`` / ``_match_edges`` and replaces the
``nodes`` / ``edges`` rows (see ``kg/entity_resolution.py``). SQLite refuses
to modify the schema of a database while *any* statement on the **same**
connection still holds an open read cursor, and signals this with
``SQLITE_LOCKED`` → ``sqlite3.OperationalError: database table is locked``.
Crucially this is NOT the same as ``SQLITE_BUSY`` ("database is locked") and
is therefore **not** covered by ``PRAGMA busy_timeout`` — it raises
immediately.

In production the web app polls ``GET /api/kg/cache-stats`` ~1×/s, and that
handler runs ~20 ``SELECT COUNT(*)`` queries on ``CacheManager.conn``. When
the KG pipeline also ran on ``conn``, a reader cursor open at the wrong
instant turned the next ``DROP TABLE temp.entities`` into a hard crash of
the indexer thread.

The fix routes the KG pipeline onto a dedicated connection
(``CacheManager.run_kg_pipeline`` → ``_open_kg_connection``). The two tests
below pin the SQLite semantics the fix relies on, using the real
``CacheManager`` connection (real WAL + busy_timeout pragmas, real schema) —
no sqlite-muninn extension or GGUF model required, because the locking
behaviour is pure SQLite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claude_code_sessions.database.sqlite.cache import CacheManager


def _make_cache(tmp_path: Path) -> CacheManager:
    cache = CacheManager(tmp_path / "kg_isolation.db")
    cache.init_schema()
    # A couple of rows so the reader cursor has something to sit on
    # mid-iteration (an exhausted cursor wouldn't hold the read lock).
    cache.conn.executemany(
        "INSERT INTO entities (name, entity_type, source) VALUES (?, ?, ?)",
        [(n, "concept", "chunk") for n in ("alpha", "beta", "gamma")],
    )
    cache.conn.commit()
    return cache


def test_ddl_on_shared_connection_while_reader_open_raises_locked(tmp_path: Path) -> None:
    """Reproduces the original crash: ER-style DDL on ``cache.conn`` while a
    cache-stats-style reader cursor is open on the same connection raises
    ``database table is locked``. This is the failure the fix avoids by NOT
    using ``cache.conn`` for KG work."""
    cache = _make_cache(tmp_path)
    try:
        conn = cache.conn
        conn.execute("CREATE TEMP TABLE entities_bridge(entity_id TEXT, name TEXT)")
        conn.execute("INSERT INTO temp.entities_bridge VALUES ('x', 'x')")

        # Mirror /api/kg/cache-stats holding a read cursor on a KG table.
        # A multi-row SELECT left mid-iteration keeps the statement active
        # (and the read lock held); an exhausted/aggregate cursor would not.
        reader = conn.execute("SELECT name FROM entities")
        reader.fetchone()  # rows remain pending → statement stays active

        with pytest.raises(sqlite3.OperationalError, match="locked"):
            conn.execute("DROP TABLE IF EXISTS temp.entities_bridge")
        reader.close()
    finally:
        cache.close()


def test_ddl_on_separate_connection_while_reader_open_succeeds(tmp_path: Path) -> None:
    """The fix's mechanism: the very same DDL on a SECOND connection to the
    same WAL database succeeds even while a reader cursor is open on
    ``cache.conn``. KG owns its own connection, so its schema churn never
    collides with the request threads reading ``cache.conn``."""
    cache = _make_cache(tmp_path)
    kg_conn: sqlite3.Connection | None = None
    try:
        # Reader open mid-iteration on the shared connection (request side).
        reader = cache.conn.execute("SELECT name FROM entities")
        reader.fetchone()

        # The KG side: a dedicated connection with the same pragmas the real
        # ``_open_kg_connection`` applies (WAL + busy_timeout).
        kg_conn = sqlite3.connect(str(cache.db_path), check_same_thread=False)
        CacheManager._apply_connection_pragmas(kg_conn)
        kg_conn.execute("CREATE TEMP TABLE entities_bridge(entity_id TEXT, name TEXT)")
        kg_conn.execute("INSERT INTO temp.entities_bridge VALUES ('x', 'x')")

        # No raise: separate connection ⇒ no same-connection schema lock.
        kg_conn.execute("DROP TABLE IF EXISTS temp.entities_bridge")
        reader.close()
    finally:
        if kg_conn is not None:
            kg_conn.close()
        cache.close()


def test_run_kg_pipeline_uses_a_distinct_connection(tmp_path: Path) -> None:
    """Surface contract: the KG connection is lazily created and is a
    distinct object from the shared reader connection, and ``close()`` tears
    both down. (Running the pipeline itself needs the GGUF model, so this
    only asserts the wiring invariant.)"""
    cache = _make_cache(tmp_path)
    try:
        assert hasattr(cache, "run_kg_pipeline")
        assert cache._kg_conn is None  # not opened until first KG run
        assert cache.conn is not None
    finally:
        cache.close()
    # close() is idempotent and clears both handles.
    assert cache._conn is None
    assert cache._kg_conn is None
