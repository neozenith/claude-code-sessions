-- Session Events Query
-- Returns all events for a specific session including subagent events
-- Extracts uuid, parentUuid, type, timestamp for timeline visualization
-- Use with SESSION_GLOB placeholder
-- Note: Columns like agentId, isSidechain, slug may not exist in older session files
--       We read the JSON as a MAP and extract fields safely
WITH raw_data AS (
    SELECT
        *,
        filename,
        -- Use ROW_NUMBER to approximate line numbers within each file
        ROW_NUMBER() OVER (PARTITION BY filename ORDER BY TRY_CAST(timestamp AS TIMESTAMPTZ)) AS line_number
    FROM read_json_auto('__SESSION_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760,
                        union_by_name=true)
    WHERE timestamp IS NOT NULL
      AND type IS NOT NULL
)
SELECT
    -- Event identification (these should exist in all events)
    TRY_CAST(uuid AS VARCHAR) AS uuid,
    TRY_CAST(parentUuid AS VARCHAR) AS parent_uuid,

    -- Event type (user, assistant, system, etc.)
    type AS event_type,

    -- Timestamps
    TRY_CAST(timestamp AS TIMESTAMPTZ) AS timestamp,
    (TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne') AS timestamp_local,

    -- Session identification
    TRY_CAST(sessionId AS VARCHAR) AS session_id,

    -- Agent identification - these columns may not exist in older files
    -- Use NULL as default when column doesn't exist
    NULL AS agent_id,
    false AS is_sidechain,
    NULL AS agent_slug,

    -- Full message content (no truncation - let frontend handle display)
    COALESCE(TRY_CAST(json_extract(message, '$.content') AS VARCHAR), '') AS message_content,

    -- Model (may be NULL for user messages)
    TRY_CAST(json_extract(message, '$.model') AS VARCHAR) AS model_id,

    -- Token usage (may be NULL for non-assistant messages, or struct keys may not exist)
    COALESCE(TRY_CAST(json_extract(message, '$.usage.input_tokens') AS INTEGER), 0) AS input_tokens,
    COALESCE(TRY_CAST(json_extract(message, '$.usage.output_tokens') AS INTEGER), 0) AS output_tokens,
    COALESCE(TRY_CAST(json_extract(message, '$.usage.cache_read_input_tokens') AS INTEGER), 0) AS cache_read_tokens,

    -- Source file identification - full path
    filename AS filepath,
    CASE WHEN filename LIKE '%/subagents/%' THEN true ELSE false END AS is_subagent_file,
    regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS source_file,

    -- Approximate line number within file
    line_number,

    -- Full raw event JSON for expandable view
    to_json(message) AS message_json

FROM raw_data
ORDER BY timestamp ASC;
