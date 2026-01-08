"""
Crawler Port - Interface for IMS web scraping

Abstract interface that crawler adapters must implement.
"""

from abc import ABC, abstractmethod
from typing import List, AsyncGenerator, Optional
from uuid import UUID

from ...domain.entities import Issue, Attachment, UserCredentials


class CrawlerPort(ABC):
    """
    Abstract interface for IMS crawling operations.

    Implementations handle web scraping, authentication, and data extraction.
    """

    @abstractmethod
    async def authenticate(self, credentials: UserCredentials) -> bool:
        """
        Authenticate with IMS system using user credentials.

        Args:
            credentials: Encrypted user credentials

        Returns:
            True if authentication successful

        Raises:
            AuthenticationError: If authentication fails
        """
        pass

    @abstractmethod
    async def search_issues(
        self,
        query: str,
        credentials: UserCredentials,
        product_codes: Optional[List[str]] = None
    ) -> List[Issue]:
        """
        Search for issues matching the query.

        Args:
            query: IMS search syntax query
            credentials: User credentials for authentication
            product_codes: Optional list of product codes to filter (e.g., ['128', '520'])

        Returns:
            List of Issue entities

        Raises:
            CrawlerError: If search fails
        """
        pass

    @abstractmethod
    async def crawl_issue_details(
        self,
        issue_id: str,
        credentials: UserCredentials,
        fallback_issue: Issue = None
    ) -> Issue:
        """
        Crawl detailed information for a single issue.

        Args:
            issue_id: IMS issue identifier
            credentials: User credentials
            fallback_issue: Optional issue from search results to use as fallback

        Returns:
            Complete Issue entity with all details

        Raises:
            CrawlerError: If crawling fails
        """
        pass

    @abstractmethod
    async def download_attachments(
        self,
        issue: Issue,
        credentials: UserCredentials
    ) -> List[Attachment]:
        """
        Download and process attachments for an issue.

        Args:
            issue: Issue entity
            credentials: User credentials

        Returns:
            List of Attachment entities with extracted text

        Raises:
            CrawlerError: If download/processing fails
        """
        pass

    @abstractmethod
    async def crawl_related_issues(
        self,
        issue: Issue,
        credentials: UserCredentials,
        max_depth: int = 1
    ) -> List[Issue]:
        """
        Recursively crawl issues related to the given issue.

        Args:
            issue: Source issue
            credentials: User credentials
            max_depth: Maximum recursion depth

        Returns:
            List of related Issue entities

        Raises:
            CrawlerError: If crawling fails
        """
        pass

    @abstractmethod
    async def crawl_issues_parallel(
        self,
        issues: List[Issue],
        credentials: UserCredentials,
        batch_size: int = 10
    ) -> List[Issue]:
        """
        Crawl multiple issues in parallel using multiple browser pages.

        Args:
            issues: List of issues to crawl (from search results)
            credentials: User credentials
            batch_size: Number of concurrent pages to use (default: 10)

        Returns:
            List of crawled Issue entities sorted by ims_id descending
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up browser resources."""
        pass
