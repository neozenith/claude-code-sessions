-- Schema Timeline Query
-- Shows one marker per day per JSON path
-- Uses file mtime as fallback when record has no timestamp
-- Joins with file_mtimes DataFrame (registered in Python)

-- Read raw events and join with file mtimes
WITH raw_events AS (
    SELECT
        j.filename,
        regexp_extract(j.filename, 'projects/([^/]+)/', 1) AS project_id,
        -- Get event date: prefer record timestamp, fallback to file mtime
        COALESCE(
            TRY_CAST(DATE_TRUNC('day', TRY_CAST(j.timestamp AS TIMESTAMPTZ)) AS DATE),
            TRY_CAST(fm.mtime_date AS DATE)
        ) AS event_date,
        -- Track timestamp source for display
        j.timestamp IS NOT NULL AS has_record_timestamp,
        -- Include version
        j.version,
        -- Check presence of each known path
        j.type IS NOT NULL AS has_type,
        j.timestamp IS NOT NULL AS has_timestamp,
        j.uuid IS NOT NULL AS has_uuid,
        j.parentUuid IS NOT NULL AS has_parentUuid,
        j.sessionId IS NOT NULL AS has_sessionId,
        j.version IS NOT NULL AS has_version,
        j.gitBranch IS NOT NULL AS has_gitBranch,
        j.agentId IS NOT NULL AS has_agentId,
        j.isSidechain IS NOT NULL AS has_isSidechain,
        j.userType IS NOT NULL AS has_userType,
        j.cwd IS NOT NULL AS has_cwd,
        j.requestId IS NOT NULL AS has_requestId,
        j.leafUuid IS NOT NULL AS has_leafUuid,
        j.summary IS NOT NULL AS has_summary,
        j.message IS NOT NULL AS has_message,
        j.message.role IS NOT NULL AS has_message_role,
        j.message.model IS NOT NULL AS has_message_model,
        j.message.id IS NOT NULL AS has_message_id,
        j.message.type IS NOT NULL AS has_message_type,
        j.message.content IS NOT NULL AS has_message_content,
        j.message.stop_reason IS NOT NULL AS has_message_stop_reason,
        j.message.usage IS NOT NULL AS has_message_usage,
        j.message.usage.input_tokens IS NOT NULL AS has_message_usage_input_tokens,
        j.message.usage.output_tokens IS NOT NULL AS has_message_usage_output_tokens,
        j.message.usage.cache_creation_input_tokens IS NOT NULL AS has_message_usage_cache_creation_input_tokens,
        j.message.usage.cache_read_input_tokens IS NOT NULL AS has_message_usage_cache_read_input_tokens,
        j.message.usage.service_tier IS NOT NULL AS has_message_usage_service_tier,
        j.message.usage.cache_creation IS NOT NULL AS has_message_usage_cache_creation,
        j.message.usage.cache_creation.ephemeral_5m_input_tokens IS NOT NULL AS has_message_usage_cache_creation_ephemeral_5m_input_tokens,
        j.message.usage.cache_creation.ephemeral_1h_input_tokens IS NOT NULL AS has_message_usage_cache_creation_ephemeral_1h_input_tokens,
        j.snapshot IS NOT NULL AS has_snapshot,
        TRY_CAST(j.snapshot.messageId AS VARCHAR) IS NOT NULL AS has_snapshot_messageId,
        j.snapshot.trackedFileBackups IS NOT NULL AS has_snapshot_trackedFileBackups,
        j.isSnapshotUpdate IS NOT NULL AS has_isSnapshotUpdate,
        j.messageId IS NOT NULL AS has_messageId
    FROM read_json_auto('__PROJECTS_GLOB__',
                        format='newline_delimited',
                        filename=true,
                        ignore_errors=true,
                        maximum_object_size=10485760) j
    LEFT JOIN file_mtimes fm ON j.filename = fm.filename
    WHERE 1=1
      __PROJECT_FILTER__
),

-- Unpivot: convert columns to rows for each path
path_events AS (
    SELECT event_date, version, 'type' AS json_path, has_record_timestamp FROM raw_events WHERE has_type
    UNION ALL SELECT event_date, version, 'timestamp', has_record_timestamp FROM raw_events WHERE has_timestamp
    UNION ALL SELECT event_date, version, 'uuid', has_record_timestamp FROM raw_events WHERE has_uuid
    UNION ALL SELECT event_date, version, 'parentUuid', has_record_timestamp FROM raw_events WHERE has_parentUuid
    UNION ALL SELECT event_date, version, 'sessionId', has_record_timestamp FROM raw_events WHERE has_sessionId
    UNION ALL SELECT event_date, version, 'version', has_record_timestamp FROM raw_events WHERE has_version
    UNION ALL SELECT event_date, version, 'gitBranch', has_record_timestamp FROM raw_events WHERE has_gitBranch
    UNION ALL SELECT event_date, version, 'agentId', has_record_timestamp FROM raw_events WHERE has_agentId
    UNION ALL SELECT event_date, version, 'isSidechain', has_record_timestamp FROM raw_events WHERE has_isSidechain
    UNION ALL SELECT event_date, version, 'userType', has_record_timestamp FROM raw_events WHERE has_userType
    UNION ALL SELECT event_date, version, 'cwd', has_record_timestamp FROM raw_events WHERE has_cwd
    UNION ALL SELECT event_date, version, 'requestId', has_record_timestamp FROM raw_events WHERE has_requestId
    UNION ALL SELECT event_date, version, 'leafUuid', has_record_timestamp FROM raw_events WHERE has_leafUuid
    UNION ALL SELECT event_date, version, 'summary', has_record_timestamp FROM raw_events WHERE has_summary
    UNION ALL SELECT event_date, version, 'message', has_record_timestamp FROM raw_events WHERE has_message
    UNION ALL SELECT event_date, version, 'message.role', has_record_timestamp FROM raw_events WHERE has_message_role
    UNION ALL SELECT event_date, version, 'message.model', has_record_timestamp FROM raw_events WHERE has_message_model
    UNION ALL SELECT event_date, version, 'message.id', has_record_timestamp FROM raw_events WHERE has_message_id
    UNION ALL SELECT event_date, version, 'message.type', has_record_timestamp FROM raw_events WHERE has_message_type
    UNION ALL SELECT event_date, version, 'message.content', has_record_timestamp FROM raw_events WHERE has_message_content
    UNION ALL SELECT event_date, version, 'message.stop_reason', has_record_timestamp FROM raw_events WHERE has_message_stop_reason
    UNION ALL SELECT event_date, version, 'message.usage', has_record_timestamp FROM raw_events WHERE has_message_usage
    UNION ALL SELECT event_date, version, 'message.usage.input_tokens', has_record_timestamp FROM raw_events WHERE has_message_usage_input_tokens
    UNION ALL SELECT event_date, version, 'message.usage.output_tokens', has_record_timestamp FROM raw_events WHERE has_message_usage_output_tokens
    UNION ALL SELECT event_date, version, 'message.usage.cache_creation_input_tokens', has_record_timestamp FROM raw_events WHERE has_message_usage_cache_creation_input_tokens
    UNION ALL SELECT event_date, version, 'message.usage.cache_read_input_tokens', has_record_timestamp FROM raw_events WHERE has_message_usage_cache_read_input_tokens
    UNION ALL SELECT event_date, version, 'message.usage.service_tier', has_record_timestamp FROM raw_events WHERE has_message_usage_service_tier
    UNION ALL SELECT event_date, version, 'message.usage.cache_creation', has_record_timestamp FROM raw_events WHERE has_message_usage_cache_creation
    UNION ALL SELECT event_date, version, 'message.usage.cache_creation.ephemeral_5m_input_tokens', has_record_timestamp FROM raw_events WHERE has_message_usage_cache_creation_ephemeral_5m_input_tokens
    UNION ALL SELECT event_date, version, 'message.usage.cache_creation.ephemeral_1h_input_tokens', has_record_timestamp FROM raw_events WHERE has_message_usage_cache_creation_ephemeral_1h_input_tokens
    UNION ALL SELECT event_date, version, 'snapshot', has_record_timestamp FROM raw_events WHERE has_snapshot
    UNION ALL SELECT event_date, version, 'snapshot.messageId', has_record_timestamp FROM raw_events WHERE has_snapshot_messageId
    UNION ALL SELECT event_date, version, 'snapshot.trackedFileBackups', has_record_timestamp FROM raw_events WHERE has_snapshot_trackedFileBackups
    UNION ALL SELECT event_date, version, 'isSnapshotUpdate', has_record_timestamp FROM raw_events WHERE has_isSnapshotUpdate
    UNION ALL SELECT event_date, version, 'messageId', has_record_timestamp FROM raw_events WHERE has_messageId
),

-- Aggregate by (json_path, event_date) - one marker per day per path
daily_events AS (
    SELECT
        json_path,
        event_date,
        -- Pick a representative version for the day (most common, or any non-null)
        MODE(version) AS version,
        -- Track if any record on this day had a real timestamp
        BOOL_OR(has_record_timestamp) AS has_record_timestamp,
        -- Count events for tooltip
        COUNT(*) AS event_count
    FROM path_events
    WHERE event_date IS NOT NULL
      __DAYS_FILTER__
    GROUP BY json_path, event_date
),

-- Compute first_seen for each path (for sorting)
path_first_seen AS (
    SELECT
        json_path,
        MIN(event_date) AS first_seen
    FROM daily_events
    GROUP BY json_path
)

SELECT
    de.event_date,
    de.version,
    de.json_path,
    pfs.first_seen,
    de.has_record_timestamp,
    de.event_count
FROM daily_events de
JOIN path_first_seen pfs ON de.json_path = pfs.json_path
ORDER BY pfs.first_seen ASC, de.json_path, de.event_date;
