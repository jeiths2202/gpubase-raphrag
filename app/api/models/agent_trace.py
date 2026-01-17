"""
Agent Execution Trace Models

Pydantic models for agent execution traces, spans, tool calls, and evaluations.
Used for API request/response and database serialization.
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================

class AgentTraceStatus(str, Enum):
    """Status of an agent execution trace"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SpanType(str, Enum):
    """Type of execution span"""
    ROOT = "ROOT"
    TASK = "TASK"
    TOOL_CALL = "TOOL_CALL"
    EVALUATION = "EVALUATION"
    RETRY = "RETRY"
    SYNTHESIS = "SYNTHESIS"
    PLANNING = "PLANNING"
    THINKING = "THINKING"


class SpanStatus(str, Enum):
    """Status of a span"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class ToolCallStatus(str, Enum):
    """Status of a tool call"""
    PENDING = "PENDING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ============================================================================
# DAG Models (for visualization)
# ============================================================================

class DAGTask(BaseModel):
    """Single task in the execution DAG"""
    task_id: str
    description: str
    agent_type: str
    status: SpanStatus = SpanStatus.PENDING
    dependencies: List[str] = Field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None


class DAGStructure(BaseModel):
    """Complete DAG structure for enterprise orchestration"""
    tasks: List[DAGTask] = Field(default_factory=list)
    execution_batches: List[List[str]] = Field(default_factory=list)
    parallelism_type: str = "none"  # none, full, partial, pipeline


# ============================================================================
# Span Models
# ============================================================================

class AgentTraceSpan(BaseModel):
    """Individual execution span"""
    span_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    parent_span_id: Optional[UUID] = None
    task_id: Optional[str] = None

    span_name: str
    span_type: SpanType
    agent_type: Optional[str] = None

    start_time: datetime
    end_time: Optional[datetime] = None
    latency_ms: Optional[int] = None

    status: SpanStatus = SpanStatus.RUNNING
    error_message: Optional[str] = None

    depth: int = 0
    execution_order: int = 0

    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        from_attributes = True


# ============================================================================
# Tool Call Models
# ============================================================================

class AgentToolCall(BaseModel):
    """Tool execution record"""
    tool_call_id: UUID = Field(default_factory=uuid4)
    span_id: UUID
    trace_id: UUID

    tool_name: str
    input_args: Dict[str, Any] = Field(default_factory=dict)
    output_result: Optional[Dict[str, Any]] = None

    status: ToolCallStatus = ToolCallStatus.PENDING
    error_message: Optional[str] = None

    start_time: datetime
    end_time: Optional[datetime] = None
    latency_ms: Optional[int] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        from_attributes = True


# ============================================================================
# Evaluation Models
# ============================================================================

class EvaluationCriteriaModel(BaseModel):
    """Evaluation criteria configuration"""
    min_confidence: float = 0.6
    require_sources: bool = False
    min_answer_length: int = 50
    max_execution_time: Optional[float] = None


class AgentEvaluation(BaseModel):
    """Result quality evaluation"""
    eval_id: UUID = Field(default_factory=uuid4)
    span_id: UUID
    trace_id: UUID
    task_id: Optional[str] = None

    passed: bool
    score: Optional[float] = Field(None, ge=0.0, le=1.0)

    criteria: EvaluationCriteriaModel = Field(default_factory=EvaluationCriteriaModel)
    issues: List[str] = Field(default_factory=list)

    retry_recommended: bool = False
    retry_reason: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        from_attributes = True


# ============================================================================
# Main Trace Models
# ============================================================================

class AgentExecutionTrace(BaseModel):
    """Complete agent execution trace"""
    trace_id: UUID = Field(default_factory=uuid4)
    user_id: str
    session_id: Optional[str] = None
    conversation_id: Optional[UUID] = None

    agent_type: str
    is_enterprise: bool = False
    task_description: str

    dag_structure: Optional[DAGStructure] = None

    start_time: datetime
    end_time: Optional[datetime] = None
    total_latency_ms: Optional[int] = None

    status: AgentTraceStatus = AgentTraceStatus.RUNNING
    error_message: Optional[str] = None

    total_steps: int = 0
    successful_steps: int = 0
    failed_steps: int = 0
    retry_count: int = 0

    final_answer: Optional[str] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now())
    updated_at: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        from_attributes = True


# ============================================================================
# Response Models (with nested data)
# ============================================================================

class AgentTraceDetail(BaseModel):
    """Full trace with all spans, tool calls, and evaluations"""
    trace_id: UUID
    user_id: str
    session_id: Optional[str] = None
    conversation_id: Optional[UUID] = None

    agent_type: str
    is_enterprise: bool
    task_description: str

    dag_structure: Optional[DAGStructure] = None

    start_time: datetime
    end_time: Optional[datetime] = None
    total_latency_ms: Optional[int] = None

    status: AgentTraceStatus
    error_message: Optional[str] = None

    total_steps: int
    successful_steps: int
    failed_steps: int
    retry_count: int

    final_answer: Optional[str] = None

    # Nested data
    spans: List[AgentTraceSpan] = Field(default_factory=list)
    tool_calls: List[AgentToolCall] = Field(default_factory=list)
    evaluations: List[AgentEvaluation] = Field(default_factory=list)

    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentTraceListItem(BaseModel):
    """Summary item for trace list"""
    trace_id: UUID
    agent_type: str
    is_enterprise: bool
    task_description: str
    status: AgentTraceStatus
    total_latency_ms: Optional[int] = None
    total_steps: int
    failed_steps: int
    created_at: datetime


# ============================================================================
# Streaming Event Models
# ============================================================================

class TraceEventType(str, Enum):
    """Types of real-time trace events"""
    TRACE_STARTED = "trace_started"
    DAG_CREATED = "dag_created"
    SPAN_STARTED = "span_started"
    SPAN_COMPLETED = "span_completed"
    SPAN_FAILED = "span_failed"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    EVALUATION_COMPLETED = "evaluation_completed"
    TASK_STATUS_UPDATED = "task_status_updated"
    TRACE_COMPLETED = "trace_completed"
    TRACE_FAILED = "trace_failed"


class TraceStreamEvent(BaseModel):
    """Event for SSE streaming"""
    event_type: TraceEventType
    trace_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    data: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Request Models
# ============================================================================

class TraceCreateRequest(BaseModel):
    """Request to create a new trace"""
    agent_type: str
    is_enterprise: bool = False
    task_description: str
    session_id: Optional[str] = None
    conversation_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SpanCreateRequest(BaseModel):
    """Request to create a new span"""
    span_name: str
    span_type: SpanType
    parent_span_id: Optional[UUID] = None
    task_id: Optional[str] = None
    agent_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TraceQueryParams(BaseModel):
    """Query parameters for listing traces"""
    agent_type: Optional[str] = None
    conversation_id: Optional[UUID] = None
    status: Optional[AgentTraceStatus] = None
    is_enterprise: Optional[bool] = None
    skip: int = 0
    limit: int = 50
