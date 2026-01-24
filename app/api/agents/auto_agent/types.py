"""
Auto Agent Type Definitions

Enterprise-grade AI orchestration types for the Meta-Agent (Auto Agent) system.
Includes ExecutionPlan, VerificationResult, Memory contexts, and related types.
"""
from enum import Enum
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid

from ..types import AgentType, AgentResult, ParallelismType


# ============================================================================
# Enums
# ============================================================================

class VerificationDecision(str, Enum):
    """Decision made by the Verifier Agent"""
    ACCEPT = "accept"              # Results are satisfactory, proceed to compose answer
    PARTIAL_RETRY = "partial_retry"  # Some tasks need retry, others are acceptable
    FULL_REPLAN = "full_replan"    # Systemic failure, need to create new plan


class IssueType(str, Enum):
    """Types of issues that can be detected during verification"""
    UNGROUNDED_CLAIM = "ungrounded_claim"      # Claim not supported by sources
    CONTRADICTION = "contradiction"             # Contradictions between agent results
    INCOMPLETE = "incomplete"                   # Answer doesn't fully address the task
    EXECUTION_FAILURE = "execution_failure"     # Agent execution failed
    TIMEOUT = "timeout"                         # Agent execution timed out
    EMPTY_RESULT = "empty_result"               # No meaningful result from agent
    LOW_CONFIDENCE = "low_confidence"           # Confidence below threshold
    HALLUCINATION = "hallucination"             # Generated content without source support


class IssueSeverity(str, Enum):
    """Severity levels for verification issues"""
    CRITICAL = "critical"    # Must be fixed, blocks acceptance
    MAJOR = "major"          # Should be fixed, affects quality
    MINOR = "minor"          # Nice to fix, minimal impact
    INFO = "info"            # Informational, no action needed


class PlanStatus(str, Enum):
    """Status of an execution plan"""
    CREATED = "created"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RETRY_PENDING = "retry_pending"
    REPLAN_PENDING = "replan_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CLARIFICATION_NEEDED = "clarification_needed"  # 질문 명확화 필요


class AmbiguityType(str, Enum):
    """Types of query ambiguity that require clarification"""
    TERM_AMBIGUOUS = "term_ambiguous"          # 용어가 여러 의미를 가질 수 있음
    SCOPE_UNCLEAR = "scope_unclear"            # 범위가 불명확
    CONTEXT_MISSING = "context_missing"        # 맥락 정보 부족
    MULTIPLE_INTENTS = "multiple_intents"      # 여러 의도가 혼재
    PRODUCT_UNSPECIFIED = "product_unspecified"  # 제품/기능 미지정


# ============================================================================
# Query Clarification Types
# ============================================================================

@dataclass
class ClarificationOption:
    """Single option for query clarification"""
    option_id: str                              # 옵션 식별자 (e.g., "opt_1")
    label: str                                  # 사용자에게 표시할 라벨
    description: str                            # 옵션 설명
    refined_query: str                          # 이 옵션 선택 시 사용할 구체화된 쿼리
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClarificationRequest:
    """Request for query clarification from user"""
    clarification_id: str                       # 고유 ID
    original_query: str                         # 원래 사용자 질문
    ambiguity_type: AmbiguityType               # 애매함의 유형
    clarification_question: str                 # 명확화를 위한 질문
    options: List[ClarificationOption] = field(default_factory=list)  # 선택 옵션들
    allow_custom_input: bool = True             # 사용자 직접 입력 허용
    confidence_without_clarification: float = 0.4  # 명확화 없이 진행 시 예상 신뢰도
    internal_reasoning: Optional[str] = None    # 내부 분석 (로그용)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "clarification_id": self.clarification_id,
            "original_query": self.original_query,
            "ambiguity_type": self.ambiguity_type.value,
            "clarification_question": self.clarification_question,
            "options": [
                {
                    "option_id": opt.option_id,
                    "label": opt.label,
                    "description": opt.description,
                    "refined_query": opt.refined_query,
                }
                for opt in self.options
            ],
            "allow_custom_input": self.allow_custom_input,
            "confidence_without_clarification": self.confidence_without_clarification,
        }


# ============================================================================
# Retry Configuration
# ============================================================================

@dataclass
class EnhancedRetryConfig:
    """Configuration for retry and replan logic"""
    max_retries: int = 2           # Maximum retry attempts per task
    max_replans: int = 1           # Maximum full replan attempts
    backoff_factor: float = 2.0    # Exponential backoff multiplier
    initial_delay: float = 1.0     # Initial delay before first retry (seconds)
    max_delay: float = 30.0        # Maximum delay between retries (seconds)
    retry_on_timeout: bool = True  # Retry if task times out
    retry_on_empty: bool = True    # Retry if result is empty
    retry_on_low_confidence: bool = True  # Retry if confidence below threshold
    confidence_threshold: float = 0.6     # Minimum acceptable confidence


# ============================================================================
# Planned Task
# ============================================================================

@dataclass
class PlannedTask:
    """
    Single task in an execution plan.
    More detailed than SubTask, includes planner's reasoning.
    """
    task_id: str
    description: str                           # What the task should accomplish
    agent_type: AgentType                      # Which agent to use
    dependencies: List[str] = field(default_factory=list)  # Task IDs that must complete first
    priority: int = 1                          # Execution priority (1 = highest)
    estimated_confidence: float = 0.8          # Planner's confidence estimate
    timeout_override: Optional[float] = None   # Custom timeout for this task
    context_requirements: List[str] = field(default_factory=list)  # Required context from dependencies
    fallback_strategy: Optional[str] = None    # What to do if task fails
    internal_reasoning: Optional[str] = None   # Chain-of-thought (not exposed to user)
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlannedTaskModel(BaseModel):
    """Pydantic model for PlannedTask serialization"""
    task_id: str = Field(..., description="Unique task identifier")
    description: str = Field(..., description="Task description")
    agent_type: str = Field(..., description="Agent type to execute this task")
    dependencies: List[str] = Field(default_factory=list, description="Dependent task IDs")
    priority: int = Field(1, description="Execution priority")
    estimated_confidence: float = Field(0.8, ge=0.0, le=1.0, description="Estimated confidence")
    timeout_override: Optional[float] = Field(None, description="Custom timeout in seconds")
    context_requirements: List[str] = Field(default_factory=list, description="Required context")
    fallback_strategy: Optional[str] = Field(None, description="Fallback on failure")


# ============================================================================
# Execution Plan
# ============================================================================

@dataclass
class ExecutionPlan:
    """
    Complete execution plan created by the Planner Agent.
    Includes task decomposition, parallelism strategy, and retry policy.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_task: str = ""                    # User's original request
    decomposed_tasks: List[PlannedTask] = field(default_factory=list)
    parallelism_strategy: ParallelismType = ParallelismType.NONE
    execution_batches: List[List[str]] = field(default_factory=list)  # Pre-computed parallel batches
    estimated_total_confidence: float = 0.8    # Overall confidence estimate
    retry_policy: EnhancedRetryConfig = field(default_factory=EnhancedRetryConfig)
    internal_reasoning: Optional[str] = None   # Planner's reasoning (hidden from user)
    status: PlanStatus = PlanStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Execution tracking
    current_batch_index: int = 0
    retry_count: int = 0
    replan_count: int = 0

    def get_task(self, task_id: str) -> Optional[PlannedTask]:
        """Get a task by ID"""
        for task in self.decomposed_tasks:
            if task.task_id == task_id:
                return task
        return None

    def get_next_batch(self) -> Optional[List[str]]:
        """Get the next batch of tasks to execute"""
        if self.current_batch_index < len(self.execution_batches):
            return self.execution_batches[self.current_batch_index]
        return None

    def advance_batch(self) -> None:
        """Advance to the next batch"""
        self.current_batch_index += 1


class ExecutionPlanModel(BaseModel):
    """Pydantic model for ExecutionPlan serialization (API responses)"""
    plan_id: str = Field(..., description="Unique plan identifier")
    original_task: str = Field(..., description="User's original request")
    decomposed_tasks: List[PlannedTaskModel] = Field(default_factory=list)
    parallelism_strategy: str = Field("none", description="Parallelism strategy")
    execution_batches: List[List[str]] = Field(default_factory=list)
    estimated_total_confidence: float = Field(0.8, ge=0.0, le=1.0)
    status: str = Field("created", description="Plan execution status")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Verification Types
# ============================================================================

@dataclass
class Issue:
    """
    Single issue detected during verification.
    """
    issue_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    issue_type: IssueType = IssueType.LOW_CONFIDENCE
    severity: IssueSeverity = IssueSeverity.MINOR
    task_id: Optional[str] = None              # Which task caused the issue
    description: str = ""                       # Human-readable description
    evidence: Optional[str] = None              # Evidence for the issue
    suggested_fix: Optional[str] = None         # How to fix it
    retryable: bool = True                      # Can be fixed by retry


@dataclass
class VerificationResult:
    """
    Result from the Verifier Agent after checking all agent results.
    """
    verification_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    decision: VerificationDecision = VerificationDecision.ACCEPT
    overall_score: float = 1.0                  # Overall quality score (0.0-1.0)

    # Component scores
    grounding_score: float = 1.0               # How well claims are grounded in sources
    consistency_score: float = 1.0             # Consistency between agent results
    completeness_score: float = 1.0            # How completely the task was addressed
    execution_score: float = 1.0               # Execution success rate

    # Issues found
    issues: List[Issue] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)  # Issue IDs that are critical

    # Retry guidance
    tasks_to_retry: List[str] = field(default_factory=list)   # Task IDs to retry
    retry_hints: Dict[str, str] = field(default_factory=dict)  # task_id -> hint

    # Metadata
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    internal_reasoning: Optional[str] = None   # Verifier's reasoning (hidden)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues"""
        return len(self.critical_issues) > 0

    @property
    def issue_count_by_severity(self) -> Dict[str, int]:
        """Count issues by severity"""
        counts = {s.value: 0 for s in IssueSeverity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return counts


class VerificationResultModel(BaseModel):
    """Pydantic model for VerificationResult serialization"""
    verification_id: str = Field(..., description="Verification ID")
    decision: str = Field(..., description="Verification decision")
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score")
    grounding_score: float = Field(..., ge=0.0, le=1.0)
    consistency_score: float = Field(..., ge=0.0, le=1.0)
    completeness_score: float = Field(..., ge=0.0, le=1.0)
    execution_score: float = Field(..., ge=0.0, le=1.0)
    tasks_to_retry: List[str] = Field(default_factory=list)


# ============================================================================
# Memory Context
# ============================================================================

@dataclass
class UserMemory:
    """
    User-specific memory persisted across sessions.
    Stored in Neo4j under /memories/user/
    """
    user_id: str
    language_preference: str = "auto"
    domain_expertise: List[str] = field(default_factory=list)
    frequently_asked_topics: List[str] = field(default_factory=list)
    response_style_preference: Optional[str] = None
    last_interaction: Optional[datetime] = None
    interaction_count: int = 0
    custom_preferences: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMemory:
    """
    System-wide memory about agent performance and patterns.
    Stored in Neo4j under /memories/system/
    """
    agent_success_rates: Dict[str, float] = field(default_factory=dict)  # agent_type -> success rate
    common_failure_patterns: List[str] = field(default_factory=list)
    average_execution_times: Dict[str, float] = field(default_factory=dict)
    popular_query_patterns: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ConversationMemory:
    """
    Current conversation context.
    Stored in PostgreSQL, rolling summary.
    """
    session_id: str
    conversation_summary: Optional[str] = None
    recent_turns: List[Dict[str, Any]] = field(default_factory=list)  # Last N turns
    key_topics: List[str] = field(default_factory=list)
    pending_context: Optional[str] = None  # Context to carry to next turn
    turn_count: int = 0


@dataclass
class AutoAgentMemoryContext:
    """
    Combined memory context passed to the Planner Agent.
    Aggregates user, system, and conversation memory.
    """
    user_memory: Optional[UserMemory] = None
    system_memory: Optional[SystemMemory] = None
    conversation_memory: Optional[ConversationMemory] = None

    # Derived insights for planner
    suggested_agents: List[AgentType] = field(default_factory=list)
    relevant_past_queries: List[str] = field(default_factory=list)
    domain_context: Optional[str] = None

    def get_language_preference(self) -> str:
        """Get user's language preference or auto"""
        if self.user_memory:
            return self.user_memory.language_preference
        return "auto"

    def get_agent_success_rate(self, agent_type: AgentType) -> float:
        """Get historical success rate for an agent type"""
        if self.system_memory:
            return self.system_memory.agent_success_rates.get(agent_type.value, 0.8)
        return 0.8  # Default assumption


# ============================================================================
# Composed Answer
# ============================================================================

@dataclass
class ComposedAnswer:
    """
    Final answer composed from verified agent results.
    All internal reasoning is stripped.
    """
    answer_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""                          # The final answer text
    language: str = "auto"                     # Language of the answer
    sources: List[Dict[str, Any]] = field(default_factory=list)  # Citations
    confidence: float = 1.0                    # Overall confidence
    next_actions: List[str] = field(default_factory=list)  # Suggested follow-ups
    metadata: Dict[str, Any] = field(default_factory=dict)
    composed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Streaming Chunks
# ============================================================================

class AutoAgentStreamChunk(BaseModel):
    """
    Streaming chunk for Auto Agent execution.
    Extends base streaming with orchestration-specific types.
    """
    chunk_type: Literal[
        # Planning phase
        "planning_start",
        "planning_progress",
        "planning_done",

        # Query Clarification phase (Human-in-the-loop)
        "clarification_needed",     # 질문 명확화 필요
        "clarification_received",   # 사용자 선택 수신

        # Execution phase
        "execution_start",
        "batch_start",
        "agent_start",
        "agent_progress",
        "agent_done",
        "batch_done",

        # Verification phase
        "verification_start",
        "verification_progress",
        "verification_done",

        # Retry/Replan
        "retry_start",
        "replan_start",

        # Composition phase
        "composition_start",
        "composition_done",

        # Final
        "next_actions",
        "done",
        "error"
    ]
    content: Optional[str] = None
    task_id: Optional[str] = None
    agent_type: Optional[str] = None
    phase: Optional[str] = None  # planning, execution, verification, composition

    # Progress info
    progress: Optional[float] = None  # 0.0-1.0
    current_step: Optional[int] = None
    total_steps: Optional[int] = None

    # Plan/Verification data
    plan_data: Optional[Dict[str, Any]] = None
    verification_data: Optional[Dict[str, Any]] = None

    # Clarification data (Human-in-the-loop)
    clarification_data: Optional[Dict[str, Any]] = None

    # Answer data
    sources: Optional[List[Dict[str, Any]]] = None
    next_actions: Optional[List[str]] = None

    # Error info
    error_message: Optional[str] = None
    error_task_id: Optional[str] = None

    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# Execution Result
# ============================================================================

@dataclass
class AutoAgentExecutionResult:
    """
    Complete result from Auto Agent orchestration.
    Includes plan, verification, and final answer.
    """
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Input
    original_task: str = ""

    # Plan
    plan: Optional[ExecutionPlan] = None

    # Agent results (keyed by task_id)
    task_results: Dict[str, AgentResult] = field(default_factory=dict)

    # Verification
    verification: Optional[VerificationResult] = None

    # Final answer
    answer: Optional[ComposedAnswer] = None

    # Execution stats
    total_execution_time: float = 0.0
    retry_attempts: int = 0
    replan_attempts: int = 0

    # Status
    success: bool = True
    error: Optional[str] = None
    partial_failure_tasks: List[str] = field(default_factory=list)

    # Timestamps
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    # Metadata for debugging/observability
    metadata: Dict[str, Any] = field(default_factory=dict)
