"""
Cached search service with Redis caching layer
"""
from typing import List, Tuple
from datetime import timedelta
from uuid import UUID
import hashlib
import json

from app.api.ims_crawler.domain.ports.cache_port import CachePort
from app.api.ims_crawler.domain.entities.issue import Issue
from app.api.ims_crawler.domain.value_objects.search_intent import SearchIntent
from app.api.ims_crawler.application.use_cases.search_issues import SearchIssuesUseCase


class CachedSearchService:
    """
    Search service with caching layer
    Caches search results to improve performance
    """

    def __init__(
        self,
        search_use_case: SearchIssuesUseCase,
        cache: CachePort,
        cache_ttl: timedelta = timedelta(minutes=15)
    ):
        """
        Initialize cached search service

        Args:
            search_use_case: Underlying search use case
            cache: Cache service
            cache_ttl: Cache expiration time
        """
        self.search_use_case = search_use_case
        self.cache = cache
        self.cache_ttl = cache_ttl

    def _make_cache_key(
        self,
        user_id: UUID,
        query: str,
        max_results: int,
        use_semantic: bool
    ) -> str:
        """Generate cache key for search query"""
        # Create deterministic hash of search parameters
        params = {
            'user_id': str(user_id),
            'query': query,
            'max_results': max_results,
            'use_semantic': use_semantic
        }
        params_str = json.dumps(params, sort_keys=True)
        query_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]

        return f"search:{user_id}:{query_hash}"

    async def search(
        self,
        query: str,
        user_id: UUID,
        max_results: int = 50,
        use_semantic: bool = True,
        force_refresh: bool = False
    ) -> Tuple[SearchIntent, List[Issue]]:
        """
        Search with caching

        Args:
            query: Search query
            user_id: User ID
            max_results: Maximum results
            use_semantic: Use semantic search
            force_refresh: Bypass cache and force fresh search

        Returns:
            Tuple of (SearchIntent, List[Issue])
        """

        cache_key = self._make_cache_key(user_id, query, max_results, use_semantic)

        # Try cache first (unless force refresh)
        if not force_refresh:
            cached_result = await self.cache.get(cache_key)
            if cached_result is not None:
                # Cache hit
                intent_data = cached_result['intent']
                issues_data = cached_result['issues']

                # Reconstruct objects
                intent = SearchIntent(**intent_data)
                issues = [Issue(**issue_data) for issue_data in issues_data]

                return intent, issues

        # Cache miss - perform actual search
        intent, issues = await self.search_use_case.search(
            query=query,
            user_id=user_id,
            max_results=max_results,
            use_semantic=use_semantic
        )

        # Cache the results
        cache_data = {
            'intent': {
                'original_query': intent.original_query,
                'search_terms': intent.search_terms,
                'priority_filter': intent.priority_filter,
                'status_filter': intent.status_filter,
                'project_filter': intent.project_filter,
                'reporter_filter': intent.reporter_filter,
                'date_range_start': intent.date_range_start.isoformat() if intent.date_range_start else None,
                'date_range_end': intent.date_range_end.isoformat() if intent.date_range_end else None,
                'use_semantic': intent.use_semantic
            },
            'issues': [
                {
                    'id': str(issue.id),
                    'user_id': str(issue.user_id),
                    'ims_id': issue.ims_id,
                    'title': issue.title,
                    'description': issue.description,
                    'status': issue.status,
                    'priority': issue.priority,
                    'reporter': issue.reporter,
                    'assignee': issue.assignee,
                    'project_key': issue.project_key,
                    'labels': issue.labels,
                    'created_at': issue.created_at.isoformat(),
                    'updated_at': issue.updated_at.isoformat(),
                    'resolved_at': issue.resolved_at.isoformat() if issue.resolved_at else None,
                    'attachments': issue.attachments
                }
                for issue in issues
            ]
        }

        await self.cache.set(cache_key, cache_data, ttl=self.cache_ttl)

        return intent, issues

    async def invalidate_user_cache(self, user_id: UUID) -> int:
        """
        Invalidate all cached searches for a user

        Args:
            user_id: User ID

        Returns:
            Number of cache entries deleted
        """
        pattern = f"search:{user_id}:*"
        return await self.cache.clear_pattern(pattern)

    async def get_cache_stats(self, user_id: UUID, query: str) -> dict:
        """
        Get cache statistics for a query

        Args:
            user_id: User ID
            query: Search query

        Returns:
            Cache statistics
        """
        cache_key = self._make_cache_key(user_id, query, 50, True)

        exists = await self.cache.exists(cache_key)
        ttl = await self.cache.get_ttl(cache_key) if exists else None

        return {
            'cached': exists,
            'ttl_seconds': ttl,
            'cache_key': cache_key
        }
