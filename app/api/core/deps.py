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
    """Mock Auth Service"""

    async def authenticate(self, username: str, password: str) -> dict:
        # TODO: Implement proper authentication
        if username == "admin" and password == "admin123":
            return {
                "id": "user_admin",
                "username": "admin",
                "role": "admin"
            }
        return None

    async def create_access_token(self, user: dict) -> str:
        expire = datetime.utcnow() + timedelta(minutes=api_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": user["id"],
            "username": user["username"],
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
