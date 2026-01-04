"""Embedding Service Port"""
from abc import ABC, abstractmethod
from typing import List

class EmbeddingServicePort(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Generate vector embedding for text using NVIDIA NV-EmbedQA"""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch"""
        pass
