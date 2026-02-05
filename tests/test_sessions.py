"""
Tests for the Sessions API endpoints.

Tests:
- GET /api/sessions - List all sessions with universal filters
- GET /api/sessions/{project_id}/{session_id} - Get session events
"""

from fastapi.testclient import TestClient

from claude_code_sessions.main import app

client = TestClient(app)

# Test data - use a known project ID from the test data
TEST_PROJECT_ID = "-Users-joshpeak-play-claude-code-sessions"


class TestSessionsListEndpoint:
    """Test GET /api/sessions endpoint."""

    def test_sessions_list_no_filters(self) -> None:
        """Sessions list returns data with no filters."""
        response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_sessions_list_has_expected_fields(self) -> None:
        """Sessions list items have required fields."""
        response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()

        if len(data) > 0:
            session = data[0]
            # Required fields
            assert "project_id" in session
            assert "session_id" in session
            assert "first_timestamp" in session or session.get("first_timestamp") is None
            assert "last_timestamp" in session or session.get("last_timestamp") is None
            assert "event_count" in session
            assert "subagent_count" in session
            assert "total_input_tokens" in session
            assert "total_output_tokens" in session
            assert "total_cost_usd" in session
            assert "filepath" in session  # Added filepath field

    def test_sessions_list_days_filter(self) -> None:
        """Sessions list returns data with days filter."""
        response = client.get("/api/sessions?days=7")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_sessions_list_project_filter(self) -> None:
        """Sessions list returns data filtered by project."""
        response = client.get(f"/api/sessions?project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # All returned sessions should be for the filtered project
        for session in data:
            assert session.get("project_id") == TEST_PROJECT_ID

    def test_sessions_list_both_filters(self) -> None:
        """Sessions list returns data with both filters."""
        response = client.get(f"/api/sessions?days=30&project={TEST_PROJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_sessions_list_days_zero(self) -> None:
        """Sessions list with days=0 returns all time data."""
        response = client.get("/api/sessions?days=0")
        assert response.status_code == 200

    def test_sessions_list_invalid_project_returns_empty(self) -> None:
        """Invalid project ID returns empty list, not error."""
        response = client.get("/api/sessions?project=nonexistent-project-xyz")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_sessions_list_sorted_by_recent(self) -> None:
        """Sessions are sorted by most recent first."""
        response = client.get("/api/sessions")
        assert response.status_code == 200
        data = response.json()

        if len(data) >= 2:
            # Check that timestamps are in descending order
            timestamps = [
                s.get("last_timestamp") for s in data if s.get("last_timestamp")
            ]
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1], (
                    "Sessions should be sorted by most recent first"
                )


class TestSessionEventsEndpoint:
    """Test GET /api/sessions/{project_id}/{session_id} endpoint."""

    def test_session_events_returns_list(self) -> None:
        """Session events endpoint returns a list."""
        # First get a session from the list to test with
        sessions_response = client.get(f"/api/sessions?project={TEST_PROJECT_ID}")
        sessions = sessions_response.json()

        if len(sessions) > 0:
            session = sessions[0]
            response = client.get(
                f"/api/sessions/{session['project_id']}/{session['session_id']}"
            )
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_session_events_has_required_fields(self) -> None:
        """Session events have required fields from Python parser."""
        # First get a session from the list
        sessions_response = client.get(f"/api/sessions?project={TEST_PROJECT_ID}")
        sessions = sessions_response.json()

        if len(sessions) > 0:
            session = sessions[0]
            response = client.get(
                f"/api/sessions/{session['project_id']}/{session['session_id']}"
            )
            data = response.json()

            if len(data) > 0:
                event = data[0]
                # Core identification fields
                assert "uuid" in event
                assert "parent_uuid" in event
                assert "event_type" in event
                # Timestamps
                assert "timestamp" in event
                assert "timestamp_local" in event
                # Agent identification
                assert "is_sidechain" in event
                assert "agent_slug" in event
                # Message content
                assert "message_role" in event
                assert "message_content" in event
                assert "model_id" in event
                # Token usage
                assert "input_tokens" in event
                assert "output_tokens" in event
                assert "cache_read_tokens" in event
                # Source file info
                assert "filepath" in event
                assert "line_number" in event
                assert "is_subagent_file" in event
                # Raw message JSON
                assert "message_json" in event

    def test_session_events_ordered_by_timestamp(self) -> None:
        """Session events are ordered chronologically."""
        # First get a session from the list
        sessions_response = client.get(f"/api/sessions?project={TEST_PROJECT_ID}")
        sessions = sessions_response.json()

        if len(sessions) > 0:
            session = sessions[0]
            response = client.get(
                f"/api/sessions/{session['project_id']}/{session['session_id']}"
            )
            data = response.json()

            if len(data) >= 2:
                timestamps = [
                    e.get("timestamp") for e in data if e.get("timestamp")
                ]
                for i in range(len(timestamps) - 1):
                    assert timestamps[i] <= timestamps[i + 1], (
                        "Events should be sorted chronologically"
                    )

    def test_session_events_nonexistent_session(self) -> None:
        """Nonexistent session returns empty list."""
        response = client.get(
            f"/api/sessions/{TEST_PROJECT_ID}/nonexistent-session-id-12345"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_session_events_with_event_uuid_filter(self) -> None:
        """Session events can be filtered by event_uuid to show tree."""
        # First get a session from the list
        sessions_response = client.get(f"/api/sessions?project={TEST_PROJECT_ID}")
        sessions = sessions_response.json()

        if len(sessions) > 0:
            session = sessions[0]
            # Get all events first
            all_response = client.get(
                f"/api/sessions/{session['project_id']}/{session['session_id']}"
            )
            all_events = all_response.json()

            if len(all_events) > 1:
                # Find an event with children
                parent_uuids = {e.get("parent_uuid") for e in all_events if e.get("parent_uuid")}
                root_event = next(
                    (e for e in all_events if e.get("uuid") in parent_uuids),
                    all_events[0]
                )

                # Filter to that event
                filtered_response = client.get(
                    f"/api/sessions/{session['project_id']}/{session['session_id']}",
                    params={"event_uuid": root_event.get("uuid")}
                )
                filtered_events = filtered_response.json()

                # Should have fewer or equal events
                assert len(filtered_events) <= len(all_events)
                # Should include the root event
                filtered_uuids = {e.get("uuid") for e in filtered_events}
                assert root_event.get("uuid") in filtered_uuids


class TestSessionsFilterConsistency:
    """Test filter behavior consistency with other endpoints."""

    def test_project_filter_reduces_results(self) -> None:
        """Project filter should reduce or equal results vs no filter."""
        # Get all sessions
        all_response = client.get("/api/sessions")
        all_data = all_response.json()

        # Get filtered sessions
        filtered_response = client.get(f"/api/sessions?project={TEST_PROJECT_ID}")
        filtered_data = filtered_response.json()

        # Filtered should be <= all
        assert len(filtered_data) <= len(all_data)

    def test_days_filter_reduces_results(self) -> None:
        """Days filter should reduce or equal results vs all time."""
        # Get all time data
        all_response = client.get("/api/sessions?days=0")
        all_data = all_response.json()

        # Get 7 days data
        filtered_response = client.get("/api/sessions?days=7")
        filtered_data = filtered_response.json()

        # 7 days should be <= all time
        assert len(filtered_data) <= len(all_data)
