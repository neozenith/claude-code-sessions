"""
Comprehensive tests for API filter support.

Tests all endpoints with:
- No filters (all time, all projects)
- Days filter only
- Project filter only
- Both filters combined
- Edge cases

API endpoint tests are parametrized via ``db_backend`` fixture to run
against both the DuckDB and SQLite backends.
"""

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.config import (
    HOME_PROJECTS_PATH,
    PRICING_CSV_PATH,
    PROJECTS_PATH,
    QUERIES_PATH,
)
from claude_code_sessions.database import DuckDBDatabase
from claude_code_sessions.database.sqlite.filters import days_clause, domain_clause, project_clause
from claude_code_sessions.main import app

client = TestClient(app)


# Test data - use a known project ID from the test data
# This is the current project which should have recent activity
TEST_PROJECT_ID = "-Users-joshpeak-play-claude-code-sessions"

# DuckDB instance for testing internal helpers directly
_duckdb = DuckDBDatabase(
    queries_path=QUERIES_PATH,
    pricing_csv_path=PRICING_CSV_PATH,
    local_projects_path=PROJECTS_PATH,
    home_projects_path=HOME_PROJECTS_PATH,
)


class TestBuildFilters:
    """Test the _build_filters helper on the DuckDB Database implementation."""

    def test_no_filters(self) -> None:
        """_build_filters with no args returns empty strings."""
        filters = _duckdb._build_filters()
        assert filters["DAYS_FILTER"] == ""
        assert filters["PROJECT_FILTER"] == ""

    def test_days_filter_only(self) -> None:
        """_build_filters with days returns proper SQL clause."""
        filters = _duckdb._build_filters(days=7)
        assert "7 days" in filters["DAYS_FILTER"]
        assert "INTERVAL" in filters["DAYS_FILTER"]
        assert filters["PROJECT_FILTER"] == ""

    def test_project_filter_only(self) -> None:
        """_build_filters with project returns proper SQL clause."""
        filters = _duckdb._build_filters(project="test-project")
        assert filters["DAYS_FILTER"] == ""
        assert "test-project" in filters["PROJECT_FILTER"]
        assert "regexp_extract" in filters["PROJECT_FILTER"]

    def test_both_filters(self) -> None:
        """_build_filters with both args returns both clauses."""
        filters = _duckdb._build_filters(days=30, project="my-project")
        assert "30 days" in filters["DAYS_FILTER"]
        assert "my-project" in filters["PROJECT_FILTER"]

    def test_days_zero_means_all_time(self) -> None:
        """_build_filters with days=0 returns empty days filter."""
        filters = _duckdb._build_filters(days=0)
        assert filters["DAYS_FILTER"] == ""

    def test_sql_injection_prevention(self) -> None:
        """_build_filters escapes single quotes in project ID."""
        filters = _duckdb._build_filters(project="test'; DROP TABLE users; --")
        assert "''" in filters["PROJECT_FILTER"]
        assert "= 'test';" not in filters["PROJECT_FILTER"]


class TestSQLiteBuildFilters:
    """Test the SQLite filter clause builders."""

    def test_days_clause_empty_when_none(self) -> None:
        """No days produces empty clause."""
        assert days_clause(None) == ""

    def test_days_clause_empty_when_zero(self) -> None:
        """days=0 produces empty clause."""
        assert days_clause(0) == ""

    def test_days_clause_empty_when_negative(self) -> None:
        """Negative days produces empty clause."""
        assert days_clause(-5) == ""

    def test_days_clause_with_value(self) -> None:
        """Positive days produces proper SQLite datetime clause."""
        result = days_clause(7)
        assert "datetime('now', '-7 days')" in result
        assert result.startswith("AND ")

    def test_days_clause_custom_column(self) -> None:
        """Custom column name is used in the clause."""
        result = days_clause(30, col="s.last_timestamp")
        assert "s.last_timestamp" in result

    def test_project_clause_empty_when_none(self) -> None:
        """No project produces empty clause."""
        assert project_clause(None) == ""

    def test_project_clause_with_value(self) -> None:
        """Project ID produces proper equality clause."""
        result = project_clause("my-project")
        assert "my-project" in result
        assert result.startswith("AND ")

    def test_project_clause_sql_injection_prevention(self) -> None:
        """Single quotes are escaped to prevent SQL injection."""
        result = project_clause("test'; DROP TABLE users; --")
        assert "''" in result
        assert "= 'test';" not in result

    def test_project_clause_custom_column(self) -> None:
        """Custom column name is used in the clause."""
        result = project_clause("proj", col="s.project_id")
        assert "s.project_id" in result

    def test_domain_clause_empty_when_no_blocked(self) -> None:
        """No blocked domains produces empty clause."""
        # domain_clause reads BLOCKED_DOMAINS at call time; if empty, returns ""
        # This test relies on the test environment having no blocked domains
        # (the default for dev/CI). If it fails, BLOCKED_DOMAINS is non-empty.
        from claude_code_sessions.config import BLOCKED_DOMAINS

        if not BLOCKED_DOMAINS:
            result = domain_clause(PROJECTS_PATH)
            assert result == ""


@pytest.mark.usefixtures("db_backend")
class TestSummaryEndpoint:
    """Test GET /api/summary endpoint."""

    def test_summary_no_filters(self) -> None:
        """Summary returns data with no filters."""
        response = client.get("/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "grand_total_cost_usd" in data[0]

    def test_summary_days_filter(self) -> None:
        """Summary returns data with days filter."""
        response = client.get("/api/summary?days=7")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_summary_project_filter(self) -> None:
        """Summary returns data with project filter."""
        response = client.get(f"/api/summary?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_summary_both_filters(self) -> None:
        """Summary returns data with both filters."""
        response = client.get(f"/api/summary?days=30&project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_summary_days_zero(self) -> None:
        """Summary with days=0 returns all time data."""
        response = client.get("/api/summary?days=0")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestDailyUsageEndpoint:
    """Test GET /api/usage/daily endpoint."""

    def test_daily_no_filters(self) -> None:
        """Daily returns data with no filters."""
        response = client.get("/api/usage/daily")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_daily_days_filter(self) -> None:
        """Daily returns data with days filter."""
        response = client.get("/api/usage/daily?days=7")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_daily_project_filter(self) -> None:
        """Daily returns data with project filter."""
        response = client.get(f"/api/usage/daily?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for row in data:
            assert row.get("project_id") == TEST_PROJECT_ID

    def test_daily_both_filters(self) -> None:
        """Daily returns data with both filters."""
        response = client.get(f"/api/usage/daily?days=30&project={TEST_PROJECT_ID}")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestWeeklyUsageEndpoint:
    """Test GET /api/usage/weekly endpoint."""

    def test_weekly_no_filters(self) -> None:
        """Weekly returns data with no filters."""
        response = client.get("/api/usage/weekly")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_weekly_days_filter(self) -> None:
        """Weekly returns data with days filter."""
        response = client.get("/api/usage/weekly?days=30")
        assert response.status_code == 200

    def test_weekly_project_filter(self) -> None:
        """Weekly returns data with project filter."""
        response = client.get(f"/api/usage/weekly?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        for row in data:
            assert row.get("project_id") == TEST_PROJECT_ID

    def test_weekly_both_filters(self) -> None:
        """Weekly returns data with both filters."""
        response = client.get(f"/api/usage/weekly?days=90&project={TEST_PROJECT_ID}")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestMonthlyUsageEndpoint:
    """Test GET /api/usage/monthly endpoint."""

    def test_monthly_no_filters(self) -> None:
        """Monthly returns data with no filters."""
        response = client.get("/api/usage/monthly")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_monthly_days_filter(self) -> None:
        """Monthly returns data with days filter."""
        response = client.get("/api/usage/monthly?days=90")
        assert response.status_code == 200

    def test_monthly_project_filter(self) -> None:
        """Monthly returns data with project filter."""
        response = client.get(f"/api/usage/monthly?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        for row in data:
            assert row.get("project_id") == TEST_PROJECT_ID

    def test_monthly_both_filters(self) -> None:
        """Monthly returns data with both filters."""
        response = client.get(f"/api/usage/monthly?days=180&project={TEST_PROJECT_ID}")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestHourlyUsageEndpoint:
    """Test GET /api/usage/hourly endpoint."""

    def test_hourly_no_filters(self) -> None:
        """Hourly returns data with no filters."""
        response = client.get("/api/usage/hourly")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_hourly_days_filter(self) -> None:
        """Hourly returns data with days filter."""
        response = client.get("/api/usage/hourly?days=14")
        assert response.status_code == 200

    def test_hourly_project_filter(self) -> None:
        """Hourly returns data with project filter."""
        response = client.get(f"/api/usage/hourly?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        for row in data:
            assert row.get("project_id") == TEST_PROJECT_ID

    def test_hourly_both_filters(self) -> None:
        """Hourly returns data with both filters."""
        response = client.get(f"/api/usage/hourly?days=7&project={TEST_PROJECT_ID}")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestSessionsEndpoint:
    """Test GET /api/usage/sessions endpoint."""

    def test_sessions_no_filters(self) -> None:
        """Sessions returns data with no filters."""
        response = client.get("/api/usage/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_sessions_days_filter(self) -> None:
        """Sessions returns data with days filter."""
        response = client.get("/api/usage/sessions?days=7")
        assert response.status_code == 200

    def test_sessions_project_filter(self) -> None:
        """Sessions returns data with project filter."""
        response = client.get(f"/api/usage/sessions?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        for row in data:
            assert row.get("project_id") == TEST_PROJECT_ID

    def test_sessions_both_filters(self) -> None:
        """Sessions returns data with both filters."""
        response = client.get(f"/api/usage/sessions?days=30&project={TEST_PROJECT_ID}")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestProjectsEndpoint:
    """Test GET /api/projects endpoint."""

    def test_projects_no_filters(self) -> None:
        """Projects returns list with no filters."""
        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        for project in data:
            assert "project_id" in project
            assert "total_cost_usd" in project
            assert "session_count" in project
            assert "event_count" in project

    def test_projects_days_filter(self) -> None:
        """Projects returns filtered list with days parameter."""
        response = client.get("/api/projects?days=7")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_projects_days_zero(self) -> None:
        """Projects with days=0 returns all time data."""
        response = client.get("/api/projects?days=0")
        assert response.status_code == 200

    def test_projects_sorted_by_cost(self) -> None:
        """Projects are sorted by cost (highest first)."""
        response = client.get("/api/projects")
        assert response.status_code == 200
        data = response.json()
        costs = [p["total_cost_usd"] for p in data]
        assert costs == sorted(costs, reverse=True)


@pytest.mark.usefixtures("db_backend")
class TestTopProjectsWeeklyEndpoint:
    """Test GET /api/usage/top-projects-weekly endpoint."""

    def test_top_projects_no_filters(self) -> None:
        """Top projects returns data with default 56 days."""
        response = client.get("/api/usage/top-projects-weekly")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_top_projects_days_filter(self) -> None:
        """Top projects returns data with days filter."""
        response = client.get("/api/usage/top-projects-weekly?days=30")
        assert response.status_code == 200


class TestSchemaTimelineEndpoint:
    """Test GET /api/schema-timeline endpoint.

    Not parametrized — schema timeline is a DuckDB-specific feature.
    The SQLite backend returns [] for this endpoint.
    """

    def test_schema_timeline_no_filters(self) -> None:
        """Schema timeline returns data with no filters."""
        response = client.get("/api/schema-timeline")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_schema_timeline_days_filter(self) -> None:
        """Schema timeline returns data with days filter."""
        response = client.get("/api/schema-timeline?days=30")
        assert response.status_code == 200

    def test_schema_timeline_project_filter(self) -> None:
        """Schema timeline returns data with project filter."""
        response = client.get(f"/api/schema-timeline?project={TEST_PROJECT_ID}")
        assert response.status_code == 200

    def test_schema_timeline_both_filters(self) -> None:
        """Schema timeline returns data with both filters."""
        response = client.get(f"/api/schema-timeline?days=90&project={TEST_PROJECT_ID}")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestTimelineEventsEndpoint:
    """Test GET /api/timeline/events/{project_id} endpoint."""

    def test_timeline_events_with_project(self) -> None:
        """Timeline events returns data for a project."""
        response = client.get(f"/api/timeline/events/{TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_timeline_events_with_days(self) -> None:
        """Timeline events returns data with days filter."""
        response = client.get(f"/api/timeline/events/{TEST_PROJECT_ID}?days=7")
        assert response.status_code == 200


@pytest.mark.usefixtures("db_backend")
class TestFilterConsistency:
    """Test that filters are applied consistently across endpoints."""

    def test_project_filter_reduces_results(self) -> None:
        """Project filter should reduce or equal results vs no filter."""
        all_response = client.get("/api/usage/daily")
        all_data = all_response.json()
        filtered_response = client.get(f"/api/usage/daily?project={TEST_PROJECT_ID}")
        filtered_data = filtered_response.json()
        assert len(filtered_data) <= len(all_data)

    def test_days_filter_reduces_results(self) -> None:
        """Days filter should reduce or equal results vs all time."""
        all_response = client.get("/api/usage/daily?days=0")
        all_data = all_response.json()
        filtered_response = client.get("/api/usage/daily?days=7")
        filtered_data = filtered_response.json()
        assert len(filtered_data) <= len(all_data)

    def test_combined_filters_reduce_more(self) -> None:
        """Combined filters should reduce results further."""
        days_response = client.get("/api/usage/daily?days=30")
        days_data = days_response.json()
        combined_response = client.get(f"/api/usage/daily?days=30&project={TEST_PROJECT_ID}")
        combined_data = combined_response.json()
        assert len(combined_data) <= len(days_data)


@pytest.mark.usefixtures("db_backend")
class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_invalid_project_returns_empty(self) -> None:
        """Invalid project ID returns empty results, not error."""
        response = client.get("/api/usage/daily?project=nonexistent-project-xyz")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_negative_days_treated_as_no_filter(self) -> None:
        """Negative days value is handled gracefully."""
        response = client.get("/api/usage/daily?days=-1")
        assert response.status_code == 200

    def test_very_large_days_value(self) -> None:
        """Very large days value works (all time equivalent)."""
        response = client.get("/api/usage/daily?days=10000")
        assert response.status_code == 200

    def test_special_characters_in_project(self) -> None:
        """Special characters in project ID are handled."""
        response = client.get("/api/usage/daily?project=test%2Fproject")
        assert response.status_code == 200
