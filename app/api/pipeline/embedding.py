"""
Embedding Stage
Handles text-to-vector conversion for RAG pipeline.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Protocol
import logging
import time

from ..core.tracing import get_trace_context_from_request
from ..core.trace_context import SpanType

logger = logging.getLogger(__name__)


# ==================== Port (Interface) ====================

class EmbeddingPort(Protocol):
    """
    Port for embedding service.

    Implementations must provide:
    - embed: Single text embedding
    - embed_batch: Batch text embedding
    """

    async def embed(self, text: str) -> List[float]:
        """Embed single text"""
        ...

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts"""
        ...


# ==================== Configuration ====================

def _get_embedding_defaults() -> dict:
    """Get embedding defaults from config settings."""
    try:
        from ..core.config import get_api_settings
        settings = get_api_settings()
        return {
            "model_name": settings.EMBEDDING_MODEL_NAME,
            "dimension": settings.EMBEDDING_DIMENSION,
            "batch_size": settings.EMBEDDING_BATCH_SIZE,
            "max_text_length": settings.EMBEDDING_MAX_TEXT_LENGTH,
            "timeout_seconds": settings.EMBEDDING_TIMEOUT_SECONDS,
        }
    except Exception:
        # Fallback to hardcoded defaults if config not available
        return {
            "model_name": "nvidia/nv-embedqa-mistral-7b-v2",
            "dimension": 4096,
            "batch_size": 32,
            "max_text_length": 8192,
            "timeout_seconds": 30.0,
        }


@dataclass
class EmbeddingConfig:
    """Configuration for embedding stage. Defaults loaded from environment variables."""
    model_name: str = None
    dimension: int = None
    batch_size: int = None
    max_text_length: int = None
    normalize: bool = True
    cache_enabled: bool = True
    timeout_seconds: float = None

    def __post_init__(self):
        """Load defaults from environment config."""
        defaults = _get_embedding_defaults()
        if self.model_name is None:
            self.model_name = defaults["model_name"]
        if self.dimension is None:
            self.dimension = defaults["dimension"]
        if self.batch_size is None:
            self.batch_size = defaults["batch_size"]
        if self.max_text_length is None:
            self.max_text_length = defaults["max_text_length"]
        if self.timeout_seconds is None:
            self.timeout_seconds = defaults["timeout_seconds"]


# ==================== Result ====================

@dataclass
class EmbeddingResult:
    """Result from embedding stage"""
    embeddings: List[List[float]]
    texts: List[str]
    dimension: int
    model: str
    duration_ms: float = 0.0
    cached_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.embeddings)

    def get_embedding(self, index: int) -> Optional[List[float]]:
        if 0 <= index < len(self.embeddings):
            return self.embeddings[index]
        return None


# ==================== Stage Implementation ====================

class EmbeddingStage:
    """
    Embedding stage of the RAG pipeline.

    Responsibilities:
    1. Text preprocessing (chunking, truncation)
    2. Vector generation via embedding service
    3. Caching for repeated texts
    4. Batch processing for efficiency

    This stage is completely independent of:
    - Retrieval logic
    - Generation/LLM logic
    - Storage concerns

    Example:
        stage = EmbeddingStage(embedder, config)

        # Single text
        result = await stage.embed_text("What is RAG?")

        # Batch processing
        result = await stage.embed_batch([
            "Document 1 content",
            "Document 2 content"
        ])
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        config: Optional[EmbeddingConfig] = None
    ):
        self.embedder = embedder
        self.config = config or EmbeddingConfig()
        self._cache: Dict[str, List[float]] = {}

    async def embed_text(self, text: str) -> EmbeddingResult:
        """
        Embed a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with single embedding
        """
        return await self.embed_batch([text])

    async def embed_batch(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> EmbeddingResult:
        """
        Embed multiple texts.

        Args:
            texts: List of texts to embed
            use_cache: Whether to use caching

        Returns:
            EmbeddingResult with embeddings
        """
        # Get trace context for E2E tracing
        trace_ctx = get_trace_context_from_request()

        # Prepare span metadata
        span_metadata = {
            "model": self.config.model_name,
            "dimension": self.config.dimension,
            "input_count": len(texts),
            "input_length": sum(len(t) for t in texts)
        }

        # Wrap in trace span if available
        if trace_ctx:
            with trace_ctx.create_span("embedding", SpanType.EMBEDDING, metadata=span_metadata):
                return await self._execute_embedding(texts, use_cache)
        else:
            return await self._execute_embedding(texts, use_cache)

    async def _execute_embedding(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> EmbeddingResult:
        """Execute embedding with timing"""
        start_time = time.time()

        # Preprocess texts
        processed_texts = [
            self._preprocess(text) for text in texts
        ]

        # Check cache
        cached_count = 0
        embeddings: List[Optional[List[float]]] = [None] * len(texts)
        texts_to_embed: List[tuple[int, str]] = []

        if use_cache and self.config.cache_enabled:
            for i, text in enumerate(processed_texts):
                if text in self._cache:
                    embeddings[i] = self._cache[text]
                    cached_count += 1
                else:
                    texts_to_embed.append((i, text))
        else:
            texts_to_embed = list(enumerate(processed_texts))

        # Embed uncached texts in batches
        if texts_to_embed:
            await self._embed_uncached(texts_to_embed, embeddings)

        duration = (time.time() - start_time) * 1000

        return EmbeddingResult(
            embeddings=[e for e in embeddings if e is not None],
            texts=texts,
            dimension=self.config.dimension,
            model=self.config.model_name,
            duration_ms=duration,
            cached_count=cached_count
        )

    async def _embed_uncached(
        self,
        texts_to_embed: List[tuple[int, str]],
        embeddings: List[Optional[List[float]]]
    ) -> None:
        """Embed uncached texts in batches"""
        batch_size = self.config.batch_size

        for i in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[i:i + batch_size]
            indices = [item[0] for item in batch]
            batch_texts = [item[1] for item in batch]

            try:
                batch_embeddings = await self.embedder.embed_batch(batch_texts)

                # Store results
                for j, (idx, text) in enumerate(batch):
                    embedding = batch_embeddings[j]
                    embeddings[idx] = embedding

                    # Cache the result
                    if self.config.cache_enabled:
                        self._cache[text] = embedding

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Try individual embedding as fallback
                for idx, text in batch:
                    try:
                        embedding = await self.embedder.embed(text)
                        embeddings[idx] = embedding
                        if self.config.cache_enabled:
                            self._cache[text] = embedding
                    except Exception as e2:
                        logger.error(f"Individual embedding failed: {e2}")

    def _preprocess(self, text: str) -> str:
        """Preprocess text before embedding"""
        # Truncate if too long
        if len(text) > self.config.max_text_length:
            text = text[:self.config.max_text_length]

        # Clean whitespace
        text = " ".join(text.split())

        return text

    def clear_cache(self) -> int:
        """Clear embedding cache, return cleared count"""
        count = len(self._cache)
        self._cache.clear()
        return count

    @property
    def cache_size(self) -> int:
        """Get current cache size"""
        return len(self._cache)


# ==================== Specialized Embedding Stages ====================

class QueryEmbeddingStage(EmbeddingStage):
    """
    Embedding stage optimized for queries.

    Queries are typically short, so this stage:
    - Has smaller max text length
    - Uses query-specific preprocessing
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        config: Optional[EmbeddingConfig] = None
    ):
        query_config = config or EmbeddingConfig(
            max_text_length=512,
            cache_enabled=True
        )
        super().__init__(embedder, query_config)

    def _preprocess(self, text: str) -> str:
        """Query-specific preprocessing"""
        text = super()._preprocess(text)
        # Add query prefix if model supports it
        # (Some embedding models perform better with prefixes)
        return text


class DocumentEmbeddingStage(EmbeddingStage):
    """
    Embedding stage optimized for documents.

    Documents are typically longer, so this stage:
    - Has larger batch size
    - Handles chunking
    """

    def __init__(
        self,
        embedder: EmbeddingPort,
        config: Optional[EmbeddingConfig] = None
    ):
        doc_config = config or EmbeddingConfig(
            batch_size=16,  # Smaller batches for longer texts
            max_text_length=8192,
            cache_enabled=False  # Documents are usually unique
        )
        super().__init__(embedder, doc_config)

    async def embed_document(
        self,
        content: str,
        chunk_size: int = 1000,
        overlap: int = 200
    ) -> EmbeddingResult:
        """
        Embed a document with chunking.

        Args:
            content: Document content
            chunk_size: Size of each chunk
            overlap: Overlap between chunks

        Returns:
            EmbeddingResult with chunk embeddings
        """
        chunks = self._chunk_text(content, chunk_size, overlap)
        return await self.embed_batch(chunks, use_cache=False)

    def _chunk_text(
        self,
        text: str,
        chunk_size: int,
        overlap: int
    ) -> List[str]:
        """Split text into overlapping chunks"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind(". ")
                if last_period > chunk_size * 0.5:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1

            chunks.append(chunk.strip())
            start = end - overlap

        return chunks
