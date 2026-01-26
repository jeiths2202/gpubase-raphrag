"""Crawl Job Repository Port - Interface for crawl job persistence"""
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from ...domain.entities import CrawlJob


class CrawlJobRepositoryPort(ABC):
    """Abstract interface for crawl job persistence"""

    @abstractmethod
    async def save(self, job: CrawlJob) -> None:
        """Save or update a crawl job"""
        pass

    @abstractmethod
    async def find_by_id(self, job_id: UUID) -> Optional[CrawlJob]:
        """Find a crawl job by ID"""
        pass

    @abstractmethod
    async def find_by_user_id(self, user_id: UUID, limit: int = 20) -> List[CrawlJob]:
        """Find crawl jobs for a user, ordered by created_at DESC"""
        pass

    @abstractmethod
    async def find_running_by_user_id(self, user_id: UUID) -> List[CrawlJob]:
        """Find all running (non-terminal) jobs for a user"""
        pass

    @abstractmethod
    async def find_by_query(
        self,
        user_id: UUID,
        query: str,
        max_age_hours: int = 24
    ) -> Optional[CrawlJob]:
        """
        Find a completed crawl job with the same query within the cache period.

        Args:
            user_id: User UUID
            query: Search query string (exact match)
            max_age_hours: Maximum age of cached results in hours

        Returns:
            Most recent completed CrawlJob if found within cache period, None otherwise
        """
        pass

    @abstractmethod
    async def delete(self, job_id: UUID) -> None:
        """Delete a crawl job"""
        pass

    @abstractmethod
    async def delete_expired_jobs(self, max_age_hours: int = 24) -> int:
        """
        Delete crawl jobs older than the specified age.

        Args:
            max_age_hours: Maximum age in hours before deletion

        Returns:
            Number of deleted jobs
        """
        pass
