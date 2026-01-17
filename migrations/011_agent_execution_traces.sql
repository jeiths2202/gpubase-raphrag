-- ============================================================================
-- Agent Execution Trace System - Database Schema
-- Migration: 011_agent_execution_traces.sql
--
-- Purpose: Store agent execution traces for real-time visualization
-- Supports: Single agent + Enterprise multi-agent orchestration
-- ============================================================================

-- ============================================================================
-- agent_execution_traces: Main trace for agent execution
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_execution_traces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id UUID NOT NULL UNIQUE,  -- Global trace identifier

    -- Request identification
    user_id VARCHAR(100) NOT NULL,
    session_id VARCHAR(100),
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,

    -- Agent information
    agent_type VARCHAR(50) NOT NULL,  -- rag, ims, vision, code, planner
    is_enterprise BOOLEAN DEFAULT FALSE,  -- Multi-agent orchestration

    -- Task information
    task_description TEXT NOT NULL,

    -- DAG structure (for enterprise orchestration)
    dag_structure JSONB DEFAULT NULL,
    /*
    Structure:
    {
        "tasks": [
            {"task_id": "t1", "description": "...", "agent_type": "rag", "dependencies": []},
            {"task_id": "t2", "description": "...", "agent_type": "ims", "dependencies": ["t1"]}
        ],
        "execution_batches": [["t1"], ["t2"]],
        "parallelism_type": "partial"  -- none, full, partial, pipeline
    }
    */

    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    total_latency_ms INTEGER,

    -- Status
    status VARCHAR(20) DEFAULT 'RUNNING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED')),
    error_message TEXT,

    -- Result summary
    total_steps INTEGER DEFAULT 0,
    successful_steps INTEGER DEFAULT 0,
    failed_steps INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,

    -- Final answer (truncated for storage)
    final_answer TEXT,

    -- Extensible metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agent_execution_traces IS 'Agent execution traces for real-time visualization and history';
COMMENT ON COLUMN agent_execution_traces.dag_structure IS 'Task decomposition DAG for enterprise multi-agent orchestration';

-- Indexes
CREATE INDEX idx_agent_traces_user_id ON agent_execution_traces(user_id);
CREATE INDEX idx_agent_traces_created_at ON agent_execution_traces(created_at DESC);
CREATE INDEX idx_agent_traces_conversation ON agent_execution_traces(conversation_id)
    WHERE conversation_id IS NOT NULL;
CREATE INDEX idx_agent_traces_status ON agent_execution_traces(status)
    WHERE status IN ('RUNNING', 'FAILED');
CREATE INDEX idx_agent_traces_agent_type ON agent_execution_traces(agent_type, created_at DESC);


-- ============================================================================
-- agent_trace_spans: Individual task/step spans within a trace
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_trace_spans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    span_id UUID NOT NULL UNIQUE,
    trace_id UUID NOT NULL REFERENCES agent_execution_traces(trace_id) ON DELETE CASCADE,
    parent_span_id UUID REFERENCES agent_trace_spans(span_id) ON DELETE SET NULL,

    -- Span identification
    task_id VARCHAR(100),  -- For DAG tasks
    span_name VARCHAR(200) NOT NULL,
    span_type VARCHAR(50) NOT NULL
        CHECK (span_type IN (
            'ROOT',          -- Root span for entire execution
            'TASK',          -- Sub-task in DAG
            'TOOL_CALL',     -- Tool execution
            'EVALUATION',    -- Result evaluation
            'RETRY',         -- Retry attempt
            'SYNTHESIS',     -- Result synthesis (multi-agent)
            'PLANNING',      -- Task planning/decomposition
            'THINKING'       -- Agent reasoning
        )),

    -- Agent context
    agent_type VARCHAR(50),  -- rag, ims, vision, code, planner

    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    latency_ms INTEGER,

    -- Status
    status VARCHAR(20) DEFAULT 'RUNNING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SKIPPED')),
    error_message TEXT,

    -- Execution order
    depth INTEGER DEFAULT 0,
    execution_order INTEGER DEFAULT 0,

    -- Span-specific metadata
    metadata JSONB DEFAULT '{}',
    /*
    Examples:
    - TASK: {"description": "...", "dependencies": ["t1"]}
    - TOOL_CALL: {"tool_name": "vector_search", "input": {...}, "output": {...}}
    - EVALUATION: {"score": 0.85, "passed": true, "issues": []}
    - RETRY: {"attempt": 2, "reason": "Low quality score"}
    */

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agent_trace_spans IS 'Individual spans for task execution, tool calls, evaluations';

-- Indexes
CREATE INDEX idx_agent_spans_trace_id ON agent_trace_spans(trace_id, start_time);
CREATE INDEX idx_agent_spans_parent ON agent_trace_spans(parent_span_id)
    WHERE parent_span_id IS NOT NULL;
CREATE INDEX idx_agent_spans_task_id ON agent_trace_spans(task_id)
    WHERE task_id IS NOT NULL;
CREATE INDEX idx_agent_spans_type ON agent_trace_spans(span_type);
CREATE INDEX idx_agent_spans_status ON agent_trace_spans(status)
    WHERE status IN ('RUNNING', 'FAILED');


-- ============================================================================
-- agent_tool_calls: Tool execution details
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_call_id UUID NOT NULL UNIQUE,
    span_id UUID NOT NULL REFERENCES agent_trace_spans(span_id) ON DELETE CASCADE,
    trace_id UUID NOT NULL REFERENCES agent_execution_traces(trace_id) ON DELETE CASCADE,

    -- Tool information
    tool_name VARCHAR(100) NOT NULL,  -- vector_search, graph_query, ims_search, etc.

    -- Input/Output (truncated for storage)
    input_args JSONB DEFAULT '{}',
    output_result JSONB DEFAULT NULL,

    -- Status
    status VARCHAR(20) DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'EXECUTING', 'COMPLETED', 'FAILED')),
    error_message TEXT,

    -- Timing
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    latency_ms INTEGER,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agent_tool_calls IS 'Detailed tool execution records for debugging';

-- Indexes
CREATE INDEX idx_tool_calls_span_id ON agent_tool_calls(span_id);
CREATE INDEX idx_tool_calls_trace_id ON agent_tool_calls(trace_id, created_at);
CREATE INDEX idx_tool_calls_tool_name ON agent_tool_calls(tool_name, created_at DESC);


-- ============================================================================
-- agent_evaluations: Result evaluation details
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_id UUID NOT NULL UNIQUE,
    span_id UUID NOT NULL REFERENCES agent_trace_spans(span_id) ON DELETE CASCADE,
    trace_id UUID NOT NULL REFERENCES agent_execution_traces(trace_id) ON DELETE CASCADE,
    task_id VARCHAR(100),  -- Reference to DAG task

    -- Evaluation result
    passed BOOLEAN NOT NULL,
    score FLOAT CHECK (score >= 0.0 AND score <= 1.0),

    -- Criteria
    criteria JSONB DEFAULT '{}',
    /*
    {
        "min_confidence": 0.6,
        "require_sources": true,
        "min_answer_length": 50,
        "max_execution_time": 120
    }
    */

    -- Issues found
    issues JSONB DEFAULT '[]',  -- ["Answer too short", "Low confidence"]

    -- Retry recommendation
    retry_recommended BOOLEAN DEFAULT FALSE,
    retry_reason TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agent_evaluations IS 'Result quality evaluations for retry logic';

-- Indexes
CREATE INDEX idx_evaluations_span_id ON agent_evaluations(span_id);
CREATE INDEX idx_evaluations_trace_id ON agent_evaluations(trace_id);
CREATE INDEX idx_evaluations_task_id ON agent_evaluations(task_id)
    WHERE task_id IS NOT NULL;
CREATE INDEX idx_evaluations_failed ON agent_evaluations(trace_id, created_at)
    WHERE passed = FALSE;


-- ============================================================================
-- Triggers for updated_at
-- ============================================================================
DROP TRIGGER IF EXISTS update_agent_traces_updated_at ON agent_execution_traces;
CREATE TRIGGER update_agent_traces_updated_at
    BEFORE UPDATE ON agent_execution_traces
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
