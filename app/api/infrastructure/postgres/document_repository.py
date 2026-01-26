"""
PostgreSQL Document Repository
Stores document metadata for persistence across server restarts.
"""
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _json_serializer(obj):
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class PostgresDocumentRepository:
    """
    Repository for storing document metadata in PostgreSQL.
    """

    def __init__(self, pool):
        """Initialize with asyncpg connection pool."""
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        """Ensure the documents table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            # Create table for documents
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    mime_type TEXT,
                    document_type TEXT DEFAULT 'text',
                    status TEXT DEFAULT 'processing',
                    chunks_count INTEGER DEFAULT 0,
                    entities_count INTEGER DEFAULT 0,
                    embedding_status TEXT DEFAULT 'pending',
                    language TEXT DEFAULT 'auto',
                    tags JSONB DEFAULT '[]',
                    processing_mode TEXT DEFAULT 'text_only',
                    vlm_processed BOOLEAN DEFAULT FALSE,
                    stats JSONB,
                    processing_info JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_status
                ON documents(status)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_created_at
                ON documents(created_at DESC)
            """)

            logger.info("documents table initialized")
            self._initialized = True

    async def save_document(
        self,
        doc_id: str,
        filename: str,
        original_name: str,
        file_size: int,
        mime_type: str,
        document_type: str = "text",
        status: str = "processing",
        language: str = "auto",
        tags: Optional[List[str]] = None,
        processing_mode: str = "text_only",
        vlm_processed: bool = False,
        chunks_count: int = 0,
        entities_count: int = 0,
        embedding_status: str = "pending",
        stats: Optional[Dict[str, Any]] = None,
        processing_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save or update document metadata."""
        await self._ensure_table()

        tags_json = json.dumps(tags or [])
        stats_json = json.dumps(stats, default=_json_serializer) if stats else None
        processing_info_json = json.dumps(processing_info, default=_json_serializer) if processing_info else None

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO documents
                (id, filename, original_name, file_size, mime_type, document_type,
                 status, chunks_count, entities_count, embedding_status,
                 language, tags, processing_mode, vlm_processed, stats, processing_info)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13, $14, $15::jsonb, $16::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    filename = EXCLUDED.filename,
                    status = EXCLUDED.status,
                    chunks_count = EXCLUDED.chunks_count,
                    entities_count = EXCLUDED.entities_count,
                    embedding_status = EXCLUDED.embedding_status,
                    vlm_processed = EXCLUDED.vlm_processed,
                    stats = EXCLUDED.stats,
                    processing_info = EXCLUDED.processing_info,
                    updated_at = NOW()
            """, doc_id, filename, original_name, file_size, mime_type, document_type,
                status, chunks_count, entities_count, embedding_status,
                language, tags_json, processing_mode, vlm_processed, stats_json, processing_info_json)

        return doc_id

    async def update_status(
        self,
        doc_id: str,
        status: str,
        chunks_count: int = None,
        entities_count: int = None,
        embedding_status: str = None,
        vlm_processed: bool = None,
        stats: Dict[str, Any] = None,
        processing_info: Dict[str, Any] = None
    ):
        """Update document status and related fields."""
        await self._ensure_table()

        updates = ["status = $2", "updated_at = NOW()"]
        params = [doc_id, status]
        param_idx = 3

        if chunks_count is not None:
            updates.append(f"chunks_count = ${param_idx}")
            params.append(chunks_count)
            param_idx += 1

        if entities_count is not None:
            updates.append(f"entities_count = ${param_idx}")
            params.append(entities_count)
            param_idx += 1

        if embedding_status is not None:
            updates.append(f"embedding_status = ${param_idx}")
            params.append(embedding_status)
            param_idx += 1

        if vlm_processed is not None:
            updates.append(f"vlm_processed = ${param_idx}")
            params.append(vlm_processed)
            param_idx += 1

        if stats is not None:
            updates.append(f"stats = ${param_idx}::jsonb")
            params.append(json.dumps(stats, default=_json_serializer))
            param_idx += 1

        if processing_info is not None:
            updates.append(f"processing_info = ${param_idx}::jsonb")
            params.append(json.dumps(processing_info, default=_json_serializer))
            param_idx += 1

        query = f"UPDATE documents SET {', '.join(updates)} WHERE id = $1"

        async with self._pool.acquire() as conn:
            await conn.execute(query, *params)

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM documents WHERE id = $1",
                doc_id
            )

            if row:
                return self._row_to_dict(row)
            return None

    async def list_documents(
        self,
        page: int = 1,
        limit: int = 20,
        search: str = None,
        status: str = None,
        document_type: str = None
    ) -> Dict[str, Any]:
        """List documents with filtering and pagination."""
        await self._ensure_table()

        conditions = []
        params = []
        param_idx = 1

        if search:
            conditions.append(f"(filename ILIKE ${param_idx} OR original_name ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        if status and status != "all":
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if document_type:
            conditions.append(f"document_type = ${param_idx}")
            params.append(document_type)
            param_idx += 1

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        async with self._pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM documents{where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            offset = (page - 1) * limit
            params.extend([limit, offset])
            query = f"""
                SELECT * FROM documents{where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            rows = await conn.fetch(query, *params)

            documents = [self._row_to_dict(row) for row in rows]

            return {
                "documents": documents,
                "total": total
            }

    async def delete_document(self, doc_id: str) -> bool:
        """Delete document by ID."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE id = $1",
                doc_id
            )
            return "DELETE 1" in result

    async def get_all_documents_dict(self) -> Dict[str, Dict[str, Any]]:
        """Get all documents as a dictionary (for cache loading)."""
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            # Mark stale "processing" documents as "interrupted" on startup
            # These documents were being processed when server was shut down
            await conn.execute("""
                UPDATE documents
                SET status = 'interrupted', updated_at = NOW()
                WHERE status = 'processing'
            """)

            rows = await conn.fetch("SELECT * FROM documents")

            return {
                row['id']: self._row_to_dict(row)
                for row in rows
            }

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row['id'],
            "filename": row['filename'],
            "original_name": row['original_name'],
            "file_size": row['file_size'],
            "mime_type": row['mime_type'],
            "document_type": row['document_type'],
            "status": row['status'],
            "chunks_count": row['chunks_count'],
            "entities_count": row['entities_count'],
            "embedding_status": row['embedding_status'],
            "language": row['language'],
            "tags": row['tags'] if row['tags'] else [],
            "processing_mode": row['processing_mode'],
            "vlm_processed": row['vlm_processed'],
            "stats": row['stats'] if row['stats'] else None,
            "processing_info": row['processing_info'] if row['processing_info'] else None,
            "created_at": row['created_at'],
            "updated_at": row['updated_at']
        }


# Singleton instance
_document_repository: Optional[PostgresDocumentRepository] = None


async def get_document_repository() -> PostgresDocumentRepository:
    """Get or create document repository singleton."""
    global _document_repository

    if _document_repository is None:
        import asyncpg
        from ...core.config import api_settings

        dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        _document_repository = PostgresDocumentRepository(pool)
        await _document_repository._ensure_table()
        logger.info("Document repository initialized")

    return _document_repository
