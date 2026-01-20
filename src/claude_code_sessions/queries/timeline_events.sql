-- Timeline Events Query
-- Returns individual events for a specific project with cumulative output tokens per session
-- Used for timeline scatterplot visualization
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_events AS (
    SELECT
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,
        regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS session_id,
        message.model AS model_id,
        -- Use top-level 'type' field for event type (user, assistant, system, etc.)
        type AS event_type,
        -- Extract message content for hover display
        -- For user messages, content is at message.content
        -- For assistant messages, it may be in message.content or nested in content array
        CASE
            WHEN type = 'user' THEN LEFT(COALESCE(CAST(message.content AS VARCHAR), ''), 500)
            WHEN type = 'assistant' THEN LEFT(COALESCE(CAST(message.content AS VARCHAR), ''), 500)
            WHEN type = 'system' THEN LEFT(COALESCE(CAST(message.content AS VARCHAR), ''), 500)
            ELSE ''
        END AS message_content,
        message.usage.input_tokens AS input_tokens,
        message.usage.output_tokens AS output_tokens,
        message.usage.cache_read_input_tokens AS cache_read_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS cache_5m_tokens,
        TRY_CAST(timestamp AS TIMESTAMPTZ) AS timestamp_utc,
        (TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne') AS timestamp_local,
        ROW_NUMBER() OVER (
            PARTITION BY regexp_extract(filename, '/([^/]+)\.jsonl$', 1)
            ORDER BY TRY_CAST(timestamp AS TIMESTAMPTZ)
        ) AS event_seq
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760)
    WHERE regexp_extract(filename, 'projects/([^/]+)/', 1) = '__PROJECT_FILTER__'
      -- Only include meaningful event types (exclude file-history-snapshot, summary, etc.)
      AND type IN ('user', 'assistant', 'system')
      -- Ensure we have a valid timestamp
      AND timestamp IS NOT NULL
      -- Optional days filter (replaced by API)
      __DAYS_FILTER__
),

session_first_event AS (
    SELECT
        session_id,
        MIN(timestamp_utc) AS first_event_time
    FROM parsed_events
    GROUP BY session_id
),

events_with_cumulative AS (
    SELECT
        e.*,
        sfe.first_event_time,
        SUM(COALESCE(e.output_tokens, 0)) OVER (
            PARTITION BY e.session_id
            ORDER BY e.timestamp_utc
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_output_tokens
    FROM parsed_events e
    JOIN session_first_event sfe ON e.session_id = sfe.session_id
)

SELECT
    project_id,
    session_id,
    event_seq,
    model_id,
    COALESCE(event_type, 'assistant') AS event_type,
    message_content,
    timestamp_utc,
    timestamp_local,
    first_event_time,
    COALESCE(input_tokens, 0) AS input_tokens,
    COALESCE(output_tokens, 0) AS output_tokens,
    COALESCE(cache_read_tokens, 0) AS cache_read_tokens,
    COALESCE(cache_creation_tokens, 0) AS cache_creation_tokens,
    COALESCE(cache_5m_tokens, 0) AS cache_5m_tokens,
    COALESCE(input_tokens, 0) + COALESCE(output_tokens, 0) AS total_tokens,
    cumulative_output_tokens
FROM events_with_cumulative
ORDER BY first_event_time ASC, session_id, event_seq;
