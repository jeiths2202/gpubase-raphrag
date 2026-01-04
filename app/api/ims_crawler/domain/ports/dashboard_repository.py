"""
Port for dashboard statistics repository
"""
from abc import ABC, abstractmethod
from typing import List, Dict
from datetime import datetime
from uuid import UUID

from app.api.ims_crawler.domain.models.dashboard import (
    ActivityMetrics,
    IssueMetrics,
    ProjectMetrics,
    TopReporter,
    TrendData
)


class DashboardRepositoryPort(ABC):
    """Interface for dashboard statistics data access"""

    @abstractmethod
    async def get_activity_metrics(self, user_id: UUID) -> ActivityMetrics:
        """Get user activity metrics"""
        pass

    @abstractmethod
    async def get_issue_metrics(self, user_id: UUID) -> IssueMetrics:
        """Get issue-related metrics"""
        pass

    @abstractmethod
    async def get_status_distribution(self, user_id: UUID) -> Dict[str, int]:
        """Get issue count by status"""
        pass

    @abstractmethod
    async def get_priority_distribution(self, user_id: UUID) -> Dict[str, int]:
        """Get issue count by priority"""
        pass

    @abstractmethod
    async def get_top_projects(self, user_id: UUID, limit: int = 10) -> List[ProjectMetrics]:
        """Get top projects by issue count"""
        pass

    @abstractmethod
    async def get_top_reporters(self, user_id: UUID, limit: int = 10) -> List[TopReporter]:
        """Get top issue reporters"""
        pass

    @abstractmethod
    async def get_issue_trend(
        self,
        user_id: UUID,
        days: int = 7
    ) -> List[TrendData]:
        """Get issue creation trend for last N days"""
        pass

    @abstractmethod
    async def get_status_trend(
        self,
        user_id: UUID,
        days: int = 7
    ) -> Dict[str, List[TrendData]]:
        """Get status change trends for last N days"""
        pass
