"""
Authentication Pydantic models
"""
from pydantic import BaseModel, Field


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
