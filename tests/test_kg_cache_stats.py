"""Tests for SQLiteDatabase.get_kg_cache_stats() — the KG Cache page backend.

Builds a real SQLite cache in a tmp dir and inserts rows directly (no
ingest pipeline, no model downloads) so every pipeline stage's done/
eligible/pending math is deterministic. Crucially this also exercises the
``chunks_vec_nodes`` guard: that sqlite-muninn shadow table is created at
runtime by the embedding phase, so on a cache that never embedded it is
ABSENT — the stats query must report 0 embedded rather than raising
``no such table``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from claude_code_sessions.database import SQLiteDatabase
from claude_code_sessions.database.sqlite.kg.payload import KGCacheStats, PipelineStage


def _stage(stats: KGCacheStats, key: str) -> PipelineStage:
    stage = next((s for s in stats.stages if s.key == key), None)
    assert stage is not None, f"missing stage {key!r}"
    return stage


@pytest.fixture
def db(tmp_path: Path) -> SQLiteDatabase:
    """A SQLiteDatabase over a throwaway cache + a projects dir with two
    *.jsonl files on disk (so the ingest stage has a non-zero backlog)."""
    projects = tmp_path / "projects"
    (projects / "p").mkdir(parents=True)
    (projects / "p" / "a.jsonl").write_text("{}\n", encoding="utf-8")
    (projects / "p" / "b.jsonl").write_text("{}\n", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    return SQLiteDatabase(
        local_projects_path=projects,
        home_projects_path=home,
        db_path=tmp_path / "cache.db",
    )


def _seed(conn: sqlite3.Connection) -> None:
    """Populate one row per stage so each backlog is non-trivial."""
    # One source_files row (2 files exist on disk → ingest backlog of 1).
    conn.execute(
        """
        INSERT INTO source_files
            (id, filepath, mtime, size_bytes, line_count, last_ingested_at,
             project_id, session_id, file_type)
        VALUES (1, '/x/a.jsonl', 0, 0, 1, '2026-01-01T00:00:00Z', 'proj', 's1', 'main_session')
        """
    )

    def _event(eid: int, kind: str, content: str | None) -> None:
        conn.execute(
            """
            INSERT INTO events
                (id, event_type, msg_kind, project_id, message_content,
                 source_file_id, line_number, raw_json)
            VALUES (?, 'user', ?, 'proj', ?, 1, ?, '{}')
            """,
            (eid, kind, content, eid),
        )

    # 3 human events with content (chunk-eligible) + 1 assistant (not).
    _event(1, "human", "hello world")
    _event(2, "human", "second prompt")
    _event(3, "human", "third prompt")
    _event(4, "assistant", "a reply")

    # Chunks for events 1 and 2 only → chunk backlog of 1 (event 3).
    conn.execute("INSERT INTO event_message_chunks (chunk_id, event_id, text) VALUES (10, 1, 'c1')")
    conn.execute("INSERT INTO event_message_chunks (chunk_id, event_id, text) VALUES (11, 2, 'c2')")

    # NER processed one chunk; RE processed none.
    conn.execute(
        "INSERT INTO ner_chunks_log (chunk_id, processed_at) VALUES (10, '2026-01-01T00:00:00Z')"
    )

    # Two distinct entity names; one embedded into entity_vec_map.
    conn.execute("INSERT INTO entities (name, source, chunk_id) VALUES ('Foo', 'ner', 10)")
    conn.execute("INSERT INTO entities (name, source, chunk_id) VALUES ('Bar', 'ner', 11)")
    conn.execute("INSERT INTO entity_vec_map (rowid, name) VALUES (1, 'Foo')")

    # Resolved graph: one node + one edge + one relation. No clusters yet.
    conn.execute("INSERT INTO nodes (name, mention_count) VALUES ('Foo', 1)")
    conn.execute("INSERT INTO edges (src, dst, rel_type, weight) VALUES ('Foo', 'Bar', 'rel', 1.0)")
    conn.execute("INSERT INTO relations (src, dst, source) VALUES ('Foo', 'Bar', 'ner')")
    conn.commit()


def test_headline_totals(db: SQLiteDatabase) -> None:
    _seed(db.cache.conn)
    stats = db.get_kg_cache_stats()

    assert stats.files_on_disk == 2
    assert stats.source_files == 1
    assert stats.events_total == 4
    assert stats.chunks_total == 2
    assert stats.entities_total == 2
    assert stats.unique_entities == 2
    assert stats.relations_total == 1
    assert stats.nodes_total == 1
    assert stats.edges_total == 1
    assert stats.communities_total == 0


def test_stage_backlogs(db: SQLiteDatabase) -> None:
    _seed(db.cache.conn)
    stats = db.get_kg_cache_stats()

    ingest = _stage(stats, "ingest")
    assert (ingest.eligible, ingest.done, ingest.pending) == (2, 1, 1)

    chunk = _stage(stats, "chunk")
    assert (chunk.eligible, chunk.done, chunk.pending) == (3, 2, 1)

    ner = _stage(stats, "ner")
    assert (ner.eligible, ner.done, ner.pending) == (2, 1, 1)

    re = _stage(stats, "re")
    assert (re.eligible, re.done, re.pending) == (2, 0, 2)

    entity_embed = _stage(stats, "entity_embed")
    assert (entity_embed.eligible, entity_embed.done, entity_embed.pending) == (2, 1, 1)

    resolve = _stage(stats, "resolve")
    assert (resolve.eligible, resolve.done) == (1, 0)


def test_embed_stage_tolerates_missing_shadow_table(db: SQLiteDatabase) -> None:
    """chunks_vec_nodes is created at runtime by sqlite-muninn; on a cache
    that never embedded it is absent. The embed stage must then report 0
    done (backlog == all chunks) instead of raising ``no such table``."""
    _seed(db.cache.conn)
    assert not db._table_exists("chunks_vec_nodes")

    stats = db.get_kg_cache_stats()
    embed = _stage(stats, "embed")
    assert (embed.eligible, embed.done, embed.pending) == (2, 0, 2)


def test_communities_counted_per_resolution_not_summed(db: SQLiteDatabase) -> None:
    """Leiden runs at multiple resolutions over the same nodes. The
    community count must reflect ONE resolution (the displayed one), not
    the sum across resolutions — otherwise it multi-counts and looks
    inflated/fake.
    """
    conn = db.cache.conn
    # resolution 0.25 (the default/displayed one): 2 communities.
    conn.execute(
        "INSERT INTO leiden_communities (node, resolution, community_id) VALUES ('A', 0.25, 0)"
    )
    conn.execute(
        "INSERT INTO leiden_communities (node, resolution, community_id) VALUES ('B', 0.25, 1)"
    )
    # resolution 1.0: 3 communities (a node maps to one community per
    # resolution — PK is (node, resolution) — so 3 communities = 3 nodes).
    conn.execute(
        "INSERT INTO leiden_communities (node, resolution, community_id) VALUES ('A', 1.0, 0)"
    )
    conn.execute(
        "INSERT INTO leiden_communities (node, resolution, community_id) VALUES ('B', 1.0, 1)"
    )
    conn.execute(
        "INSERT INTO leiden_communities (node, resolution, community_id) VALUES ('C', 1.0, 2)"
    )
    conn.execute(
        "INSERT INTO community_labels (resolution, community_id, label, member_count, model, generated_at)"
        " VALUES (0.25, 0, 'lbl', 1, 'm', '2026-01-01T00:00:00Z')"
    )
    conn.commit()

    stats = db.get_kg_cache_stats()
    assert stats.display_resolution == 0.25
    # 2 communities at resolution 0.25 — NOT 5 (the sum across resolutions).
    assert stats.communities_total == 2

    naming = _stage(stats, "naming")
    assert (naming.eligible, naming.done) == (2, 1)


def test_empty_cache_is_all_zero_not_error(db: SQLiteDatabase) -> None:
    """A cold cache (schema present, no rows) returns a fully-zero snapshot
    rather than erroring — the page must render on first boot."""
    stats = db.get_kg_cache_stats()
    assert stats.events_total == 0
    for stage in stats.stages:
        assert stage.done == 0
        assert stage.pending == max(0, stage.eligible - stage.done)
        # Only the ingest stage can have eligible > 0 (the two files on disk).
        if stage.key != "ingest":
            assert stage.eligible == 0
            assert stage.percent == 0.0
