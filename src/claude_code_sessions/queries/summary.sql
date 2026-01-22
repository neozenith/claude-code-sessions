-- Summary of total costs across all projects and sessions
WITH pricing AS (
    SELECT * FROM read_csv_auto('__PRICING_CSV_PATH__')
),

parsed_data AS (
    SELECT
        regexp_extract(filename, 'projects/([^/]+)/', 1) AS project_id,
        message.model AS model_id,
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
                        maximum_object_size=10485760)
    WHERE message.usage IS NOT NULL
      __DAYS_FILTER__
      __PROJECT_FILTER__
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
    
    -- Cost breakdown
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
LEFT JOIN pricing p ON pd.model_id = p.model_id;
