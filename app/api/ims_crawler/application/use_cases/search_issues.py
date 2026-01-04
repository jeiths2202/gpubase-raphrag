"""Search Issues Use Case - Semantic and keyword-based search"""

from typing import List
from uuid import UUID

from ...domain.entities import Issue
from ...domain.value_objects import SearchIntent
from ...infrastructure.ports.nl_parser_port import NLParserPort
from ...infrastructure.ports.issue_repository_port import IssueRepositoryPort
from ...infrastructure.ports.embedding_service_port import EmbeddingServicePort


class SearchIssuesUseCase:
    """Orchestrates NL parsing, embedding, and search"""

    def __init__(
        self,
        nl_parser: NLParserPort,
        issue_repository: IssueRepositoryPort,
        embedding_service: EmbeddingServicePort
    ):
        self.parser = nl_parser
        self.repository = issue_repository
        self.embedding = embedding_service

    async def search(
        self,
        query: str,
        user_id: UUID,
        max_results: int = 50,
        use_semantic: bool = True
    ) -> tuple[SearchIntent, List[Issue]]:
        """
        Search issues using NL query.

        Returns:
            Tuple of (parsed_intent, issues)
        """
        # Parse NL query
        intent = await self.parser.parse_query(query)

        # Semantic search if enabled
        if use_semantic and intent.requires_semantic_search():
            embedding = await self.embedding.embed_text(query)
            issues = await self.repository.search_by_vector(embedding, user_id, max_results)
        else:
            # Fallback to recent issues (TODO: implement keyword search)
            issues = await self.repository.find_by_user_id(user_id, max_results)

        return intent, issues
