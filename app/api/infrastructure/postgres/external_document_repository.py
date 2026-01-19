"""
PostgreSQL External Document Repository

Stores document metadata from external sources (Notion, GitHub, Google Drive, etc.)
Keeps external documents completely isolated from internal admin-uploaded documents.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

import asyncpg
from asyncpg import Pool

logger = logging.getLogger(__name__)


def _json_serializer(obj):
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class PostgresExternalDocumentRepository:
    """
    PostgreSQL repository for external documents.

    Handles persistence of:
    - Document metadata from external sources
    - Content sections and text
    - Processing status and sync tracking
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
        """Ensure the external_documents table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'external_documents'
                )
            """)

            if not result:
                logger.warning("external_documents table does not exist - run migration 020")
                # Create table as fallback
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS external_documents (
                        id VARCHAR(50) PRIMARY KEY,
                        user_id UUID NOT NULL,
                        connection_id VARCHAR(50) NOT NULL,
                        source VARCHAR(50) NOT NULL,
                        external_id VARCHAR(500),
                        external_url TEXT,
                        title VARCHAR(500),
                        path TEXT,
                        mime_type VARCHAR(100),
                        file_size INTEGER,
                        sections JSONB DEFAULT '[]',
                        text_content TEXT,
                        content_hash VARCHAR(64),
                        metadata JSONB DEFAULT '{}',
                        status VARCHAR(50) DEFAULT 'discovered',
                        error_message TEXT,
                        chunk_count INTEGER DEFAULT 0,
                        external_modified_at TIMESTAMP WITH TIME ZONE,
                        last_synced_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ext_doc_user_id
                    ON external_documents(user_id)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ext_doc_connection_id
                    ON external_documents(connection_id)
                """)
                await conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_doc_conn_external
                    ON external_documents(connection_id, external_id)
                """)

            self._initialized = True
            logger.info("External document repository initialized")

    async def create(
        self,
        id: str,
        user_id: str,
        connection_id: str,
        source: str,
        external_id: str,
        title: str,
        external_url: Optional[str] = None,
        path: Optional[str] = None,
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
        sections: Optional[List[Dict]] = None,
        text_content: Optional[str] = None,
        content_hash: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "discovered",
        external_modified_at: Optional[datetime] = None
    ) -> str:
        """
        Create a new external document.

        Args:
            id: Document ID
            user_id: User UUID (string)
            connection_id: Parent connection ID
            source: External resource type
            external_id: Original ID from external source
            title: Document title
            external_url: Link to original document
            path: Path in external source
            mime_type: MIME type
            file_size: File size in bytes
            sections: Document sections
            text_content: Full text content
            content_hash: Content hash for change detection
            metadata: Additional metadata
            status: Processing status
            external_modified_at: Last modified in external source

        Returns:
            Document ID
        """
        await self._ensure_table()

        sections_json = json.dumps(sections or [], default=_json_serializer)
        metadata_json = json.dumps(metadata or {}, default=_json_serializer)

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO external_documents
                (id, user_id, connection_id, source, external_id, title,
                 external_url, path, mime_type, file_size, sections, text_content,
                 content_hash, metadata, status, external_modified_at,
                 created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
                        $11::jsonb, $12, $13, $14::jsonb, $15, $16, NOW(), NOW())
            """, id, user_id, connection_id, source, external_id, title,
                external_url, path, mime_type, file_size, sections_json, text_content,
                content_hash, metadata_json, status, external_modified_at)

        logger.info(f"Created external document: {id} (title: {title})")
        return id

    async def get(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a document by ID.

        Args:
            document_id: Document ID

        Returns:
            Document data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM external_documents WHERE id = $1",
                document_id
            )

            if row:
                return self._row_to_dict(row)
            return None

    async def get_by_connection(
        self,
        connection_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get documents for a connection with pagination.

        Args:
            connection_id: Connection ID
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            Tuple of (documents list, total count)
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            # Get total count
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM external_documents WHERE connection_id = $1",
                connection_id
            )

            # Get paginated results
            rows = await conn.fetch("""
                SELECT * FROM external_documents
                WHERE connection_id = $1
                ORDER BY title ASC
                LIMIT $2 OFFSET $3
            """, connection_id, limit, offset)

            return [self._row_to_dict(row) for row in rows], total

    async def get_by_user(
        self,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get documents for a user.

        Args:
            user_id: User UUID (string)
            status: Optional status filter
            limit: Maximum results

        Returns:
            List of document data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if status:
                rows = await conn.fetch("""
                    SELECT * FROM external_documents
                    WHERE user_id = $1::uuid AND status = $2
                    ORDER BY updated_at DESC
                    LIMIT $3
                """, user_id, status, limit)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM external_documents
                    WHERE user_id = $1::uuid
                    ORDER BY updated_at DESC
                    LIMIT $2
                """, user_id, limit)

            return [self._row_to_dict(row) for row in rows]

    async def get_by_external_id(
        self,
        connection_id: str,
        external_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get document by connection and external ID.

        Args:
            connection_id: Connection ID
            external_id: Original ID from external source

        Returns:
            Document data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM external_documents
                WHERE connection_id = $1 AND external_id = $2
            """, connection_id, external_id)

            if row:
                return self._row_to_dict(row)
            return None

    async def update(
        self,
        document_id: str,
        **kwargs
    ) -> bool:
        """
        Update a document.

        Args:
            document_id: Document ID
            **kwargs: Fields to update

        Returns:
            True if updated
        """
        await self._ensure_table()

        if not kwargs:
            return False

        # Build dynamic UPDATE query
        updates = []
        params = [document_id]
        param_idx = 2

        allowed_fields = {
            "title", "path", "external_url", "mime_type", "file_size",
            "sections", "text_content", "content_hash", "metadata",
            "status", "error_message", "chunk_count",
            "external_modified_at", "last_synced_at"
        }

        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue

            if key in ("sections", "metadata") and isinstance(value, (list, dict)):
                updates.append(f"{key} = ${param_idx}::jsonb")
                params.append(json.dumps(value, default=_json_serializer))
            else:
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
            param_idx += 1

        if not updates:
            return False

        updates.append("updated_at = NOW()")
        query = f"UPDATE external_documents SET {', '.join(updates)} WHERE id = $1"

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def update_content(
        self,
        document_id: str,
        sections: Optional[List[Dict]] = None,
        text_content: Optional[str] = None,
        content_hash: Optional[str] = None,
        status: str = "ready",
        chunk_count: int = 0,
        last_synced_at: Optional[datetime] = None
    ) -> bool:
        """
        Update document content after processing.

        Args:
            document_id: Document ID
            sections: Document sections
            text_content: Full text content
            content_hash: Content hash
            status: Processing status
            chunk_count: Number of chunks created
            last_synced_at: Last sync timestamp

        Returns:
            True if updated
        """
        await self._ensure_table()

        sections_json = json.dumps(sections or [], default=_json_serializer)

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE external_documents
                SET sections = $2::jsonb,
                    text_content = $3,
                    content_hash = $4,
                    status = $5,
                    chunk_count = $6,
                    last_synced_at = $7,
                    updated_at = NOW()
                WHERE id = $1
            """, document_id, sections_json, text_content, content_hash,
                status, chunk_count, last_synced_at or datetime.now(timezone.utc))
            return "UPDATE 1" in result

    async def update_status(
        self,
        document_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update document processing status.

        Args:
            document_id: Document ID
            status: New status
            error_message: Error message (if any)

        Returns:
            True if updated
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE external_documents
                SET status = $2, error_message = $3, updated_at = NOW()
                WHERE id = $1
            """, document_id, status, error_message)
            return "UPDATE 1" in result

    async def delete(self, document_id: str) -> bool:
        """
        Delete a document.

        Args:
            document_id: Document ID

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM external_documents WHERE id = $1",
                document_id
            )
            return "DELETE 1" in result

    async def delete_by_connection(self, connection_id: str) -> int:
        """
        Delete all documents for a connection.

        Args:
            connection_id: Connection ID

        Returns:
            Number of documents deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM external_documents WHERE connection_id = $1",
                connection_id
            )
            # Extract count from result like "DELETE 5"
            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0

    async def count_by_connection(self, connection_id: str) -> int:
        """
        Count documents for a connection.

        Args:
            connection_id: Connection ID

        Returns:
            Document count
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM external_documents WHERE connection_id = $1",
                connection_id
            )

    async def get_all_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all documents as a dictionary (for cache loading).

        Returns:
            Dictionary of document_id -> document data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM external_documents")

            return {
                row['id']: self._row_to_dict(row)
                for row in rows
            }

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row["id"],
            "user_id": str(row["user_id"]),
            "connection_id": row["connection_id"],
            "source": row["source"],
            "external_id": row["external_id"],
            "external_url": row["external_url"],
            "title": row["title"],
            "path": row["path"],
            "mime_type": row["mime_type"],
            "file_size": row["file_size"],
            "sections": row["sections"] or [],
            "text_content": row["text_content"],
            "content_hash": row["content_hash"],
            "metadata": row["metadata"] or {},
            "status": row["status"],
            "error_message": row["error_message"],
            "chunk_count": row["chunk_count"],
            "external_modified_at": row["external_modified_at"],
            "last_synced_at": row["last_synced_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }


# Singleton instance
_document_repository: Optional[PostgresExternalDocumentRepository] = None


async def get_external_document_repository(
    pool: Optional[Pool] = None
) -> PostgresExternalDocumentRepository:
    """
    Get or create external document repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresExternalDocumentRepository instance
    """
    global _document_repository

    if _document_repository is None:
        if pool is None:
            import asyncpg
            from ...core.config import api_settings

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)

        _document_repository = PostgresExternalDocumentRepository(pool)
        await _document_repository._ensure_table()
        logger.info("External document repository initialized")

    return _document_repository
