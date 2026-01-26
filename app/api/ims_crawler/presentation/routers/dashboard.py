"""
API router for IMS dashboard statistics
"""
from typing import List, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime

from app.api.core.deps import get_current_user
from app.api.ims_crawler.infrastructure.dependencies import get_dashboard_statistics_use_case


router = APIRouter(prefix="/ims-dashboard", tags=["IMS Dashboard"])


class ActivityMetricsResponse(BaseModel):
    """Activity metrics response"""
    total_crawls: int
    total_issues_crawled: int
    total_attachments: int
    last_crawl_date: datetime | None
    avg_issues_per_crawl: float


class IssueMetricsResponse(BaseModel):
    """Issue metrics response"""
    total_issues: int
    open_issues: int
    closed_issues: int
    critical_issues: int
    high_priority_issues: int
    resolution_rate: float


class ProjectMetricsResponse(BaseModel):
    """Project metrics response"""
    project_key: str
    total_issues: int
    open_issues: int
    closed_issues: int
    critical_issues: int
    last_updated: datetime


class TopReporterResponse(BaseModel):
    """Top reporter response"""
    reporter: str
    issue_count: int
    critical_count: int
    open_count: int


class TrendDataResponse(BaseModel):
    """Trend data response"""
    date: datetime
    count: int


class DashboardStatisticsResponse(BaseModel):
    """Complete dashboard statistics response"""
    user_id: str
    generated_at: datetime
    activity_metrics: ActivityMetricsResponse
    issue_metrics: IssueMetricsResponse
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    top_projects: List[ProjectMetricsResponse]
    top_reporters: List[TopReporterResponse]
    issue_trend_7days: List[TrendDataResponse]
    issue_trend_30days: List[TrendDataResponse]
    status_trend: Dict[str, List[TrendDataResponse]]


@router.get("/statistics", response_model=DashboardStatisticsResponse)
async def get_dashboard_statistics(
    trend_days: int = 7,
    current_user: dict = Depends(get_current_user),
    use_case = Depends(get_dashboard_statistics_use_case)
):
    """
    Get comprehensive dashboard statistics

    - **trend_days**: Number of days for trend analysis (7 or 30)

    Returns complete dashboard with:
    - Activity metrics (crawls, issues, attachments)
    - Issue metrics (totals, open/closed, priorities)
    - Distribution by status and priority
    - Top 10 projects and reporters
    - Issue creation trends (7 and 30 days)
    - Status change trends
    """

    user_id = UUID(current_user["id"])

    try:
        stats = await use_case.get_statistics(user_id, trend_days=trend_days)

        return DashboardStatisticsResponse(
            user_id=str(stats.user_id),
            generated_at=stats.generated_at,
            activity_metrics=ActivityMetricsResponse(
                total_crawls=stats.activity_metrics.total_crawls,
                total_issues_crawled=stats.activity_metrics.total_issues_crawled,
                total_attachments=stats.activity_metrics.total_attachments,
                last_crawl_date=stats.activity_metrics.last_crawl_date,
                avg_issues_per_crawl=stats.activity_metrics.avg_issues_per_crawl
            ),
            issue_metrics=IssueMetricsResponse(
                total_issues=stats.issue_metrics.total_issues,
                open_issues=stats.issue_metrics.open_issues,
                closed_issues=stats.issue_metrics.closed_issues,
                critical_issues=stats.issue_metrics.critical_issues,
                high_priority_issues=stats.issue_metrics.high_priority_issues,
                resolution_rate=stats.issue_metrics.resolution_rate
            ),
            by_status=stats.by_status,
            by_priority=stats.by_priority,
            top_projects=[
                ProjectMetricsResponse(
                    project_key=p.project_key,
                    total_issues=p.total_issues,
                    open_issues=p.open_issues,
                    closed_issues=p.closed_issues,
                    critical_issues=p.critical_issues,
                    last_updated=p.last_updated
                )
                for p in stats.top_projects
            ],
            top_reporters=[
                TopReporterResponse(
                    reporter=r.reporter,
                    issue_count=r.issue_count,
                    critical_count=r.critical_count,
                    open_count=r.open_count
                )
                for r in stats.top_reporters
            ],
            issue_trend_7days=[
                TrendDataResponse(date=t.date, count=t.count)
                for t in stats.issue_trend_7days
            ],
            issue_trend_30days=[
                TrendDataResponse(date=t.date, count=t.count)
                for t in stats.issue_trend_30days
            ],
            status_trend={
                status: [TrendDataResponse(date=t.date, count=t.count) for t in trends]
                for status, trends in stats.status_trend.items()
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard statistics: {str(e)}")


@router.get("/quick-stats")
async def get_quick_stats(
    current_user: dict = Depends(get_current_user),
    use_case = Depends(get_dashboard_statistics_use_case)
):
    """
    Get quick statistics summary for header/widgets

    Returns minimal statistics for quick display
    """

    user_id = UUID(current_user["id"])

    try:
        stats = await use_case.get_statistics(user_id, trend_days=7)

        return {
            "total_issues": stats.issue_metrics.total_issues,
            "open_issues": stats.issue_metrics.open_issues,
            "critical_issues": stats.issue_metrics.critical_issues,
            "total_crawls": stats.activity_metrics.total_crawls,
            "resolution_rate": stats.issue_metrics.resolution_rate
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quick stats: {str(e)}")
