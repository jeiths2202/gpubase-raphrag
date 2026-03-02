"""
Multimodal Embedding Pipeline
Generates embeddings for text, images, and combined multimodal content
"""
import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Union

from ..models.document import (
    DocumentType,
    ProcessingMode,
    ImageInfo,
    TableInfo,
    ChunkInfo,
)


class EmbeddingConfig:
    """Configuration for embedding generation."""

    # NIM Embedding API (production)
    EMBEDDING_API_URL = os.getenv("EMBEDDING_API_URL", "http://localhost:12801/v1")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nvidia/nv-embedqa-mistral-7b-v2")
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    # Text embedding model
    TEXT_MODEL = EMBEDDING_MODEL
    TEXT_DIMENSION = EMBEDDING_DIMENSION


    # Image embedding model (via VLM service)
    IMAGE_MODEL = "bakllava"
    IMAGE_DIMENSION = 1024

    # Multimodal embedding model
    MULTIMODAL_MODEL = "bakllava"
    MULTIMODAL_DIMENSION = 1024

    # Batch processing
    BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    MAX_TEXT_LENGTH = 8192

    # Chunk settings
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 100

    # NIM token limit (default 512 for nvidia/nv-embedqa-mistral-7b-v2)
    NIM_MAX_TOKENS = int(os.getenv("EMBEDDING_MAX_TOKENS", "512"))
    NIM_SAFE_TOKEN_LIMIT = int(os.getenv("EMBEDDING_SAFE_TOKEN_LIMIT", "400"))

    # Timeout and retry settings
    REQUEST_TIMEOUT_TOTAL = int(os.getenv("EMBEDDING_TIMEOUT_TOTAL", "120"))  # 총 타임아웃 (기본 120초)
    REQUEST_TIMEOUT_CONNECT = int(os.getenv("EMBEDDING_TIMEOUT_CONNECT", "30"))  # 연결 타임아웃 (기본 30초)
    MAX_RETRIES = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))  # 최대 재시도 횟수
    RETRY_BASE_DELAY = float(os.getenv("EMBEDDING_RETRY_DELAY", "2.0"))  # 기본 재시도 대기 시간 (초)

class TextEmbeddingService:
    """
    Service for generating text embeddings.

    Uses NIM Embedding API (nvidia/nv-embedqa-mistral-7b-v2).
    Falls back to zero vector if NIM is unavailable.
    """

    def __init__(self, model: str = None):
        self.model = model or EmbeddingConfig.EMBEDDING_MODEL
        self.dimension = EmbeddingConfig.EMBEDDING_DIMENSION
        self.base_url = EmbeddingConfig.EMBEDDING_API_URL
        self.max_tokens = EmbeddingConfig.NIM_SAFE_TOKEN_LIMIT
        self.timeout_total = EmbeddingConfig.REQUEST_TIMEOUT_TOTAL
        self.timeout_connect = EmbeddingConfig.REQUEST_TIMEOUT_CONNECT
        self.max_retries = EmbeddingConfig.MAX_RETRIES
        self.retry_base_delay = EmbeddingConfig.RETRY_BASE_DELAY

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        CJK characters (Korean, Japanese, Chinese) typically use more tokens
        than Latin characters. This provides a conservative estimate.

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        cjk_count = 0
        for char in text:
            # CJK Unified Ideographs, Hiragana, Katakana, Hangul
            if ('\u4e00' <= char <= '\u9fff' or  # CJK Unified Ideographs
                '\u3040' <= char <= '\u309f' or  # Hiragana
                '\u30a0' <= char <= '\u30ff' or  # Katakana
                '\uac00' <= char <= '\ud7af'):   # Hangul
                cjk_count += 1

        other_count = len(text) - cjk_count

        # Very conservative estimates to ensure we stay under NIM limit:
        # CJK: ~3 tokens per character (handles complex Japanese/Korean tokenization)
        # Latin: ~0.5 tokens per character (handles multi-byte and special chars)
        # This ensures truncation happens more aggressively
        estimated = int(cjk_count * 3) + int(other_count / 2)
        return max(estimated, 1)

    def _truncate_to_token_limit(self, text: str, max_tokens: int = None) -> str:
        """
        Truncate text to stay within token limit.

        Uses binary search to find optimal truncation point.

        Args:
            text: Input text
            max_tokens: Maximum tokens (defaults to self.max_tokens)

        Returns:
            Truncated text within token limit
        """
        if not text:
            return text

        max_tokens = max_tokens or self.max_tokens

        # Quick check: if already within limit, return as-is
        if self._estimate_tokens(text) <= max_tokens:
            return text

        # Binary search for optimal truncation point
        left, right = 0, len(text)
        best_end = 0

        while left <= right:
            mid = (left + right) // 2
            if self._estimate_tokens(text[:mid]) <= max_tokens:
                best_end = mid
                left = mid + 1
            else:
                right = mid - 1

        # Try to truncate at word/sentence boundary
        truncated = text[:best_end]

        # Look for last sentence boundary (。.!?)
        for sep in ['。', '. ', '! ', '? ', '\n']:
            last_sep = truncated.rfind(sep)
            if last_sep > best_end * 0.7:  # Only if we keep >70% of content
                return truncated[:last_sep + len(sep)].strip()

        # Look for last word boundary (space)
        last_space = truncated.rfind(' ')
        if last_space > best_end * 0.8:  # Only if we keep >80% of content
            return truncated[:last_space].strip()

        return truncated.strip()

    async def embed_text(self, text: str, input_type: str = "passage") -> List[float]:
        """
        Generate embedding for a single text using NIM API.

        Args:
            text: Input text
            input_type: Type of input - "passage" for documents, "query" for search queries

        Returns:
            Embedding vector (1024 dimensions)
        """
        import logging
        logger = logging.getLogger(__name__)
        import aiohttp

        # Truncate text to stay within NIM token limit
        original_len = len(text)
        truncated_text = self._truncate_to_token_limit(text)
        # Always log truncation info for debugging
        logger.warning(f"EMBEDDING_DEBUG: input={original_len} chars, truncated={len(truncated_text)} chars, estimated={self._estimate_tokens(truncated_text)} tokens, limit={self.max_tokens}")
        if len(truncated_text) < original_len:
            logger.debug(
                f"Text truncated for NIM: {original_len} -> {len(truncated_text)} chars "
                f"(~{self._estimate_tokens(truncated_text)} tokens)"
            )

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/embeddings",
                        json={
                            "input": [truncated_text],
                            "model": self.model,
                            "input_type": input_type
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(
                            total=self.timeout_total,
                            connect=self.timeout_connect
                        )
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            embeddings = data.get("data", [])
                            if embeddings and "embedding" in embeddings[0]:
                                logger.debug(f"NIM embedding generated: {len(embeddings[0]['embedding'])} dims")
                                return embeddings[0]["embedding"]
                        else:
                            error_text = await response.text()
                            last_error = f"HTTP {response.status} - {error_text[:200]}"
                            logger.warning(f"NIM embedding failed (attempt {attempt + 1}/{self.max_retries}): {last_error}")
                            # HTTP 400 에러는 재시도해도 의미 없음 (입력 오류)
                            if response.status == 400:
                                break

            except asyncio.TimeoutError as e:
                last_error = f"Connection timeout (attempt {attempt + 1}/{self.max_retries})"
                logger.warning(f"NIM embedding error: {last_error}")
            except aiohttp.ClientError as e:
                last_error = f"Client error: {e} (attempt {attempt + 1}/{self.max_retries})"
                logger.warning(f"NIM embedding error: {last_error}")
            except Exception as e:
                last_error = f"Unexpected error: {e} (attempt {attempt + 1}/{self.max_retries})"
                logger.warning(f"NIM embedding error: {last_error}")

            # 마지막 시도가 아니면 지수 백오프로 대기
            if attempt < self.max_retries - 1:
                delay = self.retry_base_delay * (2 ** attempt)  # 2, 4, 8초...
                logger.info(f"Retrying NIM embedding in {delay:.1f}s...")
                await asyncio.sleep(delay)

        # Fallback to zero vector if all retries failed
        logger.warning(f"NIM embedding service unavailable after {self.max_retries} retries, using zero vector. Last error: {last_error}")
        return [0.0] * self.dimension

    async def embed_texts(
        self,
        texts: List[str],
        batch_size: int = None,
        input_type: str = "passage"
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts
            batch_size: Batch size for processing
            input_type: Type of input - "passage" for documents, "query" for search queries

        Returns:
            List of embedding vectors
        """
        batch_size = batch_size or EmbeddingConfig.BATCH_SIZE
        embeddings = []

        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # Process batch sequentially instead of using gather
            batch_embeddings = []
            for text in batch:
                emb = await self.embed_text(text, input_type=input_type)
                batch_embeddings.append(emb)
            embeddings.extend(batch_embeddings)

        return embeddings

    async def embed_chunks(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for document chunks.

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Chunks with embeddings added
        """
        texts = [chunk.get("content", "") for chunk in chunks]
        embeddings = await self.embed_texts(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
            chunk["has_embedding"] = True

        return chunks


class ImageType:
    """Image type detection and prompt customization."""

    CHART = "chart"
    DIAGRAM = "diagram"
    TABLE = "table"
    SCREENSHOT = "screenshot"
    PHOTO = "photo"
    UNKNOWN = "unknown"

    # Customized prompts for different image types
    PROMPTS = {
        CHART: """Analyze this chart/graph image in detail.

Describe:
1. Chart type (bar, line, pie, scatter, etc.)
2. Axes labels and units
3. Data trends and key values
4. Legend information if present
5. Overall insight from the data

Be specific about numbers and percentages visible.""",

        DIAGRAM: """Analyze this diagram/flowchart image in detail.

Describe:
1. Type of diagram (flowchart, architecture, sequence, etc.)
2. Main components/nodes and their labels
3. Connections and flow direction
4. Key relationships shown
5. Overall purpose of the diagram

Include all text labels visible.""",

        TABLE: """Analyze this table image in detail.

Describe:
1. Column headers
2. Row structure and categories
3. Key data values
4. Any totals or summaries
5. Overall content and purpose

Extract specific values where readable.""",

        SCREENSHOT: """Analyze this screenshot/UI image in detail.

Describe:
1. Type of interface (web, mobile, desktop app)
2. Main UI elements visible
3. Text content shown
4. Current state/context
5. Key actions or information displayed""",

        PHOTO: """Describe this photograph/image in detail.

Include:
1. Main subjects and objects
2. Setting/environment
3. Notable details
4. Any text visible
5. Relevance to document context""",

        UNKNOWN: """Describe this image in detail.

Include:
1. What type of image this is
2. Main content and elements
3. Any text visible
4. Key information conveyed
5. How it relates to the document context"""
    }

    @staticmethod
    def detect_type(image_data: bytes) -> str:
        """
        Detect image type based on content analysis.

        This is a simple heuristic. Could be enhanced with ML.
        """
        # For now, return UNKNOWN - VLM will figure it out
        # Future: Add image analysis to detect charts, diagrams, etc.
        return ImageType.UNKNOWN

    @staticmethod
    def get_prompt(image_type: str, context: Optional[str] = None) -> str:
        """Get customized prompt for image type."""
        base_prompt = ImageType.PROMPTS.get(image_type, ImageType.PROMPTS[ImageType.UNKNOWN])

        if context:
            return f"{base_prompt}\n\nDocument context: {context}"
        return base_prompt


class ImageEmbeddingService:
    """
    Service for generating image embeddings using VLM description + text embedding.

    Features:
    - VLM (port 12803) generates image description
    - NIM (port 12801) embeds the description text
    - Hash-based caching to avoid duplicate VLM calls
    - Semaphore-based concurrency control
    - Image type-specific prompts

    Flow:
    1. Check cache for existing description
    2. If miss, call VLM with type-specific prompt
    3. Cache the description
    4. Embed description text using NIM
    5. Return 1024-dim vector
    """

    # Default concurrency limit for VLM calls
    DEFAULT_MAX_CONCURRENT = int(os.getenv("VLM_MAX_CONCURRENT", "3"))

    def __init__(
        self,
        model: str = None,
        max_concurrent: int = None,
        enable_cache: bool = True
    ):
        self.model = model or EmbeddingConfig.IMAGE_MODEL
        self.dimension = EmbeddingConfig.IMAGE_DIMENSION
        self.max_concurrent = max_concurrent or self.DEFAULT_MAX_CONCURRENT
        self.enable_cache = enable_cache

        self._vlm_service = None
        self._text_embedder = None
        self._cache = None
        self._semaphore = None
        self._logger = None

        # Statistics
        self._stats = {
            "vlm_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "embeddings_generated": 0,
            "errors": 0
        }

    @property
    def logger(self):
        if self._logger is None:
            import logging
            self._logger = logging.getLogger(__name__)
        return self._logger

    @property
    def vlm_service(self):
        """Lazy initialization of VLM service."""
        if self._vlm_service is None:
            from .ollama_vlm_service import OllamaVLMService
            self._vlm_service = OllamaVLMService()
        return self._vlm_service

    @property
    def text_embedder(self):
        """Lazy initialization of text embedding service."""
        if self._text_embedder is None:
            self._text_embedder = TextEmbeddingService()
        return self._text_embedder

    @property
    def cache(self):
        """Lazy initialization of VLM image cache."""
        if self._cache is None and self.enable_cache:
            from .vlm_image_cache import get_vlm_image_cache
            self._cache = get_vlm_image_cache()
        return self._cache

    @property
    def semaphore(self):
        """Lazy initialization of semaphore for concurrency control."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        stats = self._stats.copy()
        if self.cache:
            stats["cache"] = self.cache.get_stats()
        return stats

    async def describe_image(
        self,
        image_data: bytes,
        context: Optional[str] = None,
        image_type: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Generate description for an image using VLM.

        Args:
            image_data: Raw image bytes
            context: Optional context about the document
            image_type: Optional image type hint (chart, diagram, etc.)
            use_cache: Whether to use caching

        Returns:
            Dict with description, alt_text, confidence, and cache info
        """
        # Try cache first
        if use_cache and self.cache:
            cached = await self.cache.get(image_data)
            if cached:
                self._stats["cache_hits"] += 1
                self.logger.debug(f"Cache hit for image description")
                return cached

        self._stats["cache_misses"] += 1

        # Detect image type if not provided
        if not image_type:
            image_type = ImageType.detect_type(image_data)

        # Get type-specific prompt
        prompt = ImageType.get_prompt(image_type, context)

        # Call VLM with semaphore for concurrency control
        async with self.semaphore:
            try:
                self._stats["vlm_calls"] += 1

                result = await self.vlm_service.describe_image(
                    image_data=image_data,
                    prompt=prompt,
                    context=context
                )

                description = result.get("description", "")

                if description:
                    self.logger.info(
                        f"VLM description generated: {len(description)} chars "
                        f"(type: {image_type})"
                    )

                    # Cache the result
                    if use_cache and self.cache:
                        await self.cache.set(
                            image_data=image_data,
                            description=description,
                            alt_text=result.get("alt_text", ""),
                            confidence=result.get("confidence", 0.0)
                        )

                return result

            except Exception as e:
                self._stats["errors"] += 1
                self.logger.error(f"VLM describe_image failed: {e}")
                return {
                    "description": "",
                    "alt_text": "",
                    "confidence": 0.0,
                    "error": str(e)
                }

    async def embed_image(
        self,
        image_data: bytes,
        context: Optional[str] = None,
        image_type: Optional[str] = None,
        use_cache: bool = True
    ) -> List[float]:
        """
        Generate embedding for a single image.

        Process:
        1. Check cache / Call VLM to generate image description
        2. Embed the description text using NIM
        3. Fallback to zero vector on failure

        Args:
            image_data: Raw image bytes
            context: Optional context about the document
            image_type: Optional image type hint
            use_cache: Whether to use caching

        Returns:
            Embedding vector (1024 dimensions)
        """
        try:
            # Step 1: Get image description (with cache)
            description_result = await self.describe_image(
                image_data, context, image_type, use_cache
            )
            description = description_result.get("description", "")

            if not description:
                self.logger.warning("VLM returned empty description, using zero vector")
                return [0.0] * self.dimension

            # Step 2: Embed the description text
            embedding = await self.text_embedder.embed_text(description, input_type="passage")

            self._stats["embeddings_generated"] += 1
            self.logger.info(
                f"Image embedded: {len(description)} chars -> {len(embedding)} dims "
                f"(cached: {description_result.get('cached', False)})"
            )
            return embedding

        except Exception as e:
            self._stats["errors"] += 1
            self.logger.error(f"Image embedding failed: {e}")
            return [0.0] * self.dimension

    async def embed_images(
        self,
        images: List[bytes],
        context: Optional[str] = None,
        image_types: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple images.

        Uses semaphore-based concurrency control.

        Args:
            images: List of image bytes
            context: Optional context about the document
            image_types: Optional list of image type hints
            use_cache: Whether to use caching

        Returns:
            List of embedding vectors
        """
        if not images:
            return []

        # Prepare image types
        if image_types is None:
            image_types = [None] * len(images)
        elif len(image_types) < len(images):
            image_types.extend([None] * (len(images) - len(image_types)))

        # Process all images concurrently (semaphore limits actual concurrency)
        tasks = [
            self.embed_image(img_data, context, img_type, use_cache)
            for img_data, img_type in zip(images, image_types)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        embeddings = []
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Batch image embedding error: {result}")
                embeddings.append([0.0] * self.dimension)
            else:
                embeddings.append(result)

        self.logger.info(
            f"Embedded {len(embeddings)} images "
            f"(cache hits: {self._stats['cache_hits']})"
        )
        return embeddings

    async def describe_and_embed_image(
        self,
        image_data: bytes,
        context: Optional[str] = None,
        image_type: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Generate both description and embedding for an image.

        Args:
            image_data: Raw image bytes
            context: Optional context
            image_type: Optional image type hint
            use_cache: Whether to use caching

        Returns:
            Dict with description, alt_text, embedding, and metadata
        """
        description_result = await self.describe_image(
            image_data, context, image_type, use_cache
        )
        description = description_result.get("description", "")

        if description:
            embedding = await self.text_embedder.embed_text(description, input_type="passage")
            self._stats["embeddings_generated"] += 1
        else:
            embedding = [0.0] * self.dimension

        return {
            "description": description,
            "alt_text": description_result.get("alt_text", ""),
            "confidence": description_result.get("confidence", 0.0),
            "embedding": embedding,
            "has_embedding": bool(description),
            "cached": description_result.get("cached", False),
            "error": description_result.get("error")
        }

    async def clear_cache(self) -> int:
        """Clear the description cache."""
        if self.cache:
            return await self.cache.clear()
        return 0


class MultimodalEmbeddingService:
    """
    Service for generating multimodal embeddings.
    Currently returns zero vectors as placeholder.
    """

    def __init__(self, model: str = None):
        self.model = model or EmbeddingConfig.MULTIMODAL_MODEL
        self.dimension = EmbeddingConfig.MULTIMODAL_DIMENSION

    async def embed_image_with_context(
        self,
        image_data: bytes,
        context_text: str = ""
    ) -> List[float]:
        """
        Generate multimodal embedding for image with text context.

        Args:
            image_data: Raw image bytes
            context_text: Optional context text

        Returns:
            Zero vector (1024 dimensions) - placeholder
        """
        return [0.0] * self.dimension

    async def embed_document_page(
        self,
        page_image: bytes,
        page_text: str = ""
    ) -> List[float]:
        """
        Generate embedding for a document page.

        Args:
            page_image: Page rendered as image
            page_text: Extracted text from page

        Returns:
            Zero vector - placeholder
        """
        return [0.0] * self.dimension

    async def embed_table_with_context(
        self,
        table_image: bytes,
        table_markdown: str,
        surrounding_text: str = ""
    ) -> List[float]:
        """
        Generate embedding for a table with context.

        Args:
            table_image: Table rendered as image
            table_markdown: Table in markdown format
            surrounding_text: Text around the table

        Returns:
            Zero vector - placeholder
        """
        return [0.0] * self.dimension


class ChunkingService:
    """
    Service for intelligent document chunking.
    Handles text, tables, and image captions.
    """

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None
    ):
        self.chunk_size = chunk_size or EmbeddingConfig.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or EmbeddingConfig.CHUNK_OVERLAP

    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Split text into chunks with overlap.

        Args:
            text: Input text
            metadata: Optional metadata to include

        Returns:
            List of chunk dictionaries
        """
        chunks = []
        words = text.split()
        current_chunk = []
        current_length = 0

        for word in words:
            current_chunk.append(word)
            current_length += len(word) + 1

            if current_length >= self.chunk_size:
                chunk_text = " ".join(current_chunk)
                chunks.append({
                    "id": f"chunk_{uuid.uuid4().hex[:8]}",
                    "index": len(chunks),
                    "content": chunk_text,
                    "content_length": len(chunk_text),
                    "chunk_type": "text",
                    "metadata": metadata or {}
                })

                # Keep overlap
                overlap_words = current_chunk[-self.chunk_overlap // 10:] if self.chunk_overlap else []
                current_chunk = overlap_words
                current_length = sum(len(w) + 1 for w in current_chunk)

        # Add remaining text
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append({
                "id": f"chunk_{uuid.uuid4().hex[:8]}",
                "index": len(chunks),
                "content": chunk_text,
                "content_length": len(chunk_text),
                "chunk_type": "text",
                "metadata": metadata or {}
            })

        return chunks

    def chunk_with_tables(
        self,
        text: str,
        tables: List[TableInfo],
        page_number: int = None
    ) -> List[Dict[str, Any]]:
        """
        Create chunks from text and tables.

        Tables get their own chunks with special handling.
        """
        chunks = []

        # First chunk the text
        text_chunks = self.chunk_text(
            text,
            metadata={"page_number": page_number}
        )
        chunks.extend(text_chunks)

        # Add table chunks
        for table in tables:
            table_chunk = {
                "id": f"chunk_{uuid.uuid4().hex[:8]}",
                "index": len(chunks),
                "content": table.markdown if table.markdown else self._table_to_text(table),
                "content_length": len(table.markdown) if table.markdown else 0,
                "chunk_type": "table",
                "source_table_id": table.id,
                "page_number": table.page_number or page_number,
                "metadata": {
                    "headers": table.headers,
                    "row_count": len(table.rows),
                    "caption": table.caption
                }
            }
            chunks.append(table_chunk)

        return chunks

    def chunk_with_images(
        self,
        text: str,
        images: List[ImageInfo],
        page_number: int = None
    ) -> List[Dict[str, Any]]:
        """
        Create chunks from text and image captions.

        Image descriptions become separate chunks.
        """
        chunks = []

        # First chunk the text
        text_chunks = self.chunk_text(
            text,
            metadata={"page_number": page_number}
        )
        chunks.extend(text_chunks)

        # Add image caption chunks
        for image in images:
            if image.description or image.alt_text:
                caption = image.description or image.alt_text
                image_chunk = {
                    "id": f"chunk_{uuid.uuid4().hex[:8]}",
                    "index": len(chunks),
                    "content": f"[Image: {caption}]",
                    "content_length": len(caption) + 9,
                    "chunk_type": "image_caption",
                    "source_image_id": image.id,
                    "page_number": image.page_number or page_number,
                    "metadata": {
                        "position": image.position,
                        "alt_text": image.alt_text
                    }
                }
                chunks.append(image_chunk)

        return chunks

    def _table_to_text(self, table: TableInfo) -> str:
        """Convert table to text representation."""
        text = f"Table: {table.caption}\n" if table.caption else "Table:\n"
        if table.headers:
            text += " | ".join(table.headers) + "\n"
        for row in table.rows:
            text += " | ".join(str(cell) for cell in row) + "\n"
        return text


class MultimodalEmbeddingPipeline:
    """
    Complete pipeline for generating embeddings from multimodal documents.

    Handles:
    - Text chunking and embedding
    - Image embedding via VLM description
    - Table embedding
    - Combined multimodal embedding

    Processing Modes:
    - TEXT_ONLY: Only text embedding (images stored but not embedded)
    - IMAGE_ONLY: OCR extraction for scanned/image-based documents
    - VLM_ENHANCED: VLM-assisted: text + OCR + layout + table extraction + image embeddings
    """

    def __init__(self):
        self.text_embedder = TextEmbeddingService()
        self.image_embedder = ImageEmbeddingService()
        self.multimodal_embedder = MultimodalEmbeddingService()
        self.chunker = ChunkingService()
        self._logger = None

    @property
    def logger(self):
        if self._logger is None:
            import logging
            self._logger = logging.getLogger(__name__)
        return self._logger

    async def _generate_image_descriptions(
        self,
        images: List[Tuple[bytes, ImageInfo]],
        document_context: str = None
    ) -> List[Tuple[bytes, ImageInfo]]:
        """
        Generate descriptions for images using VLM.

        Updates ImageInfo.description with VLM-generated descriptions.

        Args:
            images: List of (image_bytes, ImageInfo) tuples
            document_context: Optional context about the document

        Returns:
            Updated images list with descriptions
        """
        updated_images = []

        for img_bytes, img_info in images:
            # Skip if already has a description
            if img_info.description:
                updated_images.append((img_bytes, img_info))
                continue

            try:
                # Generate description using VLM
                result = await self.image_embedder.describe_image(
                    image_data=img_bytes,
                    context=document_context
                )

                description = result.get("description", "")
                alt_text = result.get("alt_text", "")

                if description:
                    # Update ImageInfo with generated description
                    img_info.description = description
                    if not img_info.alt_text:
                        img_info.alt_text = alt_text

                    self.logger.info(
                        f"VLM description for image {img_info.id}: {len(description)} chars"
                    )
                else:
                    self.logger.warning(
                        f"VLM returned empty description for image {img_info.id}"
                    )

            except Exception as e:
                self.logger.error(f"Failed to generate description for image {img_info.id}: {e}")

            updated_images.append((img_bytes, img_info))

        return updated_images

    async def process_document(
        self,
        text_content: str,
        images: List[Tuple[bytes, ImageInfo]] = None,
        tables: List[TableInfo] = None,
        processing_mode: ProcessingMode = ProcessingMode.TEXT_ONLY,
        document_context: str = None
    ) -> Dict[str, Any]:
        """
        Process a complete document and generate all embeddings.

        Args:
            text_content: Extracted text from document
            images: List of (image_bytes, ImageInfo) tuples
            tables: List of extracted tables
            processing_mode: How to process the document
            document_context: Optional context for VLM (e.g., document title)

        Returns:
            Dictionary with chunks, embeddings, and metadata
        """
        images = images or []
        tables = tables or []

        result = {
            "chunks": [],
            "image_embeddings": [],
            "vlm_descriptions_generated": 0,
            "stats": {
                "total_chunks": 0,
                "text_chunks": 0,
                "table_chunks": 0,
                "image_chunks": 0,
                "embedding_dimension": self.text_embedder.dimension
            }
        }

        # Step 1: Generate VLM descriptions for images if in VLM mode
        if images and processing_mode in [ProcessingMode.IMAGE_ONLY, ProcessingMode.VLM_ENHANCED]:
            self.logger.info(
                f"Generating VLM descriptions for {len(images)} images "
                f"(mode: {processing_mode.value})"
            )
            images = await self._generate_image_descriptions(images, document_context)

            # Count successfully generated descriptions
            result["vlm_descriptions_generated"] = sum(
                1 for _, info in images if info.description
            )

        # Step 2: Create chunks based on content
        if tables:
            chunks = self.chunker.chunk_with_tables(
                text_content,
                tables
            )
        else:
            chunks = self.chunker.chunk_text(text_content)

        # Step 3: Add image caption chunks (now with VLM descriptions)
        if images:
            image_infos = [info for _, info in images]
            image_chunks = self.chunker.chunk_with_images(
                "",  # Already processed text
                image_infos
            )
            # Only add image chunks (skip empty text chunk)
            for chunk in image_chunks:
                if chunk["chunk_type"] == "image_caption":
                    chunk["index"] = len(chunks)
                    chunks.append(chunk)

        # Step 4: Generate text embeddings for all chunks (including image captions)
        chunks = await self.text_embedder.embed_chunks(chunks)
        result["chunks"] = chunks

        # Step 5: Generate separate image embeddings if in VLM mode
        if processing_mode in [ProcessingMode.IMAGE_ONLY, ProcessingMode.VLM_ENHANCED]:
            if images:
                # Use describe_and_embed_image for efficient processing
                for img_bytes, info in images:
                    try:
                        # If description already exists, just embed it
                        if info.description:
                            embedding = await self.text_embedder.embed_text(
                                info.description,
                                input_type="passage"
                            )
                        else:
                            # Generate description and embedding together
                            embed_result = await self.image_embedder.describe_and_embed_image(
                                img_bytes,
                                context=document_context
                            )
                            embedding = embed_result.get("embedding", [0.0] * self.image_embedder.dimension)

                        result["image_embeddings"].append({
                            "image_id": info.id,
                            "description": info.description,
                            "embedding": embedding,
                            "dimension": self.image_embedder.dimension,
                            "has_vlm_description": bool(info.description)
                        })

                    except Exception as e:
                        self.logger.error(f"Failed to embed image {info.id}: {e}")
                        result["image_embeddings"].append({
                            "image_id": info.id,
                            "description": info.description,
                            "embedding": [0.0] * self.image_embedder.dimension,
                            "dimension": self.image_embedder.dimension,
                            "has_vlm_description": bool(info.description),
                            "error": str(e)
                        })

        # Update stats
        result["stats"]["total_chunks"] = len(chunks)
        result["stats"]["text_chunks"] = sum(
            1 for c in chunks if c["chunk_type"] == "text"
        )
        result["stats"]["table_chunks"] = sum(
            1 for c in chunks if c["chunk_type"] == "table"
        )
        result["stats"]["image_chunks"] = sum(
            1 for c in chunks if c["chunk_type"] == "image_caption"
        )
        result["stats"]["vlm_descriptions_generated"] = result["vlm_descriptions_generated"]
        result["stats"]["image_embeddings_count"] = len(result["image_embeddings"])
        result["stats"]["processing_mode"] = processing_mode.value

        self.logger.info(
            f"Document processed: {result['stats']['total_chunks']} chunks, "
            f"{result['stats']['image_chunks']} image captions, "
            f"{result['vlm_descriptions_generated']} VLM descriptions"
        )

        return result

    async def reembed_document(
        self,
        chunks: List[Dict[str, Any]],
        model: str = None
    ) -> List[Dict[str, Any]]:
        """
        Re-generate embeddings for existing chunks.

        Useful when switching embedding models.
        """
        if model:
            self.text_embedder = TextEmbeddingService(model)

        return await self.text_embedder.embed_chunks(chunks)


class HybridSearchIndex:
    """
    Hybrid search index combining vector and keyword search.

    In production, this would interface with:
    - Neo4j Vector Index
    - Elasticsearch/OpenSearch
    - Milvus/Qdrant/Pinecone
    """

    def __init__(self):
        self.vectors: Dict[str, List[float]] = {}  # chunk_id -> embedding
        self.texts: Dict[str, str] = {}  # chunk_id -> content
        self.metadata: Dict[str, Dict] = {}  # chunk_id -> metadata

    async def index_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_id: str
    ) -> Dict[str, Any]:
        """
        Index chunks for search.

        Args:
            chunks: Chunks with embeddings
            document_id: Parent document ID

        Returns:
            Indexing statistics
        """
        indexed = 0

        for chunk in chunks:
            chunk_id = chunk["id"]

            if "embedding" in chunk:
                self.vectors[chunk_id] = chunk["embedding"]

            self.texts[chunk_id] = chunk.get("content", "")
            self.metadata[chunk_id] = {
                "document_id": document_id,
                "chunk_type": chunk.get("chunk_type", "text"),
                "page_number": chunk.get("page_number"),
                "index": chunk.get("index", 0)
            }

            indexed += 1

        return {
            "indexed_chunks": indexed,
            "vector_indexed": len(self.vectors),
            "text_indexed": len(self.texts)
        }

    async def search(
        self,
        query_embedding: List[float],
        query_text: str = "",
        top_k: int = 10,
        filters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search.

        Args:
            query_embedding: Query vector
            query_text: Query text for keyword search
            top_k: Number of results
            filters: Optional metadata filters

        Returns:
            List of search results with scores
        """
        # In production, this would call actual vector DB
        # Mock: return random results
        import random

        results = []
        for chunk_id, text in list(self.texts.items())[:top_k]:
            results.append({
                "chunk_id": chunk_id,
                "content": text,
                "metadata": self.metadata.get(chunk_id, {}),
                "score": random.random()
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    async def delete_document(self, document_id: str) -> int:
        """
        Remove all chunks for a document.

        Returns:
            Number of chunks deleted
        """
        to_delete = [
            cid for cid, meta in self.metadata.items()
            if meta.get("document_id") == document_id
        ]

        for cid in to_delete:
            self.vectors.pop(cid, None)
            self.texts.pop(cid, None)
            self.metadata.pop(cid, None)

        return len(to_delete)


# Factory functions
def get_text_embedding_service() -> TextEmbeddingService:
    """Get text embedding service."""
    return TextEmbeddingService()


def get_image_embedding_service() -> ImageEmbeddingService:
    """Get image embedding service."""
    return ImageEmbeddingService()


def get_multimodal_embedding_service() -> MultimodalEmbeddingService:
    """Get multimodal embedding service."""
    return MultimodalEmbeddingService()


def get_chunking_service() -> ChunkingService:
    """Get chunking service."""
    return ChunkingService()


def get_embedding_pipeline() -> MultimodalEmbeddingPipeline:
    """Get complete embedding pipeline."""
    return MultimodalEmbeddingPipeline()


def get_hybrid_search_index() -> HybridSearchIndex:
    """Get hybrid search index."""
    return HybridSearchIndex()
