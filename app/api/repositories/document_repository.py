"""
Document Repository Interface
Repository for document management operations.
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from .base import BaseRepository, Entity, EntityId, BulkOperationsMixin


class DocumentStatus(str, Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ChunkEntity:
    """Document chunk entity"""
    chunk_id: str
    document_id: str
    content: str
    chunk_index: int
    token_count: int = 0
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class DocumentEntity(Entity):
    """Document entity"""
    name: str = ""
    content: str = ""
    mime_type: str = "text/plain"
    file_size: int = 0
    status: DocumentStatus = DocumentStatus.PENDING

    # Processing results
    chunk_count: int = 0
    total_tokens: int = 0

    # Metadata
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # External source info
    is_external: bool = False
    external_source: Optional[str] = None
    external_url: Optional[str] = None

    # Relationships
    chunks: List[ChunkEntity] = field(default_factory=list)


class DocumentRepository(BaseRepository[DocumentEntity], BulkOperationsMixin[DocumentEntity]):
    """
    Repository interface for document operations.

    Implementations handle document storage, retrieval, and chunk management.
    """

    # ==================== Document Operations ====================

    @abstractmethod
    async def get_by_name(self, name: str, user_id: Optional[str] = None) -> Optional[DocumentEntity]:
        """Get document by name"""
        pass

    @abstractmethod
    async def get_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> List[DocumentEntity]:
        """Get all documents in a project"""
        pass

    @abstractmethod
    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        status: Optional[DocumentStatus] = None
    ) -> List[DocumentEntity]:
        """Get all documents owned by a user"""
        pass

    @abstractmethod
    async def get_by_status(
        self,
        status: DocumentStatus,
        limit: int = 100
    ) -> List[DocumentEntity]:
        """Get documents by processing status"""
        pass

    @abstractmethod
    async def search_by_tags(
        self,
        tags: List[str],
        match_all: bool = False
    ) -> List[DocumentEntity]:
        """Search documents by tags"""
        pass

    @abstractmethod
    async def update_status(
        self,
        document_id: EntityId,
        status: DocumentStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """Update document processing status"""
        pass

    # ==================== Chunk Operations ====================

    @abstractmethod
    async def add_chunks(
        self,
        document_id: EntityId,
        chunks: List[ChunkEntity]
    ) -> List[ChunkEntity]:
        """Add chunks to a document"""
        pass

    @abstractmethod
    async def get_chunks(
        self,
        document_id: EntityId,
        skip: int = 0,
        limit: int = 100
    ) -> List[ChunkEntity]:
        """Get document chunks"""
        pass

    @abstractmethod
    async def get_chunk_by_id(self, chunk_id: str) -> Optional[ChunkEntity]:
        """Get a specific chunk"""
        pass

    @abstractmethod
    async def delete_chunks(self, document_id: EntityId) -> int:
        """Delete all chunks for a document"""
        pass

    @abstractmethod
    async def update_chunk_embedding(
        self,
        chunk_id: str,
        embedding: List[float]
    ) -> bool:
        """Update chunk embedding vector"""
        pass

    # ==================== Search Operations ====================

    @abstractmethod
    async def search_content(
        self,
        query: str,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 10
    ) -> List[DocumentEntity]:
        """Full-text search in document content"""
        pass

    @abstractmethod
    async def get_recent(
        self,
        user_id: Optional[str] = None,
        days: int = 7,
        limit: int = 10
    ) -> List[DocumentEntity]:
        """Get recently modified documents"""
        pass

    # ==================== Statistics ====================

    @abstractmethod
    async def get_stats(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get document statistics"""
        pass
