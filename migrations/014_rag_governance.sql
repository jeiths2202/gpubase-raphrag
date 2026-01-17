-- Migration: RAG Configuration & Governance
-- Version: 014
-- Description: RAG profiles, A/B experiments, and metrics for multi-tenant governance

-- =============================================================================
-- RAG Profiles Table
-- Stores versioned RAG configuration settings per space/project
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Multi-tenancy: NULL = global default
    space_id VARCHAR(100),
    project_id VARCHAR(100),

    -- Ownership and audit
    created_by UUID NOT NULL,

    -- Version tracking (immutable - create new version instead of update)
    embedding_version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN DEFAULT true,

    -- Chunking configuration
    chunk_strategy VARCHAR(50) DEFAULT 'semantic' CHECK (chunk_strategy IN ('semantic', 'paragraph', 'sentence', 'header', 'fixed')),
    chunk_size INTEGER DEFAULT 512 CHECK (chunk_size >= 100 AND chunk_size <= 4000),
    chunk_overlap INTEGER DEFAULT 80 CHECK (chunk_overlap >= 0 AND chunk_overlap <= 500),
    min_chunk_size INTEGER DEFAULT 100,
    max_chunk_size INTEGER DEFAULT 1000,
    language VARCHAR(10) DEFAULT 'auto',

    -- Embedding configuration
    embedding_model VARCHAR(100) DEFAULT 'nv-embedqa-mistral-7b-v2',
    embedding_dimension INTEGER DEFAULT 4096,
    embedding_normalize BOOLEAN DEFAULT true,
    embedding_batch_size INTEGER DEFAULT 64,

    -- Image ingestion configuration
    image_enabled BOOLEAN DEFAULT true,
    ocr_engine VARCHAR(50) DEFAULT 'vision-llm' CHECK (ocr_engine IN ('tesseract', 'paddle', 'vision-llm')),
    image_dpi INTEGER DEFAULT 300,
    layout_analysis BOOLEAN DEFAULT true,
    caption_generation BOOLEAN DEFAULT true,
    image_chunk_strategy VARCHAR(50) DEFAULT 'layout_block',

    -- Retrieval configuration
    retrieval_strategy VARCHAR(50) DEFAULT 'hybrid' CHECK (retrieval_strategy IN ('vector', 'graph', 'hybrid')),
    top_k INTEGER DEFAULT 5 CHECK (top_k >= 1 AND top_k <= 50),
    score_threshold FLOAT DEFAULT 0.7 CHECK (score_threshold >= 0.0 AND score_threshold <= 1.0),
    hybrid_alpha FLOAT DEFAULT 0.5 CHECK (hybrid_alpha >= 0.0 AND hybrid_alpha <= 1.0),

    -- Generation configuration
    temperature FLOAT DEFAULT 0.7 CHECK (temperature >= 0.0 AND temperature <= 2.0),
    max_tokens INTEGER DEFAULT 2048 CHECK (max_tokens >= 100 AND max_tokens <= 16384),

    -- A/B testing support
    traffic_percentage INTEGER DEFAULT 100 CHECK (traffic_percentage >= 0 AND traffic_percentage <= 100),
    experiment_id UUID,  -- Links to active experiment

    -- Extended metadata (JSONB for flexibility)
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT rag_profiles_unique_name_per_space UNIQUE (space_id, project_id, name)
);

-- =============================================================================
-- RAG Experiments Table
-- A/B testing experiments comparing multiple profiles
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_experiments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Multi-tenancy scope
    space_id VARCHAR(100),

    -- Baseline profile (control group)
    baseline_profile_id UUID NOT NULL REFERENCES rag_profiles(id) ON DELETE RESTRICT,

    -- Status lifecycle: draft -> active -> paused -> completed
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed')),

    -- Timeline
    started_at TIMESTAMP WITH TIME ZONE,
    ended_at TIMESTAMP WITH TIME ZONE,

    -- Aggregated counters (updated by batch job)
    total_queries INTEGER DEFAULT 0,

    -- Ownership
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Experiment Variants Table
-- Each experiment can have multiple variant profiles
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_experiment_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES rag_experiments(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES rag_profiles(id) ON DELETE RESTRICT,

    -- Traffic allocation (all variants in an experiment should sum to 100)
    traffic_ratio FLOAT NOT NULL DEFAULT 0.0 CHECK (traffic_ratio >= 0.0 AND traffic_ratio <= 1.0),

    -- Variant label for display
    variant_name VARCHAR(50),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_variant_per_experiment UNIQUE (experiment_id, profile_id)
);

-- =============================================================================
-- Experiment Metrics Table
-- Daily aggregated metrics for each profile in an experiment
-- =============================================================================
CREATE TABLE IF NOT EXISTS rag_experiment_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES rag_experiments(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES rag_profiles(id) ON DELETE CASCADE,
    metric_date DATE NOT NULL,

    -- Query metrics
    query_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,

    -- Performance metrics
    avg_latency_ms INTEGER,
    p50_latency_ms INTEGER,
    p95_latency_ms INTEGER,
    p99_latency_ms INTEGER,

    -- Retrieval quality metrics
    avg_similarity_score FLOAT,
    avg_chunks_used FLOAT,
    retrieval_hit_rate FLOAT,  -- Top-K 중 실제 사용된 비율

    -- Token consumption
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    estimated_cost FLOAT DEFAULT 0.0,

    -- User satisfaction metrics
    thumbs_up INTEGER DEFAULT 0,
    thumbs_down INTEGER DEFAULT 0,
    regenerate_count INTEGER DEFAULT 0,
    follow_up_count INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_metric_per_profile_date UNIQUE (experiment_id, profile_id, metric_date)
);

-- =============================================================================
-- Document-Profile Assignment Table
-- Links documents to specific RAG profiles (overrides space default)
-- =============================================================================
CREATE TABLE IF NOT EXISTS document_rag_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id VARCHAR(100) NOT NULL,
    profile_id UUID NOT NULL REFERENCES rag_profiles(id) ON DELETE CASCADE,

    -- Embedding status for this document under this profile
    embedding_version INTEGER NOT NULL,
    embedding_status VARCHAR(20) DEFAULT 'pending' CHECK (embedding_status IN ('pending', 'processing', 'completed', 'failed')),
    embedding_started_at TIMESTAMP WITH TIME ZONE,
    embedding_completed_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    created_by UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_doc_profile UNIQUE (document_id, profile_id)
);

-- =============================================================================
-- Alter existing query_log table to track RAG profile usage
-- =============================================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'query_log' AND column_name = 'rag_profile_id'
    ) THEN
        ALTER TABLE query_log ADD COLUMN rag_profile_id UUID REFERENCES rag_profiles(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'query_log' AND column_name = 'embedding_version'
    ) THEN
        ALTER TABLE query_log ADD COLUMN embedding_version INTEGER;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'query_log' AND column_name = 'experiment_id'
    ) THEN
        ALTER TABLE query_log ADD COLUMN experiment_id UUID REFERENCES rag_experiments(id);
    END IF;
END $$;

-- =============================================================================
-- Indexes for performance
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_rag_profiles_space ON rag_profiles(space_id, project_id, is_active);
CREATE INDEX IF NOT EXISTS idx_rag_profiles_active ON rag_profiles(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_rag_experiments_status ON rag_experiments(status, space_id);
CREATE INDEX IF NOT EXISTS idx_rag_experiments_active ON rag_experiments(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_experiment_variants_experiment ON rag_experiment_variants(experiment_id);
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_date ON rag_experiment_metrics(experiment_id, metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_experiment_metrics_profile ON rag_experiment_metrics(profile_id, metric_date DESC);
CREATE INDEX IF NOT EXISTS idx_doc_profiles_document ON document_rag_profiles(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_profiles_profile ON document_rag_profiles(profile_id, embedding_status);
CREATE INDEX IF NOT EXISTS idx_query_log_profile ON query_log(rag_profile_id, created_at DESC) WHERE rag_profile_id IS NOT NULL;

-- =============================================================================
-- Insert default global profile
-- =============================================================================
INSERT INTO rag_profiles (
    id, name, description, space_id, project_id, created_by,
    embedding_version, is_active, traffic_percentage
)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'default',
    'Global default RAG profile',
    NULL, NULL,
    '00000000-0000-0000-0000-000000000000',  -- System user
    1, true, 100
)
ON CONFLICT (space_id, project_id, name) DO NOTHING;

-- =============================================================================
-- Comments for documentation
-- =============================================================================
COMMENT ON TABLE rag_profiles IS 'Versioned RAG configuration profiles for multi-tenant governance';
COMMENT ON TABLE rag_experiments IS 'A/B testing experiments comparing RAG profiles';
COMMENT ON TABLE rag_experiment_variants IS 'Variant profiles in an A/B experiment with traffic allocation';
COMMENT ON TABLE rag_experiment_metrics IS 'Daily aggregated metrics for experiment analysis';
COMMENT ON TABLE document_rag_profiles IS 'Document-level RAG profile assignments';

COMMENT ON COLUMN rag_profiles.embedding_version IS 'Incremented when incompatible changes require re-embedding';
COMMENT ON COLUMN rag_profiles.traffic_percentage IS 'Traffic allocation for A/B testing (0-100)';
COMMENT ON COLUMN rag_experiments.status IS 'Lifecycle: draft -> active -> paused -> completed';
COMMENT ON COLUMN rag_experiment_metrics.retrieval_hit_rate IS 'Percentage of retrieved chunks actually used in generation';
