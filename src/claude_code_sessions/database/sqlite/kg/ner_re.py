"""NER + RE phase — GLiNER2 (fastino/gliner2-base-v1).

The 205 MB DeBERTa-v3-base GLiNER2 model handles both named-entity
recognition and zero-shot relation extraction. It is roughly 20× faster
than running NER+RE through a 4 B chat model (e.g. Qwen3.5-4B) on CPU
and yields more consistent label boundaries because the network was
trained on token-aligned NER targets rather than free-form generation.

Incremental: tracks completed chunks in ``ner_chunks_log`` and
``re_chunks_log``. Re-runs only process new chunks.

Per ``/escalators-not-stairs``: a chunk that produces zero entities is
still logged as processed — that is success, not failure. A chunk that
errors out propagates the exception; we never silently skip.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

from claude_code_sessions.database.sqlite.kg.gliner2_loader import get_gliner2
from claude_code_sessions.database.sqlite.kg.runtime import NER_LABELS, RE_LABELS

log = logging.getLogger(__name__)

# Outer loop: chunks committed to SQLite per batch. Smaller values mean
# more frequent visibility for the web app at the cost of slightly more
# commit overhead.
_OUTER_BATCH = 8
# Inner GLiNER2 batch size — fits comfortably in CPU memory.
_GLINER2_BATCH = 8

# GLiNER2's DeBERTa-v3-base encoder has a 512 token window (~1500 chars
# for code-dense content at ~3 chars/token). Larger inputs either get
# silently truncated internally or send the relation extractor into an
# N² pair-scoring loop that can take *minutes* per chunk. We truncate
# defensively at the boundary so the chunker's edge cases (rare
# multi-thousand-char single-paragraph prompts) can't stall the
# pipeline. Truncation is at the END — entities near the start of long
# prompts are usually the most informative anyway.
_MAX_TEXT_CHARS = 1500


def _safe_text(text: str) -> str:
    if len(text) <= _MAX_TEXT_CHARS:
        return text
    return text[:_MAX_TEXT_CHARS]


def _per_run_limit() -> int:
    """Optional per-run chunk cap.

    ``CLAUDE_SESSIONS_KG_NER_RE_BATCH=N`` processes at most N chunks per
    server start, then the next start picks up from the next un-logged
    chunk. Default ``0`` means "process every unprocessed chunk in one
    run" — the production behavior the user explicitly requested under
    ``/escalators-not-stairs`` (no skipping the first-time encoding).

    The cap is purely operational pacing for very large corpora; it
    never causes the pipeline to *skip* work, only to spread it across
    multiple runs.
    """
    raw = os.environ.get("CLAUDE_SESSIONS_KG_NER_RE_BATCH", "").strip()
    if not raw:
        return 0
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


_NER_INSERT_SQL = (
    "INSERT INTO entities (name, entity_type, source, chunk_id, confidence) VALUES (?, ?, ?, ?, ?)"
)
_RE_INSERT_SQL = (
    "INSERT INTO relations (src, dst, rel_type, weight, chunk_id, source) VALUES (?, ?, ?, ?, ?, ?)"
)


def _unprocessed_chunks(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Return (chunk_id, text) tuples whose chunk_id is missing from ner_chunks_log."""
    rows = conn.execute(
        """
        SELECT chunk_id, text
        FROM event_message_chunks
        WHERE chunk_id NOT IN (SELECT chunk_id FROM ner_chunks_log)
        ORDER BY chunk_id
        """
    ).fetchall()
    return [(int(r[0]), str(r[1])) for r in rows]


def _extract_entities_for_batch(
    model: Any,
    texts: list[str],
    chunk_ids: list[int],
) -> list[tuple[str, str, str, int, float]]:
    """Run GLiNER2 NER over a batch and flatten to insert-tuples.

    Returns ``(name, entity_type, source, chunk_id, confidence)`` rows.
    """
    results = model.batch_extract_entities(
        texts,
        list(NER_LABELS),
        batch_size=_GLINER2_BATCH,
        include_confidence=True,
    )
    rows: list[tuple[str, str, str, int, float]] = []
    for chunk_id, result in zip(chunk_ids, results, strict=True):
        for label, ents in (result or {}).get("entities", {}).items():
            for ent in ents:
                name = (ent.get("text") or "").strip()
                if not name:
                    continue
                rows.append(
                    (
                        name,
                        label,
                        "gliner2",
                        chunk_id,
                        float(ent.get("confidence", 1.0)),
                    )
                )
    return rows


def _extract_relations_for_batch(
    model: Any,
    texts: list[str],
    chunk_ids: list[int],
) -> list[tuple[str, str, str, float, int, str]]:
    """Run GLiNER2 RE over a batch and flatten to insert-tuples.

    Returns ``(src, dst, rel_type, weight, chunk_id, source)`` rows.
    """
    results = model.batch_extract_relations(
        texts,
        list(RE_LABELS),
        batch_size=_GLINER2_BATCH,
        include_confidence=True,
    )
    rows: list[tuple[str, str, str, float, int, str]] = []
    for chunk_id, result in zip(chunk_ids, results, strict=True):
        for rel_type, rels in (result or {}).get("relation_extraction", {}).items():
            for rel in rels:
                head = (rel.get("head", {}).get("text") or "").strip()
                tail = (rel.get("tail", {}).get("text") or "").strip()
                if not head or not tail or head == tail:
                    continue
                head_conf = float(rel.get("head", {}).get("confidence", 1.0))
                tail_conf = float(rel.get("tail", {}).get("confidence", 1.0))
                weight = (head_conf + tail_conf) / 2.0
                rows.append((head, tail, rel_type, weight, chunk_id, "gliner2"))
    return rows


def sync_ner_re(conn: sqlite3.Connection) -> tuple[int, int]:
    """Extract entities + relations from every unprocessed chunk via GLiNER2.

    Returns ``(entities_added, relations_added)``.
    """
    chunks = _unprocessed_chunks(conn)
    if not chunks:
        log.info("  NER+RE: no new chunks to process")
        return 0, 0

    cap = _per_run_limit()
    if cap and cap < len(chunks):
        log.info(
            "  NER+RE: per-run cap=%d (CLAUDE_SESSIONS_KG_NER_RE_BATCH); "
            "remaining %d chunks will run on subsequent server starts",
            cap,
            len(chunks) - cap,
        )
        chunks = chunks[:cap]

    log.info(
        "  NER+RE processing %d chunks via GLiNER2 (fastino/gliner2-base-v1)",
        len(chunks),
    )
    log.info("    entity labels: %s", list(NER_LABELS))
    log.info("    relation labels: %s", list(RE_LABELS))

    model = get_gliner2()
    ts = datetime.now(UTC).isoformat()
    total_entities = 0
    total_relations = 0
    t0 = time.monotonic()
    last_log = t0

    for batch_start in range(0, len(chunks), _OUTER_BATCH):
        batch = chunks[batch_start : batch_start + _OUTER_BATCH]
        chunk_ids = [cid for cid, _ in batch]
        texts = [_safe_text(text) for _, text in batch]

        ner_rows = _extract_entities_for_batch(model, texts, chunk_ids)
        if ner_rows:
            conn.executemany(_NER_INSERT_SQL, ner_rows)
            total_entities += len(ner_rows)

        re_rows = _extract_relations_for_batch(model, texts, chunk_ids)
        if re_rows:
            conn.executemany(_RE_INSERT_SQL, re_rows)
            total_relations += len(re_rows)

        conn.executemany(
            "INSERT OR IGNORE INTO ner_chunks_log (chunk_id, processed_at) VALUES (?, ?)",
            [(cid, ts) for cid in chunk_ids],
        )
        conn.executemany(
            "INSERT OR IGNORE INTO re_chunks_log (chunk_id, processed_at) VALUES (?, ?)",
            [(cid, ts) for cid in chunk_ids],
        )
        conn.commit()

        processed = min(batch_start + len(batch), len(chunks))
        now = time.monotonic()
        if now - last_log >= 3.0 or processed == len(chunks):
            rate = processed / (now - t0) if now > t0 else 0
            eta = (len(chunks) - processed) / rate if rate > 0 else 0
            log.info(
                "  NER+RE progress: %d/%d (%.1f chunks/s, ETA %.0f s, %d ents, %d rels)",
                processed,
                len(chunks),
                rate,
                eta,
                total_entities,
                total_relations,
            )
            last_log = now

    log.info(
        "  NER+RE complete: %d entities + %d relations from %d chunks in %.1f s",
        total_entities,
        total_relations,
        len(chunks),
        time.monotonic() - t0,
    )
    return total_entities, total_relations
