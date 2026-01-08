"""Issue Repository Port"""
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID
from ...domain.entities import Issue


class IssueRepositoryPort(ABC):
    @abstractmethod
    async def save(self, issue: Issue) -> UUID:
        """Save issue and return the actual stored ID (may differ on UPSERT conflict)"""
        pass

    @abstractmethod
    async def save_embedding(self, issue_id: UUID, embedding: List[float], embedded_text: str) -> None:
        """Save vector embedding for issue"""
        pass

    @abstractmethod
    async def save_relation(
        self,
        source_issue_id: UUID,
        target_issue_id: UUID,
        relation_type: str
    ) -> None:
        """
        Save a relationship between two issues.

        Args:
            source_issue_id: Source issue UUID
            target_issue_id: Target issue UUID
            relation_type: Type of relation ('relates_to', 'blocks', 'duplicates')
        """
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

    @abstractmethod
    async def search_hybrid(self, query_text: str, user_id: UUID, limit: int = 20, candidate_limit: int = 100) -> List[Issue]:
        """Hybrid search using BM25 + Semantic scoring"""
        pass

    @abstractmethod
    async def get_embedded_ims_ids(self, user_id: UUID, ims_ids: List[str]) -> set[str]:
        """
        Get set of ims_ids that already have embeddings stored.

        Args:
            user_id: User UUID
            ims_ids: List of ims_ids to check

        Returns:
            Set of ims_ids that have embeddings
        """
        pass
