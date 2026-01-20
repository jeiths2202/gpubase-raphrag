-- Migration: 022_user_feedback.sql
-- Description: User feedback system for RAG response quality
-- Features: 👍/👎 feedback, HITL learning, response consistency, citation feedback

-- ============================================
-- 1. User Feedback Table
-- ============================================

CREATE TABLE IF NOT EXISTS user_feedbacks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),

    -- References
    message_id UUID NOT NULL,
    conversation_id UUID NOT NULL,
    user_id VARCHAR(100) NOT NULL,

    -- Feedback data
    feedback_type VARCHAR(20) NOT NULL CHECK (feedback_type IN ('thumbs_up', 'thumbs_down')),
    categories JSONB DEFAULT '[]',
    comment TEXT,
    expected_answer TEXT,

    -- Processing status
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'applied', 'dismissed')),
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,

    -- Context snapshot (for HITL)
    query_snapshot TEXT,
    answer_snapshot TEXT,
    sources_snapshot JSONB DEFAULT '[]',

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for user_feedbacks
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_message_id ON user_feedbacks(message_id);
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_conversation_id ON user_feedbacks(conversation_id);
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_user_id ON user_feedbacks(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_type ON user_feedbacks(feedback_type);
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_status ON user_feedbacks(status);
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_created_at ON user_feedbacks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_categories ON user_feedbacks USING gin(categories);

-- ============================================
-- 2. Citation Feedback Table
-- ============================================

CREATE TABLE IF NOT EXISTS citation_feedbacks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- References
    message_id UUID NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    source_index INTEGER NOT NULL,

    -- Feedback
    feedback_type VARCHAR(20) NOT NULL CHECK (feedback_type IN ('helpful', 'unhelpful', 'incorrect', 'outdated')),
    comment TEXT,

    -- Source snapshot
    doc_id VARCHAR(100),
    doc_name VARCHAR(500),
    chunk_id VARCHAR(100),

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for citation_feedbacks
CREATE INDEX IF NOT EXISTS idx_citation_feedbacks_message_id ON citation_feedbacks(message_id);
CREATE INDEX IF NOT EXISTS idx_citation_feedbacks_doc_id ON citation_feedbacks(doc_id);
CREATE INDEX IF NOT EXISTS idx_citation_feedbacks_type ON citation_feedbacks(feedback_type);

-- ============================================
-- 3. HITL Re-ranking Adjustments Table
-- ============================================

CREATE TABLE IF NOT EXISTS hitl_reranking_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Document/Chunk reference
    document_id VARCHAR(100) NOT NULL,
    chunk_id VARCHAR(100),

    -- Query pattern (generalized)
    query_pattern TEXT NOT NULL,
    query_embedding vector(4096),  -- For semantic matching

    -- Adjustment
    adjustment_score FLOAT NOT NULL CHECK (adjustment_score >= -1.0 AND adjustment_score <= 1.0),
    confidence FLOAT DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),

    -- Aggregated from feedbacks
    feedback_count INTEGER DEFAULT 1,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    applied_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for hitl_reranking_adjustments
CREATE INDEX IF NOT EXISTS idx_hitl_reranking_document_id ON hitl_reranking_adjustments(document_id);
CREATE INDEX IF NOT EXISTS idx_hitl_reranking_chunk_id ON hitl_reranking_adjustments(chunk_id);
CREATE INDEX IF NOT EXISTS idx_hitl_reranking_active ON hitl_reranking_adjustments(is_active) WHERE is_active = TRUE;

-- ============================================
-- 4. Response Consistency Cache Table
-- ============================================

CREATE TABLE IF NOT EXISTS response_consistency_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Query identification
    query_hash VARCHAR(64) NOT NULL,  -- SHA256 hash of normalized query
    query_text TEXT NOT NULL,
    query_embedding vector(4096),

    -- Cached response
    answer_text TEXT NOT NULL,
    sources JSONB DEFAULT '[]',

    -- Quality metrics
    feedback_score FLOAT DEFAULT 0.0,
    usage_count INTEGER DEFAULT 1,

    -- Consistency tracking
    answer_variations INTEGER DEFAULT 1,
    consistency_score FLOAT DEFAULT 1.0,

    -- Metadata
    language VARCHAR(10) DEFAULT 'auto',
    strategy VARCHAR(20) DEFAULT 'auto',
    last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (NOW() + INTERVAL '30 days')
);

-- Indexes for response_consistency_cache
CREATE UNIQUE INDEX IF NOT EXISTS idx_consistency_cache_hash ON response_consistency_cache(query_hash);
CREATE INDEX IF NOT EXISTS idx_consistency_cache_feedback ON response_consistency_cache(feedback_score DESC);
CREATE INDEX IF NOT EXISTS idx_consistency_cache_usage ON response_consistency_cache(usage_count DESC);
CREATE INDEX IF NOT EXISTS idx_consistency_cache_expires ON response_consistency_cache(expires_at);

-- ============================================
-- 5. Feedback Aggregation View
-- ============================================

CREATE OR REPLACE VIEW v_feedback_summary AS
SELECT
    message_id,
    conversation_id,
    COUNT(*) as total_count,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up_count,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down_count,
    ROUND(
        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::NUMERIC /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as positive_ratio,
    jsonb_agg(DISTINCT categories) FILTER (WHERE categories != '[]') as all_categories
FROM user_feedbacks
GROUP BY message_id, conversation_id;

-- ============================================
-- 6. Daily Feedback Stats View
-- ============================================

CREATE OR REPLACE VIEW v_daily_feedback_stats AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_feedbacks,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down,
    ROUND(
        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::NUMERIC /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as satisfaction_rate,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT conversation_id) as unique_conversations
FROM user_feedbacks
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ============================================
-- 7. Source Quality Aggregation View
-- ============================================

CREATE OR REPLACE VIEW v_source_quality AS
SELECT
    doc_id,
    doc_name,
    COUNT(*) as total_feedbacks,
    COUNT(*) FILTER (WHERE feedback_type = 'helpful') as helpful_count,
    COUNT(*) FILTER (WHERE feedback_type = 'unhelpful') as unhelpful_count,
    COUNT(*) FILTER (WHERE feedback_type = 'incorrect') as incorrect_count,
    COUNT(*) FILTER (WHERE feedback_type = 'outdated') as outdated_count,
    ROUND(
        COUNT(*) FILTER (WHERE feedback_type = 'helpful')::NUMERIC /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as helpfulness_rate
FROM citation_feedbacks
WHERE doc_id IS NOT NULL
GROUP BY doc_id, doc_name
ORDER BY total_feedbacks DESC;

-- ============================================
-- 8. Update Trigger for user_feedbacks
-- ============================================

CREATE OR REPLACE FUNCTION update_user_feedback_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_user_feedback_timestamp ON user_feedbacks;
CREATE TRIGGER trigger_update_user_feedback_timestamp
    BEFORE UPDATE ON user_feedbacks
    FOR EACH ROW
    EXECUTE FUNCTION update_user_feedback_timestamp();

-- ============================================
-- 9. Cleanup Function for Expired Cache
-- ============================================

CREATE OR REPLACE FUNCTION cleanup_expired_consistency_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM response_consistency_cache
    WHERE expires_at < NOW();

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 10. Grant Permissions
-- ============================================

-- Note: Adjust role name as needed
-- GRANT SELECT, INSERT, UPDATE, DELETE ON user_feedbacks TO kms_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON citation_feedbacks TO kms_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON hitl_reranking_adjustments TO kms_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON response_consistency_cache TO kms_app;
-- GRANT SELECT ON v_feedback_summary TO kms_app;
-- GRANT SELECT ON v_daily_feedback_stats TO kms_app;
-- GRANT SELECT ON v_source_quality TO kms_app;

-- ============================================
-- Migration complete
-- ============================================
