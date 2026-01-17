"""
Enhancement Request Models

Data models for the AI-Driven Enhancement & Improvement Management System.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EnhancementStatus(str, Enum):
    """Status states for enhancement requests"""
    SUBMITTED = "submitted"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ARCHITECTURE_REVIEW = "architecture_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTING = "implementing"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    VERIFIED = "verified"
    RELEASED = "released"
    CLOSED = "closed"


class EnhancementType(str, Enum):
    """Types of enhancement requests"""
    FEATURE = "feature"
    BUG_FIX = "bug_fix"
    IMPROVEMENT = "improvement"
    REFACTOR = "refactor"
    DOCUMENTATION = "documentation"
    SECURITY = "security"
    PERFORMANCE = "performance"


class EnhancementPriority(str, Enum):
    """Priority levels for enhancements"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ComplexityLevel(str, Enum):
    """Complexity assessment levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# ============================================================================
# Attachment Models
# ============================================================================

class AttachmentInfo(BaseModel):
    """Information about an uploaded attachment"""
    id: str
    filename: str
    original_name: str
    file_size: int
    mime_type: str
    storage_path: str
    extracted_text: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ============================================================================
# Timeline & Comment Models
# ============================================================================

class TimelineEventType(str, Enum):
    """Types of timeline events"""
    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ANALYZED = "analyzed"
    COMMENTED = "commented"
    ATTACHMENT_ADDED = "attachment_added"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHITECTURE_STARTED = "architecture_started"
    ARCHITECTURE_COMPLETED = "architecture_completed"
    IMPLEMENTATION_STARTED = "implementation_started"
    CODE_COMMITTED = "code_committed"
    TESTING_STARTED = "testing_started"
    VERIFIED = "verified"
    RELEASED = "released"


class TimelineEvent(BaseModel):
    """A single event in the enhancement timeline"""
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: TimelineEventType
    description: str
    actor_id: str
    actor_name: str
    actor_type: str = "user"  # "user" or "agent"
    details: Optional[Dict[str, Any]] = None


class Comment(BaseModel):
    """A comment on an enhancement request"""
    id: str
    content: str
    author_id: str
    author_name: str
    author_type: str = "user"  # "user" or "agent"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None


# ============================================================================
# AI Analysis Models
# ============================================================================

class AIAnalysisResult(BaseModel):
    """Results from AI agent analysis"""
    summary: str
    type_classification: EnhancementType
    priority_recommendation: EnhancementPriority
    affected_components: List[str] = Field(default_factory=list)
    potential_risks: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    estimated_complexity: ComplexityLevel = ComplexityLevel.MEDIUM
    feasibility_score: float = Field(ge=0.0, le=1.0, default=0.5)
    recommended_approach: str = ""
    questions_for_submitter: List[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str = ""


class DesignDecision(BaseModel):
    """A design decision made by the architect agent"""
    title: str
    description: str
    rationale: str
    alternatives_considered: List[str] = Field(default_factory=list)
    trade_offs: str = ""


class FileChange(BaseModel):
    """A file modification in the architecture proposal"""
    file_path: str
    change_type: str  # "modify", "delete"
    description: str
    estimated_lines: int = 0


class NewFile(BaseModel):
    """A new file to be created"""
    file_path: str
    purpose: str
    template: Optional[str] = None


class APIChange(BaseModel):
    """An API change in the proposal"""
    endpoint: str
    method: str
    change_type: str  # "add", "modify", "deprecate", "remove"
    description: str


class ArchitectureProposal(BaseModel):
    """Architecture proposal from the architect agent"""
    approach: str
    design_decisions: List[DesignDecision] = Field(default_factory=list)
    file_changes: List[FileChange] = Field(default_factory=list)
    new_files: List[NewFile] = Field(default_factory=list)
    api_changes: List[APIChange] = Field(default_factory=list)
    database_changes: List[str] = Field(default_factory=list)
    security_considerations: List[str] = Field(default_factory=list)
    backward_compatible: bool = True
    migration_required: bool = False
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewer_agent_id: str = ""


class ImplementationPhase(BaseModel):
    """A phase in the implementation plan"""
    phase_number: int
    title: str
    description: str
    tasks: List[str] = Field(default_factory=list)
    dependencies: List[int] = Field(default_factory=list)  # Phase numbers
    estimated_effort: str = ""


class TestStrategy(BaseModel):
    """Testing strategy for the implementation"""
    unit_tests: List[str] = Field(default_factory=list)
    integration_tests: List[str] = Field(default_factory=list)
    e2e_tests: List[str] = Field(default_factory=list)
    manual_tests: List[str] = Field(default_factory=list)


class ImplementationPlan(BaseModel):
    """Complete implementation plan"""
    phases: List[ImplementationPhase] = Field(default_factory=list)
    test_strategy: TestStrategy = Field(default_factory=TestStrategy)
    rollback_plan: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_agent: str = ""


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateEnhancementRequest(BaseModel):
    """Request to create a new enhancement"""
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=20)
    type: Optional[EnhancementType] = None
    priority: Optional[EnhancementPriority] = None


class UpdateEnhancementRequest(BaseModel):
    """Request to update an enhancement"""
    title: Optional[str] = Field(None, min_length=5, max_length=200)
    description: Optional[str] = Field(None, min_length=20)
    type: Optional[EnhancementType] = None
    priority: Optional[EnhancementPriority] = None


class EnhancementListItem(BaseModel):
    """Enhancement item for list views"""
    id: str
    title: str
    type: Optional[EnhancementType] = None
    priority: Optional[EnhancementPriority] = None
    status: EnhancementStatus
    author_id: str
    author_name: str
    created_at: datetime
    updated_at: datetime
    ai_analyzed: bool = False
    attachments_count: int = 0


class EnhancementDetail(EnhancementListItem):
    """Full enhancement details"""
    description: str
    attachments: List[AttachmentInfo] = Field(default_factory=list)
    ai_analysis: Optional[AIAnalysisResult] = None
    architecture_proposal: Optional[ArchitectureProposal] = None
    implementation_plan: Optional[ImplementationPlan] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)
    comments: List[Comment] = Field(default_factory=list)
    assigned_agents: List[str] = Field(default_factory=list)
    estimated_effort: Optional[str] = None
    actual_effort: Optional[str] = None
    impact_score: Optional[float] = None


class CreateEnhancementResponse(BaseModel):
    """Response after creating an enhancement"""
    id: str
    title: str
    status: EnhancementStatus
    created_at: datetime
    message: str = "Enhancement request submitted successfully"


class AnalysisResponse(BaseModel):
    """Response after AI analysis"""
    enhancement_id: str
    analysis: AIAnalysisResult
    status: EnhancementStatus
    next_steps: List[str] = Field(default_factory=list)


class ArchitectureResponse(BaseModel):
    """Response after architecture proposal"""
    enhancement_id: str
    proposal: ArchitectureProposal
    status: EnhancementStatus
    next_steps: List[str] = Field(default_factory=list)


class ImplementationResponse(BaseModel):
    """Response after implementation plan creation"""
    enhancement_id: str
    plan: ImplementationPlan
    status: EnhancementStatus
    next_steps: List[str] = Field(default_factory=list)


class ApproveRejectRequest(BaseModel):
    """Request to approve or reject an enhancement"""
    reason: Optional[str] = None
    comments: Optional[str] = None


class EnhancementDashboardStats(BaseModel):
    """Dashboard statistics"""
    total_requests: int = 0
    by_status: Dict[str, int] = Field(default_factory=dict)
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_priority: Dict[str, int] = Field(default_factory=dict)
    avg_analysis_time_seconds: float = 0.0
    avg_resolution_time_hours: float = 0.0
    ai_analyzed_count: int = 0
    implemented_count: int = 0
