"""Background indexer service.

Owns the daemon thread that drives ``CacheManager.ensure_ready``. The
service is constructed at FastAPI startup, started inside the lifespan
context, and stopped on shutdown — so the server thread never blocks on
a multi-hour cold start.

Public surface:

* ``IndexerService(db).start()`` — spawn the indexer thread.
* ``.stop(timeout=...)``         — set the cancel event and join.
* ``.wait(timeout=...)``         — wait for natural completion.
* ``.is_running()``              — whether the thread is alive.
* ``.status()``                  — read-only dict for ``/api/health``.

Cancellation is cooperative: the cache pipeline checks the stop event at
phase / wave boundaries (Phase C wires this in) and exits early. Existing
phases (KG, embeddings) inherit the cancellation flow via the same event.

Logging: workers log via ``logging.getLogger(__name__)``. Because
``main.py`` calls ``logging.basicConfig()`` at module load, the records
propagate to whatever handlers uvicorn uses — there's no extra plumbing
required to "surface logs to the server."
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from claude_code_sessions.database.sqlite.backend import SQLiteDatabase

log = logging.getLogger(__name__)

# Phases of the public status field. Frontends key off these strings,
# so they're API contract — don't rename without coordinating.
PHASE_IDLE = "idle"
PHASE_RUNNING = "running"
PHASE_COMPLETED = "completed"
PHASE_CANCELLED = "cancelled"
PHASE_FAILED = "failed"


class IndexerService:
    """Drives ``SQLiteDatabase.ensure_ready`` in a background daemon thread.

    The constructor is cheap and side-effect-free. ``start()`` spawns a
    single daemon thread; subsequent ``start()`` calls are no-ops so the
    FastAPI lifespan can be re-entrant safely.
    """

    def __init__(self, db: SQLiteDatabase) -> None:
        self._db = db
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # RLock — start() holds the lock while calling _set_status(),
        # which itself takes the lock. A non-reentrant Lock would
        # deadlock the calling thread on the second acquisition.
        self._lock = threading.RLock()
        self._status: dict[str, Any] = {
            "phase": PHASE_IDLE,
            "started_at": None,
            "finished_at": None,
            "error": None,
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                log.debug("IndexerService.start(): already running, no-op")
                return
            self._stop.clear()
            self._set_status(
                phase=PHASE_RUNNING,
                started_at=datetime.now(UTC).isoformat(),
                finished_at=None,
                error=None,
            )
            self._thread = threading.Thread(
                target=self._run,
                name="claude-sessions-indexer",
                daemon=True,
            )
            self._thread.start()
            log.info("indexer thread started")

    def stop(self, timeout: float = 30.0) -> None:
        """Signal cancellation and wait up to ``timeout`` seconds for the
        thread to exit.

        Safe to call from any thread (including FastAPI lifespan
        shutdown). Idempotent — calling stop on a non-started or
        already-stopped service is a no-op.
        """
        with self._lock:
            thread = self._thread
        if thread is None:
            return
        if thread.is_alive():
            log.info("indexer stop requested — setting cancel event")
            self._stop.set()
            # Hand cancellation hint to CacheManager too. Phase C wires
            # this into the wave loop; until then the running phase has
            # to finish on its own, so the timeout may elapse.
            self._db.cache.request_stop()
            thread.join(timeout=timeout)
            if thread.is_alive():
                log.warning(
                    "indexer thread did not exit within %.1f s; "
                    "leaving as daemon (process exit will reap it)",
                    timeout,
                )

    def wait(self, timeout: float | None = None) -> None:
        """Block until the indexer thread exits naturally (or timeout)."""
        with self._lock:
            thread = self._thread
        if thread is None:
            return
        thread.join(timeout=timeout)

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict[str, Any]:
        """Snapshot of the current indexer state.

        Safe to call from request handlers — the status dict is copied
        under the lock so callers can't observe a torn write.
        """
        with self._lock:
            return dict(self._status)

    @property
    def stop_event(self) -> threading.Event:
        """The cancellation event. Phase C/D pass this to the wave loop
        and parser pool so workers exit at task boundaries."""
        return self._stop

    # ------------------------------------------------------------------
    # Worker — runs in the background thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        try:
            self._db.ensure_ready()
        except BaseException as exc:  # noqa: BLE001 — we re-record + re-raise into status
            log.exception("indexer thread crashed")
            self._set_status(
                phase=PHASE_FAILED,
                finished_at=datetime.now(UTC).isoformat(),
                error=f"{type(exc).__name__}: {exc}",
            )
            return

        if self._stop.is_set():
            self._set_status(
                phase=PHASE_CANCELLED,
                finished_at=datetime.now(UTC).isoformat(),
            )
            log.info("indexer thread exited (cancelled)")
        else:
            self._set_status(
                phase=PHASE_COMPLETED,
                finished_at=datetime.now(UTC).isoformat(),
            )
            log.info("indexer thread exited (completed)")

    def _set_status(self, **kwargs: Any) -> None:
        with self._lock:
            self._status.update(kwargs)
