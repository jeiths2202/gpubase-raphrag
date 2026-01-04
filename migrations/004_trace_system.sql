-- ============================================================================
-- E2E Message Tracing System - Database Schema
-- Migration: 004_trace_system.sql
-- ============================================================================

-- ============================================================================
-- traces: Main trace metadata for E2E request tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL UNIQUE,  -- Global trace identifier (UUID v4)

    -- Request identification
    user_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100),
    conversation_id UUID REFERENCES conversations(id),

    -- Request content
    original_prompt TEXT NOT NULL,
    normalized_prompt TEXT,  -- After preprocessing

    -- Model configuration
    model_name VARCHAR(100) NOT NULL,  -- "nemotron-9b", "mistral-nemo-12b"
    model_version VARCHAR(50),
    inference_params JSONB DEFAULT '{}',  -- temperature, max_tokens, etc.

    -- Timing (all in milliseconds)
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    total_latency_ms INTEGER,

    -- Per-stage latency (computed from spans)
    embedding_latency_ms INTEGER,
    retrieval_latency_ms INTEGER,
    generation_latency_ms INTEGER,

    -- Response data
    response_content TEXT,
    response_length INTEGER,  -- Character count
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,

    -- Quality & error tracking
    response_quality_flag VARCHAR(50) DEFAULT 'NORMAL'
        CHECK (response_quality_flag IN ('NORMAL', 'USER_NEGATIVE', 'EMPTY', 'LOW_CONFIDENCE', 'ERROR')),
    error_code VARCHAR(100),
    error_message TEXT,
    error_stacktrace TEXT,  -- Only in DEVELOP mode

    -- RAG metadata
    strategy VARCHAR(50) DEFAULT 'auto',  -- auto, vector, graph, hybrid, code
    language VARCHAR(10) DEFAULT 'auto',  -- auto, ko, ja, en
    rag_confidence_score FLOAT,
    rag_result_count INTEGER,

    -- Extensible metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE traces IS 'E2E trace metadata for request lifecycle tracking';
COMMENT ON COLUMN traces.trace_id IS 'Global unique trace ID propagated across all spans';
COMMENT ON COLUMN traces.response_quality_flag IS 'Auto-detected quality issues: USER_NEGATIVE (thumbs down), EMPTY (< 50 chars), LOW_CONFIDENCE (RAG < 0.5), ERROR (exception)';


-- Indexes for admin queries
CREATE INDEX idx_traces_user_id ON traces(user_id);
CREATE INDEX idx_traces_created_at ON traces(created_at DESC);
CREATE INDEX idx_traces_trace_id ON traces(trace_id);
CREATE INDEX idx_traces_latency ON traces(total_latency_ms DESC)
    WHERE total_latency_ms IS NOT NULL;
CREATE INDEX idx_traces_quality_flag ON traces(response_quality_flag)
    WHERE response_quality_flag != 'NORMAL';
CREATE INDEX idx_traces_error_code ON traces(error_code)
    WHERE error_code IS NOT NULL;
CREATE INDEX idx_traces_user_date ON traces(user_id, created_at DESC);
CREATE INDEX idx_traces_model_error ON traces(model_name, error_code)
    WHERE error_code IS NOT NULL;

-- Partial index for slow requests (P95 latency > 5000ms)
CREATE INDEX idx_traces_slow ON traces(total_latency_ms DESC, created_at DESC)
    WHERE total_latency_ms > 5000;


-- ============================================================================
-- trace_spans: Individual operation spans within a trace
-- ============================================================================
CREATE TABLE IF NOT EXISTS trace_spans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    span_id UUID NOT NULL UNIQUE,  -- Unique span identifier
    trace_id UUID NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
    parent_span_id UUID REFERENCES trace_spans(span_id),  -- NULL for root span

    -- Span identification
    span_name VARCHAR(100) NOT NULL,  -- "request", "embedding", "retrieval", "generation", "token_chunk"
    span_type VARCHAR(50) NOT NULL
        CHECK (span_type IN ('ROOT', 'EMBEDDING', 'RETRIEVAL', 'GENERATION', 'STREAMING', 'CLASSIFICATION')),

    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    latency_ms INTEGER,

    -- Status
    status VARCHAR(20) DEFAULT 'OK'
        CHECK (status IN ('OK', 'ERROR', 'TIMEOUT', 'CANCELLED')),
    error_message TEXT,

    -- Span-specific metadata
    metadata JSONB DEFAULT '{}',
    /*
    Examples of metadata by span_type:
    - EMBEDDING: {"model": "nv-embedqa", "dimension": 4096, "input_length": 512}
    - RETRIEVAL: {"strategy": "hybrid", "top_k": 5, "result_count": 5, "avg_score": 0.85}
    - GENERATION: {"model": "nemotron-9b", "temperature": 0.1, "max_tokens": 2048, "input_tokens": 1500, "output_tokens": 300}
    - STREAMING: {"chunk_index": 42, "token_content": "hello", "is_sampled": true}
    */

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE trace_spans IS 'Individual operation spans with parent-child relationships for detailed tracing';
COMMENT ON COLUMN trace_spans.parent_span_id IS 'NULL for root span, otherwise references parent span';

-- Indexes for span queries
CREATE INDEX idx_spans_trace_id ON trace_spans(trace_id, created_at);
CREATE INDEX idx_spans_parent ON trace_spans(parent_span_id)
    WHERE parent_span_id IS NOT NULL;
CREATE INDEX idx_spans_type ON trace_spans(span_type, latency_ms DESC);
CREATE INDEX idx_spans_latency ON trace_spans(latency_ms DESC)
    WHERE latency_ms IS NOT NULL;


-- ============================================================================
-- trace_metrics: Aggregated metrics for retention policy
-- ============================================================================
CREATE TABLE IF NOT EXISTS trace_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_date DATE NOT NULL,
    metric_type VARCHAR(50) NOT NULL
        CHECK (metric_type IN ('DAILY', 'WEEKLY', 'MONTHLY')),

    -- Aggregation scope
    user_id VARCHAR(100),
    model_name VARCHAR(100),
    strategy VARCHAR(50),

    -- Request counts
    total_requests INTEGER DEFAULT 0,
    successful_requests INTEGER DEFAULT 0,
    failed_requests INTEGER DEFAULT 0,
    error_requests INTEGER DEFAULT 0,

    -- Quality breakdown
    normal_quality INTEGER DEFAULT 0,
    user_negative INTEGER DEFAULT 0,
    empty_response INTEGER DEFAULT 0,
    low_confidence INTEGER DEFAULT 0,

    -- Latency statistics (milliseconds)
    avg_total_latency_ms INTEGER,
    p50_total_latency_ms INTEGER,
    p95_total_latency_ms INTEGER,
    p99_total_latency_ms INTEGER,
    max_total_latency_ms INTEGER,

    -- Per-stage latency averages
    avg_embedding_latency_ms INTEGER,
    avg_retrieval_latency_ms INTEGER,
    avg_generation_latency_ms INTEGER,

    -- Token statistics
    total_input_tokens BIGINT DEFAULT 0,
    total_output_tokens BIGINT DEFAULT 0,
    avg_tokens_per_request INTEGER,

    -- RAG statistics
    avg_rag_confidence FLOAT,
    avg_rag_results INTEGER,

    -- Extensible metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint for upsert
    UNIQUE (metric_date, metric_type, user_id, model_name, strategy)
);

COMMENT ON TABLE trace_metrics IS 'Aggregated metrics for retention policy and analytics';

CREATE INDEX idx_metrics_date ON trace_metrics(metric_date DESC);
CREATE INDEX idx_metrics_user ON trace_metrics(user_id, metric_date DESC)
    WHERE user_id IS NOT NULL;
CREATE INDEX idx_metrics_model ON trace_metrics(model_name, metric_date DESC)
    WHERE model_name IS NOT NULL;


-- ============================================================================
-- Automatic updated_at trigger
-- ============================================================================

-- Trigger function for updated_at (create only if not exists)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for traces table
DROP TRIGGER IF EXISTS update_traces_updated_at ON traces;
CREATE TRIGGER update_traces_updated_at
    BEFORE UPDATE ON traces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create triggers for trace_metrics table
DROP TRIGGER IF EXISTS update_trace_metrics_updated_at ON trace_metrics;
CREATE TRIGGER update_trace_metrics_updated_at
    BEFORE UPDATE ON trace_metrics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
