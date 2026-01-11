-- ============================================================================
-- Admin Dashboard Database Schema
-- Migration: 012_admin_dashboard.sql
-- Created: 2026-01-11
-- Purpose: Enterprise-grade AI Agent Governance & Observability Platform
-- ============================================================================

-- ============================================================================
-- 1. TOKEN USAGE LOG - Detailed records
-- ============================================================================
CREATE TABLE IF NOT EXISTS token_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Request identification
    trace_id UUID,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(100),

    -- Endpoint tracking
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,

    -- Token metrics
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,

    -- Model information
    model_name VARCHAR(100) NOT NULL DEFAULT 'nemotron-nano',
    agent_type VARCHAR(50),

    -- Performance
    execution_time_ms INTEGER NOT NULL DEFAULT 0,

    -- Cost tracking (USD)
    estimated_cost DECIMAL(10, 6) DEFAULT 0.0,

    -- Timestamp
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

COMMENT ON TABLE token_usage_log IS 'Detailed token usage log for all API requests';
COMMENT ON COLUMN token_usage_log.estimated_cost IS 'Estimated cost in USD based on model pricing';

-- Indexes for token_usage_log
CREATE INDEX IF NOT EXISTS idx_token_log_user_date ON token_usage_log(user_id, DATE(timestamp));
CREATE INDEX IF NOT EXISTS idx_token_log_endpoint ON token_usage_log(endpoint, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_token_log_timestamp ON token_usage_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_token_log_agent ON token_usage_log(agent_type, timestamp DESC)
    WHERE agent_type IS NOT NULL;


-- ============================================================================
-- 2. TOKEN USAGE DAILY - Aggregated metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS token_usage_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Aggregation key
    metric_date DATE NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    endpoint VARCHAR(200),
    model_name VARCHAR(100),
    agent_type VARCHAR(50),

    -- Aggregated metrics
    request_count INTEGER DEFAULT 0,
    total_input_tokens BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,
    total_tokens BIGINT DEFAULT 0,

    -- Performance metrics
    avg_execution_time_ms INTEGER,
    p95_execution_time_ms INTEGER,
    p99_execution_time_ms INTEGER,

    -- Cost
    total_estimated_cost DECIMAL(10, 4) DEFAULT 0.0,

    -- Success/Failure tracking
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint for upsert
    UNIQUE (metric_date, user_id, endpoint, model_name, agent_type)
);

COMMENT ON TABLE token_usage_daily IS 'Daily aggregated token usage metrics for dashboard';

CREATE INDEX IF NOT EXISTS idx_token_daily_date ON token_usage_daily(metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_token_daily_user ON token_usage_daily(user_id, metric_date DESC);


-- ============================================================================
-- 3. ADMIN AUDIT LOGS - Comprehensive audit trail
-- ============================================================================
CREATE TABLE IF NOT EXISTS admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Who performed the action
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_email VARCHAR(255) NOT NULL,
    user_role VARCHAR(50) NOT NULL,

    -- What action was performed
    action VARCHAR(100) NOT NULL,
    action_category VARCHAR(50) NOT NULL
        CHECK (action_category IN ('USER_MANAGEMENT', 'CONTENT', 'SYSTEM', 'SECURITY', 'GOVERNANCE', 'AGENT')),
    severity VARCHAR(20) NOT NULL DEFAULT 'INFO'
        CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),

    -- What resource was affected
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    resource_name VARCHAR(255),

    -- Request context
    ip_address INET,
    user_agent TEXT,
    request_id VARCHAR(100),

    -- Change details
    before_state JSONB,
    after_state JSONB,
    changes JSONB,

    -- Outcome
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,

    -- Timestamp
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Retention metadata
    retention_until TIMESTAMP WITH TIME ZONE,
    is_archived BOOLEAN DEFAULT false
);

COMMENT ON TABLE admin_audit_logs IS 'Comprehensive audit trail for all admin actions';

-- Indexes for audit_logs
CREATE INDEX IF NOT EXISTS idx_audit_user ON admin_audit_logs(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON admin_audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON admin_audit_logs(action, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON admin_audit_logs(severity, timestamp DESC)
    WHERE severity IN ('ERROR', 'CRITICAL');
CREATE INDEX IF NOT EXISTS idx_audit_resource ON admin_audit_logs(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_audit_category ON admin_audit_logs(action_category, timestamp DESC);


-- ============================================================================
-- 4. AGENT PERFORMANCE DAILY - Aggregated agent metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_performance_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Aggregation key
    metric_date DATE NOT NULL,
    agent_type VARCHAR(50) NOT NULL,

    -- Aggregated metrics
    total_executions INTEGER DEFAULT 0,
    successful_executions INTEGER DEFAULT 0,
    failed_executions INTEGER DEFAULT 0,
    timeout_executions INTEGER DEFAULT 0,

    -- Performance
    avg_execution_time_ms INTEGER,
    p50_execution_time_ms INTEGER,
    p95_execution_time_ms INTEGER,
    p99_execution_time_ms INTEGER,
    min_execution_time_ms INTEGER,
    max_execution_time_ms INTEGER,

    -- Quality
    avg_confidence_score FLOAT,

    -- Tokens
    total_input_tokens BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,

    -- Retry stats
    total_retries INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (metric_date, agent_type)
);

COMMENT ON TABLE agent_performance_daily IS 'Daily aggregated agent performance metrics';

CREATE INDEX IF NOT EXISTS idx_agent_daily_date ON agent_performance_daily(metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_agent_daily_type ON agent_performance_daily(agent_type, metric_date DESC);


-- ============================================================================
-- 5. SYSTEM HEALTH SNAPSHOTS - Health status history
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Overall health
    health_status VARCHAR(20) NOT NULL
        CHECK (health_status IN ('HEALTHY', 'DEGRADED', 'UNHEALTHY', 'CRITICAL')),

    -- Component health (JSONB for flexibility)
    components JSONB NOT NULL DEFAULT '{}',
    /*
    Example:
    {
        "database": {"status": "healthy", "latency_ms": 5},
        "llm_nemotron": {"status": "healthy", "latency_ms": 1200},
        "llm_mistral": {"status": "degraded", "latency_ms": 3500},
        "embedding_service": {"status": "healthy", "latency_ms": 300},
        "neo4j": {"status": "healthy"}
    }
    */

    -- Active alerts
    active_alerts JSONB DEFAULT '[]',

    -- System resources
    cpu_usage_percent FLOAT,
    memory_usage_percent FLOAT,
    disk_usage_percent FLOAT,

    -- Timestamp
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Anomaly flag
    is_anomaly BOOLEAN DEFAULT false
);

COMMENT ON TABLE system_health_snapshots IS 'System health status snapshots for monitoring';

CREATE INDEX IF NOT EXISTS idx_health_timestamp ON system_health_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_health_status ON system_health_snapshots(health_status, timestamp DESC)
    WHERE health_status != 'HEALTHY';


-- ============================================================================
-- 6. RAG PERFORMANCE DAILY - RAG quality metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS rag_performance_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Aggregation key
    metric_date DATE NOT NULL,
    strategy VARCHAR(50) NOT NULL,

    -- Query counts
    total_queries INTEGER DEFAULT 0,
    successful_queries INTEGER DEFAULT 0,

    -- Retrieval performance
    avg_retrieval_time_ms INTEGER,
    p95_retrieval_time_ms INTEGER,
    avg_result_count FLOAT,
    avg_similarity_score FLOAT,

    -- Generation performance
    avg_generation_time_ms INTEGER,
    p95_generation_time_ms INTEGER,

    -- Quality
    avg_confidence_score FLOAT,
    queries_with_sources INTEGER DEFAULT 0,

    -- User satisfaction
    avg_user_rating FLOAT,
    thumbs_up_count INTEGER DEFAULT 0,
    thumbs_down_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (metric_date, strategy)
);

COMMENT ON TABLE rag_performance_daily IS 'Daily aggregated RAG performance metrics';

CREATE INDEX IF NOT EXISTS idx_rag_daily_date ON rag_performance_daily(metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_rag_daily_strategy ON rag_performance_daily(strategy, metric_date DESC);


-- ============================================================================
-- 7. DASHBOARD CACHE - Fast dashboard data caching
-- ============================================================================
CREATE TABLE IF NOT EXISTS dashboard_cache (
    cache_key VARCHAR(255) PRIMARY KEY,
    cache_value JSONB NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE dashboard_cache IS 'Dashboard data cache for performance';

CREATE INDEX IF NOT EXISTS idx_cache_expires ON dashboard_cache(expires_at);


-- ============================================================================
-- 8. USER ACTIVITY SUMMARY - User engagement metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_activity_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Aggregation key
    metric_date DATE NOT NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Activity counts
    login_count INTEGER DEFAULT 0,
    query_count INTEGER DEFAULT 0,
    document_uploads INTEGER DEFAULT 0,
    mindmap_generations INTEGER DEFAULT 0,

    -- Session metrics
    total_session_duration_minutes INTEGER DEFAULT 0,
    session_count INTEGER DEFAULT 0,

    -- Feature usage
    features_used JSONB DEFAULT '[]',

    -- Timestamps
    first_activity TIMESTAMP WITH TIME ZONE,
    last_activity TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (metric_date, user_id)
);

COMMENT ON TABLE user_activity_daily IS 'Daily user activity summary for analytics';

CREATE INDEX IF NOT EXISTS idx_user_activity_date ON user_activity_daily(metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_user_activity_user ON user_activity_daily(user_id, metric_date DESC);


-- ============================================================================
-- 9. TRIGGERS - Auto-update timestamps
-- ============================================================================

-- Ensure update_updated_at_column function exists
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply triggers
DROP TRIGGER IF EXISTS update_token_daily_updated_at ON token_usage_daily;
CREATE TRIGGER update_token_daily_updated_at
    BEFORE UPDATE ON token_usage_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_agent_daily_updated_at ON agent_performance_daily;
CREATE TRIGGER update_agent_daily_updated_at
    BEFORE UPDATE ON agent_performance_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_rag_daily_updated_at ON rag_performance_daily;
CREATE TRIGGER update_rag_daily_updated_at
    BEFORE UPDATE ON rag_performance_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_activity_updated_at ON user_activity_daily;
CREATE TRIGGER update_user_activity_updated_at
    BEFORE UPDATE ON user_activity_daily
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- 10. CLEANUP FUNCTION - Auto-cleanup expired cache
-- ============================================================================
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS void AS $$
BEGIN
    DELETE FROM dashboard_cache WHERE expires_at < CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
