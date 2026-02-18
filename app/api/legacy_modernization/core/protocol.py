"""Agent Communication Protocol - message types, change requests, audit trail."""

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from ..models.enums import (
    AgentRole,
    AgentStatus,
    AuditAction,
    ChangeRequestStatus,
    MessageType,
)


class AgentId(BaseModel):
    """Unique identifier for an agent instance."""

    role: AgentRole
    instance_id: str = Field(default_factory=lambda: str(uuid4()))


class AgentMessage(BaseModel):
    """Inter-agent communication message."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    sender: AgentId
    recipient: AgentId
    message_type: MessageType
    payload: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str = Field(..., description="분석 세션 추적용")
    priority: int = Field(0, description="0=normal, 1=high, 2=urgent")


class ChangeRequest(BaseModel):
    """Change request between agents (direct overwrite prohibited)."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    requester: AgentId
    target_field: str = Field(
        ...,
        description="변경 대상 필드 (e.g., 'compatibility_findings[3].severity')",
    )
    current_value: Any = None
    proposed_value: Any = None
    justification: str = Field(
        ..., min_length=10, description="변경 사유 (최소 10자)"
    )
    confidence_delta: float = Field(0.0, description="신뢰도 변화량")
    status: ChangeRequestStatus = ChangeRequestStatus.PENDING
    resolved_by: Optional[AgentId] = None
    resolved_at: Optional[datetime] = None
    resolution_reason: Optional[str] = None


class Resolution(BaseModel):
    """Result of conflict resolution."""

    status: ChangeRequestStatus
    reason: str
    rule_applied: str


class ChangeRequestResponse(BaseModel):
    """Agent response to a change request."""

    request_id: str
    approved: bool
    reason: str
    agent_id: AgentId


class AuditEntry(BaseModel):
    """Immutable audit trail record."""

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    actor: AgentId
    action: AuditAction
    target_asset_id: str
    details: dict = Field(default_factory=dict)
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None


class AgentTask(BaseModel):
    """Task assigned to an agent by the orchestrator."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_id: str
    source_code: str = ""
    file_path: str = ""
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    assigned_to: AgentRole
    metadata: dict = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Result returned by an agent after execution."""

    agent_id: AgentId
    status: AgentStatus
    workspace_id: str = ""
    error_message: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
