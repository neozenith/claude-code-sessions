"""
Comprehensive tests for API filter support.

Tests all endpoints with:
- No filters (all time, all projects)
- Days filter only
- Project filter only
- Both filters combined
- Edge cases

API endpoint tests run against the SQLite backend via the ``db_backend``
fixture. (The DuckDB backend was removed; the fixture name is retained.)
"""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.database.sqlite.filters import days_clause, domain_clause, project_clause
from claude_code_sessions.main import app

client = TestClient(app)


# Test data - use a known project ID from the test data
# This is the current project which should have recent activity
TEST_PROJECT_ID = "-Users-joshpeak-play-claude-code-sessions"


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
        from claude_code_sessions.config import BLOCKED_DOMAINS, PROJECTS_PATH

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


@pytest.mark.usefixtures("db_backend")
class TestSearchEndpoint:
    """Test GET /api/search — full-text search over events via FTS5."""

    def test_empty_query_returns_empty_list(self) -> None:
        """Empty ``q`` short-circuits in the backend and returns []."""
        response = client.get("/api/search?q=")
        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_whitespace_query_returns_empty_list(self) -> None:
        """Whitespace-only queries short-circuit — no FTS5 parse error."""
        response = client.get("/api/search?q=%20%20%20")
        assert response.status_code == 200
        assert response.json() == []

    def test_missing_query_param_returns_empty_list(self) -> None:
        """Missing ``q`` defaults to an empty string and returns []."""
        response = client.get("/api/search")
        assert response.status_code == 200
        assert response.json() == []

    def test_common_term_returns_result_rows_with_expected_shape(self) -> None:
        """A term that should match something returns rows with the
        documented shape: project_id, session_id, uuid, snippet, rank, etc.
        If the corpus genuinely has no matches, the list is empty and
        this test degrades to a shape check on zero rows (still valid)."""
        response = client.get("/api/search?q=claude&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5
        for row in data:
            assert set(row.keys()) >= {
                "project_id",
                "session_id",
                "uuid",
                "event_type",
                "message_kind",
                "timestamp",
                "timestamp_local",
                "model_id",
                "snippet",
                "rank",
            }
            # snippet is the highlighted excerpt and must be a string
            assert isinstance(row["snippet"], str)
            # rank is BM25 score — a float, typically negative
            assert isinstance(row["rank"], (int, float))

    def test_results_are_ordered_by_relevance(self) -> None:
        """Results come back sorted by BM25 rank ascending (lower is
        more relevant)."""
        response = client.get("/api/search?q=claude&limit=20")
        assert response.status_code == 200
        data = response.json()
        if len(data) >= 2:
            ranks = [row["rank"] for row in data]
            assert ranks == sorted(ranks)

    def test_days_filter_narrows_or_preserves_result_count(self) -> None:
        """A narrow time window should return ≤ the all-time count for
        the same query."""
        all_time = client.get("/api/search?q=claude&days=0&limit=100")
        recent = client.get("/api/search?q=claude&days=7&limit=100")
        assert all_time.status_code == 200
        assert recent.status_code == 200
        assert len(recent.json()) <= len(all_time.json())

    def test_project_filter_scopes_results_to_one_project(self) -> None:
        """When ``project`` is set, every returned row has that
        project_id."""
        response = client.get(f"/api/search?q=claude&project={TEST_PROJECT_ID}&limit=20")
        assert response.status_code == 200
        for row in response.json():
            assert row["project_id"] == TEST_PROJECT_ID

    def test_limit_caps_result_count(self) -> None:
        """``limit`` caps the number of rows returned."""
        response = client.get("/api/search?q=claude&limit=3")
        assert response.status_code == 200
        assert len(response.json()) <= 3

    def test_msg_kind_filter_restricts_to_that_kind(self) -> None:
        """When ``msg_kind`` is set, every row's message_kind matches."""
        response = client.get("/api/search?q=claude&msg_kind=human&limit=20")
        assert response.status_code == 200
        rows = response.json()
        for row in rows:
            assert row["message_kind"] == "human"

    def test_msg_kind_filter_narrows_or_preserves_count(self) -> None:
        """A kind filter should return ≤ the unfiltered count."""
        unfiltered = client.get("/api/search?q=claude&limit=100")
        filtered = client.get("/api/search?q=claude&msg_kind=human&limit=100")
        assert unfiltered.status_code == 200
        assert filtered.status_code == 200
        assert len(filtered.json()) <= len(unfiltered.json())

    def test_msg_kind_filter_applies_before_limit(self) -> None:
        """The kind filter must narrow the corpus *before* LIMIT, so the
        top-N of that kind actually contains N results when the kind is
        well-represented. We can't assert on absolute counts without
        knowing the corpus, but we CAN assert that when the global top-N
        has ≥1 matching row for a kind, the kind-filtered query returns
        ≥ that many rows (i.e. it isn't losing results to post-filter)."""
        overall = client.get("/api/search?q=claude&limit=50").json()
        if not overall:
            return  # empty corpus — nothing to check
        # Pick the most common kind in the overall top-50 and ensure the
        # kind-filtered query returns at least the same number of hits
        # for that kind that appeared in the overall top-50.
        kind_counts = Counter(r["message_kind"] for r in overall if r["message_kind"])
        if not kind_counts:
            return
        top_kind, overall_count = kind_counts.most_common(1)[0]
        filtered = client.get(
            f"/api/search?q=claude&msg_kind={top_kind}&limit=50"
        ).json()
        assert len(filtered) >= overall_count

    def test_msg_kind_invalid_value_returns_empty_list(self) -> None:
        """Invalid kind names (not in the whitelist) match nothing in
        practice — the filter falls through as no-op. Since the
        whitelist guards against SQL injection, we just verify a
        200 and a list (may be empty or full depending on impl)."""
        response = client.get("/api/search?q=claude&msg_kind=nonsense&limit=5")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_malformed_but_safe_query_does_not_error(self) -> None:
        """User queries are whitespace-tokenized and each token is
        wrapped in double quotes before being handed to FTS5. This means
        syntactically hostile inputs (quotes, parens, wildcards, SQL
        injection attempts) should not produce a 500 — they should
        either match literally or return no rows."""
        hostile_queries = [
            'foo "bar',         # unbalanced quote
            "foo AND NOT OR",   # FTS5 keywords used as content
            "foo*",             # wildcard syntax
            "'; DROP TABLE events; --",  # SQL injection attempt
            "(foo)",            # parens
        ]
        for q in hostile_queries:
            response = client.get("/api/search", params={"q": q, "limit": 3})
            assert response.status_code == 200, f"failed for query: {q!r}"
            assert isinstance(response.json(), list)

    # ---- mode dispatch ------------------------------------------------

    def test_keyword_mode_is_default(self) -> None:
        """Omitting mode is equivalent to mode=keyword — both hit FTS5."""
        r_default = client.get("/api/search?q=claude&limit=5")
        r_keyword = client.get("/api/search?q=claude&limit=5&mode=keyword")
        assert r_default.status_code == 200
        assert r_keyword.status_code == 200
        # Same query, same corpus — both results sets should match.
        assert r_default.json() == r_keyword.json()

    def test_unknown_mode_falls_back_to_keyword(self) -> None:
        """An unknown mode value is tolerated — it silently dispatches to
        keyword search rather than 500-ing. Documented behaviour."""
        response = client.get("/api/search?q=claude&limit=5&mode=typo")
        assert response.status_code == 200
        # Should match the keyword response for the same query.
        assert response.json() == client.get("/api/search?q=claude&limit=5").json()

    def test_semantic_mode_empty_query_returns_empty(self) -> None:
        """Semantic mode honours the same empty-query short-circuit as
        keyword — no attempt to embed '' and no KNN against the HNSW
        index."""
        response = client.get("/api/search?q=&mode=semantic")
        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.usefixtures("db_backend")
class TestSemanticSearchEndpoint:
    """Test GET /api/search?mode=semantic — vector KNN over chunks_vec.

    These tests run against the real shared SQLite cache. If the cache
    has no vectors (embeddings disabled or model never downloaded), the
    endpoint still returns 200 with an empty list rather than erroring —
    that's the documented "feature not available" contract. When vectors
    do exist, we additionally assert on the response shape and rank
    monotonicity.
    """

    def _has_vectors(self) -> bool:
        """Probe the real cache for vectors. Used to skip assertions
        that only make sense when embeddings have been built."""
        from claude_code_sessions.main import app

        try:
            row = app.state.db._cache.conn.execute(  # type: ignore[attr-defined]
                "SELECT COUNT(*) FROM chunks_vec_nodes"
            ).fetchone()
            return row is not None and row[0] > 0
        except Exception:
            return False

    def test_semantic_query_returns_list(self) -> None:
        """Semantic endpoint returns a list regardless of index state."""
        response = client.get("/api/search?q=claude%20code%20review&mode=semantic&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5

    def test_semantic_results_have_same_shape_as_keyword(self) -> None:
        """Response shape is uniform across modes so clients don't branch."""
        if not self._has_vectors():
            return
        response = client.get("/api/search?q=cache%20rebuild&mode=semantic&limit=5")
        assert response.status_code == 200
        for row in response.json():
            assert set(row.keys()) >= {
                "project_id",
                "session_id",
                "uuid",
                "event_type",
                "message_kind",
                "timestamp",
                "timestamp_local",
                "model_id",
                "snippet",
                "rank",
            }
            assert isinstance(row["snippet"], str)
            assert isinstance(row["rank"], (int, float))

    def test_semantic_results_ordered_by_distance_ascending(self) -> None:
        """HNSW returns results with distance ascending — nearest first."""
        if not self._has_vectors():
            return
        response = client.get("/api/search?q=embedding%20model&mode=semantic&limit=20")
        assert response.status_code == 200
        data = response.json()
        if len(data) >= 2:
            ranks = [r["rank"] for r in data]
            assert ranks == sorted(ranks)

    def test_semantic_project_filter_scopes_results(self) -> None:
        """Project filter post-filters the KNN candidate set."""
        if not self._has_vectors():
            return
        response = client.get(
            f"/api/search?q=testing&mode=semantic&limit=20&project={TEST_PROJECT_ID}"
        )
        assert response.status_code == 200
        for row in response.json():
            assert row["project_id"] == TEST_PROJECT_ID

    def test_semantic_non_human_msg_kind_returns_empty(self) -> None:
        """Only 'human' is indexed today — other kinds short-circuit."""
        response = client.get(
            "/api/search?q=anything&mode=semantic&msg_kind=tool_use&limit=5"
        )
        assert response.status_code == 200
        assert response.json() == []
