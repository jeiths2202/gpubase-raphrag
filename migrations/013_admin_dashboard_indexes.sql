-- Migration: 013_admin_dashboard_indexes
-- Description: Add indexes for admin dashboard performance optimization
-- Created: 2026-01-11

-- ============================================================================
-- QUERY_LOG INDEXES
-- ============================================================================

-- Index for date-based filtering (used in trends and metrics)
CREATE INDEX IF NOT EXISTS idx_query_log_created_at
    ON query_log(created_at DESC);

-- Composite index for strategy-based queries
CREATE INDEX IF NOT EXISTS idx_query_log_strategy_created
    ON query_log(strategy, created_at DESC)
    WHERE strategy IS NOT NULL;

-- Composite index for agent_type-based queries
CREATE INDEX IF NOT EXISTS idx_query_log_agent_created
    ON query_log(agent_type, created_at DESC)
    WHERE agent_type IS NOT NULL;

-- Index for success rate calculations
CREATE INDEX IF NOT EXISTS idx_query_log_success
    ON query_log(success, created_at DESC);

-- ============================================================================
-- USERS INDEXES
-- ============================================================================

-- Index for user registration trends
CREATE INDEX IF NOT EXISTS idx_users_created_at
    ON users(created_at DESC);

-- Index for user status filtering
CREATE INDEX IF NOT EXISTS idx_users_status
    ON users(status);

-- ============================================================================
-- TOKEN_USAGE_LOG INDEXES (if table exists)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'token_usage_log') THEN
        -- Index for timestamp-based queries
        CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp
            ON token_usage_log(timestamp DESC);

        -- Index for user-based token queries
        CREATE INDEX IF NOT EXISTS idx_token_usage_user_timestamp
            ON token_usage_log(user_id, timestamp DESC);

        -- Index for endpoint-based token queries
        CREATE INDEX IF NOT EXISTS idx_token_usage_endpoint
            ON token_usage_log(endpoint, timestamp DESC);
    END IF;
END $$;

-- ============================================================================
-- AGENT_EXECUTION_TRACES INDEXES (if table exists)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'agent_execution_traces') THEN
        -- Index for date-based agent performance queries
        CREATE INDEX IF NOT EXISTS idx_agent_traces_created
            ON agent_execution_traces(created_at DESC);

        -- Composite index for agent type performance
        CREATE INDEX IF NOT EXISTS idx_agent_traces_type_created
            ON agent_execution_traces(agent_type, created_at DESC);

        -- Index for status-based filtering
        CREATE INDEX IF NOT EXISTS idx_agent_traces_status
            ON agent_execution_traces(status, created_at DESC);
    END IF;
END $$;

-- ============================================================================
-- ADMIN_AUDIT_LOGS INDEXES (if table exists)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'admin_audit_logs') THEN
        -- Index for timestamp-based queries
        CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
            ON admin_audit_logs(timestamp DESC);

        -- Index for user-based filtering
        CREATE INDEX IF NOT EXISTS idx_audit_logs_user
            ON admin_audit_logs(user_id, timestamp DESC);

        -- Index for category filtering
        CREATE INDEX IF NOT EXISTS idx_audit_logs_category
            ON admin_audit_logs(action_category, timestamp DESC);

        -- Index for severity filtering
        CREATE INDEX IF NOT EXISTS idx_audit_logs_severity
            ON admin_audit_logs(severity, timestamp DESC);
    END IF;
END $$;

-- ============================================================================
-- ANALYZE TABLES
-- ============================================================================

ANALYZE query_log;
ANALYZE users;
