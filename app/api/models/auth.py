"""
Authentication Pydantic models
"""
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, field_validator, ConfigDict
from datetime import datetime


class UserRole(str, Enum):
    """User role hierarchy for permission control"""
    ADMIN = "admin"      # Full system access
    LEADER = "leader"    # Review permission + user management
    SENIOR = "senior"    # Review permission
    USER = "user"        # Knowledge registration permission
    GUEST = "guest"      # Read-only access


# Role hierarchy for permission checks
ROLE_HIERARCHY = {
    UserRole.ADMIN: 5,
    UserRole.LEADER: 4,
    UserRole.SENIOR: 3,
    UserRole.USER: 2,
    UserRole.GUEST: 1
}


def has_permission(user_role: str, required_role: str) -> bool:
    """Check if user has required permission level"""
    try:
        user_level = ROLE_HIERARCHY.get(UserRole(user_role), 0)
        required_level = ROLE_HIERARCHY.get(UserRole(required_role), 0)
        return user_level >= required_level
    except ValueError:
        return False


def can_review(user_role: str) -> bool:
    """Check if user can review knowledge articles"""
    return has_permission(user_role, UserRole.SENIOR)


class LoginRequest(BaseModel):
    """Login request"""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "username": "admin",
                "password": "password123"
            }
        })


class RegisterRequest(BaseModel):
    """User registration request"""
    user_id: str = Field(..., min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    email: EmailStr = Field(..., description="Email for verification")
    password: str = Field(..., min_length=8, max_length=100)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "user_id": "newuser",
                "email": "user@example.com",
                "password": "SecurePassword123!"
            }
        })

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        """
        Validate password strength for registration

        Requirements:
        - Minimum 8 characters
        - At least one uppercase, lowercase, number, special char
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/" for c in v)

        if not (has_upper and has_lower and has_digit and has_special):
            raise ValueError(
                "Password must contain at least one uppercase, "
                "lowercase, number, and special character"
            )

        return v


class VerifyEmailRequest(BaseModel):
    """Email verification request"""
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "email": "user@example.com",
                "code": "123456"
            }
        })


class ResendVerificationRequest(BaseModel):
    """Resend verification code request"""
    email: EmailStr


class GoogleAuthRequest(BaseModel):
    """Google OAuth request"""
    credential: str = Field(..., description="Google OAuth credential token")

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "credential": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        })


class SSORequest(BaseModel):
    """Corporate SSO request"""
    email: EmailStr = Field(..., description="Corporate email address")

    model_config = ConfigDict(json_schema_extra={
            "example": {
                "email": "user@company.com"
            }
        })


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
    email: Optional[str] = None
    role: UserRole = UserRole.USER
    department: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None

    def can_review(self) -> bool:
        """Check if user can review knowledge articles"""
        return has_permission(self.role, UserRole.SENIOR)

    def is_reviewer(self) -> bool:
        """Check if user is senior or above"""
        return self.role in [UserRole.ADMIN, UserRole.LEADER, UserRole.SENIOR]


class UserUpdateRequest(BaseModel):
    """User update request for admin"""
    role: Optional[UserRole] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None


class UserListResponse(BaseModel):
    """User list response"""
    users: List[UserInfo]
    total: int
    page: int
    limit: int
