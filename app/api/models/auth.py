"""
Authentication Pydantic models
"""
from typing import Optional
from pydantic import BaseModel, Field, EmailStr


class LoginRequest(BaseModel):
    """Login request"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "password": "password123"
            }
        }


class RegisterRequest(BaseModel):
    """User registration request"""
    user_id: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    email: EmailStr = Field(..., description="Email for verification")
    password: str = Field(..., min_length=8, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "newuser",
                "email": "user@example.com",
                "password": "securepassword123"
            }
        }


class VerifyEmailRequest(BaseModel):
    """Email verification request"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "code": "123456"
            }
        }


class ResendVerificationRequest(BaseModel):
    """Resend verification code request"""
    email: EmailStr


class GoogleAuthRequest(BaseModel):
    """Google OAuth request"""
    credential: str = Field(..., description="Google OAuth credential token")

    class Config:
        json_schema_extra = {
            "example": {
                "credential": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class SSORequest(BaseModel):
    """Corporate SSO request"""
    email: EmailStr = Field(..., description="Corporate email address")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@company.com"
            }
        }


class RegisterResponse(BaseModel):
    """Registration response"""
    user_id: str
    email: str
    message: str = "인증 코드가 이메일로 발송되었습니다."
    verification_required: bool = True


class TokenResponse(BaseModel):
    """Token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token expiry in seconds")
    refresh_token: str


class RefreshRequest(BaseModel):
    """Token refresh request"""
    refresh_token: str


class UserInfo(BaseModel):
    """User information"""
    id: str
    username: str
    role: str = "user"
    is_active: bool = True
