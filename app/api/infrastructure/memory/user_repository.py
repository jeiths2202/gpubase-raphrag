"""
In-Memory User Repository Implementation
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import hashlib

from .base import MemoryBaseRepository
from ...repositories.user_repository import (
    UserRepository,
    UserEntity,
    UserStatus,
    UserRole,
    UserPreferences
)
from ...repositories.base import EntityId


class MemoryUserRepository(MemoryBaseRepository[UserEntity], UserRepository):
    """In-memory user repository implementation"""

    def __init__(self):
        super().__init__()
        self._email_index: Dict[str, str] = {}  # email -> user_id
        self._username_index: Dict[str, str] = {}  # username -> user_id
        self._login_history: List[Dict[str, Any]] = []

    async def create(self, entity: UserEntity) -> UserEntity:
        """Override to maintain indexes"""
        result = await super().create(entity)
        self._email_index[entity.email.lower()] = str(entity.id)
        self._username_index[entity.username.lower()] = str(entity.id)
        return result

    async def delete(self, entity_id: EntityId) -> bool:
        """Override to clean up indexes"""
        user = await self.get_by_id(entity_id)
        if user:
            self._email_index.pop(user.email.lower(), None)
            self._username_index.pop(user.username.lower(), None)
        return await super().delete(entity_id)

    # ==================== User Lookup ====================

    async def get_by_email(self, email: str) -> Optional[UserEntity]:
        user_id = self._email_index.get(email.lower())
        if user_id:
            return await self.get_by_id(user_id)
        return None

    async def get_by_username(self, username: str) -> Optional[UserEntity]:
        user_id = self._username_index.get(username.lower())
        if user_id:
            return await self.get_by_id(user_id)
        return None

    async def get_by_emails(self, emails: List[str]) -> List[UserEntity]:
        users = []
        for email in emails:
            user = await self.get_by_email(email)
            if user:
                users.append(user)
        return users

    async def search(
        self,
        query: str,
        limit: int = 20
    ) -> List[UserEntity]:
        query_lower = query.lower()
        results = []

        for user in self._storage.values():
            if (query_lower in user.username.lower() or
                query_lower in user.email.lower() or
                (user.display_name and query_lower in user.display_name.lower())):
                results.append(user)

        return results[:limit]

    # ==================== Authentication ====================

    async def verify_password(
        self,
        email: str,
        password: str
    ) -> Optional[UserEntity]:
        user = await self.get_by_email(email)
        if not user:
            return None

        # Simple hash comparison (in production use bcrypt)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if user.password_hash == password_hash:
            return user

        return None

    async def update_password(
        self,
        user_id: EntityId,
        new_password_hash: str
    ) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.password_hash = new_password_hash
        user.updated_at = datetime.utcnow()
        return True

    async def record_login(
        self,
        user_id: EntityId,
        success: bool,
        ip_address: Optional[str] = None
    ) -> None:
        user = await self.get_by_id(user_id)
        if not user:
            return

        if success:
            user.last_login_at = datetime.utcnow()
            user.failed_login_attempts = 0
        else:
            user.failed_login_attempts += 1

        self._login_history.append({
            "user_id": str(user_id),
            "success": success,
            "ip_address": ip_address,
            "timestamp": datetime.utcnow()
        })

    async def lock_account(
        self,
        user_id: EntityId,
        until: datetime
    ) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.locked_until = until
        user.updated_at = datetime.utcnow()
        return True

    async def unlock_account(self, user_id: EntityId) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.locked_until = None
        user.failed_login_attempts = 0
        user.updated_at = datetime.utcnow()
        return True

    # ==================== Email Verification ====================

    async def mark_email_verified(self, user_id: EntityId) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.email_verified = True
        user.email_verified_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        return True

    async def get_unverified_users(
        self,
        older_than_days: int = 7
    ) -> List[UserEntity]:
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        return [
            u for u in self._storage.values()
            if not u.email_verified and u.created_at < cutoff
        ]

    # ==================== MFA ====================

    async def enable_mfa(
        self,
        user_id: EntityId,
        secret: str
    ) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.mfa_enabled = True
        user.mfa_secret = secret
        user.updated_at = datetime.utcnow()
        return True

    async def disable_mfa(self, user_id: EntityId) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.mfa_enabled = False
        user.mfa_secret = None
        user.updated_at = datetime.utcnow()
        return True

    async def get_mfa_secret(self, user_id: EntityId) -> Optional[str]:
        user = await self.get_by_id(user_id)
        return user.mfa_secret if user else None

    # ==================== Status Management ====================

    async def update_status(
        self,
        user_id: EntityId,
        status: UserStatus
    ) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.status = status
        user.updated_at = datetime.utcnow()
        return True

    async def update_role(
        self,
        user_id: EntityId,
        role: UserRole
    ) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        user.role = role
        user.updated_at = datetime.utcnow()
        return True

    async def get_by_status(
        self,
        status: UserStatus,
        skip: int = 0,
        limit: int = 100
    ) -> List[UserEntity]:
        users = [u for u in self._storage.values() if u.status == status]
        users.sort(key=lambda x: x.created_at, reverse=True)
        return users[skip:skip + limit]

    async def get_by_role(
        self,
        role: UserRole,
        skip: int = 0,
        limit: int = 100
    ) -> List[UserEntity]:
        users = [u for u in self._storage.values() if u.role == role]
        users.sort(key=lambda x: x.created_at, reverse=True)
        return users[skip:skip + limit]

    # ==================== Preferences ====================

    async def update_preferences(
        self,
        user_id: EntityId,
        preferences: Dict[str, Any]
    ) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False

        for key, value in preferences.items():
            if hasattr(user.preferences, key):
                setattr(user.preferences, key, value)

        user.updated_at = datetime.utcnow()
        return True

    async def get_preferences(
        self,
        user_id: EntityId
    ) -> Optional[UserPreferences]:
        user = await self.get_by_id(user_id)
        return user.preferences if user else None

    # ==================== Statistics ====================

    async def get_stats(self) -> Dict[str, Any]:
        users = list(self._storage.values())

        status_counts = {}
        for user in users:
            status = user.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        role_counts = {}
        for user in users:
            role = user.role.value
            role_counts[role] = role_counts.get(role, 0) + 1

        return {
            "total_users": len(users),
            "verified_users": len([u for u in users if u.email_verified]),
            "mfa_enabled": len([u for u in users if u.mfa_enabled]),
            "status_breakdown": status_counts,
            "role_breakdown": role_counts
        }

    async def get_active_users(
        self,
        since: datetime
    ) -> int:
        return len([
            u for u in self._storage.values()
            if u.last_login_at and u.last_login_at >= since
        ])
