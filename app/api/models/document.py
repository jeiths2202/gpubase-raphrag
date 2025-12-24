"""
Document-related Pydantic models
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Document processing status"""
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class EmbeddingStatus(str, Enum):
    """Embedding generation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentBase(BaseModel):
    """Base document model"""
    filename: str
    original_name: str
    file_size: int = Field(ge=0, description="File size in bytes")
    mime_type: str = "application/pdf"


class DocumentCreate(BaseModel):
    """Document upload request"""
    name: Optional[str] = Field(default=None, description="Display name")
    language: str = Field(default="auto", description="Document language")
    tags: list[str] = Field(default_factory=list, description="Tags")


class DocumentStats(BaseModel):
    """Document statistics"""
    pages: int = 0
    chunks_count: int = 0
    entities_count: int = 0
    avg_chunk_size: float = 0.0
    embedding_dimension: int = 4096


class ProcessingInfo(BaseModel):
    """Document processing information"""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time_seconds: Optional[int] = None


class DocumentListItem(BaseModel):
    """Document list item"""
    id: str
    filename: str
    original_name: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    chunks_count: int = 0
    entities_count: int = 0
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    language: str = "auto"
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentListItem):
    """Document detail model"""
    tags: list[str] = Field(default_factory=list)
    stats: Optional[DocumentStats] = None
    processing_info: Optional[ProcessingInfo] = None


class DocumentUploadResponse(BaseModel):
    """Document upload response"""
    document_id: str
    filename: str
    status: DocumentStatus = DocumentStatus.PROCESSING
    message: str
    task_id: str


class DocumentDeleteResponse(BaseModel):
    """Document deletion response"""
    document_id: str
    message: str
    deleted_chunks: int = 0
    deleted_entities: int = 0


class ChunkInfo(BaseModel):
    """Chunk information"""
    id: str
    index: int
    content: str
    content_length: int
    has_embedding: bool = False
    entities: list[str] = Field(default_factory=list)


class UploadStep(BaseModel):
    """Upload processing step"""
    name: str
    status: str
    progress: Optional[int] = None


class UploadProgress(BaseModel):
    """Upload progress information"""
    current_step: str
    steps: list[UploadStep]
    overall_progress: int = Field(ge=0, le=100)


class UploadStatusResponse(BaseModel):
    """Upload status response"""
    task_id: str
    document_id: str
    status: DocumentStatus
    progress: UploadProgress
    started_at: datetime
    estimated_completion: Optional[datetime] = None
