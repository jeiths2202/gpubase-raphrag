"""
RAG Evaluation Router
RAGAS 스타일 RAG 품질 평가 API 엔드포인트
"""
import json
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ..core.deps import get_current_user
from ..models.rag_evaluation import (
    RAGMetricType,
    RAGEvaluationLevel,
    RAGEvaluationRequest,
    RAGEvaluationResponse,
    RAGEvaluationResult,
    RAGEvaluationStats,
    RAGEvaluationListItem,
    RAGEvaluationStatsRequest,
)
from ..services.rag_evaluation_service import get_rag_evaluation_service
from ..repositories.rag_evaluation_repository import get_rag_evaluation_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag-evaluation", tags=["rag-evaluation"])


@router.post(
    "/evaluate",
    response_model=RAGEvaluationResponse,
    summary="RAG 응답 품질 평가",
    description="RAGAS 스타일로 RAG 응답의 품질을 평가합니다. "
                "Faithfulness, Context Relevance, Answer Relevancy, "
                "Context Precision, Context Recall 메트릭을 계산합니다."
)
async def evaluate_rag_response(
    request: RAGEvaluationRequest,
    current_user: dict = Depends(get_current_user),
) -> RAGEvaluationResponse:
    """
    RAG 응답 품질 평가 (동기)

    - **query**: 원본 질문
    - **answer**: 생성된 응답
    - **sources**: 검색된 소스 목록
    - **ground_truth**: 정답 (Context Recall 계산용, 선택적)
    - **metrics_to_evaluate**: 평가할 메트릭 목록 (선택적, 기본=전체)
    """
    try:
        service = get_rag_evaluation_service()
        user_id = current_user.get("user_id", "anonymous")

        result = await service.evaluate(
            query=request.query,
            answer=request.answer,
            sources=request.sources,
            ground_truth=request.ground_truth,
            metrics_to_evaluate=request.metrics_to_evaluate,
            language=request.language,
            trace_id=request.trace_id,
            conversation_id=request.conversation_id,
            user_id=user_id,
        )

        return RAGEvaluationResponse(
            success=True,
            evaluation=result,
        )

    except Exception as e:
        logger.error(f"[RAGEval] Evaluation failed: {e}")
        return RAGEvaluationResponse(
            success=False,
            error=str(e),
        )


@router.post(
    "/evaluate/stream",
    summary="RAG 응답 품질 평가 (스트리밍)",
    description="각 메트릭 평가 완료 시마다 결과를 스트리밍합니다."
)
async def evaluate_rag_response_stream(
    request: RAGEvaluationRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    RAG 응답 품질 평가 (스트리밍)

    Server-Sent Events로 각 메트릭 평가 결과를 실시간 전송합니다.
    """
    user_id = current_user.get("user_id", "anonymous")

    async def generate():
        try:
            service = get_rag_evaluation_service()

            async for chunk in service.evaluate_stream(request, user_id):
                data = chunk.model_dump_json()
                yield f"data: {data}\n\n"

        except Exception as e:
            logger.error(f"[RAGEval] Stream evaluation failed: {e}")
            error_data = json.dumps({
                "chunk_type": "error",
                "message": str(e),
            })
            yield f"data: {error_data}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get(
    "/stats",
    response_model=RAGEvaluationStats,
    summary="RAG 평가 통계 조회",
    description="전체 평가 통계, 메트릭별 평균, 등급 분포, 자주 발생하는 이슈 등을 조회합니다."
)
async def get_evaluation_stats(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
) -> RAGEvaluationStats:
    """
    RAG 평가 통계 조회

    - **start_date**: 시작일 (선택적)
    - **end_date**: 종료일 (선택적)
    - **user_id**: 사용자 ID 필터 (선택적, admin만 다른 사용자 조회 가능)
    """
    repository = get_rag_evaluation_repository()
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG evaluation repository not available"
        )

    # 일반 사용자는 자신의 통계만 조회 가능
    current_user_id = current_user.get("user_id", "anonymous")
    current_role = current_user.get("role", "user")

    if user_id and user_id != current_user_id and current_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view other user's statistics"
        )

    filter_user_id = user_id if user_id else (
        None if current_role == "admin" else current_user_id
    )

    return await repository.get_stats(
        user_id=filter_user_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/list",
    response_model=list[RAGEvaluationListItem],
    summary="RAG 평가 목록 조회",
    description="평가 결과 목록을 페이지네이션으로 조회합니다."
)
async def list_evaluations(
    level_filter: Optional[RAGEvaluationLevel] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
) -> list[RAGEvaluationListItem]:
    """
    RAG 평가 목록 조회

    - **level_filter**: 등급 필터 (excellent, good, fair, poor)
    - **start_date**: 시작일
    - **end_date**: 종료일
    - **limit**: 페이지당 항목 수 (기본: 20)
    - **offset**: 시작 위치 (기본: 0)
    """
    repository = get_rag_evaluation_repository()
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG evaluation repository not available"
        )

    user_id = current_user.get("user_id", "anonymous")
    current_role = current_user.get("role", "user")

    # 일반 사용자는 자신의 평가만 조회
    filter_user_id = None if current_role == "admin" else user_id

    return await repository.list_evaluations(
        user_id=filter_user_id,
        level_filter=level_filter,
        start_date=start_date,
        end_date=end_date,
        limit=min(limit, 100),  # 최대 100개
        offset=offset,
    )


@router.get(
    "/{evaluation_id}",
    response_model=RAGEvaluationResponse,
    summary="개별 평가 결과 조회",
    description="평가 ID로 상세 결과를 조회합니다."
)
async def get_evaluation(
    evaluation_id: str,
    current_user: dict = Depends(get_current_user),
) -> RAGEvaluationResponse:
    """
    개별 평가 결과 조회

    - **evaluation_id**: 평가 ID
    """
    repository = get_rag_evaluation_repository()
    if not repository:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG evaluation repository not available"
        )

    result = await repository.get_by_id(evaluation_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation not found: {evaluation_id}"
        )

    return RAGEvaluationResponse(
        success=True,
        evaluation=result,
    )


@router.get(
    "/metrics/info",
    summary="평가 메트릭 정보",
    description="사용 가능한 평가 메트릭과 설명을 반환합니다."
)
async def get_metrics_info():
    """평가 메트릭 정보 조회"""
    return {
        "metrics": [
            {
                "type": RAGMetricType.FAITHFULNESS.value,
                "name": "Faithfulness (충실도)",
                "description": "응답이 컨텍스트에 기반하는지 평가 (환각 탐지)",
                "weight": 0.30,
                "method": "hybrid",
            },
            {
                "type": RAGMetricType.CONTEXT_RELEVANCE.value,
                "name": "Context Relevance (컨텍스트 관련성)",
                "description": "검색된 문맥이 질문과 관련성이 있는지 평가",
                "weight": 0.25,
                "method": "hybrid",
            },
            {
                "type": RAGMetricType.ANSWER_RELEVANCY.value,
                "name": "Answer Relevancy (응답 적합성)",
                "description": "응답이 질문에 적합하게 답변하는지 평가",
                "weight": 0.25,
                "method": "rule_based",
            },
            {
                "type": RAGMetricType.CONTEXT_PRECISION.value,
                "name": "Context Precision (컨텍스트 정밀도)",
                "description": "관련 컨텍스트가 상위에 잘 배치되어 있는지 평가",
                "weight": 0.10,
                "method": "rule_based",
            },
            {
                "type": RAGMetricType.CONTEXT_RECALL.value,
                "name": "Context Recall (컨텍스트 재현율)",
                "description": "정답에 필요한 정보가 컨텍스트에 포함되어 있는지 평가",
                "weight": 0.10,
                "method": "rule_based",
                "requires_ground_truth": True,
            },
        ],
        "levels": [
            {"level": "excellent", "threshold": 0.8, "description": "우수"},
            {"level": "good", "threshold": 0.6, "description": "양호"},
            {"level": "fair", "threshold": 0.4, "description": "보통"},
            {"level": "poor", "threshold": 0.0, "description": "미흡"},
        ],
    }
