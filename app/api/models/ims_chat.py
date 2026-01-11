"""
IMS Chat Models - Request/Response models for IMS-based AI chat

This module defines models for chatting with AI about crawled IMS issues.
The chat context is LIMITED to searched/crawled issues only.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum


class IMSChatRole(str, Enum):
    """Chat message role"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class IMSIssueContext(BaseModel):
    """IMS Issue context for chat"""
    issue_id: UUID
    ims_id: str
    title: str
    status_raw: Optional[str] = None
    priority_raw: Optional[str] = None
    product: Optional[str] = None
    version: Optional[str] = None
    module: Optional[str] = None
    customer: Optional[str] = None
    description: Optional[str] = None
    issue_details: Optional[str] = None
    relevance_score: float = 0.0


class IMSChatRequest(BaseModel):
    """Request model for IMS chat"""
    question: str = Field(..., description="User's question about IMS issues")
    issue_ids: List[UUID] = Field(..., description="List of IMS issue IDs to use as context (from search results)")
    conversation_id: Optional[UUID] = Field(None, description="Existing conversation ID to continue")
    language: str = Field("auto", description="Response language: auto, ko, ja, en")
    stream: bool = Field(True, description="Whether to stream the response")
    max_context_issues: int = Field(10, description="Maximum issues to include in context")

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "question": "mscasmc 토큰 오류 해결 방법은?",
                "issue_ids": ["uuid-1", "uuid-2", "uuid-3"],
                "conversation_id": None,
                "language": "auto",
                "stream": True,
                "max_context_issues": 10
            }
        })


class IMSChatMessage(BaseModel):
    """A single chat message"""
    id: UUID
    role: IMSChatRole
    content: str
    created_at: datetime
    referenced_issues: List[str] = Field(default_factory=list, description="IMS IDs referenced in this message")


class IMSChatResponse(BaseModel):
    """Response model for IMS chat (non-streaming)"""
    conversation_id: UUID
    message_id: UUID
    content: str
    role: IMSChatRole = IMSChatRole.ASSISTANT
    referenced_issues: List[IMSIssueContext] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    created_at: datetime


class IMSChatStreamEvent(BaseModel):
    """SSE event for streaming chat response"""
    event: str  # "start", "token", "sources", "done", "error"
    data: Dict[str, Any]


class IMSChatConversation(BaseModel):
    """IMS Chat conversation with history"""
    id: UUID
    title: Optional[str] = None
    issue_ids: List[UUID] = Field(default_factory=list, description="IMS issues in this conversation context")
    messages: List[IMSChatMessage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class IMSChatConversationCreate(BaseModel):
    """Create a new IMS chat conversation"""
    title: Optional[str] = None
    issue_ids: List[UUID] = Field(..., description="IMS issue IDs for this conversation context")


class IMSChatHistoryRequest(BaseModel):
    """Request to get chat history"""
    conversation_id: UUID
    limit: int = Field(50, description="Maximum messages to return")
    offset: int = Field(0, description="Offset for pagination")
