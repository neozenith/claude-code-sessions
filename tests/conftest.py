"""Shared test fixtures for claude-code-sessions.

Provides parametrized fixtures for:
- ``db_backend`` — runs tests against both DuckDB and SQLite implementations
- ``project_blocked`` — runs tests with domain blocking on and off

These compose via Cartesian product: a test using both fixtures runs
4 times (2 backends × 2 blocking states).

Usage::

    @pytest.mark.usefixtures("db_backend")
    class TestMyEndpoint:
        def test_domain_guard(self, project_blocked: bool) -> None:
            response = client.get("/api/timeline/events/some-project")
            if project_blocked:
                assert response.status_code == 404
            else:
                assert response.status_code != 404
"""

import pytest

from claude_code_sessions.config import (
    HOME_PROJECTS_PATH,
    PRICING_CSV_PATH,
    PROJECTS_PATH,
    QUERIES_PATH,
)
from claude_code_sessions.database import Database, DuckDBDatabase, SQLiteDatabase
from claude_code_sessions.main import app


# ---------------------------------------------------------------------------
# Session-scoped backend instances (created once, reused across all tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def duckdb_instance() -> DuckDBDatabase:
    """Create a DuckDB database instance once per test session."""
    return DuckDBDatabase(
        queries_path=QUERIES_PATH,
        pricing_csv_path=PRICING_CSV_PATH,
        local_projects_path=PROJECTS_PATH,
        home_projects_path=HOME_PROJECTS_PATH,
    )


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
# Database backend parametrization
# ---------------------------------------------------------------------------


@pytest.fixture(params=["duckdb", "sqlite"])
def db_backend(
    request: pytest.FixtureRequest,
    duckdb_instance: DuckDBDatabase,
    sqlite_instance: SQLiteDatabase,
) -> str:
    """Parametrize a test to run with both database backends.

    Swaps ``app.state.db`` before the test and restores it after.
    Apply to test classes via ``@pytest.mark.usefixtures("db_backend")``.
    """
    backends: dict[str, Database] = {
        "duckdb": duckdb_instance,
        "sqlite": sqlite_instance,
    }
    original: Database = app.state.db
    app.state.db = backends[request.param]
    yield request.param
    app.state.db = original


# ---------------------------------------------------------------------------
# Domain blocking parametrization
# ---------------------------------------------------------------------------

# Every module that does ``from config import is_project_blocked`` creates its
# own local name binding. We must setattr at each binding site so both backends
# see the override regardless of which one is active.
_IS_PROJECT_BLOCKED_TARGETS = [
    "claude_code_sessions.database.duckdb.is_project_blocked",
    "claude_code_sessions.database.sqlite.backend.is_project_blocked",
]


@pytest.fixture(params=[True, False], ids=["blocked", "unblocked"])
def project_blocked(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Parametrize domain blocking state.

    Each test using this fixture runs twice — once with all projects blocked,
    once with none blocked. Combined with ``db_backend``, this gives 4 runs
    per test method (2 backends × 2 blocking states).

    Returns the boolean blocking state so tests can assert conditionally.
    """
    blocked: bool = request.param
    for target in _IS_PROJECT_BLOCKED_TARGETS:
        monkeypatch.setattr(target, lambda _pid, _b=blocked: _b)
    return blocked
