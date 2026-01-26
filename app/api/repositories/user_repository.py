"""
User Repository Interface
Repository for user management operations.
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from .base import BaseRepository, Entity, EntityId


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class UserRole(str, Enum):
    """User role"""
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


@dataclass
class UserPreferences:
    """User preferences"""
    theme: str = "light"
    language: str = "en"
    timezone: str = "UTC"
    notifications_enabled: bool = True
    email_notifications: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": self.theme,
            "language": self.language,
            "timezone": self.timezone,
            "notifications_enabled": self.notifications_enabled,
            "email_notifications": self.email_notifications
        }


@dataclass
class UserEntity(Entity):
    """User entity"""
    email: str = ""
    username: str = ""
    password_hash: str = ""

    # Profile
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None

    # Status
    status: UserStatus = UserStatus.ACTIVE
    role: UserRole = UserRole.USER

    # Verification
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None

    # Security
    mfa_enabled: bool = False
    mfa_secret: Optional[str] = None
    last_login_at: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None

    # Preferences
    preferences: UserPreferences = field(default_factory=UserPreferences)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Override to exclude sensitive fields"""
        result = super().to_dict()
        # Remove sensitive fields
        result.pop("password_hash", None)
        result.pop("mfa_secret", None)
        return result

    def to_public_dict(self) -> Dict[str, Any]:
        """Get public profile info only"""
        return {
            "id": str(self.id),
            "username": self.username,
            "display_name": self.display_name or self.username,
            "avatar_url": self.avatar_url,
            "bio": self.bio
        }


class UserRepository(BaseRepository[UserEntity]):
    """
    Repository interface for user operations.
    """

    # ==================== User Lookup ====================

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        """Get user by email"""
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[UserEntity]:
        """Get user by username"""
        pass

    @abstractmethod
    async def get_by_emails(self, emails: List[str]) -> List[UserEntity]:
        """Get multiple users by email"""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int = 20
    ) -> List[UserEntity]:
        """Search users by username, email, or display name"""
        pass

    # ==================== Authentication ====================

    @abstractmethod
    async def verify_password(
        self,
        email: str,
        password: str
    ) -> Optional[UserEntity]:
        """Verify password and return user if valid"""
        pass

    @abstractmethod
    async def update_password(
        self,
        user_id: EntityId,
        new_password_hash: str
    ) -> bool:
        """Update user password"""
        pass

    @abstractmethod
    async def record_login(
        self,
        user_id: EntityId,
        success: bool,
        ip_address: Optional[str] = None
    ) -> None:
        """Record login attempt"""
        pass

    @abstractmethod
    async def lock_account(
        self,
        user_id: EntityId,
        until: datetime
    ) -> bool:
        """Lock user account until specified time"""
        pass

    @abstractmethod
    async def unlock_account(self, user_id: EntityId) -> bool:
        """Unlock user account"""
        pass

    # ==================== Email Verification ====================

    @abstractmethod
    async def mark_email_verified(self, user_id: EntityId) -> bool:
        """Mark email as verified"""
        pass

    @abstractmethod
    async def get_unverified_users(
        self,
        older_than_days: int = 7
    ) -> List[UserEntity]:
        """Get users with unverified emails"""
        pass

    # ==================== MFA ====================

    @abstractmethod
    async def enable_mfa(
        self,
        user_id: EntityId,
        secret: str
    ) -> bool:
        """Enable MFA for user"""
        pass

    @abstractmethod
    async def disable_mfa(self, user_id: EntityId) -> bool:
        """Disable MFA for user"""
        pass

    @abstractmethod
    async def get_mfa_secret(self, user_id: EntityId) -> Optional[str]:
        """Get MFA secret for verification"""
        pass

    # ==================== Status Management ====================

    @abstractmethod
    async def update_status(
        self,
        user_id: EntityId,
        status: UserStatus
    ) -> bool:
        """Update user status"""
        pass

    @abstractmethod
    async def update_role(
        self,
        user_id: EntityId,
        role: UserRole
    ) -> bool:
        """Update user role"""
        pass

    @abstractmethod
    async def get_by_status(
        self,
        status: UserStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[UserEntity]:
        """Get users by status"""
        pass

    @abstractmethod
    async def get_by_role(
        self,
        role: UserRole,
        skip: int = 0,
        limit: int = 100
    ) -> List[UserEntity]:
        """Get users by role"""
        pass

    # ==================== Preferences ====================

    @abstractmethod
    async def update_preferences(
        self,
        user_id: EntityId,
        preferences: Dict[str, Any]
    ) -> bool:
        """Update user preferences"""
        pass

    @abstractmethod
    async def get_preferences(
        self,
        user_id: EntityId
    ) -> Optional[UserPreferences]:
        """Get user preferences"""
        pass

    # ==================== Statistics ====================

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get user statistics"""
        pass

    @abstractmethod
    async def get_active_users(
        self,
        since: datetime
    ) -> int:
        """Get count of active users since date"""
        pass
