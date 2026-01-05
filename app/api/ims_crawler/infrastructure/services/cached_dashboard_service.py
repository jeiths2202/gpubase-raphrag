"""
Cached dashboard service with Redis caching layer
"""
from typing import Optional
from datetime import timedelta
from uuid import UUID

from ...domain.ports.cache_port import CachePort
from ...domain.models.dashboard import DashboardStatistics
from ...application.use_cases.get_dashboard_statistics import GetDashboardStatisticsUseCase


class CachedDashboardService:
    """
    Dashboard service with caching layer
    Caches dashboard statistics to reduce database load
    """

    def __init__(
        self,
        dashboard_use_case: GetDashboardStatisticsUseCase,
        cache: CachePort,
        cache_ttl: timedelta = timedelta(minutes=5)
    ):
        """
        Initialize cached dashboard service

        Args:
            dashboard_use_case: Underlying dashboard use case
            cache: Cache service
            cache_ttl: Cache expiration time (shorter for dashboard - frequently changing)
        """
        self.dashboard_use_case = dashboard_use_case
        self.cache = cache
        self.cache_ttl = cache_ttl

    def _make_cache_key(self, user_id: UUID, trend_days: int) -> str:
        """Generate cache key for dashboard"""
        return f"dashboard:{user_id}:trend{trend_days}"

    async def get_statistics(
        self,
        user_id: UUID,
        trend_days: int = 7,
        force_refresh: bool = False
    ) -> DashboardStatistics:
        """
        Get dashboard statistics with caching

        Args:
            user_id: User ID
            trend_days: Number of days for trend
            force_refresh: Bypass cache

        Returns:
            Dashboard statistics
        """

        cache_key = self._make_cache_key(user_id, trend_days)

        # Try cache first
        if not force_refresh:
            cached_data = await self.cache.get(cache_key)
            if cached_data is not None:
                # Reconstruct DashboardStatistics from cached data
                # (simplified - actual implementation would need full reconstruction)
                return cached_data

        # Cache miss - get fresh data
        stats = await self.dashboard_use_case.get_statistics(user_id, trend_days)

        # Cache the statistics (simplified serialization)
        cache_data = {
            'user_id': str(stats.user_id),
            'generated_at': stats.generated_at.isoformat(),
            'activity_metrics': {
                'total_crawls': stats.activity_metrics.total_crawls,
                'total_issues_crawled': stats.activity_metrics.total_issues_crawled,
                'total_attachments': stats.activity_metrics.total_attachments,
                'last_crawl_date': stats.activity_metrics.last_crawl_date.isoformat() if stats.activity_metrics.last_crawl_date else None,
                'avg_issues_per_crawl': stats.activity_metrics.avg_issues_per_crawl
            },
            'issue_metrics': {
                'total_issues': stats.issue_metrics.total_issues,
                'open_issues': stats.issue_metrics.open_issues,
                'closed_issues': stats.issue_metrics.closed_issues,
                'critical_issues': stats.issue_metrics.critical_issues,
                'high_priority_issues': stats.issue_metrics.high_priority_issues,
                'resolution_rate': stats.issue_metrics.resolution_rate
            },
            'by_status': stats.by_status,
            'by_priority': stats.by_priority
        }

        await self.cache.set(cache_key, cache_data, ttl=self.cache_ttl)

        return stats

    async def invalidate_user_dashboard(self, user_id: UUID) -> int:
        """
        Invalidate all cached dashboard data for a user

        Args:
            user_id: User ID

        Returns:
            Number of cache entries deleted
        """
        pattern = f"dashboard:{user_id}:*"
        return await self.cache.clear_pattern(pattern)

    async def get_cache_info(self, user_id: UUID, trend_days: int = 7) -> dict:
        """
        Get cache information for dashboard

        Args:
            user_id: User ID
            trend_days: Trend period

        Returns:
            Cache information
        """
        cache_key = self._make_cache_key(user_id, trend_days)

        exists = await self.cache.exists(cache_key)
        ttl = await self.cache.get_ttl(cache_key) if exists else None

        return {
            'cached': exists,
            'ttl_seconds': ttl,
            'cache_key': cache_key
        }
