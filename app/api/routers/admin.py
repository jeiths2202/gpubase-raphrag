"""
Admin API Router
관리자 전용 API - 사용자 관리, 대시보드 통계
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, EmailStr

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_current_user, get_admin_user, get_auth_service

router = APIRouter(prefix="/admin", tags=["Admin"])


# Request/Response Models
class UserListResponse(BaseModel):
    """User list response"""
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: Optional[str] = None


class UserUpdateRequest(BaseModel):
    """User update request"""
    role: Optional[str] = Field(None, pattern=r'^(admin|user)$')
    is_active: Optional[bool] = None
    email: Optional[EmailStr] = None


class UserStatsResponse(BaseModel):
    """User statistics response"""
    total_users: int
    active_users: int
    inactive_users: int
    admin_users: int
    regular_users: int
    pending_verification: int


class DashboardStats(BaseModel):
    """Dashboard statistics"""
    users: UserStatsResponse
    system: dict


@router.get(
    "/users",
    response_model=SuccessResponse[dict],
    summary="사용자 목록 조회",
    description="모든 사용자 목록을 조회합니다. (관리자 전용)"
)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """List all users with pagination"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await auth_service.list_users(page=page, limit=limit, search=search)

    return SuccessResponse(
        data=result,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/users/{user_id}",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 상세 조회",
    description="특정 사용자의 상세 정보를 조회합니다. (관리자 전용)"
)
async def get_user(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    user = await auth_service.get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=UserListResponse(**user),
        meta=MetaInfo(request_id=request_id)
    )


@router.patch(
    "/users/{user_id}",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 정보 수정",
    description="사용자의 역할, 활성화 상태 등을 수정합니다. (관리자 전용)"
)
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Update user details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Build update dict
    updates = {}
    if request.role is not None:
        updates["role"] = request.role
    if request.is_active is not None:
        updates["is_active"] = request.is_active
    if request.email is not None:
        updates["email"] = request.email

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_UPDATES", "message": "수정할 내용이 없습니다."}
        )

    user = await auth_service.update_user(user_id, updates)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=UserListResponse(**user),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/users/{user_id}",
    response_model=SuccessResponse[dict],
    summary="사용자 삭제",
    description="사용자를 삭제합니다. 기본 관리자 계정은 삭제할 수 없습니다. (관리자 전용)"
)
async def delete_user(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Delete a user"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Prevent self-deletion
    if admin_user["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SELF_DELETE", "message": "자신의 계정은 삭제할 수 없습니다."}
        )

    success = await auth_service.delete_user(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "DELETE_FAILED", "message": "사용자를 삭제할 수 없습니다. 기본 관리자 계정이거나 존재하지 않는 사용자입니다."}
        )

    return SuccessResponse(
        data={"message": "사용자가 삭제되었습니다.", "deleted_user_id": user_id},
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/users/{user_id}/toggle-active",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 활성화/비활성화",
    description="사용자의 활성화 상태를 토글합니다. (관리자 전용)"
)
async def toggle_user_active(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Toggle user active status"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Get current user
    user = await auth_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    # Toggle active status
    new_status = not user.get("is_active", True)
    updated = await auth_service.update_user(user_id, {"is_active": new_status})

    return SuccessResponse(
        data=UserListResponse(**updated),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/stats",
    response_model=SuccessResponse[UserStatsResponse],
    summary="사용자 통계",
    description="사용자 관련 통계를 조회합니다. (관리자 전용)"
)
async def get_user_stats(
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    stats = await auth_service.get_user_stats()

    return SuccessResponse(
        data=UserStatsResponse(**stats),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/dashboard",
    response_model=SuccessResponse[dict],
    summary="대시보드 통계",
    description="관리자 대시보드용 통계를 조회합니다. (관리자 전용)"
)
async def get_dashboard_stats(
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get dashboard statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    user_stats = await auth_service.get_user_stats()

    # System info (mock for now)
    system_stats = {
        "uptime": "Running",
        "api_version": "1.0.0",
        "environment": "development"
    }

    return SuccessResponse(
        data={
            "users": user_stats,
            "system": system_stats
        },
        meta=MetaInfo(request_id=request_id)
    )
