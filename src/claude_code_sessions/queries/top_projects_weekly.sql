-- Top 3 Projects by Cost - Last 8 Weeks
-- Returns weekly aggregates for the 3 most expensive projects over the last 8 weeks
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
        TRY_CAST(timestamp AS TIMESTAMP) AS timestamp,
        DATE_TRUNC('week', TRY_CAST(timestamp AS TIMESTAMP))::DATE AS week
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760)
    WHERE message.usage IS NOT NULL
      __DAYS_FILTER__
),

-- Identify top 3 projects by total cost over last 8 weeks
top_projects AS (
    SELECT
        pd.project_id,
        SUM(
            (COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
            (COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
            (COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
            (COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
            (COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)
        ) AS total_cost
    FROM parsed_data pd
    LEFT JOIN pricing p ON pd.model_family = p.model_family
    GROUP BY pd.project_id
    ORDER BY total_cost DESC
    LIMIT 3
),

-- Get weekly aggregates for top 3 projects
weekly_aggregates AS (
    SELECT
        pd.project_id,
        pd.week AS time_bucket,

        -- Total cost for the week
        ROUND(SUM(
            (COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
            (COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
            (COALESCE(pd.ephemeral_1h_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
            (COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
            (COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)
        ), 4) AS cost_usd,

        -- Token metrics
        COALESCE(SUM(pd.input_tokens), 0) AS input_tokens,
        COALESCE(SUM(pd.output_tokens), 0) AS output_tokens,
        COALESCE(SUM(pd.input_tokens), 0) + COALESCE(SUM(pd.output_tokens), 0) AS total_tokens,

        -- Session metrics
        COUNT(DISTINCT pd.session_id) AS session_count,
        COUNT(*) AS event_count

    FROM parsed_data pd
    INNER JOIN top_projects tp ON pd.project_id = tp.project_id
    LEFT JOIN pricing p ON pd.model_family = p.model_family
    GROUP BY pd.project_id, pd.week
)

SELECT
    project_id,
    time_bucket,
    cost_usd,
    input_tokens,
    output_tokens,
    total_tokens,
    session_count,
    event_count,
    ROUND(cost_usd / NULLIF(session_count, 0), 4) AS cost_per_session
FROM weekly_aggregates
ORDER BY time_bucket DESC, cost_usd DESC;
