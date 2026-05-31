"""
SQLite implementation of the Database protocol.

Stateful engine backed by a persistent SQLite cache. Incrementally indexes
JSONL session files and serves queries from pre-computed aggregates.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_code_sessions.config import (
    BLOCKED_DOMAINS,
    extract_domain,
    is_project_blocked,
)
from claude_code_sessions.database.raw_json import read_jsonl_line
from claude_code_sessions.database.sqlite.cache import CacheManager, _delta_ms
from claude_code_sessions.database.sqlite.embeddings import (
    EMBED_MAX_CHARS,
    EMBEDDED_MSG_KINDS,
    GGUF_MODEL_NAME,
    ensure_model_downloaded,
    setup_embedding_runtime,
)
from claude_code_sessions.database.sqlite.filters import (
    days_clause,
    domain_clause,
    project_clause,
)
from claude_code_sessions.database.sqlite.kg.payload import (
    DEFAULT_RESOLUTION,
    KGCacheStats,
    KGPayload,
    PipelineStage,
    SeedMetric,
    load_kg_er,
)
from claude_code_sessions.database.sqlite.pricing import (
    READ_TOKENS_PER_SEC,
    TOO_FAST_MIN_TOKENS,
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
        # Initialize the schema eagerly so query endpoints can run while
        # the background indexer is still ingesting (they just return
        # empty results). The full ``ensure_ready()`` — which does the
        # multi-hour ingestion + embedding + KG passes — is NOT called
        # here; ``IndexerService`` drives that from a background thread
        # so the server binds its port immediately on cold start.
        if self._cache.needs_rebuild():
            self._cache.reset()
        else:
            self._cache.init_schema()

    def ensure_ready(self) -> None:
        """Synchronously bring the cache up to date.

        Blocks until all phases complete. Use ``IndexerService`` to drive
        this from a background thread when the caller (e.g. uvicorn) must
        not block on a multi-hour cold start.
        """
        self._cache.ensure_ready(self.projects_path)

    @property
    def cache(self) -> CacheManager:
        """The underlying CacheManager. Exposed for IndexerService and
        for tests that need to drive the cache directly without going
        through the high-level query methods."""
        return self._cache

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

    def _scalar(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """Execute SQL returning a single integer count (0 if NULL/empty)."""
        row = self._cache.conn.execute(sql, params).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _table_exists(self, name: str) -> bool:
        """Whether a table/view exists.

        Used for runtime-created tables like ``chunks_vec_nodes`` (the
        sqlite-muninn HNSW shadow table) which are absent until the
        embedding phase has run at least once. A missing shadow table
        legitimately means "0 processed" for that stage — it is not an
        error, so the cache-stats query checks existence rather than
        letting the count raise ``no such table``.
        """
        row = self._cache.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (name,),
        ).fetchone()
        return row is not None

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
        self,
        days: int | None,
        project: str | None,
        time_col: str = "a.time_bucket",
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
                s.avg_tps, s.total_idle_ms, s.total_active_ms, s.peak_context_ratio,
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
        return self._q(
            f"""
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
        """,
            (project_id,),
        )

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
        return self._q(
            f"""
            SELECT
                e.uuid, e.parent_uuid, e.event_type, e.timestamp,
                e.timestamp_local, e.session_id, e.is_sidechain,
                e.agent_slug, e.message_role,
                e.message_content_json AS message_content,
                e.model_id, e.msg_kind AS message_kind,
                e.is_response_head,
                e.context_tokens, e.context_window, e.context_ratio,
                e.response_duration_ms,
                -- Tokens/sec on a response head: model throughput over its own
                -- generation window. NULL when duration is unknown/zero.
                CASE WHEN e.response_duration_ms > 0
                     THEN ROUND(e.output_tokens * 1000.0 / e.response_duration_ms, 2)
                     ELSE NULL END AS tps,
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
        """,
            params,
        )

    def get_session_summary(self, project_id: str, session_id: str, *, model: str) -> dict[str, Any]:
        """The 3-lens summary for a session under ``model`` (G7, ADR7.1).

        Returns ``{"status": "summarised", "lenses": {...}}`` when a row exists,
        else ``{"status": "not_summarised"}`` — never a fabricated summary.
        """
        rows = self._q(
            """SELECT task_summary, patterns, decisions_values
               FROM session_summaries
               WHERE project_id = ? AND session_id = ? AND model = ?""",
            (project_id, session_id, model),
        )
        if not rows:
            return {"status": "not_summarised"}
        row = rows[0]
        return {
            "status": "summarised",
            "lenses": {
                "task_summary": row["task_summary"],
                "patterns": row["patterns"],
                "decisions_values": row["decisions_values"],
            },
        }

    def get_rollup_summary(
        self,
        scope_path: str,
        time_granularity: str,
        time_bucket: str,
        *,
        strategy: str | None = None,
        model: str | None = None,
        days: int | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """The roll-up summary for a ``scope_path`` at a grain+bucket (G7, ADR7.1).

        ``strategy``/``model`` narrow to a specific benchmark variant when given.
        Returns ``{"status": "summarised", ...}`` or ``{"status": "not_summarised"}``.
        """
        clauses = ["scope_path = ?", "time_granularity = ?", "time_bucket = ?"]
        params: list[Any] = [scope_path, time_granularity, time_bucket]
        if strategy is not None:
            clauses.append("strategy = ?")
            params.append(strategy)
        if model is not None:
            clauses.append("model = ?")
            params.append(model)
        rows = self._q(
            f"SELECT * FROM rollup_summaries WHERE {' AND '.join(clauses)}",
            tuple(params),
        )
        if not rows:
            return {"status": "not_summarised"}
        row = rows[0]
        return {
            "status": "summarised",
            "scope_path": row["scope_path"],
            "scope_depth": row["scope_depth"],
            "time_granularity": row["time_granularity"],
            "time_bucket": row["time_bucket"],
            "strategy": row["strategy"],
            "model": row["model"],
            "child_count": row["child_count"],
            "lenses": {
                "task_summary": row["task_summary"],
                "patterns": row["patterns"],
                "decisions_values": row["decisions_values"],
            },
        }

    def get_session_metrics(self, project_id: str, session_id: str) -> list[dict[str, Any]]:
        """Per-turn idle timing for a session's main thread.

        Idle is the gap from an assistant turn-end (``stop_reason='end_turn'``
        on the response head) to the next event in the main thread, via a
        ``LEAD()`` window ordered by timestamp. Only ``is_sidechain = 0``
        events participate, so subagent activity never counts as human idle.
        One row per assistant end-of-turn head.
        """
        if is_project_blocked(project_id):
            raise LookupError(f"Project not found: {project_id}")
        # All main-thread events in time order. We walk them once, tracking the
        # most recent human prompt; at each assistant turn-end head we emit a
        # turn with its active span (human → turn-end) and idle span
        # (turn-end → next event).
        rows = self._q(
            """
            SELECT e.uuid, e.event_type, e.msg_kind, e.timestamp,
                   e.stop_reason, e.is_response_head, e.output_tokens,
                   e.response_duration_ms
            FROM events e
            WHERE e.project_id = ? AND e.session_id = ? AND e.is_sidechain = 0
            ORDER BY e.timestamp IS NULL, e.timestamp
            """,
            (project_id, session_id),
        )
        turns: list[dict[str, Any]] = []
        last_human_ts: str | None = None
        for i, r in enumerate(rows):
            if r["msg_kind"] == "human":
                last_human_ts = r["timestamp"]
            is_turn_end = (
                r["event_type"] == "assistant"
                and r["is_response_head"] == 1
                and r["stop_reason"] == "end_turn"
            )
            if not is_turn_end:
                continue
            next_ts = rows[i + 1]["timestamp"] if i + 1 < len(rows) else None
            idle_ms = _delta_ms(r["timestamp"], next_ts)
            output_tokens = r["output_tokens"] or 0
            duration_ms = r["response_duration_ms"]
            tps = round(output_tokens / (duration_ms / 1000), 2) if duration_ms else None
            # too_fast: the human replied faster than even a fast skim of this
            # response could be read — but only for responses long enough to
            # be worth reading (≥ the min-token floor).
            too_fast = (
                idle_ms is not None
                and output_tokens >= TOO_FAST_MIN_TOKENS
                and (idle_ms / 1000) < (output_tokens / READ_TOKENS_PER_SEC)
            )
            turns.append(
                {
                    "uuid": r["uuid"],
                    "timestamp": r["timestamp"],
                    "output_tokens": output_tokens,
                    "response_duration_ms": duration_ms,
                    "tps": tps,
                    "active_ms": _delta_ms(last_human_ts, r["timestamp"]),
                    "idle_ms": idle_ms,
                    "too_fast": too_fast,
                }
            )
        return turns

    def get_performance_summary(
        self, *, days: int | None = None, project: str | None = None
    ) -> dict[str, Any]:
        """Cross-session performance: per-model TPS rows + a context-ratio
        histogram, honoring the global days/project filters.

        One ordered pass over in-scope main-thread events: response heads feed
        per-model TPS and the ratio histogram; the turn walk (assistant
        end_turn → next event) feeds per-model idle/active. No zone labels —
        utilization is the raw context_ratio (G2 ADR "Quantitative ratio only").
        """
        f = self._filters(days, project)
        rows = self._q(
            f"""
            SELECT e.session_id, e.model_id, e.event_type, e.msg_kind, e.timestamp,
                   e.stop_reason, e.is_response_head, e.output_tokens,
                   e.response_duration_ms, e.context_ratio
            FROM events e
            WHERE e.session_id IS NOT NULL AND e.is_sidechain = 0 {f}
            ORDER BY e.session_id, e.timestamp IS NULL, e.timestamp
            """,
            (),
        )

        by_model: dict[str, dict[str, Any]] = {}

        def _bucket(model_id: str) -> dict[str, Any]:
            return by_model.setdefault(
                model_id,
                {"tps": [], "output": 0, "dur": 0, "count": 0, "idle": 0, "active": 0},
            )

        ratio_bins = [0] * 10  # 0–10%, 10–20%, …, 90–100%
        cur_session: str | None = None
        last_human_ts: str | None = None
        for i, r in enumerate(rows):
            if r["session_id"] != cur_session:
                cur_session = r["session_id"]
                last_human_ts = None
            is_head = (
                r["event_type"] == "assistant" and r["is_response_head"] == 1 and r["model_id"]
            )
            if is_head:
                m = _bucket(r["model_id"])
                m["count"] += 1
                dur = r["response_duration_ms"]
                if dur:
                    out = r["output_tokens"] or 0
                    m["output"] += out
                    m["dur"] += dur
                    m["tps"].append(out / (dur / 1000))
                cr = r["context_ratio"]
                if cr is not None:
                    ratio_bins[min(int(cr * 10), 9)] += 1
            if r["msg_kind"] == "human":
                last_human_ts = r["timestamp"]
            if (
                r["event_type"] == "assistant"
                and r["is_response_head"] == 1
                and r["stop_reason"] == "end_turn"
                and r["model_id"]
            ):
                same_session_next = i + 1 < len(rows) and rows[i + 1]["session_id"] == cur_session
                next_ts = rows[i + 1]["timestamp"] if same_session_next else None
                m = _bucket(r["model_id"])
                idle = _delta_ms(r["timestamp"], next_ts)
                active = _delta_ms(last_human_ts, r["timestamp"])
                m["idle"] += idle or 0
                m["active"] += active or 0

        by_model_rows = [
            {
                "model_id": model_id,
                "response_count": m["count"],
                "avg_tps": round(m["output"] / (m["dur"] / 1000), 2) if m["dur"] else None,
                "median_tps": round(statistics.median(m["tps"]), 2) if m["tps"] else None,
                "total_idle_ms": m["idle"],
                "total_active_ms": m["active"],
            }
            for model_id, m in sorted(by_model.items())
        ]
        ratio_histogram = [
            {"bin_lo": round(b / 10, 1), "bin_hi": round((b + 1) / 10, 1), "count": c}
            for b, c in enumerate(ratio_bins)
        ]
        return {"by_model": by_model_rows, "ratio_histogram": ratio_histogram}

    def search_events(
        self,
        query: str,
        *,
        days: int | None = None,
        project: str | None = None,
        msg_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        # Empty / whitespace-only queries short-circuit — FTS5 MATCH with
        # an empty string raises, and a no-query search has no
        # meaningful ranking anyway.
        cleaned = query.strip()
        if not cleaned:
            return []

        safe_limit = max(1, min(int(limit), 500))
        # FTS5 requires a syntactically valid MATCH expression. Users
        # type free-form phrases like ``make target error`` which is
        # not valid FTS5 (it's three unquoted tokens at sentence
        # boundary). The safe pattern: split on whitespace, wrap each
        # non-empty token in double quotes, AND them together. Internal
        # double-quote characters are FTS5-escaped by doubling.
        tokens = [t.replace('"', '""') for t in cleaned.split() if t]
        fts_query = " AND ".join(f'"{t}"' for t in tokens)

        # Time and project filters use the same helpers as other reads,
        # but apply to the joined events table (events_fts itself has
        # no timestamp / project columns — they live on the content
        # table it's bound to).
        f = self._filters(days, project, col_ts="e.timestamp", col_proj="e.project_id")

        # Optional kind filter. Applied server-side *before* the LIMIT so
        # a request for "top 50 human prompts" actually returns the top
        # 50 human prompts — not a post-filtered subset of the global
        # top 50. Whitelisted to the 9 derived kinds plus an empty
        # sentinel (treated as no filter).
        kind_clause = ""
        params: tuple[Any, ...] = (fts_query,)
        if msg_kind:
            allowed = {
                "human",
                "task_notification",
                "tool_result",
                "user_text",
                "meta",
                "assistant_text",
                "thinking",
                "tool_use",
                "other",
            }
            if msg_kind in allowed:
                kind_clause = "AND e.msg_kind = ?"
                params = (fts_query, msg_kind)

        # ``snippet()`` highlights the matched terms in a 200-char window.
        # ``bm25()`` ranks by TF-IDF-like relevance; lower = more relevant.
        return self._q(
            f"""
            SELECT
                e.project_id,
                e.session_id,
                e.uuid,
                e.event_type,
                e.msg_kind AS message_kind,
                e.timestamp,
                e.timestamp_local,
                e.model_id,
                snippet(events_fts, 0, '<mark>', '</mark>', '…', 32) AS snippet,
                bm25(events_fts) AS rank
            FROM events_fts
            JOIN events e ON events_fts.rowid = e.id
            WHERE events_fts MATCH ?
              AND e.timestamp IS NOT NULL
              {kind_clause}
              {f}
            ORDER BY rank
            LIMIT {safe_limit}
        """,
            params,
        )

    # -----------------------------------------------------------------
    # Semantic search — vector KNN against the HNSW chunk index
    # -----------------------------------------------------------------

    def _ensure_muninn_runtime(self) -> bool:
        """Ensure sqlite-muninn is loaded + the GGUF model is registered
        on this connection.

        Returns True if the runtime is ready for ``muninn_embed()`` calls,
        False if the embedding feature is unavailable (model missing
        AND not downloadable, or the chunks_vec table doesn't exist).

        Idempotent: ``setup_embedding_runtime`` short-circuits when the
        model is already in ``temp.muninn_models`` and the HNSW virtual
        table is already declared.
        """
        # If chunks_vec_nodes doesn't exist, embeddings were never built
        # and there's nothing to search. We return False here rather than
        # raising so the HTTP layer can serve an empty list gracefully —
        # this is "feature not available" signalling, not an error.
        row = self._cache.conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'chunks_vec_nodes'"
        ).fetchone()
        if row is None:
            return False

        # ensure_model_downloaded() will block for ~10 s on a slow link
        # but we've already paid that cost once; subsequent calls are a
        # file-exists check. If the file is gone (user cleaned the cache
        # dir) we re-download — loud failure there is correct, so we
        # don't swallow the exception.
        model_path = ensure_model_downloaded()
        setup_embedding_runtime(self._cache.conn, model_path)
        return True

    def semantic_search_events(
        self,
        query: str,
        *,
        days: int | None = None,
        project: str | None = None,
        msg_kind: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        cleaned = query.strip()
        if not cleaned:
            return []
        # Only human prompts are embedded today (see EMBEDDED_MSG_KINDS).
        # Requesting any other kind can't produce hits — short-circuit.
        if msg_kind and msg_kind not in EMBEDDED_MSG_KINDS:
            return []

        if not self._ensure_muninn_runtime():
            return []

        safe_limit = max(1, min(int(limit), 500))
        # Over-fetch 4× so post-filters (days/project) still leave enough
        # results. The HNSW index itself can't pre-filter: muninn's KNN
        # returns exactly ``k`` rows regardless of our WHERE clause.
        # Without over-fetching, a project-scoped query could see the
        # top-50 global matches collapse to <10 after filtering.
        knn_k = min(safe_limit * 4, 500)
        # Truncate query text the same way we truncate chunks when
        # embedding them — the query and stored vectors must come from
        # the same tokenizer-window regime to be comparable.
        embed_text = cleaned[:EMBED_MAX_CHARS]

        f = self._filters(days, project, col_ts="e.timestamp", col_proj="e.project_id")
        kind_clause = ""
        extra_params: tuple[Any, ...] = ()
        if msg_kind:
            kind_clause = "AND e.msg_kind = ?"
            extra_params = (msg_kind,)

        # Query shape:
        #   1. ann CTE: HNSW KNN — returns (chunk_id, distance) for the
        #      top-k nearest chunks. Embedding happens server-side via
        #      muninn_embed() directly in the MATCH clause — no round
        #      trip to the client for the vector blob.
        #   2. JOIN through event_message_chunks → events to recover
        #      project/session/timestamp/model context + apply filters.
        #   3. ORDER BY distance, cap at safe_limit.
        #
        # ``rank`` is aliased to ``distance`` so the response shape
        # matches the FTS search's ``rank`` field (both lower-is-better).
        return self._q(
            f"""
            WITH ann AS (
                SELECT rowid AS chunk_id, distance
                FROM chunks_vec
                WHERE vector MATCH muninn_embed(?, ?) AND k = ?
            )
            SELECT
                e.project_id,
                e.session_id,
                e.uuid,
                e.event_type,
                e.msg_kind AS message_kind,
                e.timestamp,
                e.timestamp_local,
                e.model_id,
                emc.text AS snippet,
                ann.distance AS rank
            FROM ann
            JOIN event_message_chunks emc ON emc.chunk_id = ann.chunk_id
            JOIN events e ON e.id = emc.event_id
            WHERE e.timestamp IS NOT NULL
              {kind_clause}
              {f}
            ORDER BY ann.distance
            LIMIT {safe_limit}
        """,
            (GGUF_MODEL_NAME, embed_text, knn_k) + extra_params,
        )

    def get_event_raw_json(self, project_id: str, session_id: str, event_uuid: str) -> str | None:
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
        "hourly": "strftime('%Y-%m-%dT%H:00:00', ec.timestamp)",
        "daily": "date(ec.timestamp)",
        "weekly": "date(ec.timestamp, 'weekday 0', '-6 days')",
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
        if call_type not in {
            "tool",
            "skill",
            "subagent",
            "cli",
            "rule",
            "make_target",
            "uv_script",
            "bun_script",
        }:
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

        return self._q(
            f"""
            SELECT
                ec.call_name,
                COUNT(*) AS call_count,
                COUNT(DISTINCT ec.session_id) AS session_count
            FROM event_calls ec
            WHERE ec.call_type = '{call_type}' {f} {exclude_clause}
            GROUP BY ec.call_name
            ORDER BY call_count DESC, ec.call_name ASC
            LIMIT {safe_limit}
        """,
            params,
        )

    # -- Knowledge graph ----------------------------------------------------

    def get_kg_er(
        self,
        *,
        resolution: float | None = None,
        top_n: int = 50,
        seed_metric: SeedMetric = "edge_betweenness",
        max_depth: int = 0,
        min_degree: int = 1,
        days: int | None = None,
        project: str | None = None,
    ) -> KGPayload:
        return load_kg_er(
            self._cache.conn,
            resolution=resolution,
            top_n=top_n,
            seed_metric=seed_metric,
            max_depth=max_depth,
            min_degree=min_degree,
            days=days,
            project=project,
        )

    def get_kg_cache_stats(self) -> KGCacheStats:
        """Per-stage backlog snapshot of the cache → knowledge-graph pipeline.

        Global by design — the indexer walks the entire projects tree, so
        these counts are NOT filtered by ``days`` / ``project``. Each
        stage's "done" definition mirrors the pipeline's own incremental
        skip query so the backlog numbers match what the next wave will
        actually process:

        * ingest      — ``*.jsonl`` files on disk vs rows in ``source_files``
        * chunk       — human events with content not yet in ``event_message_chunks``
                        (matches ``embeddings.sync_chunks``)
        * embed       — chunks not yet in ``chunks_vec_nodes`` (matches
                        ``embeddings.sync_embeddings``; shadow table may be absent)
        * ner / re    — chunks not yet logged in ``ner_chunks_log`` / ``re_chunks_log``
        * entity_embed— distinct entity names not yet in ``entity_vec_map``
        * resolve     — ``entity_vec_map`` vs ``entity_clusters`` (rebuilt wholesale)
        * communities — canonical nodes vs nodes assigned in ``leiden_communities``
        * naming      — distinct (resolution, community) vs ``community_labels``

        The ``indexer`` field is left empty here and populated by the API
        route from ``IndexerService.status()`` — the database layer has no
        handle on the background thread.
        """
        # --- Stage: ingest --------------------------------------------------
        try:
            files_on_disk = sum(1 for _ in self.projects_path.rglob("*.jsonl"))
        except FileNotFoundError:
            files_on_disk = 0
        source_files = self._scalar("SELECT COUNT(*) FROM source_files")

        # --- Stage: chunk ---------------------------------------------------
        kinds = ",".join("?" * len(EMBEDDED_MSG_KINDS))
        chunk_where = (
            f"e.message_content IS NOT NULL AND e.message_content != '' AND e.msg_kind IN ({kinds})"
        )
        chunk_eligible = self._scalar(
            f"SELECT COUNT(*) FROM events e WHERE {chunk_where}",
            EMBEDDED_MSG_KINDS,
        )
        chunk_pending = self._scalar(
            f"SELECT COUNT(*) FROM events e WHERE {chunk_where} "
            f"AND e.id NOT IN (SELECT DISTINCT event_id FROM event_message_chunks)",
            EMBEDDED_MSG_KINDS,
        )
        chunks_total = self._scalar("SELECT COUNT(*) FROM event_message_chunks")

        # --- Stage: embed ---------------------------------------------------
        # chunks_vec_nodes is created at runtime by sqlite-muninn; absent
        # until the embedding phase runs once → legitimately 0 embedded.
        embed_done = (
            self._scalar("SELECT COUNT(*) FROM chunks_vec_nodes")
            if self._table_exists("chunks_vec_nodes")
            else 0
        )

        # --- Stages: NER / RE ----------------------------------------------
        ner_done = self._scalar("SELECT COUNT(*) FROM ner_chunks_log")
        re_done = self._scalar("SELECT COUNT(*) FROM re_chunks_log")

        # --- Stage: entity embeddings --------------------------------------
        unique_entities = self._scalar("SELECT COUNT(DISTINCT name) FROM entities")
        entity_embed_done = self._scalar("SELECT COUNT(*) FROM entity_vec_map")

        # --- Stage: entity resolution --------------------------------------
        cluster_done = self._scalar("SELECT COUNT(*) FROM entity_clusters")
        nodes_total = self._scalar("SELECT COUNT(*) FROM nodes")
        edges_total = self._scalar("SELECT COUNT(*) FROM edges")

        # --- Stage: communities / naming -----------------------------------
        # Leiden runs at SEVERAL resolutions over the SAME nodes, so counting
        # communities across all resolutions multi-counts them (e.g. 3 resolutions
        # → ~3x the real number). Report against the single resolution the graph
        # page actually displays — mirroring load_kg_er's choice: prefer
        # DEFAULT_RESOLUTION, else the smallest available.
        resolutions = [
            row[0]
            for row in self._cache.conn.execute(
                "SELECT DISTINCT resolution FROM leiden_communities ORDER BY resolution"
            ).fetchall()
        ]
        display_resolution: float | None = None
        if resolutions:
            display_resolution = (
                DEFAULT_RESOLUTION if DEFAULT_RESOLUTION in resolutions else resolutions[0]
            )
            nodes_in_comm = self._scalar(
                "SELECT COUNT(DISTINCT node) FROM leiden_communities WHERE resolution = ?",
                (display_resolution,),
            )
            communities_total = self._scalar(
                "SELECT COUNT(DISTINCT community_id) FROM leiden_communities WHERE resolution = ?",
                (display_resolution,),
            )
            community_labels_done = self._scalar(
                "SELECT COUNT(*) FROM community_labels WHERE resolution = ?",
                (display_resolution,),
            )
        else:
            nodes_in_comm = 0
            communities_total = 0
            community_labels_done = 0

        events_total = self._scalar("SELECT COUNT(*) FROM events")
        entities_total = self._scalar("SELECT COUNT(*) FROM entities")
        relations_total = self._scalar("SELECT COUNT(*) FROM relations")

        def _stage(
            key: str, label: str, eligible: int, done: int, note: str | None = None
        ) -> PipelineStage:
            # Clamp: a stage can't be more than 100% covered. Re-ingests can
            # leave orphaned downstream rows (e.g. vectors / log entries for
            # chunks since deleted), so a raw ``done`` count may transiently
            # exceed ``eligible`` — coverage is "of eligible, how many done".
            done = min(done, eligible)
            pending = max(0, eligible - done)
            percent = round(100.0 * done / eligible, 1) if eligible > 0 else 0.0
            return PipelineStage(
                key=key,
                label=label,
                eligible=eligible,
                done=done,
                pending=pending,
                percent=percent,
                note=note,
            )

        stages = [
            _stage(
                "ingest",
                "Ingest source files",
                files_on_disk,
                source_files,
                note="*.jsonl files on disk vs rows in source_files.",
            ),
            _stage("chunk", "Chunk human messages", chunk_eligible, chunk_eligible - chunk_pending),
            _stage("embed", "Embed chunks", chunks_total, embed_done),
            _stage("ner", "Extract entities (NER)", chunks_total, ner_done),
            _stage("re", "Extract relations (RE)", chunks_total, re_done),
            _stage("entity_embed", "Embed entity names", unique_entities, entity_embed_done),
            _stage(
                "resolve",
                "Resolve entities",
                entity_embed_done,
                cluster_done,
                note="Rebuilt wholesale when new entity embeddings appear.",
            ),
            _stage(
                # Leiden rebuilds the whole graph each run — it is NOT a
                # per-node backlog. Scoring done/eligible against all nodes
                # made isolated entities (most of the graph) look like a
                # perpetual backlog. Score it as a wholesale stage: built
                # (100%) once communities exist, with the real numbers in
                # the note.
                "communities",
                "Detect communities (Leiden)",
                nodes_in_comm,
                nodes_in_comm,
                note=(
                    f"Wholesale rebuild each run: {communities_total} communities over "
                    f"{nodes_in_comm} connected nodes (isolated entities are unassigned by design)."
                ),
            ),
            _stage(
                "naming",
                f"Name communities (resolution {display_resolution})"
                if display_resolution is not None
                else "Name communities",
                communities_total,
                community_labels_done,
            ),
        ]

        return KGCacheStats(
            generated_at=datetime.now(UTC).isoformat(),
            indexer={},
            files_on_disk=files_on_disk,
            source_files=source_files,
            events_total=events_total,
            chunks_total=chunks_total,
            entities_total=entities_total,
            relations_total=relations_total,
            unique_entities=unique_entities,
            nodes_total=nodes_total,
            edges_total=edges_total,
            communities_total=communities_total,
            display_resolution=display_resolution,
            stages=stages,
        )
