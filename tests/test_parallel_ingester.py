"""Tests for the parallel JSONL parser pool.

The parallel ingester replaces the per-file ``CacheManager.ingest_file``
loop inside a wave. Architecture:

* N parser worker threads (default ``min(8, cpu_count())``).
  Each pulls a ``file_info`` off a work queue, parses the JSONL, and
  pushes a ``(file_info, parsed_events)`` tuple onto a result queue.
* 1 writer thread that owns the SQLite connection and drains the
  result queue, running the same INSERT statements ``ingest_file``
  ran serially.
* A ``threading.Event`` propagated to all workers + writer so the
  pipeline can be cancelled at any file boundary.

Tests assert: parity with serial ingestion (same row counts and same
data), cancellation halts cleanly, and parser exceptions surface
rather than silently dropping files.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_code_sessions.database.sqlite.cache import CacheManager
from claude_code_sessions.database.sqlite.parallel_ingester import (
    INGEST_WORKERS_ENV,
    ParallelIngester,
    resolve_worker_count,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_session(project_dir: Path, session_id: str, n_events: int) -> None:
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
def synthetic_corpus(tmp_path: Path) -> tuple[Path, list[dict]]:
    """6 projects × 2 sessions × 10 events each = 12 files / 120 events."""
    root = tmp_path / "projects"
    files = []
    for p in range(6):
        for s in range(2):
            project_dir = root / f"-Users-test-proj{p}"
            session_id = f"sess-{p}-{s}"
            _write_session(project_dir, session_id, 10)
            files.append({
                "filepath": str(project_dir / f"{session_id}.jsonl"),
                "project_id": project_dir.name,
                "session_id": session_id,
                "file_type": "main_session",
            })
    return root, files


@pytest.fixture
def fresh_cache(tmp_path: Path) -> CacheManager:
    cache = CacheManager(tmp_path / "cache.db")
    cache.init_schema()
    return cache


# ---------------------------------------------------------------------------
# resolve_worker_count
# ---------------------------------------------------------------------------


class TestResolveWorkerCount:
    def test_default_is_capped_at_8(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(INGEST_WORKERS_ENV, raising=False)
        n = resolve_worker_count()
        assert 1 <= n <= 8

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(INGEST_WORKERS_ENV, "3")
        assert resolve_worker_count() == 3

    def test_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(INGEST_WORKERS_ENV, "garbage")
        assert resolve_worker_count() >= 1

    def test_zero_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(INGEST_WORKERS_ENV, "0")
        assert resolve_worker_count() >= 1


# ---------------------------------------------------------------------------
# ParallelIngester — happy path
# ---------------------------------------------------------------------------


class TestParallelIngesterIngest:
    def test_ingests_all_files_and_events(
        self,
        fresh_cache: CacheManager,
        synthetic_corpus: tuple[Path, list[dict]],
    ) -> None:
        _root, files = synthetic_corpus
        # Mark all files as "new" with mtime/size populated — the same
        # state get_files_needing_update would have produced.
        files = fresh_cache.get_files_needing_update(files)
        ingester = ParallelIngester(fresh_cache, num_workers=4)
        result = ingester.ingest(files)

        assert result["files_processed"] == 12
        assert result["events_added"] == 120
        events = fresh_cache.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert events == 120
        # event_edges: each event has parent except the first per session
        # → (10 - 1) × 12 = 108 edges.
        edges = fresh_cache.conn.execute("SELECT COUNT(*) FROM event_edges").fetchone()[0]
        assert edges == 108

    def test_parity_with_serial_ingest(
        self,
        tmp_path: Path,
        synthetic_corpus: tuple[Path, list[dict]],
    ) -> None:
        """Run both serial and parallel ingest; row counts and event
        UUIDs must match exactly. This is the regression guard
        against subtle parser differences."""
        _root, files = synthetic_corpus

        # Serial run
        serial_cache = CacheManager(tmp_path / "serial.db")
        serial_cache.init_schema()
        serial_files = serial_cache.get_files_needing_update(files.copy())
        for f in serial_files:
            serial_cache.ingest_file(f)
        serial_cache.conn.commit()

        # Parallel run on a separate cache db
        par_cache = CacheManager(tmp_path / "parallel.db")
        par_cache.init_schema()
        par_files = par_cache.get_files_needing_update(files.copy())
        ParallelIngester(par_cache, num_workers=4).ingest(par_files)

        for table in ("events", "event_edges", "event_calls", "source_files"):
            s_count = serial_cache.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            p_count = par_cache.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert s_count == p_count, f"{table} row count mismatch: serial={s_count}, parallel={p_count}"

        # UUIDs match (set comparison — order may differ across threads)
        s_uuids = {row[0] for row in serial_cache.conn.execute("SELECT uuid FROM events").fetchall()}
        p_uuids = {row[0] for row in par_cache.conn.execute("SELECT uuid FROM events").fetchall()}
        assert s_uuids == p_uuids


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestParallelIngesterCancellation:
    def test_stop_event_set_before_ingest_returns_immediately(
        self,
        fresh_cache: CacheManager,
        synthetic_corpus: tuple[Path, list[dict]],
    ) -> None:
        _root, files = synthetic_corpus
        files = fresh_cache.get_files_needing_update(files)
        stop = threading.Event()
        stop.set()
        ingester = ParallelIngester(fresh_cache, num_workers=4, stop_event=stop)
        result = ingester.ingest(files)
        assert result["files_processed"] == 0
        assert result["events_added"] == 0

    def test_stop_event_during_ingest_halts_cleanly(
        self,
        tmp_path: Path,
    ) -> None:
        """Build a larger corpus, set stop after a few files, expect
        partial progress and no exception. The exact count is
        non-deterministic (depends on thread scheduling) but it must
        be strictly less than the total."""
        root = tmp_path / "projects"
        for p in range(20):
            _write_session(root / f"-Users-test-proj{p}", f"sess-{p}", 50)
        files = [
            {
                "filepath": str(root / f"-Users-test-proj{p}" / f"sess-{p}.jsonl"),
                "project_id": f"-Users-test-proj{p}",
                "session_id": f"sess-{p}",
                "file_type": "main_session",
            }
            for p in range(20)
        ]
        cache = CacheManager(tmp_path / "cache.db")
        cache.init_schema()
        files = cache.get_files_needing_update(files)
        stop = threading.Event()
        ingester = ParallelIngester(cache, num_workers=2, stop_event=stop)

        # Trip the stop flag from a background timer so it races the
        # ingest thread. 50 ms is enough for 1-2 files in a 2-worker
        # pool but not the full corpus.
        timer = threading.Timer(0.05, stop.set)
        timer.start()
        try:
            result = ingester.ingest(files)
        finally:
            timer.cancel()

        # Some progress, but not all 20 files. (>=0 is the safe lower
        # bound — on a slow machine the timer could fire before any
        # file finishes.)
        assert 0 <= result["files_processed"] < 20


# ---------------------------------------------------------------------------
# Exception propagation
# ---------------------------------------------------------------------------


class TestParallelIngesterExceptions:
    def test_corrupt_file_does_not_crash_ingest(
        self,
        fresh_cache: CacheManager,
        tmp_path: Path,
    ) -> None:
        """A JSON-decode error inside one file must not abort the
        whole ingest — the existing serial ingest_file silently skips
        bad lines, and the parallel path keeps that contract."""
        proj = tmp_path / "projects" / "-Users-test-projA"
        _write_session(proj, "good-session", 5)
        # Append a broken line to the second session file.
        bad_path = proj / "bad-session.jsonl"
        bad_path.write_text(
            json.dumps({"uuid": "x", "type": "user", "timestamp": "2025-01-01T00:00:00Z",
                        "sessionId": "bad-session", "message": {"role": "user", "content": "ok"}})
            + "\n{ this is not valid json\n",
            encoding="utf-8",
        )
        files = [
            {"filepath": str(proj / "good-session.jsonl"), "project_id": "-Users-test-projA",
             "session_id": "good-session", "file_type": "main_session"},
            {"filepath": str(bad_path), "project_id": "-Users-test-projA",
             "session_id": "bad-session", "file_type": "main_session"},
        ]
        files = fresh_cache.get_files_needing_update(files)
        result = ParallelIngester(fresh_cache, num_workers=2).ingest(files)
        # Both files counted as processed; only the well-formed event
        # from the bad file is ingested (5 + 1 = 6).
        assert result["files_processed"] == 2
        events = fresh_cache.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert events == 6
