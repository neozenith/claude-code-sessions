"""
Session Parser Module

Pure Python parser for Claude Code session JSONL files.
Extracts events from main session files and subagent files,
building proper parent-child relationships.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionEvent:
    """Represents a single event from a session JSONL file."""

    # Core identification
    uuid: str | None
    parent_uuid: str | None
    event_type: str

    # Timestamps
    timestamp: str | None
    timestamp_dt: datetime | None = None

    # Session identification
    session_id: str | None = None

    # Agent identification
    is_sidechain: bool = False
    agent_slug: str | None = None  # From subagent filename

    # Message content
    message_role: str | None = None
    message_content: Any = None  # Can be string or list of content items
    model_id: str | None = None

    # Token usage
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    # Source file information
    filepath: str = ""
    line_number: int = 0
    is_subagent_file: bool = False

    # Raw data for expandable view
    raw_event: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "uuid": self.uuid,
            "parent_uuid": self.parent_uuid,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "timestamp_local": (
                self.timestamp_dt.strftime("%Y-%m-%dT%H:%M:%S")
                if self.timestamp_dt
                else None
            ),
            "session_id": self.session_id,
            "is_sidechain": self.is_sidechain,
            "agent_slug": self.agent_slug,
            "message_role": self.message_role,
            "message_content": self.message_content,
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "filepath": self.filepath,
            "line_number": self.line_number,
            "is_subagent_file": self.is_subagent_file,
            # Full raw event for expandable JSON view - not just message field
            # This ensures progress, queue-operation, and other event types show their data
            "message_json": self.raw_event,
        }


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime."""
    if not ts:
        return None
    try:
        # Handle various ISO formats
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def extract_agent_slug(filepath: str) -> str | None:
    """Extract agent slug from subagent filename like 'agent-acompact-53e7c1.jsonl'."""
    path = Path(filepath)
    name = path.stem  # e.g., 'agent-acompact-53e7c1'
    if name.startswith("agent-"):
        # Remove 'agent-' prefix and trailing hash
        parts = name[6:].rsplit("-", 1)
        if len(parts) >= 1:
            return parts[0]  # e.g., 'acompact'
    return None


def parse_event_line(
    line: str,
    filepath: str,
    line_number: int,
    is_subagent: bool = False,
) -> SessionEvent | None:
    """Parse a single JSONL line into a SessionEvent.

    Args:
        line: Raw JSON line
        filepath: Path to the source file
        line_number: 1-based line number in the file
        is_subagent: Whether this is from a subagent file

    Returns:
        SessionEvent or None if line should be skipped
    """
    try:
        data = json.loads(line.strip())
    except json.JSONDecodeError:
        return None

    event_type = data.get("type")
    if not event_type:
        return None

    # Skip non-message events (file-history-snapshot, etc.)
    # But keep progress and queue-operation for completeness
    skip_types = {"file-history-snapshot"}
    if event_type in skip_types:
        return None

    # Extract message content and metadata
    message = data.get("message", {})
    message_content = None
    message_role = None
    model_id = None
    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_creation_tokens = 0

    if isinstance(message, dict):
        message_role = message.get("role")
        message_content = message.get("content")
        model_id = message.get("model")

        # Extract token usage
        usage = message.get("usage", {})
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0) or 0
            output_tokens = usage.get("output_tokens", 0) or 0
            cache_read_tokens = usage.get("cache_read_input_tokens", 0) or 0
            cache_creation = usage.get("cache_creation", {})
            if isinstance(cache_creation, dict):
                cache_creation_tokens = (
                    cache_creation.get("ephemeral_5m_input_tokens", 0) or 0
                )

    timestamp = data.get("timestamp")
    timestamp_dt = parse_timestamp(timestamp)

    return SessionEvent(
        uuid=data.get("uuid"),
        parent_uuid=data.get("parentUuid"),
        event_type=event_type,
        timestamp=timestamp,
        timestamp_dt=timestamp_dt,
        session_id=data.get("sessionId"),
        is_sidechain=data.get("isSidechain", False),
        agent_slug=extract_agent_slug(filepath) if is_subagent else None,
        message_role=message_role,
        message_content=message_content,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_creation_tokens=cache_creation_tokens,
        filepath=filepath,
        line_number=line_number,
        is_subagent_file=is_subagent,
        raw_event=data,
    )


def parse_jsonl_file(
    filepath: Path,
    is_subagent: bool = False,
) -> list[SessionEvent]:
    """Parse all events from a JSONL file.

    Args:
        filepath: Path to the JSONL file
        is_subagent: Whether this is a subagent file

    Returns:
        List of SessionEvent objects
    """
    events: list[SessionEvent] = []

    if not filepath.exists():
        return events

    try:
        with filepath.open("r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                event = parse_event_line(
                    line=line,
                    filepath=str(filepath),
                    line_number=line_number,
                    is_subagent=is_subagent,
                )
                if event:
                    events.append(event)
    except (OSError, UnicodeDecodeError) as e:
        # Log error but don't fail
        print(f"Warning: Error reading {filepath}: {e}")

    return events


def parse_session(
    projects_path: Path,
    project_id: str,
    session_id: str,
) -> list[SessionEvent]:
    """Parse all events for a session including subagent events.

    Args:
        projects_path: Base path to projects directory
        project_id: The project ID (e.g., '-Users-joshpeak-myproject')
        session_id: The session UUID

    Returns:
        List of all SessionEvent objects, sorted by timestamp
    """
    all_events: list[SessionEvent] = []

    # Main session file
    main_file = projects_path / project_id / f"{session_id}.jsonl"
    if main_file.exists():
        main_events = parse_jsonl_file(main_file, is_subagent=False)
        all_events.extend(main_events)

    # Subagent files in new-style directory
    subagent_dir = projects_path / project_id / session_id / "subagents"
    if subagent_dir.exists():
        for subagent_file in subagent_dir.glob("*.jsonl"):
            subagent_events = parse_jsonl_file(subagent_file, is_subagent=True)
            all_events.extend(subagent_events)

    # Sort by timestamp (None timestamps go last)
    all_events.sort(key=lambda e: (e.timestamp_dt is None, e.timestamp_dt))

    return all_events


def filter_event_tree(events: list[SessionEvent], root_uuid: str) -> list[SessionEvent]:
    """Filter events to include only a specific event and all its descendants.

    Args:
        events: List of all session events
        root_uuid: The UUID of the root event to filter to

    Returns:
        Filtered list containing the root event and all events that descend from it
    """
    # Build parent->children map
    children_map: dict[str, list[str]] = {}
    for event in events:
        if event.parent_uuid and event.uuid:
            if event.parent_uuid not in children_map:
                children_map[event.parent_uuid] = []
            children_map[event.parent_uuid].append(event.uuid)

    # Find all descendant UUIDs using BFS
    allowed_uuids: set[str] = {root_uuid}
    queue = [root_uuid]

    while queue:
        current = queue.pop(0)
        children = children_map.get(current, [])
        for child_uuid in children:
            if child_uuid not in allowed_uuids:
                allowed_uuids.add(child_uuid)
                queue.append(child_uuid)

    # Filter events
    return [event for event in events if event.uuid and event.uuid in allowed_uuids]


def events_to_response(events: list[SessionEvent]) -> list[dict[str, Any]]:
    """Convert list of SessionEvent to API response format."""
    return [event.to_dict() for event in events]
