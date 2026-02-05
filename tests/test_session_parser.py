"""Tests for the session_parser module."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_code_sessions.session_parser import (
    SessionEvent,
    events_to_response,
    extract_agent_slug,
    filter_event_tree,
    parse_event_line,
    parse_jsonl_file,
    parse_session,
    parse_timestamp,
)


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_parse_valid_iso_timestamp(self) -> None:
        result = parse_timestamp("2026-02-05T01:43:58.887Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 2
        assert result.day == 5

    def test_parse_timestamp_with_offset(self) -> None:
        result = parse_timestamp("2026-02-05T12:00:00+11:00")
        assert result is not None
        assert result.hour == 12

    def test_parse_none_returns_none(self) -> None:
        assert parse_timestamp(None) is None

    def test_parse_invalid_timestamp_returns_none(self) -> None:
        assert parse_timestamp("not-a-timestamp") is None
        assert parse_timestamp("") is None


class TestExtractAgentSlug:
    """Tests for extract_agent_slug function."""

    def test_extract_standard_agent_slug(self) -> None:
        assert extract_agent_slug("/path/to/agent-acompact-53e7c1.jsonl") == "acompact"

    def test_extract_multipart_slug(self) -> None:
        assert (
            extract_agent_slug("/path/to/agent-aprompt_suggestion-b5d8ef.jsonl")
            == "aprompt_suggestion"
        )

    def test_non_agent_file_returns_none(self) -> None:
        assert extract_agent_slug("/path/to/session-abc123.jsonl") is None
        assert extract_agent_slug("/path/to/regular.jsonl") is None


class TestParseEventLine:
    """Tests for parse_event_line function."""

    def test_parse_user_event(self) -> None:
        line = json.dumps(
            {
                "type": "user",
                "uuid": "abc-123",
                "parentUuid": None,
                "timestamp": "2026-02-05T01:00:00Z",
                "message": {"role": "user", "content": "Hello"},
            }
        )
        event = parse_event_line(line, "/path/file.jsonl", 1)

        assert event is not None
        assert event.event_type == "user"
        assert event.uuid == "abc-123"
        assert event.parent_uuid is None
        assert event.message_role == "user"
        assert event.message_content == "Hello"

    def test_parse_assistant_event_with_usage(self) -> None:
        line = json.dumps(
            {
                "type": "assistant",
                "uuid": "def-456",
                "parentUuid": "abc-123",
                "timestamp": "2026-02-05T01:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hi there"}],
                    "model": "claude-sonnet-4-5",
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "cache_read_input_tokens": 10,
                    },
                },
            }
        )
        event = parse_event_line(line, "/path/file.jsonl", 2)

        assert event is not None
        assert event.event_type == "assistant"
        assert event.uuid == "def-456"
        assert event.parent_uuid == "abc-123"
        assert event.model_id == "claude-sonnet-4-5"
        assert event.input_tokens == 100
        assert event.output_tokens == 50
        assert event.cache_read_tokens == 10
        assert event.message_content == [{"type": "text", "text": "Hi there"}]

    def test_parse_progress_event(self) -> None:
        line = json.dumps(
            {
                "type": "progress",
                "uuid": "prog-789",
                "parentUuid": "def-456",
                "timestamp": "2026-02-05T01:02:00Z",
            }
        )
        event = parse_event_line(line, "/path/file.jsonl", 3)

        assert event is not None
        assert event.event_type == "progress"
        assert event.uuid == "prog-789"

    def test_skip_file_history_snapshot(self) -> None:
        line = json.dumps(
            {
                "type": "file-history-snapshot",
                "messageId": "msg-123",
            }
        )
        event = parse_event_line(line, "/path/file.jsonl", 1)
        assert event is None

    def test_skip_event_without_type(self) -> None:
        line = json.dumps({"uuid": "no-type"})
        event = parse_event_line(line, "/path/file.jsonl", 1)
        assert event is None

    def test_invalid_json_returns_none(self) -> None:
        event = parse_event_line("not valid json", "/path/file.jsonl", 1)
        assert event is None

    def test_line_number_preserved(self) -> None:
        line = json.dumps({"type": "user", "uuid": "test"})
        event = parse_event_line(line, "/path/file.jsonl", 42)

        assert event is not None
        assert event.line_number == 42

    def test_filepath_preserved(self) -> None:
        line = json.dumps({"type": "user", "uuid": "test"})
        event = parse_event_line(line, "/custom/path/session.jsonl", 1)

        assert event is not None
        assert event.filepath == "/custom/path/session.jsonl"

    def test_subagent_flag_set(self) -> None:
        line = json.dumps({"type": "user", "uuid": "test"})

        main_event = parse_event_line(line, "/path/file.jsonl", 1, is_subagent=False)
        subagent_event = parse_event_line(
            line, "/path/agent-test-abc.jsonl", 1, is_subagent=True
        )

        assert main_event is not None
        assert main_event.is_subagent_file is False

        assert subagent_event is not None
        assert subagent_event.is_subagent_file is True
        assert subagent_event.agent_slug == "test"


class TestParseJsonlFile:
    """Tests for parse_jsonl_file function."""

    def test_parse_multiple_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.jsonl"
            filepath.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"type": "user", "uuid": "1", "timestamp": "2026-01-01T00:00:00Z"}
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "uuid": "2",
                                "parentUuid": "1",
                                "timestamp": "2026-01-01T00:01:00Z",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "progress",
                                "uuid": "3",
                                "parentUuid": "2",
                                "timestamp": "2026-01-01T00:02:00Z",
                            }
                        ),
                    ]
                )
            )

            events = parse_jsonl_file(filepath)

            assert len(events) == 3
            assert events[0].event_type == "user"
            assert events[1].event_type == "assistant"
            assert events[2].event_type == "progress"

    def test_skip_empty_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.jsonl"
            filepath.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "user", "uuid": "1"}),
                        "",
                        "   ",
                        json.dumps({"type": "assistant", "uuid": "2"}),
                    ]
                )
            )

            events = parse_jsonl_file(filepath)
            assert len(events) == 2

    def test_nonexistent_file_returns_empty(self) -> None:
        events = parse_jsonl_file(Path("/nonexistent/path.jsonl"))
        assert events == []

    def test_line_numbers_correct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.jsonl"
            filepath.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "file-history-snapshot"}),  # line 1 - skipped
                        json.dumps({"type": "user", "uuid": "1"}),  # line 2
                        json.dumps({"type": "assistant", "uuid": "2"}),  # line 3
                    ]
                )
            )

            events = parse_jsonl_file(filepath)

            assert len(events) == 2
            assert events[0].line_number == 2
            assert events[1].line_number == 3


class TestParseSession:
    """Tests for parse_session function."""

    def test_parse_main_file_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir)
            project_dir = projects_path / "-Users-test-project"
            project_dir.mkdir(parents=True)

            # Create main session file
            session_file = project_dir / "session-abc.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"type": "user", "uuid": "1", "timestamp": "2026-01-01T00:00:00Z"}
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "uuid": "2",
                                "timestamp": "2026-01-01T00:01:00Z",
                            }
                        ),
                    ]
                )
            )

            events = parse_session(projects_path, "-Users-test-project", "session-abc")

            assert len(events) == 2
            assert all(e.is_subagent_file is False for e in events)

    def test_parse_with_subagents(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir)
            project_dir = projects_path / "-Users-test-project"
            project_dir.mkdir(parents=True)

            # Create main session file
            session_file = project_dir / "session-abc.jsonl"
            session_file.write_text(
                json.dumps(
                    {"type": "user", "uuid": "main-1", "timestamp": "2026-01-01T00:00:00Z"}
                )
            )

            # Create subagent directory and file
            subagent_dir = project_dir / "session-abc" / "subagents"
            subagent_dir.mkdir(parents=True)
            subagent_file = subagent_dir / "agent-acompact-123abc.jsonl"
            subagent_file.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "sub-1",
                        "sessionId": "session-abc",
                        "timestamp": "2026-01-01T00:00:30Z",
                    }
                )
            )

            events = parse_session(projects_path, "-Users-test-project", "session-abc")

            assert len(events) == 2
            main_events = [e for e in events if not e.is_subagent_file]
            sub_events = [e for e in events if e.is_subagent_file]

            assert len(main_events) == 1
            assert len(sub_events) == 1
            assert sub_events[0].agent_slug == "acompact"

    def test_events_sorted_by_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir)
            project_dir = projects_path / "-Users-test-project"
            project_dir.mkdir(parents=True)

            # Create events out of order
            session_file = project_dir / "session-abc.jsonl"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {"type": "user", "uuid": "3", "timestamp": "2026-01-01T00:03:00Z"}
                        ),
                        json.dumps(
                            {"type": "user", "uuid": "1", "timestamp": "2026-01-01T00:01:00Z"}
                        ),
                        json.dumps(
                            {"type": "user", "uuid": "2", "timestamp": "2026-01-01T00:02:00Z"}
                        ),
                    ]
                )
            )

            events = parse_session(projects_path, "-Users-test-project", "session-abc")

            # Should be sorted by timestamp
            assert events[0].uuid == "1"
            assert events[1].uuid == "2"
            assert events[2].uuid == "3"

    def test_nonexistent_session_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_path = Path(tmpdir)
            events = parse_session(
                projects_path, "-Users-test-project", "nonexistent-session"
            )
            assert events == []


class TestSessionEvent:
    """Tests for SessionEvent dataclass."""

    def test_to_dict(self) -> None:
        raw = {
            "type": "assistant",
            "uuid": "abc-123",
            "parentUuid": "parent-456",
            "message": {"role": "assistant", "content": "test"},
        }
        event = SessionEvent(
            uuid="abc-123",
            parent_uuid="parent-456",
            event_type="assistant",
            timestamp="2026-02-05T01:00:00Z",
            timestamp_dt=datetime(2026, 2, 5, 1, 0, 0, tzinfo=timezone.utc),
            model_id="claude-sonnet-4-5",
            input_tokens=100,
            output_tokens=50,
            filepath="/path/to/file.jsonl",
            line_number=42,
            raw_event=raw,
        )

        d = event.to_dict()

        assert d["uuid"] == "abc-123"
        assert d["parent_uuid"] == "parent-456"
        assert d["event_type"] == "assistant"
        assert d["model_id"] == "claude-sonnet-4-5"
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["filepath"] == "/path/to/file.jsonl"
        assert d["line_number"] == 42
        # message_json now contains the full raw event, not just the message field
        assert d["message_json"] == raw

    def test_to_dict_progress_event_has_full_data(self) -> None:
        """Progress events should show full raw data, not just message field."""
        raw = {
            "type": "progress",
            "uuid": "prog-123",
            "parentUuid": "assistant-456",
            "data": {"type": "mcp_progress", "status": "started", "serverName": "serena"},
            "toolUseID": "toolu_abc123",
        }
        event = SessionEvent(
            uuid="prog-123",
            parent_uuid="assistant-456",
            event_type="progress",
            timestamp="2026-02-05T01:00:00Z",
            filepath="/path/to/file.jsonl",
            line_number=10,
            raw_event=raw,
        )

        d = event.to_dict()

        # message_json should contain the full raw event including data field
        assert d["message_json"] == raw
        assert d["message_json"]["data"]["type"] == "mcp_progress"
        assert d["message_json"]["toolUseID"] == "toolu_abc123"


class TestFilterEventTree:
    """Tests for filter_event_tree function."""

    def test_filter_returns_root_and_descendants(self) -> None:
        """Filter should return the root event and all its descendants."""
        events = [
            SessionEvent(uuid="root", parent_uuid=None, event_type="user", timestamp="t1"),
            SessionEvent(uuid="child1", parent_uuid="root", event_type="assistant", timestamp="t2"),
            SessionEvent(uuid="child2", parent_uuid="root", event_type="assistant", timestamp="t3"),
            SessionEvent(uuid="grandchild", parent_uuid="child1", event_type="user", timestamp="t4"),
            SessionEvent(uuid="other", parent_uuid=None, event_type="user", timestamp="t5"),
        ]

        filtered = filter_event_tree(events, "root")

        uuids = {e.uuid for e in filtered}
        assert uuids == {"root", "child1", "child2", "grandchild"}
        assert "other" not in uuids

    def test_filter_single_event_no_children(self) -> None:
        """Filter on a leaf event returns only that event."""
        events = [
            SessionEvent(uuid="root", parent_uuid=None, event_type="user", timestamp="t1"),
            SessionEvent(uuid="child", parent_uuid="root", event_type="assistant", timestamp="t2"),
        ]

        filtered = filter_event_tree(events, "child")

        assert len(filtered) == 1
        assert filtered[0].uuid == "child"

    def test_filter_nonexistent_uuid_returns_empty(self) -> None:
        """Filter on nonexistent UUID returns empty list."""
        events = [
            SessionEvent(uuid="root", parent_uuid=None, event_type="user", timestamp="t1"),
        ]

        filtered = filter_event_tree(events, "nonexistent")

        assert len(filtered) == 0

    def test_filter_preserves_order(self) -> None:
        """Filter should preserve the original order of events."""
        events = [
            SessionEvent(uuid="1", parent_uuid=None, event_type="user", timestamp="t1"),
            SessionEvent(uuid="2", parent_uuid="1", event_type="assistant", timestamp="t2"),
            SessionEvent(uuid="3", parent_uuid="2", event_type="user", timestamp="t3"),
        ]

        filtered = filter_event_tree(events, "1")

        assert [e.uuid for e in filtered] == ["1", "2", "3"]


class TestEventsToResponse:
    """Tests for events_to_response function."""

    def test_converts_list_of_events(self) -> None:
        events = [
            SessionEvent(
                uuid="1",
                parent_uuid=None,
                event_type="user",
                timestamp="2026-01-01T00:00:00Z",
            ),
            SessionEvent(
                uuid="2",
                parent_uuid="1",
                event_type="assistant",
                timestamp="2026-01-01T00:01:00Z",
            ),
        ]

        response = events_to_response(events)

        assert len(response) == 2
        assert response[0]["uuid"] == "1"
        assert response[1]["uuid"] == "2"
        assert response[1]["parent_uuid"] == "1"


class TestIntegrationWithRealData:
    """Integration tests using real project data if available."""

    @pytest.fixture
    def projects_path(self) -> Path:
        return Path("projects")

    def test_parse_real_session_if_exists(self, projects_path: Path) -> None:
        """Test with real data if the test session exists."""
        project_id = "-Users-joshpeak-play-claude-code-sessions"
        session_id = "cf119ac3-8a30-490f-92ff-8dc590d719ae"

        session_file = projects_path / project_id / f"{session_id}.jsonl"
        if not session_file.exists():
            pytest.skip("Test session file not found")

        events = parse_session(projects_path, project_id, session_id)

        # Basic sanity checks
        assert len(events) > 100, "Should have many events"
        assert any(e.event_type == "user" for e in events)
        assert any(e.event_type == "assistant" for e in events)

        # All events should have filepath and line_number
        assert all(e.filepath for e in events)
        assert all(e.line_number > 0 for e in events)

        # Check parent-child relationships
        uuids = {e.uuid for e in events if e.uuid}
        with_parent = [e for e in events if e.parent_uuid]
        orphans = [e for e in with_parent if e.parent_uuid not in uuids]
        assert len(orphans) == 0, "All parents should exist in the event set"
