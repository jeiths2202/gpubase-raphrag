"""
PostgreSQL Web Source Repository

Stores web source metadata and content for persistent RAG knowledge base.
Replaces in-memory storage in web_content_service.py.
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


class PostgresWebSourceRepository:
    """
    PostgreSQL repository for web sources.

    Handles persistence of:
    - Web source metadata (URL, domain, status)
    - Extracted content and text
    - Processing status and statistics
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
        """Ensure the web_sources table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'web_sources'
                )
            """)

            if not result:
                logger.warning("web_sources table does not exist - run migration 024")
                # Create table as fallback
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS web_sources (
                        id VARCHAR(50) PRIMARY KEY,
                        user_id UUID,
                        url TEXT NOT NULL,
                        display_name VARCHAR(500),
                        domain VARCHAR(255),
                        extractor VARCHAR(50) DEFAULT 'trafilatura',
                        include_images BOOLEAN DEFAULT FALSE,
                        include_links BOOLEAN DEFAULT FALSE,
                        status VARCHAR(50) DEFAULT 'pending',
                        http_status_code INTEGER,
                        error_message TEXT,
                        retry_count INTEGER DEFAULT 0,
                        extracted_text TEXT,
                        extracted_links JSONB DEFAULT '[]',
                        extracted_images JSONB DEFAULT '[]',
                        content_hash VARCHAR(64),
                        metadata JSONB DEFAULT '{}',
                        word_count INTEGER DEFAULT 0,
                        char_count INTEGER DEFAULT 0,
                        chunk_count INTEGER DEFAULT 0,
                        link_count INTEGER DEFAULT 0,
                        image_count INTEGER DEFAULT 0,
                        fetch_time_ms INTEGER DEFAULT 0,
                        extraction_time_ms INTEGER DEFAULT 0,
                        tags TEXT[] DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        fetched_at TIMESTAMPTZ,
                        processed_at TIMESTAMPTZ
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ws_user_id ON web_sources(user_id)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ws_status ON web_sources(status)
                """)
                await conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_url_user
                    ON web_sources(url, user_id)
                """)

            self._initialized = True
            logger.info("Web source repository initialized")

    async def create(
        self,
        id: str,
        url: str,
        display_name: str,
        domain: str,
        user_id: Optional[str] = None,
        extractor: str = "trafilatura",
        include_images: bool = False,
        include_links: bool = False,
        status: str = "pending",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new web source.

        Args:
            id: Web source ID (ws_xxxxxxxxxxxx)
            url: Source URL
            display_name: Display name
            domain: Domain from URL
            user_id: Owner user UUID
            extractor: Content extractor type
            include_images: Whether to extract images
            include_links: Whether to extract links
            status: Initial status
            tags: User-defined tags
            metadata: Additional metadata

        Returns:
            Web source ID
        """
        await self._ensure_table()

        metadata_json = json.dumps(metadata or {}, default=_json_serializer)

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO web_sources
                (id, user_id, url, display_name, domain, extractor,
                 include_images, include_links, status, tags, metadata,
                 created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, NOW(), NOW())
            """, id, user_id, url, display_name, domain, extractor,
                include_images, include_links, status, tags or [], metadata_json)

        logger.info(f"Created web source: {id} (url: {url})")
        return id

    async def get(self, web_source_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a web source by ID.

        Args:
            web_source_id: Web source ID

        Returns:
            Web source data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM web_sources WHERE id = $1",
                web_source_id
            )

            if row:
                return self._row_to_dict(row)
            return None

    async def get_by_url(
        self,
        url: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get web source by URL (optionally filtered by user).

        Args:
            url: Source URL
            user_id: Optional user UUID

        Returns:
            Web source data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if user_id:
                row = await conn.fetchrow("""
                    SELECT * FROM web_sources
                    WHERE url = $1 AND user_id = $2::uuid
                """, url, user_id)
            else:
                row = await conn.fetchrow("""
                    SELECT * FROM web_sources WHERE url = $1
                """, url)

            if row:
                return self._row_to_dict(row)
            return None

    async def list(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        tags: Optional[List[str]] = None,
        page: int = 1,
        limit: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List web sources with filtering and pagination.

        Args:
            user_id: Filter by user
            status: Filter by status
            domain: Filter by domain (partial match)
            tags: Filter by tags (any match)
            page: Page number (1-based)
            limit: Results per page

        Returns:
            Tuple of (web sources list, total count)
        """
        await self._ensure_table()

        # Build dynamic query
        conditions = []
        params = []
        param_idx = 1

        if user_id:
            conditions.append(f"user_id = ${param_idx}::uuid")
            params.append(user_id)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if domain:
            conditions.append(f"LOWER(domain) LIKE LOWER(${param_idx})")
            params.append(f"%{domain}%")
            param_idx += 1

        if tags:
            conditions.append(f"tags && ${param_idx}")
            params.append(tags)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        offset = (page - 1) * limit

        async with self._pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM web_sources WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            query = f"""
                SELECT * FROM web_sources
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)

            return [self._row_to_dict(row) for row in rows], total

    async def update(
        self,
        web_source_id: str,
        **kwargs
    ) -> bool:
        """
        Update a web source.

        Args:
            web_source_id: Web source ID
            **kwargs: Fields to update

        Returns:
            True if updated
        """
        await self._ensure_table()

        if not kwargs:
            return False

        # Build dynamic UPDATE query
        updates = []
        params = [web_source_id]
        param_idx = 2

        allowed_fields = {
            "display_name", "status", "http_status_code", "error_message",
            "retry_count", "extracted_text", "extracted_links", "extracted_images",
            "content_hash", "metadata", "word_count", "char_count", "chunk_count",
            "link_count", "image_count", "fetch_time_ms", "extraction_time_ms",
            "tags", "fetched_at", "processed_at"
        }

        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue

            if key in ("extracted_links", "extracted_images", "metadata"):
                if isinstance(value, (list, dict)):
                    updates.append(f"{key} = ${param_idx}::jsonb")
                    params.append(json.dumps(value, default=_json_serializer))
                else:
                    continue
            elif key == "tags" and isinstance(value, list):
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
            else:
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
            param_idx += 1

        if not updates:
            return False

        updates.append("updated_at = NOW()")
        query = f"UPDATE web_sources SET {', '.join(updates)} WHERE id = $1"

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def update_status(
        self,
        web_source_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Update web source processing status.

        Args:
            web_source_id: Web source ID
            status: New status
            error_message: Error message (if any)

        Returns:
            True if updated
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE web_sources
                SET status = $2, error_message = $3, updated_at = NOW()
                WHERE id = $1
            """, web_source_id, status, error_message)
            return "UPDATE 1" in result

    async def update_content(
        self,
        web_source_id: str,
        extracted_text: Optional[str] = None,
        extracted_links: Optional[List[Dict]] = None,
        extracted_images: Optional[List[Dict]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        content_hash: Optional[str] = None,
        word_count: int = 0,
        char_count: int = 0,
        chunk_count: int = 0,
        link_count: int = 0,
        image_count: int = 0,
        fetch_time_ms: int = 0,
        extraction_time_ms: int = 0,
        status: str = "ready",
        fetched_at: Optional[datetime] = None,
        processed_at: Optional[datetime] = None
    ) -> bool:
        """
        Update web source content after processing.

        Args:
            web_source_id: Web source ID
            extracted_text: Extracted text content
            extracted_links: Extracted links
            extracted_images: Extracted images
            metadata: Page metadata
            content_hash: Content hash
            word_count: Word count
            char_count: Character count
            chunk_count: Number of chunks
            link_count: Number of links
            image_count: Number of images
            fetch_time_ms: Fetch time in milliseconds
            extraction_time_ms: Extraction time in milliseconds
            status: New status
            fetched_at: Fetch timestamp
            processed_at: Processing timestamp

        Returns:
            True if updated
        """
        await self._ensure_table()

        links_json = json.dumps(extracted_links or [], default=_json_serializer)
        images_json = json.dumps(extracted_images or [], default=_json_serializer)
        metadata_json = json.dumps(metadata or {}, default=_json_serializer)

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE web_sources
                SET extracted_text = $2,
                    extracted_links = $3::jsonb,
                    extracted_images = $4::jsonb,
                    metadata = $5::jsonb,
                    content_hash = $6,
                    word_count = $7,
                    char_count = $8,
                    chunk_count = $9,
                    link_count = $10,
                    image_count = $11,
                    fetch_time_ms = $12,
                    extraction_time_ms = $13,
                    status = $14,
                    fetched_at = $15,
                    processed_at = $16,
                    updated_at = NOW()
                WHERE id = $1
            """, web_source_id, extracted_text, links_json, images_json,
                metadata_json, content_hash, word_count, char_count, chunk_count,
                link_count, image_count, fetch_time_ms, extraction_time_ms, status,
                fetched_at or datetime.now(timezone.utc),
                processed_at or datetime.now(timezone.utc))
            return "UPDATE 1" in result

    async def delete(self, web_source_id: str) -> bool:
        """
        Delete a web source.

        Args:
            web_source_id: Web source ID

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM web_sources WHERE id = $1",
                web_source_id
            )
            return "DELETE 1" in result

    async def delete_by_user(self, user_id: str) -> int:
        """
        Delete all web sources for a user.

        Args:
            user_id: User UUID

        Returns:
            Number of deleted web sources
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM web_sources WHERE user_id = $1::uuid",
                user_id
            )
            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0

    async def search(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search web sources by text content.

        Args:
            query: Search query
            user_id: Optional user filter
            limit: Maximum results

        Returns:
            List of matching web sources
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if user_id:
                rows = await conn.fetch("""
                    SELECT *, ts_rank(to_tsvector('simple', COALESCE(extracted_text, '')),
                                      plainto_tsquery('simple', $1)) as rank
                    FROM web_sources
                    WHERE user_id = $2::uuid
                      AND status = 'ready'
                      AND (
                        to_tsvector('simple', COALESCE(extracted_text, '')) @@ plainto_tsquery('simple', $1)
                        OR LOWER(display_name) LIKE LOWER($3)
                        OR LOWER(url) LIKE LOWER($3)
                      )
                    ORDER BY rank DESC
                    LIMIT $4
                """, query, user_id, f"%{query}%", limit)
            else:
                rows = await conn.fetch("""
                    SELECT *, ts_rank(to_tsvector('simple', COALESCE(extracted_text, '')),
                                      plainto_tsquery('simple', $1)) as rank
                    FROM web_sources
                    WHERE status = 'ready'
                      AND (
                        to_tsvector('simple', COALESCE(extracted_text, '')) @@ plainto_tsquery('simple', $1)
                        OR LOWER(display_name) LIKE LOWER($2)
                        OR LOWER(url) LIKE LOWER($2)
                      )
                    ORDER BY rank DESC
                    LIMIT $3
                """, query, f"%{query}%", limit)

            return [self._row_to_dict(row) for row in rows]

    async def get_all_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all web sources as a dictionary (for cache loading).

        Returns:
            Dictionary of web_source_id -> web source data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM web_sources")

            return {
                row['id']: self._row_to_dict(row)
                for row in rows
            }

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row["id"],
            "user_id": str(row["user_id"]) if row["user_id"] else None,
            "url": row["url"],
            "display_name": row["display_name"],
            "domain": row["domain"],
            "extractor": row["extractor"],
            "include_images": row["include_images"],
            "include_links": row["include_links"],
            "status": row["status"],
            "http_status_code": row["http_status_code"],
            "error_message": row["error_message"],
            "retry_count": row["retry_count"],
            "extracted_text": row["extracted_text"],
            "extracted_links": row["extracted_links"] or [],
            "extracted_images": row["extracted_images"] or [],
            "content_hash": row["content_hash"],
            "metadata": row["metadata"] or {},
            "word_count": row["word_count"],
            "char_count": row["char_count"],
            "chunk_count": row["chunk_count"],
            "link_count": row["link_count"],
            "image_count": row["image_count"],
            "fetch_time_ms": row["fetch_time_ms"],
            "extraction_time_ms": row["extraction_time_ms"],
            "tags": list(row["tags"]) if row["tags"] else [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "fetched_at": row["fetched_at"],
            "processed_at": row["processed_at"]
        }


# Singleton instance
_web_source_repository: Optional[PostgresWebSourceRepository] = None


async def get_web_source_repository(
    pool: Optional[Pool] = None
) -> PostgresWebSourceRepository:
    """
    Get or create web source repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresWebSourceRepository instance
    """
    global _web_source_repository

    if _web_source_repository is None:
        if pool is None:
            import asyncpg
            from ...core.config import api_settings

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)

        _web_source_repository = PostgresWebSourceRepository(pool)
        await _web_source_repository._ensure_table()
        logger.info("Web source repository initialized")

    return _web_source_repository
