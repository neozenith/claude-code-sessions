"""
Tests for the embedding subsystem: chunker + sync + HNSW runtime.

The chunker tests are pure-function tests with no DB. The sync tests
build a tiny in-memory SQLite DB containing a minimal ``events`` table,
run ``sync_chunks()``, and assert on counts / FK behavior / idempotency.

The full HNSW-round-trip test is gated behind the real GGUF model — if
it's already downloaded locally we exercise the whole
download → register → embed pipeline; otherwise we skip. We deliberately
don't trigger the 150 MB download from the test suite.
"""

from __future__ import annotations

import sqlite3

import pytest
import sqlite_muninn

from claude_code_sessions.database.sqlite.embeddings import (
    CHUNKS_SCHEMA_SQL,
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    GGUF_EMBEDDING_DIM,
    MODELS_DIR,
    GGUF_MODEL_FILENAME,
    chunk_text,
    setup_embedding_runtime,
    sync_chunks,
    sync_embeddings,
)


# ---------------------------------------------------------------------------
# Pure chunker tests
# ---------------------------------------------------------------------------


class TestChunkText:
    def test_empty_string_returns_empty_list(self) -> None:
        assert chunk_text("") == []

    def test_short_string_returns_single_chunk_even_below_min(self) -> None:
        # Short inputs bypass min-size filtering — otherwise they'd be
        # silently dropped, which is graceful degradation we want to
        # avoid in the ingest path.
        short = "hi there"
        assert len(short) < CHUNK_MIN_CHARS
        result = chunk_text(short)
        assert result == [(short, 0)]

    def test_single_paragraph_at_min_boundary(self) -> None:
        text = "x" * (CHUNK_MIN_CHARS + 50)
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0][0] == text
        assert chunks[0][1] == 0

    def test_two_paragraphs_fit_in_one_chunk(self) -> None:
        para_a = "a" * 200
        para_b = "b" * 200
        text = f"{para_a}\n\n{para_b}"
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0][0] == text
        assert chunks[0][1] == 0

    def test_oversized_text_produces_multiple_chunks(self) -> None:
        # Enough paragraphs to exceed CHUNK_MAX_CHARS at least twice over.
        para = "p" * (CHUNK_MAX_CHARS // 3)
        text = "\n\n".join([para] * 10)
        chunks = chunk_text(text)
        assert len(chunks) >= 2
        # Every chunk must stay under CHUNK_MAX_CHARS.
        for chunk, _ in chunks:
            assert len(chunk) <= CHUNK_MAX_CHARS

    def test_tiny_trailing_paragraph_merges_into_previous(self) -> None:
        big = "B" * CHUNK_MIN_CHARS * 2
        tiny = "tail"  # below CHUNK_MIN_CHARS
        text = f"{big}\n\n{tiny}"
        chunks = chunk_text(text)
        # Trailing tiny chunk should be absorbed into the last emitted one.
        assert len(chunks) == 1
        assert tiny in chunks[0][0]

    def test_char_offset_preserves_original_position(self) -> None:
        # Confirm chunk_offset maps back into the source string.
        para_a = "a" * 500
        para_b = "b" * 500
        para_c = "c" * 500
        text = f"{para_a}\n\n{para_b}\n\n{para_c}"
        chunks = chunk_text(text)
        for chunk, offset in chunks:
            # The chunk's first real content should line up with the
            # source at ``offset`` — we check only the first character
            # because paragraph stripping can reflow whitespace.
            assert text[offset : offset + 1] == chunk[0]


# ---------------------------------------------------------------------------
# Sync integration — in-memory DB with a minimal events table
# ---------------------------------------------------------------------------


def _minimal_events_schema(conn: sqlite3.Connection) -> None:
    """Create just enough of the events schema for the chunker to query.

    The real schema in ``schema.py`` has dozens of columns we don't need.
    We replicate only the columns sync_chunks reads.
    """
    conn.executescript(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_kind TEXT,
            message_content TEXT
        );
        """
    )
    conn.executescript(CHUNKS_SCHEMA_SQL)


@pytest.fixture
def in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _minimal_events_schema(conn)
    return conn


class TestSyncChunks:
    def test_empty_events_is_noop(self, in_memory_db: sqlite3.Connection) -> None:
        assert sync_chunks(in_memory_db) == 0

    def test_human_message_gets_chunked(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO events (msg_kind, message_content) VALUES (?, ?)",
            ("human", "x" * (CHUNK_MIN_CHARS + 100)),
        )
        in_memory_db.commit()

        added = sync_chunks(in_memory_db)
        assert added >= 1
        row_count = in_memory_db.execute(
            "SELECT COUNT(*) FROM event_message_chunks"
        ).fetchone()[0]
        assert row_count == added

    def test_non_human_kinds_are_skipped(self, in_memory_db: sqlite3.Connection) -> None:
        # assistant_text / tool_use / etc. are NOT embedded — keeps the
        # vector index focused on user prompts.
        for kind in ("assistant_text", "tool_use", "tool_result", "thinking"):
            in_memory_db.execute(
                "INSERT INTO events (msg_kind, message_content) VALUES (?, ?)",
                (kind, "content " * 200),
            )
        in_memory_db.commit()

        assert sync_chunks(in_memory_db) == 0
        assert in_memory_db.execute(
            "SELECT COUNT(*) FROM event_message_chunks"
        ).fetchone()[0] == 0

    def test_sync_is_idempotent(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO events (msg_kind, message_content) VALUES (?, ?)",
            ("human", "x" * 300),
        )
        in_memory_db.commit()

        first = sync_chunks(in_memory_db)
        second = sync_chunks(in_memory_db)
        assert first > 0
        # Second run finds nothing new to chunk.
        assert second == 0

    def test_deleting_event_cascades_chunks(self, in_memory_db: sqlite3.Connection) -> None:
        in_memory_db.execute(
            "INSERT INTO events (msg_kind, message_content) VALUES (?, ?)",
            ("human", "x" * 400),
        )
        in_memory_db.commit()
        sync_chunks(in_memory_db)
        assert in_memory_db.execute(
            "SELECT COUNT(*) FROM event_message_chunks"
        ).fetchone()[0] > 0

        in_memory_db.execute("DELETE FROM events WHERE id = 1")
        in_memory_db.commit()
        # FK CASCADE should wipe the dependent chunks automatically.
        assert in_memory_db.execute(
            "SELECT COUNT(*) FROM event_message_chunks"
        ).fetchone()[0] == 0

    def test_empty_and_whitespace_content_is_skipped(
        self, in_memory_db: sqlite3.Connection
    ) -> None:
        in_memory_db.executemany(
            "INSERT INTO events (msg_kind, message_content) VALUES (?, ?)",
            [
                ("human", ""),
                ("human", None),
            ],
        )
        in_memory_db.commit()
        assert sync_chunks(in_memory_db) == 0


# ---------------------------------------------------------------------------
# HNSW runtime — gated on the real GGUF being present. We never trigger
# a download from tests; if the user has it cached we exercise the full
# round-trip, otherwise we skip cleanly.
# ---------------------------------------------------------------------------


GGUF_PATH = MODELS_DIR / GGUF_MODEL_FILENAME
GGUF_PRESENT = GGUF_PATH.exists()


@pytest.mark.skipif(
    not GGUF_PRESENT,
    reason="GGUF model not downloaded locally; skipping end-to-end embedding test",
)
class TestSyncEmbeddings:
    """End-to-end test that actually embeds a tiny corpus.

    Only runs if the GGUF is already on disk at ``MODELS_DIR`` — we
    never initiate the 150 MB download from the test suite.
    """

    def test_setup_and_embed_roundtrip(self, in_memory_db: sqlite3.Connection) -> None:
        # Seed one human event long enough to produce a chunk.
        in_memory_db.execute(
            "INSERT INTO events (msg_kind, message_content) VALUES (?, ?)",
            ("human", "The quick brown fox jumps over the lazy dog. " * 20),
        )
        in_memory_db.commit()

        sync_chunks(in_memory_db)
        chunk_count = in_memory_db.execute(
            "SELECT COUNT(*) FROM event_message_chunks"
        ).fetchone()[0]
        assert chunk_count >= 1

        setup_embedding_runtime(in_memory_db, GGUF_PATH)
        embedded = sync_embeddings(in_memory_db)
        assert embedded == chunk_count

        # Shadow table should now have one row per chunk.
        nodes = in_memory_db.execute("SELECT COUNT(*) FROM chunks_vec_nodes").fetchone()[0]
        assert nodes == chunk_count


# ---------------------------------------------------------------------------
# Muninn smoke test — no model needed, just the extension
# ---------------------------------------------------------------------------


class TestMuninnExtension:
    def test_extension_loads(self) -> None:
        """Sanity check that the compiled extension loads. Catches packaging
        regressions where the wheel's dylib doesn't match the runtime."""
        conn = sqlite3.connect(":memory:")
        conn.enable_load_extension(True)
        sqlite_muninn.load(conn)
        conn.execute(
            f"CREATE VIRTUAL TABLE v USING hnsw_index(dimensions={GGUF_EMBEDDING_DIM}, metric='cosine')"
        )
        # Shadow tables must exist after the VT is created — this is the
        # invariant sync_embeddings relies on for staleness detection.
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE 'v%'"
            )
        }
        assert "v" in tables
        assert "v_nodes" in tables
