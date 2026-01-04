"""Issue Repository Port"""
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from ...domain.entities import Issue

class IssueRepositoryPort(ABC):
    @abstractmethod
    async def save(self, issue: Issue) -> None:
        pass

    @abstractmethod
    async def find_by_id(self, issue_id: UUID) -> Optional[Issue]:
        pass

    @abstractmethod
    async def find_by_user_id(self, user_id: UUID, limit: int = 100) -> List[Issue]:
        pass

    @abstractmethod
    async def search_by_vector(self, embedding: List[float], user_id: UUID, limit: int = 20) -> List[Issue]:
        pass
