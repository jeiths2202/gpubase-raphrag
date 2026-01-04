"""
Use case for getting dashboard statistics
"""
from uuid import UUID
from datetime import datetime

from app.api.ims_crawler.domain.ports.dashboard_repository import DashboardRepositoryPort
from app.api.ims_crawler.domain.models.dashboard import DashboardStatistics


class GetDashboardStatisticsUseCase:
    """Use case for retrieving dashboard statistics"""

    def __init__(self, dashboard_repository: DashboardRepositoryPort):
        self.dashboard_repository = dashboard_repository

    async def get_statistics(
        self,
        user_id: UUID,
        trend_days: int = 7
    ) -> DashboardStatistics:
        """
        Get comprehensive dashboard statistics for user

        Args:
            user_id: User ID
            trend_days: Number of days for trend analysis (7 or 30)

        Returns:
            Complete dashboard statistics
        """

        # Fetch all metrics in parallel
        activity_metrics = await self.dashboard_repository.get_activity_metrics(user_id)
        issue_metrics = await self.dashboard_repository.get_issue_metrics(user_id)
        by_status = await self.dashboard_repository.get_status_distribution(user_id)
        by_priority = await self.dashboard_repository.get_priority_distribution(user_id)
        top_projects = await self.dashboard_repository.get_top_projects(user_id, limit=10)
        top_reporters = await self.dashboard_repository.get_top_reporters(user_id, limit=10)
        issue_trend_7days = await self.dashboard_repository.get_issue_trend(user_id, days=7)
        issue_trend_30days = await self.dashboard_repository.get_issue_trend(user_id, days=30)
        status_trend = await self.dashboard_repository.get_status_trend(user_id, days=trend_days)

        return DashboardStatistics(
            user_id=user_id,
            generated_at=datetime.utcnow(),
            activity_metrics=activity_metrics,
            issue_metrics=issue_metrics,
            by_status=by_status,
            by_priority=by_priority,
            top_projects=top_projects,
            top_reporters=top_reporters,
            issue_trend_7days=issue_trend_7days,
            issue_trend_30days=issue_trend_30days,
            status_trend=status_trend
        )
