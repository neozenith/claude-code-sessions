-- Sessions List Query
-- Returns all sessions grouped by project with aggregated stats
-- Includes count of subagent files per session
-- Supports universal filters (days, project)
-- Note: Excludes agent-*.jsonl files (subagent sessions that link to parent via sessionId)
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

-- Parse all JSONL files (both main session files and subagent files)
all_events AS (
    SELECT
        -- Extract project_id from the file path
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,

        -- Extract session_id - handle both main session and subagent paths
        -- Main session: projects/{project_id}/{session_id}.jsonl
        -- Subagent (old style): projects/{project_id}/agent-{id}.jsonl (linked via sessionId field)
        -- Subagent (new style): projects/{project_id}/{session_id}/subagents/{agent_id}.jsonl
        CASE
            WHEN filename LIKE '%/subagents/%' THEN
                regexp_extract(filename, 'projects/[^/]+/([^/]+)/subagents/', 1)
            WHEN regexp_extract(filename, '/([^/]+)\.jsonl$', 1) LIKE 'agent-%' THEN
                -- For agent-*.jsonl files, use sessionId from the record to link to parent
                TRY_CAST(sessionId AS VARCHAR)
            ELSE
                regexp_extract(filename, '/([^/]+)\.jsonl$', 1)
        END AS session_id,

        -- Flag subagent files (both old and new style)
        CASE
            WHEN filename LIKE '%/subagents/%' THEN true
            WHEN regexp_extract(filename, '/([^/]+)\.jsonl$', 1) LIKE 'agent-%' THEN true
            ELSE false
        END AS is_subagent_file,

        -- Filepath for display
        filename AS filepath,

        -- Extract agentId for unique subagent counting
        TRY_CAST(agentId AS VARCHAR) AS agent_id,

        -- Model for pricing
        message.model AS model_id,

        -- Token usage
        message.usage.input_tokens AS input_tokens,
        message.usage.output_tokens AS output_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,

        -- Timestamp
        TRY_CAST(timestamp AS TIMESTAMPTZ) AS timestamp_utc

    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760,
                        union_by_name=true)
    WHERE timestamp IS NOT NULL
      __DAYS_FILTER__
      __PROJECT_FILTER__
),

-- Aggregate events with usage data for cost calculation
usage_events AS (
    SELECT
        e.project_id,
        e.session_id,
        e.model_id,
        e.input_tokens,
        e.output_tokens,
        e.cache_creation_input_tokens,
        e.cache_read_input_tokens,
        e.ephemeral_5m_input_tokens,
        e.ephemeral_1h_input_tokens
    FROM all_events e
    WHERE e.input_tokens IS NOT NULL OR e.output_tokens IS NOT NULL
),

-- Calculate costs per session
session_costs AS (
    SELECT
        u.project_id,
        u.session_id,
        COUNT(*) AS usage_event_count,
        COALESCE(SUM(u.input_tokens), 0) AS total_input_tokens,
        COALESCE(SUM(u.output_tokens), 0) AS total_output_tokens,
        -- Total cost calculation
        SUM(
            COALESCE((u.input_tokens / 1000000.0) * p.base_input_price, 0) +
            COALESCE((u.ephemeral_5m_input_tokens / 1000000.0) * p.cache_5m_write_price, 0) +
            COALESCE((u.ephemeral_1h_input_tokens / 1000000.0) * p.cache_1h_write_price, 0) +
            COALESCE((u.cache_read_input_tokens / 1000000.0) * p.cache_read_price, 0) +
            COALESCE((u.output_tokens / 1000000.0) * p.output_price, 0)
        ) AS total_cost_usd
    FROM usage_events u
    LEFT JOIN pricing p ON u.model_id = p.model_id
    GROUP BY u.project_id, u.session_id
),

-- Aggregate all events per session (including non-usage events)
session_stats AS (
    SELECT
        project_id,
        session_id,
        COUNT(*) AS event_count,
        COUNT(DISTINCT agent_id) AS subagent_count,
        MIN(timestamp_utc) AS first_timestamp,
        MAX(timestamp_utc) AS last_timestamp,
        -- Get the main session filepath (non-subagent file)
        MIN(CASE WHEN NOT is_subagent_file THEN filepath END) AS main_filepath
    FROM all_events
    WHERE session_id IS NOT NULL
      -- Exclude standalone agent-*.jsonl entries that don't have a parent session
      -- (they should be linked via sessionId, but if sessionId is null, skip them)
      AND NOT (is_subagent_file AND session_id IS NULL)
    GROUP BY project_id, session_id
)

SELECT
    s.project_id,
    s.session_id,
    s.first_timestamp,
    s.last_timestamp,
    s.event_count,
    COALESCE(s.subagent_count, 0) AS subagent_count,
    COALESCE(c.total_input_tokens, 0) AS total_input_tokens,
    COALESCE(c.total_output_tokens, 0) AS total_output_tokens,
    ROUND(COALESCE(c.total_cost_usd, 0), 4) AS total_cost_usd,
    s.main_filepath AS filepath
FROM session_stats s
LEFT JOIN session_costs c ON s.project_id = c.project_id AND s.session_id = c.session_id
WHERE s.project_id IS NOT NULL
  AND s.session_id IS NOT NULL
  -- Only include sessions that have a main session file (not just subagent files)
  AND s.main_filepath IS NOT NULL
ORDER BY s.last_timestamp DESC NULLS LAST;
