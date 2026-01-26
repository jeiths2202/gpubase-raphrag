"""
API Key Service

Business logic layer for API key management.
Wraps repository operations with validation and permission checks.
"""
import logging
from typing import Optional, List, Tuple
from uuid import UUID

from ..models.api_key import (
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyResponse,
    ApiKeyCreatedResponse,
    ApiKeyValidationResult,
    ApiKeyListResponse,
    RateLimitStatus,
)
from ..infrastructure.postgres.api_key_repository import PostgresApiKeyRepository

logger = logging.getLogger(__name__)

# Singleton instance
_api_key_service: Optional["ApiKeyService"] = None


class ApiKeyService:
    """
    API Key Service for managing public access keys.

    Features:
    - Create/update/delete API keys
    - Validate keys and check permissions
    - Rate limiting enforcement
    - Usage tracking
    """

    def __init__(self, repository: PostgresApiKeyRepository):
        """
        Initialize API Key Service.

        Args:
            repository: API key repository instance
        """
        self._repository = repository

    async def create_api_key(
        self,
        data: ApiKeyCreate,
        owner_id: Optional[UUID] = None
    ) -> ApiKeyCreatedResponse:
        """
        Create a new API key.

        Args:
            data: API key creation data
            owner_id: Optional owner user ID

        Returns:
            Created API key with the full key (shown only once)
        """
        logger.info(f"Creating API key: {data.name}")
        return await self._repository.create(data, owner_id)

    async def validate_api_key(
        self,
        api_key: str,
        endpoint: Optional[str] = None,
        agent_type: Optional[str] = None
    ) -> ApiKeyValidationResult:
        """
        Validate an API key and check permissions.

        Args:
            api_key: The API key to validate
            endpoint: Optional endpoint being accessed
            agent_type: Optional agent type being used

        Returns:
            Validation result with permissions
        """
        result = await self._repository.validate(api_key)

        if not result.is_valid:
            return result

        # Check endpoint permission
        if endpoint and result.allowed_endpoints:
            allowed = any(
                endpoint.startswith(ep) or ep == "*"
                for ep in result.allowed_endpoints
            )
            if not allowed:
                return ApiKeyValidationResult(
                    is_valid=False,
                    error=f"Endpoint '{endpoint}' not allowed for this API key"
                )

        # Check agent type permission
        if agent_type and result.allowed_agent_types:
            if agent_type not in result.allowed_agent_types and "*" not in result.allowed_agent_types:
                return ApiKeyValidationResult(
                    is_valid=False,
                    error=f"Agent type '{agent_type}' not allowed for this API key"
                )

        return result

    async def check_and_increment_rate_limit(
        self,
        api_key_id: UUID
    ) -> Tuple[bool, Optional[RateLimitStatus]]:
        """
        Check rate limits and increment if allowed.

        Args:
            api_key_id: API key ID

        Returns:
            Tuple of (is_allowed, rate_limit_status)
        """
        is_allowed, status = await self._repository.check_rate_limit(api_key_id)

        if is_allowed:
            await self._repository.increment_rate_limit(api_key_id)

        return is_allowed, status

    async def record_usage(
        self,
        api_key_id: UUID,
        endpoint: str,
        method: str,
        agent_type: Optional[str] = None,
        tokens_used: int = 0,
        response_time_ms: int = 0,
        status_code: int = 200,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Record API usage for analytics."""
        await self._repository.record_usage(
            api_key_id=api_key_id,
            endpoint=endpoint,
            method=method,
            agent_type=agent_type,
            tokens_used=tokens_used,
            response_time_ms=response_time_ms,
            status_code=status_code,
            client_ip=client_ip,
            user_agent=user_agent,
            error_message=error_message
        )

    async def get_api_key(self, api_key_id: UUID) -> Optional[ApiKeyResponse]:
        """Get API key by ID."""
        return await self._repository.get_by_id(api_key_id)

    async def list_api_keys(
        self,
        owner_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False
    ) -> ApiKeyListResponse:
        """
        List API keys.

        Args:
            owner_id: Filter by owner (None = all, for admin)
            page: Page number
            page_size: Items per page
            include_inactive: Include inactive keys

        Returns:
            Paginated list of API keys
        """
        if owner_id:
            keys, total = await self._repository.list_by_owner(
                owner_id, page, page_size, include_inactive
            )
        else:
            keys, total = await self._repository.list_all(
                page, page_size, include_inactive
            )

        return ApiKeyListResponse(
            items=keys,
            total=total,
            page=page,
            page_size=page_size
        )

    async def update_api_key(
        self,
        api_key_id: UUID,
        data: ApiKeyUpdate,
        owner_id: Optional[UUID] = None
    ) -> Optional[ApiKeyResponse]:
        """
        Update an API key.

        Args:
            api_key_id: API key ID to update
            data: Update data
            owner_id: Owner ID for permission check (None = admin, skip check)

        Returns:
            Updated API key or None if not found/not authorized
        """
        if owner_id:
            # Verify ownership
            existing = await self._repository.get_by_id(api_key_id)
            if not existing or existing.owner_id != owner_id:
                return None

        return await self._repository.update(api_key_id, data)

    async def delete_api_key(
        self,
        api_key_id: UUID,
        owner_id: Optional[UUID] = None,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete an API key.

        Args:
            api_key_id: API key ID to delete
            owner_id: Owner ID for permission check (None = admin, skip check)
            hard_delete: If True, permanently delete

        Returns:
            True if deleted, False if not found/not authorized
        """
        if owner_id:
            # Verify ownership
            existing = await self._repository.get_by_id(api_key_id)
            if not existing or existing.owner_id != owner_id:
                return False

        if hard_delete:
            return await self._repository.hard_delete(api_key_id)
        return await self._repository.delete(api_key_id)

    async def cleanup_rate_limits(self, older_than_hours: int = 24) -> int:
        """Clean up old rate limit entries."""
        return await self._repository.cleanup_old_rate_limits(older_than_hours)


def get_api_key_service() -> Optional[ApiKeyService]:
    """Get the singleton API key service instance."""
    return _api_key_service


def set_api_key_service(service: ApiKeyService) -> None:
    """Set the singleton API key service instance."""
    global _api_key_service
    _api_key_service = service


async def init_api_key_service(pool) -> ApiKeyService:
    """
    Initialize the API key service with a database pool.

    Args:
        pool: asyncpg connection pool

    Returns:
        Initialized ApiKeyService instance
    """
    repository = PostgresApiKeyRepository(pool)
    service = ApiKeyService(repository)
    set_api_key_service(service)
    logger.info("API Key service initialized")
    return service
