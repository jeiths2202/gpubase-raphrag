-- ============================================
-- Real-time Analytics Dashboard Schema
-- Migration: 023_analytics_dashboard.sql
-- ============================================

-- Query Analytics: 쿼리 분석 테이블
CREATE TABLE IF NOT EXISTS query_analytics (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    conversation_id UUID,

    -- Response metrics
    response_time_ms INTEGER,
    was_answered BOOLEAN DEFAULT TRUE,
    answer_source VARCHAR(50),  -- vector, graph, hybrid, code, cache
    sources_count INTEGER DEFAULT 0,

    -- Quality metrics (from RAG evaluation)
    evaluation_id UUID,
    faithfulness_score FLOAT,
    context_relevance_score FLOAT,
    answer_relevancy_score FLOAT,
    overall_quality_score FLOAT,

    -- Feedback
    feedback_type VARCHAR(20),  -- thumbs_up, thumbs_down
    feedback_received_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for query analytics
CREATE INDEX IF NOT EXISTS idx_query_analytics_hash ON query_analytics(query_hash);
CREATE INDEX IF NOT EXISTS idx_query_analytics_user ON query_analytics(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_analytics_created ON query_analytics(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_analytics_answered ON query_analytics(was_answered, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_analytics_quality ON query_analytics(overall_quality_score) WHERE overall_quality_score IS NOT NULL;

-- ============================================
-- Document Citation Analytics
-- ============================================

CREATE TABLE IF NOT EXISTS document_citation_analytics (
    id SERIAL PRIMARY KEY,
    doc_id VARCHAR(100) NOT NULL,
    doc_name VARCHAR(500),
    chunk_id VARCHAR(100),

    -- Citation context
    query_hash VARCHAR(64),
    query_text TEXT,
    user_id VARCHAR(100) NOT NULL,

    -- Relevance
    relevance_score FLOAT,
    position_in_results INTEGER,
    was_helpful BOOLEAN,

    -- Timestamps
    cited_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_citation_doc ON document_citation_analytics(doc_id, cited_at DESC);
CREATE INDEX IF NOT EXISTS idx_doc_citation_cited ON document_citation_analytics(cited_at DESC);
CREATE INDEX IF NOT EXISTS idx_doc_citation_helpful ON document_citation_analytics(doc_id, was_helpful);

-- ============================================
-- System Performance Metrics
-- ============================================

CREATE TABLE IF NOT EXISTS system_performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Request metrics
    endpoint VARCHAR(200) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,

    -- Error info
    is_error BOOLEAN DEFAULT FALSE,
    error_type VARCHAR(100),
    error_message TEXT,

    -- Context
    user_id VARCHAR(100),
    request_id VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_perf_metrics_timestamp ON system_performance_metrics(metric_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_perf_metrics_endpoint ON system_performance_metrics(endpoint, metric_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_perf_metrics_errors ON system_performance_metrics(is_error, metric_timestamp DESC) WHERE is_error = TRUE;

-- ============================================
-- Hourly Aggregations (Pre-computed)
-- ============================================

CREATE TABLE IF NOT EXISTS analytics_hourly_aggregates (
    id SERIAL PRIMARY KEY,
    hour_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Query metrics
    total_queries INTEGER DEFAULT 0,
    unique_queries INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0,

    -- Response metrics
    avg_response_time_ms FLOAT,
    p50_response_time_ms FLOAT,
    p90_response_time_ms FLOAT,
    p95_response_time_ms FLOAT,

    -- Quality metrics
    avg_faithfulness FLOAT,
    avg_context_relevance FLOAT,
    avg_answer_relevancy FLOAT,
    avg_overall_quality FLOAT,
    evaluations_count INTEGER DEFAULT 0,

    -- Feedback metrics
    thumbs_up_count INTEGER DEFAULT 0,
    thumbs_down_count INTEGER DEFAULT 0,

    -- Unanswered
    unanswered_count INTEGER DEFAULT 0,

    -- Error metrics
    error_count INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(hour_timestamp)
);

CREATE INDEX IF NOT EXISTS idx_hourly_agg_timestamp ON analytics_hourly_aggregates(hour_timestamp DESC);

-- ============================================
-- Daily Aggregations
-- ============================================

CREATE TABLE IF NOT EXISTS analytics_daily_aggregates (
    id SERIAL PRIMARY KEY,
    date_timestamp DATE NOT NULL,

    -- Query metrics
    total_queries INTEGER DEFAULT 0,
    unique_queries INTEGER DEFAULT 0,
    unique_users INTEGER DEFAULT 0,
    new_users INTEGER DEFAULT 0,
    returning_users INTEGER DEFAULT 0,

    -- Response metrics
    avg_response_time_ms FLOAT,
    p50_response_time_ms FLOAT,
    p90_response_time_ms FLOAT,

    -- Quality metrics
    avg_faithfulness FLOAT,
    avg_context_relevance FLOAT,
    avg_answer_relevancy FLOAT,
    avg_overall_quality FLOAT,
    evaluations_count INTEGER DEFAULT 0,

    -- Quality distribution
    quality_excellent_count INTEGER DEFAULT 0,  -- >= 0.8
    quality_good_count INTEGER DEFAULT 0,       -- >= 0.6
    quality_fair_count INTEGER DEFAULT 0,       -- >= 0.4
    quality_poor_count INTEGER DEFAULT 0,       -- < 0.4

    -- Feedback metrics
    thumbs_up_count INTEGER DEFAULT 0,
    thumbs_down_count INTEGER DEFAULT 0,
    satisfaction_rate FLOAT,

    -- Unanswered
    unanswered_count INTEGER DEFAULT 0,
    unanswered_rate FLOAT,

    -- Error metrics
    total_requests INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_rate FLOAT,

    -- Session metrics
    total_conversations INTEGER DEFAULT 0,
    avg_queries_per_session FLOAT,
    avg_session_duration_min FLOAT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(date_timestamp)
);

CREATE INDEX IF NOT EXISTS idx_daily_agg_date ON analytics_daily_aggregates(date_timestamp DESC);

-- ============================================
-- Popular Queries Cache
-- ============================================

CREATE TABLE IF NOT EXISTS popular_queries_cache (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,

    -- Counts
    total_count INTEGER DEFAULT 1,
    period_count INTEGER DEFAULT 1,  -- count in current period

    -- Metrics
    avg_response_time_ms FLOAT,
    avg_satisfaction FLOAT,

    -- Timestamps
    first_asked_at TIMESTAMP WITH TIME ZONE,
    last_asked_at TIMESTAMP WITH TIME ZONE,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(query_hash)
);

CREATE INDEX IF NOT EXISTS idx_popular_queries_count ON popular_queries_cache(total_count DESC);
CREATE INDEX IF NOT EXISTS idx_popular_queries_recent ON popular_queries_cache(last_asked_at DESC);

-- ============================================
-- Unanswered Queries Tracking
-- ============================================

CREATE TABLE IF NOT EXISTS unanswered_queries (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,

    -- Counts
    occurrence_count INTEGER DEFAULT 1,

    -- Failure info
    failure_reasons JSONB DEFAULT '[]'::JSONB,

    -- Timestamps
    first_asked_at TIMESTAMP WITH TIME ZONE,
    last_asked_at TIMESTAMP WITH TIME ZONE,

    -- Status
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,

    UNIQUE(query_hash)
);

CREATE INDEX IF NOT EXISTS idx_unanswered_count ON unanswered_queries(occurrence_count DESC) WHERE is_resolved = FALSE;

-- ============================================
-- User Activity Summary
-- ============================================

CREATE TABLE IF NOT EXISTS user_activity_summary (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,

    -- Query metrics
    total_queries INTEGER DEFAULT 0,
    total_conversations INTEGER DEFAULT 0,

    -- Time metrics
    avg_queries_per_session FLOAT,
    most_active_hour INTEGER,  -- 0-23

    -- Quality metrics
    avg_response_satisfaction FLOAT,
    thumbs_up_given INTEGER DEFAULT 0,
    thumbs_down_given INTEGER DEFAULT 0,

    -- Topics
    top_query_topics JSONB DEFAULT '[]'::JSONB,

    -- Timestamps
    first_active_at TIMESTAMP WITH TIME ZONE,
    last_active_at TIMESTAMP WITH TIME ZONE,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_activity_queries ON user_activity_summary(total_queries DESC);
CREATE INDEX IF NOT EXISTS idx_user_activity_recent ON user_activity_summary(last_active_at DESC);

-- ============================================
-- Content Gaps (Identified from queries)
-- ============================================

CREATE TABLE IF NOT EXISTS content_gaps (
    id SERIAL PRIMARY KEY,
    topic VARCHAR(200) NOT NULL,

    -- Query info
    query_examples JSONB DEFAULT '[]'::JSONB,
    query_count INTEGER DEFAULT 0,

    -- Coverage
    current_coverage_score FLOAT DEFAULT 0.0,

    -- Recommendation
    recommendation TEXT,

    -- Status
    status VARCHAR(20) DEFAULT 'identified',  -- identified, in_progress, resolved
    resolved_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(topic)
);

CREATE INDEX IF NOT EXISTS idx_content_gaps_status ON content_gaps(status, query_count DESC);

-- ============================================
-- Views for Quick Analytics
-- ============================================

-- Real-time dashboard summary view
CREATE OR REPLACE VIEW v_dashboard_summary AS
SELECT
    COUNT(*) as total_queries_today,
    COUNT(DISTINCT user_id) as unique_users_today,
    AVG(response_time_ms) as avg_response_time_ms,
    AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL) as avg_quality_score,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up_today,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down_today,
    CASE
        WHEN COUNT(*) FILTER (WHERE feedback_type IS NOT NULL) > 0
        THEN COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::FLOAT /
             COUNT(*) FILTER (WHERE feedback_type IS NOT NULL)
        ELSE 0.0
    END as satisfaction_rate,
    COUNT(*) FILTER (WHERE was_answered = FALSE) as unanswered_count
FROM query_analytics
WHERE created_at >= CURRENT_DATE;

-- Hourly usage pattern view
CREATE OR REPLACE VIEW v_hourly_usage_pattern AS
SELECT
    EXTRACT(HOUR FROM created_at)::INTEGER as hour,
    COUNT(*) as query_count,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(response_time_ms) as avg_response_time_ms
FROM query_analytics
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY EXTRACT(HOUR FROM created_at)
ORDER BY hour;

-- Top cited documents view
CREATE OR REPLACE VIEW v_top_cited_documents AS
SELECT
    doc_id,
    doc_name,
    COUNT(*) as citation_count,
    COUNT(DISTINCT query_hash) as unique_queries,
    AVG(relevance_score) as avg_relevance_score,
    COUNT(*) FILTER (WHERE was_helpful = TRUE) as helpful_count,
    COUNT(*) FILTER (WHERE was_helpful = FALSE) as unhelpful_count,
    CASE
        WHEN COUNT(*) FILTER (WHERE was_helpful IS NOT NULL) > 0
        THEN COUNT(*) FILTER (WHERE was_helpful = TRUE)::FLOAT /
             COUNT(*) FILTER (WHERE was_helpful IS NOT NULL)
        ELSE NULL
    END as helpfulness_rate,
    MAX(cited_at) as last_cited_at
FROM document_citation_analytics
WHERE cited_at >= NOW() - INTERVAL '30 days'
GROUP BY doc_id, doc_name
ORDER BY citation_count DESC;

-- Quality trend view (last 7 days)
CREATE OR REPLACE VIEW v_quality_trend_7days AS
SELECT
    DATE_TRUNC('day', created_at) as date,
    AVG(faithfulness_score) FILTER (WHERE faithfulness_score IS NOT NULL) as avg_faithfulness,
    AVG(context_relevance_score) FILTER (WHERE context_relevance_score IS NOT NULL) as avg_context_relevance,
    AVG(answer_relevancy_score) FILTER (WHERE answer_relevancy_score IS NOT NULL) as avg_answer_relevancy,
    AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL) as avg_overall_quality,
    COUNT(*) FILTER (WHERE overall_quality_score IS NOT NULL) as evaluation_count
FROM query_analytics
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY date;

-- Error rate by endpoint view
CREATE OR REPLACE VIEW v_error_rate_by_endpoint AS
SELECT
    endpoint,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE is_error = TRUE) as error_count,
    CASE
        WHEN COUNT(*) > 0
        THEN COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / COUNT(*)
        ELSE 0.0
    END as error_rate,
    AVG(response_time_ms) as avg_response_time_ms
FROM system_performance_metrics
WHERE metric_timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY endpoint
ORDER BY error_count DESC;

-- ============================================
-- Function: Aggregate hourly stats
-- ============================================

CREATE OR REPLACE FUNCTION aggregate_hourly_analytics()
RETURNS void AS $$
DECLARE
    target_hour TIMESTAMP WITH TIME ZONE;
BEGIN
    -- Get the previous hour
    target_hour := DATE_TRUNC('hour', NOW() - INTERVAL '1 hour');

    INSERT INTO analytics_hourly_aggregates (
        hour_timestamp,
        total_queries, unique_queries, unique_users,
        avg_response_time_ms, p50_response_time_ms, p90_response_time_ms, p95_response_time_ms,
        avg_faithfulness, avg_context_relevance, avg_answer_relevancy, avg_overall_quality,
        evaluations_count,
        thumbs_up_count, thumbs_down_count,
        unanswered_count, error_count
    )
    SELECT
        target_hour,
        COUNT(*),
        COUNT(DISTINCT query_hash),
        COUNT(DISTINCT user_id),
        AVG(response_time_ms),
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms),
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY response_time_ms),
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms),
        AVG(faithfulness_score) FILTER (WHERE faithfulness_score IS NOT NULL),
        AVG(context_relevance_score) FILTER (WHERE context_relevance_score IS NOT NULL),
        AVG(answer_relevancy_score) FILTER (WHERE answer_relevancy_score IS NOT NULL),
        AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL),
        COUNT(*) FILTER (WHERE overall_quality_score IS NOT NULL),
        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up'),
        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down'),
        COUNT(*) FILTER (WHERE was_answered = FALSE),
        0  -- error_count from performance metrics
    FROM query_analytics
    WHERE created_at >= target_hour AND created_at < target_hour + INTERVAL '1 hour'
    ON CONFLICT (hour_timestamp) DO UPDATE SET
        total_queries = EXCLUDED.total_queries,
        unique_queries = EXCLUDED.unique_queries,
        unique_users = EXCLUDED.unique_users,
        avg_response_time_ms = EXCLUDED.avg_response_time_ms,
        p50_response_time_ms = EXCLUDED.p50_response_time_ms,
        p90_response_time_ms = EXCLUDED.p90_response_time_ms,
        p95_response_time_ms = EXCLUDED.p95_response_time_ms,
        avg_faithfulness = EXCLUDED.avg_faithfulness,
        avg_context_relevance = EXCLUDED.avg_context_relevance,
        avg_answer_relevancy = EXCLUDED.avg_answer_relevancy,
        avg_overall_quality = EXCLUDED.avg_overall_quality,
        evaluations_count = EXCLUDED.evaluations_count,
        thumbs_up_count = EXCLUDED.thumbs_up_count,
        thumbs_down_count = EXCLUDED.thumbs_down_count,
        unanswered_count = EXCLUDED.unanswered_count;
END;
$$ LANGUAGE plpgsql;

-- Comment
COMMENT ON TABLE query_analytics IS '쿼리별 분석 데이터 - 실시간 분석 대시보드용';
COMMENT ON TABLE document_citation_analytics IS '문서 인용 분석 - 콘텐츠 효과 측정용';
COMMENT ON TABLE system_performance_metrics IS '시스템 성능 메트릭 - 응답 지연시간, 에러율 등';
COMMENT ON TABLE analytics_hourly_aggregates IS '시간별 집계 데이터 - 빠른 조회를 위한 사전 계산';
COMMENT ON TABLE analytics_daily_aggregates IS '일별 집계 데이터 - 트렌드 분석용';
