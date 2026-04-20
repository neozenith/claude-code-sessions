"""
SQLite schema definitions for the session cache.

Compatible with the introspect script at
``.claude/skills/introspect/scripts/introspect_sessions.py``.
The ``reflections`` and ``event_annotations`` tables are not created here
but are tolerated if the introspect script creates them.
"""

from pathlib import Path

CACHE_DB_PATH = Path.home() / ".claude" / "cache" / "introspect_sessions.db"

# Must match the introspect script's version so both tools coexist.
SCHEMA_VERSION = "10"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cache_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath TEXT UNIQUE NOT NULL,
    mtime REAL NOT NULL,
    size_bytes INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    last_ingested_at TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT,
    file_type TEXT NOT NULL CHECK (file_type IN ('main_session', 'subagent', 'agent_root'))
);
CREATE INDEX IF NOT EXISTS idx_source_files_project ON source_files(project_id);
CREATE INDEX IF NOT EXISTS idx_source_files_session ON source_files(session_id);
CREATE INDEX IF NOT EXISTS idx_source_files_mtime ON source_files(mtime);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT UNIQUE NOT NULL,
    first_activity TEXT,
    last_activity TEXT,
    session_count INTEGER DEFAULT 0,
    event_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_projects_last_activity ON projects(last_activity);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    first_timestamp TEXT,
    last_timestamp TEXT,
    event_count INTEGER DEFAULT 0,
    subagent_count INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    total_cache_read_tokens INTEGER DEFAULT 0,
    total_cache_creation_tokens INTEGER DEFAULT 0,
    total_cost_usd REAL DEFAULT 0.0,
    UNIQUE(project_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_timestamp ON sessions(last_timestamp);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT,
    parent_uuid TEXT,
    prompt_id TEXT,
    event_type TEXT NOT NULL,
    msg_kind TEXT,
    timestamp TEXT,
    timestamp_local TEXT,
    session_id TEXT,
    project_id TEXT NOT NULL,
    is_sidechain INTEGER DEFAULT 0,
    agent_id TEXT,
    agent_slug TEXT,
    message_role TEXT,
    message_content TEXT,
    message_content_json TEXT,
    model_id TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_5m_tokens INTEGER DEFAULT 0,
    token_rate REAL DEFAULT 0.0,
    billable_tokens REAL DEFAULT 0.0,
    total_cost_usd REAL DEFAULT 0.0,
    source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_uuid ON events(uuid);
CREATE INDEX IF NOT EXISTS idx_events_parent_uuid ON events(parent_uuid);
CREATE INDEX IF NOT EXISTS idx_events_prompt_id ON events(prompt_id);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_msg_kind ON events(msg_kind);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_source_file ON events(source_file_id);
CREATE INDEX IF NOT EXISTS idx_events_project_session ON events(project_id, session_id);
CREATE INDEX IF NOT EXISTS idx_events_session_type ON events(session_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_session_uuid ON events(session_id, uuid);
CREATE INDEX IF NOT EXISTS idx_source_files_project_session
    ON source_files(project_id, session_id);

-- Covering index for analytical GROUP BY queries. Lets SQLite answer
-- /api/summary, /api/usage/{daily,weekly,monthly,hourly}, and /api/projects
-- index-only without touching the main table. Leading (timestamp) supports
-- the universal days-filter range scan; trailing columns cover every measure
-- the aggregation queries need.
CREATE INDEX IF NOT EXISTS idx_events_covering ON events(
    timestamp, project_id, session_id, model_id,
    input_tokens, output_tokens,
    cache_read_tokens, cache_creation_tokens, total_cost_usd
);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    message_content, content='events', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, message_content) VALUES (new.id, new.message_content);
END;
CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, message_content)
        VALUES('delete', old.id, old.message_content);
END;
CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, message_content)
        VALUES('delete', old.id, old.message_content);
    INSERT INTO events_fts(rowid, message_content) VALUES (new.id, new.message_content);
END;

CREATE TABLE IF NOT EXISTS event_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_uuid TEXT NOT NULL,
    parent_event_uuid TEXT NOT NULL,
    source_file_id INTEGER NOT NULL REFERENCES source_files(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_event_edges_forward
    ON event_edges(project_id, session_id, event_uuid);
CREATE INDEX IF NOT EXISTS idx_event_edges_reverse
    ON event_edges(project_id, session_id, parent_event_uuid);
CREATE INDEX IF NOT EXISTS idx_event_edges_source_file ON event_edges(source_file_id);

-- =====================================================================
-- event_calls — raw fact table for tool/skill/subagent/cli/rule calls
-- =====================================================================
-- One row per observed "call" inside an event. Each event can emit many
-- rows: an assistant message may carry N parallel tool_use blocks, a
-- Bash command may invoke several CLI heads, and a user message may
-- inject many <system-reminder> rule blocks at once.
--
-- call_type discriminator:
--   'tool'        - generic tool_use (Read, Edit, Grep, Write, ...). Bash
--                   also emits one 'tool' row plus N 'cli' rows.
--   'skill'       - tool_use with name=="Skill"; call_name = input.skill
--   'subagent'    - tool_use with name=="Agent"; call_name = input.subagent_type
--   'cli'         - command head parsed from Bash input.command
--   'rule'        - .claude/rules/... path parsed from <system-reminder> text
--   'make_target' - target arg(s) parsed from `make <target> ...` segments
--                   within Bash commands (additive to the 'cli' row for make)
--
-- timestamp/project_id/session_id are denormalized off `events` so the
-- common "calls in a time window" / "calls per project" queries don't
-- need a join back to the main table.
-- =====================================================================

CREATE TABLE IF NOT EXISTS event_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL DEFAULT 0,
    call_type TEXT NOT NULL CHECK (
        call_type IN ('tool', 'skill', 'subagent', 'cli', 'rule', 'make_target')
    ),
    call_name TEXT NOT NULL,
    timestamp TEXT,
    project_id TEXT NOT NULL,
    session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_calls_event
    ON event_calls(event_id);
CREATE INDEX IF NOT EXISTS idx_event_calls_type_name
    ON event_calls(call_type, call_name);
CREATE INDEX IF NOT EXISTS idx_event_calls_timestamp
    ON event_calls(timestamp);
CREATE INDEX IF NOT EXISTS idx_event_calls_project_session
    ON event_calls(project_id, session_id);

-- =====================================================================
-- Dimensional aggregation tables (star schema)
-- =====================================================================
-- These tables pre-aggregate event measures at four time granularities.
-- Analytical endpoints (/api/summary, /api/usage/{daily,weekly,monthly,hourly})
-- read from these instead of GROUP BY-ing over millions of events.
--
-- Grain: (time_bucket, project_id, session_id, model_id)
-- Dimensions: time_bucket (ISO string), project_id, session_id, model_id
-- Measures (additive): event_count, input_tokens, output_tokens,
--                      cache_read_tokens, cache_creation_tokens,
--                      total_cost_usd, billable_tokens
--
-- Session uniqueness: COUNT(DISTINCT session_id) at query time — measures
-- stay additive per Kimball's dimensional-modelling rule.
--
-- session_id / model_id use '' as a sentinel for NULL so the PRIMARY KEY
-- uniqueness check works (SQLite's PK treats NULLs as non-equal).
-- =====================================================================

CREATE TABLE IF NOT EXISTS agg (
    granularity TEXT NOT NULL,  -- 'hourly', 'daily', 'weekly', 'monthly'
    time_bucket TEXT NOT NULL,
    project_id TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    event_count INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd REAL NOT NULL DEFAULT 0.0,
    billable_tokens REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (granularity, time_bucket, project_id, session_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_agg_granularity_time
    ON agg(granularity, time_bucket);
CREATE INDEX IF NOT EXISTS idx_agg_granularity_project_time
    ON agg(granularity, project_id, time_bucket);
"""
