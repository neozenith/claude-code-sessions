"""
SQLite implementation of the Database protocol.

Stateful engine backed by a persistent SQLite cache. Incrementally indexes
JSONL session files and serves queries from pre-computed aggregates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_code_sessions.config import (
    BLOCKED_DOMAINS,
    extract_domain,
    is_project_blocked,
)
from claude_code_sessions.database.sqlite.cache import CacheManager
from claude_code_sessions.database.sqlite.filters import (
    days_clause,
    domain_clause,
    project_clause,
)
from claude_code_sessions.database.sqlite.schema import CACHE_DB_PATH


class SQLiteDatabase:
    """SQLite-backed analytics database.

    Reads from the persistent cache at ``~/.claude/cache/introspect_sessions.db``,
    running an incremental update on startup to pick up any new session data.
    """

    def __init__(
        self,
        *,
        local_projects_path: Path,
        home_projects_path: Path,
        db_path: Path = CACHE_DB_PATH,
    ) -> None:
        self._local_projects_path = local_projects_path
        self._home_projects_path = home_projects_path
        self._cache = CacheManager(db_path)
        self._cache.ensure_ready(self.projects_path)

    @property
    def projects_path(self) -> Path:
        if self._local_projects_path.exists() and any(self._local_projects_path.iterdir()):
            return self._local_projects_path
        if self._home_projects_path.exists():
            return self._home_projects_path
        raise FileNotFoundError("No projects data found")

    # -- Helpers -------------------------------------------------------------

    def _q(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute SQL and return list of dicts."""
        cursor = self._cache.conn.cursor()
        rows = cursor.execute(sql, params).fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def _filters(
        self,
        days: int | None = None,
        project: str | None = None,
        col_ts: str = "e.timestamp",
        col_proj: str = "e.project_id",
    ) -> str:
        """Build combined filter string from individual clauses."""
        parts = [
            days_clause(days, col_ts),
            project_clause(project, col_proj),
            domain_clause(self.projects_path, col_proj),
        ]
        return " ".join(p for p in parts if p)

    # -- Public query methods ------------------------------------------------

    def get_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project)
        return self._q(f"""
            SELECT
                COUNT(*) AS total_events,
                COUNT(DISTINCT e.session_id) AS total_sessions,
                COALESCE(SUM(e.input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(e.cache_read_tokens), 0) AS total_cache_read_tokens,
                COALESCE(SUM(e.cache_creation_tokens), 0) AS total_cache_creation_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS grand_total_cost_usd,
                SUM(CASE WHEN e.is_sidechain = 1 THEN e.input_tokens ELSE 0 END)
                    AS subagent_input_tokens,
                SUM(CASE WHEN e.is_sidechain = 1 THEN e.output_tokens ELSE 0 END)
                    AS subagent_output_tokens,
                SUM(CASE WHEN e.is_sidechain = 0 THEN e.input_tokens ELSE 0 END)
                    AS main_input_tokens,
                SUM(CASE WHEN e.is_sidechain = 0 THEN e.output_tokens ELSE 0 END)
                    AS main_output_tokens
            FROM events e
            WHERE 1=1 {f}
        """)

    def get_daily_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project)
        return self._q(f"""
            SELECT
                e.project_id, e.model_id,
                DATE(e.timestamp) AS time_bucket,
                COUNT(*) AS event_count,
                COUNT(DISTINCT e.session_id) AS session_count,
                COALESCE(SUM(e.input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(e.cache_read_tokens), 0) AS total_cache_read_input_tokens,
                COALESCE(SUM(e.cache_creation_tokens), 0) AS total_cache_creation_input_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS total_cost_usd
            FROM events e
            WHERE e.timestamp IS NOT NULL {f}
            GROUP BY e.project_id, e.model_id, DATE(e.timestamp)
            ORDER BY time_bucket DESC
        """)

    def get_weekly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project)
        return self._q(f"""
            SELECT
                e.project_id, e.model_id,
                DATE(e.timestamp, 'weekday 0', '-6 days') AS time_bucket,
                COUNT(*) AS event_count,
                COUNT(DISTINCT e.session_id) AS session_count,
                COALESCE(SUM(e.input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(e.cache_read_tokens), 0) AS total_cache_read_input_tokens,
                COALESCE(SUM(e.cache_creation_tokens), 0) AS total_cache_creation_input_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS total_cost_usd
            FROM events e
            WHERE e.timestamp IS NOT NULL {f}
            GROUP BY e.project_id, e.model_id, DATE(e.timestamp, 'weekday 0', '-6 days')
            ORDER BY time_bucket DESC
        """)

    def get_monthly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project)
        return self._q(f"""
            SELECT
                e.project_id, e.model_id,
                STRFTIME('%Y-%m-01', e.timestamp) AS time_bucket,
                COUNT(*) AS event_count,
                COUNT(DISTINCT e.session_id) AS session_count,
                COALESCE(SUM(e.input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(e.cache_read_tokens), 0) AS total_cache_read_input_tokens,
                COALESCE(SUM(e.cache_creation_tokens), 0) AS total_cache_creation_input_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS total_cost_usd
            FROM events e
            WHERE e.timestamp IS NOT NULL {f}
            GROUP BY e.project_id, e.model_id, STRFTIME('%Y-%m-01', e.timestamp)
            ORDER BY time_bucket DESC
        """)

    def get_hourly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project, col_ts="e.timestamp_local")
        return self._q(f"""
            SELECT
                e.project_id,
                DATE(e.timestamp_local) AS time_bucket,
                CAST(STRFTIME('%H', e.timestamp_local) AS INTEGER) AS hour_of_day,
                COUNT(*) AS event_count,
                COUNT(DISTINCT e.session_id) AS session_count,
                COALESCE(SUM(e.input_tokens), 0) AS input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS output_tokens,
                COALESCE(SUM(e.input_tokens), 0) + COALESCE(SUM(e.output_tokens), 0)
                    AS total_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS total_cost_usd
            FROM events e
            WHERE e.timestamp_local IS NOT NULL {f}
            GROUP BY e.project_id, DATE(e.timestamp_local),
                     CAST(STRFTIME('%H', e.timestamp_local) AS INTEGER)
            ORDER BY time_bucket DESC, hour_of_day
        """)

    def get_session_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project)
        return self._q(f"""
            SELECT
                e.project_id, e.session_id, e.model_id,
                COUNT(*) AS event_count,
                MIN(e.timestamp) AS first_timestamp,
                MAX(e.timestamp) AS last_timestamp,
                COALESCE(SUM(e.input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(e.cache_read_tokens), 0) AS total_cache_read_input_tokens,
                COALESCE(SUM(e.cache_creation_tokens), 0) AS total_cache_creation_input_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS total_cost_usd
            FROM events e
            WHERE e.session_id IS NOT NULL {f}
            GROUP BY e.project_id, e.session_id, e.model_id
            ORDER BY last_timestamp DESC
        """)

    def get_sessions_list(
        self,
        *,
        days: int | None = None,
        project: str | None = None,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        f = self._filters(days, project, col_ts="s.last_timestamp", col_proj="s.project_id")
        sort_map: dict[str, str] = {
            "last_active": "s.last_timestamp",
            "events": "s.event_count",
            "subagents": "COALESCE(s.subagent_count, 0)",
            "cost": "ROUND(COALESCE(s.total_cost_usd, 0), 4)",
        }
        col = sort_map.get(sort_by, "s.last_timestamp")
        direction = "ASC" if sort_order.strip().lower() == "asc" else "DESC"
        return self._q(f"""
            SELECT
                s.project_id, s.session_id,
                s.first_timestamp, s.last_timestamp,
                s.event_count, s.subagent_count,
                s.total_input_tokens, s.total_output_tokens,
                s.total_cache_read_tokens, s.total_cache_creation_tokens,
                ROUND(COALESCE(s.total_cost_usd, 0), 4) AS total_cost_usd
            FROM sessions s
            WHERE 1=1 {f}
            ORDER BY {col} {direction}
        """)

    def get_projects(self, *, days: int | None = None) -> list[dict[str, Any]]:
        f = self._filters(days, col_ts="s.last_timestamp", col_proj="s.project_id")
        return self._q(f"""
            SELECT
                s.project_id,
                ROUND(COALESCE(SUM(s.total_cost_usd), 0), 4) AS total_cost_usd,
                COALESCE(SUM(s.event_count), 0) AS event_count,
                COUNT(*) AS session_count
            FROM sessions s
            WHERE 1=1 {f}
            GROUP BY s.project_id
            ORDER BY total_cost_usd DESC
        """)

    def get_top_projects_weekly(self, *, days: int | None = None) -> list[dict[str, Any]]:
        effective_days = days if days is not None else 56
        f = self._filters(effective_days)
        return self._q(f"""
            WITH top_projects AS (
                SELECT e.project_id, ROUND(SUM(e.total_cost_usd), 4) AS total_cost
                FROM events e WHERE e.timestamp IS NOT NULL {f}
                GROUP BY e.project_id ORDER BY total_cost DESC LIMIT 3
            )
            SELECT e.project_id,
                DATE(e.timestamp, 'weekday 0', '-6 days') AS time_bucket,
                COUNT(*) AS event_count,
                COUNT(DISTINCT e.session_id) AS session_count,
                COALESCE(SUM(e.input_tokens), 0) AS input_tokens,
                COALESCE(SUM(e.output_tokens), 0) AS output_tokens,
                COALESCE(SUM(e.input_tokens), 0) + COALESCE(SUM(e.output_tokens), 0)
                    AS total_tokens,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0), 4) AS cost_usd,
                ROUND(COALESCE(SUM(e.total_cost_usd), 0) /
                    NULLIF(COUNT(DISTINCT e.session_id), 0), 4) AS cost_per_session
            FROM events e
            JOIN top_projects tp ON e.project_id = tp.project_id
            WHERE e.timestamp IS NOT NULL {f}
            GROUP BY e.project_id, DATE(e.timestamp, 'weekday 0', '-6 days')
            ORDER BY e.project_id, time_bucket
        """)

    def get_timeline_events(
        self, project_id: str, *, days: int | None = None
    ) -> list[dict[str, Any]]:
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")
        day_filter = days_clause(days)
        return self._q(f"""
            SELECT
                e.project_id, e.session_id, e.uuid, e.event_type,
                e.timestamp, e.model_id, e.output_tokens, e.total_cost_usd,
                SUM(e.output_tokens) OVER (
                    PARTITION BY e.session_id ORDER BY e.timestamp
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_output_tokens,
                MIN(e.timestamp) OVER (PARTITION BY e.session_id) AS session_first_event
            FROM events e
            WHERE e.project_id = ? AND e.timestamp IS NOT NULL {day_filter}
            ORDER BY session_first_event, e.timestamp
        """, (project_id,))

    def get_schema_timeline(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        # Schema timeline is a DuckDB-specific feature (JSON path introspection).
        return []

    def get_session_events(
        self, project_id: str, session_id: str, *, event_uuid: str | None = None
    ) -> list[dict[str, Any]]:
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")
        uuid_clause = ""
        params: tuple[Any, ...] = (project_id, session_id)
        if event_uuid:
            uuid_clause = """AND e.uuid IN (
                WITH RECURSIVE tree(uuid) AS (
                    VALUES(?)
                    UNION ALL
                    SELECT ee.event_uuid FROM event_edges ee
                    JOIN tree t ON ee.parent_event_uuid = t.uuid
                    WHERE ee.session_id = ?
                )
                SELECT uuid FROM tree
            )"""
            params = (project_id, session_id, event_uuid, session_id)
        return self._q(f"""
            SELECT
                e.uuid, e.parent_uuid, e.event_type, e.timestamp,
                e.timestamp_local, e.session_id, e.is_sidechain,
                e.agent_slug, e.message_role,
                e.message_content_json AS message_content,
                e.model_id, e.msg_kind AS message_kind,
                CASE WHEN e.is_sidechain = 1 THEN 1 ELSE 0 END AS is_meta,
                e.input_tokens, e.output_tokens,
                e.cache_read_tokens, e.cache_creation_tokens,
                e.raw_json AS message_json
            FROM events e
            WHERE e.project_id = ? AND e.session_id = ? {uuid_clause}
            ORDER BY e.timestamp
        """, params)

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
