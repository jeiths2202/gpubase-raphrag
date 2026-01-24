"""
PostgreSQL Verified Knowledge Repository Implementation

Production-ready PostgreSQL implementation for Smarter RAG system:
- Verified Knowledge Store management
- Training batch management
- Usage tracking
- Vector similarity search
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

import asyncpg
from asyncpg import Pool, Connection

logger = logging.getLogger(__name__)


class VerifiedKnowledgeEntity:
    """Verified Knowledge entity"""

    def __init__(
        self,
        id: str,
        message_id: str,
        conversation_id: str,
        user_id: str,
        question: str,
        answer: str,
        answer_summary: Optional[str] = None,
        feedback_score: float = 1.0,
        thumbs_up_count: int = 1,
        thumbs_down_count: int = 0,
        confidence_score: float = 0.5,
        usage_count: int = 0,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        language: str = "ko",
        query_type: Optional[str] = None,
        source_documents: Optional[List[Dict[str, Any]]] = None,
        is_trained: bool = False,
        trained_at: Optional[datetime] = None,
        training_batch_id: Optional[str] = None,
        training_version: int = 0,
        status: str = "active",
        superseded_by: Optional[str] = None,
        deprecated_reason: Optional[str] = None,
        reviewed_by: Optional[str] = None,
        reviewed_at: Optional[datetime] = None,
        review_notes: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        last_used_at: Optional[datetime] = None,
    ):
        self.id = id
        self.message_id = message_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.question = question
        self.answer = answer
        self.answer_summary = answer_summary
        self.feedback_score = feedback_score
        self.thumbs_up_count = thumbs_up_count
        self.thumbs_down_count = thumbs_down_count
        self.confidence_score = confidence_score
        self.usage_count = usage_count
        self.category = category
        self.tags = tags or []
        self.language = language
        self.query_type = query_type
        self.source_documents = source_documents or []
        self.is_trained = is_trained
        self.trained_at = trained_at
        self.training_batch_id = training_batch_id
        self.training_version = training_version
        self.status = status
        self.superseded_by = superseded_by
        self.deprecated_reason = deprecated_reason
        self.reviewed_by = reviewed_by
        self.reviewed_at = reviewed_at
        self.review_notes = review_notes
        self.created_at = created_at
        self.updated_at = updated_at
        self.last_used_at = last_used_at


class TrainingBatchEntity:
    """Training batch entity"""

    def __init__(
        self,
        id: str,
        batch_id: str,
        total_samples: int = 0,
        trained_samples: int = 0,
        min_feedback_score: float = 0.8,
        min_thumbs_up: int = 1,
        base_model: str = "Qwen2.5-7B-Instruct",
        adapter_name: Optional[str] = None,
        status: str = "pending",
        error_message: Optional[str] = None,
        eval_loss: Optional[float] = None,
        eval_accuracy: Optional[float] = None,
        eval_perplexity: Optional[float] = None,
        scheduled_at: Optional[datetime] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.batch_id = batch_id
        self.total_samples = total_samples
        self.trained_samples = trained_samples
        self.min_feedback_score = min_feedback_score
        self.min_thumbs_up = min_thumbs_up
        self.base_model = base_model
        self.adapter_name = adapter_name
        self.status = status
        self.error_message = error_message
        self.eval_loss = eval_loss
        self.eval_accuracy = eval_accuracy
        self.eval_perplexity = eval_perplexity
        self.scheduled_at = scheduled_at
        self.started_at = started_at
        self.completed_at = completed_at
        self.created_at = created_at


class PostgresVerifiedKnowledgeRepository:
    """
    PostgreSQL implementation of Verified Knowledge Repository.

    Features:
    - Connection pooling for performance
    - Vector similarity search
    - Training batch management
    - Usage tracking
    """

    def __init__(self, pool: Pool):
        """Initialize PostgreSQL repository."""
        self._pool = pool

    @classmethod
    async def create(
        cls,
        dsn: str,
        *,
        min_size: int = 5,
        max_size: int = 20,
        **kwargs
    ) -> "PostgresVerifiedKnowledgeRepository":
        """Factory method to create repository with connection pool."""
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

    def _to_uuid(self, entity_id: Optional[str]) -> Optional[UUID]:
        """Convert entity ID to UUID."""
        if entity_id is None:
            return None
        if isinstance(entity_id, UUID):
            return entity_id
        return UUID(entity_id)

    def _row_to_entity(self, row: asyncpg.Record) -> VerifiedKnowledgeEntity:
        """Convert database row to VerifiedKnowledgeEntity."""
        return VerifiedKnowledgeEntity(
            id=str(row["id"]),
            message_id=str(row["message_id"]),
            conversation_id=str(row["conversation_id"]),
            user_id=row["user_id"],
            question=row["question"],
            answer=row["answer"],
            answer_summary=row.get("answer_summary"),
            feedback_score=float(row.get("feedback_score") or 1.0),
            thumbs_up_count=int(row.get("thumbs_up_count") or 1),
            thumbs_down_count=int(row.get("thumbs_down_count") or 0),
            confidence_score=float(row.get("confidence_score") or 0.5),
            usage_count=int(row.get("usage_count") or 0),
            category=row.get("category"),
            tags=row.get("tags") or [],
            language=row.get("language", "ko"),
            query_type=row.get("query_type"),
            source_documents=json.loads(row["source_documents"]) if row.get("source_documents") else [],
            is_trained=row.get("is_trained", False),
            trained_at=row.get("trained_at"),
            training_batch_id=row.get("training_batch_id"),
            training_version=int(row.get("training_version") or 0),
            status=row.get("status", "active"),
            superseded_by=str(row["superseded_by"]) if row.get("superseded_by") else None,
            deprecated_reason=row.get("deprecated_reason"),
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=row.get("reviewed_at"),
            review_notes=row.get("review_notes"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            last_used_at=row.get("last_used_at"),
        )

    def _row_to_batch(self, row: asyncpg.Record) -> TrainingBatchEntity:
        """Convert database row to TrainingBatchEntity."""
        return TrainingBatchEntity(
            id=str(row["id"]),
            batch_id=row["batch_id"],
            total_samples=int(row.get("total_samples") or 0),
            trained_samples=int(row.get("trained_samples") or 0),
            min_feedback_score=float(row.get("min_feedback_score") or 0.8),
            min_thumbs_up=int(row.get("min_thumbs_up") or 1),
            base_model=row.get("base_model", "Qwen2.5-7B-Instruct"),
            adapter_name=row.get("adapter_name"),
            status=row.get("status", "pending"),
            error_message=row.get("error_message"),
            eval_loss=float(row["eval_loss"]) if row.get("eval_loss") else None,
            eval_accuracy=float(row["eval_accuracy"]) if row.get("eval_accuracy") else None,
            eval_perplexity=float(row["eval_perplexity"]) if row.get("eval_perplexity") else None,
            scheduled_at=row.get("scheduled_at"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            created_at=row.get("created_at"),
        )

    # ==================== Verified Knowledge CRUD ====================

    async def get(self, entity_id: str) -> Optional[VerifiedKnowledgeEntity]:
        """Get verified knowledge by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM verified_knowledge WHERE id = $1",
                self._to_uuid(entity_id)
            )
            return self._row_to_entity(row) if row else None

    async def get_by_message_id(self, message_id: str) -> Optional[VerifiedKnowledgeEntity]:
        """Get verified knowledge by message ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM verified_knowledge WHERE message_id = $1",
                self._to_uuid(message_id)
            )
            return self._row_to_entity(row) if row else None

    async def create(
        self,
        message_id: str,
        conversation_id: str,
        user_id: str,
        question: str,
        answer: str,
        source_documents: Optional[List[Dict[str, Any]]] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        language: str = "ko",
        query_type: Optional[str] = None,
    ) -> VerifiedKnowledgeEntity:
        """Create a new verified knowledge entry."""
        async with self._pool.acquire() as conn:
            entity_id = uuid4()
            now = datetime.now(timezone.utc)

            row = await conn.fetchrow(
                """
                INSERT INTO verified_knowledge (
                    id, message_id, conversation_id, user_id,
                    question, answer, source_documents,
                    category, tags, language, query_type,
                    feedback_score, thumbs_up_count, status,
                    created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
                )
                ON CONFLICT (message_id) DO UPDATE SET
                    thumbs_up_count = verified_knowledge.thumbs_up_count + 1,
                    feedback_score = (verified_knowledge.thumbs_up_count + 1)::FLOAT /
                        NULLIF(verified_knowledge.thumbs_up_count + 1 + verified_knowledge.thumbs_down_count, 0),
                    updated_at = NOW()
                RETURNING *
                """,
                entity_id,
                self._to_uuid(message_id),
                self._to_uuid(conversation_id),
                user_id,
                question,
                answer,
                json.dumps(source_documents or []),
                category,
                tags or [],
                language,
                query_type,
                1.0,  # initial feedback_score
                1,    # initial thumbs_up_count
                "active",
                now,
                now
            )
            return self._row_to_entity(row)

    async def update(self, entity: VerifiedKnowledgeEntity) -> VerifiedKnowledgeEntity:
        """Update an existing verified knowledge entry."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE verified_knowledge SET
                    answer_summary = $2,
                    category = $3,
                    tags = $4,
                    language = $5,
                    query_type = $6,
                    status = $7,
                    review_notes = $8,
                    reviewed_by = $9,
                    reviewed_at = $10,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                self._to_uuid(entity.id),
                entity.answer_summary,
                entity.category,
                entity.tags,
                entity.language,
                entity.query_type,
                entity.status,
                entity.review_notes,
                entity.reviewed_by,
                entity.reviewed_at,
            )
            if not row:
                raise ValueError(f"Verified knowledge {entity.id} not found")
            return self._row_to_entity(row)

    async def delete(self, entity_id: str) -> bool:
        """Hard delete a verified knowledge entry."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM verified_knowledge WHERE id = $1",
                self._to_uuid(entity_id)
            )
            return result == "DELETE 1"

    async def deprecate(
        self,
        entity_id: str,
        reason: str,
        superseded_by: Optional[str] = None
    ) -> bool:
        """Mark a verified knowledge entry as deprecated."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE verified_knowledge SET
                    status = 'deprecated',
                    deprecated_reason = $2,
                    superseded_by = $3,
                    updated_at = NOW()
                WHERE id = $1
                """,
                self._to_uuid(entity_id),
                reason,
                self._to_uuid(superseded_by) if superseded_by else None
            )
            return result == "UPDATE 1"

    # ==================== Search & Query ====================

    async def search_by_text(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.5,
        language: Optional[str] = None,
        category: Optional[str] = None,
        status: str = "active"
    ) -> List[Tuple[VerifiedKnowledgeEntity, float]]:
        """
        Search verified knowledge by text similarity.

        Uses PostgreSQL full-text search as fallback when no embedding available.
        """
        async with self._pool.acquire() as conn:
            params = [query, limit]
            param_idx = 3

            query_sql = """
                SELECT *,
                    ts_rank(
                        to_tsvector('simple', question || ' ' || answer),
                        plainto_tsquery('simple', $1)
                    ) as rank
                FROM verified_knowledge
                WHERE status = $4
                    AND to_tsvector('simple', question || ' ' || answer)
                        @@ plainto_tsquery('simple', $1)
            """
            params.append(status)
            param_idx += 1

            if language:
                query_sql += f" AND language = ${param_idx}"
                params.append(language)
                param_idx += 1

            if category:
                query_sql += f" AND category = ${param_idx}"
                params.append(category)
                param_idx += 1

            query_sql += f"""
                ORDER BY rank DESC, feedback_score DESC
                LIMIT $2
            """

            rows = await conn.fetch(query_sql, *params)

            results = []
            for row in rows:
                entity = self._row_to_entity(row)
                score = float(row["rank"]) if row.get("rank") else 0.0
                if score >= min_score:
                    results.append((entity, score))

            return results

    async def search_by_embedding(
        self,
        embedding: List[float],
        limit: int = 10,
        min_similarity: float = 0.7,
        language: Optional[str] = None,
        category: Optional[str] = None,
        status: str = "active"
    ) -> List[Tuple[VerifiedKnowledgeEntity, float]]:
        """Search verified knowledge by vector similarity."""
        async with self._pool.acquire() as conn:
            # Build query with filters
            query_sql = """
                SELECT *,
                    1 - (question_embedding <=> $1::vector) as similarity
                FROM verified_knowledge
                WHERE status = $2
                    AND question_embedding IS NOT NULL
            """
            params = [embedding, status]
            param_idx = 3

            if language:
                query_sql += f" AND language = ${param_idx}"
                params.append(language)
                param_idx += 1

            if category:
                query_sql += f" AND category = ${param_idx}"
                params.append(category)
                param_idx += 1

            query_sql += f"""
                ORDER BY question_embedding <=> $1::vector
                LIMIT ${param_idx}
            """
            params.append(limit)

            rows = await conn.fetch(query_sql, *params)

            results = []
            for row in rows:
                similarity = float(row["similarity"]) if row.get("similarity") else 0.0
                if similarity >= min_similarity:
                    entity = self._row_to_entity(row)
                    results.append((entity, similarity))

            return results

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        is_trained: Optional[bool] = None,
        category: Optional[str] = None,
        language: Optional[str] = None,
        min_feedback_score: Optional[float] = None,
        order_by: str = "feedback_score DESC"
    ) -> List[VerifiedKnowledgeEntity]:
        """List verified knowledge with optional filters."""
        async with self._pool.acquire() as conn:
            query = "SELECT * FROM verified_knowledge WHERE 1=1"
            params = []
            param_idx = 1

            if status:
                query += f" AND status = ${param_idx}"
                params.append(status)
                param_idx += 1

            if is_trained is not None:
                query += f" AND is_trained = ${param_idx}"
                params.append(is_trained)
                param_idx += 1

            if category:
                query += f" AND category = ${param_idx}"
                params.append(category)
                param_idx += 1

            if language:
                query += f" AND language = ${param_idx}"
                params.append(language)
                param_idx += 1

            if min_feedback_score is not None:
                query += f" AND feedback_score >= ${param_idx}"
                params.append(min_feedback_score)
                param_idx += 1

            # Validate order_by to prevent SQL injection
            allowed_orders = [
                "feedback_score DESC", "feedback_score ASC",
                "usage_count DESC", "usage_count ASC",
                "created_at DESC", "created_at ASC",
                "updated_at DESC", "updated_at ASC",
            ]
            if order_by not in allowed_orders:
                order_by = "feedback_score DESC"

            query += f" ORDER BY {order_by} LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, skip])

            rows = await conn.fetch(query, *params)
            return [self._row_to_entity(row) for row in rows]

    async def count(
        self,
        status: Optional[str] = None,
        is_trained: Optional[bool] = None
    ) -> int:
        """Count verified knowledge entries."""
        async with self._pool.acquire() as conn:
            query = "SELECT COUNT(*) FROM verified_knowledge WHERE 1=1"
            params = []
            param_idx = 1

            if status:
                query += f" AND status = ${param_idx}"
                params.append(status)
                param_idx += 1

            if is_trained is not None:
                query += f" AND is_trained = ${param_idx}"
                params.append(is_trained)
                param_idx += 1

            return await conn.fetchval(query, *params)

    # ==================== Usage Tracking ====================

    async def record_usage(
        self,
        knowledge_id: str,
        query: str,
        similarity_score: float,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        source_type: str = "verified"
    ) -> None:
        """Record usage of a verified knowledge entry."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Insert usage log
                await conn.execute(
                    """
                    INSERT INTO knowledge_usage_log (
                        knowledge_id, conversation_id, user_id,
                        query, similarity_score, source_type
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    self._to_uuid(knowledge_id),
                    self._to_uuid(conversation_id) if conversation_id else None,
                    user_id,
                    query,
                    similarity_score,
                    source_type
                )

                # Update usage count and last_used_at
                await conn.execute(
                    """
                    UPDATE verified_knowledge SET
                        usage_count = usage_count + 1,
                        last_used_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1
                    """,
                    self._to_uuid(knowledge_id)
                )

    async def record_usage_feedback(
        self,
        knowledge_id: str,
        was_helpful: bool
    ) -> None:
        """Record feedback on a usage of verified knowledge."""
        async with self._pool.acquire() as conn:
            # Update the most recent usage log
            await conn.execute(
                """
                UPDATE knowledge_usage_log SET
                    was_helpful = $2
                WHERE id = (
                    SELECT id FROM knowledge_usage_log
                    WHERE knowledge_id = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                )
                """,
                self._to_uuid(knowledge_id),
                was_helpful
            )

            # Update confidence score based on helpfulness
            adjustment = 0.05 if was_helpful else -0.05
            await conn.execute(
                """
                UPDATE verified_knowledge SET
                    confidence_score = GREATEST(0, LEAST(1, confidence_score + $2)),
                    updated_at = NOW()
                WHERE id = $1
                """,
                self._to_uuid(knowledge_id),
                adjustment
            )

    # ==================== Embedding Management ====================

    async def update_embedding(
        self,
        entity_id: str,
        embedding: List[float]
    ) -> bool:
        """Update the question embedding for a verified knowledge entry."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE verified_knowledge SET
                    question_embedding = $2::vector,
                    updated_at = NOW()
                WHERE id = $1
                """,
                self._to_uuid(entity_id),
                embedding
            )
            return result == "UPDATE 1"

    async def get_entries_without_embedding(
        self,
        limit: int = 100
    ) -> List[VerifiedKnowledgeEntity]:
        """Get verified knowledge entries that don't have embeddings yet."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM verified_knowledge
                WHERE question_embedding IS NULL
                    AND status = 'active'
                ORDER BY created_at ASC
                LIMIT $1
                """,
                limit
            )
            return [self._row_to_entity(row) for row in rows]

    # ==================== Training Management ====================

    async def get_training_ready(
        self,
        min_feedback_score: float = 0.8,
        min_thumbs_up: int = 1,
        limit: int = 1000
    ) -> List[VerifiedKnowledgeEntity]:
        """Get entries ready for training (not yet trained, high quality)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM verified_knowledge
                WHERE status = 'active'
                    AND is_trained = FALSE
                    AND feedback_score >= $1
                    AND thumbs_up_count >= $2
                ORDER BY feedback_score DESC, thumbs_up_count DESC
                LIMIT $3
                """,
                min_feedback_score,
                min_thumbs_up,
                limit
            )
            return [self._row_to_entity(row) for row in rows]

    async def mark_as_trained(
        self,
        entity_ids: List[str],
        batch_id: str,
        training_version: int
    ) -> int:
        """Mark entries as trained."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE verified_knowledge SET
                    is_trained = TRUE,
                    trained_at = NOW(),
                    training_batch_id = $2,
                    training_version = $3,
                    updated_at = NOW()
                WHERE id = ANY($1::uuid[])
                """,
                [self._to_uuid(eid) for eid in entity_ids],
                batch_id,
                training_version
            )
            # Extract count from result string like "UPDATE 5"
            count = int(result.split()[-1]) if result else 0
            return count

    # ==================== Unlearn Management (👎 제거) ====================

    async def get_unlearn_required(
        self,
        limit: int = 1000
    ) -> List[VerifiedKnowledgeEntity]:
        """Get entries that need to be unlearned (marked with 👎)."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM verified_knowledge
                WHERE status = 'unlearn_required'
                    AND is_trained = TRUE
                    AND unlearn_completed_at IS NULL
                ORDER BY unlearn_requested_at ASC
                LIMIT $1
                """,
                limit
            )
            return [self._row_to_entity(row) for row in rows]

    async def mark_as_unlearned(
        self,
        entity_ids: List[str],
        batch_id: str
    ) -> int:
        """Mark entries as unlearned (removed from model)."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE verified_knowledge SET
                    unlearn_completed_at = NOW(),
                    unlearn_batch_id = $2,
                    status = 'deprecated',
                    updated_at = NOW()
                WHERE id = ANY($1::uuid[])
                """,
                [self._to_uuid(eid) for eid in entity_ids],
                batch_id
            )
            count = int(result.split()[-1]) if result else 0
            return count

    async def remove_by_message_id(self, message_id: str) -> bool:
        """
        Remove knowledge by message_id (called when 👎 is received).
        If already trained, marks for unlearning. Otherwise, deletes.
        """
        async with self._pool.acquire() as conn:
            # Check if entry exists and is trained
            row = await conn.fetchrow(
                """
                SELECT id, is_trained FROM verified_knowledge
                WHERE message_id = $1
                """,
                self._to_uuid(message_id)
            )

            if not row:
                return False

            if row["is_trained"]:
                # Already trained - mark for unlearning
                result = await conn.execute(
                    """
                    UPDATE verified_knowledge SET
                        status = 'unlearn_required',
                        unlearn_requested_at = NOW(),
                        deprecated_reason = 'User marked as unhelpful (thumbs_down)',
                        updated_at = NOW()
                    WHERE message_id = $1
                    """,
                    self._to_uuid(message_id)
                )
                logger.info(f"[VerifiedKnowledge] Marked for unlearning: {message_id}")
            else:
                # Not yet trained - just delete
                result = await conn.execute(
                    """
                    DELETE FROM verified_knowledge
                    WHERE message_id = $1
                    """,
                    self._to_uuid(message_id)
                )
                logger.info(f"[VerifiedKnowledge] Deleted (not trained): {message_id}")

            return "1" in result

    # ==================== Training Batch Management ====================

    async def create_training_batch(
        self,
        batch_id: str,
        total_samples: int,
        min_feedback_score: float = 0.8,
        min_thumbs_up: int = 1,
        base_model: str = "Qwen2.5-7B-Instruct",
        scheduled_at: Optional[datetime] = None
    ) -> TrainingBatchEntity:
        """Create a new training batch."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO training_batches (
                    batch_id, total_samples, min_feedback_score, min_thumbs_up,
                    base_model, status, scheduled_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                batch_id,
                total_samples,
                min_feedback_score,
                min_thumbs_up,
                base_model,
                "pending",
                scheduled_at
            )
            return self._row_to_batch(row)

    async def get_training_batch(self, batch_id: str) -> Optional[TrainingBatchEntity]:
        """Get training batch by ID."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM training_batches WHERE batch_id = $1",
                batch_id
            )
            return self._row_to_batch(row) if row else None

    async def update_training_batch_status(
        self,
        batch_id: str,
        status: str,
        error_message: Optional[str] = None,
        trained_samples: Optional[int] = None,
        adapter_name: Optional[str] = None,
        eval_metrics: Optional[Dict[str, float]] = None
    ) -> bool:
        """Update training batch status."""
        async with self._pool.acquire() as conn:
            now = datetime.now(timezone.utc)

            # Build dynamic update
            updates = ["status = $2"]
            params = [batch_id, status]
            param_idx = 3

            if error_message is not None:
                updates.append(f"error_message = ${param_idx}")
                params.append(error_message)
                param_idx += 1

            if trained_samples is not None:
                updates.append(f"trained_samples = ${param_idx}")
                params.append(trained_samples)
                param_idx += 1

            if adapter_name is not None:
                updates.append(f"adapter_name = ${param_idx}")
                params.append(adapter_name)
                param_idx += 1

            if eval_metrics:
                if "loss" in eval_metrics:
                    updates.append(f"eval_loss = ${param_idx}")
                    params.append(eval_metrics["loss"])
                    param_idx += 1
                if "accuracy" in eval_metrics:
                    updates.append(f"eval_accuracy = ${param_idx}")
                    params.append(eval_metrics["accuracy"])
                    param_idx += 1
                if "perplexity" in eval_metrics:
                    updates.append(f"eval_perplexity = ${param_idx}")
                    params.append(eval_metrics["perplexity"])
                    param_idx += 1

            # Add timestamp updates based on status
            if status == "training":
                updates.append(f"started_at = ${param_idx}")
                params.append(now)
                param_idx += 1
            elif status in ("completed", "failed"):
                updates.append(f"completed_at = ${param_idx}")
                params.append(now)
                param_idx += 1

            query = f"UPDATE training_batches SET {', '.join(updates)} WHERE batch_id = $1"
            result = await conn.execute(query, *params)
            return result == "UPDATE 1"

    async def list_training_batches(
        self,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[TrainingBatchEntity]:
        """List training batches."""
        async with self._pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT * FROM training_batches
                    WHERE status = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    status,
                    limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM training_batches
                    ORDER BY created_at DESC
                    LIMIT $1
                    """,
                    limit
                )
            return [self._row_to_batch(row) for row in rows]

    # ==================== Statistics ====================

    async def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM v_verified_knowledge_stats")
            if not row:
                return {}
            return {
                "total_count": int(row["total_count"] or 0),
                "active_count": int(row["active_count"] or 0),
                "deprecated_count": int(row["deprecated_count"] or 0),
                "trained_count": int(row["trained_count"] or 0),
                "pending_training_count": int(row["pending_training_count"] or 0),
                "avg_feedback_score": float(row["avg_feedback_score"] or 0),
                "avg_usage_count": float(row["avg_usage_count"] or 0),
                "total_usage_count": int(row["total_usage_count"] or 0),
                "category_count": int(row["category_count"] or 0),
                "last_created_at": row["last_created_at"],
                "last_updated_at": row["last_updated_at"],
            }

    async def get_category_stats(self) -> List[Dict[str, Any]]:
        """Get statistics by category."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM v_verified_knowledge_by_category")
            return [
                {
                    "category": row["category"],
                    "count": int(row["count"] or 0),
                    "avg_score": float(row["avg_score"] or 0),
                    "total_usage": int(row["total_usage"] or 0),
                    "trained_count": int(row["trained_count"] or 0),
                }
                for row in rows
            ]

    async def get_daily_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get daily statistics."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM v_verified_knowledge_daily_stats
                WHERE date >= NOW() - $1::interval
                ORDER BY date DESC
                """,
                timedelta(days=days)
            )
            return [
                {
                    "date": row["date"].isoformat() if row["date"] else None,
                    "new_entries": int(row["new_entries"] or 0),
                    "trained_entries": int(row["trained_entries"] or 0),
                    "avg_score": float(row["avg_score"] or 0),
                }
                for row in rows
            ]

    # ==================== Training Schedule ====================

    async def get_training_schedule(self) -> Optional[Dict[str, Any]]:
        """Get the training schedule configuration."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM training_schedule ORDER BY id LIMIT 1"
            )
            if not row:
                return None
            return {
                "id": str(row["id"]),
                "cron_expression": row["cron_expression"],
                "is_enabled": row["is_enabled"],
                "last_run_at": row["last_run_at"],
                "last_batch_id": row["last_batch_id"],
                "last_status": row["last_status"],
                "next_run_at": row["next_run_at"],
                "min_samples_required": int(row["min_samples_required"] or 10),
                "auto_deploy": row["auto_deploy"],
            }

    async def update_training_schedule(
        self,
        cron_expression: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        min_samples_required: Optional[int] = None,
        auto_deploy: Optional[bool] = None,
        next_run_at: Optional[datetime] = None,
        last_run_at: Optional[datetime] = None,
        last_batch_id: Optional[str] = None,
        last_status: Optional[str] = None
    ) -> bool:
        """Update training schedule configuration."""
        async with self._pool.acquire() as conn:
            updates = []
            params = []
            param_idx = 1

            if cron_expression is not None:
                updates.append(f"cron_expression = ${param_idx}")
                params.append(cron_expression)
                param_idx += 1

            if is_enabled is not None:
                updates.append(f"is_enabled = ${param_idx}")
                params.append(is_enabled)
                param_idx += 1

            if min_samples_required is not None:
                updates.append(f"min_samples_required = ${param_idx}")
                params.append(min_samples_required)
                param_idx += 1

            if auto_deploy is not None:
                updates.append(f"auto_deploy = ${param_idx}")
                params.append(auto_deploy)
                param_idx += 1

            if next_run_at is not None:
                updates.append(f"next_run_at = ${param_idx}")
                params.append(next_run_at)
                param_idx += 1

            if last_run_at is not None:
                updates.append(f"last_run_at = ${param_idx}")
                params.append(last_run_at)
                param_idx += 1

            if last_batch_id is not None:
                updates.append(f"last_batch_id = ${param_idx}")
                params.append(last_batch_id)
                param_idx += 1

            if last_status is not None:
                updates.append(f"last_status = ${param_idx}")
                params.append(last_status)
                param_idx += 1

            if not updates:
                return True

            updates.append("updated_at = NOW()")
            query = f"UPDATE training_schedule SET {', '.join(updates)}"
            result = await conn.execute(query, *params)
            return "UPDATE" in result
