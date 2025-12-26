"""
External Connection Models
Models for managing user's external resource connections (OneNote, GitHub, Google Drive, Notion, Confluence)
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ExternalResourceType(str, Enum):
    """Supported external resource types"""
    ONENOTE = "onenote"
    GITHUB = "github"
    GOOGLE_DRIVE = "google_drive"
    NOTION = "notion"
    CONFLUENCE = "confluence"


class ConnectionStatus(str, Enum):
    """Connection status"""
    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"
    EXPIRED = "expired"


class SyncStatus(str, Enum):
    """Document sync status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AuthType(str, Enum):
    """Authentication type"""
    OAUTH2 = "oauth2"
    API_TOKEN = "api_token"
    PAT = "personal_access_token"


class ExternalConnection(BaseModel):
    """
    Represents a user's connection to an external resource.
    Stores OAuth tokens and connection metadata.
    """
    id: str = Field(..., description="Connection ID")
    user_id: str = Field(..., description="User ID who owns this connection")
    resource_type: ExternalResourceType = Field(..., description="Type of external resource")
    status: ConnectionStatus = Field(default=ConnectionStatus.NOT_CONNECTED)
    auth_type: AuthType = Field(default=AuthType.OAUTH2)

    # OAuth tokens (encrypted in storage)
    access_token: Optional[str] = Field(default=None, description="Encrypted access token")
    refresh_token: Optional[str] = Field(default=None, description="Encrypted refresh token")
    token_expires_at: Optional[datetime] = Field(default=None)

    # API Token (for non-OAuth resources)
    api_token: Optional[str] = Field(default=None, description="Encrypted API token")

    # Resource-specific config
    resource_config: Dict[str, Any] = Field(default_factory=dict)

    # Sync information
    last_sync_at: Optional[datetime] = Field(default=None)
    next_sync_at: Optional[datetime] = Field(default=None)
    sync_status: SyncStatus = Field(default=SyncStatus.PENDING)
    sync_error: Optional[str] = Field(default=None)

    # Statistics
    document_count: int = Field(default=0)
    chunk_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class ExternalConnectionCreate(BaseModel):
    """Request to create/initiate external connection"""
    resource_type: ExternalResourceType
    # Optional for API token auth
    api_token: Optional[str] = None
    # Resource-specific config
    config: Dict[str, Any] = Field(default_factory=dict)


class ExternalConnectionResponse(BaseModel):
    """Connection info response (no tokens)"""
    id: str
    user_id: str
    resource_type: ExternalResourceType
    status: ConnectionStatus
    auth_type: AuthType
    last_sync_at: Optional[datetime] = None
    sync_status: SyncStatus
    document_count: int = 0
    chunk_count: int = 0
    created_at: datetime
    error_message: Optional[str] = None


class OAuthCallbackRequest(BaseModel):
    """OAuth callback request"""
    code: str
    state: str
    resource_type: ExternalResourceType


class OAuthInitResponse(BaseModel):
    """OAuth initiation response"""
    auth_url: str
    state: str
    resource_type: ExternalResourceType


# ================== External Document Models ==================

class ExternalDocumentStatus(str, Enum):
    """Document processing status"""
    DISCOVERED = "discovered"
    FETCHING = "fetching"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class ExternalDocument(BaseModel):
    """
    Normalized document from external resource.
    Common schema for all external sources.
    """
    id: str = Field(..., description="Internal document ID")
    user_id: str = Field(..., description="User ID who owns this document")
    connection_id: str = Field(..., description="Connection this document belongs to")

    # Source identification
    source: ExternalResourceType
    external_id: str = Field(..., description="Original ID from external source")
    external_url: Optional[str] = Field(default=None, description="Link to original document")

    # Document metadata
    title: str
    path: Optional[str] = Field(default=None, description="Path in external source (folder/notebook)")
    mime_type: Optional[str] = None
    file_size: Optional[int] = None

    # Content (normalized)
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    text_content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Processing status
    status: ExternalDocumentStatus = Field(default=ExternalDocumentStatus.DISCOVERED)
    error_message: Optional[str] = None

    # Sync tracking
    external_modified_at: Optional[datetime] = Field(default=None, description="Last modified in external source")
    last_synced_at: Optional[datetime] = None
    content_hash: Optional[str] = Field(default=None, description="Hash for change detection")

    # Chunking info
    chunk_count: int = 0

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class ExternalChunk(BaseModel):
    """
    Chunk from external document for vector storage.
    User-scoped, not mixed with global knowledge.
    """
    id: str
    user_id: str
    document_id: str
    connection_id: str
    source: ExternalResourceType

    # Content
    content: str
    index: int

    # Embedding
    embedding: Optional[List[float]] = None

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_name: str = ""
    source_url: Optional[str] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None

    # Flags
    is_table: bool = False
    is_code: bool = False

    class Config:
        use_enum_values = True


class ExternalSearchResult(BaseModel):
    """Search result from external resource vector store"""
    chunk_id: str
    document_id: str
    user_id: str
    connection_id: str
    source: ExternalResourceType

    content: str
    score: float

    source_name: str
    source_url: Optional[str] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ================== API Request/Response Models ==================

class ConnectionListResponse(BaseModel):
    """List of user's external connections"""
    connections: List[ExternalConnectionResponse]
    total: int


class SyncRequest(BaseModel):
    """Request to sync a connection"""
    full_sync: bool = Field(default=False, description="Force full sync instead of incremental")


class SyncResponse(BaseModel):
    """Sync operation response"""
    connection_id: str
    status: SyncStatus
    documents_synced: int = 0
    documents_added: int = 0
    documents_updated: int = 0
    documents_deleted: int = 0
    message: str = ""


class ExternalDocumentListResponse(BaseModel):
    """List of documents from external connection"""
    documents: List[Dict[str, Any]]
    total: int
    connection_id: str
    resource_type: ExternalResourceType


class ExternalResourceConfig(BaseModel):
    """Configuration for each external resource type"""
    resource_type: ExternalResourceType
    display_name: str
    icon: str
    auth_type: AuthType
    description: str
    supported_formats: List[str] = Field(default_factory=list)


# Resource configurations
EXTERNAL_RESOURCE_CONFIGS = {
    ExternalResourceType.ONENOTE: ExternalResourceConfig(
        resource_type=ExternalResourceType.ONENOTE,
        display_name="OneNote",
        icon="📔",
        auth_type=AuthType.OAUTH2,
        description="Microsoft OneNote 노트북 연결",
        supported_formats=["notebook", "section", "page"]
    ),
    ExternalResourceType.GITHUB: ExternalResourceConfig(
        resource_type=ExternalResourceType.GITHUB,
        display_name="GitHub",
        icon="🐙",
        auth_type=AuthType.OAUTH2,
        description="GitHub 저장소 문서 연결",
        supported_formats=["md", "txt", "rst", "adoc"]
    ),
    ExternalResourceType.GOOGLE_DRIVE: ExternalResourceConfig(
        resource_type=ExternalResourceType.GOOGLE_DRIVE,
        display_name="Google Drive",
        icon="📁",
        auth_type=AuthType.OAUTH2,
        description="Google Drive 문서 연결",
        supported_formats=["docs", "sheets", "pdf", "txt"]
    ),
    ExternalResourceType.NOTION: ExternalResourceConfig(
        resource_type=ExternalResourceType.NOTION,
        display_name="Notion",
        icon="📝",
        auth_type=AuthType.OAUTH2,
        description="Notion 페이지 및 데이터베이스 연결",
        supported_formats=["page", "database"]
    ),
    ExternalResourceType.CONFLUENCE: ExternalResourceConfig(
        resource_type=ExternalResourceType.CONFLUENCE,
        display_name="Confluence",
        icon="📚",
        auth_type=AuthType.API_TOKEN,
        description="Atlassian Confluence 페이지 연결",
        supported_formats=["page", "blog", "attachment"]
    )
}


class PriorityRAGRequest(BaseModel):
    """Request for priority-based RAG with external resources"""
    query: str
    user_id: str
    session_id: Optional[str] = None

    # RAG options
    use_external_resources: bool = Field(default=True, description="Include external resources in search")
    use_session_docs: bool = Field(default=True, description="Include session documents")
    use_global_kb: bool = Field(default=True, description="Include global knowledge base")

    # Weights for priority
    external_weight: float = Field(default=2.5, ge=1.0, le=5.0)
    session_weight: float = Field(default=2.0, ge=1.0, le=5.0)

    # Search options
    top_k: int = Field(default=5, ge=1, le=20)
    min_score: float = Field(default=0.3, ge=0.0, le=1.0)

    # Response options
    language: str = Field(default="auto")
    include_sources: bool = Field(default=True)
