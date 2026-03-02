"""
Parallel Embedding Executor Service
병렬 임베딩 실행 서비스

Handles concurrent embedding generation with retry logic and fault tolerance.
"""
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from ..models.adaptive_chunk import AdaptiveChunk, ChunkType
from ..ports.adaptive_embedding_port import ParallelEmbeddingExecutorPort
from ..ports.embedding_port import EmbeddingPort
from ..core.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingProgress:
    """Track embedding progress for a document."""
    pdf_id: str
    total_chunks: int
    completed_chunks: int = 0
    failed_chunks: int = 0
    in_progress: int = 0
    failed_chunk_ids: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    @property
    def progress_percentage(self) -> float:
        if self.total_chunks == 0:
            return 100.0
        return (self.completed_chunks / self.total_chunks) * 100

    @property
    def is_complete(self) -> bool:
        return self.completed_chunks + self.failed_chunks >= self.total_chunks

    def to_dict(self) -> Dict[str, Any]:
        elapsed = time.time() - self.start_time
        return {
            "pdf_id": self.pdf_id,
            "total_chunks": self.total_chunks,
            "completed_chunks": self.completed_chunks,
            "failed_chunks": self.failed_chunks,
            "in_progress": self.in_progress,
            "progress_percentage": round(self.progress_percentage, 1),
            "is_complete": self.is_complete,
            "elapsed_seconds": round(elapsed, 2),
            "failed_chunk_ids": self.failed_chunk_ids
        }


class ParallelEmbeddingExecutor(ParallelEmbeddingExecutorPort):
    """
    Executes embedding generation in parallel with retry logic.
    병렬 임베딩 생성 및 재시도 로직 구현
    """

    def __init__(
        self,
        embedding_service: EmbeddingPort,
        default_concurrency: int = None,
        default_timeout: float = None,
        default_retry_count: int = None,
        retry_base_delay: float = None,
        retry_max_delay: float = None
    ):
        """
        Initialize executor.

        Args:
            embedding_service: Service for generating embeddings
            default_concurrency: Default max concurrent requests (uses settings if None)
            default_timeout: Default timeout per chunk in seconds (uses settings if None)
            default_retry_count: Default retry attempts (uses settings if None)
            retry_base_delay: Base delay for exponential backoff (uses settings if None)
            retry_max_delay: Maximum delay between retries (uses settings if None)
        """
        self.embedding_service = embedding_service

        # Only load settings if any parameter needs default value
        needs_settings = any(p is None for p in [
            default_concurrency, default_timeout, default_retry_count,
            retry_base_delay, retry_max_delay
        ])

        if needs_settings:
            settings = get_settings()
            adaptive = settings.adaptive_embedding
            self.default_concurrency = default_concurrency if default_concurrency is not None else adaptive.embedding_concurrency
            self.default_timeout = default_timeout if default_timeout is not None else adaptive.embedding_timeout
            self.default_retry_count = default_retry_count if default_retry_count is not None else adaptive.embedding_retry_count
            self.retry_base_delay = retry_base_delay if retry_base_delay is not None else adaptive.retry_base_delay
            self.retry_max_delay = retry_max_delay if retry_max_delay is not None else adaptive.retry_max_delay
        else:
            self.default_concurrency = default_concurrency
            self.default_timeout = default_timeout
            self.default_retry_count = default_retry_count
            self.retry_base_delay = retry_base_delay
            self.retry_max_delay = retry_max_delay

        # Track progress per PDF
        self._progress: Dict[str, EmbeddingProgress] = {}

    async def embed_chunks(
        self,
        chunks: List[AdaptiveChunk],
        concurrency: int = None,
        timeout_per_chunk: float = None,
        on_progress: Optional[Callable[[EmbeddingProgress], None]] = None
    ) -> List[AdaptiveChunk]:
        """
        Generate embeddings for chunks in parallel.
        """
        if not chunks:
            return []

        concurrency = concurrency or self.default_concurrency
        timeout = timeout_per_chunk or self.default_timeout

        # Group by PDF ID
        pdf_chunks: Dict[str, List[AdaptiveChunk]] = {}
        for chunk in chunks:
            if chunk.pdf_id not in pdf_chunks:
                pdf_chunks[chunk.pdf_id] = []
            pdf_chunks[chunk.pdf_id].append(chunk)

        result_chunks = []

        for pdf_id, pdf_chunk_list in pdf_chunks.items():
            # Initialize progress tracking
            self._progress[pdf_id] = EmbeddingProgress(
                pdf_id=pdf_id,
                total_chunks=len(pdf_chunk_list)
            )

            # Create semaphore for concurrency control
            semaphore = asyncio.Semaphore(concurrency)

            # Create tasks for all chunks
            tasks = []
            for chunk in pdf_chunk_list:
                task = self._embed_chunk_with_semaphore(
                    chunk, semaphore, timeout, pdf_id, on_progress
                )
                tasks.append(task)

            # Execute all tasks
            logger.warning(f"GATHER_DEBUG: Starting asyncio.gather for {len(tasks)} tasks")
            embedded_chunks = await asyncio.gather(*tasks, return_exceptions=True)
            logger.warning(f"GATHER_DEBUG: asyncio.gather returned, processing {len(embedded_chunks)} results")

            # Process results
            for i, result in enumerate(embedded_chunks):
                # Log progress every 500 items
                if i > 0 and i % 500 == 0:
                    logger.warning(f"GATHER_DEBUG: Processed {i}/{len(embedded_chunks)} results")
                if isinstance(result, Exception):
                    logger.error(f"Chunk embedding failed: {result}")
                    # Keep original chunk without embedding
                    result_chunks.append(pdf_chunk_list[i])
                elif result is not None:
                    result_chunks.append(result)
                else:
                    result_chunks.append(pdf_chunk_list[i])

            # Log completion
            progress = self._progress[pdf_id]
            logger.warning(f"GATHER_DEBUG: All results processed, result_chunks length={len(result_chunks)}")
            logger.info(
                f"Embedding completed for {pdf_id}: "
                f"{progress.completed_chunks}/{progress.total_chunks} succeeded, "
                f"{progress.failed_chunks} failed"
            )

        logger.warning(f"GATHER_DEBUG: Returning {len(result_chunks)} chunks from embed_chunks")
        return result_chunks

    async def embed_single(
        self,
        chunk: AdaptiveChunk,
        retry_count: int = None
    ) -> AdaptiveChunk:
        """
        Embed a single chunk with retry logic.
        """
        retry_count = retry_count or self.default_retry_count

        for attempt in range(retry_count + 1):
            try:
                # Skip if already has embedding
                if chunk.has_embedding:
                    logger.warning(f"EMBED_DEBUG: Skipping chunk {chunk.chunk_id} - already has embedding")
                    return chunk

                logger.warning(f"EMBED_DEBUG: Embedding chunk {chunk.chunk_id}, content length={len(chunk.content)}")
                # Generate embedding
                result = await self.embedding_service.embed_text(chunk.content)
                logger.warning(f"EMBED_DEBUG: Got result for chunk {chunk.chunk_id}, embedding length={len(result.embedding) if result.embedding else 0}")

                # Update chunk with embedding
                chunk.embedding = result.embedding
                chunk.embedding_model_version = self.embedding_service.__class__.__name__

                return chunk

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout embedding chunk {chunk.chunk_id}, "
                    f"attempt {attempt + 1}/{retry_count + 1}"
                )
            except Exception as e:
                logger.warning(
                    f"Error embedding chunk {chunk.chunk_id}: {e}, "
                    f"attempt {attempt + 1}/{retry_count + 1}"
                )

            # Exponential backoff
            if attempt < retry_count:
                delay = min(
                    self.retry_base_delay * (2 ** attempt),
                    self.retry_max_delay
                )
                await asyncio.sleep(delay)

        # All retries failed
        logger.error(f"Failed to embed chunk {chunk.chunk_id} after {retry_count + 1} attempts")
        return chunk

    async def get_embedding_status(self, pdf_id: str) -> Dict[str, Any]:
        """
        Get embedding progress status for a document.
        """
        if pdf_id in self._progress:
            return self._progress[pdf_id].to_dict()

        return {
            "pdf_id": pdf_id,
            "total_chunks": 0,
            "completed_chunks": 0,
            "failed_chunks": 0,
            "in_progress": 0,
            "progress_percentage": 0.0,
            "is_complete": True,
            "elapsed_seconds": 0,
            "failed_chunk_ids": []
        }

    async def _embed_chunk_with_semaphore(
        self,
        chunk: AdaptiveChunk,
        semaphore: asyncio.Semaphore,
        timeout: float,
        pdf_id: str,
        on_progress: Optional[Callable[[EmbeddingProgress], None]]
    ) -> AdaptiveChunk:
        """
        Embed a chunk with semaphore for concurrency control.
        """
        async with semaphore:
            progress = self._progress[pdf_id]
            progress.in_progress += 1

            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    self.embed_single(chunk),
                    timeout=timeout
                )

                if result.has_embedding:
                    progress.completed_chunks += 1
                else:
                    progress.failed_chunks += 1
                    progress.failed_chunk_ids.append(chunk.chunk_id)

                # Log progress every 500 completions
                total_done = progress.completed_chunks + progress.failed_chunks
                if total_done > 0 and total_done % 500 == 0:
                    logger.warning(f"SEMAPHORE_DEBUG: {total_done}/{progress.total_chunks} tasks completed")

                return result

            except asyncio.TimeoutError:
                logger.error(f"Timeout embedding chunk {chunk.chunk_id}")
                progress.failed_chunks += 1
                progress.failed_chunk_ids.append(chunk.chunk_id)
                return chunk

            except Exception as e:
                logger.error(f"Error embedding chunk {chunk.chunk_id}: {e}")
                progress.failed_chunks += 1
                progress.failed_chunk_ids.append(chunk.chunk_id)
                return chunk

            finally:
                progress.in_progress -= 1

                # Call progress callback
                if on_progress:
                    try:
                        on_progress(progress)
                    except Exception as e:
                        logger.warning(f"Progress callback error: {e}")

    async def embed_chunks_batch(
        self,
        chunks: List[AdaptiveChunk],
        batch_size: int = 10
    ) -> List[AdaptiveChunk]:
        """
        Embed chunks in batches for memory efficiency.

        Args:
            chunks: Chunks to embed
            batch_size: Number of chunks per batch

        Returns:
            Chunks with embeddings
        """
        if not chunks:
            return []

        result_chunks = []

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            logger.debug(f"Embedding batch {i // batch_size + 1}, size: {len(batch)}")

            try:
                # Get texts for batch embedding
                texts = [chunk.content for chunk in batch]

                # Batch embed
                batch_result = await self.embedding_service.embed_texts(texts)

                # Update chunks with embeddings
                for j, chunk in enumerate(batch):
                    if j < len(batch_result.embeddings):
                        chunk.embedding = batch_result.embeddings[j].embedding
                        chunk.embedding_model_version = batch_result.model or "unknown"
                    result_chunks.append(chunk)

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Fallback to individual embedding
                for chunk in batch:
                    embedded_chunk = await self.embed_single(chunk)
                    result_chunks.append(embedded_chunk)

        return result_chunks

    def clear_progress(self, pdf_id: str):
        """Clear progress tracking for a document."""
        if pdf_id in self._progress:
            del self._progress[pdf_id]


class MockEmbeddingExecutor(ParallelEmbeddingExecutorPort):
    """
    Mock embedding executor for testing.
    """

    def __init__(self, embedding_dimension: int = 1024):
        self.embedding_dimension = embedding_dimension
        self._progress: Dict[str, EmbeddingProgress] = {}

    async def embed_chunks(
        self,
        chunks: List[AdaptiveChunk],
        concurrency: int = 5,
        timeout_per_chunk: float = 30.0
    ) -> List[AdaptiveChunk]:
        """Generate mock embeddings."""
        import random

        for chunk in chunks:
            # Generate random embedding
            chunk.embedding = [random.random() for _ in range(self.embedding_dimension)]
            chunk.embedding_model_version = "mock-embedding-v1"

        return chunks

    async def embed_single(
        self,
        chunk: AdaptiveChunk,
        retry_count: int = 3
    ) -> AdaptiveChunk:
        """Generate mock embedding for single chunk."""
        import random

        chunk.embedding = [random.random() for _ in range(self.embedding_dimension)]
        chunk.embedding_model_version = "mock-embedding-v1"
        return chunk

    async def get_embedding_status(self, pdf_id: str) -> Dict[str, Any]:
        """Get mock status."""
        return {
            "pdf_id": pdf_id,
            "total_chunks": 0,
            "completed_chunks": 0,
            "failed_chunks": 0,
            "in_progress": 0,
            "progress_percentage": 100.0,
            "is_complete": True,
            "elapsed_seconds": 0,
            "failed_chunk_ids": []
        }


# Singleton instance
_executor: Optional[ParallelEmbeddingExecutor] = None


def get_parallel_embedding_executor(
    embedding_service: EmbeddingPort = None
) -> ParallelEmbeddingExecutor:
    """Get or create parallel embedding executor instance."""
    global _executor
    if _executor is None and embedding_service is not None:
        _executor = ParallelEmbeddingExecutor(embedding_service)
    return _executor


def create_parallel_embedding_executor(
    embedding_service: EmbeddingPort,
    concurrency: int = None,
    timeout: float = None
) -> ParallelEmbeddingExecutor:
    """Create a new parallel embedding executor."""
    return ParallelEmbeddingExecutor(
        embedding_service=embedding_service,
        default_concurrency=concurrency,
        default_timeout=timeout
    )
