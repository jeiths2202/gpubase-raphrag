"""
PostgreSQL Text Chunk Repository
Stores text chunks with embeddings for RAG using pgvector.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PostgresTextChunkRepository:
    """
    Repository for storing and searching text chunks with embeddings.
    Uses PostgreSQL with pgvector extension.
    """

    def __init__(self, pool):
        """Initialize with asyncpg connection pool."""
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        """Ensure the text_chunks table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            # Create table for text chunks
            # NOTE: vector(4096) matches NIM embedding model (nvidia/nv-embedqa-mistral-7b-v2)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS text_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    content_length INTEGER DEFAULT 0,
                    chunk_type TEXT DEFAULT 'text',
                    page_number INTEGER,
                    embedding vector(4096),
                    has_embedding BOOLEAN DEFAULT FALSE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_text_chunks_document_id
                ON text_chunks(document_id)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_text_chunks_has_embedding
                ON text_chunks(has_embedding)
            """)

            logger.info("text_chunks table initialized")
            self._initialized = True

    async def save_chunk(
        self,
        chunk_id: str,
        document_id: str,
        content: str,
        chunk_index: int = 0,
        chunk_type: str = "text",
        page_number: Optional[int] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save a text chunk with optional embedding."""
        await self._ensure_table()

        has_embedding = embedding is not None and len(embedding) > 0

        async with self._pool.acquire() as conn:
            if has_embedding:
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await conn.execute("""
                    INSERT INTO text_chunks
                    (id, document_id, chunk_index, content, content_length,
                     chunk_type, page_number, embedding, has_embedding, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9, $10::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        has_embedding = EXCLUDED.has_embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, chunk_id, document_id, chunk_index, content, len(content),
                    chunk_type, page_number, embedding_str, has_embedding,
                    str(metadata or {}).replace("'", '"'))
            else:
                await conn.execute("""
                    INSERT INTO text_chunks
                    (id, document_id, chunk_index, content, content_length,
                     chunk_type, page_number, has_embedding, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        has_embedding = EXCLUDED.has_embedding,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, chunk_id, document_id, chunk_index, content, len(content),
                    chunk_type, page_number, has_embedding,
                    str(metadata or {}).replace("'", '"'))

        return chunk_id

    async def save_chunks_batch(
        self,
        chunks: List[Dict[str, Any]],
        document_id: str
    ) -> int:
        """Save multiple chunks at once."""
        await self._ensure_table()
        saved = 0

        for chunk in chunks:
            try:
                await self.save_chunk(
                    chunk_id=chunk.get("id"),
                    document_id=document_id,
                    content=chunk.get("content", ""),
                    chunk_index=chunk.get("index", 0),
                    chunk_type=chunk.get("chunk_type", "text"),
                    page_number=chunk.get("page_number"),
                    embedding=chunk.get("embedding"),
                    metadata=chunk.get("metadata")
                )
                saved += 1
            except Exception as e:
                logger.error(f"Failed to save chunk {chunk.get('id')}: {e}")

        return saved

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        min_similarity: float = 0.3,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using cosine similarity."""
        await self._ensure_table()

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        async with self._pool.acquire() as conn:
            if document_id:
                rows = await conn.fetch("""
                    SELECT
                        id, document_id, chunk_index, content, content_length,
                        chunk_type, page_number, metadata,
                        1 - (embedding <=> $1::vector) as similarity
                    FROM text_chunks
                    WHERE has_embedding = TRUE
                      AND document_id = $4
                      AND 1 - (embedding <=> $1::vector) >= $3
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, limit, min_similarity, document_id)
            else:
                rows = await conn.fetch("""
                    SELECT
                        id, document_id, chunk_index, content, content_length,
                        chunk_type, page_number, metadata,
                        1 - (embedding <=> $1::vector) as similarity
                    FROM text_chunks
                    WHERE has_embedding = TRUE
                      AND 1 - (embedding <=> $1::vector) >= $3
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, limit, min_similarity)

            results = []
            for row in rows:
                results.append({
                    "chunk_id": row["id"],
                    "document_id": row["document_id"],
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                    "content_length": row["content_length"],
                    "chunk_type": row["chunk_type"],
                    "page_number": row["page_number"],
                    "metadata": row["metadata"],
                    "similarity": float(row["similarity"])
                })

            return results

    async def get_chunks_by_document(
        self,
        document_id: str
    ) -> List[Dict[str, Any]]:
        """Get all chunks for a document."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, document_id, chunk_index, content, content_length,
                       chunk_type, page_number, has_embedding, metadata
                FROM text_chunks
                WHERE document_id = $1
                ORDER BY chunk_index
            """, document_id)

            return [dict(row) for row in rows]

    async def delete_document_chunks(self, document_id: str) -> int:
        """Delete all chunks for a document."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM text_chunks WHERE document_id = $1
            """, document_id)
            count = int(result.split()[-1])
            return count

    async def get_stats(self) -> Dict[str, Any]:
        """Get repository statistics."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_chunks,
                    COUNT(*) FILTER (WHERE has_embedding = TRUE) as embedded_chunks,
                    COUNT(DISTINCT document_id) as total_documents,
                    SUM(content_length) as total_content_length
                FROM text_chunks
            """)

            return {
                "total_chunks": row["total_chunks"],
                "embedded_chunks": row["embedded_chunks"],
                "total_documents": row["total_documents"],
                "total_content_length": row["total_content_length"] or 0
            }
