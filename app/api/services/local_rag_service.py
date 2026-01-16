"""
Local RAG Service
PostgreSQL + Ollama based RAG service for local-only mode (no GPU/Neo4j required).
"""
import logging
import asyncio
from typing import Optional, List, Dict, Any

from .multimodal_embedding import (
    TextEmbeddingService,
    ChunkingService,
    EmbeddingConfig
)

logger = logging.getLogger(__name__)


class LocalRAGService:
    """
    Local RAG service using PostgreSQL for storage and Ollama for embeddings.
    Works without Neo4j or GPU servers.
    """

    def __init__(self, text_chunk_repository=None, llm_service=None):
        """
        Initialize the local RAG service.

        Args:
            text_chunk_repository: PostgresTextChunkRepository instance
            llm_service: Optional LLM service for response generation
        """
        self._chunk_repo = text_chunk_repository
        self._llm_service = llm_service
        self._text_embedder = TextEmbeddingService()
        self._chunker = ChunkingService()

    async def embed_document(
        self,
        document_id: str,
        text_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process and embed a document's text content.

        Args:
            document_id: Document identifier
            text_content: Full text content to embed
            metadata: Optional metadata to store with chunks

        Returns:
            Processing result with chunk count and stats
        """
        if not self._chunk_repo:
            raise RuntimeError("Text chunk repository not initialized")

        logger.info(f"Embedding document {document_id[:16]}...")

        # Chunk the text
        chunks = self._chunker.chunk_text(text_content, metadata)
        logger.info(f"Created {len(chunks)} chunks")

        # Generate embeddings for all chunks
        embedded_count = 0
        for i, chunk in enumerate(chunks):
            try:
                embedding = await self._text_embedder.embed_text(chunk["content"])
                chunk["embedding"] = embedding
                chunk["has_embedding"] = True
                embedded_count += 1

                if (i + 1) % 10 == 0:
                    logger.info(f"Embedded {i + 1}/{len(chunks)} chunks")
            except Exception as e:
                logger.error(f"Failed to embed chunk {i}: {e}")
                chunk["embedding"] = None
                chunk["has_embedding"] = False

        # Save chunks to PostgreSQL
        saved = await self._chunk_repo.save_chunks_batch(chunks, document_id)

        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "embedded_chunks": embedded_count,
            "saved_chunks": saved,
            "embedding_dimension": self._text_embedder.dimension,
            "success": saved > 0
        }

    async def search(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.3,
        document_id: Optional[str] = None,
        language: str = "auto",
        use_expansion: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using vector similarity.

        Args:
            query: Search query
            limit: Maximum number of results
            min_similarity: Minimum similarity threshold
            document_id: Optional filter by document
            language: Query language for expansion (auto, ja, ko, en)
            use_expansion: Whether to use query expansion for synonyms

        Returns:
            List of matching chunks with similarity scores
        """
        if not self._chunk_repo:
            raise RuntimeError("Text chunk repository not initialized")

        # Apply query expansion for better retrieval
        search_query = query
        if use_expansion:
            try:
                from .query_expansion_service import get_query_expansion_service
                expansion_service = get_query_expansion_service()
                expanded = expansion_service.expand(query, language)
                search_query = expanded.get_expanded_query()
                logger.info(f"Query expanded: '{query}' -> '{search_query}'")
            except Exception as e:
                logger.warning(f"Query expansion failed, using original: {e}")

        # Generate query embedding with expanded terms
        query_embedding = await self._text_embedder.embed_text(search_query)

        # Search for similar chunks
        results = await self._chunk_repo.search_similar(
            query_embedding=query_embedding,
            limit=limit,
            min_similarity=min_similarity,
            document_id=document_id
        )

        return results

    async def query(
        self,
        question: str,
        top_k: int = 5,
        language: str = "en",
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Answer a question using RAG.

        Args:
            question: User question
            top_k: Number of context chunks to retrieve
            language: Response language
            document_id: Optional filter by document

        Returns:
            Answer with sources
        """
        # Search for relevant context
        sources = await self.search(
            query=question,
            limit=top_k,
            min_similarity=0.2,
            document_id=document_id
        )

        if not sources:
            return {
                "answer": "No relevant information found in the knowledge base.",
                "sources": [],
                "success": False
            }

        # Build context from sources
        context_parts = []
        for i, source in enumerate(sources):
            context_parts.append(
                f"[Source {i + 1}] (similarity: {source['similarity']:.2%})\n"
                f"{source['content'][:500]}"
            )
        context = "\n\n".join(context_parts)

        # Generate answer using LLM if available
        if self._llm_service:
            answer = await self._llm_service.generate(
                prompt=f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:",
                max_tokens=1000
            )
        else:
            # Fallback: return context directly
            answer = f"Based on the knowledge base:\n\n{context[:1500]}"

        return {
            "answer": answer,
            "sources": [
                {
                    "chunk_id": s["chunk_id"],
                    "document_id": s["document_id"],
                    "content": s["content"][:200] + "...",
                    "similarity": s["similarity"]
                }
                for s in sources
            ],
            "success": True
        }

    async def get_stats(self) -> Dict[str, Any]:
        """Get RAG service statistics."""
        if not self._chunk_repo:
            return {"error": "Repository not initialized"}

        stats = await self._chunk_repo.get_stats()
        stats["embedding_model"] = self._text_embedder.model
        stats["embedding_dimension"] = self._text_embedder.dimension
        return stats


# Global instance
_local_rag_service = None


async def get_local_rag_service() -> LocalRAGService:
    """Get or create the local RAG service singleton."""
    global _local_rag_service

    if _local_rag_service is None:
        from ..core.deps import get_postgres_pool
        from ..infrastructure.postgres.text_chunk_repository import PostgresTextChunkRepository

        pool = await get_postgres_pool()
        chunk_repo = PostgresTextChunkRepository(pool)
        _local_rag_service = LocalRAGService(text_chunk_repository=chunk_repo)

    return _local_rag_service
