"""
PostgreSQL External Chunk Repository

Stores chunk metadata for external documents.
Actual embeddings are stored in Neo4j :ExternalChunk nodes.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import asyncpg
from asyncpg import Pool

logger = logging.getLogger(__name__)


def _json_serializer(obj):
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class PostgresExternalChunkRepository:
    """
    PostgreSQL repository for external chunks.

    Handles persistence of:
    - Chunk content and metadata
    - Source information
    - Embedding status tracking (actual vectors in Neo4j)
    """

    def __init__(self, pool: Pool):
        """
        Initialize with asyncpg connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        """Ensure the external_chunks table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'external_chunks'
                )
            """)

            if not result:
                logger.warning("external_chunks table does not exist - run migration 020")
                # Create table as fallback
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS external_chunks (
                        id VARCHAR(50) PRIMARY KEY,
                        user_id UUID NOT NULL,
                        document_id VARCHAR(50) NOT NULL,
                        connection_id VARCHAR(50) NOT NULL,
                        content TEXT NOT NULL,
                        chunk_index INTEGER DEFAULT 0,
                        source VARCHAR(50),
                        source_name VARCHAR(500),
                        source_url TEXT,
                        section_title VARCHAR(500),
                        page_number INTEGER,
                        is_code BOOLEAN DEFAULT FALSE,
                        is_table BOOLEAN DEFAULT FALSE,
                        embedding_stored BOOLEAN DEFAULT FALSE,
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ext_chunk_user_id
                    ON external_chunks(user_id)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ext_chunk_document_id
                    ON external_chunks(document_id)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ext_chunk_connection_id
                    ON external_chunks(connection_id)
                """)

            self._initialized = True
            logger.info("External chunk repository initialized")

    async def create(
        self,
        id: str,
        user_id: str,
        document_id: str,
        connection_id: str,
        content: str,
        chunk_index: int = 0,
        source: Optional[str] = None,
        source_name: Optional[str] = None,
        source_url: Optional[str] = None,
        section_title: Optional[str] = None,
        page_number: Optional[int] = None,
        is_code: bool = False,
        is_table: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new external chunk.

        Args:
            id: Chunk ID
            user_id: User UUID (string)
            document_id: Parent document ID
            connection_id: Parent connection ID
            content: Chunk text content
            chunk_index: Index of chunk in document
            source: External resource type
            source_name: Document title
            source_url: Link to original document
            section_title: Section this chunk belongs to
            page_number: Page number (if applicable)
            is_code: Whether this is code content
            is_table: Whether this is table content
            metadata: Additional metadata

        Returns:
            Chunk ID
        """
        await self._ensure_table()

        metadata_json = json.dumps(metadata or {}, default=_json_serializer)

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO external_chunks
                (id, user_id, document_id, connection_id, content, chunk_index,
                 source, source_name, source_url, section_title, page_number,
                 is_code, is_table, metadata, created_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW())
            """, id, user_id, document_id, connection_id, content, chunk_index,
                source, source_name, source_url, section_title, page_number,
                is_code, is_table, metadata_json)

        return id

    async def create_batch(
        self,
        chunks: List[Dict[str, Any]]
    ) -> int:
        """
        Create multiple chunks in batch.

        Args:
            chunks: List of chunk dictionaries

        Returns:
            Number of chunks created
        """
        await self._ensure_table()

        if not chunks:
            return 0

        async with self._pool.acquire() as conn:
            # Use executemany for batch insert
            values = [
                (
                    c["id"],
                    c["user_id"],
                    c["document_id"],
                    c["connection_id"],
                    c["content"],
                    c.get("chunk_index", 0),
                    c.get("source"),
                    c.get("source_name"),
                    c.get("source_url"),
                    c.get("section_title"),
                    c.get("page_number"),
                    c.get("is_code", False),
                    c.get("is_table", False),
                    json.dumps(c.get("metadata", {}), default=_json_serializer)
                )
                for c in chunks
            ]

            await conn.executemany("""
                INSERT INTO external_chunks
                (id, user_id, document_id, connection_id, content, chunk_index,
                 source, source_name, source_url, section_title, page_number,
                 is_code, is_table, metadata, created_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW())
            """, values)

        logger.info(f"Created {len(chunks)} external chunks")
        return len(chunks)

    async def get(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            Chunk data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM external_chunks WHERE id = $1",
                chunk_id
            )

            if row:
                return self._row_to_dict(row)
            return None

    async def get_by_document(
        self,
        document_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a document.

        Args:
            document_id: Document ID

        Returns:
            List of chunk data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM external_chunks
                WHERE document_id = $1
                ORDER BY chunk_index ASC
            """, document_id)

            return [self._row_to_dict(row) for row in rows]

    async def get_by_connection(
        self,
        connection_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a connection.

        Args:
            connection_id: Connection ID

        Returns:
            List of chunk data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM external_chunks
                WHERE connection_id = $1
                ORDER BY document_id, chunk_index ASC
            """, connection_id)

            return [self._row_to_dict(row) for row in rows]

    async def get_by_user(
        self,
        user_id: str,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get all chunks for a user.

        Args:
            user_id: User UUID (string)
            limit: Maximum results

        Returns:
            List of chunk data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM external_chunks
                WHERE user_id = $1::uuid
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)

            return [self._row_to_dict(row) for row in rows]

    async def mark_embedding_stored(self, chunk_id: str) -> bool:
        """
        Mark a chunk as having its embedding stored in Neo4j.

        Args:
            chunk_id: Chunk ID

        Returns:
            True if updated
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE external_chunks SET embedding_stored = TRUE WHERE id = $1",
                chunk_id
            )
            return "UPDATE 1" in result

    async def mark_embeddings_stored_batch(self, chunk_ids: List[str]) -> int:
        """
        Mark multiple chunks as having embeddings stored.

        Args:
            chunk_ids: List of chunk IDs

        Returns:
            Number of chunks updated
        """
        await self._ensure_table()

        if not chunk_ids:
            return 0

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE external_chunks
                SET embedding_stored = TRUE
                WHERE id = ANY($1::varchar[])
            """, chunk_ids)

            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0

    async def delete(self, chunk_id: str) -> bool:
        """
        Delete a chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM external_chunks WHERE id = $1",
                chunk_id
            )
            return "DELETE 1" in result

    async def delete_by_document(self, document_id: str) -> int:
        """
        Delete all chunks for a document.

        Args:
            document_id: Document ID

        Returns:
            Number of chunks deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM external_chunks WHERE document_id = $1",
                document_id
            )
            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0

    async def delete_by_connection(self, connection_id: str) -> int:
        """
        Delete all chunks for a connection.

        Args:
            connection_id: Connection ID

        Returns:
            Number of chunks deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM external_chunks WHERE connection_id = $1",
                connection_id
            )
            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0

    async def count_by_document(self, document_id: str) -> int:
        """
        Count chunks for a document.

        Args:
            document_id: Document ID

        Returns:
            Chunk count
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM external_chunks WHERE document_id = $1",
                document_id
            )

    async def count_by_connection(self, connection_id: str) -> int:
        """
        Count chunks for a connection.

        Args:
            connection_id: Connection ID

        Returns:
            Chunk count
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM external_chunks WHERE connection_id = $1",
                connection_id
            )

    async def count_by_user(self, user_id: str) -> int:
        """
        Count chunks for a user.

        Args:
            user_id: User UUID (string)

        Returns:
            Chunk count
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM external_chunks WHERE user_id = $1::uuid",
                user_id
            )

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get chunk statistics for a user.

        Args:
            user_id: User UUID (string)

        Returns:
            Dictionary with stats by connection
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    connection_id,
                    COUNT(*) AS chunk_count,
                    SUM(CASE WHEN embedding_stored THEN 1 ELSE 0 END) AS embedded_count
                FROM external_chunks
                WHERE user_id = $1::uuid
                GROUP BY connection_id
            """, user_id)

            connections = {}
            total_chunks = 0
            total_embedded = 0

            for row in rows:
                connections[row["connection_id"]] = {
                    "chunk_count": row["chunk_count"],
                    "embedded_count": row["embedded_count"]
                }
                total_chunks += row["chunk_count"]
                total_embedded += row["embedded_count"]

            return {
                "total_chunks": total_chunks,
                "total_embedded": total_embedded,
                "connections": connections
            }

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row["id"],
            "user_id": str(row["user_id"]),
            "document_id": row["document_id"],
            "connection_id": row["connection_id"],
            "content": row["content"],
            "chunk_index": row["chunk_index"],
            "source": row["source"],
            "source_name": row["source_name"],
            "source_url": row["source_url"],
            "section_title": row["section_title"],
            "page_number": row["page_number"],
            "is_code": row["is_code"],
            "is_table": row["is_table"],
            "embedding_stored": row["embedding_stored"],
            "metadata": row["metadata"] or {},
            "created_at": row["created_at"]
        }


# Singleton instance
_chunk_repository: Optional[PostgresExternalChunkRepository] = None


async def get_external_chunk_repository(
    pool: Optional[Pool] = None
) -> PostgresExternalChunkRepository:
    """
    Get or create external chunk repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresExternalChunkRepository instance
    """
    global _chunk_repository

    if _chunk_repository is None:
        if pool is None:
            import asyncpg
            from ...core.config import api_settings

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)

        _chunk_repository = PostgresExternalChunkRepository(pool)
        await _chunk_repository._ensure_table()
        logger.info("External chunk repository initialized")

    return _chunk_repository
