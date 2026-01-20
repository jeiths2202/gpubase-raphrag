"""
Real-time Analytics Dashboard API Endpoints

Provides endpoints for:
- Query analytics (popular questions, trends, unanswered rate)
- Response quality metrics (Faithfulness, Relevancy averages)
- Usage patterns (hourly/daily usage, user analysis)
- Content effectiveness (document citations, usefulness)
- System performance (latency, throughput, error rate)
- Dashboard summary
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse

from app.api.core.deps import get_current_user, get_analytics_dashboard_service
from app.api.models.analytics_dashboard import (
    TimeGranularity,
    QueryAnalytics,
    ResponseQualityAnalytics,
    UsagePatternAnalytics,
    ContentEffectivenessAnalytics,
    SystemPerformanceAnalytics,
    DashboardSummary,
    AnalyticsRequest,
    AnalyticsExportRequest
)
from app.api.services.analytics_dashboard_service import AnalyticsDashboardService

router = APIRouter(prefix="/analytics", tags=["analytics-dashboard"])


# ============================================
# Dashboard Summary
# ============================================

@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="대시보드 요약 조회",
    description="전체 대시보드 요약 정보를 조회합니다"
)
async def get_dashboard_summary(
    start_date: Optional[datetime] = Query(None, description="시작 날짜"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get complete dashboard summary"""
    return await service.get_dashboard_summary(start_date, end_date)


# ============================================
# Query Analytics
# ============================================

@router.get(
    "/queries",
    response_model=QueryAnalytics,
    summary="쿼리 분석 조회",
    description="인기 질문, 검색 트렌드, 미답변 비율 등을 조회합니다"
)
async def get_query_analytics(
    start_date: Optional[datetime] = Query(None, description="시작 날짜"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜"),
    granularity: TimeGranularity = Query(TimeGranularity.DAILY, description="시간 단위"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    user_id: Optional[str] = Query(None, description="사용자 필터"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get query analytics with popular questions, trends, and unanswered rate"""
    return await service.get_query_analytics(
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        limit=limit,
        user_id=user_id
    )


@router.get(
    "/queries/popular",
    summary="인기 질문 조회",
    description="가장 많이 검색된 질문 목록을 조회합니다"
)
async def get_popular_queries(
    days: int = Query(7, ge=1, le=90, description="조회 기간 (일)"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get most popular queries"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    analytics = await service.get_query_analytics(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

    return {"popular_queries": analytics.popular_queries}


@router.get(
    "/queries/unanswered",
    summary="미답변 질문 조회",
    description="답변되지 않은 질문 목록을 조회합니다"
)
async def get_unanswered_queries(
    days: int = Query(7, ge=1, le=90, description="조회 기간 (일)"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get unanswered queries"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    analytics = await service.get_query_analytics(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

    return {
        "unanswered_count": analytics.unanswered_count,
        "unanswered_rate": analytics.unanswered_rate,
        "top_unanswered": analytics.top_unanswered
    }


# ============================================
# Response Quality Analytics
# ============================================

@router.get(
    "/quality",
    response_model=ResponseQualityAnalytics,
    summary="응답 품질 분석 조회",
    description="평균 Faithfulness, Relevancy 점수 등 품질 메트릭을 조회합니다"
)
async def get_quality_analytics(
    start_date: Optional[datetime] = Query(None, description="시작 날짜"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜"),
    include_trends: bool = Query(True, description="트렌드 포함 여부"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get response quality analytics"""
    return await service.get_quality_analytics(
        start_date=start_date,
        end_date=end_date,
        include_trends=include_trends
    )


@router.get(
    "/quality/distribution",
    summary="품질 분포 조회",
    description="응답 품질 등급별 분포를 조회합니다"
)
async def get_quality_distribution(
    days: int = Query(7, ge=1, le=90, description="조회 기간 (일)"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get quality score distribution"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    analytics = await service.get_quality_analytics(
        start_date=start_date,
        end_date=end_date,
        include_trends=False
    )

    dist = analytics.quality_distribution
    total = dist.total

    return {
        "distribution": {
            "excellent": {"count": dist.excellent_count, "percentage": dist.excellent_count / total * 100 if total > 0 else 0},
            "good": {"count": dist.good_count, "percentage": dist.good_count / total * 100 if total > 0 else 0},
            "fair": {"count": dist.fair_count, "percentage": dist.fair_count / total * 100 if total > 0 else 0},
            "poor": {"count": dist.poor_count, "percentage": dist.poor_count / total * 100 if total > 0 else 0}
        },
        "total": total
    }


# ============================================
# Usage Pattern Analytics
# ============================================

@router.get(
    "/usage",
    response_model=UsagePatternAnalytics,
    summary="사용 패턴 분석 조회",
    description="시간대별 사용량, 사용자별 분석을 조회합니다"
)
async def get_usage_analytics(
    start_date: Optional[datetime] = Query(None, description="시작 날짜"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get usage pattern analytics"""
    return await service.get_usage_analytics(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


@router.get(
    "/usage/hourly",
    summary="시간대별 사용량 조회",
    description="24시간 기준 시간대별 사용량을 조회합니다"
)
async def get_hourly_usage(
    days: int = Query(7, ge=1, le=30, description="조회 기간 (일)"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get hourly usage pattern"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    analytics = await service.get_usage_analytics(
        start_date=start_date,
        end_date=end_date
    )

    return {
        "hourly_usage": analytics.hourly_usage,
        "peak_hours": analytics.peak_hours
    }


@router.get(
    "/usage/users",
    summary="사용자별 분석 조회",
    description="상위 활동 사용자 목록을 조회합니다"
)
async def get_user_analytics(
    days: int = Query(7, ge=1, le=90, description="조회 기간 (일)"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get user activity analytics"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    analytics = await service.get_usage_analytics(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

    return {
        "total_users": analytics.total_users,
        "avg_queries_per_user": analytics.avg_queries_per_user,
        "top_users": analytics.top_users
    }


# ============================================
# Content Effectiveness Analytics
# ============================================

@router.get(
    "/content",
    response_model=ContentEffectivenessAnalytics,
    summary="콘텐츠 효과 분석 조회",
    description="문서별 인용 빈도, 유용성 점수를 조회합니다"
)
async def get_content_analytics(
    start_date: Optional[datetime] = Query(None, description="시작 날짜"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get content effectiveness analytics"""
    return await service.get_content_analytics(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


@router.get(
    "/content/top-cited",
    summary="인용 빈도 상위 문서 조회",
    description="가장 많이 인용된 문서 목록을 조회합니다"
)
async def get_top_cited_documents(
    days: int = Query(30, ge=1, le=90, description="조회 기간 (일)"),
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get top cited documents"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    analytics = await service.get_content_analytics(
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )

    return {"top_cited_documents": analytics.top_cited_documents}


@router.get(
    "/content/gaps",
    summary="콘텐츠 갭 조회",
    description="식별된 콘텐츠 갭 목록을 조회합니다"
)
async def get_content_gaps(
    limit: int = Query(10, ge=1, le=50, description="결과 수"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get identified content gaps"""
    analytics = await service.get_content_analytics(limit=limit)

    return {"content_gaps": analytics.content_gaps}


# ============================================
# System Performance Analytics
# ============================================

@router.get(
    "/performance",
    response_model=SystemPerformanceAnalytics,
    summary="시스템 성능 분석 조회",
    description="응답 지연시간, 처리량, 에러율을 조회합니다"
)
async def get_performance_analytics(
    start_date: Optional[datetime] = Query(None, description="시작 날짜"),
    end_date: Optional[datetime] = Query(None, description="종료 날짜"),
    include_trends: bool = Query(True, description="트렌드 포함 여부"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get system performance analytics"""
    return await service.get_performance_analytics(
        start_date=start_date,
        end_date=end_date,
        include_trends=include_trends
    )


@router.get(
    "/performance/latency",
    summary="응답 지연시간 조회",
    description="응답 지연시간 메트릭 (평균, p50, p90, p95, p99)을 조회합니다"
)
async def get_latency_metrics(
    hours: int = Query(24, ge=1, le=168, description="조회 기간 (시간)"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get latency metrics"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=hours)

    analytics = await service.get_performance_analytics(
        start_date=start_date,
        end_date=end_date,
        include_trends=False
    )

    return {"latency": analytics.latency}


@router.get(
    "/performance/errors",
    summary="에러 현황 조회",
    description="에러율, 에러 타입별/엔드포인트별 분포를 조회합니다"
)
async def get_error_metrics(
    hours: int = Query(24, ge=1, le=168, description="조회 기간 (시간)"),
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get error metrics"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=hours)

    analytics = await service.get_performance_analytics(
        start_date=start_date,
        end_date=end_date,
        include_trends=False
    )

    return {"errors": analytics.errors}


@router.get(
    "/performance/health",
    summary="컴포넌트 상태 조회",
    description="시스템 컴포넌트별 상태를 조회합니다"
)
async def get_component_health(
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Get component health status"""
    analytics = await service.get_performance_analytics(include_trends=False)

    return {"component_health": analytics.component_health}


# ============================================
# Aggregation Endpoints (Admin)
# ============================================

@router.post(
    "/aggregate/hourly",
    summary="시간별 집계 실행",
    description="이전 시간의 분석 데이터를 집계합니다 (관리자 전용)"
)
async def run_hourly_aggregation(
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Run hourly analytics aggregation"""
    # Check admin role
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    await service.aggregate_hourly_stats()
    return {"status": "success", "message": "Hourly aggregation completed"}


@router.post(
    "/aggregate/daily",
    summary="일별 집계 실행",
    description="이전 일의 분석 데이터를 집계합니다 (관리자 전용)"
)
async def run_daily_aggregation(
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Run daily analytics aggregation"""
    # Check admin role
    if not hasattr(current_user, 'role') or current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    await service.aggregate_daily_stats()
    return {"status": "success", "message": "Daily aggregation completed"}


# ============================================
# Export
# ============================================

@router.post(
    "/export",
    summary="분석 데이터 내보내기",
    description="지정된 기간의 분석 데이터를 내보냅니다"
)
async def export_analytics(
    request: AnalyticsExportRequest,
    service: AnalyticsDashboardService = Depends(get_analytics_dashboard_service),
    current_user=Depends(get_current_user)
):
    """Export analytics data"""
    # Get the requested analytics type
    data = None

    if request.analytics_type == "query":
        data = await service.get_query_analytics(
            start_date=request.start_date,
            end_date=request.end_date
        )
    elif request.analytics_type == "quality":
        data = await service.get_quality_analytics(
            start_date=request.start_date,
            end_date=request.end_date
        )
    elif request.analytics_type == "usage":
        data = await service.get_usage_analytics(
            start_date=request.start_date,
            end_date=request.end_date
        )
    elif request.analytics_type == "content":
        data = await service.get_content_analytics(
            start_date=request.start_date,
            end_date=request.end_date
        )
    elif request.analytics_type == "performance":
        data = await service.get_performance_analytics(
            start_date=request.start_date,
            end_date=request.end_date
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid analytics_type: {request.analytics_type}"
        )

    if data is None:
        raise HTTPException(status_code=500, detail="Failed to fetch analytics data")

    # Convert to dict for export
    export_data = data.model_dump() if hasattr(data, 'model_dump') else data

    if request.format == "csv":
        # For CSV, we'd need to flatten the data - return as JSON for now
        return JSONResponse(
            content={"error": "CSV export not yet implemented", "data": export_data}
        )

    return export_data
