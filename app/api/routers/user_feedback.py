"""
User Feedback Router

API endpoints for:
- Response feedback (👍/👎)
- Detailed feedback with categories
- Citation feedback
- HITL statistics
- Response consistency
"""
import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..models.user_feedback import (
    FeedbackType,
    FeedbackCategory,
    PositiveFeedbackCategory,
    CitationFeedbackType,
    FeedbackStatus,
    QuickFeedbackRequest,
    DetailedFeedbackRequest,
    CitationFeedbackRequest,
    FeedbackResponse,
    FeedbackSummary,
    FeedbackDetail,
    UserFeedbackStats,
    HITLStats,
    ConsistencyCheckRequest,
    ConsistencyCheckResponse,
    ConsistencyStats,
    EnhancedCitation,
    CitationDisplayConfig,
)
from ..services.user_feedback_service import get_user_feedback_service
from ..repositories.user_feedback_repository import get_user_feedback_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ============================================
# Quick Feedback Endpoints
# ============================================

@router.post(
    "/quick",
    response_model=FeedbackResponse,
    summary="빠른 피드백 제출",
    description="👍 또는 👎로 응답에 대한 빠른 피드백을 제출합니다."
)
async def submit_quick_feedback(
    request: QuickFeedbackRequest,
    current_user: dict = Depends(get_current_user),
) -> FeedbackResponse:
    """
    빠른 피드백 제출 (👍/👎)

    - **message_id**: 피드백 대상 메시지 ID
    - **feedback_type**: thumbs_up 또는 thumbs_down
    """
    try:
        service = get_user_feedback_service()
        user_id = current_user.get("user_id", "anonymous")

        return await service.submit_quick_feedback(request, user_id)

    except Exception as e:
        logger.error(f"[Feedback] Quick feedback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post(
    "/detailed",
    response_model=FeedbackResponse,
    summary="상세 피드백 제출",
    description="카테고리와 코멘트가 포함된 상세 피드백을 제출합니다."
)
async def submit_detailed_feedback(
    request: DetailedFeedbackRequest,
    current_user: dict = Depends(get_current_user),
) -> FeedbackResponse:
    """
    상세 피드백 제출

    - **message_id**: 피드백 대상 메시지 ID
    - **feedback_type**: thumbs_up 또는 thumbs_down
    - **categories**: 피드백 카테고리 목록
    - **comment**: 추가 코멘트 (선택)
    - **expected_answer**: 기대했던 답변 (선택, HITL 학습용)
    """
    try:
        service = get_user_feedback_service()
        user_id = current_user.get("user_id", "anonymous")

        return await service.submit_detailed_feedback(request, user_id)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[Feedback] Detailed feedback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Citation Feedback Endpoints
# ============================================

@router.post(
    "/citation",
    summary="출처 피드백 제출",
    description="개별 출처/인용에 대한 피드백을 제출합니다."
)
async def submit_citation_feedback(
    request: CitationFeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    출처 피드백 제출

    - **message_id**: 메시지 ID
    - **source_index**: 출처 인덱스 (0부터 시작)
    - **feedback_type**: helpful, unhelpful, incorrect, outdated
    - **comment**: 추가 코멘트 (선택)
    """
    try:
        service = get_user_feedback_service()
        user_id = current_user.get("user_id", "anonymous")

        return await service.submit_citation_feedback(request, user_id)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[Feedback] Citation feedback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Feedback Retrieval Endpoints
# ============================================

@router.get(
    "/message/{message_id}/summary",
    response_model=FeedbackSummary,
    summary="메시지 피드백 요약",
    description="특정 메시지에 대한 피드백 요약을 조회합니다."
)
async def get_message_feedback_summary(
    message_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> FeedbackSummary:
    """메시지 피드백 요약 조회"""
    try:
        service = get_user_feedback_service()
        return await service.get_feedback_summary(message_id)
    except Exception as e:
        logger.error(f"[Feedback] Summary error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/stats",
    response_model=UserFeedbackStats,
    summary="피드백 통계",
    description="전체 피드백 통계를 조회합니다."
)
async def get_feedback_stats(
    start_date: Optional[datetime] = Query(None, description="시작일"),
    end_date: Optional[datetime] = Query(None, description="종료일"),
    current_user: dict = Depends(get_current_user),
) -> UserFeedbackStats:
    """피드백 통계 조회"""
    try:
        service = get_user_feedback_service()
        user_id = current_user.get("user_id", "anonymous")
        current_role = current_user.get("role", "user")

        # 일반 사용자는 자신의 피드백만 조회
        filter_user_id = None if current_role == "admin" else user_id

        return await service.get_feedback_stats(
            start_date=start_date,
            end_date=end_date,
            user_id=filter_user_id,
        )
    except Exception as e:
        logger.error(f"[Feedback] Stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/list",
    summary="피드백 목록",
    description="피드백 목록을 조회합니다."
)
async def list_feedbacks(
    feedback_type: Optional[FeedbackType] = Query(None, description="피드백 타입 필터"),
    status_filter: Optional[FeedbackStatus] = Query(None, alias="status", description="상태 필터"),
    start_date: Optional[datetime] = Query(None, description="시작일"),
    end_date: Optional[datetime] = Query(None, description="종료일"),
    limit: int = Query(default=50, ge=1, le=200, description="페이지당 항목 수"),
    offset: int = Query(default=0, ge=0, description="시작 위치"),
    current_user: dict = Depends(get_current_user),
):
    """피드백 목록 조회"""
    try:
        repository = get_user_feedback_repository()
        if not repository:
            return []

        user_id = current_user.get("user_id", "anonymous")
        current_role = current_user.get("role", "user")

        filter_user_id = None if current_role == "admin" else user_id

        feedbacks = await repository.list_feedbacks(
            user_id=filter_user_id,
            status=status_filter.value if status_filter else None,
            feedback_type=feedback_type.value if feedback_type else None,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        return feedbacks
    except Exception as e:
        logger.error(f"[Feedback] List error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# HITL Endpoints
# ============================================

@router.get(
    "/hitl/stats",
    response_model=HITLStats,
    summary="HITL 학습 통계",
    description="Human-in-the-Loop 학습 통계를 조회합니다."
)
async def get_hitl_stats(
    current_user: dict = Depends(get_current_user),
) -> HITLStats:
    """HITL 학습 통계 조회"""
    try:
        # Admin only
        if current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )

        service = get_user_feedback_service()
        return await service.get_hitl_stats()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Feedback] HITL stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Response Consistency Endpoints
# ============================================

@router.post(
    "/consistency/check",
    response_model=ConsistencyCheckResponse,
    summary="응답 일관성 확인",
    description="유사한 질문에 대한 캐시된 응답이 있는지 확인합니다."
)
async def check_consistency(
    request: ConsistencyCheckRequest,
    current_user: dict = Depends(get_current_user),
) -> ConsistencyCheckResponse:
    """응답 일관성 확인"""
    try:
        service = get_user_feedback_service()
        return await service.check_consistency(request)
    except Exception as e:
        logger.error(f"[Feedback] Consistency check error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get(
    "/consistency/stats",
    response_model=ConsistencyStats,
    summary="일관성 통계",
    description="응답 일관성 캐시 통계를 조회합니다."
)
async def get_consistency_stats(
    current_user: dict = Depends(get_current_user),
) -> ConsistencyStats:
    """일관성 통계 조회"""
    try:
        service = get_user_feedback_service()
        return await service.get_consistency_stats()
    except Exception as e:
        logger.error(f"[Feedback] Consistency stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Citation Enhancement Endpoints
# ============================================

class EnhanceCitationsRequest(BaseModel):
    """Request for citation enhancement"""
    sources: List[dict] = Field(..., description="소스 목록")
    config: Optional[CitationDisplayConfig] = Field(None, description="표시 설정")


@router.post(
    "/citations/enhance",
    response_model=List[EnhancedCitation],
    summary="출처 정보 강화",
    description="출처 정보에 표시 포맷과 피드백 점수를 추가합니다."
)
async def enhance_citations(
    request: EnhanceCitationsRequest,
    current_user: dict = Depends(get_current_user),
) -> List[EnhancedCitation]:
    """출처 정보 강화"""
    try:
        service = get_user_feedback_service()
        return service.enhance_citations(
            request.sources,
            request.config
        )
    except Exception as e:
        logger.error(f"[Feedback] Citation enhance error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================
# Category Info Endpoint
# ============================================

@router.get(
    "/categories",
    summary="피드백 카테고리 정보",
    description="사용 가능한 피드백 카테고리 목록을 반환합니다."
)
async def get_feedback_categories():
    """피드백 카테고리 정보 조회"""
    return {
        "negative_categories": [
            {"value": c.value, "label": _get_category_label(c.value)}
            for c in FeedbackCategory
        ],
        "positive_categories": [
            {"value": c.value, "label": _get_positive_category_label(c.value)}
            for c in PositiveFeedbackCategory
        ],
        "citation_types": [
            {"value": c.value, "label": _get_citation_label(c.value)}
            for c in CitationFeedbackType
        ],
    }


def _get_category_label(value: str) -> str:
    """Get Korean label for negative category"""
    labels = {
        "incorrect_info": "잘못된 정보",
        "incomplete": "불완전한 답변",
        "irrelevant": "관련 없는 답변",
        "outdated": "오래된 정보",
        "hallucination": "환각 (없는 내용 생성)",
        "poor_citation": "출처 부정확",
        "too_verbose": "너무 장황함",
        "too_brief": "너무 간단함",
        "wrong_language": "잘못된 언어",
        "formatting": "형식 문제",
        "other": "기타",
    }
    return labels.get(value, value)


def _get_positive_category_label(value: str) -> str:
    """Get Korean label for positive category"""
    labels = {
        "accurate": "정확한 정보",
        "helpful": "도움이 됨",
        "well_cited": "출처가 명확함",
        "comprehensive": "포괄적인 답변",
        "concise": "간결함",
        "well_formatted": "형식이 좋음",
    }
    return labels.get(value, value)


def _get_citation_label(value: str) -> str:
    """Get Korean label for citation feedback type"""
    labels = {
        "helpful": "도움이 되는 출처",
        "unhelpful": "도움이 안 되는 출처",
        "incorrect": "잘못된 출처",
        "outdated": "오래된 출처",
    }
    return labels.get(value, value)
