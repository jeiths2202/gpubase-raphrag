"""
Stats API Router
시스템 통계 API
"""
import uuid
from fastapi import APIRouter, Depends, Query

from ..models.base import SuccessResponse, MetaInfo
from ..models.stats import (
    SystemStats,
    QueryStatsDetail,
    DocumentStatsDetail,
)
from ..core.deps import get_current_user, get_stats_service

router = APIRouter(prefix="/stats", tags=["Statistics"])


@router.get(
    "",
    response_model=SuccessResponse[SystemStats],
    summary="시스템 전체 통계",
    description="데이터베이스, 임베딩, 질의, 저장소 등 시스템 전체 통계를 조회합니다."
)
async def get_system_stats(
    current_user: dict = Depends(get_current_user),
    stats_service = Depends(get_stats_service)
):
    """Get complete system statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await stats_service.get_system_stats()

    return SuccessResponse(
        data=SystemStats(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/queries",
    response_model=SuccessResponse[QueryStatsDetail],
    summary="질의 통계 상세",
    description="기간별 질의 통계를 상세 조회합니다."
)
async def get_query_stats(
    period: str = Query(default="7d", description="기간 (1d, 7d, 30d, 90d)"),
    granularity: str = Query(default="day", description="집계 단위 (hour, day, week)"),
    current_user: dict = Depends(get_current_user),
    stats_service = Depends(get_stats_service)
):
    """Get detailed query statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Validate period
    valid_periods = ["1d", "7d", "30d", "90d"]
    if period not in valid_periods:
        period = "7d"

    # Validate granularity
    valid_granularities = ["hour", "day", "week"]
    if granularity not in valid_granularities:
        granularity = "day"

    result = await stats_service.get_query_stats(period=period, granularity=granularity)

    return SuccessResponse(
        data=QueryStatsDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/documents",
    response_model=SuccessResponse[DocumentStatsDetail],
    summary="문서 통계",
    description="문서 관련 통계를 조회합니다."
)
async def get_document_stats(
    current_user: dict = Depends(get_current_user),
    stats_service = Depends(get_stats_service)
):
    """Get document statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await stats_service.get_document_stats()

    return SuccessResponse(
        data=DocumentStatsDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )
