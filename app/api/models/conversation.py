"""
Conversation and Message Pydantic models for ChatGPT-equivalent history system.

This module provides models for:
- Conversation management (create, update, list, detail)
- Message operations (create, response, feedback)
- Regeneration and fork functionality
- Context window management for RAG
- Rolling summarization
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, ConfigDict


# ============================================
# Enums
# ============================================

class MessageRole(str, Enum):
    """Message role in conversation"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class SummaryType(str, Enum):
    """Type of conversation summary"""
    ROLLING = "rolling"      # Auto-generated when token threshold exceeded
    CHECKPOINT = "checkpoint"  # User-triggered checkpoint
    FINAL = "final"          # End of conversation summary


class ConversationStatus(str, Enum):
    """Conversation status for filtering"""
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


# ============================================
# Message Models
# ============================================

class MessageCreate(BaseModel):
    """Request model for creating a new message"""
    role: MessageRole
    content: str = Field(..., min_length=1, max_length=100000)
    parent_message_id: Optional[UUID] = None
    model: Optional[str] = None

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Strip whitespace and validate non-empty"""
        v = v.strip()
        if not v:
            raise ValueError('Content cannot be empty or whitespace only')
        return v


class MessageFeedback(BaseModel):
    """Request model for message feedback"""
    score: int = Field(..., ge=1, le=5, description="Rating from 1 to 5")
    text: Optional[str] = Field(None, max_length=2000)


class MessageSource(BaseModel):
    """Source information for RAG-generated messages"""
    doc_id: Optional[str] = None
    doc_name: str
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    content: str = Field(..., max_length=1000)
    score: float = Field(..., ge=0.0, le=1.0)
    source_type: str = "vector"  # vector, graph, session, external
    is_session_doc: bool = False
    is_external_resource: bool = False
    source_url: Optional[str] = None
    external_source: Optional[str] = None  # notion, github, confluence, etc.
    page_number: Optional[int] = None
    section_title: Optional[str] = None


class MessageResponse(BaseModel):
    """Response model for a message"""
    id: UUID
    conversation_id: UUID
    parent_message_id: Optional[UUID] = None
    role: MessageRole
    content: str

    # Token information
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: Optional[str] = None

    # RAG sources (for assistant messages)
    sources: List[Dict[str, Any]] = Field(default_factory=list)

    # Feedback
    feedback_score: Optional[int] = None
    feedback_text: Optional[str] = None

    # Branch information
    is_regenerated: bool = False
    regeneration_count: int = 0
    is_active_branch: bool = True
    branch_depth: int = 0

    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageListItem(BaseModel):
    """Simplified message for list views"""
    id: UUID
    role: MessageRole
    content_preview: str = Field(..., max_length=200)
    total_tokens: int = 0
    is_regenerated: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================
# Conversation Models
# ============================================

class ConversationCreate(BaseModel):
    """Request model for creating a new conversation"""
    title: Optional[str] = Field(None, max_length=500)
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    strategy: Optional[str] = Field(default="auto", pattern="^(auto|vector|graph|hybrid|code)$")
    language: Optional[str] = Field(default="auto", pattern="^(auto|ko|ja|en)$")
    agent_type: Optional[str] = Field(default="auto", pattern="^(auto|rag|ims|vision|code|planner)$")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace from title"""
        return v.strip() if v else v


class ConversationUpdate(BaseModel):
    """Request model for updating a conversation"""
    title: Optional[str] = Field(None, max_length=500)
    is_archived: Optional[bool] = None
    is_starred: Optional[bool] = None
    strategy: Optional[str] = Field(None, pattern="^(auto|vector|graph|hybrid|code)$")
    language: Optional[str] = Field(None, pattern="^(auto|ko|ja|en)$")
    agent_type: Optional[str] = Field(None, pattern="^(auto|rag|ims|vision|code|planner)$")
    metadata: Optional[Dict[str, Any]] = None


class ConversationListItem(BaseModel):
    """Conversation summary for list views"""
    id: UUID
    title: Optional[str]
    message_count: int = 0
    total_tokens: int = 0
    is_archived: bool = False
    is_starred: bool = False
    strategy: Optional[str] = None
    language: Optional[str] = None
    agent_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Preview content
    first_message_preview: Optional[str] = None
    last_message_preview: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ConversationDetail(ConversationListItem):
    """Full conversation detail with messages"""
    user_id: str
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    messages: List[MessageResponse] = Field(default_factory=list)
    active_summary: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================
# Regenerate Models
# ============================================

class RegenerateRequest(BaseModel):
    """Request to regenerate an assistant message"""
    message_id: UUID
    strategy: Optional[str] = Field(None, pattern="^(auto|vector|graph|hybrid|code)$")
    language: Optional[str] = Field(None, pattern="^(auto|ko|ja|en)$")


class RegenerateResponse(BaseModel):
    """Response from message regeneration"""
    original_message_id: UUID
    new_message: MessageResponse
    regeneration_count: int


# ============================================
# Fork Models
# ============================================

class ConversationForkRequest(BaseModel):
    """Request to fork conversation from a specific message"""
    from_message_id: UUID
    new_title: Optional[str] = Field(None, max_length=500)
    include_system_messages: bool = True


class ConversationForkResponse(BaseModel):
    """Response from forking a conversation"""
    original_conversation_id: UUID
    new_conversation: ConversationDetail
    forked_from_message_id: UUID
    messages_copied: int


# ============================================
# Summary Models
# ============================================

class SummaryCreate(BaseModel):
    """Request model for creating a summary"""
    summary_text: str = Field(..., min_length=10, max_length=10000)
    summary_type: SummaryType = SummaryType.ROLLING
    covers_from_message_id: Optional[UUID] = None
    covers_to_message_id: Optional[UUID] = None
    message_count_covered: int = 0
    tokens_before_summary: int = 0
    tokens_after_summary: int = 0
    key_topics: List[str] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)


class SummaryResponse(BaseModel):
    """Response model for a conversation summary"""
    id: UUID
    conversation_id: UUID
    summary_text: str
    summary_type: SummaryType
    message_count_covered: int
    tokens_before_summary: int
    tokens_after_summary: int
    compression_ratio: Optional[float] = None
    key_topics: List[str] = Field(default_factory=list)
    key_entities: List[str] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================
# Context Window Models
# ============================================

class ContextWindowConfig(BaseModel):
    """Configuration for context window management"""
    max_tokens: int = Field(default=8000, ge=1000, le=128000)
    reserved_for_response: int = Field(default=2000, ge=500)
    system_prompt_tokens: int = Field(default=500)
    rag_context_tokens: int = Field(default=2000)
    summary_tokens: int = Field(default=1000)
    recent_turns_count: int = Field(default=6, ge=1, le=50)


class ReconstructedContext(BaseModel):
    """Reconstructed context for LLM input"""
    system_prompt: str
    summary: Optional[str] = None
    recent_messages: List[Dict[str, str]] = Field(default_factory=list)  # [{role, content}]
    rag_context: Optional[str] = None
    current_input: str

    # Metadata
    total_tokens: int = 0
    summary_used: bool = False
    messages_included: int = 0
    messages_summarized: int = 0


class ContextWindowResult(BaseModel):
    """Result from context window extraction"""
    messages: List[MessageResponse] = Field(default_factory=list)
    summary: Optional[str] = None
    total_tokens: int = 0
    messages_included: int = 0
    messages_summarized: int = 0


# ============================================
# Query Models (for RAG integration)
# ============================================

class ConversationQueryRequest(BaseModel):
    """Request for querying with conversation context"""
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_id: UUID
    strategy: str = Field(default="auto", pattern="^(auto|vector|graph|hybrid|code)$")
    language: str = Field(default="auto", pattern="^(auto|ko|ja|en)$")
    include_session_docs: bool = True
    include_external_resources: bool = True


class ConversationQueryResponse(BaseModel):
    """Response from conversation-aware query"""
    answer: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    strategy: str
    language: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    conversation_id: UUID
    message_id: UUID
    context_info: Dict[str, Any] = Field(default_factory=dict)


# ============================================
# Search Models
# ============================================

class ConversationSearchRequest(BaseModel):
    """Request for searching conversations"""
    query: str = Field(..., min_length=2, max_length=200)
    include_archived: bool = False
    limit: int = Field(default=20, ge=1, le=100)


class ConversationSearchResult(BaseModel):
    """Search result with relevance scoring"""
    conversation: ConversationListItem
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    matched_content: Optional[str] = None  # Snippet with match highlighted


# ============================================
# Audit Models
# ============================================

class ConversationAuditEntry(BaseModel):
    """Audit log entry for conversation operations"""
    id: UUID
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    user_id: str
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
