"""
Base Connector Interface
Abstract base class for all external resource connectors.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, AsyncGenerator
from enum import Enum


class ConnectorStatus(str, Enum):
    """Connector operation status"""
    SUCCESS = "success"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    AUTH_EXPIRED = "auth_expired"
    NOT_FOUND = "not_found"


@dataclass
class ConnectorDocument:
    """
    Normalized document from external source.
    All connectors return documents in this format.
    """
    external_id: str
    title: str
    content: str
    external_url: Optional[str] = None
    path: Optional[str] = None
    mime_type: Optional[str] = None
    modified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Structured content
    sections: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For change detection
    content_hash: Optional[str] = None
    etag: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "external_id": self.external_id,
            "title": self.title,
            "content": self.content,
            "external_url": self.external_url,
            "path": self.path,
            "mime_type": self.mime_type,
            "modified_at": self.modified_at.isoformat() if self.modified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sections": self.sections,
            "metadata": self.metadata,
            "content_hash": self.content_hash
        }


@dataclass
class ConnectorResult:
    """Result of a connector operation"""
    status: ConnectorStatus
    data: Any = None
    message: str = ""
    error: Optional[str] = None


class BaseConnector(ABC):
    """
    Abstract base class for external resource connectors.

    Each connector is responsible for:
    1. OAuth/API authentication
    2. Document listing
    3. Document content fetching
    4. Incremental sync support
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_token: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.api_token = api_token
        self.config = config or {}

    @property
    @abstractmethod
    def resource_type(self) -> str:
        """Return the resource type identifier"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name"""
        pass

    @property
    @abstractmethod
    def oauth_scopes(self) -> List[str]:
        """Required OAuth scopes"""
        pass

    # ================== Authentication ==================

    @abstractmethod
    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            redirect_uri: Callback URL after auth
            state: State parameter for CSRF protection

        Returns:
            OAuth authorization URL
        """
        pass

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorResult:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Callback URL used in initial request

        Returns:
            ConnectorResult with tokens in data
        """
        pass

    @abstractmethod
    async def refresh_access_token(self) -> ConnectorResult:
        """
        Refresh the access token using refresh token.

        Returns:
            ConnectorResult with new tokens in data
        """
        pass

    async def validate_connection(self) -> ConnectorResult:
        """
        Validate that the connection is working.

        Returns:
            ConnectorResult indicating connection status
        """
        try:
            # Try to list documents as validation
            async for _ in self.list_documents():
                return ConnectorResult(
                    status=ConnectorStatus.SUCCESS,
                    message="Connection validated"
                )
            return ConnectorResult(
                status=ConnectorStatus.SUCCESS,
                message="Connection validated (no documents)"
            )
        except Exception as e:
            return ConnectorResult(
                status=ConnectorStatus.ERROR,
                error=str(e),
                message="Connection validation failed"
            )

    # ================== Document Operations ==================

    @abstractmethod
    async def list_documents(
        self,
        path: Optional[str] = None,
        modified_since: Optional[datetime] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        List documents from external source.

        Args:
            path: Optional path/folder to list from
            modified_since: Only list documents modified after this time (for incremental sync)

        Yields:
            Document metadata dictionaries
        """
        pass

    @abstractmethod
    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """
        Fetch full document content.

        Args:
            external_id: Document ID in external system

        Returns:
            ConnectorResult with ConnectorDocument in data
        """
        pass

    async def fetch_documents_batch(
        self,
        external_ids: List[str],
        batch_size: int = 10
    ) -> AsyncGenerator[ConnectorResult, None]:
        """
        Fetch multiple documents in batches.

        Args:
            external_ids: List of document IDs
            batch_size: Number of concurrent fetches

        Yields:
            ConnectorResult for each document
        """
        import asyncio

        for i in range(0, len(external_ids), batch_size):
            batch = external_ids[i:i + batch_size]
            tasks = [self.fetch_document(doc_id) for doc_id in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    yield ConnectorResult(
                        status=ConnectorStatus.ERROR,
                        error=str(result)
                    )
                else:
                    yield result

    # ================== Sync Support ==================

    async def get_changes_since(
        self,
        since: datetime
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Get documents changed since a specific time.
        Default implementation uses list_documents with modified_since.

        Args:
            since: Get changes after this time

        Yields:
            Changed document metadata
        """
        async for doc in self.list_documents(modified_since=since):
            yield doc

    async def check_document_exists(self, external_id: str) -> bool:
        """
        Check if a document still exists in external source.

        Args:
            external_id: Document ID to check

        Returns:
            True if document exists
        """
        result = await self.fetch_document(external_id)
        return result.status == ConnectorStatus.SUCCESS

    # ================== Helper Methods ==================

    def normalize_content(self, raw_content: Any, content_type: str) -> str:
        """
        Normalize raw content to plain text.

        Args:
            raw_content: Raw content from API
            content_type: Content MIME type

        Returns:
            Normalized plain text
        """
        if isinstance(raw_content, str):
            return raw_content

        # HTML to text
        if content_type and "html" in content_type:
            return self._html_to_text(raw_content)

        # JSON/dict to text
        if isinstance(raw_content, dict):
            return self._dict_to_text(raw_content)

        return str(raw_content)

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text with structure preserved"""
        import re

        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)

        # Convert headers to markdown-style
        for i in range(1, 7):
            text = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', rf'\n{"#" * i} \1\n', text, flags=re.DOTALL)

        # Convert lists
        text = re.sub(r'<li[^>]*>(.*?)</li>', r'• \1\n', text, flags=re.DOTALL)

        # Convert paragraphs
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL)

        # Convert line breaks
        text = re.sub(r'<br\s*/?>', '\n', text)

        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        import html
        text = html.unescape(text)

        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()

        return text

    def _dict_to_text(self, data: Dict) -> str:
        """Convert dictionary to readable text"""
        lines = []

        def process_value(key: str, value: Any, indent: int = 0):
            prefix = "  " * indent
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                for k, v in value.items():
                    process_value(k, v, indent + 1)
            elif isinstance(value, list):
                lines.append(f"{prefix}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        process_value("-", item, indent + 1)
                    else:
                        lines.append(f"{prefix}  • {item}")
            else:
                lines.append(f"{prefix}{key}: {value}")

        for key, value in data.items():
            process_value(key, value)

        return "\n".join(lines)
