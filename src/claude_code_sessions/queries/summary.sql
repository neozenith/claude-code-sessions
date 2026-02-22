-- Summary of total costs across all projects and sessions
-- Now includes subagent/sidechain breakdown for visibility into where tokens are spent
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,
        message.model AS model_id,
        -- Extract model family for pricing lookup
        CASE
            WHEN message.model LIKE '%opus%' THEN 'opus'
            WHEN message.model LIKE '%sonnet%' THEN 'sonnet'
            WHEN message.model LIKE '%haiku%' THEN 'haiku'
            ELSE 'unknown'
        END AS model_family,
        -- Subagent identification
        -- Use TRY_CAST to handle records where isSidechain field doesn't exist
        COALESCE(TRY_CAST(isSidechain AS BOOLEAN), false) AS is_sidechain,
        message.usage.input_tokens AS input_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,
        message.usage.output_tokens AS output_tokens
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760,
                        union_by_name=true)
    WHERE message.usage IS NOT NULL
      __DAYS_FILTER__
      __PROJECT_FILTER__
      __DOMAIN_FILTER__
)

SELECT
    'GRAND TOTAL' AS summary_level,
    COUNT(DISTINCT pd.project_id) AS total_projects,
    COUNT(*) AS total_events,

    -- Token totals
    COALESCE(SUM(pd.input_tokens), 0) AS total_input_tokens,
    COALESCE(SUM(pd.ephemeral_5m_input_tokens), 0) AS total_cache_5m_tokens,
    COALESCE(SUM(pd.cache_read_input_tokens), 0) AS total_cache_read_tokens,
    COALESCE(SUM(pd.output_tokens), 0) AS total_output_tokens,

    -- ========== SUBAGENT/SIDECHAIN BREAKDOWN ==========
    -- Event counts by agent type
    COUNT(CASE WHEN NOT pd.is_sidechain THEN 1 END) AS main_agent_events,
    COUNT(CASE WHEN pd.is_sidechain THEN 1 END) AS subagent_events,

    -- Main agent token usage
    COALESCE(SUM(CASE WHEN NOT pd.is_sidechain THEN pd.input_tokens END), 0) AS main_agent_input_tokens,
    COALESCE(SUM(CASE WHEN NOT pd.is_sidechain THEN pd.output_tokens END), 0) AS main_agent_output_tokens,

    -- Subagent token usage
    COALESCE(SUM(CASE WHEN pd.is_sidechain THEN pd.input_tokens END), 0) AS subagent_input_tokens,
    COALESCE(SUM(CASE WHEN pd.is_sidechain THEN pd.output_tokens END), 0) AS subagent_output_tokens,

    -- Percentage of total tokens from subagents
    ROUND(
        100.0 * COALESCE(SUM(CASE WHEN pd.is_sidechain THEN pd.input_tokens + pd.output_tokens END), 0) /
        NULLIF(COALESCE(SUM(pd.input_tokens + pd.output_tokens), 0), 0),
    1) AS subagent_token_pct,

    -- ========== COST BREAKDOWN ==========
    ROUND(SUM((COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0)), 2) AS total_cost_base_input,
    ROUND(SUM((COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0)), 2) AS total_cost_cache_writes,
    ROUND(SUM((COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0)), 2) AS total_cost_cache_reads,
    ROUND(SUM((COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)), 2) AS total_cost_output,

    -- Grand total cost
    ROUND(
        SUM((COALESCE(pd.input_tokens, 0) / 1000000.0) * COALESCE(p.base_input_price, 0)) +
        SUM((COALESCE(pd.ephemeral_5m_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0)) +
        SUM((COALESCE(pd.cache_read_input_tokens, 0) / 1000000.0) * COALESCE(p.cache_read_price, 0)) +
        SUM((COALESCE(pd.output_tokens, 0) / 1000000.0) * COALESCE(p.output_price, 0)),
    2) AS grand_total_cost_usd

FROM parsed_data pd
LEFT JOIN pricing p ON pd.model_family = p.model_family;
