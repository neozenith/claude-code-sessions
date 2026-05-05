"""Wave-based ingestion pipeline.

The original ``CacheManager.update()`` ran phases 3..7 linearly: ingest
all files, *then* chunk, *then* embed, *then* run the KG. For a fresh
build over a multi-GB corpus that meant nothing was queryable until the
whole pipeline finished — and any failure threw away all progress.

The wave pipeline reshapes that work into bounded batches:

    while files_remaining and not stop.is_set():
        wave = next_wave(WAVE_SIZE)
        ingest_wave(wave)        # phase 3 — JSON parse + SQL insert
        sync_chunks(conn)        # phase 5 — only NEW event_ids
        sync_embeddings(conn)    # phase 6 — only NEW chunks
        sync_kg_synchronously()  # phase 7 — only NEW chunks/entities
        log_wave_summary()

Each wave commits as it completes, so the dashboard sees data appear
incrementally and a crash mid-build leaves wave-1..N-1 intact. The
sync_* functions are already incremental (they key off per-phase log
tables) so this works without changes inside them.

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
            log.info("wave pipeline: nothing to do")
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

        for wave_idx, wave in enumerate(waves, 1):
            if self.stop_event.is_set():
                log.info(
                    "wave pipeline: stop signalled before wave %d/%d — exiting",
                    wave_idx,
                    total_waves,
                )
                result["cancelled"] = True
                break

            wave_summary = self._run_one_wave(wave_idx, total_waves, wave)
            result["files_processed"] += wave_summary["files_processed"]
            result["events_added"] += wave_summary["events_added"]
            result["chunks_added"] += wave_summary["chunks_added"]
            result["waves_completed"] += 1

            if self.on_wave_done is not None:
                self.on_wave_done(wave_idx, wave_summary)

        elapsed = time.monotonic() - t0
        log.info(
            "wave pipeline: done — %d wave(s), %d files, %d events, %d chunks in %.1f s%s",
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

    def _run_one_wave(
        self,
        wave_idx: int,
        total: int,
        wave: list[dict[str, Any]],
    ) -> dict[str, int]:
        log.info("──────── wave %d/%d (%d files) ────────", wave_idx, total, len(wave))
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

        # Phase 5: chunk human-prompt events from this wave. sync_chunks
        # is global-incremental — it picks up any event_id without
        # corresponding chunks, which after phase 3 above is exactly
        # this wave's events.
        if self.stop_event.is_set():
            chunks_added = 0
        else:
            chunks_added = sync_chunks(self.cache.conn)

        # Phase 6 (embeddings) and Phase 7 (KG) are skipped here unless
        # the env flags are clear. The CacheManager already wraps these
        # behind its sync_embeddings / _spawn_kg helpers, so the wave
        # loop stays simple and gates on the same env vars users
        # already set.
        if not self.stop_event.is_set():
            self.cache.sync_embeddings()

        # KG runs inline per-wave so we don't pile up overlapping
        # background runs. Skipping it via env in tests/CI keeps the
        # wave-loop unit tests fast.
        kg_flag = os.environ.get("CLAUDE_SESSIONS_DISABLE_KG", "").strip().lower()
        if kg_flag not in {"1", "true", "yes", "on"} and not self.stop_event.is_set():
            from claude_code_sessions.database.sqlite.kg import sync_kg

            sync_kg(self.cache.conn)

        elapsed = time.monotonic() - t_wave
        summary = {
            "files_processed": files_processed,
            "events_added": events_added,
            "chunks_added": chunks_added,
        }
        log.info(
            "──── wave %d/%d done — %d files, %d events, %d chunks in %.1f s ────",
            wave_idx,
            total,
            summary["files_processed"],
            summary["events_added"],
            summary["chunks_added"],
            elapsed,
        )
        return summary
