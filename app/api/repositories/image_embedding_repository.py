"""
Image Embedding Repository Interface

Abstract repository for multimodal image storage and embedding operations:
- Store extracted images from documents with embeddings
- Vector similarity search for image retrieval
- Document-scoped image management
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from .base import BaseRepository, Entity, EntityId


# ============================================
# Entity Definitions
# ============================================

@dataclass
class ImageEmbeddingEntity(Entity):
    """
    Image embedding entity for multimodal RAG.

    Stores extracted images from documents with their vector embeddings
    for similarity search during retrieval.
    """
    document_id: str = ""
    image_id: str = ""
    page_number: Optional[int] = None

    # Image binary data
    image_data: bytes = b""
    mime_type: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None

    # Position in document page (x, y, width, height)
    position: Optional[Dict[str, float]] = None

    # VLM-generated description
    description: Optional[str] = None
    alt_text: Optional[str] = None

    # Embedding vector (4096 dimensions for bakllava)
    embedding: Optional[List[float]] = None

    # Figure reference for matching images to text (e.g., "図1.1", "Figure 1-1")
    figure_reference: Optional[str] = None
    figure_caption: Optional[str] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageSearchResult:
    """Result from image similarity search."""
    id: str
    document_id: str
    image_id: str
    page_number: Optional[int]
    description: Optional[str]
    similarity: float
    # Optional: include image data for inline display
    image_data: Optional[bytes] = None
    mime_type: str = "image/png"


# ============================================
# Repository Interface
# ============================================

class ImageEmbeddingRepository(BaseRepository[ImageEmbeddingEntity]):
    """
    Repository interface for image embedding operations.

    Provides methods for:
    - Storing images with embeddings
    - Vector similarity search
    - Document-scoped image retrieval
    - Bulk operations for document processing
    """

    @abstractmethod
    async def store_image(
        self,
        entity: ImageEmbeddingEntity
    ) -> ImageEmbeddingEntity:
        """
        Store an image with its embedding.

        Args:
            entity: Image embedding entity to store

        Returns:
            Stored entity with generated ID
        """
        pass

    @abstractmethod
    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        min_similarity: float = 0.1,
        document_id: Optional[str] = None
    ) -> List[ImageSearchResult]:
        """
        Search for similar images using vector similarity.

        Args:
            query_embedding: Query vector (4096 dimensions)
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold (0-1)
            document_id: Optional filter by document

        Returns:
            List of matching images ordered by similarity
        """
        pass

    @abstractmethod
    async def get_by_document_id(
        self,
        document_id: str,
        include_data: bool = False
    ) -> List[ImageEmbeddingEntity]:
        """
        Get all images for a document.

        Args:
            document_id: Document identifier
            include_data: Whether to include image binary data

        Returns:
            List of images ordered by page number
        """
        pass

    @abstractmethod
    async def get_by_image_id(
        self,
        image_id: str,
        include_data: bool = True
    ) -> Optional[ImageEmbeddingEntity]:
        """
        Get an image by its image_id.

        Args:
            image_id: Unique image identifier
            include_data: Whether to include image binary data

        Returns:
            Image entity if found
        """
        pass

    @abstractmethod
    async def delete_by_document_id(
        self,
        document_id: str
    ) -> int:
        """
        Delete all images for a document.

        Args:
            document_id: Document identifier

        Returns:
            Number of deleted images
        """
        pass

    @abstractmethod
    async def bulk_store(
        self,
        entities: List[ImageEmbeddingEntity]
    ) -> List[ImageEmbeddingEntity]:
        """
        Store multiple images in batch.

        Args:
            entities: List of image entities to store

        Returns:
            List of stored entities with generated IDs
        """
        pass

    @abstractmethod
    async def update_embedding(
        self,
        image_id: str,
        embedding: List[float]
    ) -> bool:
        """
        Update the embedding for an existing image.

        Args:
            image_id: Image identifier
            embedding: New embedding vector

        Returns:
            True if updated, False if image not found
        """
        pass

    @abstractmethod
    async def update_description(
        self,
        image_id: str,
        description: str,
        alt_text: Optional[str] = None
    ) -> bool:
        """
        Update the VLM-generated description for an image.

        Args:
            image_id: Image identifier
            description: New description
            alt_text: Optional alt text

        Returns:
            True if updated, False if image not found
        """
        pass

    @abstractmethod
    async def count_by_document(
        self,
        document_id: str
    ) -> int:
        """
        Count images in a document.

        Args:
            document_id: Document identifier

        Returns:
            Number of images
        """
        pass
