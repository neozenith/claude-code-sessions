"""
Tests for the Timeline endpoint.

Tests cover:
- Timeline events endpoint returns proper structure
- Filtering by project_id works correctly
- Events are ordered correctly for timeline visualization

Note: These are integration tests that require actual projects data.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from claude_code_sessions.main import app

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def test_client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


# =============================================================================
# Tests: Timeline Endpoint
# =============================================================================


class TestTimelineEndpoint:
    """Tests for the /api/timeline/events/{project_id} endpoint."""

    def test_timeline_events_returns_list(self, test_client: TestClient) -> None:
        """Test that the endpoint returns a list (even if empty)."""
        # Use a made-up project ID - should return empty list, not error
        response = test_client.get("/api/timeline/events/-fake-test-project")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Empty list is valid for non-existent project
        assert data == []

    def test_timeline_events_with_real_project(self, test_client: TestClient) -> None:
        """Test timeline with a real project from the hourly API."""
        # First get a real project ID from hourly API
        hourly_response = test_client.get("/api/usage/hourly?days=7")
        if hourly_response.status_code != 200:
            pytest.skip("Could not fetch hourly data to get project IDs")

        hourly_data = hourly_response.json()
        if not hourly_data:
            pytest.skip("No hourly data available - no projects to test")

        # Get first project ID
        project_id = hourly_data[0].get("project_id")
        if not project_id:
            pytest.skip("No project_id in hourly data")

        # Now test timeline endpoint
        response = test_client.get(f"/api/timeline/events/{project_id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestTimelineEventStructure:
    """Tests for the structure of timeline event data."""

    def test_event_has_required_fields(self, test_client: TestClient) -> None:
        """Test that events have all required fields for timeline visualization."""
        # First get a real project ID
        hourly_response = test_client.get("/api/usage/hourly?days=30")
        hourly_data = hourly_response.json()
        if not hourly_data:
            pytest.skip("No hourly data available")

        project_id = hourly_data[0].get("project_id")

        response = test_client.get(f"/api/timeline/events/{project_id}")
        data = response.json()

        if not data:
            pytest.skip("No timeline events returned for this project")

        event = data[0]
        required_fields = [
            "project_id",
            "session_id",
            "event_seq",
            "model_id",
            "event_type",
            "message_content",
            "timestamp_utc",
            "timestamp_local",
            "input_tokens",
            "output_tokens",
            "cumulative_output_tokens",
        ]

        for field in required_fields:
            assert field in event, f"Missing required field: {field}"

    def test_cumulative_tokens_increase(self, test_client: TestClient) -> None:
        """Test that cumulative output tokens increase within a session."""
        # First get a real project ID
        hourly_response = test_client.get("/api/usage/hourly?days=30")
        hourly_data = hourly_response.json()
        if not hourly_data:
            pytest.skip("No hourly data available")

        project_id = hourly_data[0].get("project_id")

        response = test_client.get(f"/api/timeline/events/{project_id}")
        data = response.json()

        if not data:
            pytest.skip("No timeline events returned for this project")

        # Group by session and verify cumulative tokens are non-decreasing
        sessions: dict[str, list[dict[str, Any]]] = {}
        for event in data:
            session_id = event.get("session_id", "")
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append(event)

        for session_id, events in sessions.items():
            if len(events) > 1:
                sorted_events = sorted(events, key=lambda e: e.get("event_seq", 0))
                prev_cumulative = 0
                for event in sorted_events:
                    current_cumulative = event.get("cumulative_output_tokens", 0)
                    assert current_cumulative >= prev_cumulative, (
                        f"Cumulative tokens decreased in session {session_id}: "
                        f"{prev_cumulative} -> {current_cumulative}"
                    )
                    prev_cumulative = current_cumulative


class TestTimelineSessionOrdering:
    """Tests for session ordering in timeline data."""

    def test_sessions_ordered_by_first_event(self, test_client: TestClient) -> None:
        """Test that sessions are ordered by their first event time."""
        # First get a real project ID
        hourly_response = test_client.get("/api/usage/hourly?days=30")
        hourly_data = hourly_response.json()
        if not hourly_data:
            pytest.skip("No hourly data available")

        project_id = hourly_data[0].get("project_id")

        response = test_client.get(f"/api/timeline/events/{project_id}")
        data = response.json()

        if not data:
            pytest.skip("No timeline events returned")

        # Get first event times for each session
        session_first_times: dict[str, str] = {}
        for event in data:
            session_id = event.get("session_id", "")
            first_time = event.get("first_event_time", "")
            if session_id and first_time:
                if session_id not in session_first_times:
                    session_first_times[session_id] = first_time

        # The data should already be ordered by first_event_time
        first_times = list(session_first_times.values())
        assert first_times == sorted(first_times), "Sessions are not ordered by first event time"


# =============================================================================
# Tests: Health Check
# =============================================================================


class TestHealthEndpoint:
    """Tests for health endpoint."""

    def test_health_returns_projects_path(self, test_client: TestClient) -> None:
        """Test that health endpoint includes projects path."""
        response = test_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "projects_path" in data
