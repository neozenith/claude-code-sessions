-- Claude Code Session Usage Analysis
-- Aggregates token usage across all sessions grouped by project, session, and model
-- Includes billing calculations based on Anthropic API pricing (as of 2025)
-- Now includes subagent/sidechain token breakdown for visibility into where tokens are spent
-- Pricing table for Claude models (per million tokens)
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        -- Extract project_id from the file path
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,

        -- Extract session_id from filename (the .jsonl filename without extension)
        regexp_extract(filename, '/([^/]+)\.jsonl$', 1) AS session_id,

        -- Extract model from the nested message structure
        message.model AS model_id,

        -- Subagent/sidechain identification
        -- isSidechain = true indicates this event belongs to a subagent (Task tool invocation)
        -- Use TRY_CAST to handle records where isSidechain field doesn't exist
        COALESCE(TRY_CAST(isSidechain AS BOOLEAN), false) AS is_sidechain,

        -- Extract all usage token fields
        message.usage.input_tokens AS input_tokens,
        message.usage.cache_creation_input_tokens AS cache_creation_input_tokens,
        message.usage.cache_read_input_tokens AS cache_read_input_tokens,
        message.usage.cache_creation.ephemeral_5m_input_tokens AS ephemeral_5m_input_tokens,
        message.usage.cache_creation.ephemeral_1h_input_tokens AS ephemeral_1h_input_tokens,
        message.usage.output_tokens AS output_tokens,

        -- Extract timestamp for duration calculation
        TRY_CAST(timestamp AS TIMESTAMP) AS timestamp,

        -- Track each row as an event/turn
        1 AS event_count

    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760,
                        union_by_name=true)

    -- Only include rows that have usage data (assistant messages)
    WHERE message.usage IS NOT NULL
      __DAYS_FILTER__
      __PROJECT_FILTER__
)

SELECT
    pd.project_id,
    pd.session_id,
    pd.model_id,

    -- Count of events/turns in this session
    COUNT(*) AS event_count,

    -- Timestamp metrics
    MIN(pd.timestamp) AS min_timestamp,
    MAX(pd.timestamp) AS max_timestamp,
    MAX(pd.timestamp) - MIN(pd.timestamp) AS duration,

    -- Sum all token usage metrics
    COALESCE(SUM(pd.input_tokens), 0) AS total_input_tokens,
    COALESCE(SUM(pd.cache_creation_input_tokens), 0) AS total_cache_creation_input_tokens,
    COALESCE(SUM(pd.cache_read_input_tokens), 0) AS total_cache_read_input_tokens,
    COALESCE(SUM(pd.ephemeral_5m_input_tokens), 0) AS total_ephemeral_5m_input_tokens,
    COALESCE(SUM(pd.ephemeral_1h_input_tokens), 0) AS total_ephemeral_1h_input_tokens,
    COALESCE(SUM(pd.output_tokens), 0) AS total_output_tokens,

    -- Calculate total tokens for convenience
    COALESCE(SUM(pd.input_tokens), 0) +
    COALESCE(SUM(pd.cache_creation_input_tokens), 0) +
    COALESCE(SUM(pd.cache_read_input_tokens), 0) +
    COALESCE(SUM(pd.output_tokens), 0) AS total_all_tokens,

    -- ========== SUBAGENT/SIDECHAIN BREAKDOWN ==========
    -- Event counts by agent type
    COUNT(CASE WHEN NOT pd.is_sidechain THEN 1 END) AS main_agent_events,
    COUNT(CASE WHEN pd.is_sidechain THEN 1 END) AS subagent_events,

    -- Main agent token usage (is_sidechain = false)
    COALESCE(SUM(CASE WHEN NOT pd.is_sidechain THEN pd.input_tokens END), 0) AS main_agent_input_tokens,
    COALESCE(SUM(CASE WHEN NOT pd.is_sidechain THEN pd.output_tokens END), 0) AS main_agent_output_tokens,

    -- Subagent token usage (is_sidechain = true)
    COALESCE(SUM(CASE WHEN pd.is_sidechain THEN pd.input_tokens END), 0) AS subagent_input_tokens,
    COALESCE(SUM(CASE WHEN pd.is_sidechain THEN pd.output_tokens END), 0) AS subagent_output_tokens,

    -- Percentage of tokens from subagents
    ROUND(
        100.0 * COALESCE(SUM(CASE WHEN pd.is_sidechain THEN pd.input_tokens + pd.output_tokens END), 0) /
        NULLIF(COALESCE(SUM(pd.input_tokens + pd.output_tokens), 0), 0),
    1) AS subagent_token_pct,

    -- ========== BILLING CALCULATIONS ==========
    -- Base input tokens cost
    ROUND((COALESCE(SUM(pd.input_tokens), 0) / 1000000.0) * COALESCE(p.base_input_price, 0), 4) AS cost_base_input,

    -- Cache creation costs (5m ephemeral cache writes)
    ROUND((COALESCE(SUM(pd.ephemeral_5m_input_tokens), 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0), 4) AS cost_cache_5m_writes,

    -- Cache creation costs (1h ephemeral cache writes)
    ROUND((COALESCE(SUM(pd.ephemeral_1h_input_tokens), 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0), 4) AS cost_cache_1h_writes,

    -- Cache read costs (cache hits)
    ROUND((COALESCE(SUM(pd.cache_read_input_tokens), 0) / 1000000.0) * COALESCE(p.cache_read_price, 0), 4) AS cost_cache_reads,

    -- Output tokens cost
    ROUND((COALESCE(SUM(pd.output_tokens), 0) / 1000000.0) * COALESCE(p.output_price, 0), 4) AS cost_output,

    -- Total session cost
    ROUND(
        (COALESCE(SUM(pd.input_tokens), 0) / 1000000.0) * COALESCE(p.base_input_price, 0) +
        (COALESCE(SUM(pd.ephemeral_5m_input_tokens), 0) / 1000000.0) * COALESCE(p.cache_5m_write_price, 0) +
        (COALESCE(SUM(pd.ephemeral_1h_input_tokens), 0) / 1000000.0) * COALESCE(p.cache_1h_write_price, 0) +
        (COALESCE(SUM(pd.cache_read_input_tokens), 0) / 1000000.0) * COALESCE(p.cache_read_price, 0) +
        (COALESCE(SUM(pd.output_tokens), 0) / 1000000.0) * COALESCE(p.output_price, 0),
    4) AS total_cost_usd

FROM parsed_data pd
LEFT JOIN pricing p ON pd.model_id = p.model_id

GROUP BY
    pd.project_id,
    pd.session_id,
    pd.model_id,
    p.base_input_price,
    p.cache_5m_write_price,
    p.cache_1h_write_price,
    p.cache_read_price,
    p.output_price

ORDER BY
    total_cost_usd DESC;
