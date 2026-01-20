-- RAG Evaluation System
-- RAGAS 스타일 RAG 품질 평가 저장
-- Created: 2025-01-20

-- RAG Evaluations Table
CREATE TABLE IF NOT EXISTS rag_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID UNIQUE NOT NULL,
    trace_id UUID REFERENCES agent_execution_traces(trace_id) ON DELETE SET NULL,
    conversation_id UUID,
    user_id VARCHAR(100) NOT NULL,

    -- Input data
    query TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources_count INTEGER NOT NULL DEFAULT 0,
    sources_json JSONB,  -- Stored for reproducibility

    -- Individual metric scores (0.0-1.0)
    faithfulness_score FLOAT,
    context_relevance_score FLOAT,
    answer_relevancy_score FLOAT,
    context_precision_score FLOAT,
    context_recall_score FLOAT,

    -- Overall assessment
    overall_score FLOAT NOT NULL,
    overall_level VARCHAR(20) NOT NULL CHECK (overall_level IN ('excellent', 'good', 'fair', 'poor')),

    -- Detailed results (JSONB for flexibility)
    metric_details JSONB,  -- Full MetricResult for each metric
    issues JSONB,          -- Array of issue strings
    recommendations JSONB, -- Array of recommendation strings

    -- Metadata
    evaluation_time_ms INTEGER,
    ground_truth_provided BOOLEAN DEFAULT FALSE,
    language VARCHAR(10) DEFAULT 'ko',
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_rag_eval_user_id ON rag_evaluations(user_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rag_eval_level ON rag_evaluations(overall_level);
CREATE INDEX IF NOT EXISTS idx_rag_eval_score ON rag_evaluations(overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_rag_eval_trace ON rag_evaluations(trace_id) WHERE trace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rag_eval_conversation ON rag_evaluations(conversation_id) WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rag_eval_date ON rag_evaluations(evaluated_at DESC);

-- Index for metric-specific queries
CREATE INDEX IF NOT EXISTS idx_rag_eval_faithfulness ON rag_evaluations(faithfulness_score DESC) WHERE faithfulness_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rag_eval_context_rel ON rag_evaluations(context_relevance_score DESC) WHERE context_relevance_score IS NOT NULL;

-- GIN index for JSONB searches
CREATE INDEX IF NOT EXISTS idx_rag_eval_issues_gin ON rag_evaluations USING GIN (issues);

-- Comment on table
COMMENT ON TABLE rag_evaluations IS 'RAG 응답 품질 평가 결과 (RAGAS 스타일)';
COMMENT ON COLUMN rag_evaluations.evaluation_id IS '평가 고유 식별자';
COMMENT ON COLUMN rag_evaluations.faithfulness_score IS '충실도: 응답이 컨텍스트에 기반하는지 (환각 탐지)';
COMMENT ON COLUMN rag_evaluations.context_relevance_score IS '컨텍스트 관련성: 검색된 문맥의 질문 관련성';
COMMENT ON COLUMN rag_evaluations.answer_relevancy_score IS '응답 적합성: 응답이 질문에 적합한지';
COMMENT ON COLUMN rag_evaluations.context_precision_score IS '컨텍스트 정밀도: 관련 컨텍스트의 순위 품질';
COMMENT ON COLUMN rag_evaluations.context_recall_score IS '컨텍스트 재현율: 필요 정보 포함도 (ground truth 필요)';
COMMENT ON COLUMN rag_evaluations.overall_level IS '종합 등급: excellent(>=0.8), good(>=0.6), fair(>=0.4), poor(<0.4)';
