"""
Verified Knowledge Service

Smarter RAG 시스템의 핵심 서비스:
- 👍 피드백 → 자동 학습 등록
- 👎 피드백 → 학습에서 제거 (unlearn)
- Verified Knowledge Store 관리
- Learning LLM 학습 파이프라인
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from ..infrastructure.postgres.verified_knowledge_repository import (
    PostgresVerifiedKnowledgeRepository,
    VerifiedKnowledgeEntity,
    TrainingBatchEntity,
)

logger = logging.getLogger(__name__)


class VerifiedKnowledgeService:
    """
    Verified Knowledge 관리 서비스

    핵심 기능:
    1. 피드백 처리: 👍 → 학습 등록, 👎 → 학습 제거
    2. 검색: RAG에서 Verified Knowledge 우선 검색
    3. 학습 관리: 배치 학습, Unlearn 처리
    4. 통계: 학습 현황, 품질 메트릭
    """

    def __init__(
        self,
        repository: PostgresVerifiedKnowledgeRepository,
        embedding_service=None,
        min_similarity_threshold: float = 0.85,
    ):
        self.repository = repository
        self.embedding_service = embedding_service
        self.min_similarity_threshold = min_similarity_threshold

    # ============================================
    # 피드백 처리 (👍/👎)
    # ============================================

    async def handle_thumbs_up(
        self,
        message_id: str,
        conversation_id: str,
        user_id: str,
        question: str,
        answer: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        category: Optional[str] = None,
        language: str = "ko",
    ) -> VerifiedKnowledgeEntity:
        """
        👍 피드백 처리: Verified Knowledge Store에 등록

        Args:
            message_id: 메시지 ID
            conversation_id: 대화 ID
            user_id: 사용자 ID
            question: 사용자 질문
            answer: 시스템 응답
            sources: 참조 문서들
            category: 카테고리
            language: 언어

        Returns:
            생성/업데이트된 VerifiedKnowledgeEntity
        """
        logger.info(f"[VerifiedKnowledge] 👍 Processing thumbs_up for message: {message_id}")

        # Validate required fields - reject empty question/answer
        if not question or not question.strip():
            logger.warning(
                f"[VerifiedKnowledge] ❌ Rejected thumbs_up: empty question for message {message_id}"
            )
            raise ValueError("Question is required for verified knowledge registration")

        if not answer or not answer.strip():
            logger.warning(
                f"[VerifiedKnowledge] ❌ Rejected thumbs_up: empty answer for message {message_id}"
            )
            raise ValueError("Answer is required for verified knowledge registration")

        # Verified Knowledge Store에 등록
        entity = await self.repository.create(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            question=question,
            answer=answer,
            source_documents=sources,
            category=category,
            language=language,
        )

        # 임베딩 생성 (백그라운드)
        if self.embedding_service:
            try:
                embedding = await self.embedding_service.get_embedding(question)
                await self.repository.update_embedding(entity.id, embedding)
                logger.info(f"[VerifiedKnowledge] Embedding generated for: {entity.id}")
            except Exception as e:
                logger.warning(f"[VerifiedKnowledge] Failed to generate embedding: {e}")

        logger.info(
            f"[VerifiedKnowledge] ✅ Registered for learning: id={entity.id}, "
            f"score={entity.feedback_score}, thumbs_up={entity.thumbs_up_count}"
        )

        return entity

    async def handle_thumbs_down(
        self,
        message_id: str,
    ) -> bool:
        """
        👎 피드백 처리: Verified Knowledge Store에서 제거 / Unlearn 마킹

        Args:
            message_id: 메시지 ID

        Returns:
            처리 성공 여부
        """
        logger.info(f"[VerifiedKnowledge] 👎 Processing thumbs_down for message: {message_id}")

        success = await self.repository.remove_by_message_id(message_id)

        if success:
            logger.info(f"[VerifiedKnowledge] ❌ Removed/marked for unlearning: {message_id}")
        else:
            logger.info(f"[VerifiedKnowledge] No entry found for message: {message_id}")

        return success

    # ============================================
    # 검색 (RAG 통합용)
    # ============================================

    async def search(
        self,
        query: str,
        limit: int = 5,
        min_similarity: Optional[float] = None,
        language: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Tuple[VerifiedKnowledgeEntity, float]]:
        """
        Verified Knowledge 검색

        RAG 파이프라인에서 문서 검색 전에 호출.
        높은 유사도의 검증된 지식이 있으면 해당 답변을 우선 사용.

        Args:
            query: 검색 쿼리
            limit: 최대 결과 수
            min_similarity: 최소 유사도 (기본: self.min_similarity_threshold)
            language: 언어 필터
            category: 카테고리 필터

        Returns:
            (VerifiedKnowledgeEntity, similarity_score) 튜플 리스트
        """
        threshold = min_similarity or self.min_similarity_threshold

        # 임베딩 기반 검색 시도
        if self.embedding_service:
            try:
                query_embedding = await self.embedding_service.get_embedding(query)
                results = await self.repository.search_by_embedding(
                    embedding=query_embedding,
                    limit=limit,
                    min_similarity=threshold,
                    language=language,
                    category=category,
                )
                if results:
                    logger.info(
                        f"[VerifiedKnowledge] Found {len(results)} matches via embedding search "
                        f"(top score: {results[0][1]:.3f})"
                    )
                    return results
            except Exception as e:
                logger.warning(f"[VerifiedKnowledge] Embedding search failed: {e}")

        # 폴백: 텍스트 기반 검색
        results = await self.repository.search_by_text(
            query=query,
            limit=limit,
            min_score=0.3,  # 텍스트 검색은 더 낮은 임계값
            language=language,
            category=category,
        )

        if results:
            logger.info(
                f"[VerifiedKnowledge] Found {len(results)} matches via text search "
                f"(top score: {results[0][1]:.3f})"
            )

        return results

    async def get_best_match(
        self,
        query: str,
        min_similarity: Optional[float] = None,
        language: Optional[str] = None,
    ) -> Optional[Tuple[VerifiedKnowledgeEntity, float]]:
        """
        가장 좋은 매칭 결과 반환

        Returns:
            (entity, score) 또는 None
        """
        results = await self.search(
            query=query,
            limit=1,
            min_similarity=min_similarity,
            language=language,
        )
        return results[0] if results else None

    async def record_usage(
        self,
        knowledge_id: str,
        query: str,
        similarity_score: float,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """검증된 지식 사용 기록"""
        await self.repository.record_usage(
            knowledge_id=knowledge_id,
            query=query,
            similarity_score=similarity_score,
            conversation_id=conversation_id,
            user_id=user_id,
            source_type="verified",
        )

    # ============================================
    # 학습 파이프라인
    # ============================================

    async def get_training_data(
        self,
        min_feedback_score: float = 0.8,
        min_thumbs_up: int = 1,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        학습용 데이터 수집

        Returns:
            Instruction-tuning 형식의 학습 데이터
            [
                {
                    "id": "...",
                    "instruction": "사용자 질문",
                    "input": "",  # 컨텍스트 (optional)
                    "output": "검증된 응답"
                },
                ...
            ]
        """
        entities = await self.repository.get_training_ready(
            min_feedback_score=min_feedback_score,
            min_thumbs_up=min_thumbs_up,
            limit=limit,
        )

        training_data = []
        for entity in entities:
            training_data.append({
                "id": entity.id,
                "instruction": entity.question,
                "input": "",  # 필요시 source_documents 요약 추가
                "output": entity.answer,
                "metadata": {
                    "category": entity.category,
                    "language": entity.language,
                    "feedback_score": entity.feedback_score,
                    "thumbs_up_count": entity.thumbs_up_count,
                }
            })

        logger.info(f"[VerifiedKnowledge] Collected {len(training_data)} training samples")
        return training_data

    async def get_unlearn_data(
        self,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Unlearn 대상 데이터 수집 (👎 받은 학습된 지식)

        Returns:
            Unlearn 대상 데이터
            [
                {
                    "id": "...",
                    "instruction": "사용자 질문",
                    "output": "제거할 응답",
                    "training_batch_id": "원래 학습된 배치",
                },
                ...
            ]
        """
        entities = await self.repository.get_unlearn_required(limit=limit)

        unlearn_data = []
        for entity in entities:
            unlearn_data.append({
                "id": entity.id,
                "instruction": entity.question,
                "output": entity.answer,
                "training_batch_id": entity.training_batch_id,
                "training_version": entity.training_version,
            })

        logger.info(f"[VerifiedKnowledge] Collected {len(unlearn_data)} unlearn samples")
        return unlearn_data

    async def create_training_batch(
        self,
        min_feedback_score: float = 0.8,
        min_thumbs_up: int = 1,
        base_model: str = "Qwen2.5-7B-Instruct",
        scheduled_at: Optional[datetime] = None,
    ) -> Optional[TrainingBatchEntity]:
        """
        새 학습 배치 생성

        Returns:
            TrainingBatchEntity 또는 샘플이 없으면 None
        """
        # 학습 대상 수집
        training_data = await self.get_training_data(
            min_feedback_score=min_feedback_score,
            min_thumbs_up=min_thumbs_up,
        )

        # Unlearn 대상 수집
        unlearn_data = await self.get_unlearn_data()

        if not training_data and not unlearn_data:
            logger.info("[VerifiedKnowledge] No samples for training/unlearning")
            return None

        # 배치 ID 생성
        now = datetime.now(timezone.utc)
        batch_id = f"batch_{now.strftime('%Y%m%d_%H%M%S')}"

        batch = await self.repository.create_training_batch(
            batch_id=batch_id,
            total_samples=len(training_data),
            min_feedback_score=min_feedback_score,
            min_thumbs_up=min_thumbs_up,
            base_model=base_model,
            scheduled_at=scheduled_at or now,
        )

        logger.info(
            f"[VerifiedKnowledge] Created training batch: {batch_id}, "
            f"train={len(training_data)}, unlearn={len(unlearn_data)}"
        )

        return batch

    async def complete_training(
        self,
        batch_id: str,
        trained_ids: List[str],
        unlearned_ids: List[str],
        adapter_name: str,
        training_version: int,
        eval_metrics: Optional[Dict[str, float]] = None,
    ) -> bool:
        """
        학습 완료 처리

        Args:
            batch_id: 배치 ID
            trained_ids: 학습 완료된 지식 ID 리스트
            unlearned_ids: Unlearn 완료된 지식 ID 리스트
            adapter_name: 생성된 어댑터 이름
            training_version: 학습 버전
            eval_metrics: 평가 메트릭 (loss, accuracy, perplexity)

        Returns:
            성공 여부
        """
        # 학습된 항목 마킹
        if trained_ids:
            await self.repository.mark_as_trained(
                entity_ids=trained_ids,
                batch_id=batch_id,
                training_version=training_version,
            )

        # Unlearn 완료 마킹
        if unlearned_ids:
            await self.repository.mark_as_unlearned(
                entity_ids=unlearned_ids,
                batch_id=batch_id,
            )

        # 배치 상태 업데이트
        await self.repository.update_training_batch_status(
            batch_id=batch_id,
            status="completed",
            trained_samples=len(trained_ids),
            adapter_name=adapter_name,
            eval_metrics=eval_metrics,
        )

        logger.info(
            f"[VerifiedKnowledge] Training completed: batch={batch_id}, "
            f"trained={len(trained_ids)}, unlearned={len(unlearned_ids)}, "
            f"adapter={adapter_name}"
        )

        return True

    async def fail_training(
        self,
        batch_id: str,
        error_message: str,
    ) -> bool:
        """학습 실패 처리"""
        await self.repository.update_training_batch_status(
            batch_id=batch_id,
            status="failed",
            error_message=error_message,
        )
        logger.error(f"[VerifiedKnowledge] Training failed: batch={batch_id}, error={error_message}")
        return True

    # ============================================
    # 통계
    # ============================================

    async def get_stats(self) -> Dict[str, Any]:
        """전체 통계 조회"""
        stats = await self.repository.get_stats()

        # Unlearn 대기 수 추가
        unlearn_pending = await self.repository.count(
            status="unlearn_required",
            is_trained=True,
        )
        stats["unlearn_pending_count"] = unlearn_pending

        return stats

    async def get_category_stats(self) -> List[Dict[str, Any]]:
        """카테고리별 통계"""
        return await self.repository.get_category_stats()

    async def get_daily_stats(self, days: int = 30) -> List[Dict[str, Any]]:
        """일별 통계"""
        return await self.repository.get_daily_stats(days=days)

    async def get_training_batches(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[TrainingBatchEntity]:
        """학습 배치 목록"""
        return await self.repository.list_training_batches(
            status=status,
            limit=limit,
        )

    # ============================================
    # 관리
    # ============================================

    async def get_by_id(self, entity_id: str) -> Optional[VerifiedKnowledgeEntity]:
        """ID로 조회"""
        return await self.repository.get(entity_id)

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        is_trained: Optional[bool] = None,
        category: Optional[str] = None,
        language: Optional[str] = None,
        min_feedback_score: Optional[float] = None,
    ) -> List[VerifiedKnowledgeEntity]:
        """목록 조회"""
        return await self.repository.list(
            skip=skip,
            limit=limit,
            status=status,
            is_trained=is_trained,
            category=category,
            language=language,
            min_feedback_score=min_feedback_score,
        )

    async def update_category(
        self,
        entity_id: str,
        category: str,
    ) -> Optional[VerifiedKnowledgeEntity]:
        """카테고리 업데이트"""
        entity = await self.repository.get(entity_id)
        if not entity:
            return None
        entity.category = category
        return await self.repository.update(entity)

    async def deprecate(
        self,
        entity_id: str,
        reason: str,
    ) -> bool:
        """지식 비활성화"""
        return await self.repository.deprecate(entity_id, reason)

    # ============================================
    # 스케줄 관리
    # ============================================

    async def get_training_schedule(self) -> Optional[Dict[str, Any]]:
        """학습 스케줄 조회"""
        return await self.repository.get_training_schedule()

    async def update_training_schedule(
        self,
        cron_expression: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        min_samples_required: Optional[int] = None,
        auto_deploy: Optional[bool] = None,
    ) -> bool:
        """학습 스케줄 업데이트"""
        return await self.repository.update_training_schedule(
            cron_expression=cron_expression,
            is_enabled=is_enabled,
            min_samples_required=min_samples_required,
            auto_deploy=auto_deploy,
        )


# ============================================
# Service Factory
# ============================================

_verified_knowledge_service: Optional[VerifiedKnowledgeService] = None


def get_verified_knowledge_service() -> Optional[VerifiedKnowledgeService]:
    """Get VerifiedKnowledgeService singleton"""
    global _verified_knowledge_service
    return _verified_knowledge_service


def initialize_verified_knowledge_service(
    repository: PostgresVerifiedKnowledgeRepository,
    embedding_service=None,
    min_similarity_threshold: float = 0.85,
) -> VerifiedKnowledgeService:
    """Initialize VerifiedKnowledgeService with dependencies"""
    global _verified_knowledge_service
    _verified_knowledge_service = VerifiedKnowledgeService(
        repository=repository,
        embedding_service=embedding_service,
        min_similarity_threshold=min_similarity_threshold,
    )
    logger.info("[VerifiedKnowledge] Service initialized")
    return _verified_knowledge_service
