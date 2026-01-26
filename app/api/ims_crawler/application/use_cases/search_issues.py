"""Search Issues Use Case - Semantic, hybrid, and keyword-based search"""

from typing import List, Literal
from uuid import UUID

from ...domain.entities import Issue
from ...domain.value_objects import SearchIntent
from ...infrastructure.ports.nl_parser_port import NLParserPort
from ...infrastructure.ports.issue_repository_port import IssueRepositoryPort
from ...infrastructure.ports.embedding_service_port import EmbeddingServicePort


SearchStrategy = Literal['semantic', 'hybrid', 'recent']


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
        search_strategy: SearchStrategy = 'hybrid',
        use_semantic: bool = None  # Deprecated: use search_strategy instead
    ) -> tuple[SearchIntent, List[Issue]]:
        """
        Search issues using NL query with configurable strategy.

        Args:
            query: Natural language search query
            user_id: User identifier
            max_results: Maximum number of results to return
            search_strategy: Search strategy - 'semantic', 'hybrid', or 'recent'
            use_semantic: Deprecated parameter for backward compatibility

        Returns:
            Tuple of (parsed_intent, issues)
        """
        # Parse NL query
        intent = await self.parser.parse_query(query)

        # Backward compatibility: map use_semantic to search_strategy
        if use_semantic is not None:
            search_strategy = 'semantic' if use_semantic else 'recent'

        # Execute search based on strategy
        if search_strategy == 'hybrid' and intent.requires_semantic_search():
            # Hybrid search (BM25 30% + Semantic 70%)
            issues = await self.repository.search_hybrid(
                query_text=query,
                user_id=user_id,
                limit=max_results,
                candidate_limit=max_results * 5  # Retrieve 5x candidates for ranking
            )
        elif search_strategy == 'semantic' and intent.requires_semantic_search():
            # Pure semantic search
            embedding = await self.embedding.embed_text(query)
            issues = await self.repository.search_by_vector(embedding, user_id, max_results)
        else:
            # Fallback to recent issues
            issues = await self.repository.find_by_user_id(user_id, max_results)

        return intent, issues
