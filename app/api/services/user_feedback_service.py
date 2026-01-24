"""
User Feedback Service

Provides:
- Response feedback collection (👍/👎)
- Human-in-the-Loop learning signal generation
- Response consistency checking
- Citation feedback and quality tracking
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, AsyncGenerator
from uuid import UUID, uuid4

from ..models.user_feedback import (
    FeedbackType,
    FeedbackCategory,
    FeedbackStatus,
    CitationFeedbackType,
    QuickFeedbackRequest,
    DetailedFeedbackRequest,
    CitationFeedbackRequest,
    FeedbackResponse,
    FeedbackSummary,
    FeedbackDetail,
    HITLSignal,
    ReRankingUpdate,
    HITLStats,
    QueryAnswerPair,
    ConsistencyCheckRequest,
    ConsistencyCheckResponse,
    ConsistencyStats,
    EnhancedCitation,
    CitationDisplayConfig,
    UserFeedbackStats,
)

logger = logging.getLogger(__name__)


class UserFeedbackService:
    """Service for managing user feedback and HITL learning"""

    def __init__(
        self,
        repository=None,
        embedding_service=None,
        conversation_service=None,
        verified_knowledge_service=None,
    ):
        self.repository = repository
        self.embedding_service = embedding_service
        self.conversation_service = conversation_service
        self.verified_knowledge_service = verified_knowledge_service

        # Configuration
        self.consistency_threshold = 0.85
        self.hitl_min_feedback_count = 3
        self.cache_expiry_days = 30

    # ============================================
    # Feedback Collection
    # ============================================

    async def submit_quick_feedback(
        self,
        request: QuickFeedbackRequest,
        user_id: str,
    ) -> FeedbackResponse:
        """Submit quick 👍/👎 feedback"""
        try:
            # Get message context
            message_context = await self._get_message_context(request.message_id)

            feedback_id = uuid4()
            feedback_data = {
                "feedback_id": str(feedback_id),
                "message_id": str(request.message_id),
                "conversation_id": str(message_context.get("conversation_id", "")),
                "user_id": user_id,
                "feedback_type": request.feedback_type.value,
                "categories": [],
                "query_snapshot": message_context.get("query"),
                "answer_snapshot": message_context.get("answer"),
                "sources_snapshot": message_context.get("sources", []),
                "status": FeedbackStatus.PENDING.value,
            }

            # Save to repository
            if self.repository:
                await self.repository.save_feedback(feedback_data)

            # Verified Knowledge Store 연동 (Smarter RAG)
            if self.verified_knowledge_service:
                try:
                    if request.feedback_type == FeedbackType.THUMBS_UP:
                        # 👍: 학습 대상으로 등록
                        await self.verified_knowledge_service.handle_thumbs_up(
                            message_id=str(request.message_id),
                            conversation_id=str(message_context.get("conversation_id", "")),
                            user_id=user_id,
                            question=message_context.get("query", ""),
                            answer=message_context.get("answer", ""),
                            sources=message_context.get("sources", []),
                        )
                        logger.info(f"[Feedback] ✅ Registered to Verified Knowledge: {request.message_id}")
                    else:
                        # 👎: 학습에서 제거
                        await self.verified_knowledge_service.handle_thumbs_down(
                            message_id=str(request.message_id),
                        )
                        logger.info(f"[Feedback] ❌ Removed from Verified Knowledge: {request.message_id}")
                except Exception as e:
                    logger.warning(f"[Feedback] Verified Knowledge processing failed: {e}")

            # Generate HITL signal if negative
            if request.feedback_type == FeedbackType.THUMBS_DOWN:
                await self._generate_hitl_signal(feedback_data)

            logger.info(
                f"[Feedback] Quick feedback submitted: {request.feedback_type.value} "
                f"for message {request.message_id}"
            )

            return FeedbackResponse(
                feedback_id=feedback_id,
                message_id=request.message_id,
                feedback_type=request.feedback_type,
                status=FeedbackStatus.PENDING,
                created_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"[Feedback] Error submitting quick feedback: {e}")
            raise

    async def cancel_feedback(
        self,
        message_id: str,
        user_id: str,
    ) -> bool:
        """Cancel/delete feedback for a message"""
        try:
            if not self.repository:
                return False

            # Get existing feedback to check type
            existing = await self.repository.get_feedback_by_message_and_user(
                message_id, user_id
            )

            if not existing:
                logger.warning(f"[Feedback] No feedback found to cancel: {message_id}")
                return False

            # Delete from repository
            deleted = await self.repository.delete_feedback_by_message_and_user(
                message_id, user_id
            )

            if deleted:
                # Also remove from verified_knowledge if it was a thumbs_up
                if existing.get("feedback_type") == "thumbs_up" and self.verified_knowledge_service:
                    try:
                        await self.verified_knowledge_service.handle_thumbs_down(
                            message_id=message_id,
                        )
                    except Exception as e:
                        logger.warning(f"[Feedback] Error removing from verified knowledge: {e}")

                logger.info(f"[Feedback] Cancelled feedback for message: {message_id}")
                return True

            return False

        except Exception as e:
            logger.error(f"[Feedback] Error cancelling feedback: {e}")
            raise

    async def get_user_feedback_for_message(
        self,
        message_id: str,
        user_id: str,
    ) -> Optional[str]:
        """Get user's feedback type for a message (if any)"""
        try:
            if not self.repository:
                return None

            feedback = await self.repository.get_feedback_by_message_and_user(
                message_id, user_id
            )

            if feedback:
                return feedback.get("feedback_type")

            return None

        except Exception as e:
            logger.error(f"[Feedback] Error getting user feedback: {e}")
            return None

    async def submit_detailed_feedback(
        self,
        request: DetailedFeedbackRequest,
        user_id: str,
    ) -> FeedbackResponse:
        """Submit detailed feedback with categories and comments"""
        try:
            message_context = await self._get_message_context(request.message_id)

            feedback_id = uuid4()
            feedback_data = {
                "feedback_id": str(feedback_id),
                "message_id": str(request.message_id),
                "conversation_id": str(message_context.get("conversation_id", "")),
                "user_id": user_id,
                "feedback_type": request.feedback_type.value,
                "categories": request.categories,
                "comment": request.comment,
                "expected_answer": request.expected_answer,
                "query_snapshot": message_context.get("query"),
                "answer_snapshot": message_context.get("answer"),
                "sources_snapshot": message_context.get("sources", []),
                "status": FeedbackStatus.PENDING.value,
            }

            if self.repository:
                await self.repository.save_feedback(feedback_data)

            # Generate HITL signal with detailed context
            await self._generate_hitl_signal(feedback_data)

            # Update consistency cache if negative feedback
            if request.feedback_type == FeedbackType.THUMBS_DOWN:
                await self._update_consistency_cache_score(
                    message_context.get("query", ""),
                    -0.1  # Decrease score
                )

            logger.info(
                f"[Feedback] Detailed feedback submitted: {request.feedback_type.value} "
                f"with {len(request.categories)} categories"
            )

            return FeedbackResponse(
                feedback_id=feedback_id,
                message_id=request.message_id,
                feedback_type=request.feedback_type,
                categories=request.categories,
                status=FeedbackStatus.PENDING,
                created_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"[Feedback] Error submitting detailed feedback: {e}")
            raise

    async def submit_citation_feedback(
        self,
        request: CitationFeedbackRequest,
        user_id: str,
    ) -> Dict[str, Any]:
        """Submit feedback for a specific citation"""
        try:
            message_context = await self._get_message_context(request.message_id)
            sources = message_context.get("sources", [])

            if request.source_index >= len(sources):
                raise ValueError(f"Invalid source index: {request.source_index}")

            source = sources[request.source_index]

            citation_data = {
                "message_id": str(request.message_id),
                "user_id": user_id,
                "source_index": request.source_index,
                "feedback_type": request.feedback_type.value,
                "comment": request.comment,
                "doc_id": source.get("doc_id"),
                "doc_name": source.get("doc_name", source.get("source", "")),
                "chunk_id": source.get("chunk_id"),
            }

            if self.repository:
                await self.repository.save_citation_feedback(citation_data)

            # Update source quality in HITL system
            if source.get("doc_id"):
                adjustment = self._calculate_source_adjustment(request.feedback_type)
                await self._update_source_quality(
                    source.get("doc_id"),
                    source.get("chunk_id"),
                    adjustment
                )

            logger.info(
                f"[Feedback] Citation feedback: {request.feedback_type.value} "
                f"for source {request.source_index}"
            )

            return {
                "success": True,
                "message_id": str(request.message_id),
                "source_index": request.source_index,
                "feedback_type": request.feedback_type.value,
            }

        except Exception as e:
            logger.error(f"[Feedback] Error submitting citation feedback: {e}")
            raise

    # ============================================
    # Feedback Retrieval
    # ============================================

    async def get_feedback_summary(
        self,
        message_id: str,
    ) -> FeedbackSummary:
        """Get aggregated feedback summary for a message"""
        if not self.repository:
            return FeedbackSummary(message_id=message_id)

        try:
            summary = await self.repository.get_feedback_summary(str(message_id))
            # Convert types safely (PostgreSQL returns Decimal/None)
            return FeedbackSummary(
                message_id=message_id,
                thumbs_up_count=int(summary.get("thumbs_up_count") or 0),
                thumbs_down_count=int(summary.get("thumbs_down_count") or 0),
                total_count=int(summary.get("total_count") or 0),
                positive_ratio=float(summary.get("positive_ratio") or 0.0),
                top_categories=summary.get("top_categories") or [],
            )
        except Exception as e:
            logger.error(f"[Feedback] Error getting summary: {e}")
            return FeedbackSummary(message_id=message_id)

    async def get_feedback_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[str] = None,
    ) -> UserFeedbackStats:
        """Get aggregated feedback statistics"""
        if not self.repository:
            return UserFeedbackStats(
                period_start=start_date or datetime.utcnow() - timedelta(days=30),
                period_end=end_date or datetime.utcnow(),
            )

        try:
            stats = await self.repository.get_feedback_stats(
                start_date=start_date,
                end_date=end_date,
                user_id=user_id,
            )

            return UserFeedbackStats(
                period_start=start_date or datetime.utcnow() - timedelta(days=30),
                period_end=end_date or datetime.utcnow(),
                total_feedbacks=stats.get("total_feedbacks", 0),
                thumbs_up=stats.get("thumbs_up", 0),
                thumbs_down=stats.get("thumbs_down", 0),
                satisfaction_rate=stats.get("satisfaction_rate", 0.0),
                category_distribution=stats.get("category_distribution", {}),
                daily_trend=stats.get("daily_trend", []),
                top_negative_categories=stats.get("top_negative_categories", []),
                top_positive_categories=stats.get("top_positive_categories", []),
                hitl_signals_generated=stats.get("hitl_signals_generated", 0),
                hitl_updates_applied=stats.get("hitl_updates_applied", 0),
            )
        except Exception as e:
            logger.error(f"[Feedback] Error getting stats: {e}")
            raise

    # ============================================
    # HITL (Human-in-the-Loop) Learning
    # ============================================

    async def _generate_hitl_signal(
        self,
        feedback_data: Dict[str, Any],
    ) -> Optional[HITLSignal]:
        """Generate learning signal from feedback"""
        try:
            query = feedback_data.get("query_snapshot", "")
            answer = feedback_data.get("answer_snapshot", "")
            sources = feedback_data.get("sources_snapshot", [])
            feedback_type = FeedbackType(feedback_data.get("feedback_type", "thumbs_down"))
            categories = feedback_data.get("categories", [])

            if not query or not answer:
                return None

            # Calculate relevance adjustment
            relevance_adjustment = self._calculate_relevance_adjustment(
                feedback_type,
                categories
            )

            signal = HITLSignal(
                query=query,
                original_answer=answer,
                expected_answer=feedback_data.get("expected_answer"),
                feedback_type=feedback_type,
                categories=categories,
                sources=sources,
                relevance_adjustment=relevance_adjustment,
            )

            # Store signal for batch processing
            if self.repository:
                await self.repository.save_hitl_signal({
                    "query": query,
                    "answer": answer,
                    "expected_answer": feedback_data.get("expected_answer"),
                    "feedback_type": feedback_type.value,
                    "categories": categories,
                    "sources": sources,
                    "relevance_adjustment": relevance_adjustment,
                })

            # Check if we should update re-ranking
            await self._check_and_apply_reranking(query, sources, relevance_adjustment)

            return signal

        except Exception as e:
            logger.error(f"[HITL] Error generating signal: {e}")
            return None

    def _calculate_relevance_adjustment(
        self,
        feedback_type: FeedbackType,
        categories: List[str],
    ) -> float:
        """Calculate relevance adjustment score based on feedback"""
        base_score = 0.1 if feedback_type == FeedbackType.THUMBS_UP else -0.1

        # Adjust based on categories
        category_weights = {
            FeedbackCategory.HALLUCINATION.value: -0.3,
            FeedbackCategory.INCORRECT_INFO.value: -0.25,
            FeedbackCategory.IRRELEVANT.value: -0.2,
            FeedbackCategory.POOR_CITATION.value: -0.15,
            FeedbackCategory.INCOMPLETE.value: -0.1,
            FeedbackCategory.OUTDATED.value: -0.1,
        }

        for cat in categories:
            if cat in category_weights:
                base_score += category_weights[cat]

        return max(-1.0, min(1.0, base_score))

    def _calculate_source_adjustment(
        self,
        feedback_type: CitationFeedbackType,
    ) -> float:
        """Calculate source quality adjustment"""
        adjustments = {
            CitationFeedbackType.HELPFUL: 0.1,
            CitationFeedbackType.UNHELPFUL: -0.1,
            CitationFeedbackType.INCORRECT: -0.2,
            CitationFeedbackType.OUTDATED: -0.15,
        }
        return adjustments.get(feedback_type, 0.0)

    async def _check_and_apply_reranking(
        self,
        query: str,
        sources: List[Dict[str, Any]],
        adjustment: float,
    ) -> None:
        """Check feedback count and apply re-ranking if threshold met"""
        if not self.repository:
            return

        try:
            # Generalize query pattern (simple normalization)
            query_pattern = self._normalize_query(query)

            for source in sources:
                doc_id = source.get("doc_id")
                if not doc_id:
                    continue

                # Get current feedback count for this pattern
                current = await self.repository.get_reranking_adjustment(
                    doc_id,
                    query_pattern
                )

                if current:
                    new_count = current.get("feedback_count", 0) + 1
                    new_adjustment = (
                        current.get("adjustment_score", 0) * current.get("feedback_count", 1) +
                        adjustment
                    ) / new_count

                    await self.repository.update_reranking_adjustment(
                        doc_id,
                        query_pattern,
                        {
                            "adjustment_score": new_adjustment,
                            "feedback_count": new_count,
                            "positive_count": current.get("positive_count", 0) + (1 if adjustment > 0 else 0),
                            "negative_count": current.get("negative_count", 0) + (1 if adjustment < 0 else 0),
                        }
                    )

                    # Apply if threshold met
                    if new_count >= self.hitl_min_feedback_count:
                        await self._apply_reranking(doc_id, query_pattern, new_adjustment)
                else:
                    # Create new entry
                    await self.repository.create_reranking_adjustment({
                        "document_id": doc_id,
                        "chunk_id": source.get("chunk_id"),
                        "query_pattern": query_pattern,
                        "adjustment_score": adjustment,
                        "feedback_count": 1,
                        "positive_count": 1 if adjustment > 0 else 0,
                        "negative_count": 1 if adjustment < 0 else 0,
                    })

        except Exception as e:
            logger.error(f"[HITL] Error checking reranking: {e}")

    async def _apply_reranking(
        self,
        doc_id: str,
        query_pattern: str,
        adjustment: float,
    ) -> None:
        """Apply re-ranking adjustment to search system"""
        logger.info(
            f"[HITL] Applying re-ranking: doc={doc_id}, "
            f"pattern={query_pattern[:50]}..., adjustment={adjustment:.2f}"
        )

        if self.repository:
            await self.repository.mark_reranking_applied(doc_id, query_pattern)

    async def _update_source_quality(
        self,
        doc_id: str,
        chunk_id: Optional[str],
        adjustment: float,
    ) -> None:
        """Update source quality score"""
        if not self.repository:
            return

        try:
            await self.repository.update_source_quality(
                doc_id,
                chunk_id,
                adjustment
            )
        except Exception as e:
            logger.error(f"[HITL] Error updating source quality: {e}")

    def _normalize_query(self, query: str) -> str:
        """Normalize query for pattern matching"""
        # Simple normalization: lowercase, strip, remove extra spaces
        normalized = " ".join(query.lower().strip().split())
        return normalized[:500]  # Limit length

    async def get_hitl_stats(self) -> HITLStats:
        """Get HITL learning statistics"""
        if not self.repository:
            return HITLStats()

        try:
            stats = await self.repository.get_hitl_stats()
            return HITLStats(**stats)
        except Exception as e:
            logger.error(f"[HITL] Error getting stats: {e}")
            return HITLStats()

    # ============================================
    # Response Consistency
    # ============================================

    async def check_consistency(
        self,
        request: ConsistencyCheckRequest,
    ) -> ConsistencyCheckResponse:
        """Check if a similar query has a cached response"""
        try:
            query_hash = self._hash_query(request.query)

            if self.repository:
                cached = await self.repository.get_cached_response(query_hash)

                if cached and cached.get("feedback_score", 0) >= 0:
                    return ConsistencyCheckResponse(
                        has_similar_query=True,
                        similar_query=cached.get("query_text"),
                        cached_answer=cached.get("answer_text"),
                        similarity_score=1.0,  # Exact match
                        recommendation="use_cached" if cached.get("feedback_score", 0) > 0 else "review_needed",
                    )

            # Check semantic similarity if embedding service available
            if self.embedding_service:
                similar = await self._find_similar_query(
                    request.query,
                    request.threshold
                )
                if similar:
                    return ConsistencyCheckResponse(
                        has_similar_query=True,
                        similar_query=similar.get("query"),
                        cached_answer=similar.get("answer"),
                        similarity_score=similar.get("similarity", 0.0),
                        recommendation="review_needed",
                    )

            return ConsistencyCheckResponse(
                has_similar_query=False,
                recommendation="generate_new",
            )

        except Exception as e:
            logger.error(f"[Consistency] Error checking: {e}")
            return ConsistencyCheckResponse(
                has_similar_query=False,
                recommendation="generate_new",
            )

    async def cache_response(
        self,
        query: str,
        answer: str,
        sources: List[Dict[str, Any]],
        language: str = "auto",
        strategy: str = "auto",
    ) -> None:
        """Cache a response for consistency"""
        if not self.repository:
            return

        try:
            query_hash = self._hash_query(query)

            # Generate embedding if service available
            query_embedding = None
            if self.embedding_service:
                try:
                    query_embedding = await self.embedding_service.get_embedding(query)
                except Exception:
                    pass

            await self.repository.save_cached_response({
                "query_hash": query_hash,
                "query_text": query,
                "query_embedding": query_embedding,
                "answer_text": answer,
                "sources": sources,
                "language": language,
                "strategy": strategy,
                "feedback_score": 0.0,
                "usage_count": 1,
                "expires_at": datetime.utcnow() + timedelta(days=self.cache_expiry_days),
            })

        except Exception as e:
            logger.error(f"[Consistency] Error caching response: {e}")

    async def _update_consistency_cache_score(
        self,
        query: str,
        score_delta: float,
    ) -> None:
        """Update feedback score for cached response"""
        if not self.repository or not query:
            return

        try:
            query_hash = self._hash_query(query)
            await self.repository.update_cache_score(query_hash, score_delta)
        except Exception as e:
            logger.error(f"[Consistency] Error updating cache score: {e}")

    def _hash_query(self, query: str) -> str:
        """Generate hash for query"""
        normalized = self._normalize_query(query)
        return hashlib.sha256(normalized.encode()).hexdigest()

    async def _find_similar_query(
        self,
        query: str,
        threshold: float,
    ) -> Optional[Dict[str, Any]]:
        """Find semantically similar cached query"""
        if not self.embedding_service or not self.repository:
            return None

        try:
            query_embedding = await self.embedding_service.get_embedding(query)
            similar = await self.repository.find_similar_cached_response(
                query_embedding,
                threshold
            )
            return similar
        except Exception:
            return None

    async def get_consistency_stats(self) -> ConsistencyStats:
        """Get response consistency statistics"""
        if not self.repository:
            return ConsistencyStats()

        try:
            stats = await self.repository.get_consistency_stats()
            return ConsistencyStats(**stats)
        except Exception as e:
            logger.error(f"[Consistency] Error getting stats: {e}")
            return ConsistencyStats()

    # ============================================
    # Citation Enhancement
    # ============================================

    def enhance_citations(
        self,
        sources: List[Dict[str, Any]],
        config: Optional[CitationDisplayConfig] = None,
    ) -> List[EnhancedCitation]:
        """Enhance citations with display formatting"""
        if config is None:
            config = CitationDisplayConfig()

        enhanced = []
        for i, source in enumerate(sources):
            citation_parts = [f"[{i + 1}]"]

            doc_name = source.get("doc_name", source.get("source", "Unknown"))
            citation_parts.append(doc_name)

            if config.show_page_numbers and source.get("page_number"):
                citation_parts.append(f"p.{source['page_number']}")

            if config.show_section_titles and source.get("section_title"):
                citation_parts.append(f"§{source['section_title']}")

            citation_text = " ".join(citation_parts)

            content = source.get("content", "")
            preview = content[:config.max_preview_length]
            if len(content) > config.max_preview_length:
                preview += "..."

            enhanced.append(EnhancedCitation(
                source_index=i,
                doc_id=source.get("doc_id"),
                doc_name=doc_name,
                chunk_id=source.get("chunk_id"),
                content_preview=preview,
                full_content=content,
                score=source.get("score", 0.0),
                source_type=source.get("source_type", "vector"),
                page_number=source.get("page_number"),
                section_title=source.get("section_title"),
                source_url=source.get("source_url"),
                citation_text=citation_text,
            ))

        return enhanced

    # ============================================
    # Helper Methods
    # ============================================

    async def _get_message_context(
        self,
        message_id: str,
    ) -> Dict[str, Any]:
        """Get message context for feedback"""
        if self.conversation_service:
            try:
                message = await self.conversation_service.get_message(message_id)
                if message:
                    # Get the user's question (previous message)
                    query = await self.conversation_service.get_parent_message_content(
                        str(message_id)
                    )
                    return {
                        "conversation_id": message.get("conversation_id"),
                        "query": query,
                        "answer": message.get("content"),
                        "sources": message.get("sources", []),
                    }
            except Exception as e:
                logger.warning(f"[Feedback] Error getting message context: {e}")

        return {
            "conversation_id": None,
            "query": None,
            "answer": None,
            "sources": [],
        }


# ============================================
# Service Factory
# ============================================

_user_feedback_service: Optional[UserFeedbackService] = None


def get_user_feedback_service() -> UserFeedbackService:
    """Get or create UserFeedbackService singleton"""
    global _user_feedback_service
    if _user_feedback_service is None:
        _user_feedback_service = UserFeedbackService()
    return _user_feedback_service


def initialize_user_feedback_service(
    repository=None,
    embedding_service=None,
    conversation_service=None,
    verified_knowledge_service=None,
) -> UserFeedbackService:
    """Initialize UserFeedbackService with dependencies"""
    global _user_feedback_service
    _user_feedback_service = UserFeedbackService(
        repository=repository,
        embedding_service=embedding_service,
        conversation_service=conversation_service,
        verified_knowledge_service=verified_knowledge_service,
    )
    return _user_feedback_service
