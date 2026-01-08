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
    async def delete(self, job_id: UUID) -> None:
        """Delete a crawl job"""
        pass
