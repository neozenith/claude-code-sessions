-- Claude Code Session Usage Analysis - Hourly Aggregation (Last 14 Days)
-- Groups by date, hour of day for heatmap visualization
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,
        regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS session_id,
        message.model AS model_id,
        -- Extract model family for pricing lookup
        CASE
            WHEN message.model LIKE '%opus%' THEN 'opus'
            WHEN message.model LIKE '%sonnet%' THEN 'sonnet'
            WHEN message.model LIKE '%haiku%' THEN 'haiku'
            ELSE 'unknown'
        END AS model_family,
        message.usage.input_tokens AS input_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,
        message.usage.output_tokens AS output_tokens,
        -- Convert UTC timestamp to Australia/Melbourne timezone
        (TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne') AS timestamp_local,
        DATE_TRUNC('day', TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne')::DATE AS date,
        EXTRACT(HOUR FROM (TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne')) AS hour
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760)
    WHERE message.usage IS NOT NULL
      __DAYS_FILTER__
      __PROJECT_FILTER__
)

SELECT
    project_id,
    date AS time_bucket,
    hour AS hour_of_day,

    -- Cost calculation
    ROUND(SUM(
        (COALESCE(input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
        (COALESCE(ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
        (COALESCE(ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
        (COALESCE(cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
        (COALESCE(output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)
    ), 4) AS total_cost_usd,

    -- Token metrics
    COALESCE(SUM(input_tokens), 0) AS input_tokens,
    COALESCE(SUM(output_tokens), 0) AS output_tokens,
    COALESCE(SUM(input_tokens), 0) + COALESCE(SUM(output_tokens), 0) AS total_tokens,

    -- Activity metrics
    COUNT(DISTINCT session_id) AS session_count,
    COUNT(*) AS event_count

FROM parsed_data
LEFT JOIN pricing p ON parsed_data.model_family = p.model_family
GROUP BY project_id, date, hour
ORDER BY date DESC, hour ASC;
