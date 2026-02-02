"""
PostgreSQL Text Chunk Repository
Stores text chunks with embeddings for RAG using pgvector.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# H3: Metadata search constants
METADATA_SEARCH_DEFAULT_LIMIT = 100


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

    # =========================================================================
    # H3: Metadata-based search methods (optimized with indexes)
    # =========================================================================

    async def search_by_metadata(
        self,
        document_id: Optional[str] = None,
        section_path: Optional[str] = None,
        page_range: Optional[Tuple[int, int]] = None,
        chunk_type: Optional[str] = None,
        limit: int = METADATA_SEARCH_DEFAULT_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Search chunks by metadata fields using indexed columns.

        Uses generated column indexes for fast filtering:
        - section_path: B-tree index on generated column
        - page_number: B-tree index
        - chunk_type: B-tree index with partial indexes

        Args:
            document_id: Filter by document
            section_path: Filter by section (prefix match supported, e.g., "2.3")
            page_range: Filter by page range (start, end) inclusive
            chunk_type: Filter by chunk type (text, error_code, table, etc.)
            limit: Maximum results to return

        Returns:
            List of chunk dictionaries ordered by chunk_index
        """
        await self._ensure_table()

        conditions = []
        params = []
        param_idx = 1

        if document_id:
            conditions.append(f"document_id = ${param_idx}")
            params.append(document_id)
            param_idx += 1

        if section_path:
            # Prefix match for hierarchical sections (e.g., "2.3" matches "2.3.1", "2.3.2")
            conditions.append(f"section_path LIKE ${param_idx}")
            params.append(f"{section_path}%")
            param_idx += 1

        if page_range:
            start_page, end_page = page_range
            conditions.append(f"page_number >= ${param_idx}")
            params.append(start_page)
            param_idx += 1
            conditions.append(f"page_number <= ${param_idx}")
            params.append(end_page)
            param_idx += 1

        if chunk_type:
            conditions.append(f"chunk_type = ${param_idx}")
            params.append(chunk_type)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        query = f"""
            SELECT id, document_id, chunk_index, content, content_length,
                   chunk_type, page_number, section_path, has_embedding, metadata
            FROM text_chunks
            WHERE {where_clause}
            ORDER BY chunk_index
            LIMIT ${param_idx}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def search_by_jsonb_metadata(
        self,
        metadata_filter: Dict[str, Any],
        document_id: Optional[str] = None,
        limit: int = METADATA_SEARCH_DEFAULT_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Search chunks using JSONB containment operator (@>).

        Uses GIN index (idx_text_chunks_metadata_gin) for fast JSONB queries.

        Args:
            metadata_filter: JSONB filter dict (e.g., {"source": "manual", "language": "ja"})
            document_id: Optional document filter
            limit: Maximum results

        Returns:
            List of matching chunks
        """
        await self._ensure_table()

        import json
        filter_json = json.dumps(metadata_filter)

        async with self._pool.acquire() as conn:
            if document_id:
                rows = await conn.fetch("""
                    SELECT id, document_id, chunk_index, content, content_length,
                           chunk_type, page_number, has_embedding, metadata
                    FROM text_chunks
                    WHERE metadata @> $1::jsonb
                      AND document_id = $2
                    ORDER BY chunk_index
                    LIMIT $3
                """, filter_json, document_id, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, document_id, chunk_index, content, content_length,
                           chunk_type, page_number, has_embedding, metadata
                    FROM text_chunks
                    WHERE metadata @> $1::jsonb
                    ORDER BY chunk_index
                    LIMIT $2
                """, filter_json, limit)

            return [dict(row) for row in rows]

    async def get_chunks_by_section(
        self,
        document_id: str,
        section_path: str,
        include_subsections: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks in a specific section.

        Args:
            document_id: Document ID
            section_path: Section path (e.g., "2.3.1")
            include_subsections: If True, includes "2.3.1.1", "2.3.1.2", etc.

        Returns:
            List of chunks in the section
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if include_subsections:
                # Prefix match for subsections
                rows = await conn.fetch("""
                    SELECT id, document_id, chunk_index, content, content_length,
                           chunk_type, page_number, section_path, has_embedding, metadata
                    FROM text_chunks
                    WHERE document_id = $1
                      AND section_path LIKE $2
                    ORDER BY chunk_index
                """, document_id, f"{section_path}%")
            else:
                # Exact match only
                rows = await conn.fetch("""
                    SELECT id, document_id, chunk_index, content, content_length,
                           chunk_type, page_number, section_path, has_embedding, metadata
                    FROM text_chunks
                    WHERE document_id = $1
                      AND section_path = $2
                    ORDER BY chunk_index
                """, document_id, section_path)

            return [dict(row) for row in rows]

    async def get_chunks_by_page_range(
        self,
        document_id: str,
        start_page: int,
        end_page: int
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks within a page range.

        Args:
            document_id: Document ID
            start_page: Start page (inclusive)
            end_page: End page (inclusive)

        Returns:
            List of chunks in the page range
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, document_id, chunk_index, content, content_length,
                       chunk_type, page_number, has_embedding, metadata
                FROM text_chunks
                WHERE document_id = $1
                  AND page_number >= $2
                  AND page_number <= $3
                ORDER BY page_number, chunk_index
            """, document_id, start_page, end_page)

            return [dict(row) for row in rows]

    async def get_error_code_chunks(
        self,
        document_id: Optional[str] = None,
        limit: int = METADATA_SEARCH_DEFAULT_LIMIT
    ) -> List[Dict[str, Any]]:
        """
        Get all error code chunks (uses partial index for fast access).

        Returns:
            List of error code chunks
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if document_id:
                rows = await conn.fetch("""
                    SELECT id, document_id, chunk_index, content, content_length,
                           chunk_type, page_number, has_embedding, metadata
                    FROM text_chunks
                    WHERE chunk_type = 'error_code'
                      AND document_id = $1
                    ORDER BY chunk_index
                    LIMIT $2
                """, document_id, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, document_id, chunk_index, content, content_length,
                           chunk_type, page_number, has_embedding, metadata
                    FROM text_chunks
                    WHERE chunk_type = 'error_code'
                    ORDER BY document_id, chunk_index
                    LIMIT $1
                """, limit)

            return [dict(row) for row in rows]

    async def vector_search_with_filters(
        self,
        query_embedding: List[float],
        limit: int = 10,
        min_similarity: float = 0.3,
        document_ids: Optional[List[str]] = None,
        section_path: Optional[str] = None,
        chunk_type: Optional[str] = None,
        page_range: Optional[Tuple[int, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search with metadata filters.

        Combines vector search with metadata filtering for precise results.

        Args:
            query_embedding: Query vector (4096 dimensions)
            limit: Maximum results
            min_similarity: Minimum cosine similarity (0-1)
            document_ids: Filter by document IDs
            section_path: Filter by section (prefix match)
            chunk_type: Filter by chunk type
            page_range: Filter by page range

        Returns:
            List of similar chunks with similarity scores
        """
        await self._ensure_table()

        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        conditions = ["has_embedding = TRUE"]
        params = [embedding_str, min_similarity]
        param_idx = 3

        if document_ids:
            conditions.append(f"document_id = ANY(${param_idx})")
            params.append(document_ids)
            param_idx += 1

        if section_path:
            conditions.append(f"section_path LIKE ${param_idx}")
            params.append(f"{section_path}%")
            param_idx += 1

        if chunk_type:
            conditions.append(f"chunk_type = ${param_idx}")
            params.append(chunk_type)
            param_idx += 1

        if page_range:
            conditions.append(f"page_number >= ${param_idx}")
            params.append(page_range[0])
            param_idx += 1
            conditions.append(f"page_number <= ${param_idx}")
            params.append(page_range[1])
            param_idx += 1

        params.append(limit)
        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                id, document_id, chunk_index, content, content_length,
                chunk_type, page_number, section_path, metadata,
                1 - (embedding <=> $1::vector) as similarity
            FROM text_chunks
            WHERE {where_clause}
              AND 1 - (embedding <=> $1::vector) >= $2
            ORDER BY embedding <=> $1::vector
            LIMIT ${param_idx}
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

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
                    "section_path": row.get("section_path"),
                    "metadata": row["metadata"],
                    "similarity": float(row["similarity"])
                })

            return results
