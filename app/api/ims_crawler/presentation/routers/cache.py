"""
API router for IMS cache management
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.core.deps import get_current_user
from app.api.ims_crawler.infrastructure.dependencies import (
    get_cache_service,
    get_cached_search_service,
    get_cached_dashboard_service
)


router = APIRouter(prefix="/ims-cache", tags=["IMS Cache"])


class CacheStatsResponse(BaseModel):
    """Cache statistics response"""
    search_cached: bool
    search_ttl_seconds: int | None
    dashboard_cached: bool
    dashboard_ttl_seconds: int | None


@router.delete("/invalidate/search")
async def invalidate_search_cache(
    current_user: dict = Depends(get_current_user),
    cached_search_service = Depends(get_cached_search_service)
):
    """
    Invalidate all cached search results for current user

    Useful after:
    - Completing a crawl job (new issues added)
    - Updating issue statuses
    - Deleting issues
    """

    user_id = UUID(current_user["id"])

    try:
        deleted_count = await cached_search_service.invalidate_user_cache(user_id)

        return {
            "message": f"Invalidated {deleted_count} cached search entries",
            "deleted_count": deleted_count,
            "user_id": str(user_id)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}")


@router.delete("/invalidate/dashboard")
async def invalidate_dashboard_cache(
    current_user: dict = Depends(get_current_user),
    cached_dashboard_service = Depends(get_cached_dashboard_service)
):
    """
    Invalidate cached dashboard statistics for current user

    Useful after:
    - Completing a crawl job
    - Major data changes
    """

    user_id = UUID(current_user["id"])

    try:
        deleted_count = await cached_dashboard_service.invalidate_user_dashboard(user_id)

        return {
            "message": f"Invalidated {deleted_count} cached dashboard entries",
            "deleted_count": deleted_count,
            "user_id": str(user_id)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}")


@router.delete("/invalidate/all")
async def invalidate_all_cache(
    current_user: dict = Depends(get_current_user),
    cached_search_service = Depends(get_cached_search_service),
    cached_dashboard_service = Depends(get_cached_dashboard_service)
):
    """
    Invalidate all cached data for current user

    Clears both search results and dashboard statistics
    """

    user_id = UUID(current_user["id"])

    try:
        search_deleted = await cached_search_service.invalidate_user_cache(user_id)
        dashboard_deleted = await cached_dashboard_service.invalidate_user_dashboard(user_id)
        total_deleted = search_deleted + dashboard_deleted

        return {
            "message": f"Invalidated all cache for user",
            "search_entries_deleted": search_deleted,
            "dashboard_entries_deleted": dashboard_deleted,
            "total_deleted": total_deleted,
            "user_id": str(user_id)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}")


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    query: str = "test",
    current_user: dict = Depends(get_current_user),
    cached_search_service = Depends(get_cached_search_service),
    cached_dashboard_service = Depends(get_cached_dashboard_service)
):
    """
    Get cache statistics for current user

    Shows:
    - Whether search results are cached
    - Remaining TTL for cached data
    - Dashboard cache status
    """

    user_id = UUID(current_user["id"])

    try:
        # Get search cache stats
        search_stats = await cached_search_service.get_cache_stats(user_id, query)

        # Get dashboard cache stats
        dashboard_stats = await cached_dashboard_service.get_cache_info(user_id, trend_days=7)

        return CacheStatsResponse(
            search_cached=search_stats['cached'],
            search_ttl_seconds=search_stats['ttl_seconds'],
            dashboard_cached=dashboard_stats['cached'],
            dashboard_ttl_seconds=dashboard_stats['ttl_seconds']
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")


@router.post("/warmup")
async def warmup_cache(
    current_user: dict = Depends(get_current_user),
    cached_dashboard_service = Depends(get_cached_dashboard_service)
):
    """
    Warm up cache by pre-loading dashboard statistics

    Useful:
    - After application startup
    - Before expected high traffic
    """

    user_id = UUID(current_user["id"])

    try:
        # Pre-load dashboard for 7 and 30 days
        await cached_dashboard_service.get_statistics(user_id, trend_days=7)
        await cached_dashboard_service.get_statistics(user_id, trend_days=30)

        return {
            "message": "Cache warmed up successfully",
            "cached_entries": ["dashboard:7days", "dashboard:30days"],
            "user_id": str(user_id)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to warm up cache: {str(e)}")
