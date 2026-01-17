"""
Image Repository for PostgreSQL
PDF 이미지 저장소

Stores and retrieves images extracted from PDF documents.
"""
import logging
import uuid
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PostgresImageRepository:
    """
    Repository for storing and retrieving PDF images.
    PostgreSQL에 PDF 이미지 저장 및 조회
    """

    def __init__(self, connection_pool):
        """
        Initialize with asyncpg connection pool.

        Args:
            connection_pool: asyncpg connection pool
        """
        self._pool = connection_pool

    async def save_images(self, images: List[Dict[str, Any]]) -> int:
        """
        Save multiple images to database.

        Args:
            images: List of image data dicts

        Returns:
            Number of images saved
        """
        if not images:
            return 0

        async with self._pool.acquire() as conn:
            saved_count = 0
            for img in images:
                try:
                    # Serialize position dict to JSON string
                    position_json = json.dumps(img.get("position")) if img.get("position") else None

                    await conn.execute("""
                        INSERT INTO image_embeddings (
                            id, document_id, image_id, page_number,
                            image_data, mime_type, width, height, file_size,
                            position, created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11)
                        ON CONFLICT (image_id) DO UPDATE SET
                            image_data = EXCLUDED.image_data,
                            mime_type = EXCLUDED.mime_type,
                            width = EXCLUDED.width,
                            height = EXCLUDED.height,
                            file_size = EXCLUDED.file_size,
                            position = EXCLUDED.position,
                            updated_at = EXCLUDED.updated_at
                    """,
                        uuid.uuid4(),
                        img["document_id"],
                        img["image_id"],
                        img["page_number"],
                        img["image_data"],
                        img["mime_type"],
                        img["width"],
                        img["height"],
                        img["file_size"],
                        position_json,
                        datetime.now(timezone.utc)
                    )
                    saved_count += 1
                except Exception as e:
                    logger.error(f"Failed to save image {img.get('image_id')}: {e}")

            logger.info(f"Saved {saved_count}/{len(images)} images")
            return saved_count

    async def get_image(self, image_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single image by ID.

        Args:
            image_id: Image identifier

        Returns:
            Image data dict or None
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT image_id, document_id, page_number,
                       image_data, mime_type, width, height, file_size,
                       description, alt_text, figure_caption, position
                FROM image_embeddings
                WHERE image_id = $1
            """, image_id)

            if row:
                return dict(row)
            return None

    async def get_images_by_document(
        self,
        document_id: str,
        page_number: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all images for a document.

        Args:
            document_id: Document identifier
            page_number: Optional page filter

        Returns:
            List of image data dicts (without binary data)
        """
        async with self._pool.acquire() as conn:
            if page_number:
                rows = await conn.fetch("""
                    SELECT image_id, document_id, page_number,
                           mime_type, width, height, file_size,
                           description, alt_text, figure_caption, position
                    FROM image_embeddings
                    WHERE document_id = $1 AND page_number = $2
                    ORDER BY page_number, image_id
                """, document_id, page_number)
            else:
                rows = await conn.fetch("""
                    SELECT image_id, document_id, page_number,
                           mime_type, width, height, file_size,
                           description, alt_text, figure_caption, position
                    FROM image_embeddings
                    WHERE document_id = $1
                    ORDER BY page_number, image_id
                """, document_id)

            return [dict(row) for row in rows]

    async def get_images_by_page_range(
        self,
        document_id: str,
        page_start: int,
        page_end: int
    ) -> List[Dict[str, Any]]:
        """
        Get images within a page range.

        Args:
            document_id: Document identifier
            page_start: Start page (inclusive)
            page_end: End page (inclusive)

        Returns:
            List of image metadata (without binary data)
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT image_id, document_id, page_number,
                       mime_type, width, height, file_size,
                       description, alt_text, figure_caption, position
                FROM image_embeddings
                WHERE document_id = $1
                  AND page_number >= $2
                  AND page_number <= $3
                ORDER BY page_number, image_id
            """, document_id, page_start, page_end)

            return [dict(row) for row in rows]

    async def delete_images_by_document(self, document_id: str) -> int:
        """
        Delete all images for a document.

        Args:
            document_id: Document identifier

        Returns:
            Number of images deleted
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM image_embeddings WHERE document_id = $1
            """, document_id)
            deleted = int(result.split()[-1])
            logger.info(f"Deleted {deleted} images for document {document_id}")
            return deleted

    async def update_image_description(
        self,
        image_id: str,
        description: str = None,
        alt_text: str = None,
        figure_caption: str = None
    ) -> bool:
        """
        Update image description fields.

        Args:
            image_id: Image identifier
            description: Image description
            alt_text: Alt text for accessibility
            figure_caption: Figure caption from document

        Returns:
            True if updated, False otherwise
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE image_embeddings
                SET description = COALESCE($2, description),
                    alt_text = COALESCE($3, alt_text),
                    figure_caption = COALESCE($4, figure_caption),
                    updated_at = $5
                WHERE image_id = $1
            """, image_id, description, alt_text, figure_caption, datetime.now(timezone.utc))
            return result == "UPDATE 1"

    async def count_images(self, document_id: str = None) -> int:
        """Count images, optionally filtered by document."""
        async with self._pool.acquire() as conn:
            if document_id:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM image_embeddings WHERE document_id = $1",
                    document_id
                )
            return await conn.fetchval("SELECT COUNT(*) FROM image_embeddings")

    async def update_clip_embedding(
        self,
        image_id: str,
        clip_embedding: List[float]
    ) -> bool:
        """
        Update CLIP embedding for an image.

        Args:
            image_id: Image identifier
            clip_embedding: CLIP embedding vector (512 dimensions)

        Returns:
            True if updated, False otherwise
        """
        async with self._pool.acquire() as conn:
            # Convert list to string format for pgvector
            embedding_str = f"[{','.join(str(v) for v in clip_embedding)}]"
            result = await conn.execute("""
                UPDATE image_embeddings
                SET clip_embedding = $2::vector,
                    updated_at = $3
                WHERE image_id = $1
            """, image_id, embedding_str, datetime.now(timezone.utc))
            return result == "UPDATE 1"

    async def search_by_clip_embedding(
        self,
        query_embedding: List[float],
        document_id: Optional[str] = None,
        limit: int = 5,
        min_similarity: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Search similar images using CLIP embedding.

        Args:
            query_embedding: Query CLIP embedding (512 dimensions)
            document_id: Optional filter by document
            limit: Maximum results
            min_similarity: Minimum similarity threshold

        Returns:
            List of image metadata with similarity scores
        """
        async with self._pool.acquire() as conn:
            # Convert to pgvector format
            embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"

            if document_id:
                rows = await conn.fetch("""
                    SELECT
                        image_id, document_id, page_number,
                        mime_type, width, height, file_size,
                        description, alt_text, figure_caption,
                        1 - (clip_embedding <=> $1::vector) as similarity
                    FROM image_embeddings
                    WHERE document_id = $2
                      AND clip_embedding IS NOT NULL
                      AND 1 - (clip_embedding <=> $1::vector) >= $4
                    ORDER BY clip_embedding <=> $1::vector
                    LIMIT $3
                """, embedding_str, document_id, limit, min_similarity)
            else:
                rows = await conn.fetch("""
                    SELECT
                        image_id, document_id, page_number,
                        mime_type, width, height, file_size,
                        description, alt_text, figure_caption,
                        1 - (clip_embedding <=> $1::vector) as similarity
                    FROM image_embeddings
                    WHERE clip_embedding IS NOT NULL
                      AND 1 - (clip_embedding <=> $1::vector) >= $3
                    ORDER BY clip_embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, limit, min_similarity)

            return [dict(row) for row in rows]

    async def get_images_without_clip_embedding(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get images that don't have CLIP embeddings yet.

        Args:
            limit: Maximum number of images to return

        Returns:
            List of image data including binary for embedding
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT image_id, document_id, page_number, image_data, mime_type
                FROM image_embeddings
                WHERE clip_embedding IS NULL
                ORDER BY created_at
                LIMIT $1
            """, limit)

            return [dict(row) for row in rows]


# Singleton instance
_repository: Optional[PostgresImageRepository] = None


def get_image_repository(pool=None) -> PostgresImageRepository:
    """Get or create image repository instance."""
    global _repository
    if _repository is None and pool is not None:
        _repository = PostgresImageRepository(pool)
    return _repository


def reset_image_repository():
    """Reset singleton instance."""
    global _repository
    _repository = None
