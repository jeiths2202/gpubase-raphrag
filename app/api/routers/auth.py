"""
Auth API Router
인증 관련 API

SECURITY FEATURES:
- HttpOnly cookies for token storage (prevents XSS token theft)
- Secure flag for HTTPS-only cookies in production
- SameSite=Strict for CSRF protection
- Dual support: cookies (preferred) and Authorization header (API clients)
"""
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import HTTPBearer

from ..models.base import SuccessResponse, MetaInfo
from ..models.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    UserInfo,
    RegisterRequest,
    RegisterResponse,
    VerifyEmailRequest,
    ResendVerificationRequest,
    GoogleAuthRequest,
    SSORequest,
)
from ..core.deps import get_current_user, get_auth_service
from ..core.config import api_settings
from ..core.cookie_auth import set_auth_cookies, clear_auth_cookies, get_refresh_token_from_cookie

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    summary="로그인",
    description="사용자 인증 및 JWT 토큰을 발급합니다. 토큰은 HttpOnly 쿠키에 저장됩니다."
)
async def login(
    request: LoginRequest,
    response: Response,
    auth_service = Depends(get_auth_service)
):
    """
    Authenticate user and return JWT tokens.

    SECURITY:
    - Tokens are set as HttpOnly cookies (prevents XSS access)
    - Response body includes token info for API clients
    - Cookie takes priority over Authorization header
    """
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

    # SECURITY: Set HttpOnly cookies for browser clients
    set_auth_cookies(response, access_token, refresh_token)

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
    http_request: Request,
    response: Response,
    request: RefreshRequest = None,
    auth_service = Depends(get_auth_service)
):
    """
    Refresh access token using refresh token.

    SECURITY:
    - Accepts refresh token from cookie OR request body
    - Cookie takes priority over request body
    - New tokens are set as HttpOnly cookies
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Get refresh token from cookie first, then request body
    token_value = get_refresh_token_from_cookie(http_request)
    if not token_value and request and request.refresh_token:
        token_value = request.refresh_token

    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_MISSING_TOKEN",
                "message": "Refresh 토큰이 필요합니다."
            }
        )

    # Verify refresh token and get user
    user = await auth_service.verify_refresh_token(token_value)

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
    new_refresh_token = await auth_service.create_refresh_token(user)

    # SECURITY: Set new HttpOnly cookies
    set_auth_cookies(response, access_token, new_refresh_token)

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_token=new_refresh_token
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/logout",
    response_model=SuccessResponse[dict],
    summary="로그아웃",
    description="현재 토큰을 무효화하고 쿠키를 삭제합니다."
)
async def logout(
    response: Response,
    current_user: dict = Depends(get_current_user),
    auth_service = Depends(get_auth_service)
):
    """
    Invalidate current tokens and clear cookies.

    SECURITY:
    - Clears HttpOnly cookies from browser
    - Invalidates tokens on server-side
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Invalidate tokens on server
    await auth_service.invalidate_tokens(current_user["id"])

    # SECURITY: Clear HttpOnly cookies
    clear_auth_cookies(response)

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


@router.post(
    "/register",
    response_model=SuccessResponse[RegisterResponse],
    summary="회원가입",
    description="새 사용자를 등록하고 이메일 인증 코드를 발송합니다."
)
async def register(
    request: RegisterRequest,
    auth_service = Depends(get_auth_service)
):
    """Register a new user and send verification email"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await auth_service.register_user(
        user_id=request.user_id,
        email=request.email,
        password=request.password
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": result["error"],
                "message": result["message"]
            }
        )

    return SuccessResponse(
        data=RegisterResponse(
            user_id=result["user_id"],
            email=result["email"],
            message=result["message"]
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/verify",
    response_model=SuccessResponse[TokenResponse],
    summary="이메일 인증",
    description="이메일로 발송된 인증 코드를 확인하고 계정을 활성화합니다."
)
async def verify_email(
    request: VerifyEmailRequest,
    auth_service = Depends(get_auth_service)
):
    """Verify email with code and return tokens"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await auth_service.verify_email(
        email=request.email,
        code=request.code
    )

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": result["error"],
                "message": result["message"]
            }
        )

    # Generate tokens for verified user
    user = result["user"]
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
    "/resend-verification",
    response_model=SuccessResponse[dict],
    summary="인증 코드 재발송",
    description="이메일 인증 코드를 재발송합니다."
)
async def resend_verification(
    request: ResendVerificationRequest,
    auth_service = Depends(get_auth_service)
):
    """Resend verification email"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await auth_service.resend_verification(email=request.email)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": result["error"],
                "message": result["message"]
            }
        )

    return SuccessResponse(
        data={"message": result["message"]},
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/google",
    response_model=SuccessResponse[TokenResponse],
    summary="Google 로그인",
    description="Google OAuth를 사용하여 로그인합니다."
)
async def google_auth(
    request: GoogleAuthRequest,
    auth_service = Depends(get_auth_service)
):
    """Authenticate with Google OAuth"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    user = await auth_service.authenticate_google(request.credential)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTH_GOOGLE_FAILED",
                "message": "Google 인증에 실패했습니다."
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
    "/sso",
    response_model=SuccessResponse[dict],
    summary="회사 SSO 로그인",
    description="회사 이메일을 사용한 SSO 로그인을 시작합니다."
)
async def initiate_sso(
    request: SSORequest,
    auth_service = Depends(get_auth_service)
):
    """Initiate corporate SSO login"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await auth_service.initiate_sso(email=request.email)

    if "error" in result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": result["error"],
                "message": result["message"]
            }
        )

    return SuccessResponse(
        data={
            "sso_url": result["sso_url"],
            "message": result["message"]
        },
        meta=MetaInfo(request_id=request_id)
    )
