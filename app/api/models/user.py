"""
User and AuthIdentity Database Models

PURPOSE:
- Separate Authentication (Google/SSO) from Internal User Management
- PostgreSQL is the SINGLE SOURCE OF TRUTH for user identity
- Workspace ownership based on internal user_id, NOT provider IDs

DESIGN PRINCIPLES:
1. Authentication (AuthN) resolves to internal user_id
2. Authorization (AuthZ) uses internal user role
3. Workspace/Document ownership uses internal user_id
4. Multiple auth providers can map to single internal user
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, validator
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class UserRole(str, Enum):
    """
    User role hierarchy for permission control

    ADMIN: Full system access (admin panel, user management, all operations)
    LEADER: Review permission + user management
    SENIOR: Review permission for knowledge articles
    USER: Knowledge registration permission (default for new users)
    GUEST: Read-only access
    """
    ADMIN = "admin"
    LEADER = "leader"
    SENIOR = "senior"
    USER = "user"
    GUEST = "guest"


class UserStatus(str, Enum):
    """
    User account status

    PENDING: Email verification pending (new users)
    ACTIVE: Normal operation
    INACTIVE: Temporarily disabled (no login)
    SUSPENDED: Temporary ban (violated policy)
    """
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class AuthProvider(str, Enum):
    """
    Supported authentication providers

    LOCAL: Username/password authentication
    GOOGLE: Google OAuth
    SSO: Corporate SSO (SAML/OIDC)
    MICROSOFT: Microsoft OAuth (future)
    GITHUB: GitHub OAuth (future)
    """
    LOCAL = "local"
    GOOGLE = "google"
    SSO = "sso"
    MICROSOFT = "microsoft"
    GITHUB = "github"


# ============================================================================
# INTERNAL USER MODELS (PostgreSQL-backed)
# ============================================================================

class UserBase(BaseModel):
    """Base user model with common fields"""
    email: EmailStr
    display_name: Optional[str] = None
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.ACTIVE
    department: Optional[str] = None
    language: str = Field(default="ko", pattern="^(ko|en|ja)$")


class UserCreate(UserBase):
    """
    Create new user (internal use only)

    NOTE: External authentication (Google/SSO) uses get_or_create_user_from_auth()
    This model is for manual user creation by admin
    """
    password: Optional[str] = Field(None, min_length=8)

    @validator('password')
    def validate_password_strength(cls, v, values):
        """
        Validate password strength for local authentication

        Requirements:
        - Minimum 8 characters
        - At least one uppercase, lowercase, number, special char
        """
        if v is None:
            # SSO-only user, no password required
            return v

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        # Check complexity (optional, can be enhanced)
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


class UserUpdate(BaseModel):
    """Update user information (admin operation)"""
    display_name: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    department: Optional[str] = None
    language: Optional[str] = Field(None, pattern="^(ko|en|ja)$")


class User(UserBase):
    """
    Complete user model (from database)

    IMPORTANT: This represents INTERNAL user identity
    - id: Internal UUID used for workspace/document ownership
    - email: Primary identifier
    - password_hash: NULL for SSO-only users
    - role: Authorization level
    - status: Account state
    """
    id: UUID
    password_hash: Optional[str] = None  # Internal use only, never expose
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserPublic(BaseModel):
    """
    Public user model (safe for API responses)

    SECURITY: Never expose password_hash or internal sensitive data
    """
    id: UUID
    email: str
    display_name: Optional[str]
    role: UserRole
    status: UserStatus
    department: Optional[str]
    language: str
    created_at: datetime
    last_login_at: Optional[datetime]

    # Helper methods
    def can_review(self) -> bool:
        """Check if user can review knowledge articles"""
        return self.role in [UserRole.ADMIN, UserRole.LEADER, UserRole.SENIOR]

    def is_admin(self) -> bool:
        """Check if user has admin privileges"""
        return self.role == UserRole.ADMIN


# ============================================================================
# AUTH IDENTITY MODELS (External Authentication Mapping)
# ============================================================================

class AuthIdentityCreate(BaseModel):
    """
    Create authentication identity mapping

    PURPOSE: Link external authentication (Google/SSO) to internal user
    """
    user_id: UUID
    provider: AuthProvider
    provider_user_id: str  # Google's 'sub' claim, SSO user ID, etc.
    email: Optional[EmailStr] = None
    provider_metadata: Optional[Dict[str, Any]] = None


class AuthIdentity(AuthIdentityCreate):
    """
    Complete authentication identity model

    DESIGN: One internal user can have MULTIPLE auth identities
    Example: user@company.com can login via:
    - Google OAuth (provider='google', provider_user_id='1234567890')
    - Corporate SSO (provider='sso', provider_user_id='user@company.com')
    - Local password (provider='local', provider_user_id=email)

    All three map to the SAME internal user_id for workspace ownership
    """
    id: UUID
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============================================================================
# AUTHENTICATION REQUEST/RESPONSE MODELS
# ============================================================================

class LocalLoginRequest(BaseModel):
    """
    Local authentication request (username/password)

    FIXED ADMIN CREDENTIALS:
    - ID: admin
    - Password: SecureAdm1nP@ss2024!
    """
    id: str = Field(..., description="User ID or email for login")
    password: str = Field(..., min_length=1)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "admin",
                "password": "SecureAdm1nP@ss2024!"
            }
        }


class ExternalAuthRequest(BaseModel):
    """External authentication request (Google/SSO)"""
    provider: AuthProvider
    credential: str = Field(..., description="OAuth token or SSO token")
    email: Optional[EmailStr] = None
    display_name: Optional[str] = None
    provider_metadata: Optional[Dict[str, Any]] = None


class AuthResponse(BaseModel):
    """
    Successful authentication response

    CRITICAL: JWT 'sub' claim MUST be the internal user.id (UUID)
    NEVER use provider_user_id for JWT sub claim
    """
    user: UserPublic
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str


# ============================================================================
# USER MANAGEMENT MODELS (Admin API)
# ============================================================================

class UserListResponse(BaseModel):
    """User list response for admin panel"""
    users: List[UserPublic]
    total: int
    page: int
    limit: int


class UserAuthMethodsSummary(BaseModel):
    """
    Summary of user's authentication methods

    Shows which providers user can use to login
    """
    user_id: UUID
    email: str
    display_name: Optional[str]
    auth_methods: List[AuthProvider]
    auth_method_count: int
    created_at: datetime
    last_login_at: Optional[datetime]


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def has_permission(user_role: UserRole, required_role: UserRole) -> bool:
    """
    Check if user has required permission level

    Role hierarchy: admin > leader > senior > user > guest
    """
    hierarchy = {
        UserRole.ADMIN: 5,
        UserRole.LEADER: 4,
        UserRole.SENIOR: 3,
        UserRole.USER: 2,
        UserRole.GUEST: 1
    }
    return hierarchy.get(user_role, 0) >= hierarchy.get(required_role, 0)


# ============================================================================
# COMMENTS (Design Documentation)
# ============================================================================

"""
DESIGN DECISION: Why separate users from auth_identities?

PROBLEM:
If we store user identity in auth_identities table:
- Workspace ownership breaks when user changes auth provider
- Cannot support multiple login methods for same user
- Provider-specific IDs leak into business logic

SOLUTION:
1. users table = INTERNAL identity (stable, owns workspaces)
2. auth_identities table = EXTERNAL authentication (can change, multiple)

FLOW:
1. User logs in via Google → authenticate_google()
2. Resolve Google 'sub' to internal user_id via auth_identities
3. Issue JWT with 'sub' = internal user_id (UUID)
4. All workspace/document queries use internal user_id
5. User can add SSO later → new auth_identity row, same user_id

BENEFITS:
- Stable workspace ownership (user_id never changes)
- Support multiple auth methods per user
- Provider changes don't break data relationships
- Clean separation of AuthN and AuthZ
"""
