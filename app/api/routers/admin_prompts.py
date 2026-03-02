"""
Admin Prompt Configuration Router

Provides API endpoints for managing system prompts:
- List and view prompts
- Update prompt content
- Version history and rollback
- File synchronization

All endpoints require admin authentication.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..core.deps import get_current_user
from ..models.prompt_config import (
    PromptSummary, PromptDetail, PromptUpdateRequest,
    PromptHistory, PromptTestRequest, PromptTestResult,
    SyncResult, PromptCategory
)
from ..services.prompt_config_service import (
    get_prompt_config_service, PromptConfigService
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/prompts",
    tags=["Admin - Prompt Configuration"],
)


# Dependency to verify admin user
async def require_admin(user: dict = Depends(get_current_user)):
    """Require admin privileges for the endpoint."""
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    user_role = user.get('role')
    if user_role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user


# Dependency to get service
async def get_service() -> PromptConfigService:
    return get_prompt_config_service()


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "",
    response_model=List[PromptSummary],
    summary="List all prompts",
    description="Returns all prompts with optional filtering by category and language."
)
async def list_prompts(
    category: Optional[PromptCategory] = Query(None, description="Filter by category"),
    language: Optional[str] = Query(None, description="Filter by language code"),
    service: PromptConfigService = Depends(get_service),
    _admin=Depends(require_admin),
) -> List[PromptSummary]:
    """List all prompts."""
    return await service.get_all_prompts(category=category, language=language)


@router.get(
    "/{prompt_id}",
    response_model=PromptDetail,
    summary="Get prompt detail",
    description="Returns full prompt detail including content."
)
async def get_prompt(
    prompt_id: str,
    language: str = Query("en", description="Language code"),
    service: PromptConfigService = Depends(get_service),
    _admin=Depends(require_admin),
) -> PromptDetail:
    """Get full prompt detail."""
    prompt = await service.get_prompt(prompt_id, language)
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt not found: {prompt_id}"
        )
    return prompt


@router.put(
    "/{prompt_id}",
    response_model=PromptDetail,
    summary="Update prompt",
    description="Updates prompt content. Creates new version in history."
)
async def update_prompt(
    prompt_id: str,
    request: PromptUpdateRequest,
    language: str = Query("en", description="Language code"),
    service: PromptConfigService = Depends(get_service),
    admin=Depends(require_admin),
) -> PromptDetail:
    """Update prompt content."""
    try:
        user_id = admin.get('id')
        return await service.update_prompt(
            prompt_id=prompt_id,
            language=language,
            content=request.content,
            reason=request.reason,
            user_id=user_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )


@router.get(
    "/{prompt_id}/history",
    response_model=List[PromptHistory],
    summary="Get version history",
    description="Returns version history for a prompt."
)
async def get_prompt_history(
    prompt_id: str,
    language: str = Query("en", description="Language code"),
    limit: int = Query(20, ge=1, le=100, description="Maximum entries"),
    service: PromptConfigService = Depends(get_service),
    _admin=Depends(require_admin),
) -> List[PromptHistory]:
    """Get version history."""
    return await service.get_prompt_history(prompt_id, language, limit)


@router.post(
    "/{prompt_id}/rollback/{version_id}",
    response_model=PromptDetail,
    summary="Rollback to version",
    description="Rollback prompt to a specific version from history."
)
async def rollback_prompt(
    prompt_id: str,
    version_id: UUID,
    language: str = Query("en", description="Language code"),
    service: PromptConfigService = Depends(get_service),
    admin=Depends(require_admin),
) -> PromptDetail:
    """Rollback to specific version."""
    try:
        user_id = admin.get('id')
        return await service.rollback_prompt(
            prompt_id=prompt_id,
            language=language,
            version_id=version_id,
            user_id=user_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post(
    "/{prompt_id}/test",
    response_model=PromptTestResult,
    summary="Test prompt",
    description="Test prompt rendering with sample variables."
)
async def test_prompt(
    prompt_id: str,
    request: PromptTestRequest,
    language: str = Query("en", description="Language code"),
    service: PromptConfigService = Depends(get_service),
    _admin=Depends(require_admin),
) -> PromptTestResult:
    """Test prompt with sample input."""
    return await service.test_prompt(
        prompt_id=prompt_id,
        language=language,
        test_query=request.test_query,
        variables=request.variables
    )


@router.post(
    "/sync",
    response_model=SyncResult,
    summary="Sync from files",
    description="Sync prompts from file system to database."
)
async def sync_prompts(
    service: PromptConfigService = Depends(get_service),
    _admin=Depends(require_admin),
) -> SyncResult:
    """Sync prompts from files."""
    return await service.sync_from_files()


@router.post(
    "/reload",
    summary="Reload cache",
    description="Force reload all prompts into runtime cache."
)
async def reload_cache(
    service: PromptConfigService = Depends(get_service),
    _admin=Depends(require_admin),
):
    """Force reload prompts into cache."""
    await service.reload_cache()
    return {"status": "ok", "message": "Cache reloaded"}
