"""
DuckDB implementation of the Database protocol.

Stateless engine that full-scans JSONL session files on every request
using DuckDB's in-memory ``read_json_auto`` glob. No persistent index.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from claude_code_sessions.config import (
    BLOCKED_DOMAINS,
    HOME_PREFIX,
    extract_domain,
    is_project_blocked,
)
from claude_code_sessions.database.raw_json import read_jsonl_line
from claude_code_sessions.session_parser import (
    events_to_response,
    filter_event_tree,
    parse_session,
)

# Allowlist mapping for sort_by parameter values -> SQL column expressions.
# Using an explicit allowlist prevents SQL injection from user-supplied sort_by values.
_SORT_COLUMN_MAP: dict[str, str] = {
    "last_active": "s.last_timestamp",
    "events": "s.event_count",
    "subagents": "COALESCE(s.subagent_count, 0)",
    "cost": "ROUND(COALESCE(c.total_cost_usd, 0), 4)",
}


class DuckDBDatabase:
    """DuckDB-backed analytics database.

    Executes SQL templates from the queries/ directory against JSONL session
    files using DuckDB's in-memory engine. Each query creates a fresh
    connection, reads data via ``read_json_auto`` glob, and returns results
    as a list of dicts.
    """

    def __init__(
        self,
        *,
        queries_path: Path,
        pricing_csv_path: Path,
        local_projects_path: Path,
        home_projects_path: Path,
    ) -> None:
        self._queries_path = queries_path
        self._pricing_csv_path = pricing_csv_path
        self._local_projects_path = local_projects_path
        self._home_projects_path = home_projects_path

    # -- Properties ----------------------------------------------------------

    @property
    def projects_path(self) -> Path:
        """Resolve projects path, preferring local copy over home directory.

        Raises:
            FileNotFoundError: If no projects data directory can be found.
        """
        if self._local_projects_path.exists() and any(self._local_projects_path.iterdir()):
            return self._local_projects_path
        if self._home_projects_path.exists():
            return self._home_projects_path
        raise FileNotFoundError("No projects data found")

    # -- Public query methods ------------------------------------------------

    def get_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        return self._execute_query("summary", self._build_filters(days=days, project=project))

    def get_daily_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        return self._execute_query("by_day", self._build_filters(days=days, project=project))

    def get_weekly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        return self._execute_query("by_week", self._build_filters(days=days, project=project))

    def get_monthly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        return self._execute_query("by_month", self._build_filters(days=days, project=project))

    def get_hourly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        filters: dict[str, str] = {}
        if days and days > 0:
            filters["DAYS_FILTER"] = (
                f"AND TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE "
                f"'Australia/Melbourne' >= CURRENT_DATE - INTERVAL '{days} days'"
            )
        else:
            filters["DAYS_FILTER"] = ""
        if project:
            safe_project = project.replace("'", "''")
            filters["PROJECT_FILTER"] = (
                f"AND regexp_extract(filename, 'projects/([^/]+)/', 1) = '{safe_project}'"
            )
        else:
            filters["PROJECT_FILTER"] = ""
        filters["DOMAIN_FILTER"] = self._build_domain_filter_sql()
        return self._execute_query("by_hour", filters)

    def get_session_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        return self._execute_query("sessions", self._build_filters(days=days, project=project))

    def get_sessions_list(
        self,
        *,
        days: int | None = None,
        project: str | None = None,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        filters = self._build_filters(
            days=days, project=project, sort_by=sort_by, sort_order=sort_order
        )
        return self._execute_query("sessions_list", filters)

    def get_projects(self, *, days: int | None = None) -> list[dict[str, Any]]:
        filters = self._build_filters(days=days)
        data = self._execute_query("by_month", filters)
        projects: dict[str, dict[str, Any]] = {}
        for row in data:
            proj = row.get("project_id", "unknown")
            if proj not in projects:
                projects[proj] = {
                    "project_id": proj,
                    "total_cost_usd": 0.0,
                    "session_count": 0,
                    "event_count": 0,
                }
            projects[proj]["total_cost_usd"] += float(row.get("total_cost_usd", 0))
            projects[proj]["session_count"] += int(row.get("session_count", 0))
            projects[proj]["event_count"] += int(row.get("event_count", 0))
        return sorted(projects.values(), key=lambda p: p["total_cost_usd"], reverse=True)

    def get_top_projects_weekly(self, *, days: int | None = None) -> list[dict[str, Any]]:
        filters: dict[str, str] = {}
        effective_days = days if days is not None else 56
        if effective_days and effective_days > 0:
            filters["DAYS_FILTER"] = (
                f"AND TRY_CAST(timestamp AS TIMESTAMP) >= "
                f"CURRENT_DATE - INTERVAL '{effective_days} days'"
            )
        else:
            filters["DAYS_FILTER"] = ""
        filters["DOMAIN_FILTER"] = self._build_domain_filter_sql()
        return self._execute_query("top_projects_weekly", filters)

    def get_timeline_events(
        self, project_id: str, *, days: int | None = None
    ) -> list[dict[str, Any]]:
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")
        filters: dict[str, str] = {"PROJECT_FILTER": project_id}
        if days and days > 0:
            filters["DAYS_FILTER"] = f"AND timestamp_utc >= NOW() - INTERVAL '{days} days'"
        else:
            filters["DAYS_FILTER"] = ""
        filters["DOMAIN_FILTER"] = self._build_domain_filter_sql()
        return self._execute_query("timeline_events", filters)

    def get_schema_timeline(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        filters: dict[str, str] = {}
        if days and days > 0:
            filters["DAYS_FILTER"] = f"AND event_date >= CURRENT_DATE - INTERVAL '{days} days'"
        else:
            filters["DAYS_FILTER"] = ""
        if project:
            filters["PROJECT_FILTER"] = f"AND project_id = '{project}'"
        else:
            filters["PROJECT_FILTER"] = ""
        filters["DOMAIN_FILTER"] = self._build_domain_filter_sql()
        projects_path = self.projects_path
        file_mtimes_df = self._get_file_mtimes_df(projects_path)
        return self._execute_query(
            "schema_timeline", filters, dataframes={"file_mtimes": file_mtimes_df}
        )

    def get_session_events(
        self, project_id: str, session_id: str, *, event_uuid: str | None = None
    ) -> list[dict[str, Any]]:
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")
        events = parse_session(self.projects_path, project_id, session_id)
        if event_uuid:
            events = filter_event_tree(events, event_uuid)
        return events_to_response(events)

    def get_event_raw_json(
        self, project_id: str, session_id: str, event_uuid: str
    ) -> str | None:
        """Fetch raw JSON line from the source JSONL file on demand.

        The DuckDB path already reads JSONL per request, so we parse the
        session and find the event by uuid, then use its (filepath,
        line_number) to read the raw line from disk.
        """
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")

        events = parse_session(self.projects_path, project_id, session_id)
        for ev in events:
            if ev.uuid == event_uuid:
                return read_jsonl_line(Path(ev.filepath), ev.line_number)
        return None

    def get_domains(self) -> dict[str, list[str]]:
        projects_path = self.projects_path
        all_domains: set[str] = set()
        for project_dir in projects_path.iterdir():
            if project_dir.is_dir():
                domain = extract_domain(project_dir.name)
                if domain:
                    all_domains.add(domain)
        sorted_all = sorted(all_domains)
        blocked = sorted(d for d in sorted_all if d in BLOCKED_DOMAINS)
        available = sorted(d for d in sorted_all if d not in BLOCKED_DOMAINS)
        return {"available": available, "blocked": blocked, "all": sorted_all}

    def is_project_blocked(self, project_id: str) -> bool:
        return is_project_blocked(project_id)

    def get_calls_timeline(
        self,
        *,
        granularity: str,
        days: int | None = None,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        # DuckDB backend is the stateless full-scan reader and doesn't
        # materialize event_calls (that fact table lives in the SQLite
        # cache). Dashboards that want call metrics should point at the
        # SQLite backend. Returning an empty list here satisfies the
        # Protocol without pretending to have data we haven't parsed.
        _ = (granularity, days, project)
        return []

    def get_top_calls(
        self,
        *,
        call_type: str,
        days: int | None = None,
        project: str | None = None,
        limit: int = 20,
        exclude: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        _ = (call_type, days, project, limit, exclude)
        return []

    # -- Private helpers -----------------------------------------------------

    def _build_domain_filter_sql(self) -> str:
        """Generate SQL AND clauses to exclude blocked domains."""
        if not BLOCKED_DOMAINS:
            return ""
        clauses = []
        for domain in BLOCKED_DOMAINS:
            clauses.append(
                f"AND regexp_extract(filename, 'projects/([^/]+)/', 1) "
                f"NOT LIKE '{HOME_PREFIX}-{domain}-%'"
            )
        return "\n    ".join(clauses)

    def _build_filters(
        self,
        *,
        days: int | None = None,
        project: str | None = None,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> dict[str, str]:
        """Build filter dict for SQL query placeholders."""
        filters: dict[str, str] = {}
        if days and days > 0:
            filters["DAYS_FILTER"] = (
                f"AND TRY_CAST(timestamp AS TIMESTAMP) >= CURRENT_DATE - INTERVAL '{days} days'"
            )
        else:
            filters["DAYS_FILTER"] = ""
        if project:
            safe_project = project.replace("'", "''")
            filters["PROJECT_FILTER"] = (
                f"AND regexp_extract(filename, 'projects/([^/]+)/', 1) = '{safe_project}'"
            )
        else:
            filters["PROJECT_FILTER"] = ""
        filters["DOMAIN_FILTER"] = self._build_domain_filter_sql()
        valid_sort_by = sort_by if sort_by in _SORT_COLUMN_MAP else "last_active"
        valid_sort_order = "ASC" if sort_order.strip().lower() == "asc" else "DESC"
        filters["SORT_COLUMN"] = _SORT_COLUMN_MAP[valid_sort_by]
        filters["SORT_ORDER"] = valid_sort_order
        return filters

    def _execute_query(
        self,
        query_name: str,
        filters: dict[str, str] | None = None,
        dataframes: dict[str, pd.DataFrame] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SQL query file and return results as list of dicts."""
        query_file = self._queries_path / f"{query_name}.sql"
        if not query_file.exists():
            raise FileNotFoundError(f"Query file not found: {query_name}.sql")
        sql = query_file.read_text()
        projects_path = self.projects_path
        sql = sql.replace("__PROJECTS_GLOB__", f"{projects_path}/**/*.jsonl")
        sql = sql.replace("__PRICING_CSV_PATH__", str(self._pricing_csv_path))
        if filters:
            for key, value in filters.items():
                sql = sql.replace(f"__{key}__", value)
        conn = duckdb.connect(":memory:")
        try:
            if dataframes:
                for table_name, df in dataframes.items():
                    conn.register(table_name, df)
            result = conn.execute(sql).fetchall()
            columns = [desc[0] for desc in conn.description]
            return [dict(zip(columns, row, strict=False)) for row in result]
        finally:
            conn.close()

    @staticmethod
    def _get_file_mtimes_df(projects_path: Path) -> pd.DataFrame:
        """Get file modification times as a pandas DataFrame."""
        records = []
        for filepath in projects_path.glob("**/*.jsonl"):
            project_dir = filepath.parent.name
            if is_project_blocked(project_dir):
                continue
            mtime = filepath.stat().st_mtime
            mtime_date = datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%d")
            records.append({"filename": str(filepath.resolve()), "mtime_date": mtime_date})
        return pd.DataFrame(records)
