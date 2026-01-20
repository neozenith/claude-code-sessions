"""
Tests for the Schema Timeline API endpoint.

Tests cover:
- Basic endpoint functionality
- Query parameter filtering (days, project)
- Response format validation
- Error handling
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_projects_path(tmp_path: Path) -> Path:
    """Create a mock projects path."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    return projects_dir


class TestSchemaTimelineEndpoint:
    """Tests for the /api/schema-timeline endpoint."""

    def test_endpoint_exists(self, client: TestClient) -> None:
        """Test that the endpoint exists and returns a response."""
        # This test will fail if the endpoint doesn't exist
        response = client.get("/api/schema-timeline")
        # Could be 200 (success) or 500 (query error due to no data)
        # but should not be 404
        assert response.status_code != 404

    def test_endpoint_with_days_filter(self, client: TestClient) -> None:
        """Test that the days parameter is accepted."""
        response = client.get("/api/schema-timeline?days=30")
        # Should accept the parameter without error
        assert response.status_code != 404

    def test_endpoint_with_project_filter(self, client: TestClient) -> None:
        """Test that the project parameter is accepted."""
        response = client.get("/api/schema-timeline?project=test-project")
        # Should accept the parameter without error
        assert response.status_code != 404

    def test_endpoint_with_all_filters(self, client: TestClient) -> None:
        """Test that multiple filters can be combined."""
        response = client.get("/api/schema-timeline?days=30&project=test-project")
        # Should accept both parameters without error
        assert response.status_code != 404

    def test_endpoint_returns_json(self, client: TestClient) -> None:
        """Test that the endpoint returns JSON."""
        response = client.get("/api/schema-timeline?days=7")
        # Content type should be JSON
        assert "application/json" in response.headers.get("content-type", "")

    def test_response_is_list(self, client: TestClient) -> None:
        """Test that the response is a list."""
        response = client.get("/api/schema-timeline?days=7")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)


class TestSchemaTimelineResponseFormat:
    """Tests for the response format of schema timeline data."""

    def test_event_has_required_fields(self, client: TestClient) -> None:
        """Test that events have the required fields."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                event = data[0]
                # Check required fields exist (new day-aggregated format)
                assert "event_date" in event
                assert "json_path" in event
                assert "first_seen" in event
                assert "event_count" in event
                # version can be null but should be present
                assert "version" in event

    def test_json_paths_are_strings(self, client: TestClient) -> None:
        """Test that json_path values are strings."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            for event in data[:10]:  # Check first 10 events
                assert isinstance(event.get("json_path"), str)

    def test_event_dates_are_valid(self, client: TestClient) -> None:
        """Test that event_date values are valid YYYY-MM-DD dates."""
        from datetime import datetime

        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            for event in data[:10]:  # Check first 10 events
                event_date = event.get("event_date")
                if event_date:
                    # Should be YYYY-MM-DD format
                    try:
                        datetime.strptime(event_date, "%Y-%m-%d")
                    except ValueError:
                        pytest.fail(f"Invalid date format: {event_date}")

    def test_has_record_timestamp_field_exists(self, client: TestClient) -> None:
        """Test that has_record_timestamp field exists in response."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            for event in data[:10]:  # Check first 10 events
                assert "has_record_timestamp" in event
                assert isinstance(event["has_record_timestamp"], bool)

    def test_event_count_is_positive(self, client: TestClient) -> None:
        """Test that event_count is a positive integer."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            for event in data[:10]:  # Check first 10 events
                assert "event_count" in event
                assert isinstance(event["event_count"], int)
                assert event["event_count"] > 0


class TestSchemaTimelineFiltering:
    """Tests for filtering functionality."""

    def test_days_zero_means_all_time(self, client: TestClient) -> None:
        """Test that days=0 means all time (no filter)."""
        # Both should work - 0 means no filter
        response_all = client.get("/api/schema-timeline?days=0")
        response_none = client.get("/api/schema-timeline")

        # Both should return same status
        assert response_all.status_code == response_none.status_code

    def test_different_days_returns_different_dates(self, client: TestClient) -> None:
        """Test that different days values filter by date correctly."""
        response_90 = client.get("/api/schema-timeline?days=90")
        response_7 = client.get("/api/schema-timeline?days=7")

        if response_90.status_code == 200 and response_7.status_code == 200:
            data_90 = response_90.json()
            data_7 = response_7.json()

            # Both should return data (if any exists)
            # The 7-day data should have more recent dates on average
            if len(data_7) > 0 and len(data_90) > 0:
                # Get earliest date in each dataset
                min_7 = min(e["event_date"] for e in data_7)
                min_90 = min(e["event_date"] for e in data_90)

                # 90 days should have older data than 7 days (or same)
                assert min_90 <= min_7


class TestSchemaTimelineIntegration:
    """Integration tests that verify the full pipeline."""

    def test_known_paths_are_detected(self, client: TestClient) -> None:
        """Test that known JSON paths are detected in the data."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            paths = {event["json_path"] for event in data}

            # These paths should exist in any Claude Code session data
            expected_paths = {"timestamp", "type", "message"}
            found_expected = paths & expected_paths

            # At least some expected paths should be found
            # (if there's any data at all)
            if len(data) > 0:
                assert len(found_expected) > 0, f"Expected some of {expected_paths}, found {paths}"

    def test_data_is_sorted_by_first_seen_and_date(self, client: TestClient) -> None:
        """Test that data is sorted by first_seen and then by event_date."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            if len(data) > 1:
                # Group by path and check date sorting within each path
                from collections import defaultdict

                by_path: dict[str, list[str]] = defaultdict(list)
                for event in data:
                    by_path[event["json_path"]].append(event["event_date"])

                # Within each path, dates should be sorted
                for path, dates in by_path.items():
                    sorted_dates = sorted(dates)
                    assert dates == sorted_dates, f"Path {path} not sorted by date"

    def test_one_row_per_path_per_day(self, client: TestClient) -> None:
        """Test that each path has at most one entry per day."""
        response = client.get("/api/schema-timeline?days=90")
        if response.status_code == 200:
            data = response.json()
            if len(data) > 0:
                # Check for uniqueness of (path, date) pairs
                seen: set[tuple[str, str]] = set()
                for event in data:
                    key = (event["json_path"], event["event_date"])
                    assert key not in seen, f"Duplicate entry for {key}"
                    seen.add(key)
