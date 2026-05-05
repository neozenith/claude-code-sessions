"""
Embedding sync: chunker, GGUF model downloader, HNSW vector builder.

This module owns the entire embedding lifecycle:

1. **Model management** — downloads the NomicEmbed GGUF file to
   ``~/.claude/cache/models/`` on first use (cached across runs).
2. **Chunking** — splits ``events.message_content`` into paragraph-based
   chunks sized to fit the model's context window. Stored in
   ``event_message_chunks``. The FK ``event_id → events.id`` with
   ``ON DELETE CASCADE`` handles cleanup when events are re-ingested.
3. **Embedding** — invokes ``muninn_embed()`` via SQL and inserts the
   resulting vector bytes into the ``chunks_vec`` HNSW virtual table.
   The shadow table ``chunks_vec_nodes`` is the source of truth for
   "which chunk_ids have been embedded" — we never scan the virtual
   table directly.

Both the chunks and embeddings phases are **incremental**: they only
process rows that don't yet have downstream artifacts. Re-running is a
no-op when nothing has changed.

The ``sqlite-muninn`` extension must be loaded on the connection before
``sync_embeddings`` is called. ``sqlite_muninn.load(conn)`` does this in
one line — we call it lazily so that callers that never embed (e.g. a
fresh install that hasn't downloaded the GGUF yet) don't pay the cost.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import urllib.request
from pathlib import Path

import sqlite_muninn

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — sized for NomicEmbed v1.5 Q8_0 quantised GGUF
# ---------------------------------------------------------------------------

# Registration name used inside ``temp.muninn_models`` — arbitrary but
# must match between ``setup_embedding_runtime()`` and ``sync_embeddings()``.
GGUF_MODEL_NAME = "NomicEmbed"

# HuggingFace-hosted GGUF file. Downloading via plain urllib keeps us off
# the huggingface_hub dependency chain.
GGUF_MODEL_FILENAME = "nomic-embed-text-v1.5.Q8_0.gguf"
GGUF_MODEL_URL = (
    "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/" + GGUF_MODEL_FILENAME
)

# Output vector dimensionality for NomicEmbed v1.5 — matches the HNSW
# ``dimensions=`` virtual-table parameter. Changing this requires a
# different model and a cache rebuild.
GGUF_EMBEDDING_DIM = 768

# Local cache of downloaded models. Shared across all tools that use the
# same SQLite cache (the main app + the introspect skill script).
MODELS_DIR = Path.home() / ".claude" / "cache" / "models"

# Chunk sizing — empirical from the sessions_demo reference. Code-heavy
# content averages ~3.1 chars/token, so 1200 chars ≈ 400 tokens per
# chunk, safely under the 2048-token model context. Chunks below
# CHUNK_MIN_CHARS are absorbed into an adjacent chunk rather than emitted
# as noise.
CHUNK_MAX_CHARS = 1200
CHUNK_MIN_CHARS = 100

# Hard ceiling on text passed to ``muninn_embed()`` — guards against
# oversized chunks (shouldn't happen given CHUNK_MAX_CHARS, but the
# stored chunk text is unconstrained). Truncation is at the front; we
# keep the beginning as the highest-signal content for embeddings.
EMBED_MAX_CHARS = 1500

# Only user-typed prompts are embedded for now. Keeps the index small
# and the semantic search focused on "what the user asked about" rather
# than assistant output or tool results.
EMBEDDED_MSG_KINDS: tuple[str, ...] = ("human",)


# ---------------------------------------------------------------------------
# Schema fragment — tables created at schema init time. The HNSW virtual
# table is NOT here because it requires sqlite_muninn.load() first; it's
# created lazily at runtime.
# ---------------------------------------------------------------------------

CHUNKS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS event_message_chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    chunk_offset INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_event_id
    ON event_message_chunks(event_id);

CREATE VIRTUAL TABLE IF NOT EXISTS event_message_chunks_fts
    USING fts5(text, content=event_message_chunks, content_rowid=chunk_id);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON event_message_chunks BEGIN
    INSERT INTO event_message_chunks_fts(rowid, text)
        VALUES (new.chunk_id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON event_message_chunks BEGIN
    INSERT INTO event_message_chunks_fts(event_message_chunks_fts, rowid, text)
        VALUES('delete', old.chunk_id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON event_message_chunks BEGIN
    INSERT INTO event_message_chunks_fts(event_message_chunks_fts, rowid, text)
        VALUES('delete', old.chunk_id, old.text);
    INSERT INTO event_message_chunks_fts(rowid, text)
        VALUES (new.chunk_id, new.text);
END;
"""


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------


def ensure_model_downloaded(*, force: bool = False) -> Path:
    """Return the local path to the GGUF model, downloading on first use.

    The model is ~150 MB (Q8_0 quant); download runs once per machine.
    Subsequent calls are a file-existence check. ``force=True`` re-downloads.

    Raises ``URLError`` / ``HTTPError`` on network failure — fail loud,
    since without the model the embedding phase cannot run.
    """
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / GGUF_MODEL_FILENAME
    if target.exists() and not force:
        log.info(
            "  GGUF model already present: %s (%.1f MiB)",
            target,
            target.stat().st_size / (1024 * 1024),
        )
        return target

    log.info("  downloading GGUF model %s → %s", GGUF_MODEL_URL, target)
    # User-Agent required: HuggingFace rejects Python's default "Python-urllib/X".
    req = urllib.request.Request(
        GGUF_MODEL_URL,
        headers={"User-Agent": "claude-code-sessions/1.0"},
    )
    t0 = time.monotonic()
    # Write to a .partial file then rename — an interrupted download
    # leaves a stub that won't be mistaken for a completed model.
    partial = target.with_suffix(target.suffix + ".partial")
    with urllib.request.urlopen(req) as resp, partial.open("wb") as out:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        last_log = t0
        chunk_bytes = 1024 * 1024  # 1 MiB read unit
        while True:
            chunk = resp.read(chunk_bytes)
            if not chunk:
                break
            out.write(chunk)
            downloaded += len(chunk)
            now = time.monotonic()
            if now - last_log >= 5.0:
                pct = f"{100 * downloaded / total:.1f}%" if total else "?%"
                rate_mb_s = (downloaded / (now - t0)) / (1024 * 1024) if now > t0 else 0
                log.info(
                    "  downloaded %.1f MiB / %.1f MiB (%s, %.1f MiB/s)",
                    downloaded / (1024 * 1024),
                    total / (1024 * 1024) if total else 0,
                    pct,
                    rate_mb_s,
                )
                last_log = now
    partial.rename(target)
    log.info(
        "Downloaded GGUF model (%.1f MiB in %.1f s)",
        target.stat().st_size / (1024 * 1024),
        time.monotonic() - t0,
    )
    return target


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


def chunk_text(text: str) -> list[tuple[str, int]]:
    """Split ``text`` into paragraph-based chunks of (chunk_text, char_offset).

    Algorithm (mirrors sessions_demo.phases.chunks._split_into_chunks):
      1. Split on double-newline paragraphs.
      2. Greedy-pack paragraphs into a running chunk until adding the next
         one would exceed ``CHUNK_MAX_CHARS`` — emit then, start fresh.
      3. Chunks below ``CHUNK_MIN_CHARS`` are absorbed into the preceding
         chunk rather than emitted standalone.
      4. Very short texts (below ``CHUNK_MIN_CHARS`` total) become a single
         chunk rather than being dropped.

    ``char_offset`` is the start position of the chunk in the original
    text — useful if we later want to highlight the exact matched region.
    """
    if not text:
        return []
    if len(text) < CHUNK_MIN_CHARS:
        return [(text, 0)]

    chunks: list[tuple[str, int]] = []
    paragraphs = text.split("\n\n")

    offset = 0
    current_chunk = ""
    current_offset = 0

    for i, raw_para in enumerate(paragraphs):
        para = raw_para.strip()
        if not para:
            # Preserve the \n\n separator in the running offset so later
            # chunks' char_offset still maps into the original string.
            offset += 2
            continue

        if not current_chunk:
            current_chunk = para
            current_offset = offset
        elif len(current_chunk) + len(para) + 2 <= CHUNK_MAX_CHARS:
            current_chunk += "\n\n" + para
        else:
            if len(current_chunk) >= CHUNK_MIN_CHARS:
                chunks.append((current_chunk, current_offset))
            current_chunk = para
            current_offset = offset

        offset += len(para) + (2 if i < len(paragraphs) - 1 else 0)

    if current_chunk:
        if len(current_chunk) >= CHUNK_MIN_CHARS or not chunks:
            chunks.append((current_chunk, current_offset))
        else:
            # Tail chunk is too short — merge into the previous one.
            prev_text, prev_offset = chunks[-1]
            chunks[-1] = (prev_text + "\n\n" + current_chunk, prev_offset)

    return chunks


# ---------------------------------------------------------------------------
# Sync — runs at the tail of CacheManager.update()
# ---------------------------------------------------------------------------


def sync_chunks(conn: sqlite3.Connection) -> int:
    """Chunk any human-message events that don't yet have chunks.

    Returns the number of chunks inserted this run. Safe to call
    repeatedly — it only processes events that aren't already covered.

    We scope to ``msg_kind = 'human'`` for now (see ``EMBEDDED_MSG_KINDS``):
    that's the most useful signal for semantic search and keeps the
    index size modest.
    """
    kinds_placeholders = ",".join("?" * len(EMBEDDED_MSG_KINDS))
    # Count first so we can log an estimate. This is the same query as
    # the fetch below, just with COUNT(*). Cheap — it's an indexed scan.
    total = conn.execute(
        f"""
        SELECT COUNT(*) FROM events e
        WHERE e.message_content IS NOT NULL
          AND e.message_content != ''
          AND e.msg_kind IN ({kinds_placeholders})
          AND e.id NOT IN (SELECT DISTINCT event_id FROM event_message_chunks)
        """,
        EMBEDDED_MSG_KINDS,
    ).fetchone()[0]
    if total == 0:
        return 0

    log.info("  chunking %d events (kinds=%s)", total, ",".join(EMBEDDED_MSG_KINDS))
    t0 = time.monotonic()

    cursor = conn.execute(
        f"""
        SELECT e.id, e.message_content
        FROM events e
        WHERE e.message_content IS NOT NULL
          AND e.message_content != ''
          AND e.msg_kind IN ({kinds_placeholders})
          AND e.id NOT IN (SELECT DISTINCT event_id FROM event_message_chunks)
        """,
        EMBEDDED_MSG_KINDS,
    )

    total_chunks = 0
    events_processed = 0
    for row in cursor:
        event_id = row[0]
        text = row[1]
        for chunk, chunk_offset in chunk_text(text):
            conn.execute(
                "INSERT INTO event_message_chunks (event_id, text, chunk_offset) VALUES (?, ?, ?)",
                (event_id, chunk, chunk_offset),
            )
            total_chunks += 1
        events_processed += 1
        if events_processed % 500 == 0:
            log.info(
                "    chunked %d/%d events (%d chunks so far)",
                events_processed,
                total,
                total_chunks,
            )

    conn.commit()
    log.info(
        "  created %d chunks from %d events (%.1f s)",
        total_chunks,
        events_processed,
        time.monotonic() - t0,
    )
    return total_chunks


def setup_embedding_runtime(conn: sqlite3.Connection, model_path: Path) -> None:
    """Load muninn, register the GGUF model, and ensure the HNSW VT exists.

    Idempotent: safe to call on every connection open. The expensive
    part (creating the HNSW VT) is a no-op after the first call.
    """
    conn.enable_load_extension(True)
    sqlite_muninn.load(conn)
    conn.enable_load_extension(False)

    # ``temp.muninn_models`` is a per-connection registry. An
    # ``INSERT OR IGNORE`` doesn't work here because the value comes
    # from ``muninn_embed_model()``; we instead check existence first.
    row = conn.execute(
        "SELECT name FROM temp.muninn_models WHERE name = ?",
        (GGUF_MODEL_NAME,),
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO temp.muninn_models(name, model) SELECT ?, muninn_embed_model(?)",
            (GGUF_MODEL_NAME, str(model_path)),
        )
        log.debug("Registered GGUF model %s → %s", GGUF_MODEL_NAME, model_path)

    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec "
        f"USING hnsw_index(dimensions={GGUF_EMBEDDING_DIM}, metric='cosine')"
    )
    conn.commit()


def sync_embeddings(conn: sqlite3.Connection) -> int:
    """Embed any chunks that don't yet have a vector in ``chunks_vec``.

    Uses ``chunks_vec_nodes`` (the shadow table — a regular SQLite table)
    to detect "not yet embedded" rows. A direct scan of ``chunks_vec``
    (the HNSW virtual table) returns no rows in muninn's implementation,
    so staleness checks MUST go through the shadow table.

    Prerequisite: ``setup_embedding_runtime(conn, model_path)`` must
    have been called on this connection already.

    Returns the number of vectors inserted.
    """
    total = conn.execute(
        """
        SELECT COUNT(*) FROM event_message_chunks c
        WHERE c.chunk_id NOT IN (SELECT id FROM chunks_vec_nodes)
        """,
    ).fetchone()[0]
    if total == 0:
        return 0

    log.info("  embedding %d chunks (dim=%d, model=%s)", total, GGUF_EMBEDDING_DIM, GGUF_MODEL_NAME)
    t0 = time.monotonic()

    cursor = conn.execute(
        """
        SELECT c.chunk_id, c.text
        FROM event_message_chunks c
        WHERE c.chunk_id NOT IN (SELECT id FROM chunks_vec_nodes)
        """,
    )

    total_embedded = 0
    failed = 0
    last_log = t0
    for row in cursor:
        chunk_id, text = row[0], row[1]
        try:
            embed_text = text[:EMBED_MAX_CHARS]
            result = conn.execute(
                "SELECT muninn_embed(?, ?)",
                (GGUF_MODEL_NAME, embed_text),
            ).fetchone()
            if result and result[0]:
                conn.execute(
                    "INSERT INTO chunks_vec(rowid, vector) VALUES (?, ?)",
                    (chunk_id, result[0]),
                )
                total_embedded += 1
        except sqlite3.OperationalError as e:
            # One bad chunk shouldn't abort the whole pass. Log and
            # continue — the next run picks up any rows we skipped.
            log.warning("Failed to embed chunk %d: %s", chunk_id, e)
            failed += 1

        now = time.monotonic()
        if now - last_log >= 30.0:
            elapsed = now - t0
            rate = total_embedded / elapsed if elapsed > 0 else 0
            remaining = total - total_embedded
            eta_s = remaining / rate if rate > 0 else 0
            log.info(
                "    embedded %d/%d chunks (%.1f chunks/s, elapsed %.0f s, eta %.0f s)",
                total_embedded,
                total,
                rate,
                elapsed,
                eta_s,
            )
            last_log = now

    conn.commit()
    log.info(
        "  embedded %d/%d chunks (%d failed, %.1f s)",
        total_embedded,
        total,
        failed,
        time.monotonic() - t0,
    )
    return total_embedded
