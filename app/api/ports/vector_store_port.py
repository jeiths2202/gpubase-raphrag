"""
Vector Store Port Interface
Abstract interface for vector database operations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum


class DistanceMetric(str, Enum):
    """Distance metric for similarity search"""
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    DOT_PRODUCT = "dot_product"


@dataclass
class VectorStoreConfig:
    """Vector store configuration"""
    collection_name: str = "default"
    dimensions: int = 4096  # Match NV-EmbedQA-Mistral-7B v2 output
    distance_metric: DistanceMetric = DistanceMetric.COSINE
    index_type: str = "hnsw"

    # Connection settings
    host: Optional[str] = None
    port: Optional[int] = None
    api_key: Optional[str] = None

    # Index parameters
    ef_construction: int = 200
    m: int = 16

    # Provider-specific settings
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorDocument:
    """Document with vector embedding"""
    id: str
    embedding: List[float]
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Search result from vector store"""
    id: str
    score: float
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Source document reference
    document_id: Optional[str] = None
    chunk_index: Optional[int] = None


@dataclass
class SearchFilter:
    """Filter for vector search"""
    field: str
    operator: str  # eq, ne, gt, gte, lt, lte, in, contains
    value: Any


class VectorStorePort(ABC):
    """
    Abstract interface for vector database operations.

    All vector store implementations must implement this interface.
    This allows swapping between different providers (Pinecone, Weaviate, Milvus, Qdrant, etc.)
    without changing the application logic.
    """

    @abstractmethod
    async def create_collection(
        self,
        name: str,
        dimensions: int,
        distance_metric: DistanceMetric = DistanceMetric.COSINE,
        config: Optional[VectorStoreConfig] = None
    ) -> bool:
        """
        Create a new vector collection.

        Args:
            name: Collection name
            dimensions: Vector dimensions
            distance_metric: Distance metric for similarity
            config: Optional configuration

        Returns:
            True if created successfully
        """
        pass

    @abstractmethod
    async def delete_collection(self, name: str) -> bool:
        """
        Delete a vector collection.

        Args:
            name: Collection name

        Returns:
            True if deleted successfully
        """
        pass

    @abstractmethod
    async def list_collections(self) -> List[str]:
        """
        List all collections.

        Returns:
            List of collection names
        """
        pass

    @abstractmethod
    async def collection_exists(self, name: str) -> bool:
        """
        Check if collection exists.

        Args:
            name: Collection name

        Returns:
            True if exists
        """
        pass

    @abstractmethod
    async def insert(
        self,
        collection: str,
        documents: List[VectorDocument]
    ) -> List[str]:
        """
        Insert documents into collection.

        Args:
            collection: Collection name
            documents: Documents to insert

        Returns:
            List of inserted document IDs
        """
        pass

    @abstractmethod
    async def upsert(
        self,
        collection: str,
        documents: List[VectorDocument]
    ) -> List[str]:
        """
        Insert or update documents.

        Args:
            collection: Collection name
            documents: Documents to upsert

        Returns:
            List of upserted document IDs
        """
        pass

    @abstractmethod
    async def delete(
        self,
        collection: str,
        ids: List[str]
    ) -> int:
        """
        Delete documents by ID.

        Args:
            collection: Collection name
            ids: Document IDs to delete

        Returns:
            Number of deleted documents
        """
        pass

    @abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 10,
        filters: Optional[List[SearchFilter]] = None,
        include_metadata: bool = True
    ) -> List[SearchResult]:
        """
        Search for similar vectors.

        Args:
            collection: Collection name
            query_vector: Query embedding vector
            top_k: Number of results to return
            filters: Optional metadata filters
            include_metadata: Whether to include metadata

        Returns:
            List of search results
        """
        pass

    @abstractmethod
    async def search_by_id(
        self,
        collection: str,
        document_id: str,
        top_k: int = 10,
        filters: Optional[List[SearchFilter]] = None
    ) -> List[SearchResult]:
        """
        Find similar documents to a given document.

        Args:
            collection: Collection name
            document_id: Source document ID
            top_k: Number of results
            filters: Optional filters

        Returns:
            List of similar documents
        """
        pass

    @abstractmethod
    async def get_by_ids(
        self,
        collection: str,
        ids: List[str]
    ) -> List[VectorDocument]:
        """
        Get documents by IDs.

        Args:
            collection: Collection name
            ids: Document IDs

        Returns:
            List of documents
        """
        pass

    async def hybrid_search(
        self,
        collection: str,
        query_vector: List[float],
        query_text: str,
        top_k: int = 10,
        alpha: float = 0.5,
        filters: Optional[List[SearchFilter]] = None
    ) -> List[SearchResult]:
        """
        Hybrid search combining vector and keyword search.

        Args:
            collection: Collection name
            query_vector: Query embedding
            query_text: Query text for keyword search
            top_k: Number of results
            alpha: Weight for vector search (1-alpha for keyword)
            filters: Optional filters

        Returns:
            List of search results
        """
        raise NotImplementedError("Hybrid search not supported by this provider")

    @abstractmethod
    async def count(
        self,
        collection: str,
        filters: Optional[List[SearchFilter]] = None
    ) -> int:
        """
        Count documents in collection.

        Args:
            collection: Collection name
            filters: Optional filters

        Returns:
            Document count
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the vector store is healthy.

        Returns:
            True if service is healthy
        """
        pass

    async def get_stats(self, collection: str) -> Dict[str, Any]:
        """
        Get collection statistics.

        Args:
            collection: Collection name

        Returns:
            Statistics dictionary
        """
        return {
            "count": await self.count(collection)
        }
