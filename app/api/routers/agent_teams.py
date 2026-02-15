"""
Agent Teams Feedback Router

Pattern E (Self-Improvement) 피드백 API 엔드포인트.
사용자 피드백 수집, 학습 데이터 생성/내보내기, 통계 제공.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-teams", tags=["Agent Teams"])


# =============================================================================
# Request/Response Models
# =============================================================================

class FeedbackRequest(BaseModel):
    """사용자 피드백 제출 요청"""
    query: str = Field(..., description="원래 질문")
    product: str = Field(..., description="제품 ID")
    feedback: str = Field(..., description="positive 또는 negative")
    answer: Optional[str] = Field(None, description="생성된 답변")
    comment: Optional[str] = Field(None, description="사용자 코멘트")


class ExportRequest(BaseModel):
    """QLoRA 학습 데이터 내보내기 요청"""
    min_score: float = Field(default=0.7, ge=0.0, le=1.0, description="최소 점수 기준")
    output_path: Optional[str] = Field(None, description="출력 파일 경로 (미지정 시 자동 생성)")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/feedback", summary="사용자 피드백 제출")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    RAG 응답에 대한 사용자 피드백을 기록합니다.
    축적된 피드백은 QLoRA 재학습 데이터로 활용됩니다.
    """
    from ..services.agent_teams.self_improvement import get_self_improvement_service

    service = get_self_improvement_service()
    recorded = service.record_user_feedback(
        query=request.query,
        product=request.product,
        feedback=request.feedback,
        answer=request.answer,
        comment=request.comment,
    )

    return {
        "status": "ok",
        "recorded": recorded,
        "message": "피드백이 기록되었습니다." if recorded else "중복 피드백입니다.",
    }


@router.get("/feedback/stats", summary="피드백 통계 조회")
async def get_feedback_stats(
    current_user: dict = Depends(get_current_user),
):
    """축적된 피드백 통계를 반환합니다."""
    from ..services.agent_teams.self_improvement import get_self_improvement_service

    service = get_self_improvement_service()
    stats = service.get_stats()

    return {"status": "ok", "data": stats}


@router.post("/feedback/export", summary="QLoRA 학습 데이터 내보내기")
async def export_training_data(
    request: ExportRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    축적된 피드백에서 QLoRA 학습용 JSONL 데이터를 내보냅니다.
    scripts/training/convert_to_qlora.py 호환 포맷.
    """
    from ..services.agent_teams.self_improvement import get_self_improvement_service

    service = get_self_improvement_service()

    candidates = service.generate_training_candidates(
        min_score=request.min_score,
    )
    output_path = service.export_qlora_dataset(
        output_path=request.output_path,
        min_score=request.min_score,
    )

    return {
        "status": "ok",
        "output_path": output_path,
        "stats": candidates["stats"],
    }


@router.get("/feedback/suggestions", summary="개선 제안 조회")
async def get_improvement_suggestions(
    current_user: dict = Depends(get_current_user),
):
    """피드백 분석에서 자동 생성된 개선 제안을 반환합니다."""
    from ..services.agent_teams.self_improvement import get_self_improvement_service

    service = get_self_improvement_service()
    suggestions = service.get_improvement_suggestions()

    return {
        "status": "ok",
        "suggestions": suggestions,
        "count": len(suggestions),
    }
