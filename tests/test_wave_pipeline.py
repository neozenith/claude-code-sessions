"""Tests for the wave-based ingestion pipeline.

Phase C replaces the linear ``CacheManager.update()`` body with a wave
loop:

    while files_remaining and not stop.is_set():
        wave = next_wave(WAVE_SIZE)
        ingest_wave(wave)        # phase 3
        sync_chunks(conn)        # phase 5
        sync_embeddings(conn)    # phase 6 (skipped via env in tests)
        sync_kg(conn)            # phase 7 (skipped via env in tests)
        log_wave_summary()

The contract under test:

* All files end up ingested when the loop finishes naturally.
* The cache is queryable mid-pipeline — after wave N completes, the
  events from waves 1..N are visible.
* Setting the stop event causes the loop to exit cleanly at the
  next wave boundary.
* Wave size is configurable via the ``CLAUDE_SESSIONS_WAVE_SIZE`` env
  var, with a sensible default.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from claude_code_sessions.database.sqlite.cache import CacheManager
from claude_code_sessions.database.sqlite.wave_pipeline import (
    DEFAULT_WAVE_SIZE,
    WavePipeline,
    resolve_wave_size,
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
def projects_with_n_files(tmp_path: Path) -> tuple[Path, int]:
    """A synthetic tree with 12 files (4 projects × 3 sessions, 5 events each)."""
    root = tmp_path / "projects"
    n_files = 0
    for p in range(4):
        for s in range(3):
            _write_session(root / f"-Users-test-proj{p}", f"sess-{p}-{s}", 5)
            n_files += 1
    return root, n_files


@pytest.fixture
def fresh_cache(tmp_path: Path) -> CacheManager:
    cache = CacheManager(tmp_path / "cache.db")
    cache.init_schema()
    return cache


# ---------------------------------------------------------------------------
# resolve_wave_size — env var + clamping
# ---------------------------------------------------------------------------


class TestResolveWaveSize:
    def test_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_SESSIONS_WAVE_SIZE", raising=False)
        assert resolve_wave_size() == DEFAULT_WAVE_SIZE

    def test_env_var_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_SESSIONS_WAVE_SIZE", "13")
        assert resolve_wave_size() == 13

    def test_invalid_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_SESSIONS_WAVE_SIZE", "garbage")
        assert resolve_wave_size() == DEFAULT_WAVE_SIZE

    def test_zero_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_SESSIONS_WAVE_SIZE", "0")
        assert resolve_wave_size() == DEFAULT_WAVE_SIZE


# ---------------------------------------------------------------------------
# WavePipeline.run — completion + correctness
# ---------------------------------------------------------------------------


class TestWavePipelineRun:
    def test_processes_all_files_with_small_wave(
        self,
        fresh_cache: CacheManager,
        projects_with_n_files: tuple[Path, int],
    ) -> None:
        proj_root, n_files = projects_with_n_files
        pipeline = WavePipeline(fresh_cache, wave_size=5)
        result = pipeline.run(proj_root)

        # All files were ingested across the waves.
        assert result["files_processed"] == n_files
        # Wave count = ceil(n_files / wave_size).
        assert result["waves_completed"] == (n_files + 4) // 5
        # Cache holds every event.
        events = fresh_cache.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert events == n_files * 5

    def test_single_wave_when_corpus_smaller_than_wave_size(
        self,
        fresh_cache: CacheManager,
        projects_with_n_files: tuple[Path, int],
    ) -> None:
        proj_root, n_files = projects_with_n_files
        pipeline = WavePipeline(fresh_cache, wave_size=1000)
        result = pipeline.run(proj_root)
        assert result["waves_completed"] == 1
        assert result["files_processed"] == n_files

    def test_empty_corpus_completes_with_zero_waves(
        self, fresh_cache: CacheManager, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty-projects"
        empty.mkdir()
        pipeline = WavePipeline(fresh_cache, wave_size=10)
        result = pipeline.run(empty)
        assert result["waves_completed"] == 0
        assert result["files_processed"] == 0

    def test_re_run_is_a_noop(
        self,
        fresh_cache: CacheManager,
        projects_with_n_files: tuple[Path, int],
    ) -> None:
        """Running the pipeline twice over an unchanged corpus must not
        re-ingest anything (mtime/size match means files are skipped)."""
        proj_root, n_files = projects_with_n_files
        pipeline = WavePipeline(fresh_cache, wave_size=5)
        pipeline.run(proj_root)
        result = pipeline.run(proj_root)
        assert result["files_processed"] == 0
        assert result["waves_completed"] == 0


# ---------------------------------------------------------------------------
# Cooperative cancellation via stop event
# ---------------------------------------------------------------------------


class TestWavePipelineStop:
    def test_stop_event_set_before_run_returns_immediately(
        self,
        fresh_cache: CacheManager,
        projects_with_n_files: tuple[Path, int],
    ) -> None:
        proj_root, _ = projects_with_n_files
        stop = threading.Event()
        stop.set()
        pipeline = WavePipeline(fresh_cache, wave_size=2, stop_event=stop)
        result = pipeline.run(proj_root)
        # Stop set before any wave starts → no waves, no files.
        assert result["waves_completed"] == 0
        assert result["files_processed"] == 0

    def test_stop_event_set_mid_run_halts_at_wave_boundary(
        self,
        fresh_cache: CacheManager,
        projects_with_n_files: tuple[Path, int],
    ) -> None:
        """Set the stop event from inside a wave hook — the next wave
        should not start, and the result reflects partial progress."""
        proj_root, n_files = projects_with_n_files
        stop = threading.Event()
        pipeline = WavePipeline(fresh_cache, wave_size=2, stop_event=stop)

        # Hook fires after every wave; flip the stop flag after wave 1.
        wave_count = {"n": 0}

        def _on_wave_done(idx: int, summary: dict[str, int]) -> None:
            wave_count["n"] += 1
            if wave_count["n"] == 1:
                stop.set()

        pipeline.on_wave_done = _on_wave_done
        result = pipeline.run(proj_root)

        # We completed exactly 1 wave (wave size 2) — 2 files, 10 events.
        assert result["waves_completed"] == 1
        assert result["files_processed"] == 2
        events = fresh_cache.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert events == 10
        # And the corpus still has 10 unprocessed files waiting.
        assert n_files - result["files_processed"] == 10


# ---------------------------------------------------------------------------
# Logging — phase banners surface to the configured handler
# ---------------------------------------------------------------------------


class TestWavePipelineLogging:
    def test_emits_per_wave_banner(
        self,
        fresh_cache: CacheManager,
        projects_with_n_files: tuple[Path, int],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        proj_root, _ = projects_with_n_files
        with caplog.at_level("INFO", logger="claude_code_sessions.database.sqlite"):
            pipeline = WavePipeline(fresh_cache, wave_size=4)
            pipeline.run(proj_root)
        # At least one wave banner per wave completed.
        wave_lines = [r for r in caplog.records if "wave" in r.getMessage().lower()]
        assert len(wave_lines) >= 1
