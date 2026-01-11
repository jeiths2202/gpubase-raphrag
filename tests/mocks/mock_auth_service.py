"""
Mock Auth Service

Provides JWT authentication without external validation.
For local testing only.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from jose import jwt
import hashlib


class MockAuthService:
    """
    Mock authentication service for testing.

    Features:
    - In-memory user storage
    - JWT token generation and validation
    - Password hashing (simplified for tests)
    - No external dependencies
    """

    # Test secret key (only for testing)
    JWT_SECRET = "test-secret-key-minimum-32-characters-for-testing"
    JWT_ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    REFRESH_TOKEN_EXPIRE_DAYS = 7

    def __init__(self):
        # In-memory user storage
        self._users: Dict[str, Dict[str, Any]] = {
            "testuser": {
                "id": "user_001",
                "username": "testuser",
                "email": "test@example.com",
                "password_hash": self._hash_password("testpass123"),
                "role": "user",
                "is_active": True,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "admin": {
                "id": "user_admin",
                "username": "admin",
                "email": "admin@example.com",
                "password_hash": self._hash_password("adminpass123"),
                "role": "admin",
                "is_active": True,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        self._tokens: Dict[str, str] = {}  # refresh_token -> user_id
        self._call_history: list = []

    def _hash_password(self, password: str) -> str:
        """Simple password hashing for tests"""
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        return self._hash_password(password) == password_hash

    async def authenticate(
        self,
        username: str,
        password: str
    ) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with username and password.

        Returns user dict if successful, None otherwise.
        """
        self._call_history.append({
            "method": "authenticate",
            "username": username,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        user = self._users.get(username)
        if not user:
            return None

        if not self._verify_password(password, user["password_hash"]):
            return None

        if not user.get("is_active", False):
            return None

        return {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
        }

    async def create_access_token(self, user: Dict[str, Any]) -> str:
        """Create JWT access token"""
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": user["id"],
            "username": user["username"],
            "role": user.get("role", "user"),
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access"
        }

        return jwt.encode(payload, self.JWT_SECRET, algorithm=self.JWT_ALGORITHM)

    async def create_refresh_token(self, user: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        expire = datetime.now(timezone.utc) + timedelta(days=self.REFRESH_TOKEN_EXPIRE_DAYS)

        payload = {
            "sub": user["id"],
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "refresh"
        }

        token = jwt.encode(payload, self.JWT_SECRET, algorithm=self.JWT_ALGORITHM)
        self._tokens[token] = user["id"]

        return token

    async def verify_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify refresh token and return user"""
        try:
            payload = jwt.decode(token, self.JWT_SECRET, algorithms=[self.JWT_ALGORITHM])

            if payload.get("type") != "refresh":
                return None

            user_id = payload.get("sub")

            # Find user by ID
            for user in self._users.values():
                if user["id"] == user_id:
                    return {
                        "id": user["id"],
                        "username": user["username"],
                        "email": user["email"],
                        "role": user["role"],
                        "is_active": user["is_active"],
                    }

            return None

        except Exception:
            return None

    async def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify access token and return user info"""
        try:
            payload = jwt.decode(token, self.JWT_SECRET, algorithms=[self.JWT_ALGORITHM])

            if payload.get("type") != "access":
                return None

            return {
                "id": payload.get("sub"),
                "username": payload.get("username"),
                "role": payload.get("role", "user"),
                "is_active": True,
            }

        except Exception:
            return None

    async def register(
        self,
        username: str,
        email: str,
        password: str
    ) -> Dict[str, Any]:
        """Register a new user"""
        self._call_history.append({
            "method": "register",
            "username": username,
            "email": email,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        if username in self._users:
            raise ValueError("Username already exists")

        # Check email uniqueness
        for user in self._users.values():
            if user["email"] == email:
                raise ValueError("Email already exists")

        user_id = f"user_{len(self._users) + 1:03d}"

        user = {
            "id": user_id,
            "username": username,
            "email": email,
            "password_hash": self._hash_password(password),
            "role": "user",
            "is_active": True,
            "is_verified": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._users[username] = user

        return {
            "id": user_id,
            "username": username,
            "email": email,
            "message": "User registered successfully"
        }

    async def logout(self, refresh_token: str) -> bool:
        """Logout user by invalidating refresh token"""
        if refresh_token in self._tokens:
            del self._tokens[refresh_token]
            return True
        return False

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        for user in self._users.values():
            if user["id"] == user_id:
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "is_active": user["is_active"],
                }
        return None

    # ==================== Test Helpers ====================

    def add_test_user(
        self,
        username: str,
        password: str,
        email: str = None,
        role: str = "user"
    ) -> Dict[str, Any]:
        """Add a test user for testing purposes"""
        user_id = f"user_{len(self._users) + 1:03d}"

        user = {
            "id": user_id,
            "username": username,
            "email": email or f"{username}@test.com",
            "password_hash": self._hash_password(password),
            "role": role,
            "is_active": True,
            "is_verified": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._users[username] = user
        return user

    def get_call_history(self) -> list:
        """Get call history for assertions"""
        return self._call_history

    def reset(self) -> None:
        """Reset mock state"""
        self._tokens.clear()
        self._call_history.clear()
        # Keep default test users
        self._users = {
            "testuser": self._users.get("testuser", {
                "id": "user_001",
                "username": "testuser",
                "email": "test@example.com",
                "password_hash": self._hash_password("testpass123"),
                "role": "user",
                "is_active": True,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }),
            "admin": self._users.get("admin", {
                "id": "user_admin",
                "username": "admin",
                "email": "admin@example.com",
                "password_hash": self._hash_password("adminpass123"),
                "role": "admin",
                "is_active": True,
                "is_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }),
        }
