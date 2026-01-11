"""
Session Document Models for Context-Aware RAG
Handles documents uploaded during a chat session for priority-based retrieval
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SessionDocumentType(str, Enum):
    """Type of session document"""
    FILE = "file"        # Uploaded file
    TEXT = "text"        # Pasted text
    URL = "url"          # Web content (future)


class SessionDocumentStatus(str, Enum):
    """Processing status of session document"""
    PENDING = "pending"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"


class SessionChunk(BaseModel):
    """A chunk from a session document with embedding"""
    id: str
    session_id: str
    document_id: str
    content: str
    index: int
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Source info for citation
    source_type: str = "session"  # Always 'session' for these
    source_name: str = ""
    page_number: Optional[int] = None


class SessionDocument(BaseModel):
    """Document uploaded during a chat session"""
    id: str
    session_id: str
    user_id: Optional[str] = None

    # Document info
    document_type: SessionDocumentType = SessionDocumentType.FILE
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: int = 0

    # Content
    original_content: str = ""
    text_content: str = ""

    # Processing
    status: SessionDocumentStatus = SessionDocumentStatus.PENDING
    error_message: Optional[str] = None

    # Chunks
    chunk_count: int = 0
    chunks: List[SessionChunk] = Field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None


class SessionDocumentCreate(BaseModel):
    """Request to create a session document"""
    session_id: str
    document_type: SessionDocumentType = SessionDocumentType.TEXT
    filename: Optional[str] = None
    content: Optional[str] = None  # For text paste
    mime_type: Optional[str] = None


class SessionDocumentListItem(BaseModel):
    """Compact session document info for listing"""
    id: str
    session_id: str
    document_type: SessionDocumentType
    filename: Optional[str] = None
    status: SessionDocumentStatus
    chunk_count: int = 0
    word_count: int = 0
    created_at: datetime
    error_message: Optional[str] = None


class SessionDocumentUploadResponse(BaseModel):
    """Response after uploading a session document"""
    document_id: str
    session_id: str
    status: SessionDocumentStatus
    message: str


class SessionContext(BaseModel):
    """Session context for RAG queries"""
    session_id: str
    document_ids: List[str] = Field(default_factory=list)
    total_chunks: int = 0
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


class SessionSearchResult(BaseModel):
    """Search result from session documents"""
    chunk_id: str
    document_id: str
    session_id: str
    content: str
    score: float
    source_name: str
    source_type: str = "session"
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PriorityRAGRequest(BaseModel):
    """RAG query request with session context priority"""
    question: str
    session_id: Optional[str] = None
    strategy: str = "auto"
    language: str = "auto"
    options: Dict[str, Any] = Field(default_factory=dict)

    # Priority settings
    use_session_docs: bool = True
    session_weight: float = Field(default=2.0, ge=1.0, le=5.0)  # Boost for session results
    min_session_results: int = Field(default=0, ge=0)  # Minimum results from session
    fallback_to_global: bool = True  # Use global KB if session not enough


class PriorityRAGResponse(BaseModel):
    """RAG response with source distinction"""
    answer: str
    strategy: str
    language: str
    confidence: float

    # Separated sources
    session_sources: List[Dict[str, Any]] = Field(default_factory=list)
    global_sources: List[Dict[str, Any]] = Field(default_factory=list)

    # Combined sources (for backward compatibility)
    sources: List[Dict[str, Any]] = Field(default_factory=list)

    # Query analysis
    query_analysis: Dict[str, Any] = Field(default_factory=dict)

    # Source usage info
    used_session_docs: bool = False
    session_doc_count: int = 0
