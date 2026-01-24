"""
User Feedback Repository

PostgreSQL repository for user feedback, HITL learning, and consistency caching.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class UserFeedbackRepository:
    """Repository for user feedback persistence"""

    def __init__(self, db_pool=None):
        self.db_pool = db_pool

    # ============================================
    # Feedback CRUD
    # ============================================

    async def save_feedback(self, feedback_data: Dict[str, Any]) -> str:
        """Save user feedback"""
        if not self.db_pool:
            logger.warning("[FeedbackRepo] No database pool available")
            return feedback_data.get("feedback_id", "")

        query = """
            INSERT INTO user_feedbacks (
                feedback_id, message_id, conversation_id, user_id,
                feedback_type, categories, comment, expected_answer,
                query_snapshot, answer_snapshot, sources_snapshot, status
            ) VALUES (
                $1::uuid, $2, $3, $4,
                $5, $6::jsonb, $7, $8,
                $9, $10, $11::jsonb, $12
            )
            RETURNING feedback_id
        """

        try:
            # Handle conversation_id: convert empty string to None
            conv_id = feedback_data.get("conversation_id")
            if conv_id and conv_id != "" and conv_id != "None":
                conv_id = conv_id
            else:
                conv_id = None

            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(
                    query,
                    feedback_data["feedback_id"],
                    feedback_data["message_id"],
                    conv_id,
                    feedback_data["user_id"],
                    feedback_data["feedback_type"],
                    json.dumps(feedback_data.get("categories", [])),
                    feedback_data.get("comment"),
                    feedback_data.get("expected_answer"),
                    feedback_data.get("query_snapshot"),
                    feedback_data.get("answer_snapshot"),
                    json.dumps(feedback_data.get("sources_snapshot", [])),
                    feedback_data.get("status", "pending"),
                )
                return str(result) if result else feedback_data["feedback_id"]
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error saving feedback: {e}")
            raise

    async def get_feedback_by_id(self, feedback_id: str) -> Optional[Dict[str, Any]]:
        """Get feedback by ID"""
        if not self.db_pool:
            return None

        query = """
            SELECT * FROM user_feedbacks WHERE feedback_id = $1::uuid
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, feedback_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting feedback: {e}")
            return None

    async def get_feedback_by_message_and_user(
        self, message_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get feedback by message ID and user ID"""
        if not self.db_pool:
            return None

        query = """
            SELECT * FROM user_feedbacks
            WHERE message_id = $1 AND user_id = $2
            ORDER BY created_at DESC
            LIMIT 1
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, message_id, user_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting feedback by message/user: {e}")
            return None

    async def delete_feedback_by_message_and_user(
        self, message_id: str, user_id: str
    ) -> bool:
        """Delete feedback by message ID and user ID"""
        if not self.db_pool:
            return False

        query = """
            DELETE FROM user_feedbacks
            WHERE message_id = $1 AND user_id = $2
            RETURNING feedback_id
        """

        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval(query, message_id, user_id)
                if result:
                    logger.info(f"[FeedbackRepo] Deleted feedback: {result}")
                    return True
                return False
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error deleting feedback: {e}")
            return False

    async def get_feedback_summary(self, message_id: str) -> Dict[str, Any]:
        """Get aggregated feedback summary for a message"""
        if not self.db_pool:
            return {}

        query = """
            SELECT
                COUNT(*) as total_count,
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up_count,
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down_count,
                ROUND(
                    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::NUMERIC /
                    NULLIF(COUNT(*), 0) * 100,
                    2
                ) as positive_ratio
            FROM user_feedbacks
            WHERE message_id = $1
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, message_id)
                if row:
                    # Get top categories
                    cat_query = """
                        SELECT category, COUNT(*) as count
                        FROM user_feedbacks,
                             jsonb_array_elements_text(categories) as category
                        WHERE message_id = $1
                        GROUP BY category
                        ORDER BY count DESC
                        LIMIT 5
                    """
                    cat_rows = await conn.fetch(cat_query, message_id)
                    top_categories = [
                        {"category": r["category"], "count": r["count"]}
                        for r in cat_rows
                    ]

                    return {
                        "total_count": row["total_count"],
                        "thumbs_up_count": row["thumbs_up_count"],
                        "thumbs_down_count": row["thumbs_down_count"],
                        "positive_ratio": float(row["positive_ratio"] or 0),
                        "top_categories": top_categories,
                    }
                return {}
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting summary: {e}")
            return {}

    async def list_feedbacks(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        feedback_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List feedbacks with filters"""
        if not self.db_pool:
            return []

        conditions = ["1=1"]
        params = []
        param_idx = 1

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if feedback_type:
            conditions.append(f"feedback_type = ${param_idx}")
            params.append(feedback_type)
            param_idx += 1

        if start_date:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        query = f"""
            SELECT * FROM user_feedbacks
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error listing feedbacks: {e}")
            return []

    async def get_feedback_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get aggregated feedback statistics"""
        if not self.db_pool:
            return {}

        conditions = ["1=1"]
        params = []
        param_idx = 1

        if start_date:
            conditions.append(f"created_at >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            conditions.append(f"created_at <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        query = f"""
            SELECT
                COUNT(*) as total_feedbacks,
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up,
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down,
                ROUND(
                    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::NUMERIC /
                    NULLIF(COUNT(*), 0) * 100,
                    2
                ) as satisfaction_rate
            FROM user_feedbacks
            WHERE {' AND '.join(conditions)}
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, *params)
                if not row:
                    return {}

                # Get daily trend
                trend_query = f"""
                    SELECT
                        DATE(created_at) as date,
                        COUNT(*) as count,
                        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as positive
                    FROM user_feedbacks
                    WHERE {' AND '.join(conditions)}
                    GROUP BY DATE(created_at)
                    ORDER BY date DESC
                    LIMIT 30
                """
                trend_rows = await conn.fetch(trend_query, *params)

                # Get category distribution
                cat_query = f"""
                    SELECT category, COUNT(*) as count
                    FROM user_feedbacks,
                         jsonb_array_elements_text(categories) as category
                    WHERE {' AND '.join(conditions)}
                    GROUP BY category
                    ORDER BY count DESC
                """
                cat_rows = await conn.fetch(cat_query, *params)

                return {
                    "total_feedbacks": row["total_feedbacks"],
                    "thumbs_up": row["thumbs_up"],
                    "thumbs_down": row["thumbs_down"],
                    "satisfaction_rate": float(row["satisfaction_rate"] or 0),
                    "daily_trend": [
                        {
                            "date": str(r["date"]),
                            "count": r["count"],
                            "positive": r["positive"],
                        }
                        for r in trend_rows
                    ],
                    "category_distribution": {
                        r["category"]: r["count"] for r in cat_rows
                    },
                }
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting stats: {e}")
            return {}

    # ============================================
    # Citation Feedback
    # ============================================

    async def save_citation_feedback(self, data: Dict[str, Any]) -> None:
        """Save citation feedback"""
        if not self.db_pool:
            return

        query = """
            INSERT INTO citation_feedbacks (
                message_id, user_id, source_index,
                feedback_type, comment, doc_id, doc_name, chunk_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    data["message_id"],
                    data["user_id"],
                    data["source_index"],
                    data["feedback_type"],
                    data.get("comment"),
                    data.get("doc_id"),
                    data.get("doc_name"),
                    data.get("chunk_id"),
                )
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error saving citation feedback: {e}")

    async def get_source_quality(self, doc_id: str) -> Dict[str, Any]:
        """Get source quality metrics"""
        if not self.db_pool:
            return {}

        query = """
            SELECT * FROM v_source_quality WHERE doc_id = $1
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, doc_id)
                return dict(row) if row else {}
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting source quality: {e}")
            return {}

    # ============================================
    # HITL Re-ranking
    # ============================================

    async def save_hitl_signal(self, signal_data: Dict[str, Any]) -> None:
        """Save HITL learning signal"""
        # HITL signals are implicitly stored via feedback and reranking adjustments
        pass

    async def get_reranking_adjustment(
        self,
        doc_id: str,
        query_pattern: str,
    ) -> Optional[Dict[str, Any]]:
        """Get existing re-ranking adjustment"""
        if not self.db_pool:
            return None

        query = """
            SELECT * FROM hitl_reranking_adjustments
            WHERE document_id = $1 AND query_pattern = $2 AND is_active = TRUE
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, doc_id, query_pattern)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting reranking: {e}")
            return None

    async def create_reranking_adjustment(self, data: Dict[str, Any]) -> None:
        """Create new re-ranking adjustment"""
        if not self.db_pool:
            return

        query = """
            INSERT INTO hitl_reranking_adjustments (
                document_id, chunk_id, query_pattern,
                adjustment_score, feedback_count, positive_count, negative_count
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    data["document_id"],
                    data.get("chunk_id"),
                    data["query_pattern"],
                    data["adjustment_score"],
                    data.get("feedback_count", 1),
                    data.get("positive_count", 0),
                    data.get("negative_count", 0),
                )
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error creating reranking: {e}")

    async def update_reranking_adjustment(
        self,
        doc_id: str,
        query_pattern: str,
        data: Dict[str, Any],
    ) -> None:
        """Update re-ranking adjustment"""
        if not self.db_pool:
            return

        query = """
            UPDATE hitl_reranking_adjustments
            SET adjustment_score = $3,
                feedback_count = $4,
                positive_count = $5,
                negative_count = $6,
                updated_at = NOW()
            WHERE document_id = $1 AND query_pattern = $2 AND is_active = TRUE
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    doc_id,
                    query_pattern,
                    data["adjustment_score"],
                    data["feedback_count"],
                    data.get("positive_count", 0),
                    data.get("negative_count", 0),
                )
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error updating reranking: {e}")

    async def mark_reranking_applied(self, doc_id: str, query_pattern: str) -> None:
        """Mark re-ranking as applied"""
        if not self.db_pool:
            return

        query = """
            UPDATE hitl_reranking_adjustments
            SET applied_at = NOW()
            WHERE document_id = $1 AND query_pattern = $2
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(query, doc_id, query_pattern)
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error marking applied: {e}")

    async def update_source_quality(
        self,
        doc_id: str,
        chunk_id: Optional[str],
        adjustment: float,
    ) -> None:
        """Update source quality score"""
        # This is handled via citation_feedbacks table aggregation
        pass

    async def get_hitl_stats(self) -> Dict[str, Any]:
        """Get HITL learning statistics"""
        if not self.db_pool:
            return {}

        try:
            async with self.db_pool.acquire() as conn:
                # Get overall stats
                stats_query = """
                    SELECT
                        COUNT(*) as total_adjustments,
                        COUNT(*) FILTER (WHERE applied_at IS NOT NULL) as applied_count,
                        AVG(adjustment_score) as avg_adjustment,
                        SUM(positive_count) as total_positive,
                        SUM(negative_count) as total_negative
                    FROM hitl_reranking_adjustments
                    WHERE is_active = TRUE
                """
                row = await conn.fetchrow(stats_query)

                return {
                    "total_signals": row["total_adjustments"] if row else 0,
                    "positive_signals": row["total_positive"] if row else 0,
                    "negative_signals": row["total_negative"] if row else 0,
                    "applied_updates": row["applied_count"] if row else 0,
                    "pending_updates": (row["total_adjustments"] - row["applied_count"]) if row else 0,
                    "avg_adjustment": float(row["avg_adjustment"] or 0) if row else 0,
                }
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting HITL stats: {e}")
            return {}

    # ============================================
    # Response Consistency Cache
    # ============================================

    async def save_cached_response(self, data: Dict[str, Any]) -> None:
        """Save response to consistency cache"""
        if not self.db_pool:
            return

        query = """
            INSERT INTO response_consistency_cache (
                query_hash, query_text, query_embedding,
                answer_text, sources, language, strategy,
                feedback_score, usage_count, expires_at
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10)
            ON CONFLICT (query_hash) DO UPDATE SET
                usage_count = response_consistency_cache.usage_count + 1,
                last_used_at = NOW()
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    data["query_hash"],
                    data["query_text"],
                    data.get("query_embedding"),
                    data["answer_text"],
                    json.dumps(data.get("sources", [])),
                    data.get("language", "auto"),
                    data.get("strategy", "auto"),
                    data.get("feedback_score", 0.0),
                    data.get("usage_count", 1),
                    data.get("expires_at"),
                )
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error saving cached response: {e}")

    async def get_cached_response(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached response by query hash"""
        if not self.db_pool:
            return None

        query = """
            SELECT * FROM response_consistency_cache
            WHERE query_hash = $1 AND expires_at > NOW()
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, query_hash)
                if row:
                    # Update usage
                    await conn.execute(
                        "UPDATE response_consistency_cache SET usage_count = usage_count + 1, last_used_at = NOW() WHERE query_hash = $1",
                        query_hash
                    )
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting cached response: {e}")
            return None

    async def update_cache_score(self, query_hash: str, score_delta: float) -> None:
        """Update feedback score for cached response"""
        if not self.db_pool:
            return

        query = """
            UPDATE response_consistency_cache
            SET feedback_score = feedback_score + $2
            WHERE query_hash = $1
        """

        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(query, query_hash, score_delta)
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error updating cache score: {e}")

    async def find_similar_cached_response(
        self,
        query_embedding: List[float],
        threshold: float,
    ) -> Optional[Dict[str, Any]]:
        """Find semantically similar cached response"""
        if not self.db_pool or not query_embedding:
            return None

        query = """
            SELECT *,
                   1 - (query_embedding <=> $1::vector) as similarity
            FROM response_consistency_cache
            WHERE query_embedding IS NOT NULL
              AND expires_at > NOW()
              AND 1 - (query_embedding <=> $1::vector) >= $2
            ORDER BY similarity DESC
            LIMIT 1
        """

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(query, query_embedding, threshold)
                if row:
                    result = dict(row)
                    result["similarity"] = float(row["similarity"])
                    return result
                return None
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error finding similar response: {e}")
            return None

    async def get_consistency_stats(self) -> Dict[str, Any]:
        """Get consistency cache statistics"""
        if not self.db_pool:
            return {}

        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT
                        COUNT(*) as total_cached,
                        AVG(feedback_score) as avg_feedback_score,
                        SUM(usage_count) as total_usage,
                        AVG(consistency_score) as avg_consistency
                    FROM response_consistency_cache
                    WHERE expires_at > NOW()
                """
                row = await conn.fetchrow(query)

                return {
                    "total_cached_pairs": row["total_cached"] if row else 0,
                    "avg_consistency_score": float(row["avg_consistency"] or 0) if row else 0,
                    "cache_hit_rate": 0.0,  # Would need access logs to calculate
                }
        except Exception as e:
            logger.error(f"[FeedbackRepo] Error getting consistency stats: {e}")
            return {}


# ============================================
# Factory
# ============================================

_user_feedback_repository: Optional[UserFeedbackRepository] = None


def get_user_feedback_repository() -> Optional[UserFeedbackRepository]:
    """Get UserFeedbackRepository singleton"""
    return _user_feedback_repository


def initialize_user_feedback_repository(db_pool=None) -> UserFeedbackRepository:
    """Initialize UserFeedbackRepository with database pool"""
    global _user_feedback_repository
    _user_feedback_repository = UserFeedbackRepository(db_pool=db_pool)
    return _user_feedback_repository
