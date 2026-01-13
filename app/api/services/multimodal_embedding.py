"""
Multimodal Embedding Pipeline
Generates embeddings for text, images, and combined multimodal content
"""
import asyncio
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

    # Text embedding model (Ollama nomic-embed-text for local, NIM for production)
    TEXT_MODEL = "nomic-embed-text"  # Ollama model
    TEXT_DIMENSION = 768  # nomic-embed-text dimension

    # Ollama settings
    OLLAMA_BASE_URL = "http://localhost:11434"

    # Image embedding model (bakllava via Ollama)
    IMAGE_MODEL = "bakllava"
    IMAGE_DIMENSION = 4096  # bakllava embedding dimension

    # Multimodal embedding model
    MULTIMODAL_MODEL = "bakllava"
    MULTIMODAL_DIMENSION = 4096

    # Batch processing
    BATCH_SIZE = 32
    MAX_TEXT_LENGTH = 8192

    # Chunk settings
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 100


class TextEmbeddingService:
    """
    Service for generating text embeddings using Ollama.

    Uses nomic-embed-text model via Ollama for local embeddings.
    Falls back to mock embeddings if Ollama is unavailable.
    """

    def __init__(self, model: str = None):
        self.model = model or EmbeddingConfig.TEXT_MODEL
        self.dimension = EmbeddingConfig.TEXT_DIMENSION
        self.base_url = EmbeddingConfig.OLLAMA_BASE_URL
        self._session = None

    def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession()
        return self._session

    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text using Ollama.

        Args:
            text: Input text

        Returns:
            Embedding vector (768 dimensions for nomic-embed-text)
        """
        import logging
        logger = logging.getLogger(__name__)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text[:8192]},
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        embedding = data.get("embedding", [])
                        if embedding:
                            return embedding
                    else:
                        logger.warning(f"Ollama embedding failed: HTTP {response.status}")
        except Exception as e:
            logger.warning(f"Ollama embedding error: {e}, using fallback")

        # Fallback to zero vector
        return [0.0] * self.dimension

    async def embed_texts(
        self,
        texts: List[str],
        batch_size: int = None
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts
            batch_size: Batch size for processing

        Returns:
            List of embedding vectors
        """
        batch_size = batch_size or EmbeddingConfig.BATCH_SIZE
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = await asyncio.gather(
                *[self.embed_text(text) for text in batch]
            )
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


class ImageEmbeddingService:
    """
    Service for generating image embeddings using Ollama bakllava.

    Uses bakllava VLM model for multimodal embeddings with 4096 dimensions.
    Falls back to mock embeddings if Ollama is unavailable.
    """

    def __init__(self, model: str = None):
        self.model = model or EmbeddingConfig.IMAGE_MODEL
        self.dimension = EmbeddingConfig.IMAGE_DIMENSION
        self._vlm_service = None

    def _get_vlm_service(self):
        """Lazy load the Ollama VLM service."""
        if self._vlm_service is None:
            from .ollama_vlm_service import get_ollama_vlm_service
            self._vlm_service = get_ollama_vlm_service()
        return self._vlm_service

    async def embed_image(self, image_data: bytes) -> List[float]:
        """
        Generate embedding for a single image using bakllava.

        Args:
            image_data: Raw image bytes

        Returns:
            Embedding vector (4096 dimensions)
        """
        try:
            vlm_service = self._get_vlm_service()
            embedding = await vlm_service.generate_embedding(image_data)
            return embedding
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Image embedding failed, using fallback: {e}"
            )
            # Fallback to zero vector
            return [0.0] * self.dimension

    async def embed_images(
        self,
        images: List[bytes],
        batch_size: int = 2
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple images.

        Args:
            images: List of image bytes
            batch_size: Batch size for processing (lower for VLM)

        Returns:
            List of embedding vectors
        """
        try:
            vlm_service = self._get_vlm_service()
            return await vlm_service.batch_embed(images, batch_size)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Batch image embedding failed, using fallback: {e}"
            )
            # Fallback to zero vectors
            return [[0.0] * self.dimension for _ in images]

    async def describe_image(self, image_data: bytes) -> Dict[str, Any]:
        """
        Generate description for an image using bakllava.

        Args:
            image_data: Raw image bytes

        Returns:
            Dict with description and alt_text
        """
        try:
            vlm_service = self._get_vlm_service()
            return await vlm_service.describe_image(image_data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Image description failed: {e}"
            )
            return {
                "description": "",
                "alt_text": "",
                "confidence": 0.0,
                "error": str(e)
            }


class MultimodalEmbeddingService:
    """
    Service for generating multimodal embeddings using Ollama bakllava.

    Provides context-aware image embeddings for document understanding.
    """

    def __init__(self, model: str = None):
        self.model = model or EmbeddingConfig.MULTIMODAL_MODEL
        self.dimension = EmbeddingConfig.MULTIMODAL_DIMENSION
        self._vlm_service = None

    def _get_vlm_service(self):
        """Lazy load the Ollama VLM service."""
        if self._vlm_service is None:
            from .ollama_vlm_service import get_ollama_vlm_service
            self._vlm_service = get_ollama_vlm_service()
        return self._vlm_service

    async def embed_image_with_context(
        self,
        image_data: bytes,
        context_text: str = ""
    ) -> List[float]:
        """
        Generate multimodal embedding for image with text context.

        Uses bakllava to generate embeddings that understand
        both the image content and surrounding context.

        Args:
            image_data: Raw image bytes
            context_text: Optional context text

        Returns:
            Multimodal embedding vector (4096 dimensions)
        """
        try:
            vlm_service = self._get_vlm_service()
            # Use description with context to get better embedding
            if context_text:
                result = await vlm_service.describe_image(
                    image_data,
                    context=context_text
                )
            embedding = await vlm_service.generate_embedding(image_data)
            return embedding
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Multimodal embedding failed: {e}"
            )
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
            Embedding vector for the entire page
        """
        return await self.embed_image_with_context(page_image, page_text)

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
            Embedding vector
        """
        context = f"{surrounding_text}\n\n{table_markdown}"
        return await self.embed_image_with_context(table_image, context)


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
    - Image embedding
    - Table embedding
    - Combined multimodal embedding
    """

    def __init__(self):
        self.text_embedder = TextEmbeddingService()
        self.image_embedder = ImageEmbeddingService()
        self.multimodal_embedder = MultimodalEmbeddingService()
        self.chunker = ChunkingService()

    async def process_document(
        self,
        text_content: str,
        images: List[Tuple[bytes, ImageInfo]] = None,
        tables: List[TableInfo] = None,
        processing_mode: ProcessingMode = ProcessingMode.TEXT_ONLY
    ) -> Dict[str, Any]:
        """
        Process a complete document and generate all embeddings.

        Args:
            text_content: Extracted text from document
            images: List of (image_bytes, ImageInfo) tuples
            tables: List of extracted tables
            processing_mode: How to process the document

        Returns:
            Dictionary with chunks, embeddings, and metadata
        """
        images = images or []
        tables = tables or []

        result = {
            "chunks": [],
            "image_embeddings": [],
            "stats": {
                "total_chunks": 0,
                "text_chunks": 0,
                "table_chunks": 0,
                "image_chunks": 0,
                "embedding_dimension": self.text_embedder.dimension
            }
        }

        # Create chunks based on content
        if tables:
            chunks = self.chunker.chunk_with_tables(
                text_content,
                tables
            )
        else:
            chunks = self.chunker.chunk_text(text_content)

        # Add image caption chunks
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

        # Generate text embeddings for all chunks
        chunks = await self.text_embedder.embed_chunks(chunks)
        result["chunks"] = chunks

        # Generate image embeddings if in multimodal mode
        if processing_mode in [ProcessingMode.MULTIMODAL, ProcessingMode.VLM_ENHANCED]:
            if images:
                image_data = [img_bytes for img_bytes, _ in images]
                embeddings = await self.image_embedder.embed_images(image_data)

                for i, (_, info) in enumerate(images):
                    result["image_embeddings"].append({
                        "image_id": info.id,
                        "embedding": embeddings[i],
                        "dimension": self.image_embedder.dimension
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
