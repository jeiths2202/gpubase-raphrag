"""
Agent System Types and Models
Defines core types, enums, and Pydantic models for the agent system.
"""
from enum import Enum
from typing import Dict, List, Any, Optional, TypedDict, Literal, Union, TYPE_CHECKING
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

if TYPE_CHECKING:
    from .intent import IntentResult


class AgentType(str, Enum):
    """Types of specialized agents"""
    RAG = "rag"
    IMS = "ims"
    VISION = "vision"
    CODE = "code"
    PLANNER = "planner"


class MessageRole(str, Enum):
    """Message roles in agent conversation"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolStatus(str, Enum):
    """Tool execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class PermissionAction(str, Enum):
    """Permission actions"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# TypedDicts for internal use
class ToolResult(TypedDict):
    """Result of a tool execution"""
    success: bool
    output: str
    error: Optional[str]
    metadata: Optional[Dict[str, Any]]


class ToolCallDict(TypedDict):
    """Tool call request"""
    tool_name: str
    arguments: Dict[str, Any]
    call_id: str


# Pydantic Models for API
class ToolCall(BaseModel):
    """Tool call request model"""
    tool_name: str = Field(..., description="Name of the tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique call ID")


class AgentMessage(BaseModel):
    """Message in agent conversation"""
    role: MessageRole
    content: str
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None  # Tool name for tool messages
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolExecutionEvent(BaseModel):
    """Event emitted during tool execution (for streaming)"""
    event_type: Literal["tool_start", "tool_progress", "tool_end", "tool_error"]
    call_id: str
    tool_name: str
    status: ToolStatus
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ThinkingEvent(BaseModel):
    """Event emitted during agent thinking (for streaming)"""
    event_type: Literal["thinking_start", "thinking_delta", "thinking_end"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentEvent(BaseModel):
    """Union event for agent streaming"""
    event_type: str
    data: Union[ToolExecutionEvent, ThinkingEvent, Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Dataclasses for internal context
@dataclass
class AgentContext:
    """Context for agent execution"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    language: str = "auto"
    max_steps: int = 10
    timeout: float = 300.0  # 5 minutes
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Session-specific data
    uploaded_documents: List[str] = field(default_factory=list)
    external_resources: Dict[str, Any] = field(default_factory=dict)

    # File context for RAG priority (attached files content)
    file_context: Optional[str] = None

    # URL context for RAG priority (fetched web content)
    url_context: Optional[str] = None
    url_source: Optional[str] = None  # Source URL for attribution

    # Intent classification result (set by orchestrator)
    intent: Optional["IntentResult"] = None


@dataclass
class AgentResult:
    """Result of agent execution"""
    answer: str
    agent_type: AgentType
    steps: int
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ToolDefinition:
    """Tool definition for LLM function calling"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    required: List[str] = field(default_factory=list)


# API Request/Response Models
class AgentRequest(BaseModel):
    """API request for agent execution"""
    task: str = Field(..., description="Task or question for the agent")
    agent_type: Optional[AgentType] = Field(None, description="Specific agent type (auto-selected if not provided)")
    session_id: Optional[str] = Field(None, description="Session ID for context continuity")
    language: str = Field("auto", description="Response language (auto, en, ko, ja)")
    max_steps: int = Field(10, ge=1, le=50, description="Maximum reasoning steps")
    include_sources: bool = Field(True, description="Include sources in response")
    stream: bool = Field(False, description="Enable streaming response")
    file_context: Optional[str] = Field(None, description="Attached file content for RAG priority context")
    url_context: Optional[str] = Field(None, description="URL to fetch and use as RAG context")


class AgentResponse(BaseModel):
    """API response from agent execution"""
    answer: str
    agent_type: AgentType
    session_id: str
    steps: int
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time: float
    success: bool = True
    error: Optional[str] = None


class ArtifactType(str, Enum):
    """Types of artifacts that can be extracted from agent responses"""
    CODE = "code"
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    DIFF = "diff"
    LOG = "log"


class AgentStreamChunk(BaseModel):
    """Streaming chunk from agent execution"""
    chunk_type: Literal["thinking", "tool_call", "tool_result", "text", "sources", "done", "error", "status", "artifact"]
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None
    sources: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None

    # Artifact-specific fields
    artifact_id: Optional[str] = None
    artifact_type: Optional[str] = None  # code, text, markdown, html, json, diff, log
    artifact_title: Optional[str] = None
    artifact_language: Optional[str] = None  # python, javascript, typescript, etc.


# Permission Models
@dataclass
class PermissionRule:
    """Permission rule for tool access"""
    tool: str  # Tool name or "*" for all
    pattern: str  # Resource pattern (e.g., "*.py", "/api/*")
    action: PermissionAction
    description: Optional[str] = None


@dataclass
class AgentPermissions:
    """Permissions for an agent"""
    agent_type: AgentType
    rules: List[PermissionRule] = field(default_factory=list)
    default_action: PermissionAction = PermissionAction.DENY


# ============================================================================
# Enterprise Orchestration Types
# ============================================================================

class TaskStatus(str, Enum):
    """Status of a task in the execution DAG"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class ParallelismType(str, Enum):
    """Type of parallelism detected in a task"""
    NONE = "none"           # Sequential execution
    FULL = "full"           # All subtasks can run in parallel
    PARTIAL = "partial"     # Some subtasks can run in parallel
    PIPELINE = "pipeline"   # Pipeline parallelism (batches)


@dataclass
class SubTask:
    """Single task in the execution DAG"""
    task_id: str
    description: str
    agent_type: AgentType
    dependencies: List[str] = field(default_factory=list)  # task_ids that must complete first
    status: TaskStatus = TaskStatus.PENDING
    result: Optional["AgentResult"] = None
    retry_count: int = 0
    timeout_override: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class TaskDAG:
    """Directed Acyclic Graph of tasks for multi-agent orchestration"""
    tasks: Dict[str, SubTask] = field(default_factory=dict)
    root_task: Optional[str] = None  # Original task description
    execution_batches: List[List[str]] = field(default_factory=list)  # Pre-computed parallel batches
    parallelism_type: ParallelismType = ParallelismType.NONE
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_ready_tasks(self) -> List[SubTask]:
        """Get tasks ready to execute (dependencies satisfied, not started)"""
        ready = []
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            # Check all dependencies are completed
            deps_satisfied = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            if deps_satisfied:
                ready.append(task)
        return ready

    def mark_running(self, task_id: str) -> None:
        """Mark a task as running"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.RUNNING
            self.tasks[task_id].start_time = datetime.now(timezone.utc)

    def mark_completed(self, task_id: str, result: "AgentResult") -> None:
        """Mark a task as completed with result"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.COMPLETED
            self.tasks[task_id].result = result
            self.tasks[task_id].end_time = datetime.now(timezone.utc)

    def mark_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed"""
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.FAILED
            self.tasks[task_id].error = error
            self.tasks[task_id].end_time = datetime.now(timezone.utc)

    def is_complete(self) -> bool:
        """Check if all tasks are completed or failed"""
        return all(
            task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED)
            for task in self.tasks.values()
        )

    def has_pending_tasks(self) -> bool:
        """Check if there are pending tasks"""
        return any(task.status == TaskStatus.PENDING for task in self.tasks.values())


class EvaluationCriteria(BaseModel):
    """Criteria for evaluating agent results"""
    min_confidence: float = Field(0.6, ge=0.0, le=1.0, description="Minimum confidence threshold")
    require_sources: bool = Field(False, description="Require sources in result")
    min_answer_length: int = Field(10, ge=0, description="Minimum answer length")
    max_execution_time: Optional[float] = Field(None, description="Maximum execution time in seconds")
    custom_checks: List[str] = Field(default_factory=list, description="Custom validation rules")


class RetryConfig(BaseModel):
    """Configuration for retry logic"""
    max_retries: int = Field(2, ge=0, le=5, description="Maximum retry attempts")
    backoff_factor: float = Field(2.0, ge=1.0, description="Exponential backoff factor")
    initial_delay: float = Field(1.0, ge=0.0, description="Initial delay in seconds")
    retry_on_failure: bool = Field(True, description="Retry on task failure")
    retry_on_low_quality: bool = Field(True, description="Retry on low quality results")


class OrchestrationConfig(BaseModel):
    """Configuration for enterprise orchestration"""
    enable_parallel: bool = Field(True, description="Enable parallel agent execution")
    enable_retry: bool = Field(True, description="Enable result evaluation and retry")
    enable_evaluation: bool = Field(True, description="Enable result quality evaluation")
    continue_on_failure: bool = Field(True, description="Continue execution on partial failures")
    enable_synthesis: bool = Field(True, description="Enable multi-result synthesis")
    enable_next_actions: bool = Field(True, description="Enable next-action recommendations")
    evaluation_criteria: EvaluationCriteria = Field(default_factory=EvaluationCriteria)
    retry_config: RetryConfig = Field(default_factory=RetryConfig)
    timeout_overrides: Optional[Dict[str, float]] = Field(None, description="Per-agent timeout overrides")


@dataclass
class EvaluationResult:
    """Result of evaluating an agent result"""
    passed: bool
    score: float  # 0.0 to 1.0
    issues: List[str] = field(default_factory=list)
    retry_recommended: bool = False
    retry_reason: Optional[str] = None


@dataclass
class TraceEvent:
    """Single event in execution trace"""
    timestamp: datetime
    event_type: str  # task_start, task_complete, task_failed, task_retry, synthesis, etc.
    task_id: Optional[str] = None
    agent_type: Optional[AgentType] = None
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTrace:
    """Complete execution trace for explainability"""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    events: List[TraceEvent] = field(default_factory=list)
    dag: Optional[TaskDAG] = None
    evaluations: Dict[str, EvaluationResult] = field(default_factory=dict)
    synthesis_metadata: Dict[str, Any] = field(default_factory=dict)
    next_actions: List[str] = field(default_factory=list)
    total_time: float = 0.0

    def record(self, event_type: str, task_id: Optional[str] = None,
               agent_type: Optional[AgentType] = None, **data) -> None:
        """Record an event to the trace"""
        self.events.append(TraceEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            task_id=task_id,
            agent_type=agent_type,
            data=data
        ))


class EnterpriseAgentRequest(BaseModel):
    """Extended request for enterprise orchestration"""
    task: str = Field(..., description="Task or question for the agent")
    agent_type: Optional[AgentType] = Field(None, description="Specific agent type (auto-selected if not provided)")
    session_id: Optional[str] = Field(None, description="Session ID for context continuity")
    language: str = Field("auto", description="Response language (auto, en, ko, ja)")
    max_steps: int = Field(10, ge=1, le=50, description="Maximum reasoning steps per agent")
    include_sources: bool = Field(True, description="Include sources in response")
    stream: bool = Field(False, description="Enable streaming response")
    file_context: Optional[str] = Field(None, description="Attached file content")
    url_context: Optional[str] = Field(None, description="URL to fetch and use as context")

    # Enterprise orchestration options
    enable_multi_agent: bool = Field(False, description="Enable multi-agent orchestration")
    orchestration_config: OrchestrationConfig = Field(default_factory=OrchestrationConfig)


class EnterpriseAgentResponse(BaseModel):
    """Extended response from enterprise orchestration"""
    answer: str
    agent_type: AgentType
    session_id: str
    steps: int
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    execution_time: float
    success: bool = True
    error: Optional[str] = None

    # Enterprise orchestration results
    trace: Optional[Dict[str, Any]] = Field(None, description="Execution trace for explainability")
    subtask_results: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="Individual subtask results")
    next_actions: List[str] = Field(default_factory=list, description="Recommended next actions")
    partial_failures: List[str] = Field(default_factory=list, description="Failed subtask IDs")


class ParallelStreamChunk(BaseModel):
    """Streaming chunk for parallel agent execution"""
    chunk_type: Literal[
        "orchestration_start",  # Orchestration started
        "dag_created",          # DAG created, shows task breakdown
        "batch_start",          # Starting a batch of parallel tasks
        "agent_start",          # Single agent started
        "agent_chunk",          # Chunk from running agent
        "agent_done",           # Single agent completed
        "batch_done",           # Batch completed
        "evaluation",           # Result evaluation
        "retry",                # Retrying a task
        "synthesis",            # Synthesizing results
        "next_actions",         # Next action recommendations
        "done",                 # Orchestration complete
        "error"                 # Error occurred
    ]
    content: Optional[str] = None
    task_id: Optional[str] = None
    agent_type: Optional[AgentType] = None
    agent_chunk: Optional[AgentStreamChunk] = None
    metadata: Optional[Dict[str, Any]] = None
