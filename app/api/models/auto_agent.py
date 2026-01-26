"""
Auto Agent API Models

Pydantic models for the Auto Agent API endpoints.
"""
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class AutoAgentRequest(BaseModel):
    """Request model for Auto Agent execution"""
    task: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User's task or question for the AI system"
    )
    session_id: Optional[str] = Field(
        None,
        description="Session ID for context continuity"
    )
    language: str = Field(
        "auto",
        description="Response language (auto, en, ko, ja)"
    )
    max_steps: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum reasoning steps per agent"
    )
    include_sources: bool = Field(
        True,
        description="Include sources in response"
    )
    stream: bool = Field(
        False,
        description="Enable streaming response"
    )

    # Context options
    file_context: Optional[str] = Field(
        None,
        description="Attached file content for RAG priority context"
    )
    url_context: Optional[str] = Field(
        None,
        description="URL content to use as context"
    )

    # Auto Agent specific options
    max_retries: int = Field(
        2,
        ge=0,
        le=5,
        description="Maximum retry attempts per task"
    )
    max_replans: int = Field(
        1,
        ge=0,
        le=3,
        description="Maximum full replan attempts"
    )
    confidence_threshold: float = Field(
        0.6,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for acceptance"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task": "OpenFrame의 oscboot 오류 해결 방법과 관련 이슈를 알려줘",
                "language": "ko",
                "max_retries": 2,
                "confidence_threshold": 0.7
            }
        }


class TaskInfo(BaseModel):
    """Information about a planned task"""
    task_id: str = Field(..., description="Task identifier")
    description: str = Field(..., description="Task description")
    agent_type: str = Field(..., description="Agent type (rag, ims, code, vision)")
    dependencies: List[str] = Field(default_factory=list, description="Dependent task IDs")
    status: str = Field("pending", description="Task status")


class PlanInfo(BaseModel):
    """Information about the execution plan"""
    plan_id: str = Field(..., description="Plan identifier")
    task_count: int = Field(..., description="Number of tasks in plan")
    parallelism_strategy: str = Field(..., description="Parallelism strategy")
    tasks: List[TaskInfo] = Field(default_factory=list, description="Planned tasks")
    estimated_confidence: float = Field(..., ge=0.0, le=1.0, description="Estimated confidence")


class VerificationInfo(BaseModel):
    """Information about verification results"""
    decision: str = Field(..., description="Verification decision (accept, partial_retry, full_replan)")
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall quality score")
    grounding_score: float = Field(..., ge=0.0, le=1.0, description="Grounding score")
    consistency_score: float = Field(..., ge=0.0, le=1.0, description="Consistency score")
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Completeness score")
    execution_score: float = Field(..., ge=0.0, le=1.0, description="Execution success score")
    issue_count: int = Field(0, description="Number of issues found")


class SourceInfo(BaseModel):
    """Information about a source reference"""
    title: str = Field(..., description="Source title")
    type: str = Field("document", description="Source type (document, ims_issue, code_sample)")
    reference: Optional[str] = Field(None, description="Reference ID or code")
    url: Optional[str] = Field(None, description="Source URL if available")


class AutoAgentResponse(BaseModel):
    """Response model for Auto Agent execution"""
    execution_id: str = Field(..., description="Unique execution identifier")
    answer: str = Field(..., description="Final composed answer")
    language: str = Field(..., description="Answer language")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence score")

    # Plan info
    plan: Optional[PlanInfo] = Field(None, description="Execution plan information")

    # Verification info
    verification: Optional[VerificationInfo] = Field(None, description="Verification results")

    # Sources
    sources: List[SourceInfo] = Field(default_factory=list, description="Source citations")

    # Next actions
    next_actions: List[str] = Field(default_factory=list, description="Suggested follow-up actions")

    # Execution stats
    execution_time: float = Field(..., description="Total execution time in seconds")
    retry_count: int = Field(0, description="Number of retry attempts")
    replan_count: int = Field(0, description="Number of replan attempts")

    # Status
    success: bool = Field(True, description="Whether execution succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")

    # Partial failures
    partial_failures: List[str] = Field(
        default_factory=list,
        description="Task IDs that failed but were recovered"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "execution_id": "550e8400-e29b-41d4-a716-446655440000",
                "answer": "## oscboot 오류 해결 방법\n\n1. 환경 변수 확인...",
                "language": "ko",
                "confidence": 0.88,
                "sources": [
                    {"title": "OpenFrame 운영 가이드", "type": "document", "reference": "DOC-001"}
                ],
                "next_actions": ["로그 분석 요청", "특정 에러 코드 검색"],
                "execution_time": 12.5,
                "success": True
            }
        }


class AutoAgentStreamEvent(BaseModel):
    """SSE event for streaming Auto Agent execution"""
    event: str = Field(..., description="Event type")
    data: Dict[str, Any] = Field(..., description="Event data")

    class Config:
        json_schema_extra = {
            "example": {
                "event": "planning_done",
                "data": {
                    "plan_id": "abc123",
                    "task_count": 3,
                    "parallelism": "partial"
                }
            }
        }


class AutoAgentStatusResponse(BaseModel):
    """Response model for Auto Agent status check"""
    enabled: bool = Field(..., description="Whether Auto Agent is enabled")
    version: str = Field("1.0.0", description="Auto Agent version")
    components: Dict[str, bool] = Field(
        default_factory=dict,
        description="Component availability status"
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution statistics"
    )
