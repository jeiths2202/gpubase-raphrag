"""
Dependency Injection for FastAPI
"""
from typing import Optional
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from .config import api_settings

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    Validate JWT token and return current user.
    For development, returns a mock user if no token is provided.
    """
    # Development mode: allow requests without token
    if credentials is None:
        if api_settings.DEBUG:
            return {
                "id": "dev_user",
                "username": "developer",
                "role": "admin",
                "is_active": True
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "인증이 필요합니다."},
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        token = credentials.credentials
        payload = jwt.decode(
            token,
            api_settings.JWT_SECRET_KEY,
            algorithms=[api_settings.JWT_ALGORITHM]
        )

        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AUTH_INVALID_TOKEN", "message": "유효하지 않은 토큰입니다."}
            )

        # Check expiration
        exp = payload.get("exp")
        if exp and datetime.utcnow() > datetime.fromtimestamp(exp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AUTH_TOKEN_EXPIRED", "message": "토큰이 만료되었습니다."}
            )

        return {
            "id": user_id,
            "username": payload.get("username", ""),
            "role": payload.get("role", "user"),
            "is_active": True
        }

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_INVALID_TOKEN", "message": "유효하지 않은 토큰입니다."}
        )


async def get_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Require admin role"""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AUTH_INSUFFICIENT_PERMISSION", "message": "관리자 권한이 필요합니다."}
        )
    return current_user


# Service Dependencies
# Import actual service implementations
from ..services.rag_service import RAGService, get_rag_service as _get_rag_service
from ..services.stats_service import StatsService, get_stats_service as _get_stats_service
from ..services.health_service import HealthService, get_health_service as _get_health_service


class DocumentService:
    """Mock Document Service"""

    async def list_documents(self, page: int, limit: int,
                            search: str = None, status: str = None) -> dict:
        return {"documents": [], "total": 0}

    async def upload_document(self, file_content: bytes, filename: str,
                             display_name: str = None, language: str = "auto",
                             tags: list = None) -> dict:
        import uuid
        return {
            "document_id": f"doc_{uuid.uuid4().hex[:12]}",
            "filename": filename,
            "task_id": f"task_{uuid.uuid4().hex[:12]}"
        }

    async def get_upload_status(self, task_id: str) -> dict:
        return None

    async def get_document(self, document_id: str) -> dict:
        return None

    async def delete_document(self, document_id: str) -> dict:
        return None

    async def get_document_chunks(self, document_id: str, page: int, limit: int) -> dict:
        return None


class HistoryService:
    """Mock History Service"""

    async def list_history(self, user_id: str, page: int, limit: int, **filters) -> dict:
        return {"history": [], "total": 0}

    async def get_history_detail(self, query_id: str) -> dict:
        return None

    async def delete_history(self, query_id: str) -> bool:
        return False

    async def list_conversations(self, user_id: str, page: int, limit: int) -> dict:
        return {"conversations": [], "total": 0}

    async def create_conversation(self, user_id: str, title: str) -> dict:
        import uuid
        from datetime import datetime
        return {
            "id": f"conv_{uuid.uuid4().hex[:12]}",
            "title": title,
            "queries_count": 0,
            "last_query_at": None,
            "created_at": datetime.utcnow()
        }

    async def delete_conversation(self, conversation_id: str) -> dict:
        return None




class SettingsService:
    """Mock Settings Service"""

    async def get_settings(self) -> dict:
        return {
            "rag": {
                "default_strategy": "auto",
                "top_k": 5,
                "vector_weight": 0.5,
                "chunk_size": 1000,
                "chunk_overlap": 200
            },
            "llm": {
                "temperature": 0.1,
                "max_tokens": 2048
            },
            "ui": {
                "language": "auto",
                "theme": "dark",
                "show_sources": True
            }
        }

    async def update_settings(self, updates: dict) -> bool:
        return True


class AuthService:
    """Auth Service with registration and email verification"""

    # In-memory storage (replace with database in production)
    _users: dict = {
        "admin": {
            "id": "user_admin",
            "username": "admin",
            "email": "admin@system.local",
            "password_hash": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",  # sha256("admin")
            "role": "admin",
            "is_verified": True,
            "created_at": "2025-01-01T00:00:00Z",
            "is_active": True
        }
    }
    _pending_verifications: dict = {}  # email -> {code, user_data, expires_at}
    _verified_emails: set = {"admin@system.local"}

    async def authenticate(self, username: str, password: str) -> dict:
        """Authenticate user with username and password"""
        import hashlib

        # Check registered users
        if username in self._users:
            user = self._users[username]
            hashed = hashlib.sha256(password.encode()).hexdigest()
            if user["password_hash"] == hashed and user.get("is_verified", False):
                if not user.get("is_active", True):
                    return None  # User is deactivated
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user.get("role", "user")
                }
        return None

    async def register_user(self, user_id: str, email: str, password: str) -> dict:
        """Register a new user and send verification email"""
        import hashlib
        import random
        import uuid

        # Check if user_id already exists
        if user_id in self._users:
            return {"error": "USER_EXISTS", "message": "이미 존재하는 사용자 ID입니다."}

        # Check if email already registered
        for u in self._users.values():
            if u["email"] == email:
                return {"error": "EMAIL_EXISTS", "message": "이미 등록된 이메일입니다."}

        # Generate verification code
        verification_code = str(random.randint(100000, 999999))

        # Hash password
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Store pending verification
        self._pending_verifications[email] = {
            "code": verification_code,
            "user_data": {
                "id": f"user_{uuid.uuid4().hex[:12]}",
                "username": user_id,
                "email": email,
                "password_hash": password_hash,
                "role": "user",
                "is_verified": False
            },
            "expires_at": datetime.utcnow() + timedelta(minutes=10)
        }

        # Send verification email (mock for now)
        await self._send_verification_email(email, verification_code)

        return {
            "success": True,
            "user_id": user_id,
            "email": email,
            "message": "인증 코드가 이메일로 발송되었습니다."
        }

    async def verify_email(self, email: str, code: str) -> dict:
        """Verify email with code"""
        if email not in self._pending_verifications:
            return {"error": "NO_PENDING", "message": "인증 대기 중인 이메일이 없습니다."}

        pending = self._pending_verifications[email]

        # Check expiration
        if datetime.utcnow() > pending["expires_at"]:
            del self._pending_verifications[email]
            return {"error": "CODE_EXPIRED", "message": "인증 코드가 만료되었습니다."}

        # Verify code
        if pending["code"] != code:
            return {"error": "INVALID_CODE", "message": "잘못된 인증 코드입니다."}

        # Create user
        user_data = pending["user_data"]
        user_data["is_verified"] = True
        self._users[user_data["username"]] = user_data
        self._verified_emails.add(email)

        # Clean up
        del self._pending_verifications[email]

        return {
            "success": True,
            "user": {
                "id": user_data["id"],
                "username": user_data["username"],
                "email": user_data["email"],
                "role": user_data["role"]
            }
        }

    async def resend_verification(self, email: str) -> dict:
        """Resend verification code"""
        import random

        if email not in self._pending_verifications:
            return {"error": "NO_PENDING", "message": "인증 대기 중인 이메일이 없습니다."}

        # Generate new code
        new_code = str(random.randint(100000, 999999))
        self._pending_verifications[email]["code"] = new_code
        self._pending_verifications[email]["expires_at"] = datetime.utcnow() + timedelta(minutes=10)

        # Send email
        await self._send_verification_email(email, new_code)

        return {"success": True, "message": "새 인증 코드가 발송되었습니다."}

    async def _send_verification_email(self, email: str, code: str) -> bool:
        """Send verification email (mock implementation)"""
        # TODO: Implement actual email sending (SMTP, SendGrid, etc.)
        print(f"[EMAIL] Sending verification code {code} to {email}")
        return True

    async def authenticate_google(self, credential: str) -> dict:
        """Authenticate with Google OAuth"""
        # TODO: Implement Google token verification
        # For now, decode and mock the response
        try:
            # In production, verify with Google's API
            # from google.oauth2 import id_token
            # from google.auth.transport import requests
            # idinfo = id_token.verify_oauth2_token(credential, requests.Request(), GOOGLE_CLIENT_ID)

            # Mock response for development
            import uuid
            return {
                "id": f"google_{uuid.uuid4().hex[:12]}",
                "username": "google_user",
                "email": "user@gmail.com",
                "role": "user",
                "provider": "google"
            }
        except Exception:
            return None

    async def initiate_sso(self, email: str) -> dict:
        """Initiate corporate SSO flow"""
        # Check if corporate email
        domain = email.split("@")[1].lower() if "@" in email else ""
        corp_domains = ["company.com", "company.co.kr"]

        if domain not in corp_domains:
            return {"error": "NOT_CORPORATE", "message": "회사 이메일이 아닙니다."}

        # TODO: Implement actual SSO (SAML/OIDC) flow
        # For now, return SSO URL mock
        import uuid
        return {
            "success": True,
            "sso_url": f"/auth/sso/callback?token={uuid.uuid4().hex}",
            "message": "SSO 인증 페이지로 이동합니다."
        }

    async def create_access_token(self, user: dict) -> str:
        expire = datetime.utcnow() + timedelta(minutes=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": user["id"],
            "username": user["username"],
            "email": user.get("email", ""),
            "role": user.get("role", "user"),
            "exp": expire
        }
        return jwt.encode(payload, api_settings.JWT_SECRET_KEY, algorithm=api_settings.JWT_ALGORITHM)

    async def create_refresh_token(self, user: dict) -> str:
        expire = datetime.utcnow() + timedelta(days=api_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": user["id"],
            "type": "refresh",
            "exp": expire
        }
        return jwt.encode(payload, api_settings.JWT_SECRET_KEY, algorithm=api_settings.JWT_ALGORITHM)

    async def verify_refresh_token(self, token: str) -> dict:
        try:
            payload = jwt.decode(token, api_settings.JWT_SECRET_KEY, algorithms=[api_settings.JWT_ALGORITHM])
            if payload.get("type") != "refresh":
                return None
            return {"id": payload.get("sub"), "username": "", "role": "user"}
        except JWTError:
            return None

    async def invalidate_tokens(self, user_id: str) -> bool:
        # TODO: Implement token blacklist
        return True

    # User Management Methods (Admin)
    async def list_users(self, page: int = 1, limit: int = 20, search: str = None) -> dict:
        """List all users with pagination"""
        users_list = []
        for username, user in self._users.items():
            if search and search.lower() not in username.lower() and search.lower() not in user.get("email", "").lower():
                continue
            users_list.append({
                "id": user["id"],
                "username": user["username"],
                "email": user.get("email", ""),
                "role": user.get("role", "user"),
                "is_active": user.get("is_active", True),
                "is_verified": user.get("is_verified", False),
                "created_at": user.get("created_at", "")
            })

        total = len(users_list)
        start = (page - 1) * limit
        end = start + limit
        paginated = users_list[start:end]

        return {
            "users": paginated,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }

    async def get_user(self, user_id: str) -> dict:
        """Get user by ID"""
        for user in self._users.values():
            if user["id"] == user_id:
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user.get("email", ""),
                    "role": user.get("role", "user"),
                    "is_active": user.get("is_active", True),
                    "is_verified": user.get("is_verified", False),
                    "created_at": user.get("created_at", "")
                }
        return None

    async def update_user(self, user_id: str, updates: dict) -> dict:
        """Update user details"""
        for username, user in self._users.items():
            if user["id"] == user_id:
                # Update allowed fields
                if "role" in updates:
                    user["role"] = updates["role"]
                if "is_active" in updates:
                    user["is_active"] = updates["is_active"]
                if "email" in updates:
                    user["email"] = updates["email"]

                self._users[username] = user
                return {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user.get("email", ""),
                    "role": user.get("role", "user"),
                    "is_active": user.get("is_active", True),
                    "is_verified": user.get("is_verified", False)
                }
        return None

    async def delete_user(self, user_id: str) -> bool:
        """Delete user by ID"""
        for username, user in list(self._users.items()):
            if user["id"] == user_id:
                # Prevent deleting admin
                if user.get("role") == "admin" and username == "admin":
                    return False
                del self._users[username]
                return True
        return False

    async def get_user_stats(self) -> dict:
        """Get user statistics for dashboard"""
        total_users = len(self._users)
        active_users = sum(1 for u in self._users.values() if u.get("is_active", True))
        admin_users = sum(1 for u in self._users.values() if u.get("role") == "admin")
        pending_verification = len(self._pending_verifications)

        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "admin_users": admin_users,
            "regular_users": total_users - admin_users,
            "pending_verification": pending_verification
        }


# Dependency injection functions
def get_rag_service() -> RAGService:
    """Get RAG service instance (real implementation)"""
    return _get_rag_service()


def get_document_service() -> DocumentService:
    return DocumentService()


def get_history_service() -> HistoryService:
    return HistoryService()


def get_stats_service() -> StatsService:
    """Get stats service instance (real implementation)"""
    return _get_stats_service()


def get_settings_service() -> SettingsService:
    return SettingsService()


def get_auth_service() -> AuthService:
    return AuthService()


def get_health_service() -> HealthService:
    """Get health service instance (real implementation)"""
    return _get_health_service()
