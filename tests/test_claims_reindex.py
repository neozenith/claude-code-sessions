"""CR5 manual reindex — the background job state machine (injected fake runner)."""

from __future__ import annotations

import threading
import time

from claude_code_sessions.claims_reindex import ClaimsReindexManager, ProgressCb


def _wait(manager: ClaimsReindexManager, state: str, timeout: float = 3.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if manager.status()["state"] == state:
            return
        time.sleep(0.01)
    raise AssertionError(f"never reached {state!r}; status={manager.status()}")


def test_runs_and_publishes_progress() -> None:
    m = ClaimsReindexManager()

    def runner(scope: str, grain: str, model: str, limit: int, progress: ProgressCb) -> None:
        progress(sessions_total=2)
        progress(sessions_done=2, rollups_written=5)

    m.start("play", "month", "M", 10, runner)
    _wait(m, "done")
    s = m.status()
    assert s["sessions_total"] == 2 and s["sessions_done"] == 2 and s["rollups_written"] == 5
    assert s["scope_path"] == "play" and s["model"] == "M"


def test_single_flight_ignores_second_start() -> None:
    m = ClaimsReindexManager()
    release = threading.Event()

    def slow(scope: str, grain: str, model: str, limit: int, progress: ProgressCb) -> None:
        release.wait(2)

    m.start("first", "month", "M", 10, slow)
    res = m.start("second", "day", "M2", 10, slow)  # while first still running
    assert res["already_running"] is True
    assert m.status()["scope_path"] == "first"  # not clobbered by the ignored second start
    release.set()
    _wait(m, "done")


def test_runner_exception_becomes_error_state() -> None:
    m = ClaimsReindexManager()

    def boom(scope: str, grain: str, model: str, limit: int, progress: ProgressCb) -> None:
        raise RuntimeError("kaboom")

    m.start("p", "month", "M", 10, boom)
    _wait(m, "error")
    assert "kaboom" in (m.status()["error"] or "")
