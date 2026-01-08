"""
PostgreSQL Crawl Job Repository - Store and retrieve crawl jobs

Implements crawl job persistence for progress tracking and history.
"""

import asyncpg
from typing import List, Optional
from uuid import UUID

from ...domain.entities import CrawlJob, CrawlJobStatus
from ..ports.crawl_job_repository_port import CrawlJobRepositoryPort


class PostgreSQLCrawlJobRepository(CrawlJobRepositoryPort):
    """
    PostgreSQL implementation of crawl job repository.

    Persists crawl jobs for history and recovery.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize repository with connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def save(self, job: CrawlJob) -> None:
        """
        Save or update a crawl job.

        Uses UPSERT for idempotent saves.
        """
        query = """
            INSERT INTO ims_crawl_jobs (
                id, user_id, raw_query, parsed_query, search_intent,
                status, current_step, progress_percentage,
                issues_found, issues_crawled, attachments_processed, related_issues_crawled,
                created_at, started_at, completed_at,
                error_message, retry_count, max_retries,
                include_attachments, include_related_issues, max_issues,
                result_issue_ids
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
            ON CONFLICT (id)
            DO UPDATE SET
                status = EXCLUDED.status,
                current_step = EXCLUDED.current_step,
                progress_percentage = EXCLUDED.progress_percentage,
                issues_found = EXCLUDED.issues_found,
                issues_crawled = EXCLUDED.issues_crawled,
                attachments_processed = EXCLUDED.attachments_processed,
                related_issues_crawled = EXCLUDED.related_issues_crawled,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                error_message = EXCLUDED.error_message,
                retry_count = EXCLUDED.retry_count,
                result_issue_ids = EXCLUDED.result_issue_ids
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                job.id,
                job.user_id,
                job.raw_query,
                job.parsed_query,
                job.search_intent,
                job.status.value,
                job.current_step,
                job.progress_percentage,
                job.issues_found,
                job.issues_crawled,
                job.attachments_processed,
                job.related_issues_crawled,
                job.created_at,
                job.started_at,
                job.completed_at,
                job.error_message,
                job.retry_count,
                job.max_retries,
                job.include_attachments,
                job.include_related_issues,
                job.max_issues,
                job.result_issue_ids
            )

    async def find_by_id(self, job_id: UUID) -> Optional[CrawlJob]:
        """Find a crawl job by ID"""
        query = """
            SELECT * FROM ims_crawl_jobs WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, job_id)
            return self._row_to_job(row) if row else None

    async def find_by_user_id(self, user_id: UUID, limit: int = 20) -> List[CrawlJob]:
        """
        Find crawl jobs for a user.

        Args:
            user_id: User UUID
            limit: Max results

        Returns:
            List of jobs sorted by created_at DESC
        """
        query = """
            SELECT * FROM ims_crawl_jobs
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, limit)
            return [self._row_to_job(row) for row in rows]

    async def find_running_by_user_id(self, user_id: UUID) -> List[CrawlJob]:
        """
        Find all running (non-terminal) jobs for a user.

        Args:
            user_id: User UUID

        Returns:
            List of running jobs
        """
        query = """
            SELECT * FROM ims_crawl_jobs
            WHERE user_id = $1
            AND status NOT IN ('completed', 'failed', 'cancelled')
            ORDER BY created_at DESC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
            return [self._row_to_job(row) for row in rows]

    async def delete(self, job_id: UUID) -> None:
        """Delete a crawl job"""
        query = """
            DELETE FROM ims_crawl_jobs WHERE id = $1
        """

        async with self.pool.acquire() as conn:
            await conn.execute(query, job_id)

    def _row_to_job(self, row: asyncpg.Record) -> CrawlJob:
        """Convert database row to CrawlJob entity"""
        return CrawlJob(
            id=row['id'],
            user_id=row['user_id'],
            raw_query=row['raw_query'],
            parsed_query=row['parsed_query'],
            search_intent=row['search_intent'],
            status=CrawlJobStatus(row['status']),
            current_step=row['current_step'] or "Initializing...",
            progress_percentage=row['progress_percentage'] or 0,
            issues_found=row['issues_found'] or 0,
            issues_crawled=row['issues_crawled'] or 0,
            attachments_processed=row['attachments_processed'] or 0,
            related_issues_crawled=row['related_issues_crawled'] or 0,
            created_at=row['created_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            error_message=row['error_message'],
            retry_count=row['retry_count'] or 0,
            max_retries=row['max_retries'] or 3,
            include_attachments=row['include_attachments'] if row['include_attachments'] is not None else True,
            include_related_issues=row['include_related_issues'] if row['include_related_issues'] is not None else True,
            max_issues=row['max_issues'] or 100,
            result_issue_ids=list(row['result_issue_ids']) if row['result_issue_ids'] else []
        )
