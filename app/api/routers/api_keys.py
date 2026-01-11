"""
API Keys Router

Endpoints for managing API keys (admin and owner access).
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..core.deps import get_current_user, get_admin_user
from ..models.api_key import (
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyResponse,
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
)
from ..services.api_key_service import get_api_key_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _get_service():
    """Get API key service or raise error."""
    service = get_api_key_service()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "API Key 서비스를 사용할 수 없습니다."}
        )
    return service


# ============================================================
# User Endpoints (manage own API keys)
# ============================================================

@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    data: ApiKeyCreate,
    current_user: dict = Depends(get_current_user)
) -> ApiKeyCreatedResponse:
    """
    Create a new API key for the current user.

    The full API key is shown only once in the response.
    Save it securely - it cannot be retrieved again.

    Args:
        data: API key configuration

    Returns:
        Created API key with the full key
    """
    service = _get_service()

    user_id = UUID(current_user["id"])
    result = await service.create_api_key(data, owner_id=user_id)

    logger.info(f"User {user_id} created API key: {result.key_prefix}...")

    return result


@router.get("", response_model=ApiKeyListResponse)
async def list_my_api_keys(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    include_inactive: bool = Query(False, description="Include inactive keys"),
    current_user: dict = Depends(get_current_user)
) -> ApiKeyListResponse:
    """
    List API keys owned by the current user.

    Args:
        page: Page number (1-based)
        page_size: Items per page (max 100)
        include_inactive: Include inactive keys

    Returns:
        Paginated list of API keys
    """
    service = _get_service()

    user_id = UUID(current_user["id"])
    return await service.list_api_keys(
        owner_id=user_id,
        page=page,
        page_size=page_size,
        include_inactive=include_inactive
    )


@router.get("/{api_key_id}", response_model=ApiKeyResponse)
async def get_my_api_key(
    api_key_id: UUID,
    current_user: dict = Depends(get_current_user)
) -> ApiKeyResponse:
    """
    Get details of an API key owned by the current user.

    Args:
        api_key_id: API key ID

    Returns:
        API key details (without the actual key)
    """
    service = _get_service()

    key = await service.get_api_key(api_key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "API 키를 찾을 수 없습니다."}
        )

    user_id = UUID(current_user["id"])
    if key.owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "이 API 키에 접근할 권한이 없습니다."}
        )

    return key


@router.patch("/{api_key_id}", response_model=ApiKeyResponse)
async def update_my_api_key(
    api_key_id: UUID,
    data: ApiKeyUpdate,
    current_user: dict = Depends(get_current_user)
) -> ApiKeyResponse:
    """
    Update an API key owned by the current user.

    Args:
        api_key_id: API key ID
        data: Fields to update

    Returns:
        Updated API key details
    """
    service = _get_service()

    user_id = UUID(current_user["id"])
    result = await service.update_api_key(api_key_id, data, owner_id=user_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "API 키를 찾을 수 없거나 접근 권한이 없습니다."}
        )

    return result


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_api_key(
    api_key_id: UUID,
    current_user: dict = Depends(get_current_user)
) -> None:
    """
    Delete (deactivate) an API key owned by the current user.

    Args:
        api_key_id: API key ID
    """
    service = _get_service()

    user_id = UUID(current_user["id"])
    deleted = await service.delete_api_key(api_key_id, owner_id=user_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "API 키를 찾을 수 없거나 접근 권한이 없습니다."}
        )


# ============================================================
# Admin Endpoints (manage all API keys)
# ============================================================

@router.get("/admin/all", response_model=ApiKeyListResponse)
async def list_all_api_keys(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    include_inactive: bool = Query(False, description="Include inactive keys"),
    admin_user: dict = Depends(get_admin_user)
) -> ApiKeyListResponse:
    """
    List all API keys (admin only).

    Args:
        page: Page number
        page_size: Items per page
        include_inactive: Include inactive keys

    Returns:
        Paginated list of all API keys
    """
    service = _get_service()

    return await service.list_api_keys(
        owner_id=None,  # All keys
        page=page,
        page_size=page_size,
        include_inactive=include_inactive
    )


@router.post("/admin/create", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_api_key(
    data: ApiKeyCreate,
    owner_id: Optional[UUID] = Query(None, description="Owner user ID (optional)"),
    admin_user: dict = Depends(get_admin_user)
) -> ApiKeyCreatedResponse:
    """
    Create an API key (admin only).

    Can create system-wide API keys without an owner.

    Args:
        data: API key configuration
        owner_id: Optional owner user ID

    Returns:
        Created API key with the full key
    """
    service = _get_service()

    result = await service.create_api_key(data, owner_id=owner_id)

    admin_id = admin_user.get("id")
    logger.info(f"Admin {admin_id} created API key: {result.key_prefix}... (owner: {owner_id})")

    return result


@router.get("/admin/{api_key_id}", response_model=ApiKeyResponse)
async def admin_get_api_key(
    api_key_id: UUID,
    admin_user: dict = Depends(get_admin_user)
) -> ApiKeyResponse:
    """
    Get any API key details (admin only).

    Args:
        api_key_id: API key ID

    Returns:
        API key details
    """
    service = _get_service()

    key = await service.get_api_key(api_key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "API 키를 찾을 수 없습니다."}
        )

    return key


@router.patch("/admin/{api_key_id}", response_model=ApiKeyResponse)
async def admin_update_api_key(
    api_key_id: UUID,
    data: ApiKeyUpdate,
    admin_user: dict = Depends(get_admin_user)
) -> ApiKeyResponse:
    """
    Update any API key (admin only).

    Args:
        api_key_id: API key ID
        data: Fields to update

    Returns:
        Updated API key details
    """
    service = _get_service()

    result = await service.update_api_key(api_key_id, data, owner_id=None)  # Skip ownership check

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "API 키를 찾을 수 없습니다."}
        )

    return result


@router.delete("/admin/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_api_key(
    api_key_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete"),
    admin_user: dict = Depends(get_admin_user)
) -> None:
    """
    Delete any API key (admin only).

    Args:
        api_key_id: API key ID
        hard_delete: If true, permanently delete (cannot be undone)
    """
    service = _get_service()

    deleted = await service.delete_api_key(api_key_id, owner_id=None, hard_delete=hard_delete)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "API 키를 찾을 수 없습니다."}
        )

    admin_id = admin_user.get("id")
    logger.info(f"Admin {admin_id} deleted API key: {api_key_id} (hard_delete={hard_delete})")


@router.post("/admin/cleanup", status_code=status.HTTP_200_OK)
async def admin_cleanup_rate_limits(
    older_than_hours: int = Query(24, ge=1, le=168, description="Clean entries older than this"),
    admin_user: dict = Depends(get_admin_user)
) -> dict:
    """
    Clean up old rate limit entries (admin only).

    Args:
        older_than_hours: Delete entries older than this (1-168 hours)

    Returns:
        Number of entries deleted
    """
    service = _get_service()

    count = await service.cleanup_rate_limits(older_than_hours)

    return {"deleted_count": count, "older_than_hours": older_than_hours}
