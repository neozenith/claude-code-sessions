-- Claude Code Session Usage Analysis - Weekly Aggregation
-- Groups by project_id, model_id, and week (Monday of each week)
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        -- Extract project_id from the file path
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,

        -- Extract session_id from filename
        regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS session_id,

        -- Extract model from the nested message structure
        message.model AS model_id,

        -- Extract model family for pricing lookup
        CASE
            WHEN message.model LIKE '%opus%' THEN 'opus'
            WHEN message.model LIKE '%sonnet%' THEN 'sonnet'
            WHEN message.model LIKE '%haiku%' THEN 'haiku'
            ELSE 'unknown'
        END AS model_family,

        -- Extract all usage token fields
        message.usage.input_tokens AS input_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,
        message.usage.output_tokens AS output_tokens,

        -- Extract timestamp and derive time dimensions
        TRY_CAST(timestamp AS TIMESTAMP) AS timestamp,
        DATE_TRUNC('day', TRY_CAST(timestamp AS TIMESTAMP))::DATE AS day,
        DATE_TRUNC('week', TRY_CAST(timestamp AS TIMESTAMP))::DATE AS week,
        DATE_TRUNC('month', TRY_CAST(timestamp AS TIMESTAMP))::DATE AS month

    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760)

    -- Only include rows that have usage data (assistant messages)
    WHERE message.usage IS NOT NULL
      __DAYS_FILTER__
      __PROJECT_FILTER__
      __DOMAIN_FILTER__
)

SELECT
    pd.project_id,
    pd.model_id,
    pd.week AS time_bucket,

    -- Total cost (per-row multiplication inside SUM for correct GROUP BY)
    ROUND(SUM(
        (COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
        (COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
        (COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
        (COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
        (COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)
    ), 4) AS total_cost_usd,

    -- Count of distinct sessions and events
    COUNT(DISTINCT pd.session_id) AS session_count,
    COUNT(*) AS event_count,

    -- Sum all token usage metrics
    COALESCE(SUM(pd.input_tokens), 0) AS total_input_tokens,
    COALESCE(SUM(pd.cache_creation_input_tokens), 0) AS total_cache_creation_input_tokens,
    COALESCE(SUM(pd.cache_read_input_tokens), 0) AS total_cache_read_input_tokens,
    COALESCE(SUM(pd.ephemeral_5m_input_tokens), 0) AS total_ephemeral_5m_input_tokens,
    COALESCE(SUM(pd.ephemeral_1h_input_tokens), 0) AS total_ephemeral_1h_input_tokens,
    COALESCE(SUM(pd.output_tokens), 0) AS total_output_tokens,

    -- Calculate total tokens
    COALESCE(SUM(pd.input_tokens), 0) +
    COALESCE(SUM(pd.cache_creation_input_tokens), 0) +
    COALESCE(SUM(pd.cache_read_input_tokens), 0) +
    COALESCE(SUM(pd.output_tokens), 0) AS total_all_tokens,

    -- Billing breakdown (costs in USD)
    ROUND(SUM((COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0)), 4) AS cost_base_input,
    ROUND(SUM((COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0)), 4) AS cost_cache_5m_writes,
    ROUND(SUM((COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0)), 4) AS cost_cache_1h_writes,
    ROUND(SUM((COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0)), 4) AS cost_cache_reads,
    ROUND(SUM((COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)), 4) AS cost_output

FROM parsed_data pd
LEFT JOIN pricing p ON pd.model_family = p.model_family

GROUP BY
    pd.project_id,
    pd.model_id,
    pd.week,
    pd.model_family

ORDER BY
    pd.week DESC,
    total_cost_usd DESC;
