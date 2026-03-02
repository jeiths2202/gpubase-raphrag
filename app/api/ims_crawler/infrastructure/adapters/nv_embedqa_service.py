"""
NV-EmbedQA Embedding Service - Generate 1024-dim vectors for semantic search

Wraps existing HybridRAG embedding infrastructure for IMS issues.
"""

from typing import List
from ..ports.embedding_service_port import EmbeddingServicePort
from ....ports.embedding_port import EmbeddingPort


class NvEmbedQAService(EmbeddingServicePort):
    """
    NV-EmbedQA embedding service for IMS issues.

    Generates 1024-dimensional vectors using BGE-M3.
    """

    def __init__(self, embedding_adapter: EmbeddingPort):
        """
        Initialize service with embedding adapter.

        Args:
            embedding_adapter: HybridRAG embedding adapter (langchain-based)
        """
        self.embedding = embedding_adapter

    async def embed_text(self, text: str) -> List[float]:
        """
        Generate vector embedding for single text.

        Args:
            text: Text to embed (issue title + description)

        Returns:
            1024-dimensional vector

        Example:
            >>> service = NvEmbedQAService(embedding_adapter)
            >>> vector = await service.embed_text("Critical bug in authentication")
            >>> len(vector)
            1024
        """
        result = await self.embedding.embed_texts([text])
        # BatchEmbeddingResult.embeddings is List[EmbeddingResult]
        # EmbeddingResult.embedding is List[float]
        return result.embeddings[0].embedding if result.embeddings else []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of 1024-dimensional vectors

        Example:
            >>> texts = ["Bug in login", "Feature request for dashboard"]
            >>> vectors = await service.embed_batch(texts)
            >>> len(vectors)
            2
            >>> all(len(v) == 1024 for v in vectors)
            True
        """
        result = await self.embedding.embed_texts(texts)
        return [emb.embedding for emb in result.embeddings]
