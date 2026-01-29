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
    # OpenCode Agent - Document-grounded with hallucination detection
    OPENCODE = "opencode"
    # Enhancement agents
    ENHANCEMENT_ANALYST = "enhancement_analyst"
    ENHANCEMENT_ARCHITECT = "enhancement_architect"
    ENHANCEMENT_CODER = "enhancement_coder"
    ENHANCEMENT_QA = "enhancement_qa"


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolExecutionEvent(BaseModel):
    """Event emitted during tool execution (for streaming)"""
    event_type: Literal["tool_start", "tool_progress", "tool_end", "tool_error"]
    call_id: str
    tool_name: str
    status: ToolStatus
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ThinkingEvent(BaseModel):
    """Event emitted during agent thinking (for streaming)"""
    event_type: Literal["thinking_start", "thinking_delta", "thinking_end"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentEvent(BaseModel):
    """Union event for agent streaming"""
    event_type: str
    data: Union[ToolExecutionEvent, ThinkingEvent, Dict[str, Any]]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Search scope for Agent-Driven RAG
@dataclass
class SearchScope:
    """Search scope for scoped RAG queries"""
    documents: List[str] = field(default_factory=list)  # Selected document IDs
    sections: List[str] = field(default_factory=list)   # Selected section paths
    keywords: List[str] = field(default_factory=list)   # Keywords for filtering


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

    # Deep Agent flag (set by orchestrator)
    use_deep_agent: bool = False

    # Agent-Driven RAG: search scope (set from request)
    search_scope: Optional[SearchScope] = None


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


# Response mode for hybrid RAG (LLM vs Direct Return)
class ResponseMode(str, Enum):
    """응답 생성 모드 - 할루시네이션 최소화를 위한 설정"""
    DIRECT = "direct"   # LLM 없이 검색 결과 직접 반환 (할루시네이션 0%)
    LLM = "llm"         # 기존 LLM synthesis 방식
    HYBRID = "hybrid"   # 검색 결과 품질에 따라 자동 선택 (권장)


# ============================================================================
# Structured Answer Types for ChatGPT-level RAG Output
# ============================================================================

class BlockType(str, Enum):
    """Types of content blocks in structured answers"""
    TEXT = "text"
    HEADING = "heading"
    LIST = "list"
    CODE = "code"
    TABLE = "table"
    QUOTE = "quote"
    IMAGE = "image"
    SOURCE_CITATION = "source_citation"
    NO_ANSWER = "no_answer"
    PRODUCT_VERSION = "product_version"  # Multi-product platform comparison block


class AnswerBlock(BaseModel):
    """
    Individual block in a structured answer.
    Supports multiple content types for ChatGPT-like output rendering.
    """
    type: BlockType = Field(..., description="Type of the content block")
    content: Optional[str] = Field(None, description="Main text content")

    # List block fields
    items: Optional[List[str]] = Field(None, description="List items for LIST type")
    ordered: bool = Field(False, description="Whether list is ordered (numbered)")

    # Code block fields
    language: Optional[str] = Field(None, description="Programming language for CODE type")

    # Table block fields
    headers: Optional[List[str]] = Field(None, description="Table headers for TABLE type")
    rows: Optional[List[List[str]]] = Field(None, description="Table rows for TABLE type")

    # Heading block fields
    level: Optional[int] = Field(None, ge=1, le=4, description="Heading level (1-4)")

    # Image block fields
    url: Optional[str] = Field(None, description="Image URL for IMAGE type")
    caption: Optional[str] = Field(None, description="Image caption")

    # Source citation fields
    doc_name: Optional[str] = Field(None, description="Document name for SOURCE_CITATION")
    page: Optional[int] = Field(None, description="Page number for SOURCE_CITATION")
    chunk_id: Optional[str] = Field(None, description="Chunk ID for SOURCE_CITATION")
    score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance score")

    # Product version block fields (for multi-product platform comparison)
    name: Optional[str] = Field(None, description="Command/error/term name for PRODUCT_VERSION")
    doc_type: Optional[str] = Field(None, description="Document type: commands, error-codes, glossary, apis")
    variants: Optional[List[Dict[str, Any]]] = Field(None, description="Platform variants for PRODUCT_VERSION")
    has_differences: Optional[bool] = Field(None, description="Whether variants differ across platforms")
    available_platforms: Optional[List[str]] = Field(None, description="List of available platforms (MVS, MSP, XSP, VOS3)")

    class Config:
        json_schema_extra = {
            "examples": [
                {"type": "text", "content": "This is a text block."},
                {"type": "heading", "content": "Section Title", "level": 2},
                {"type": "list", "items": ["Item 1", "Item 2"], "ordered": True},
                {"type": "code", "content": "print('hello')", "language": "python"},
            ]
        }


class StructuredAnswer(BaseModel):
    """
    Structured answer composed of multiple content blocks.
    Enables ChatGPT-like rendering with proper formatting.
    """
    blocks: List[AnswerBlock] = Field(..., description="Ordered list of content blocks")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Overall answer confidence")
    language: str = Field("auto", description="Answer language (auto, ko, en, ja)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")

    def to_markdown(self) -> str:
        """Convert structured answer to markdown string for backward compatibility"""
        lines = []
        for block in self.blocks:
            if block.type == BlockType.TEXT:
                lines.append(block.content or "")
            elif block.type == BlockType.HEADING:
                level = block.level or 2
                lines.append(f"{'#' * level} {block.content or ''}")
            elif block.type == BlockType.LIST:
                for i, item in enumerate(block.items or [], 1):
                    prefix = f"{i}." if block.ordered else "-"
                    lines.append(f"{prefix} {item}")
            elif block.type == BlockType.CODE:
                lang = block.language or ""
                lines.append(f"```{lang}\n{block.content or ''}\n```")
            elif block.type == BlockType.TABLE:
                if block.headers:
                    lines.append("| " + " | ".join(block.headers) + " |")
                    lines.append("| " + " | ".join(["---"] * len(block.headers)) + " |")
                for row in block.rows or []:
                    lines.append("| " + " | ".join(row) + " |")
            elif block.type == BlockType.QUOTE:
                lines.append(f"> {block.content or ''}")
            elif block.type == BlockType.SOURCE_CITATION:
                page_info = f" (p.{block.page})" if block.page else ""
                score_info = f" [{block.score*100:.0f}%]" if block.score else ""
                lines.append(f"📎 {block.doc_name or 'Unknown'}{page_info}{score_info}")
            elif block.type == BlockType.NO_ANSWER:
                lines.append(block.content or "No relevant information found.")
            elif block.type == BlockType.PRODUCT_VERSION:
                # Format product version block as markdown
                name = block.name or "Unknown"
                doc_type = block.doc_type or "commands"
                platforms = ", ".join(block.available_platforms or [])
                lines.append(f"### [{doc_type.upper()}] {name}")
                if platforms:
                    lines.append(f"**플랫폼**: {platforms}")
                if block.has_differences:
                    lines.append("⚠️ **플랫폼별 차이 있음**")
                for variant in block.variants or []:
                    platform = variant.get("platform", "Unknown")
                    version = variant.get("product_version", "")
                    description = variant.get("description", "")
                    syntax = variant.get("syntax", "")
                    source_pdf = variant.get("source_pdf", "")
                    version_str = f" (v{version})" if version else ""
                    lines.append(f"\n#### {platform}{version_str}")
                    if description:
                        lines.append(description)
                    if syntax:
                        lines.append(f"```\n{syntax}\n```")
                    if source_pdf:
                        lines.append(f"📄 출처: {source_pdf}")
            lines.append("")
        return "\n".join(lines)


# Pydantic model for search scope in API requests
class SearchScopeModel(BaseModel):
    """Search scope for Agent-Driven RAG queries"""
    documents: List[str] = Field(default_factory=list, description="Selected document IDs")
    sections: List[str] = Field(default_factory=list, description="Selected section paths")
    keywords: List[str] = Field(default_factory=list, description="Keywords for filtering")


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
    ui_context: Optional[Dict[str, Any]] = Field(None, description="UI context for context-aware AI responses")
    use_deep_agent: bool = Field(True, description="Use Deep Agents framework for execution")
    response_mode: ResponseMode = Field(
        ResponseMode.HYBRID,
        description="Response generation mode: 'hybrid' (auto-select based on search quality - default), 'direct' (no LLM, zero hallucination), 'llm' (traditional)"
    )
    search_scope: Optional[SearchScopeModel] = Field(None, description="Agent-Driven RAG: selected search scope")
    structured_output: bool = Field(
        False,
        description="Enable ChatGPT-style structured answer blocks for improved rendering"
    )
    skip_clarification: bool = Field(
        False,
        description="Skip query clarification (Human-in-the-loop) for this request"
    )


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
    chunk_type: Literal[
        "thinking", "tool_call", "tool_result", "text", "sources", "done", "error", "status", "artifact", "image",
        # RAG analysis chunk types for detailed progress visualization
        "rag_analysis",      # 프롬프트 분석 결과 (키워드, 의도, 검색 전략)
        "chunk_structure",   # 문서의 청킹 구조
        "embedding_info",    # 임베딩된 구조 정보
        "generation_start",  # 답변 생성 시작
        "generation_progress",  # 답변 생성 과정
        # Individual search result for expandable card display
        "search_result",     # 개별 검색 결과 (텍스트, 이미지, 테이블 포함)
        # Source reliability for search result credibility
        "source_reliability", # 출처 신뢰도 정보
        # Query clarification (Human-in-the-loop)
        "clarification_needed",   # 질문 명확화 필요 (옵션 목록 포함)
        "clarification_received", # 사용자 선택 수신
        # RAG Evaluation chunk types (RAGAS-style quality metrics)
        "rag_evaluation",     # RAG 평가 결과 (종합 점수, 메트릭별 점수, 이슈)
        "rag_evaluation_progress",  # RAG 평가 진행 중 (메트릭별 진행 상태)
        # User feedback prompt
        "feedback_prompt",    # 피드백 요청 (message_id와 함께 UI에 👍/👎 버튼 표시)
        # Enhanced citation display
        "enhanced_citations",  # 강화된 출처 정보 (피드백 점수, 표시 포맷 포함)
        # Structured answer chunk types for ChatGPT-like output
        "answer_start",       # 구조화 답변 시작 (total_blocks, confidence 포함)
        "answer_block",       # 개별 블록 스트리밍
        "answer_complete"     # 답변 완료
    ]
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

    # Search result fields (for search_result chunk type)
    result_index: Optional[int] = None          # 결과 순서 (1, 2, 3...)
    result_total: Optional[int] = None          # 전체 결과 수
    result_title: Optional[str] = None          # 문서/섹션 제목
    result_content: Optional[str] = None        # 텍스트 내용
    result_images: Optional[List[Dict[str, Any]]] = None   # 관련 이미지들
    result_tables: Optional[List[Dict[str, Any]]] = None   # 관련 테이블들
    result_source: Optional[Dict[str, Any]] = None         # 참조 문서 정보
    result_score: Optional[float] = None        # 관련도 점수

    # Structured answer fields (for answer_block chunk type)
    answer_block: Optional[AnswerBlock] = None  # 개별 답변 블록
    block_index: Optional[int] = None           # 현재 블록 인덱스
    total_blocks: Optional[int] = None          # 전체 블록 수


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
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
    use_deep_agent: bool = Field(True, description="Use Deep Agents framework for execution")

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

    # Trace data for UI visualization
    trace_data: Optional[Dict[str, Any]] = None
    """
    Structure for trace visualization:
    {
        "trace_id": "uuid",
        "dag": {
            "tasks": [{"task_id": "t1", "description": "...", "agent_type": "rag", "status": "completed", "dependencies": []}],
            "execution_batches": [["t1", "t2"], ["t3"]],
            "parallelism_type": "partial"
        },
        "current_task": {"task_id": "t2", "status": "running", "start_time": "..."},
        "evaluations": {"t1": {"passed": true, "score": 0.9, "issues": []}},
        "timeline": [{"event": "task_start", "task_id": "t1", "timestamp": "...", "data": {...}}]
    }
    """
