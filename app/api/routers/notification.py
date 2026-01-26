"""
Notification API Router
Handles in-app notifications and preferences
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_user
from ..models.notification import (
    Notification, NotificationType,
    NotificationListResponse, MarkReadRequest, NotificationCountResponse
)
from ..services.notification_service import get_notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def get_service():
    return get_notification_service()


@router.get("", response_model=dict)
async def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    type: Optional[NotificationType] = Query(None, description="Filter by type"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """List notifications for current user"""
    notifications, total, unread_count = await service.get_notifications(
        user_id=current_user["id"],
        is_read=is_read,
        notification_type=type,
        page=page,
        limit=limit
    )

    return {
        "status": "success",
        "data": {
            "notifications": [n.model_dump() for n in notifications],
            "total": total,
            "unread_count": unread_count,
            "page": page,
            "limit": limit
        }
    }


@router.get("/count", response_model=dict)
async def get_unread_count(
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get unread notification count"""
    counts = await service.get_unread_count(current_user["id"])

    return {
        "status": "success",
        "data": counts
    }


@router.post("/read", response_model=dict)
async def mark_as_read(
    request: MarkReadRequest,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Mark specific notifications as read"""
    count = await service.mark_as_read(
        notification_ids=request.notification_ids,
        user_id=current_user["id"]
    )

    return {
        "status": "success",
        "data": {
            "marked_count": count
        },
        "message": f"{count}개의 알림을 읽음으로 표시했습니다."
    }


@router.post("/read-all", response_model=dict)
async def mark_all_as_read(
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Mark all notifications as read"""
    count = await service.mark_all_as_read(current_user["id"])

    return {
        "status": "success",
        "data": {
            "marked_count": count
        },
        "message": "모든 알림을 읽음으로 표시했습니다."
    }


@router.delete("/{notification_id}", response_model=dict)
async def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Delete a notification"""
    success = await service.delete_notification(
        notification_id=notification_id,
        user_id=current_user["id"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "알림을 찾을 수 없습니다."}
        )

    return {
        "status": "success",
        "message": "알림이 삭제되었습니다."
    }


@router.get("/preferences", response_model=dict)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get notification preferences"""
    preferences = await service.get_preferences(current_user["id"])

    return {
        "status": "success",
        "data": {
            "preferences": preferences.model_dump()
        }
    }


@router.put("/preferences", response_model=dict)
async def update_preferences(
    preferences: dict,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Update notification preferences"""
    updated = await service.update_preferences(
        user_id=current_user["id"],
        preferences=preferences
    )

    return {
        "status": "success",
        "data": {
            "preferences": updated.model_dump()
        },
        "message": "알림 설정이 업데이트되었습니다."
    }
