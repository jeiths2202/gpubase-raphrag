"""
PostgreSQL Image Embedding Repository Implementation

Production-ready PostgreSQL implementation with:
- Async operations using asyncpg
- Vector similarity search using pgvector
- Bulk operations for efficient document processing
- Binary image data storage
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

import asyncpg
from asyncpg import Pool, Connection

from ...repositories.image_embedding_repository import (
    ImageEmbeddingRepository,
    ImageEmbeddingEntity,
    ImageSearchResult,
)
from ...repositories.base import EntityId

logger = logging.getLogger(__name__)


class PostgresImageEmbeddingRepository(ImageEmbeddingRepository):
    """
    PostgreSQL implementation of ImageEmbeddingRepository.

    Features:
    - pgvector for efficient vector similarity search
    - HNSW index for fast approximate nearest neighbor
    - Binary storage for image data
    - Bulk operations for document processing
    """

    def __init__(self, pool: Pool):
        """
        Initialize PostgreSQL repository.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

    @classmethod
    async def create_with_pool(
        cls,
        dsn: str,
        *,
        min_size: int = 5,
        max_size: int = 20,
        **kwargs
    ) -> "PostgresImageEmbeddingRepository":
        """
        Factory method to create repository with connection pool.

        Args:
            dsn: PostgreSQL connection string
            min_size: Minimum pool connections
            max_size: Maximum pool connections
        """
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            **kwargs
        )
        return cls(pool)

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()

    # ==================== Helper Methods ====================

    def _normalize_id(self, entity_id: EntityId) -> str:
        """Normalize entity ID to string."""
        if isinstance(entity_id, UUID):
            return str(entity_id)
        return entity_id

    def _to_uuid(self, entity_id: Optional[EntityId]) -> Optional[UUID]:
        """Convert entity ID to UUID."""
        if entity_id is None:
            return None
        if isinstance(entity_id, UUID):
            return entity_id
        return UUID(entity_id)

    def _row_to_entity(
        self,
        row: asyncpg.Record,
        include_data: bool = False
    ) -> ImageEmbeddingEntity:
        """Convert database row to ImageEmbeddingEntity."""
        # Parse embedding from pgvector format
        embedding = None
        if row.get("embedding"):
            # pgvector returns as string "[1.0, 2.0, ...]" or as list
            emb_val = row["embedding"]
            if isinstance(emb_val, str):
                embedding = json.loads(emb_val)
            elif hasattr(emb_val, '__iter__'):
                embedding = list(emb_val)

        # Parse position JSON
        position = None
        if row.get("position"):
            pos_val = row["position"]
            if isinstance(pos_val, str):
                position = json.loads(pos_val)
            else:
                position = dict(pos_val) if pos_val else None

        # Parse metadata JSON
        metadata = {}
        if row.get("metadata"):
            meta_val = row["metadata"]
            if isinstance(meta_val, str):
                metadata = json.loads(meta_val)
            else:
                metadata = dict(meta_val) if meta_val else {}

        return ImageEmbeddingEntity(
            id=str(row["id"]),
            document_id=row["document_id"],
            image_id=row["image_id"],
            page_number=row.get("page_number"),
            image_data=row.get("image_data", b"") if include_data else b"",
            mime_type=row.get("mime_type", "image/png"),
            width=row.get("width"),
            height=row.get("height"),
            file_size=row.get("file_size"),
            position=position,
            description=row.get("description"),
            alt_text=row.get("alt_text"),
            embedding=embedding,
            metadata=metadata,
            figure_reference=row.get("figure_reference"),
            figure_caption=row.get("figure_caption"),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    def _embedding_to_pgvector(self, embedding: Optional[List[float]]) -> Optional[str]:
        """Convert embedding list to pgvector format."""
        if embedding is None:
            return None
        return f"[{','.join(str(x) for x in embedding)}]"

    # ==================== CRUD Operations ====================

    async def create(self, entity: ImageEmbeddingEntity) -> ImageEmbeddingEntity:
        """Create a new image embedding."""
        return await self.store_image(entity)

    async def get_by_id(self, entity_id: EntityId) -> Optional[ImageEmbeddingEntity]:
        """Get image embedding by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, document_id, image_id, page_number,
                       image_data, mime_type, width, height, file_size,
                       position, description, alt_text, embedding,
                       metadata, created_at, updated_at
                FROM image_embeddings
                WHERE id = $1
                """,
                self._to_uuid(entity_id)
            )
            if row:
                return self._row_to_entity(row, include_data=True)
            return None

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ImageEmbeddingEntity]:
        """Get all image embeddings with pagination."""
        async with self._pool.acquire() as conn:
            # Build filter conditions
            conditions = []
            params = []
            param_idx = 1

            if filters:
                if "document_id" in filters:
                    conditions.append(f"document_id = ${param_idx}")
                    params.append(filters["document_id"])
                    param_idx += 1

            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)

            query = f"""
                SELECT id, document_id, image_id, page_number,
                       mime_type, width, height, file_size,
                       position, description, alt_text,
                       metadata, created_at, updated_at
                FROM image_embeddings
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, skip])

            rows = await conn.fetch(query, *params)
            return [self._row_to_entity(row, include_data=False) for row in rows]

    async def update(
        self,
        entity_id: EntityId,
        data: Dict[str, Any]
    ) -> Optional[ImageEmbeddingEntity]:
        """Update an image embedding."""
        async with self._pool.acquire() as conn:
            # Build update fields
            set_parts = []
            params = []
            param_idx = 1

            for key, value in data.items():
                if key == "embedding":
                    set_parts.append(f"embedding = ${param_idx}::vector")
                    params.append(self._embedding_to_pgvector(value))
                elif key == "position":
                    set_parts.append(f"position = ${param_idx}::jsonb")
                    params.append(json.dumps(value) if value else None)
                elif key == "metadata":
                    set_parts.append(f"metadata = ${param_idx}::jsonb")
                    params.append(json.dumps(value) if value else "{}")
                else:
                    set_parts.append(f"{key} = ${param_idx}")
                    params.append(value)
                param_idx += 1

            if not set_parts:
                return await self.get_by_id(entity_id)

            params.append(self._to_uuid(entity_id))
            query = f"""
                UPDATE image_embeddings
                SET {', '.join(set_parts)}, updated_at = CURRENT_TIMESTAMP
                WHERE id = ${param_idx}
                RETURNING id, document_id, image_id, page_number,
                          image_data, mime_type, width, height, file_size,
                          position, description, alt_text, embedding,
                          metadata, created_at, updated_at
            """

            row = await conn.fetchrow(query, *params)
            if row:
                return self._row_to_entity(row, include_data=True)
            return None

    async def delete(self, entity_id: EntityId) -> bool:
        """Delete an image embedding."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM image_embeddings WHERE id = $1",
                self._to_uuid(entity_id)
            )
            return result == "DELETE 1"

    async def exists(self, entity_id: EntityId) -> bool:
        """Check if image embedding exists."""
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM image_embeddings WHERE id = $1)",
                self._to_uuid(entity_id)
            )
            return result

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count image embeddings."""
        async with self._pool.acquire() as conn:
            if filters and "document_id" in filters:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM image_embeddings WHERE document_id = $1",
                    filters["document_id"]
                )
            return await conn.fetchval("SELECT COUNT(*) FROM image_embeddings")

    # ==================== Image-specific Operations ====================

    async def store_image(
        self,
        entity: ImageEmbeddingEntity
    ) -> ImageEmbeddingEntity:
        """Store an image with its embedding."""
        async with self._pool.acquire() as conn:
            entity_id = uuid4()
            image_id = entity.image_id or f"img_{entity_id}"

            row = await conn.fetchrow(
                """
                INSERT INTO image_embeddings (
                    id, document_id, image_id, page_number,
                    image_data, mime_type, width, height, file_size,
                    position, description, alt_text, embedding, metadata,
                    figure_reference, figure_caption
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                    $13::vector, $14::jsonb, $15, $16
                )
                RETURNING id, document_id, image_id, page_number,
                          image_data, mime_type, width, height, file_size,
                          position, description, alt_text, embedding,
                          metadata, figure_reference, figure_caption,
                          created_at, updated_at
                """,
                entity_id,
                entity.document_id,
                image_id,
                entity.page_number,
                entity.image_data,
                entity.mime_type,
                entity.width,
                entity.height,
                entity.file_size or (len(entity.image_data) if entity.image_data else 0),
                json.dumps(entity.position) if entity.position else None,
                entity.description,
                entity.alt_text,
                self._embedding_to_pgvector(entity.embedding),
                json.dumps(entity.metadata) if entity.metadata else "{}",
                entity.figure_reference,
                entity.figure_caption
            )

            logger.info(f"Stored image {image_id} for document {entity.document_id}")
            return self._row_to_entity(row, include_data=True)

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        min_similarity: float = 0.1,
        document_id: Optional[str] = None
    ) -> List[ImageSearchResult]:
        """Search for similar images using vector similarity."""
        async with self._pool.acquire() as conn:
            embedding_str = self._embedding_to_pgvector(query_embedding)

            if document_id:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, document_id, image_id, page_number,
                        description, image_data, mime_type,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM image_embeddings
                    WHERE embedding IS NOT NULL
                      AND document_id = $2
                      AND 1 - (embedding <=> $1::vector) >= $3
                    ORDER BY embedding <=> $1::vector
                    LIMIT $4
                    """,
                    embedding_str,
                    document_id,
                    min_similarity,
                    limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        id, document_id, image_id, page_number,
                        description, image_data, mime_type,
                        1 - (embedding <=> $1::vector) AS similarity
                    FROM image_embeddings
                    WHERE embedding IS NOT NULL
                      AND 1 - (embedding <=> $1::vector) >= $2
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                    """,
                    embedding_str,
                    min_similarity,
                    limit
                )

            results = []
            for row in rows:
                results.append(ImageSearchResult(
                    id=str(row["id"]),
                    document_id=row["document_id"],
                    image_id=row["image_id"],
                    page_number=row.get("page_number"),
                    description=row.get("description"),
                    similarity=float(row["similarity"]),
                    image_data=row.get("image_data"),
                    mime_type=row.get("mime_type", "image/png")
                ))

            logger.debug(f"Found {len(results)} similar images (min_sim={min_similarity})")
            return results

    async def get_by_document_id(
        self,
        document_id: str,
        include_data: bool = False
    ) -> List[ImageEmbeddingEntity]:
        """Get all images for a document."""
        async with self._pool.acquire() as conn:
            if include_data:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           image_data, mime_type, width, height, file_size,
                           position, description, alt_text, embedding,
                           metadata, created_at, updated_at
                    FROM image_embeddings
                    WHERE document_id = $1
                    ORDER BY page_number, created_at
                """
            else:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           mime_type, width, height, file_size,
                           position, description, alt_text,
                           metadata, created_at, updated_at
                    FROM image_embeddings
                    WHERE document_id = $1
                    ORDER BY page_number, created_at
                """

            rows = await conn.fetch(query, document_id)
            return [self._row_to_entity(row, include_data=include_data) for row in rows]

    async def get_by_image_id(
        self,
        image_id: str,
        include_data: bool = True
    ) -> Optional[ImageEmbeddingEntity]:
        """Get an image by its image_id."""
        async with self._pool.acquire() as conn:
            if include_data:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           image_data, mime_type, width, height, file_size,
                           position, description, alt_text, embedding,
                           metadata, created_at, updated_at
                    FROM image_embeddings
                    WHERE image_id = $1
                """
            else:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           mime_type, width, height, file_size,
                           position, description, alt_text,
                           metadata, created_at, updated_at
                    FROM image_embeddings
                    WHERE image_id = $1
                """

            row = await conn.fetchrow(query, image_id)
            if row:
                return self._row_to_entity(row, include_data=include_data)
            return None

    async def delete_by_document_id(self, document_id: str) -> int:
        """Delete all images for a document."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM image_embeddings WHERE document_id = $1",
                document_id
            )
            # Parse "DELETE N" to get count
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Deleted {count} images for document {document_id}")
            return count

    async def bulk_store(
        self,
        entities: List[ImageEmbeddingEntity]
    ) -> List[ImageEmbeddingEntity]:
        """Store multiple images in batch."""
        if not entities:
            return []

        results = []
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for entity in entities:
                    stored = await self.store_image(entity)
                    results.append(stored)

        logger.info(f"Bulk stored {len(results)} images")
        return results

    async def update_embedding(
        self,
        image_id: str,
        embedding: List[float]
    ) -> bool:
        """Update the embedding for an existing image."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE image_embeddings
                SET embedding = $1::vector, updated_at = CURRENT_TIMESTAMP
                WHERE image_id = $2
                """,
                self._embedding_to_pgvector(embedding),
                image_id
            )
            return result == "UPDATE 1"

    async def update_description(
        self,
        image_id: str,
        description: str,
        alt_text: Optional[str] = None
    ) -> bool:
        """Update the VLM-generated description for an image."""
        async with self._pool.acquire() as conn:
            if alt_text is not None:
                result = await conn.execute(
                    """
                    UPDATE image_embeddings
                    SET description = $1, alt_text = $2, updated_at = CURRENT_TIMESTAMP
                    WHERE image_id = $3
                    """,
                    description,
                    alt_text,
                    image_id
                )
            else:
                result = await conn.execute(
                    """
                    UPDATE image_embeddings
                    SET description = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE image_id = $2
                    """,
                    description,
                    image_id
                )
            return result == "UPDATE 1"

    async def count_by_document(self, document_id: str) -> int:
        """Count images in a document."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM image_embeddings WHERE document_id = $1",
                document_id
            )

    async def get_by_figure_references(
        self,
        document_id: str,
        figure_references: List[str],
        include_data: bool = True
    ) -> List[ImageEmbeddingEntity]:
        """
        Get images by their figure references (normalized).

        Args:
            document_id: Document ID to search within
            figure_references: List of normalized references (e.g., ["fig_1_1", "fig_2"])
            include_data: Whether to include binary image data

        Returns:
            List of matching ImageEmbeddingEntity objects
        """
        if not figure_references:
            return []

        async with self._pool.acquire() as conn:
            # Build query with ANY for matching multiple references
            if include_data:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           image_data, mime_type, width, height, file_size,
                           position, description, alt_text, embedding,
                           metadata, figure_reference, figure_caption,
                           created_at, updated_at
                    FROM image_embeddings
                    WHERE document_id = $1
                      AND figure_reference = ANY($2)
                    ORDER BY page_number, figure_reference
                """
            else:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           mime_type, width, height, file_size,
                           position, description, alt_text,
                           metadata, figure_reference, figure_caption,
                           created_at, updated_at
                    FROM image_embeddings
                    WHERE document_id = $1
                      AND figure_reference = ANY($2)
                    ORDER BY page_number, figure_reference
                """

            rows = await conn.fetch(query, document_id, figure_references)
            return [self._row_to_entity(row, include_data=include_data) for row in rows]

    async def update_figure_reference(
        self,
        image_id: str,
        figure_reference: str,
        figure_caption: Optional[str] = None
    ) -> bool:
        """Update the figure reference for an image."""
        async with self._pool.acquire() as conn:
            if figure_caption is not None:
                result = await conn.execute(
                    """
                    UPDATE image_embeddings
                    SET figure_reference = $1, figure_caption = $2,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE image_id = $3
                    """,
                    figure_reference,
                    figure_caption,
                    image_id
                )
            else:
                result = await conn.execute(
                    """
                    UPDATE image_embeddings
                    SET figure_reference = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE image_id = $2
                    """,
                    figure_reference,
                    image_id
                )
            return result == "UPDATE 1"

    async def get_by_page_numbers(
        self,
        document_id: str,
        page_numbers: List[int],
        include_data: bool = True
    ) -> List[ImageEmbeddingEntity]:
        """
        Get images by document ID and page numbers.

        Args:
            document_id: Document ID to search within
            page_numbers: List of page numbers to fetch images from
            include_data: Whether to include binary image data

        Returns:
            List of ImageEmbeddingEntity objects for the specified pages
        """
        if not page_numbers:
            return []

        async with self._pool.acquire() as conn:
            if include_data:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           image_data, mime_type, width, height, file_size,
                           position, description, alt_text, embedding,
                           metadata, figure_reference, figure_caption,
                           created_at, updated_at
                    FROM image_embeddings
                    WHERE document_id = $1
                      AND page_number = ANY($2)
                    ORDER BY page_number
                """
            else:
                query = """
                    SELECT id, document_id, image_id, page_number,
                           mime_type, width, height, file_size,
                           position, description, alt_text,
                           metadata, figure_reference, figure_caption,
                           created_at, updated_at
                    FROM image_embeddings
                    WHERE document_id = $1
                      AND page_number = ANY($2)
                    ORDER BY page_number
                """

            rows = await conn.fetch(query, document_id, page_numbers)
            logger.debug(f"Found {len(rows)} images for pages {page_numbers} in document {document_id}")
            return [self._row_to_entity(row, include_data=include_data) for row in rows]
