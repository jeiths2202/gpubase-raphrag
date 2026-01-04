"""
NV-EmbedQA Embedding Service - Generate 4096-dim vectors for semantic search

Wraps existing HybridRAG embedding infrastructure for IMS issues.
"""

from typing import List
from ..ports.embedding_service_port import EmbeddingServicePort
from ....ports.embedding_port import EmbeddingPort


class NvEmbedQAService(EmbeddingServicePort):
    """
    NV-EmbedQA embedding service for IMS issues.

    Generates 4096-dimensional vectors using NVIDIA NV-EmbedQA-Mistral-7B v2.
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
            4096-dimensional vector

        Example:
            >>> service = NvEmbedQAService(embedding_adapter)
            >>> vector = await service.embed_text("Critical bug in authentication")
            >>> len(vector)
            4096
        """
        vectors = await self.embedding.embed_texts([text])
        return vectors[0] if vectors else []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed

        Returns:
            List of 4096-dimensional vectors

        Example:
            >>> texts = ["Bug in login", "Feature request for dashboard"]
            >>> vectors = await service.embed_batch(texts)
            >>> len(vectors)
            2
            >>> all(len(v) == 4096 for v in vectors)
            True
        """
        return await self.embedding.embed_texts(texts)
