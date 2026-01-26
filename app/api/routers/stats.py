"""
Stats API Router
시스템 통계 API
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..models.base import SuccessResponse, MetaInfo
from ..models.stats import (
    SystemStats,
    QueryStatsDetail,
    DocumentStatsDetail,
)
from ..core.deps import get_current_user, get_stats_service, get_postgres_pool

router = APIRouter(prefix="/stats", tags=["Statistics"])


class HomeDashboardStats(BaseModel):
    """Home page dashboard statistics"""
    documents_indexed: int = 0
    queries_this_month: int = 0
    active_users: int = 0
    avg_response_time_ms: float = 0
    documents_trend: Optional[float] = None
    queries_trend: Optional[float] = None
    users_trend: Optional[float] = None
    response_trend: Optional[float] = None


@router.get(
    "/home-dashboard",
    response_model=SuccessResponse[HomeDashboardStats],
    summary="홈 대시보드 통계",
    description="홈페이지 대시보드에 표시할 기본 통계를 조회합니다."
)
async def get_home_dashboard_stats(
    current_user: dict = Depends(get_current_user),
    pool = Depends(get_postgres_pool)
):
    """Get statistics for home page dashboard"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        async with pool.acquire() as conn:
            # Current month start
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

            # Documents count
            docs_count = await conn.fetchval("SELECT COUNT(*) FROM documents") or 0

            # Queries this month from query_log
            queries_this_month = await conn.fetchval(
                "SELECT COUNT(*) FROM query_log WHERE created_at >= $1",
                month_start
            ) or 0

            # Queries last month for trend
            queries_last_month = await conn.fetchval(
                "SELECT COUNT(*) FROM query_log WHERE created_at >= $1 AND created_at < $2",
                prev_month_start, month_start
            ) or 0

            # Calculate queries trend
            queries_trend = None
            if queries_last_month > 0:
                queries_trend = ((queries_this_month - queries_last_month) / queries_last_month) * 100

            # Active users (users who made queries this month)
            active_users = await conn.fetchval(
                "SELECT COUNT(DISTINCT user_id) FROM query_log WHERE created_at >= $1",
                month_start
            ) or 0

            # Average response time this month
            avg_response = await conn.fetchval(
                "SELECT AVG(execution_time_ms) FROM query_log WHERE created_at >= $1",
                month_start
            ) or 0

            # Previous month average for trend
            prev_avg_response = await conn.fetchval(
                "SELECT AVG(execution_time_ms) FROM query_log WHERE created_at >= $1 AND created_at < $2",
                prev_month_start, month_start
            ) or 0

            # Calculate response trend (negative is better for response time)
            response_trend = None
            if prev_avg_response > 0:
                response_trend = ((avg_response - prev_avg_response) / prev_avg_response) * 100

            stats = HomeDashboardStats(
                documents_indexed=docs_count,
                queries_this_month=queries_this_month,
                active_users=active_users,
                avg_response_time_ms=round(avg_response, 2) if avg_response else 0,
                queries_trend=round(queries_trend, 1) if queries_trend is not None else None,
                response_trend=round(response_trend, 1) if response_trend is not None else None,
            )

            return SuccessResponse(
                data=stats,
                meta=MetaInfo(request_id=request_id)
            )

    except Exception as e:
        # Return empty stats on error
        return SuccessResponse(
            data=HomeDashboardStats(),
            meta=MetaInfo(request_id=request_id)
        )


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
