"""
CacheManager for the SQLite session cache.

Handles schema initialization, file discovery, incremental ingestion,
and aggregate table rebuilding. Adapted from the introspect skill script.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claude_code_sessions.database.sqlite.pricing import compute_event_costs, message_kind
from claude_code_sessions.database.sqlite.schema import CACHE_DB_PATH, SCHEMA_SQL, SCHEMA_VERSION

log = logging.getLogger(__name__)


class CacheManager:
    """Manages the SQLite cache for session data."""

    def __init__(self, db_path: Path = CACHE_DB_PATH) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        log.info("Initializing cache schema at %s", self.db_path)
        self.conn.executescript(SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR REPLACE INTO cache_metadata (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        self.conn.execute(
            "INSERT OR REPLACE INTO cache_metadata (key, value) VALUES (?, ?)",
            ("created_at", datetime.now(UTC).isoformat()),
        )
        self.conn.commit()
        log.info("Cache schema initialized (version %s)", SCHEMA_VERSION)

    def needs_rebuild(self) -> bool:
        try:
            row = self.conn.execute(
                "SELECT value FROM cache_metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                return True
            return bool(row[0] != SCHEMA_VERSION)
        except sqlite3.OperationalError:
            return True

    def reset(self) -> None:
        log.warning("Resetting cache database — schema version mismatch")
        self.close()
        if self.db_path.exists():
            self.db_path.unlink()
        self.init_schema()

    # -- File discovery ------------------------------------------------------

    def discover_files(self, projects_path: Path) -> list[dict[str, Any]]:
        """Discover all JSONL session files under the projects directory."""
        files: list[dict[str, Any]] = []
        if not projects_path.exists():
            return files

        for project_dir in projects_path.iterdir():
            if not project_dir.is_dir():
                continue
            project_id = project_dir.name
            for jsonl_file in project_dir.rglob("*.jsonl"):
                rel_path = jsonl_file.relative_to(project_dir)
                parts = rel_path.parts
                file_info: dict[str, Any] = {
                    "filepath": str(jsonl_file),
                    "project_id": project_id,
                    "session_id": None,
                    "file_type": "unknown",
                }
                if len(parts) == 1:
                    filename = parts[0]
                    if filename.startswith("agent-"):
                        file_info["file_type"] = "agent_root"
                    else:
                        file_info["session_id"] = filename.replace(".jsonl", "")
                        file_info["file_type"] = "main_session"
                elif len(parts) >= 2 and "subagents" in parts:
                    file_info["session_id"] = parts[0]
                    file_info["file_type"] = "subagent"
                elif len(parts) == 2:
                    file_info["session_id"] = parts[0]
                    file_info["file_type"] = "subagent"
                files.append(file_info)
        return files

    def get_files_needing_update(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Filter to files that are new or modified since last ingestion."""
        cursor = self.conn.cursor()
        needs_update: list[dict[str, Any]] = []
        for file_info in files:
            filepath = file_info["filepath"]
            try:
                stat = os.stat(filepath)
                current_mtime = stat.st_mtime
                current_size = stat.st_size
            except OSError:
                continue
            cached = cursor.execute(
                "SELECT mtime, size_bytes FROM source_files WHERE filepath = ?", (filepath,)
            ).fetchone()
            if cached is None:
                file_info["mtime"] = current_mtime
                file_info["size_bytes"] = current_size
                file_info["reason"] = "new"
                needs_update.append(file_info)
            elif cached["mtime"] != current_mtime or cached["size_bytes"] != current_size:
                file_info["mtime"] = current_mtime
                file_info["size_bytes"] = current_size
                file_info["reason"] = "modified"
                needs_update.append(file_info)
        return needs_update

    # -- Ingestion -----------------------------------------------------------

    def ingest_file(self, file_info: dict[str, Any]) -> int:
        """Ingest a single JSONL file into the cache. Returns event count."""
        filepath = file_info["filepath"]
        project_id = file_info["project_id"]
        session_id = file_info.get("session_id")
        file_type = file_info["file_type"]
        mtime = file_info["mtime"]
        size_bytes = file_info["size_bytes"]

        cursor = self.conn.cursor()

        # Delete existing data for this file (if re-ingesting)
        existing = cursor.execute(
            "SELECT id FROM source_files WHERE filepath = ?", (filepath,)
        ).fetchone()
        if existing:
            cursor.execute("DELETE FROM event_edges WHERE source_file_id = ?", (existing[0],))
            cursor.execute("DELETE FROM events WHERE source_file_id = ?", (existing[0],))
            cursor.execute("DELETE FROM source_files WHERE id = ?", (existing[0],))

        events_data: list[dict[str, Any]] = []
        line_count = 0
        detected_session_id = session_id

        try:
            with open(filepath, encoding="utf-8") as f:
                for line_num, line in enumerate(f, start=1):
                    line_count = line_num
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if file_type == "agent_root" and detected_session_id is None:
                        detected_session_id = raw.get("sessionId")
                    event = self._parse_event(raw, line_num)
                    if event:
                        events_data.append(event)
        except (FileNotFoundError, PermissionError) as e:
            log.warning("Could not read %s: %s", filepath, e)
            return 0

        cursor.execute(
            """INSERT INTO source_files
               (filepath, mtime, size_bytes, line_count, last_ingested_at,
                project_id, session_id, file_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (filepath, mtime, size_bytes, line_count, datetime.now(UTC).isoformat(),
             project_id, detected_session_id, file_type),
        )
        source_file_id = cursor.lastrowid
        # Expose the new id to the caller so update() can scope agg refresh
        # to the timestamp window of the files it just ingested.
        file_info["source_file_id"] = source_file_id

        for event in events_data:
            cursor.execute(
                """INSERT INTO events
                   (uuid, parent_uuid, prompt_id, event_type, msg_kind,
                    timestamp, timestamp_local, session_id, project_id,
                    is_sidechain, agent_id, agent_slug,
                    message_role, message_content, message_content_json, model_id,
                    input_tokens, output_tokens, cache_read_tokens,
                    cache_creation_tokens, cache_5m_tokens,
                    token_rate, billable_tokens, total_cost_usd,
                    source_file_id, line_number, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (event["uuid"], event["parent_uuid"], event["prompt_id"],
                 event["event_type"], event["msg_kind"],
                 event["timestamp"], event["timestamp_local"],
                 detected_session_id, project_id,
                 event["is_sidechain"], event["agent_id"], event["agent_slug"],
                 event["message_role"], event["message_content"],
                 event["message_content_json"], event["model_id"],
                 event["input_tokens"], event["output_tokens"],
                 event["cache_read_tokens"], event["cache_creation_tokens"],
                 event["cache_5m_tokens"],
                 event["token_rate"], event["billable_tokens"], event["total_cost_usd"],
                 source_file_id, event["line_number"], event["raw_json"]),
            )

        for event in events_data:
            if event["uuid"] and event["parent_uuid"]:
                cursor.execute(
                    """INSERT INTO event_edges
                       (project_id, session_id, event_uuid, parent_event_uuid, source_file_id)
                       VALUES (?, ?, ?, ?, ?)""",
                    (project_id, detected_session_id,
                     event["uuid"], event["parent_uuid"], source_file_id),
                )

        return len(events_data)

    def _parse_event(self, raw: dict[str, Any], line_number: int) -> dict[str, Any] | None:
        """Parse a raw JSON event dict for cache insertion."""
        event_type = raw.get("type", "")
        if event_type == "file-history-snapshot":
            return None

        timestamp = raw.get("timestamp")
        uuid = raw.get("uuid")
        parent_uuid = raw.get("parentUuid")
        prompt_id = raw.get("promptId")
        is_sidechain = raw.get("isSidechain", False)
        agent_id = raw.get("agentId")
        agent_slug = raw.get("slug")
        is_meta = raw.get("isMeta", False)

        message = raw.get("message", {}) or {}
        message_role = message.get("role") if isinstance(message, dict) else None
        content_raw = message.get("content") if isinstance(message, dict) else None
        model_id = message.get("model") if isinstance(message, dict) else None

        # Strip signatures from thinking blocks
        if isinstance(content_raw, list):
            content_raw = [
                {k: v for k, v in block.items() if k != "signature"}
                if isinstance(block, dict)
                and block.get("type") == "thinking"
                and "signature" in block
                else block
                for block in content_raw
            ]

        msg_kind = message_kind(event_type, bool(is_meta), content_raw)
        text = self._extract_text(content_raw)

        usage = message.get("usage", {}) if isinstance(message, dict) else {}
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0
        cache_read_tokens = usage.get("cache_read_input_tokens", 0) or 0
        cache_creation_tokens = usage.get("cache_creation_input_tokens", 0) or 0
        cache_creation = usage.get("cache_creation", {}) or {}
        cache_5m_tokens = cache_creation.get("ephemeral_5m_input_tokens", 0) or 0

        token_rate, billable_tokens, total_cost_usd = compute_event_costs(
            model_id, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
        )

        timestamp_local = None
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp_local = dt.astimezone().isoformat()
            except (ValueError, TypeError):
                pass

        return {
            "uuid": uuid, "parent_uuid": parent_uuid, "prompt_id": prompt_id,
            "event_type": event_type, "msg_kind": msg_kind,
            "timestamp": timestamp, "timestamp_local": timestamp_local,
            "is_sidechain": 1 if is_sidechain else 0,
            "agent_id": agent_id, "agent_slug": agent_slug,
            "message_role": message_role, "message_content": text,
            "message_content_json": json.dumps(content_raw) if content_raw else None,
            "model_id": model_id,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_5m_tokens": cache_5m_tokens,
            "token_rate": token_rate, "billable_tokens": billable_tokens,
            "total_cost_usd": total_cost_usd,
            # raw_json is intentionally empty — the source-of-truth for the
            # raw payload is the JSONL file on disk (see source_files.filepath
            # + line_number). Storing a duplicate copy here was costing 2+ GB
            # and leaking thinking-block signatures into the cache. Use
            # `SQLiteDatabase.get_event_raw_json(event_id)` to fetch on demand.
            "line_number": line_number, "raw_json": "",
        }

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Extract plain text from message content for FTS indexing."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        parts.append(block.get("thinking", ""))
                    elif block.get("type") == "tool_use":
                        parts.append(f"[tool: {block.get('name', '')}]")
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(filter(None, parts))
        return ""

    # -- Aggregates ----------------------------------------------------------

    # SQLite expressions that truncate timestamp to each granularity.
    # Used by refresh_aggregates_for_range() to rebuild agg_* tables.
    _AGG_BUCKET_EXPRS: dict[str, str] = {
        "hourly":  "strftime('%Y-%m-%dT%H:00:00', timestamp)",
        "daily":   "date(timestamp)",
        "weekly":  "date(timestamp, 'weekday 0', '-6 days')",
        "monthly": "strftime('%Y-%m-01', timestamp)",
    }

    def _refresh_one_agg(
        self, cursor: sqlite3.Cursor, granularity: str, bucket_expr: str,
        start: str | None, end: str | None,
    ) -> int:
        """Delete + re-insert agg rows for one granularity in a time range.

        If start/end are None, processes the entire events table (cold rebuild).
        Returns the number of agg rows inserted.
        """
        table = f"agg_{granularity}"

        if start is None or end is None:
            cursor.execute(f"DELETE FROM {table}")
        else:
            cursor.execute(
                f"DELETE FROM {table} WHERE time_bucket >= ? AND time_bucket <= ?",
                (start, end),
            )

        # Build the range predicate for the INSERT SELECT
        range_clause = ""
        range_params: tuple[Any, ...] = ()
        if start is not None and end is not None:
            # Filter the source events by the bucketed range. We use the
            # computed time_bucket for the filter so only events whose bucket
            # falls inside [start, end] are processed — matches the DELETE.
            range_clause = f"AND {bucket_expr} BETWEEN ? AND ?"
            range_params = (start, end)

        cursor.execute(f"""
            INSERT INTO {table} (
                time_bucket, project_id, session_id, model_id,
                event_count,
                input_tokens, output_tokens,
                cache_read_tokens, cache_creation_tokens,
                total_cost_usd, billable_tokens
            )
            SELECT
                {bucket_expr} AS time_bucket,
                project_id,
                COALESCE(session_id, ''),
                COALESCE(model_id, ''),
                COUNT(*),
                COALESCE(SUM(input_tokens), 0),
                COALESCE(SUM(output_tokens), 0),
                COALESCE(SUM(cache_read_tokens), 0),
                COALESCE(SUM(cache_creation_tokens), 0),
                COALESCE(SUM(total_cost_usd), 0.0),
                COALESCE(SUM(billable_tokens), 0.0)
            FROM events
            WHERE timestamp IS NOT NULL
              {range_clause}
            GROUP BY {bucket_expr}, project_id,
                     COALESCE(session_id, ''), COALESCE(model_id, '')
        """, range_params)

        return cursor.rowcount

    def _agg_tables_empty(self) -> bool:
        """True if ALL agg tables are empty (first run after schema upgrade)."""
        cursor = self.conn.cursor()
        for granularity in self._AGG_BUCKET_EXPRS:
            count = cursor.execute(f"SELECT COUNT(*) FROM agg_{granularity}").fetchone()[0]
            if count > 0:
                return False
        return True

    def _timestamp_window_for_files(
        self, source_file_ids: list[int],
    ) -> tuple[str, str] | None:
        """Return (min_ts, max_ts) across events from the given source files.

        Returns None if no events have timestamps (edge case: ingested files
        contained no dated events).
        """
        if not source_file_ids:
            return None
        placeholders = ",".join("?" * len(source_file_ids))
        row = self.conn.execute(
            f"""
            SELECT MIN(timestamp), MAX(timestamp)
            FROM events
            WHERE timestamp IS NOT NULL
              AND source_file_id IN ({placeholders})
            """,
            tuple(source_file_ids),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return str(row[0]), str(row[1])

    def refresh_aggregates_for_range(
        self, start_bucket: str | None = None, end_bucket: str | None = None,
    ) -> dict[str, int]:
        """Refresh all four agg_* tables for the given time range.

        Pass ``start_bucket=None, end_bucket=None`` to do a full cold rebuild
        (wipes each table and re-populates from scratch).

        The range is expressed in ISO timestamp form, matching the format
        produced by each granularity's bucket expression. A safe strategy is
        to pass (MIN(affected_timestamp), MAX(affected_timestamp)) — the
        per-granularity filter handles the truncation.
        """
        t0 = time.monotonic()
        cursor = self.conn.cursor()
        counts: dict[str, int] = {}
        for granularity, expr in self._AGG_BUCKET_EXPRS.items():
            counts[granularity] = self._refresh_one_agg(
                cursor, granularity, expr, start_bucket, end_bucket,
            )
        self.conn.commit()
        elapsed_ms = (time.monotonic() - t0) * 1000
        range_desc = "full" if start_bucket is None else f"{start_bucket}..{end_bucket}"
        log.info(
            "Refreshed agg tables (%s): %s (%.0f ms)",
            range_desc,
            ", ".join(f"{g}={c}" for g, c in counts.items()),
            elapsed_ms,
        )
        return counts

    def rebuild_aggregates(self) -> None:
        """Rebuild projects and sessions tables from events."""
        t0 = time.monotonic()
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM projects")
        cursor.execute("""
            INSERT INTO projects
                (project_id, first_activity, last_activity, session_count, event_count)
            SELECT project_id,
                   MIN(timestamp), MAX(timestamp),
                   COUNT(DISTINCT session_id), COUNT(*)
            FROM events WHERE timestamp IS NOT NULL
            GROUP BY project_id
        """)
        cursor.execute("DELETE FROM sessions")
        cursor.execute("""
            INSERT INTO sessions (
                session_id, project_id, first_timestamp, last_timestamp,
                event_count, subagent_count,
                total_input_tokens, total_output_tokens,
                total_cache_read_tokens, total_cache_creation_tokens)
            SELECT session_id, project_id,
                   MIN(timestamp), MAX(timestamp),
                   COUNT(*), COUNT(DISTINCT agent_id) - 1,
                   SUM(input_tokens), SUM(output_tokens),
                   SUM(cache_read_tokens), SUM(cache_creation_tokens)
            FROM events WHERE session_id IS NOT NULL
            GROUP BY project_id, session_id
        """)
        cursor.execute("""
            UPDATE sessions SET total_cost_usd = (
                SELECT COALESCE(SUM(e.total_cost_usd), 0)
                FROM events e
                WHERE e.session_id = sessions.session_id
                  AND e.project_id = sessions.project_id
            )
        """)
        self.conn.commit()
        elapsed_ms = (time.monotonic() - t0) * 1000
        project_count = cursor.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        session_count = cursor.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        log.info(
            "Rebuilt aggregates: %d projects, %d sessions (%.0f ms)",
            project_count, session_count, elapsed_ms,
        )

    # -- Update orchestration ------------------------------------------------

    def update(self, projects_path: Path) -> dict[str, Any]:
        """Perform incremental update of the cache. Returns counts."""
        t0 = time.monotonic()

        all_files = self.discover_files(projects_path)
        log.info("Discovered %d JSONL files in %s", len(all_files), projects_path)

        files_to_update = self.get_files_needing_update(all_files)
        if not files_to_update:
            log.info("Cache is up to date — no files changed")
            # Even when no files changed, the agg_* tables may be empty
            # (first start after the schema upgrade that added them). In
            # that case we still need to do a full population from the
            # already-present events.
            if self._agg_tables_empty():
                log.info("Dimensional aggregates empty — backfilling from events")
                self.refresh_aggregates_for_range()
            return {"files_updated": 0, "events_added": 0}

        new_count = sum(1 for f in files_to_update if f.get("reason") == "new")
        modified_count = sum(1 for f in files_to_update if f.get("reason") == "modified")
        log.info(
            "Cache update needed: %d files (%d new, %d modified)",
            len(files_to_update), new_count, modified_count,
        )

        total_events = 0
        affected_source_file_ids: list[int] = []
        for i, file_info in enumerate(files_to_update, 1):
            events_added = self.ingest_file(file_info)
            total_events += events_added
            # Track the source_file_ids that were (re-)ingested so we can
            # scope the agg refresh to just their timestamp window.
            sfid = file_info.get("source_file_id")
            if isinstance(sfid, int):
                affected_source_file_ids.append(sfid)
            if i % 50 == 0 or i == len(files_to_update):
                log.info(
                    "  Ingested %d/%d files (%d events so far)",
                    i, len(files_to_update), total_events,
                )
        self.conn.commit()

        # Session/project roll-ups (kept as full rebuild — cheap, tiny tables)
        self.rebuild_aggregates()

        # Dimensional agg_* tables — incremental by affected time range.
        # If the agg tables are empty (first run after the schema addition),
        # this takes the full-rebuild path. Otherwise we scope to the window
        # of timestamps that were just ingested.
        if self._agg_tables_empty():
            log.info("Dimensional aggregates empty — doing full cold rebuild")
            self.refresh_aggregates_for_range()
        elif affected_source_file_ids:
            window = self._timestamp_window_for_files(affected_source_file_ids)
            if window is not None:
                self.refresh_aggregates_for_range(window[0], window[1])

        self.conn.execute(
            "INSERT OR REPLACE INTO cache_metadata (key, value) VALUES (?, ?)",
            ("last_update_at", datetime.now(UTC).isoformat()),
        )
        self.conn.commit()

        elapsed = time.monotonic() - t0
        log.info(
            "Cache update complete: %d files, %d events in %.1f s",
            len(files_to_update), total_events, elapsed,
        )
        return {"files_updated": len(files_to_update), "events_added": total_events}

    def ensure_ready(self, projects_path: Path) -> None:
        """Ensure cache exists, schema is current, and data is fresh.

        The schema SQL uses ``CREATE X IF NOT EXISTS`` throughout, so running
        ``init_schema()`` on every startup is safe and idempotent — and it
        picks up new additive schema changes (new indexes, new columns via
        ALTER TABLE, etc.) without forcing a full rebuild.
        """
        if not self.db_path.exists():
            log.info("Cache not found — initializing from scratch")
            self.init_schema()
            self.update(projects_path)
            return

        if self.needs_rebuild():
            log.info("Schema version mismatch — rebuilding cache")
            self.reset()
            self.update(projects_path)
            return

        # Existing cache with matching version — still run init_schema() to
        # apply any additive changes (new indexes), then incrementally update.
        self.init_schema()
        self.update(projects_path)
