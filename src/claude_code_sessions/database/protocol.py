"""
Database Protocol for Claude Code Sessions analytics.

Defines the interface that all database backends must implement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Database(Protocol):
    """Interface for all data access in the Claude Code Sessions dashboard.

    Implementations may use DuckDB, SQLite, PostgreSQL, or any other backend.
    The API layer depends only on this protocol — never on a concrete class.
    """

    @property
    def projects_path(self) -> Path:
        """Resolved path to the projects data directory."""
        ...

    def get_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Overall usage summary with costs, event counts, subagent breakdown."""
        ...

    def get_daily_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Daily aggregated usage."""
        ...

    def get_weekly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Weekly aggregated usage."""
        ...

    def get_monthly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Monthly aggregated usage."""
        ...

    def get_hourly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Hourly usage breakdown for heatmap visualization."""
        ...

    def get_session_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """Per-session token usage and cost details."""
        ...

    def get_sessions_list(
        self,
        *,
        days: int | None = None,
        project: str | None = None,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        """Sessions grouped by project with filtering and sorting."""
        ...

    def get_projects(self, *, days: int | None = None) -> list[dict[str, Any]]:
        """Project list aggregated by total cost, sessions, and events."""
        ...

    def get_top_projects_weekly(self, *, days: int | None = None) -> list[dict[str, Any]]:
        """Top projects by cost with weekly breakdown."""
        ...

    def get_timeline_events(
        self, project_id: str, *, days: int | None = None
    ) -> list[dict[str, Any]]:
        """Event-level timeline with cumulative output tokens for a project."""
        ...

    def get_schema_timeline(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        """JSON path evolution timeline with version tracking."""
        ...

    def get_session_events(
        self, project_id: str, session_id: str, *, event_uuid: str | None = None
    ) -> list[dict[str, Any]]:
        """All events for a specific session including subagent events."""
        ...

    def get_event_raw_json(
        self, project_id: str, session_id: str, event_uuid: str
    ) -> str | None:
        """Fetch a single event's raw JSONL line from the source file on disk.

        Returns the raw line as stored in the JSONL source, or None if the
        event isn't found. This is an on-demand alternative to storing the
        raw payload in the cache — the ``events`` table tracks
        (source_file_id, line_number) which lets us seek to the right line.
        """
        ...

    def get_domains(self) -> dict[str, list[str]]:
        """Domain filtering status: available, blocked, and all discovered domains."""
        ...

    def is_project_blocked(self, project_id: str) -> bool:
        """Check if a project belongs to a blocked domain."""
        ...
