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
from claude_code_sessions.database.raw_json import read_jsonl_line
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

    # ------------------------------------------------------------------
    # Dimensional-aggregate readers
    # ------------------------------------------------------------------
    # All time-bucketed analytical queries read from the `agg` table
    # (filtered by `granularity`) instead of GROUP BY-ing over millions
    # of events. The table is maintained incrementally by CacheManager.

    def _agg_filters(
        self, days: int | None, project: str | None, time_col: str = "a.time_bucket",
    ) -> str:
        """Filter clauses for agg_* reads. Re-uses days/project/domain clauses
        but scoped to the agg table column aliases."""
        parts = [
            days_clause(days, time_col),
            project_clause(project, "a.project_id"),
            domain_clause(self.projects_path, "a.project_id"),
        ]
        return " ".join(p for p in parts if p)

    def get_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        # Roll-up from agg_daily — finest granularity that still gives us
        # a small row count for any sensible time window.
        f = self._agg_filters(days, project)
        return self._q(f"""
            SELECT
                COUNT(DISTINCT a.project_id) AS total_projects,
                COALESCE(SUM(a.event_count), 0) AS total_events,
                COUNT(DISTINCT a.session_id) AS total_sessions,
                COALESCE(SUM(a.input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(a.output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(a.cache_read_tokens), 0) AS total_cache_read_tokens,
                COALESCE(SUM(a.cache_creation_tokens), 0) AS total_cache_creation_tokens,
                ROUND(COALESCE(SUM(a.total_cost_usd), 0), 4) AS grand_total_cost_usd
            FROM agg a
            WHERE a.granularity = 'daily' {f}
        """)

    def get_daily_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._agg_filters(days, project)
        return self._q(f"""
            SELECT
                a.project_id,
                NULLIF(a.model_id, '') AS model_id,
                a.time_bucket,
                SUM(a.event_count) AS event_count,
                COUNT(DISTINCT NULLIF(a.session_id, '')) AS session_count,
                SUM(a.input_tokens) AS total_input_tokens,
                SUM(a.output_tokens) AS total_output_tokens,
                SUM(a.cache_read_tokens) AS total_cache_read_input_tokens,
                SUM(a.cache_creation_tokens) AS total_cache_creation_input_tokens,
                ROUND(SUM(a.total_cost_usd), 4) AS total_cost_usd
            FROM agg a
            WHERE a.granularity = 'daily' {f}
            GROUP BY a.project_id, a.model_id, a.time_bucket
            ORDER BY a.time_bucket DESC
        """)

    def get_weekly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._agg_filters(days, project)
        return self._q(f"""
            SELECT
                a.project_id,
                NULLIF(a.model_id, '') AS model_id,
                a.time_bucket,
                SUM(a.event_count) AS event_count,
                COUNT(DISTINCT NULLIF(a.session_id, '')) AS session_count,
                SUM(a.input_tokens) AS total_input_tokens,
                SUM(a.output_tokens) AS total_output_tokens,
                SUM(a.cache_read_tokens) AS total_cache_read_input_tokens,
                SUM(a.cache_creation_tokens) AS total_cache_creation_input_tokens,
                ROUND(SUM(a.total_cost_usd), 4) AS total_cost_usd
            FROM agg a
            WHERE a.granularity = 'weekly' {f}
            GROUP BY a.project_id, a.model_id, a.time_bucket
            ORDER BY a.time_bucket DESC
        """)

    def get_monthly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        f = self._agg_filters(days, project)
        return self._q(f"""
            SELECT
                a.project_id,
                NULLIF(a.model_id, '') AS model_id,
                a.time_bucket,
                SUM(a.event_count) AS event_count,
                COUNT(DISTINCT NULLIF(a.session_id, '')) AS session_count,
                SUM(a.input_tokens) AS total_input_tokens,
                SUM(a.output_tokens) AS total_output_tokens,
                SUM(a.cache_read_tokens) AS total_cache_read_input_tokens,
                SUM(a.cache_creation_tokens) AS total_cache_creation_input_tokens,
                ROUND(SUM(a.total_cost_usd), 4) AS total_cost_usd
            FROM agg a
            WHERE a.granularity = 'monthly' {f}
            GROUP BY a.project_id, a.model_id, a.time_bucket
            ORDER BY a.time_bucket DESC
        """)

    def get_hourly_usage(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        # Read from agg_hourly. time_bucket is ISO "YYYY-MM-DDTHH:00:00" —
        # we derive the (date, hour_of_day) tuple the frontend expects.
        f = self._agg_filters(days, project)
        return self._q(f"""
            SELECT
                a.project_id,
                SUBSTR(a.time_bucket, 1, 10) AS time_bucket,
                CAST(SUBSTR(a.time_bucket, 12, 2) AS INTEGER) AS hour_of_day,
                SUM(a.event_count) AS event_count,
                COUNT(DISTINCT NULLIF(a.session_id, '')) AS session_count,
                SUM(a.input_tokens) AS input_tokens,
                SUM(a.output_tokens) AS output_tokens,
                SUM(a.input_tokens) + SUM(a.output_tokens) AS total_tokens,
                ROUND(SUM(a.total_cost_usd), 4) AS total_cost_usd
            FROM agg a
            WHERE a.granularity = 'hourly' {f}
            GROUP BY a.project_id,
                     SUBSTR(a.time_bucket, 1, 10),
                     CAST(SUBSTR(a.time_bucket, 12, 2) AS INTEGER)
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
        # Per-session call-type counts + top-skill name are computed from the
        # `event_calls` fact table. Two CTEs:
        #   - call_counts: pivots rows by call_type into one row per session
        #   - top_skills : ROW_NUMBER() over skill invocations per session,
        #                  tied on call_name ASC for a stable winner.
        # LEFT JOIN so sessions without any calls still appear (counts=0,
        # top_skill=NULL).
        return self._q(f"""
            WITH call_counts AS (
                SELECT
                    project_id,
                    session_id,
                    SUM(CASE WHEN call_type = 'tool' THEN 1 ELSE 0 END)
                        AS tool_call_count,
                    SUM(CASE WHEN call_type = 'skill' THEN 1 ELSE 0 END)
                        AS skill_call_count,
                    SUM(CASE WHEN call_type = 'make_target' THEN 1 ELSE 0 END)
                        AS make_target_call_count
                FROM event_calls
                GROUP BY project_id, session_id
            ),
            skill_rank AS (
                SELECT
                    project_id,
                    session_id,
                    call_name,
                    COUNT(*) AS n,
                    ROW_NUMBER() OVER (
                        PARTITION BY project_id, session_id
                        ORDER BY COUNT(*) DESC, call_name ASC
                    ) AS rn
                FROM event_calls
                WHERE call_type = 'skill'
                GROUP BY project_id, session_id, call_name
            )
            SELECT
                s.project_id, s.session_id,
                s.first_timestamp, s.last_timestamp,
                s.event_count, s.subagent_count,
                s.total_input_tokens, s.total_output_tokens,
                s.total_cache_read_tokens, s.total_cache_creation_tokens,
                ROUND(COALESCE(s.total_cost_usd, 0), 4) AS total_cost_usd,
                COALESCE(cc.tool_call_count, 0) AS tool_call_count,
                COALESCE(cc.skill_call_count, 0) AS skill_call_count,
                COALESCE(cc.make_target_call_count, 0) AS make_target_call_count,
                ts.call_name AS top_skill
            FROM sessions s
            LEFT JOIN call_counts cc
                ON cc.project_id = s.project_id
               AND cc.session_id = s.session_id
            LEFT JOIN skill_rank ts
                ON ts.project_id = s.project_id
               AND ts.session_id = s.session_id
               AND ts.rn = 1
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
        # Two-stage query over agg_weekly:
        #   1. Find top 3 projects by total cost in the window
        #   2. Return their weekly breakdown
        # Both stages read from the pre-aggregated table — tiny rows.
        effective_days = days if days is not None else 56
        f = self._agg_filters(effective_days, project=None)
        return self._q(f"""
            WITH top_projects AS (
                SELECT a.project_id, ROUND(SUM(a.total_cost_usd), 4) AS total_cost
                FROM agg a
                WHERE a.granularity = 'weekly' {f}
                GROUP BY a.project_id
                ORDER BY total_cost DESC
                LIMIT 3
            )
            SELECT a.project_id,
                a.time_bucket,
                SUM(a.event_count) AS event_count,
                COUNT(DISTINCT NULLIF(a.session_id, '')) AS session_count,
                SUM(a.input_tokens) AS input_tokens,
                SUM(a.output_tokens) AS output_tokens,
                SUM(a.input_tokens) + SUM(a.output_tokens) AS total_tokens,
                ROUND(SUM(a.total_cost_usd), 4) AS cost_usd,
                ROUND(SUM(a.total_cost_usd) /
                    NULLIF(COUNT(DISTINCT NULLIF(a.session_id, '')), 0), 4)
                    AS cost_per_session
            FROM agg a
            JOIN top_projects tp ON a.project_id = tp.project_id
            WHERE a.granularity = 'weekly' {f}
            GROUP BY a.project_id, a.time_bucket
            ORDER BY a.project_id, a.time_bucket
        """)

    def get_timeline_events(
        self, project_id: str, *, days: int | None = None
    ) -> list[dict[str, Any]]:
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")
        day_filter = days_clause(days)
        # Column names match the frontend `TimelineEvent` type in
        # `api-client.ts`:
        #   event_seq, timestamp_utc, timestamp_local, first_event_time,
        #   input_tokens, output_tokens, cache_read_tokens,
        #   cache_creation_tokens, cache_5m_tokens, total_tokens,
        #   cumulative_output_tokens, message_content.
        # Without the full set, Timeline.tsx crashes at
        # `e.input_tokens.toLocaleString()` during hover-text build.
        return self._q(f"""
            SELECT
                e.project_id,
                e.session_id,
                e.uuid,
                e.event_type,
                e.model_id,
                e.message_content,
                e.timestamp AS timestamp_utc,
                e.timestamp_local,
                MIN(e.timestamp) OVER (PARTITION BY e.session_id)
                    AS first_event_time,
                ROW_NUMBER() OVER (
                    PARTITION BY e.session_id ORDER BY e.timestamp
                ) AS event_seq,
                COALESCE(e.input_tokens, 0) AS input_tokens,
                COALESCE(e.output_tokens, 0) AS output_tokens,
                COALESCE(e.cache_read_tokens, 0) AS cache_read_tokens,
                COALESCE(e.cache_creation_tokens, 0) AS cache_creation_tokens,
                COALESCE(e.cache_5m_tokens, 0) AS cache_5m_tokens,
                COALESCE(e.input_tokens, 0) + COALESCE(e.output_tokens, 0)
                    AS total_tokens,
                SUM(COALESCE(e.output_tokens, 0)) OVER (
                    PARTITION BY e.session_id ORDER BY e.timestamp
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_output_tokens,
                e.total_cost_usd
            FROM events e
            WHERE e.project_id = ? AND e.timestamp IS NOT NULL {day_filter}
            ORDER BY first_event_time, e.timestamp
        """, (project_id,))

    def get_schema_timeline(
        self, *, days: int | None = None, project: str | None = None
    ) -> list[dict[str, Any]]:
        # Schema timeline was a DuckDB-only feature (JSON path
        # introspection over the raw JSONL files). Retained as a stub so
        # the frontend SchemaTimeline page doesn't 404; it will show the
        # empty-state. Re-implement if you need schema-evolution tracking.
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
                -- raw_json intentionally omitted: fetch on demand via
                -- get_event_raw_json(project_id, session_id, uuid)
                NULL AS message_json
            FROM events e
            WHERE e.project_id = ? AND e.session_id = ? {uuid_clause}
            -- NULL timestamps (e.g. last-prompt markers) sort to the END so
            -- the chronologically first real event appears at position 0.
            ORDER BY e.timestamp IS NULL, e.timestamp
        """, params)

    def get_event_raw_json(
        self, project_id: str, session_id: str, event_uuid: str
    ) -> str | None:
        """Fetch raw JSON line from the source JSONL file on demand."""
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")

        cursor = self._cache.conn.cursor()
        row = cursor.execute(
            """
            SELECT sf.filepath, e.line_number
            FROM events e
            JOIN source_files sf ON sf.id = e.source_file_id
            WHERE e.project_id = ? AND e.session_id = ? AND e.uuid = ?
            LIMIT 1
            """,
            (project_id, session_id, event_uuid),
        ).fetchone()

        if row is None:
            return None

        return read_jsonl_line(Path(row["filepath"]), int(row["line_number"]))

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

    # ------------------------------------------------------------------
    # event_calls queries
    # ------------------------------------------------------------------
    # The event_calls table has timestamp/project_id/session_id
    # denormalized off the parent event row so dashboards can filter
    # without joining back to `events`.

    # SQLite time-bucket expressions parallel those in CacheManager. Kept
    # inline here because `agg` doesn't carry call_type/call_name — only
    # additive token measures — so we can't read off it.
    _CALLS_BUCKET_EXPRS: dict[str, str] = {
        "hourly":  "strftime('%Y-%m-%dT%H:00:00', ec.timestamp)",
        "daily":   "date(ec.timestamp)",
        "weekly":  "date(ec.timestamp, 'weekday 0', '-6 days')",
        "monthly": "strftime('%Y-%m-01', ec.timestamp)",
    }

    def _calls_filters(self, days: int | None, project: str | None) -> str:
        """Filter clauses for reads off event_calls.

        Re-uses the same days/project/domain clause builders but with
        ``ec.timestamp`` / ``ec.project_id`` as the column names.
        """
        parts = [
            days_clause(days, "ec.timestamp"),
            project_clause(project, "ec.project_id"),
            domain_clause(self.projects_path, "ec.project_id"),
        ]
        return " ".join(p for p in parts if p)

    def get_calls_timeline(
        self,
        *,
        granularity: str,
        days: int | None = None,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        bucket_expr = self._CALLS_BUCKET_EXPRS.get(granularity)
        if bucket_expr is None:
            raise ValueError(f"unknown granularity: {granularity}")
        f = self._calls_filters(days, project)
        return self._q(f"""
            SELECT
                {bucket_expr} AS time_bucket,
                ec.call_type,
                COUNT(*) AS call_count
            FROM event_calls ec
            WHERE ec.timestamp IS NOT NULL {f}
            GROUP BY time_bucket, ec.call_type
            ORDER BY time_bucket, ec.call_type
        """)

    def get_top_calls(
        self,
        *,
        call_type: str,
        days: int | None = None,
        project: str | None = None,
        limit: int = 20,
        exclude: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        # call_type comes from the API — constrain it to the known set
        # so we can safely interpolate (no user-controlled SQL).
        if call_type not in {"tool", "skill", "subagent", "cli", "rule", "make_target"}:
            raise ValueError(f"unknown call_type: {call_type}")
        safe_limit = max(1, min(int(limit), 500))
        f = self._calls_filters(days, project)

        # Bind exclude list as parameters so arbitrary call names can be
        # passed without SQL-injection risk. Empty list → no clause.
        exclude_clause = ""
        params: tuple[Any, ...] = ()
        if exclude:
            placeholders = ",".join("?" for _ in exclude)
            exclude_clause = f"AND ec.call_name NOT IN ({placeholders})"
            params = tuple(exclude)

        return self._q(f"""
            SELECT
                ec.call_name,
                COUNT(*) AS call_count,
                COUNT(DISTINCT ec.session_id) AS session_count
            FROM event_calls ec
            WHERE ec.call_type = '{call_type}' {f} {exclude_clause}
            GROUP BY ec.call_name
            ORDER BY call_count DESC, ec.call_name ASC
            LIMIT {safe_limit}
        """, params)
