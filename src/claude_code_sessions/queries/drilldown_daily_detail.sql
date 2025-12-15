-- Drill-down: Daily detail for a specific project showing UTC vs Local timezone differences
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,
        regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS session_id,
        message.model AS model_id,
        message.usage.input_tokens AS input_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,
        message.usage.output_tokens AS output_tokens,
        TRY_CAST(timestamp AS TIMESTAMPTZ) AS timestamp_utc,
        DATE_TRUNC('day', TRY_CAST(timestamp AS TIMESTAMPTZ) AT TIME ZONE 'Australia/Melbourne')::DATE AS date_local,
        DATE_TRUNC('day', TRY_CAST(timestamp AS TIMESTAMPTZ))::DATE AS date_utc
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760)
    WHERE message.usage IS NOT NULL
)

SELECT
    pd.project_id,
    pd.date_local,
    pd.date_utc,

    -- Show when dates differ (timezone boundary events)
    CASE
        WHEN pd.date_local != pd.date_utc THEN 'TIMEZONE_MISMATCH'
        ELSE 'ALIGNED'
    END AS timezone_status,

    -- Session and event counts
    COUNT(DISTINCT pd.session_id) AS session_count,
    COUNT(*) AS event_count,

    -- Model breakdown
    pd.model_id,

    -- Total cost
    ROUND(SUM(
        (COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
        (COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
        (COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
        (COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
        (COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)
    ), 4) AS total_cost_usd,

    -- Token totals
    COALESCE(SUM(pd.input_tokens), 0) AS total_input_tokens,
    COALESCE(SUM(pd.output_tokens), 0) AS total_output_tokens

FROM parsed_data pd
LEFT JOIN pricing p ON pd.model_id = p.model_id
WHERE pd.project_id = '__PROJECT_FILTER__'
GROUP BY pd.project_id, pd.date_local, pd.date_utc, pd.model_id
ORDER BY pd.date_local DESC, timezone_status DESC, total_cost_usd DESC;
