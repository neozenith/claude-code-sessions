"""Shared test fixtures for claude-code-sessions.

Provides parametrized fixtures for:
- ``db_backend`` — installs the SQLite backend on ``app.state.db`` for the
  test. Historically this parametrized over both DuckDB and SQLite; the
  DuckDB backend has been removed, but the fixture name is kept so
  existing test classes using ``@pytest.mark.usefixtures("db_backend")``
  keep working.
- ``project_blocked`` — runs tests with domain blocking on and off.

Tests must never trigger the embedding sync: it downloads a ~150 MB
GGUF model and runs for minutes against a real corpus. We set the
disable flag before importing anything that could construct a
CacheManager.
"""

import os

# Must be set BEFORE importing claude_code_sessions — CacheManager.update()
# reads this env var when it decides whether to run embeddings.
os.environ.setdefault("CLAUDE_SESSIONS_DISABLE_EMBEDDINGS", "1")
# Same test-isolation rationale for the knowledge-graph phase: it
# downloads a multi-GiB chat GGUF on first run and would dominate the
# runtime of any unit test that touches CacheManager.update().
os.environ.setdefault("CLAUDE_SESSIONS_DISABLE_KG", "1")

import pytest  # noqa: E402

from claude_code_sessions.config import (  # noqa: E402
    HOME_PROJECTS_PATH,
    PROJECTS_PATH,
)
from claude_code_sessions.database import Database, SQLiteDatabase  # noqa: E402
from claude_code_sessions.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Session-scoped backend instances (created once, reused across all tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sqlite_instance() -> SQLiteDatabase:
    """Create a SQLite database instance once per test session.

    The constructor calls ``ensure_ready()`` which builds/updates the cache
    from JSONL files. This runs once and is reused across all tests.
    """
    return SQLiteDatabase(
        local_projects_path=PROJECTS_PATH,
        home_projects_path=HOME_PROJECTS_PATH,
    )


# ---------------------------------------------------------------------------
# Database backend fixture (SQLite only — DuckDB was removed)
# ---------------------------------------------------------------------------


@pytest.fixture(params=["sqlite"])
def db_backend(
    request: pytest.FixtureRequest,
    sqlite_instance: SQLiteDatabase,
) -> str:
    """Install the SQLite backend on ``app.state.db`` for the duration of
    the test. The ``params=["sqlite"]`` is retained so the test IDs carry
    an explicit ``[sqlite]`` suffix, matching historical convention.
    """
    original: Database = app.state.db
    app.state.db = sqlite_instance
    yield request.param
    app.state.db = original


# ---------------------------------------------------------------------------
# Domain blocking parametrization
# ---------------------------------------------------------------------------

_IS_PROJECT_BLOCKED_TARGETS = [
    "claude_code_sessions.database.sqlite.backend.is_project_blocked",
]


@pytest.fixture(params=[True, False], ids=["blocked", "unblocked"])
def project_blocked(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Parametrize domain blocking state.

    Returns the boolean blocking state so tests can assert conditionally.
    """
    blocked: bool = request.param
    for target in _IS_PROJECT_BLOCKED_TARGETS:
        monkeypatch.setattr(target, lambda _pid, _b=blocked: _b)
    return blocked
