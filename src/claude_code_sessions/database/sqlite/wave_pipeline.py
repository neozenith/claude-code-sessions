"""Wave-based ingestion pipeline.

The original ``CacheManager.update()`` ran phases 3..7 linearly: ingest
all files, *then* chunk, *then* embed, *then* run the KG. For a fresh
build over a multi-GB corpus that meant nothing was queryable until the
whole pipeline finished — and any failure threw away all progress.

The wave pipeline runs in **two serial passes** — ingest is fast and must always
bring the cache up to date first; the embedding/KG work is slow and is drained
afterwards in bounded waves so it never holds a write lock while ingest is writing:

    # PASS 1 — ingest (fast): get every event into the cache, all waves first.
    while files_remaining and not stop.is_set():
        wave = next_wave(WAVE_SIZE)
        ingest_wave(wave)        # phase 3 — JSON parse + SQL insert
        rebuild_aggregates()     # phase 4

    # PASS 2 — slow downstream, AFTER ingest, in bounded waves:
    sync_chunks(conn)            # phase 5 — only NEW event_ids
    sync_embeddings(conn)        # phase 6 — only NEW chunks
    while pending_ner_chunks():  # phase 7 — NER/RE is capped per run
        run_kg_pipeline()        #   (dedicated connection; commits per wave)

Each wave commits as it completes, so the dashboard sees data appear
incrementally and a crash mid-build leaves earlier work intact. The
sync_* functions are already incremental (they key off per-phase log
tables) so this works without changes inside them. Serialising ingest
ahead of KG removes the ingest-write vs KG-write lock contention that
previously crashed the boot indexer with "database is locked".

Cooperative cancellation: a ``threading.Event`` is checked at every
wave boundary and once again before each phase inside the wave. The
parser pool added in Phase D will check the same event between files
inside ``ingest_wave``.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Any

from claude_code_sessions.database.sqlite.embeddings import sync_chunks
from claude_code_sessions.database.sqlite.parallel_ingester import ParallelIngester

if TYPE_CHECKING:
    from claude_code_sessions.database.sqlite.cache import CacheManager

log = logging.getLogger(__name__)

# Default wave size. 50 files is a sweet spot in early profiling: small
# enough that a single wave commits within ~30 s on cold corpora, large
# enough that fixed per-wave overhead (KG entity-resolution clustering,
# Leiden community detection) doesn't dominate.
DEFAULT_WAVE_SIZE = 50

# Env-var name. Lives here so callers don't pass magic strings around.
WAVE_SIZE_ENV = "CLAUDE_SESSIONS_WAVE_SIZE"


def resolve_wave_size() -> int:
    """Return the configured wave size.

    ``CLAUDE_SESSIONS_WAVE_SIZE`` overrides the default. Invalid or
    non-positive values fall back silently to the default — wave size
    is a tuning knob, not a correctness setting, so a typo shouldn't
    halt startup.
    """
    raw = os.environ.get(WAVE_SIZE_ENV, "").strip()
    if not raw:
        return DEFAULT_WAVE_SIZE
    try:
        value = int(raw)
    except ValueError:
        log.warning("invalid %s=%r — falling back to %d", WAVE_SIZE_ENV, raw, DEFAULT_WAVE_SIZE)
        return DEFAULT_WAVE_SIZE
    if value <= 0:
        return DEFAULT_WAVE_SIZE
    return value


WaveDoneHook = Callable[[int, dict[str, int]], None]


class WavePipeline:
    """Drives the cache build in bounded waves.

    Phase 7 (KG) runs synchronously here rather than in a daemon thread.
    The original CacheManager design backgrounded KG so the server boot
    wouldn't block — but the wave pipeline is itself running in a
    background thread (``IndexerService``), so backgrounding KG again
    would just create a queue of incomplete waves. Inline-per-wave
    keeps the per-wave commit story tidy: when a wave is logged "done,"
    every downstream artifact is already committed.
    """

    def __init__(
        self,
        cache: CacheManager,
        *,
        wave_size: int | None = None,
        stop_event: Event | None = None,
    ) -> None:
        self.cache = cache
        self.wave_size = wave_size if wave_size is not None else resolve_wave_size()
        # Reuse CacheManager's stop_event by default so callers that
        # already hold a CacheManager handle (e.g. IndexerService via
        # ``db.cache.request_stop()``) don't need to thread an
        # additional Event.
        self.stop_event = stop_event if stop_event is not None else cache._stop_event
        self.on_wave_done: WaveDoneHook | None = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, projects_path: Path) -> dict[str, Any]:
        """Drive the wave loop until exhausted or cancelled.

        Returns a summary dict with counts. The shape is stable across
        early-exits (cancellation) — fields are zero rather than absent.
        """
        t0 = time.monotonic()

        # Phase 2 (discovery) is a single pass — files don't appear
        # mid-build, and any new files added while we're running will
        # be picked up on the next ``ensure_ready`` invocation. We skip
        # the discovery cost on every wave that way.
        log.info("wave pipeline scanning %s", projects_path)
        all_files = self.cache.discover_files(projects_path)
        files_to_update = self.cache.get_files_needing_update(all_files)
        log.info(
            "wave pipeline: %d total files, %d need update, wave_size=%d",
            len(all_files),
            len(files_to_update),
            self.wave_size,
        )

        result: dict[str, Any] = {
            "files_total": len(all_files),
            "files_processed": 0,
            "waves_completed": 0,
            "events_added": 0,
            "chunks_added": 0,
            "cancelled": False,
        }

        if not files_to_update:
            # No new/changed files to ingest — but a previous run may have
            # been interrupted or crashed *after* chunking and *before*
            # embedding / KG, leaving a residual downstream backlog. Those
            # phases are global-incremental and are otherwise gated behind
            # file ingest, so without this catch-up they would NEVER drain
            # on a warm cache — coverage would stall permanently. Run them
            # once so the backlog can complete.
            log.info("wave pipeline: no files need ingest — running downstream catch-up")
            result["chunks_added"] += self._drain_downstream()
            return result

        # Slice the to-do list into waves. The slice is materialised
        # ahead of time so we can report total wave count upfront —
        # useful for progress UIs.
        waves = [
            files_to_update[i : i + self.wave_size]
            for i in range(0, len(files_to_update), self.wave_size)
        ]
        total_waves = len(waves)
        log.info("wave pipeline: %d wave(s) queued", total_waves)

        # ── PASS 1: ingest + aggregate every wave first (fast) ─────────
        # No downstream work here — get all events into the cache before any
        # KG write opens, so ingest and KG never contend for the write lock.
        for wave_idx, wave in enumerate(waves, 1):
            if self.stop_event.is_set():
                log.info(
                    "wave pipeline: stop signalled before wave %d/%d — exiting",
                    wave_idx,
                    total_waves,
                )
                result["cancelled"] = True
                break

            wave_summary = self._ingest_one_wave(wave_idx, total_waves, wave)
            result["files_processed"] += wave_summary["files_processed"]
            result["events_added"] += wave_summary["events_added"]
            result["waves_completed"] += 1

            if self.on_wave_done is not None:
                self.on_wave_done(wave_idx, wave_summary)

        # ── PASS 2: slow downstream (chunk → embed → KG) in bounded waves ──
        # Runs only after all ingest is committed, so the KG connection's
        # writes never collide with an ingest write.
        if not self.stop_event.is_set():
            result["chunks_added"] += self._drain_downstream()

        elapsed = time.monotonic() - t0
        log.info(
            "wave pipeline: done — %d ingest wave(s), %d files, %d events, %d chunks in %.1f s%s",
            result["waves_completed"],
            result["files_processed"],
            result["events_added"],
            result["chunks_added"],
            elapsed,
            " (cancelled)" if result["cancelled"] else "",
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ingest_one_wave(
        self,
        wave_idx: int,
        total: int,
        wave: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Ingest + aggregate a single wave (phases 3-4 only). The slow downstream
        phases (chunk/embed/KG) are deferred to :meth:`_drain_downstream` so they run
        after *all* ingest, never interleaved with it."""
        log.info("──────── ingest wave %d/%d (%d files) ────────", wave_idx, total, len(wave))
        t_wave = time.monotonic()

        # Phase 3: parallel ingest. ParallelIngester forks the file list
        # across N parser threads (one tasks per file, JSON parse + event
        # parsing) and funnels parsed batches into a single SQLite writer
        # thread. The contract: all SQL state-mutation runs serially
        # (SQLite connections aren't safe for concurrent writes), but
        # the bulk JSON-parse work happens in parallel.
        ingester = ParallelIngester(self.cache, stop_event=self.stop_event)
        ingest_summary = ingester.ingest(wave)
        events_added = ingest_summary["events_added"]
        files_processed = ingest_summary["files_processed"]
        self.cache.conn.commit()

        # Phase 4 (agg): rebuild project/session rollups + dimensional
        # aggregate refresh. Mirrors the original update() decision:
        # on a fresh cache (agg table empty) do a full rebuild, else
        # a per-range refresh scoped to this wave's timestamp window.
        affected_ids = [
            f.get("source_file_id") for f in wave if isinstance(f.get("source_file_id"), int)
        ]
        if affected_ids:
            self.cache.rebuild_aggregates()
            if self.cache._agg_tables_empty():
                # First wave on a fresh cache. A full rebuild is cheap
                # at this point because there's only one wave's worth
                # of events in the table.
                self.cache.refresh_aggregates_for_range()
            else:
                window = self.cache._timestamp_window_for_files(affected_ids)  # type: ignore[arg-type]
                if window is not None:
                    self.cache.refresh_aggregates_for_range(window[0], window[1])

        elapsed = time.monotonic() - t_wave
        summary = {
            "files_processed": files_processed,
            "events_added": events_added,
            "chunks_added": 0,  # chunking is deferred to the downstream drain
        }
        log.info(
            "──── ingest wave %d/%d done — %d files, %d events in %.1f s ────",
            wave_idx,
            total,
            summary["files_processed"],
            summary["events_added"],
            elapsed,
        )
        return summary

    @staticmethod
    def _flag(name: str) -> bool:
        return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}

    def _drain_downstream(self) -> int:
        """Run the slow downstream phases (chunk → embed → KG) AFTER all ingest, in
        bounded waves.

        chunk + embed are global-incremental and drain in one pass each. KG NER/RE is
        capped per run (``CLAUDE_SESSIONS_KG_NER_RE_BATCH``), so we call
        ``run_kg_pipeline`` repeatedly until the NER backlog clears — each call commits
        and the KG connection's lock is released between waves, so a long build never
        holds one giant write lock against the request threads. KG runs at least once
        so a warm-cache catch-up of stranded entity-resolution/community work drains too.

        Honours the cancellation event between phases and the same
        ``CLAUDE_SESSIONS_DISABLE_{EMBEDDINGS,KG}`` test-isolation flags. Returns the
        number of chunks added this pass (matching the historical return contract).
        """
        if self.stop_event.is_set():
            return 0

        chunks_added = sync_chunks(self.cache.conn)

        # Phase 6 (embeddings) — gated on CLAUDE_SESSIONS_DISABLE_EMBEDDINGS. This also
        # loads the sqlite-muninn extension + embedding model onto the connection, which
        # KG depends on (entity embeddings call muninn_embed(); ER/communities use the
        # muninn graph modules) — so if embeddings are disabled, KG is skipped too.
        if self._flag("CLAUDE_SESSIONS_DISABLE_EMBEDDINGS"):
            log.info("downstream: embeddings disabled — skipping embed + KG (KG depends on them)")
            return chunks_added

        if not self.stop_event.is_set():
            self.cache.sync_embeddings()

        if self._flag("CLAUDE_SESSIONS_DISABLE_KG") or self.stop_event.is_set():
            return chunks_added

        # Phase 7 (KG) in bounded waves. run_kg_pipeline uses a DEDICATED connection
        # (schema-mutating DDL would raise SQLITE_LOCKED on the shared conn the request
        # threads read through). Loop until NER/RE has no pending chunks, with a
        # no-progress guard so a chunk GLiNER can't process never spins forever.
        prev_pending: int | None = None
        kg_wave = 0
        while not self.stop_event.is_set():
            kg_wave += 1
            self.cache.run_kg_pipeline()
            pending = self.cache.pending_ner_chunks()
            if pending == 0:
                break
            if prev_pending is not None and pending >= prev_pending:
                log.warning(
                    "downstream KG drain stalled at %d chunk(s) pending NER/RE — stopping",
                    pending,
                )
                break
            log.info("downstream KG wave %d done — %d chunk(s) still pending", kg_wave, pending)
            prev_pending = pending

        return chunks_added
