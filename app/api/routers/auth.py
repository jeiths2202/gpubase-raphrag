"""
Auth API Router
인증 관련 API
"""
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from ..models.base import SuccessResponse, MetaInfo
from ..models.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    UserInfo,
)
from ..core.deps import get_current_user, get_auth_service
from ..core.config import api_settings

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    summary="로그인",
    description="사용자 인증 및 JWT 토큰을 발급합니다."
)
async def login(
    request: LoginRequest,
    auth_service = Depends(get_auth_service)
):
    """Authenticate user and return JWT tokens"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Authenticate user
    user = await auth_service.authenticate(
        username=request.username,
        password=request.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_INVALID_CREDENTIALS",
                "message": "아이디 또는 비밀번호가 올바르지 않습니다."
            }
        )

    # Generate tokens
    access_token = await auth_service.create_access_token(user)
    refresh_token = await auth_service.create_refresh_token(user)

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=refresh_token
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/refresh",
    response_model=SuccessResponse[TokenResponse],
    summary="토큰 갱신",
    description="Refresh 토큰을 사용하여 새 Access 토큰을 발급합니다."
)
async def refresh_token(
    request: RefreshRequest,
    auth_service = Depends(get_auth_service)
):
    """Refresh access token using refresh token"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Verify refresh token and get user
    user = await auth_service.verify_refresh_token(request.refresh_token)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_INVALID_TOKEN",
                "message": "유효하지 않은 토큰입니다."
            }
        )

    # Generate new tokens
    access_token = await auth_service.create_access_token(user)
    refresh_token = await auth_service.create_refresh_token(user)

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=refresh_token
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/logout",
    response_model=SuccessResponse[dict],
    summary="로그아웃",
    description="현재 토큰을 무효화합니다."
)
async def logout(
    current_user: dict = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """Invalidate current tokens"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Invalidate tokens
    await auth_service.invalidate_tokens(current_user["id"])

    return SuccessResponse(
        data={"message": "로그아웃되었습니다."},
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/me",
    response_model=SuccessResponse[UserInfo],
    summary="현재 사용자 정보",
    description="현재 인증된 사용자의 정보를 조회합니다."
)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    """Get current user information"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    return SuccessResponse(
        data=UserInfo(
            id=current_user["id"],
            username=current_user["username"],
            role=current_user.get("role", "user"),
            is_active=current_user.get("is_active", True)
        ),
        meta=MetaInfo(request_id=request_id)
    )
