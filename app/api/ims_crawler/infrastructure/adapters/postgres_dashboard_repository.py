"""
PostgreSQL implementation of dashboard repository
"""
from typing import List, Dict
from datetime import datetime, timedelta
from uuid import UUID
import asyncpg

from app.api.ims_crawler.domain.ports.dashboard_repository import DashboardRepositoryPort
from app.api.ims_crawler.domain.models.dashboard import (
    ActivityMetrics,
    IssueMetrics,
    ProjectMetrics,
    TopReporter,
    TrendData
)


class PostgreSQLDashboardRepository(DashboardRepositoryPort):
    """PostgreSQL implementation of dashboard statistics repository"""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_activity_metrics(self, user_id: UUID) -> ActivityMetrics:
        """Get user activity metrics from crawl jobs"""
        query = """
            SELECT
                COUNT(*) as total_crawls,
                COALESCE(SUM(crawled_issues), 0) as total_issues_crawled,
                COALESCE(SUM(attachments_processed), 0) as total_attachments,
                MAX(completed_at) as last_crawl_date
            FROM ims_crawl_jobs
            WHERE user_id = $1 AND status = 'completed'
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)

            total_crawls = row['total_crawls'] or 0
            total_issues = row['total_issues_crawled'] or 0
            avg_issues = total_issues / total_crawls if total_crawls > 0 else 0.0

            return ActivityMetrics(
                total_crawls=total_crawls,
                total_issues_crawled=total_issues,
                total_attachments=row['total_attachments'] or 0,
                last_crawl_date=row['last_crawl_date'],
                avg_issues_per_crawl=round(avg_issues, 2)
            )

    async def get_issue_metrics(self, user_id: UUID) -> IssueMetrics:
        """Get issue-related metrics"""
        query = """
            SELECT
                COUNT(*) as total_issues,
                COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS', 'PENDING')) as open_issues,
                COUNT(*) FILTER (WHERE status IN ('CLOSED', 'RESOLVED', 'DONE')) as closed_issues,
                COUNT(*) FILTER (WHERE priority = 'CRITICAL') as critical_issues,
                COUNT(*) FILTER (WHERE priority = 'HIGH') as high_priority_issues
            FROM ims_issues
            WHERE user_id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)

            total = row['total_issues'] or 0
            closed = row['closed_issues'] or 0
            resolution_rate = (closed / total * 100) if total > 0 else 0.0

            return IssueMetrics(
                total_issues=total,
                open_issues=row['open_issues'] or 0,
                closed_issues=closed,
                critical_issues=row['critical_issues'] or 0,
                high_priority_issues=row['high_priority_issues'] or 0,
                resolution_rate=round(resolution_rate, 2)
            )

    async def get_status_distribution(self, user_id: UUID) -> Dict[str, int]:
        """Get issue count by status"""
        query = """
            SELECT status, COUNT(*) as count
            FROM ims_issues
            WHERE user_id = $1
            GROUP BY status
            ORDER BY count DESC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            return {row['status']: row['count'] for row in rows}

    async def get_priority_distribution(self, user_id: UUID) -> Dict[str, int]:
        """Get issue count by priority"""
        query = """
            SELECT priority, COUNT(*) as count
            FROM ims_issues
            WHERE user_id = $1
            GROUP BY priority
            ORDER BY
                CASE priority
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3
                    WHEN 'LOW' THEN 4
                    ELSE 5
                END
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            return {row['priority']: row['count'] for row in rows}

    async def get_top_projects(self, user_id: UUID, limit: int = 10) -> List[ProjectMetrics]:
        """Get top projects by issue count"""
        query = """
            SELECT
                SPLIT_PART(ims_id, '-', 1) as project_key,
                COUNT(*) as total_issues,
                COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS', 'PENDING')) as open_issues,
                COUNT(*) FILTER (WHERE status IN ('CLOSED', 'RESOLVED', 'DONE')) as closed_issues,
                COUNT(*) FILTER (WHERE priority = 'CRITICAL') as critical_issues,
                MAX(updated_at) as last_updated
            FROM ims_issues
            WHERE user_id = $1
            GROUP BY SPLIT_PART(ims_id, '-', 1)
            ORDER BY total_issues DESC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit)

            return [
                ProjectMetrics(
                    project_key=row['project_key'],
                    total_issues=row['total_issues'],
                    open_issues=row['open_issues'],
                    closed_issues=row['closed_issues'],
                    critical_issues=row['critical_issues'],
                    last_updated=row['last_updated']
                )
                for row in rows
            ]

    async def get_top_reporters(self, user_id: UUID, limit: int = 10) -> List[TopReporter]:
        """Get top issue reporters"""
        query = """
            SELECT
                reporter,
                COUNT(*) as issue_count,
                COUNT(*) FILTER (WHERE priority = 'CRITICAL') as critical_count,
                COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS', 'PENDING')) as open_count
            FROM ims_issues
            WHERE user_id = $1
            GROUP BY reporter
            ORDER BY issue_count DESC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit)

            return [
                TopReporter(
                    reporter=row['reporter'],
                    issue_count=row['issue_count'],
                    critical_count=row['critical_count'],
                    open_count=row['open_count']
                )
                for row in rows
            ]

    async def get_issue_trend(
        self,
        user_id: UUID,
        days: int = 7
    ) -> List[TrendData]:
        """Get issue creation trend for last N days"""
        query = """
            WITH date_series AS (
                SELECT generate_series(
                    CURRENT_DATE - $2::integer,
                    CURRENT_DATE,
                    '1 day'::interval
                )::date as date
            )
            SELECT
                ds.date,
                COUNT(i.id) as count
            FROM date_series ds
            LEFT JOIN ims_issues i ON DATE(i.created_at) = ds.date AND i.user_id = $1
            GROUP BY ds.date
            ORDER BY ds.date
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, days)

            return [
                TrendData(
                    date=row['date'],
                    count=row['count']
                )
                for row in rows
            ]

    async def get_status_trend(
        self,
        user_id: UUID,
        days: int = 7
    ) -> Dict[str, List[TrendData]]:
        """Get status change trends for last N days"""
        query = """
            WITH date_series AS (
                SELECT generate_series(
                    CURRENT_DATE - $2::integer,
                    CURRENT_DATE,
                    '1 day'::interval
                )::date as date
            )
            SELECT
                ds.date,
                i.status,
                COUNT(i.id) as count
            FROM date_series ds
            LEFT JOIN ims_issues i ON DATE(i.updated_at) = ds.date AND i.user_id = $1
            GROUP BY ds.date, i.status
            ORDER BY ds.date, i.status
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, days)

            # Group by status
            trends_by_status: Dict[str, List[TrendData]] = {}

            for row in rows:
                if row['status']:
                    status = row['status']
                    if status not in trends_by_status:
                        trends_by_status[status] = []

                    trends_by_status[status].append(
                        TrendData(
                            date=row['date'],
                            count=row['count']
                        )
                    )

            return trends_by_status
