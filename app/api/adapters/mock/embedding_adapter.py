"""
Mock Embedding Adapter
Mock implementation for testing and development.
"""
from typing import Optional, List
import asyncio
import hashlib
import random

from ...ports.embedding_port import (
    EmbeddingPort,
    EmbeddingConfig,
    EmbeddingResult,
    BatchEmbeddingResult
)


class MockEmbeddingAdapter(EmbeddingPort):
    """
    Mock embedding adapter for testing and development.

    Generates deterministic embeddings based on text hash.
    """

    def __init__(
        self,
        dimensions: int = 1536,
        model: str = "mock-embedding",
        simulate_delay: bool = True,
        delay_ms: int = 50
    ):
        self._dimensions = dimensions
        self.model = model
        self.simulate_delay = simulate_delay
        self.delay_ms = delay_ms
        self._call_count = 0

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions"""
        return self._dimensions

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate deterministic embedding from text"""
        # Use text hash to seed random generator for reproducibility
        text_hash = hashlib.md5(text.encode()).hexdigest()
        seed = int(text_hash[:8], 16)
        rng = random.Random(seed)

        # Generate normalized embedding
        embedding = [rng.gauss(0, 1) for _ in range(self._dimensions)]

        # Normalize to unit vector
        norm = sum(x * x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]

        return embedding

    async def embed_text(
        self,
        text: str,
        config: Optional[EmbeddingConfig] = None
    ) -> EmbeddingResult:
        """Generate mock embedding"""
        self._call_count += 1

        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000)

        return EmbeddingResult(
            text=text,
            embedding=self._generate_embedding(text),
            token_count=len(text) // 4
        )

    async def embed_texts(
        self,
        texts: List[str],
        config: Optional[EmbeddingConfig] = None
    ) -> BatchEmbeddingResult:
        """Generate mock embeddings for multiple texts"""
        self._call_count += len(texts)

        if self.simulate_delay:
            await asyncio.sleep(self.delay_ms / 1000 * len(texts) / 10)

        results = []
        total_tokens = 0

        for text in texts:
            token_count = len(text) // 4
            total_tokens += token_count

            results.append(EmbeddingResult(
                text=text,
                embedding=self._generate_embedding(text),
                token_count=token_count
            ))

        return BatchEmbeddingResult(
            embeddings=results,
            total_tokens=total_tokens,
            model=self.model
        )

    async def get_available_models(self) -> List[str]:
        """Return mock models"""
        return ["mock-embedding", "mock-embedding-large"]

    async def health_check(self) -> bool:
        """Always healthy"""
        return True

    # ==================== Test Helpers ====================

    def get_call_count(self) -> int:
        """Get number of calls made"""
        return self._call_count

    def reset(self) -> None:
        """Reset mock state"""
        self._call_count = 0

    def compute_similarity_for_texts(self, text1: str, text2: str) -> float:
        """Compute similarity between two texts using mock embeddings"""
        emb1 = self._generate_embedding(text1)
        emb2 = self._generate_embedding(text2)
        return self.compute_similarity(emb1, emb2)
