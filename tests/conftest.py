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
from claude_code_sessions.database.sqlite.indexer import IndexerService  # noqa: E402
from claude_code_sessions.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Session-scoped backend instances (created once, reused across all tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def sqlite_instance() -> SQLiteDatabase:
    """Create a SQLite database instance once per test session.

    Construction is now side-effect-free (the FastAPI server delegates
    ingestion to a background thread), so tests that depend on a
    populated cache must call ``ensure_ready()`` explicitly. We do that
    here once per session and reuse the instance across all tests.
    """
    db = SQLiteDatabase(
        local_projects_path=PROJECTS_PATH,
        home_projects_path=HOME_PROJECTS_PATH,
    )
    db.ensure_ready()
    return db


@pytest.fixture(scope="session", autouse=True)
def _install_app_state(sqlite_instance: SQLiteDatabase):
    """Install ``app.state.db`` and ``app.state.indexer`` for the whole
    test session.

    The FastAPI lifespan only sets these fields when the server actually
    runs. Tests that hit the app via ``TestClient(app)`` without
    entering the lifespan context need the state pre-installed. We
    use the session-scoped sqlite_instance (already populated) and a
    fresh IndexerService that we never ``start()`` — its ``.status()``
    returns the idle dict, which is exactly what the /api/health
    endpoint expects.
    """
    app.state.db = sqlite_instance
    app.state.indexer = IndexerService(sqlite_instance)
    yield
    # Keep the session-wide state in place after the yield — there's no
    # cleanup to do, and other session-scoped consumers may still be
    # tearing down.


# ---------------------------------------------------------------------------
# Database backend fixture (SQLite only — DuckDB was removed)
# ---------------------------------------------------------------------------


@pytest.fixture(params=["sqlite"])
def db_backend(
    request: pytest.FixtureRequest,
    sqlite_instance: SQLiteDatabase,
):
    """Install the SQLite backend on ``app.state.db`` for the duration of
    the test. The ``params=["sqlite"]`` is retained so the test IDs carry
    an explicit ``[sqlite]`` suffix, matching historical convention.

    With the FastAPI lifespan owning startup, ``app.state.db`` is no
    longer set at module load — it's installed inside the lifespan
    context. Tests that exercise the API directly (without going
    through TestClient) need this fixture to set up state explicitly.
    We tolerate the attribute being absent by falling back to ``None``
    so the post-test restore is a delete instead of an assignment.
    """
    sentinel = object()
    original: Database | object = getattr(app.state, "db", sentinel)
    app.state.db = sqlite_instance
    yield request.param
    if original is sentinel:
        del app.state.db
    else:
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
