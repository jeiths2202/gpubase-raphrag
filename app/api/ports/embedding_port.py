"""
Embedding Port Interface
Abstract interface for text embedding operations.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class EmbeddingConfig:
    """Embedding configuration"""
    model: str = "text-embedding-3-small"
    dimensions: int = 4096  # Match NV-EmbedQA-Mistral-7B v2 output
    batch_size: int = 100
    timeout: int = 60

    # Provider-specific settings
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResult:
    """Embedding result for a single text"""
    text: str
    embedding: List[float]
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchEmbeddingResult:
    """Batch embedding result"""
    embeddings: List[EmbeddingResult]
    total_tokens: int = 0
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class EmbeddingPort(ABC):
    """
    Abstract interface for text embedding operations.

    All embedding implementations must implement this interface.
    This allows swapping between different providers (OpenAI, Cohere, local models, etc.)
    without changing the application logic.
    """

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the embedding dimensions"""
        pass

    @abstractmethod
    async def embed_text(
        self,
        text: str,
        config: Optional[EmbeddingConfig] = None
    ) -> EmbeddingResult:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed
            config: Optional configuration override

        Returns:
            EmbeddingResult with vector
        """
        pass

    @abstractmethod
    async def embed_texts(
        self,
        texts: List[str],
        config: Optional[EmbeddingConfig] = None
    ) -> BatchEmbeddingResult:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            config: Optional configuration override

        Returns:
            BatchEmbeddingResult with all embeddings
        """
        pass

    async def embed_query(
        self,
        query: str,
        config: Optional[EmbeddingConfig] = None
    ) -> EmbeddingResult:
        """
        Generate embedding for a search query.
        Some providers use different models for queries vs documents.

        Args:
            query: Query text to embed
            config: Optional configuration

        Returns:
            EmbeddingResult with query vector
        """
        # Default implementation uses same embedding
        return await self.embed_text(query, config)

    async def embed_documents(
        self,
        documents: List[str],
        config: Optional[EmbeddingConfig] = None
    ) -> BatchEmbeddingResult:
        """
        Generate embeddings for documents (for indexing).
        Some providers use different models for queries vs documents.

        Args:
            documents: Document texts to embed
            config: Optional configuration

        Returns:
            BatchEmbeddingResult with document vectors
        """
        # Default implementation uses same embedding
        return await self.embed_texts(documents, config)

    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """
        Get list of available embedding models.

        Returns:
            List of model identifiers
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the embedding service is healthy.

        Returns:
            True if service is healthy
        """
        pass

    def compute_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float]
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Similarity score (0-1)
        """
        import math

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = math.sqrt(sum(a * a for a in embedding1))
        norm2 = math.sqrt(sum(b * b for b in embedding2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)
