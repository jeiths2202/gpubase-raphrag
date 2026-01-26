"""
HttpOnly Cookie Authentication
Secure token handling via cookies to prevent XSS token theft.

SECURITY FEATURES:
- HttpOnly: Prevents JavaScript access to tokens
- Secure: Only sent over HTTPS (production)
- SameSite=Strict: Prevents CSRF attacks
- Scoped paths: Refresh token only sent to auth endpoints

MIGRATION NOTES:
- Frontend should use withCredentials: true for API calls
- Authorization header is still supported for API clients
- Cookie takes priority over header when both are present
"""
import os
from typing import Optional
from fastapi import Request, Response

from .config import api_settings


class CookieConfig:
    """Cookie security configuration"""

    # Cookie names
    ACCESS_TOKEN_NAME = "kms_access_token"
    REFRESH_TOKEN_NAME = "kms_refresh_token"

    # Security flags
    HTTPONLY = True  # Prevent JavaScript access
    SAMESITE = "strict"  # Prevent CSRF

    # HTTPS only in production
    @classmethod
    def is_secure(cls) -> bool:
        """Check if cookies should require HTTPS"""
        env = os.environ.get("APP_ENV", "production").lower()
        return env not in ["development", "dev", "local"]

    # Cookie paths
    ACCESS_TOKEN_PATH = "/api"  # Available for all API endpoints
    REFRESH_TOKEN_PATH = "/api/v1/auth"  # Restricted to auth endpoints

    # Expiration (in seconds)
    @classmethod
    def get_access_token_max_age(cls) -> int:
        """Get access token expiration in seconds"""
        return api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @classmethod
    def get_refresh_token_max_age(cls) -> int:
        """Get refresh token expiration in seconds"""
        return api_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: Optional[str] = None
) -> None:
    """
    Set secure authentication cookies.

    SECURITY:
    - HttpOnly prevents JavaScript access (XSS protection)
    - Secure flag ensures HTTPS-only in production
    - SameSite=Strict prevents CSRF attacks
    - Scoped paths limit token exposure

    Args:
        response: FastAPI Response object
        access_token: JWT access token
        refresh_token: JWT refresh token (optional)
    """
    # Access token cookie - available for all API endpoints
    response.set_cookie(
        key=CookieConfig.ACCESS_TOKEN_NAME,
        value=access_token,
        max_age=CookieConfig.get_access_token_max_age(),
        path=CookieConfig.ACCESS_TOKEN_PATH,
        httponly=CookieConfig.HTTPONLY,
        secure=CookieConfig.is_secure(),
        samesite=CookieConfig.SAMESITE,
    )

    # Refresh token cookie - restricted to auth endpoints only
    if refresh_token:
        response.set_cookie(
            key=CookieConfig.REFRESH_TOKEN_NAME,
            value=refresh_token,
            max_age=CookieConfig.get_refresh_token_max_age(),
            path=CookieConfig.REFRESH_TOKEN_PATH,
            httponly=CookieConfig.HTTPONLY,
            secure=CookieConfig.is_secure(),
            samesite=CookieConfig.SAMESITE,
        )


def clear_auth_cookies(response: Response) -> None:
    """
    Clear authentication cookies on logout.

    Sets cookies with expired dates to force browser to delete them.

    Args:
        response: FastAPI Response object
    """
    # Clear access token
    response.delete_cookie(
        key=CookieConfig.ACCESS_TOKEN_NAME,
        path=CookieConfig.ACCESS_TOKEN_PATH,
        httponly=CookieConfig.HTTPONLY,
        secure=CookieConfig.is_secure(),
        samesite=CookieConfig.SAMESITE,
    )

    # Clear refresh token
    response.delete_cookie(
        key=CookieConfig.REFRESH_TOKEN_NAME,
        path=CookieConfig.REFRESH_TOKEN_PATH,
        httponly=CookieConfig.HTTPONLY,
        secure=CookieConfig.is_secure(),
        samesite=CookieConfig.SAMESITE,
    )


def get_token_from_cookie(request: Request) -> Optional[str]:
    """
    Extract access token from cookie.

    Args:
        request: FastAPI Request object

    Returns:
        Access token string or None if not present
    """
    return request.cookies.get(CookieConfig.ACCESS_TOKEN_NAME)


def get_refresh_token_from_cookie(request: Request) -> Optional[str]:
    """
    Extract refresh token from cookie.

    Args:
        request: FastAPI Request object

    Returns:
        Refresh token string or None if not present
    """
    return request.cookies.get(CookieConfig.REFRESH_TOKEN_NAME)


def get_token_from_request(
    request: Request,
    authorization_header: Optional[str] = None
) -> Optional[str]:
    """
    Extract token from request, preferring cookie over header.

    Priority:
    1. HttpOnly Cookie (more secure)
    2. Authorization Header (for API clients)

    Args:
        request: FastAPI Request object
        authorization_header: Authorization header value (optional)

    Returns:
        Token string or None
    """
    # Try cookie first (more secure, preferred)
    token = get_token_from_cookie(request)
    if token:
        return token

    # Fall back to Authorization header for API clients
    if authorization_header and authorization_header.startswith("Bearer "):
        return authorization_header[7:]  # Remove "Bearer " prefix

    return None
