-- Migration: 009_query_log_faq.sql
-- AI Agent Query Logging and FAQ Integration
-- Created: 2026-01-11

-- ============================================
-- 1. Query Log Table
-- Stores all AI agent queries for analytics
-- ============================================
CREATE TABLE IF NOT EXISTS query_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Request identification
    user_id VARCHAR(100),
    session_id VARCHAR(100),
    conversation_id UUID,

    -- Query content
    query_text TEXT NOT NULL,
    query_normalized TEXT,
    query_hash VARCHAR(64) NOT NULL,

    -- Classification
    agent_type VARCHAR(50) NOT NULL,
    intent_type VARCHAR(50),
    category VARCHAR(100),
    language VARCHAR(10) DEFAULT 'auto',

    -- Execution metrics
    execution_time_ms INTEGER,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    success BOOLEAN DEFAULT true,

    -- Response summary for FAQ generation
    response_summary TEXT,

    -- Privacy control
    is_public BOOLEAN DEFAULT false,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for query_log
CREATE INDEX IF NOT EXISTS idx_query_log_created_at ON query_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_hash ON query_log(query_hash);
CREATE INDEX IF NOT EXISTS idx_query_log_agent_type ON query_log(agent_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_user ON query_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_query_log_category ON query_log(category, created_at DESC);

-- ============================================
-- 2. Query Aggregates Table
-- Aggregated statistics for FAQ generation
-- ============================================
CREATE TABLE IF NOT EXISTS query_aggregates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Aggregation key
    query_normalized TEXT NOT NULL,
    query_hash VARCHAR(64) NOT NULL UNIQUE,

    -- Representative data
    representative_query TEXT NOT NULL,
    representative_answer TEXT,

    -- Statistics
    frequency_count INTEGER DEFAULT 1,
    last_asked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    first_asked_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    unique_users_count INTEGER DEFAULT 0,

    -- Classification
    agent_type VARCHAR(50),
    intent_type VARCHAR(50),
    category VARCHAR(100),

    -- Quality metrics
    avg_helpfulness_score FLOAT DEFAULT 0.0,
    total_feedback_count INTEGER DEFAULT 0,

    -- FAQ eligibility (auto-publish when frequency >= threshold)
    popularity_score FLOAT DEFAULT 0.0,
    is_faq_eligible BOOLEAN DEFAULT false,
    faq_display_order INTEGER,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for query_aggregates
CREATE INDEX IF NOT EXISTS idx_aggregates_popularity ON query_aggregates(popularity_score DESC);
CREATE INDEX IF NOT EXISTS idx_aggregates_frequency ON query_aggregates(frequency_count DESC);
CREATE INDEX IF NOT EXISTS idx_aggregates_faq ON query_aggregates(is_faq_eligible, popularity_score DESC)
    WHERE is_faq_eligible = true;
CREATE INDEX IF NOT EXISTS idx_aggregates_category ON query_aggregates(category, popularity_score DESC);

-- ============================================
-- 3. FAQ Items Table
-- Curated FAQ items (static + dynamic + curated)
-- ============================================
CREATE TABLE IF NOT EXISTS faq_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source
    source_type VARCHAR(20) NOT NULL
        CHECK (source_type IN ('static', 'dynamic', 'curated')),
    query_aggregate_id UUID REFERENCES query_aggregates(id) ON DELETE SET NULL,

    -- Content (multilingual)
    question_en TEXT,
    question_ko TEXT,
    question_ja TEXT,
    answer_en TEXT,
    answer_ko TEXT,
    answer_ja TEXT,

    -- Classification
    category VARCHAR(100) NOT NULL,
    tags JSONB DEFAULT '[]',

    -- Display
    display_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    is_pinned BOOLEAN DEFAULT false,

    -- Statistics
    view_count INTEGER DEFAULT 0,
    helpful_count INTEGER DEFAULT 0,
    not_helpful_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for faq_items
CREATE INDEX IF NOT EXISTS idx_faq_items_active ON faq_items(is_active, display_order);
CREATE INDEX IF NOT EXISTS idx_faq_items_category ON faq_items(category, display_order)
    WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_faq_items_view_count ON faq_items(view_count DESC)
    WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_faq_items_pinned ON faq_items(is_pinned DESC, display_order)
    WHERE is_active = true;

-- ============================================
-- 4. Triggers for updated_at
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_query_log_updated_at ON query_log;
CREATE TRIGGER update_query_log_updated_at
    BEFORE UPDATE ON query_log
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_query_aggregates_updated_at ON query_aggregates;
CREATE TRIGGER update_query_aggregates_updated_at
    BEFORE UPDATE ON query_aggregates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_faq_items_updated_at ON faq_items;
CREATE TRIGGER update_faq_items_updated_at
    BEFORE UPDATE ON faq_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 5. Function: Calculate Popularity Score
-- ============================================
CREATE OR REPLACE FUNCTION calculate_popularity_score(
    p_frequency INTEGER,
    p_recency_days FLOAT,
    p_helpfulness_ratio FLOAT,
    p_unique_users INTEGER
) RETURNS FLOAT AS $$
DECLARE
    recency_factor FLOAT;
    diversity_factor FLOAT;
    helpfulness_factor FLOAT;
    frequency_score FLOAT;
BEGIN
    -- Recency decay: more recent = higher score
    recency_factor := 1.0 / (1.0 + (p_recency_days / 30.0));

    -- User diversity: more unique users = higher score
    diversity_factor := LEAST(1.0, p_unique_users / 10.0);

    -- Helpfulness: higher ratio = higher score
    helpfulness_factor := 0.5 + (COALESCE(p_helpfulness_ratio, 0.5) * 0.5);

    -- Base score from frequency (log scale)
    frequency_score := LOG(2, 1 + p_frequency);

    RETURN frequency_score * recency_factor * diversity_factor * helpfulness_factor;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 6. Function: Update Aggregate and Check FAQ Eligibility
-- ============================================
CREATE OR REPLACE FUNCTION update_aggregate_and_check_faq()
RETURNS TRIGGER AS $$
DECLARE
    recency_days FLOAT;
    helpfulness_ratio FLOAT;
    new_score FLOAT;
    faq_threshold INTEGER := 3;  -- Minimum frequency for auto FAQ eligibility
BEGIN
    -- Calculate recency
    recency_days := EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - NEW.last_asked_at)) / 86400.0;

    -- Calculate helpfulness ratio
    IF NEW.total_feedback_count > 0 THEN
        helpfulness_ratio := NEW.avg_helpfulness_score;
    ELSE
        helpfulness_ratio := 0.5;
    END IF;

    -- Calculate new popularity score
    new_score := calculate_popularity_score(
        NEW.frequency_count,
        recency_days,
        helpfulness_ratio,
        NEW.unique_users_count
    );

    -- Update score and FAQ eligibility
    NEW.popularity_score := new_score;
    NEW.is_faq_eligible := (NEW.frequency_count >= faq_threshold);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_aggregate_score ON query_aggregates;
CREATE TRIGGER update_aggregate_score
    BEFORE INSERT OR UPDATE ON query_aggregates
    FOR EACH ROW
    EXECUTE FUNCTION update_aggregate_and_check_faq();

-- ============================================
-- 7. Comments
-- ============================================
COMMENT ON TABLE query_log IS 'Stores all AI agent queries for analytics and FAQ generation';
COMMENT ON TABLE query_aggregates IS 'Aggregated statistics for similar queries';
COMMENT ON TABLE faq_items IS 'FAQ items displayed on the FAQ page (static, dynamic, curated)';

COMMENT ON COLUMN query_log.query_hash IS 'SHA-256 hash of normalized query for deduplication';
COMMENT ON COLUMN query_log.is_public IS 'Whether query can be shown in public FAQ';
COMMENT ON COLUMN query_aggregates.popularity_score IS 'Computed score for FAQ ranking';
COMMENT ON COLUMN query_aggregates.is_faq_eligible IS 'Auto-set to true when frequency >= threshold';
COMMENT ON COLUMN faq_items.source_type IS 'static=hardcoded, dynamic=from queries, curated=admin edited';
