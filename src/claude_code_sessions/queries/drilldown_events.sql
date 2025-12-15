-- Drill-down: Individual events for a specific session
-- Shows row-level data with full timestamp and cost detail
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,
        regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS session_id,
        message.model AS model_id,
        message.role AS role,
        message.usage.input_tokens AS input_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,
        message.usage.output_tokens AS output_tokens,
        TRY_CAST(timestamp AS TIMESTAMPTZ) AS timestamp_utc,
        (TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne') AS timestamp_local,
        DATE_TRUNC('day', TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne')::DATE AS date_local,
        DATE_TRUNC('day', TRY_CAST(timestamp AS TIMESTAMPTZ))::DATE AS date_utc,
        EXTRACT(HOUR FROM (TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne')) AS hour_local,
        EXTRACT(HOUR FROM TRY_CAST(timestamp AS TIMESTAMPTZ)) AS hour_utc,
        ROW_NUMBER() OVER (PARTITION BY regexp_extract(filename, '/([^/]+)\.jsonl$', 1) ORDER BY TRY_CAST(timestamp AS TIMESTAMPTZ)) AS event_seq
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760)
    WHERE message.usage IS NOT NULL
)

SELECT
    pd.project_id,
    pd.session_id,
    pd.event_seq,
    pd.model_id,
    pd.role,

    -- Timestamps with timezone info
    pd.timestamp_utc,
    pd.timestamp_local,
    pd.date_utc,
    pd.date_local,
    pd.hour_utc,
    pd.hour_local,

    -- Token usage
    COALESCE(pd.input_tokens, 0) AS input_tokens,
    COALESCE(pd.ephemeral_5m_input_tokens, 0) AS cache_5m_write_tokens,
    COALESCE(pd.ephemeral_1h_input_tokens, 0) AS cache_1h_write_tokens,
    COALESCE(pd.cache_read_input_tokens, 0) AS cache_read_tokens,
    COALESCE(pd.output_tokens, 0) AS output_tokens,
    COALESCE(pd.input_tokens, 0) + COALESCE(pd.output_tokens, 0) AS total_tokens,

    -- Cost breakdown per event
    ROUND((COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0), 6) AS cost_base_input,
    ROUND((COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0), 6) AS cost_cache_5m_writes,
    ROUND((COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0), 6) AS cost_cache_1h_writes,
    ROUND((COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0), 6) AS cost_cache_reads,
    ROUND((COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0), 6) AS cost_output,

    -- Total event cost
    ROUND(
        (COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
        (COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
        (COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
        (COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
        (COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0),
    6) AS event_cost_usd

FROM parsed_data pd
LEFT JOIN pricing p ON pd.model_id = p.model_id
WHERE pd.project_id = '__PROJECT_FILTER__'
  AND pd.session_id = '__SESSION_FILTER__'
ORDER BY pd.timestamp_local ASC;
