"""Parallel JSONL parser pool.

Drives phase 3 of the cache build using a producer/consumer split:

* **Parsers** — N worker threads call ``CacheManager._parse_file`` for
  files pulled off a work queue. Pure CPU + I/O work, GIL-friendly
  because ``json.loads`` releases the GIL during parsing.

* **Writer** — single thread that drains a result queue and runs
  ``CacheManager._write_parsed`` for each parsed file. SQLite's
  Python connection isn't safe for concurrent writes, so all DB
  state-mutation funnels through this thread.

Cancellation is cooperative: the supplied ``threading.Event`` is
checked between every file (parsers) and every queue ``get`` (writer).
On stop the work queue is drained, parsers exit, and the writer
flushes whatever it already has in flight.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from claude_code_sessions.database.sqlite.cache import CacheManager

log = logging.getLogger(__name__)


# Env var that overrides the worker count. Same naming style as
# CLAUDE_SESSIONS_WAVE_SIZE so the tuning surface is consistent.
INGEST_WORKERS_ENV = "CLAUDE_SESSIONS_INGEST_WORKERS"
DEFAULT_MAX_WORKERS = 8


def resolve_worker_count() -> int:
    """Default to ``min(8, cpu_count())``; override via env var.

    Cap at 8 because the writer thread is the bottleneck after that —
    extra parsers just queue up parsed batches the writer can't drain
    fast enough, burning RAM with no throughput gain. Override the cap
    explicitly if you have measured otherwise.
    """
    raw = os.environ.get(INGEST_WORKERS_ENV, "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            log.warning("invalid %s=%r — using auto-detected count", INGEST_WORKERS_ENV, raw)

    cpu = os.cpu_count() or 4
    return min(DEFAULT_MAX_WORKERS, cpu)


# Sentinel used to signal "no more work" to the writer thread.
_WRITER_DONE = object()


class ParallelIngester:
    """Ingests a list of files using a parser pool + single writer.

    Usage::

        ingester = ParallelIngester(cache, num_workers=4)
        result = ingester.ingest(files_to_update)
        # result["files_processed"], result["events_added"]

    Caller is responsible for committing if they want a single
    transaction across the whole batch — ``_write_parsed`` doesn't
    commit per file, and neither does this class. The wave pipeline
    does ``cache.conn.commit()`` after each ingest call.
    """

    def __init__(
        self,
        cache: CacheManager,
        *,
        num_workers: int | None = None,
        stop_event: threading.Event | None = None,
        result_queue_max: int = 32,
    ) -> None:
        self.cache = cache
        self.num_workers = num_workers if num_workers is not None else resolve_worker_count()
        self.stop_event = stop_event if stop_event is not None else threading.Event()
        # Bounded queue keeps RAM in check when parsers run faster than
        # the writer (large files take ~ms to parse but each row is a
        # separate INSERT — writer is slower).
        self._results: queue.Queue[Any] = queue.Queue(maxsize=result_queue_max)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def ingest(self, files: list[dict[str, Any]]) -> dict[str, int]:
        """Run the full parallel ingest. Returns a summary dict.

        ``files`` is the same shape ``CacheManager.ingest_file`` accepts:
        each item must have ``filepath``, ``project_id``, ``file_type``,
        ``mtime``, ``size_bytes`` populated (the same dicts produced by
        ``get_files_needing_update``).
        """
        if self.stop_event.is_set():
            log.info("parallel ingester: stop already set — skipping")
            return {"files_processed": 0, "events_added": 0}
        if not files:
            return {"files_processed": 0, "events_added": 0}

        log.info(
            "parallel ingester: %d files, %d worker(s)",
            len(files),
            self.num_workers,
        )
        t0 = time.monotonic()

        writer_result: dict[str, int] = {"files_processed": 0, "events_added": 0}
        writer_exc: list[BaseException] = []

        # Spin up the writer thread first so it's ready to drain as
        # soon as the first parsed batch lands. The writer owns the
        # SQLite connection for the duration of the ingest.
        writer = threading.Thread(
            target=self._writer_loop,
            args=(writer_result, writer_exc),
            name="parallel-ingester-writer",
        )
        writer.start()

        # Parsers run in a thread pool. Submit one task per file —
        # the pool naturally bounds concurrency to ``num_workers``.
        try:
            with ThreadPoolExecutor(
                max_workers=self.num_workers,
                thread_name_prefix="parallel-ingester-parser",
            ) as pool:
                for file_info in files:
                    if self.stop_event.is_set():
                        break
                    pool.submit(self._parser_task, file_info)
                # Falling out of the ``with`` waits for all submitted
                # tasks to finish (or raise). After this point, every
                # parsed file is on the queue.
        finally:
            # Tell the writer "no more work" — it drains and exits.
            self._results.put(_WRITER_DONE)
            writer.join()

        if writer_exc:
            # Re-raise the writer's exception on the caller's thread so
            # the wave pipeline (and IndexerService) record it as a
            # failure rather than silently dropping it.
            raise writer_exc[0]

        elapsed = time.monotonic() - t0
        log.info(
            "parallel ingester: %d files, %d events in %.1f s",
            writer_result["files_processed"],
            writer_result["events_added"],
            elapsed,
        )
        return writer_result

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    def _parser_task(self, file_info: dict[str, Any]) -> None:
        """Parse one file and push the result onto the writer queue.

        Uncaught exceptions here would silently drop a file, so we
        catch broadly and stash the exception on the queue — the
        writer loop unpacks it and re-raises on the main thread.
        """
        if self.stop_event.is_set():
            return
        try:
            parsed = self.cache._parse_file(file_info)
            if parsed is None:
                # Unreadable file — _parse_file already logged the
                # warning. Skip silently to match serial ingest behaviour.
                return
            self._results.put(parsed)
        except BaseException as exc:  # noqa: BLE001 — re-raised on main thread
            log.exception("parser failed on %s", file_info.get("filepath"))
            self._results.put(exc)

    def _writer_loop(
        self,
        result: dict[str, int],
        exc_holder: list[BaseException],
    ) -> None:
        """Drain the result queue and run SQL writes."""
        while True:
            item = self._results.get()
            if item is _WRITER_DONE:
                return
            if isinstance(item, BaseException):
                exc_holder.append(item)
                # Drain remaining items so parsers don't block on a
                # full queue, but don't process them — first failure
                # wins.
                self._drain_queue()
                return
            if self.stop_event.is_set():
                # Even mid-drain, stop should land. We've already
                # written some files; let the caller see what landed.
                self._drain_queue()
                return
            try:
                events = self.cache._write_parsed(item)
            except BaseException as exc:  # noqa: BLE001
                exc_holder.append(exc)
                self._drain_queue()
                return
            result["files_processed"] += 1
            result["events_added"] += events

    def _drain_queue(self) -> None:
        """Empty the queue without processing — used after stop or
        exception so parsers don't block on a full queue."""
        while True:
            try:
                item = self._results.get_nowait()
            except queue.Empty:
                return
            if item is _WRITER_DONE:
                return
