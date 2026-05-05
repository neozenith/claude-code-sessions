"""Tests for the background IndexerService.

The service owns:
- a daemon thread that drives ``CacheManager.ensure_ready``
- a ``threading.Event`` that signals cancellation
- a status dict (lock-protected) exposed for ``/api/health``

Tests use real SQLite cache files in ``tmp_path`` and a tiny synthetic
JSONL corpus so ``ensure_ready`` completes in <1 s. The KG and embedding
phases are disabled via the same env flags the production conftest uses
(set globally at conftest load time).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_code_sessions.database.sqlite.backend import SQLiteDatabase
from claude_code_sessions.database.sqlite.indexer import IndexerService


# ---------------------------------------------------------------------------
# Fixtures — synthetic project tree
# ---------------------------------------------------------------------------


def _write_session(project_dir: Path, session_id: str, n_events: int) -> None:
    """Drop a tiny JSONL file at ``<project>/<session>.jsonl``."""
    project_dir.mkdir(parents=True, exist_ok=True)
    base = datetime(2025, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(n_events):
        ts = base + timedelta(seconds=i)
        rows.append({
            "uuid": f"{session_id}-{i}",
            "parentUuid": f"{session_id}-{i - 1}" if i > 0 else None,
            "type": "user" if i % 2 == 0 else "assistant",
            "timestamp": ts.isoformat().replace("+00:00", "Z"),
            "sessionId": session_id,
            "message": {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"event {i}",
            },
        })
    (project_dir / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


@pytest.fixture
def synthetic_projects(tmp_path: Path) -> Path:
    """Build a 2-project / 3-session synthetic tree."""
    root = tmp_path / "projects"
    _write_session(root / "-Users-test-projA", "session-aaa", 5)
    _write_session(root / "-Users-test-projA", "session-bbb", 3)
    _write_session(root / "-Users-test-projB", "session-ccc", 7)
    return root


@pytest.fixture
def fresh_db(tmp_path: Path, synthetic_projects: Path) -> SQLiteDatabase:
    """A SQLiteDatabase whose ensure_ready has NOT been run yet."""
    return SQLiteDatabase(
        local_projects_path=synthetic_projects,
        home_projects_path=synthetic_projects,
        db_path=tmp_path / "cache.db",
    )


# ---------------------------------------------------------------------------
# IndexerService construction + thread lifecycle
# ---------------------------------------------------------------------------


class TestIndexerServiceLifecycle:
    def test_construction_does_not_run_indexer(self, fresh_db: SQLiteDatabase) -> None:
        """Constructing the service must not start the thread or touch
        the cache. Caller decides when to start()."""
        svc = IndexerService(fresh_db)
        assert not svc.is_running()
        assert svc.status()["phase"] == "idle"

    def test_start_runs_indexer_in_thread_and_completes(
        self, fresh_db: SQLiteDatabase
    ) -> None:
        svc = IndexerService(fresh_db)
        svc.start()
        # Wait up to 30 s for the synthetic corpus to be indexed.
        svc.wait(timeout=30)
        assert not svc.is_running()
        # Status reflects completion.
        s = svc.status()
        assert s["phase"] == "completed"
        # Sanity-check actual data made it into the cache.
        events = fresh_db.get_summary()
        assert events
        assert events[0]["total_events"] == 15  # 5 + 3 + 7

    def test_double_start_is_a_noop(self, fresh_db: SQLiteDatabase) -> None:
        svc = IndexerService(fresh_db)
        svc.start()
        svc.start()  # second call must not spawn a second thread
        svc.wait(timeout=30)
        assert svc.status()["phase"] == "completed"

    def test_stop_cancels_running_indexer(
        self, tmp_path: Path
    ) -> None:
        """The stop event must propagate. With a synthetic-corpus build,
        completion is fast — but the contract is: stop() returns within
        the join timeout, and is_running() flips to False."""
        # Larger synthetic tree so stop has a chance to land mid-flight.
        proj_root = tmp_path / "projects"
        for i in range(20):
            _write_session(proj_root / f"-Users-test-proj{i}", f"session-{i}", 50)
        db = SQLiteDatabase(
            local_projects_path=proj_root,
            home_projects_path=proj_root,
            db_path=tmp_path / "cache.db",
        )
        svc = IndexerService(db)
        svc.start()
        # Don't sleep here — IndexerService.stop() waits on the thread.
        svc.stop(timeout=30)
        assert not svc.is_running()
        # Phase is either "completed" (finished before stop landed) or
        # "cancelled" (stop event observed mid-build). Both are fine.
        assert svc.status()["phase"] in {"completed", "cancelled"}


class TestIndexerServiceStatus:
    def test_status_has_required_fields(self, fresh_db: SQLiteDatabase) -> None:
        svc = IndexerService(fresh_db)
        s = svc.status()
        # Stable shape so /api/health can rely on it.
        assert {"phase", "started_at", "finished_at", "error"} <= s.keys()

    def test_status_records_error_on_failure(
        self, tmp_path: Path, synthetic_projects: Path
    ) -> None:
        """If ensure_ready raises, the indexer must record the error
        rather than swallowing it. status['phase'] becomes 'failed'."""
        db = SQLiteDatabase(
            local_projects_path=synthetic_projects,
            home_projects_path=synthetic_projects,
            db_path=tmp_path / "cache.db",
        )
        # Force the cache layer to blow up by closing its connection
        # underneath. ensure_ready then raises ProgrammingError on first
        # query — exactly the kind of unexpected fault we want surfaced.
        original_ensure = db.ensure_ready

        def _boom() -> None:
            raise RuntimeError("synthetic indexer failure")

        db.ensure_ready = _boom  # type: ignore[method-assign]
        try:
            svc = IndexerService(db)
            svc.start()
            svc.wait(timeout=10)
            s = svc.status()
            assert s["phase"] == "failed"
            assert s["error"] is not None
            assert "synthetic indexer failure" in s["error"]
        finally:
            db.ensure_ready = original_ensure  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# SQLiteDatabase no longer eager-runs ensure_ready
# ---------------------------------------------------------------------------


class TestDatabaseConstructionIsLazy:
    def test_constructor_does_not_invoke_ensure_ready(
        self, tmp_path: Path, synthetic_projects: Path
    ) -> None:
        """Sanity: the constructor opens the cache but does not populate
        events. This is the change that lets the FastAPI server bind its
        port immediately on cold start."""
        db = SQLiteDatabase(
            local_projects_path=synthetic_projects,
            home_projects_path=synthetic_projects,
            db_path=tmp_path / "cache.db",
        )
        # No events yet — schema is initialized but the JSONL files have
        # not been ingested.
        rows = db._q("SELECT COUNT(*) AS n FROM events")
        assert rows[0]["n"] == 0

    def test_explicit_ensure_ready_populates_cache(
        self, tmp_path: Path, synthetic_projects: Path
    ) -> None:
        db = SQLiteDatabase(
            local_projects_path=synthetic_projects,
            home_projects_path=synthetic_projects,
            db_path=tmp_path / "cache.db",
        )
        db.ensure_ready()
        rows = db._q("SELECT COUNT(*) AS n FROM events")
        assert rows[0]["n"] == 15
