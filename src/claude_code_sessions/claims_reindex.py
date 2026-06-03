"""CR5 manual (re)trigger of claims indexation for one scope×grain slice.

Mirrors the ``/api/kg/reindex`` background pattern: a POST kicks a daemon thread
that runs L1 claim extraction over the slice's sessions + the set-union roll-up +
the failure roll-up for one model, while a status endpoint is polled. The heavy
work (model load + ``muninn_chat``) runs OFF the request thread, on its own SQLite
connection, so the API stays responsive.

The work is injected (``runner``) so the manager's state machine is unit-testable
without loading a GGUF; :func:`default_runner` is the real slice.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

# A progress callback the runner calls to publish counts mid-run.
ProgressCb = Callable[..., None]
Runner = Callable[[str, str, str, int, ProgressCb], None]


class ClaimsReindexManager:
    """Single-flight background runner for claims (re)indexation of a slice."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._status: dict[str, Any] = {"state": "idle"}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def is_running(self) -> bool:
        with self._lock:
            return self._status.get("state") == "running"

    def start(
        self, scope_path: str, grain: str, model: str, limit: int, runner: Runner
    ) -> dict[str, Any]:
        """Begin a run unless one is in flight (idempotent — a double-click is a no-op)."""
        with self._lock:
            if self._status.get("state") == "running":
                return {**self._status, "already_running": True}
            self._status = {
                "state": "running", "scope_path": scope_path, "grain": grain, "model": model,
                "sessions_total": 0, "sessions_done": 0, "failures": 0, "rollups_written": 0,
                "message": "starting", "started_at": datetime.now(UTC).isoformat(),
                "finished_at": None, "error": None,
            }
        self._thread = threading.Thread(
            target=self._run, args=(scope_path, grain, model, limit, runner), daemon=True
        )
        self._thread.start()
        return {**self.status(), "already_running": False}

    def _progress(self, **kw: Any) -> None:
        with self._lock:
            self._status.update(kw)

    def _run(self, scope_path: str, grain: str, model: str, limit: int, runner: Runner) -> None:
        try:
            runner(scope_path, grain, model, limit, self._progress)
            self._progress(
                state="done", message="complete", finished_at=datetime.now(UTC).isoformat()
            )
        except Exception as exc:  # noqa: BLE001 — surface as job error, never crash the server
            log.exception("claims reindex failed for %s/%s/%s", model, scope_path, grain)
            self._progress(
                state="error", error=str(exc), message="failed",
                finished_at=datetime.now(UTC).isoformat(),
            )


def default_runner(
    scope_path: str, grain: str, model: str, limit: int, progress: ProgressCb
) -> None:
    """The real slice: extract claims for the scope's sessions (model), then roll up
    that grain + the failure stream. Runs on its own chat connection at the
    evidence-sized 64k context. Imports are lazy (heavy summariser deps)."""
    from claude_code_sessions.config import PROJECTS_PATH
    from claude_code_sessions.database.sqlite.claims import (
        MuninnClaimsEngine,
        ensure_claims_schema,
        extract_session_claims,
        rollup_failures,
        set_union_rollup,
    )
    from claude_code_sessions.project_resolver import ProjectResolver
    from claude_code_sessions.summarise_cli import (
        DEFAULT_N_CTX,
        GRAINS,
        _embed,
        _open_chat_connection,
        bench_session_keys,
        gguf_path,
        make_embed_cosine,
    )

    path = gguf_path(model)
    if path is None:
        raise RuntimeError(f"no GGUF on disk for model {model!r} (cannot reindex)")
    conn = _open_chat_connection(model, path, n_ctx=DEFAULT_N_CTX)
    try:
        conn.execute("PRAGMA busy_timeout=30000")  # tolerate the server's concurrent writes
        ensure_claims_schema(conn)
        resolver = ProjectResolver(PROJECTS_PATH)
        keys = bench_session_keys(conn, resolver, (scope_path,), since=None)[:limit]
        progress(sessions_total=len(keys), message="extracting claims")
        engine = MuninnClaimsEngine(conn)
        done = fails = 0
        for pid, sid in keys:
            try:
                extract_session_claims(conn, pid, sid, engine, model)
                done += 1
            except (ValueError, KeyError):  # parse failure already recorded to the failure stream
                fails += 1
            progress(sessions_done=done, failures=fails)
        # L1 (extraction) is grain-independent — one session_claims set serves every
        # grain. L2 (set-union) is the only grain-sensitive layer and is cheap (no
        # muninn_chat). So a single reindex rebuilds ALL grains' roll-ups, not just the
        # one the user happened to be viewing — otherwise day/week stay empty after a
        # month reindex. INSERT OR REPLACE makes each grain rebuild idempotent.
        progress(message=f"rolling up all grains (viewing {grain})")
        make_embed_cosine(conn)  # register the embedder for the cosine dedup tier
        written = 0
        for g in GRAINS:
            written += set_union_rollup(conn, model, g, resolver, embed=lambda t: _embed(conn, t))
            rollup_failures(conn, model, g, resolver)
            progress(rollups_written=written)
    finally:
        conn.close()
