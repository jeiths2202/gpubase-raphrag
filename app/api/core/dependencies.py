"""
FastAPI Dependencies
Clean dependency injection for FastAPI routes.
"""
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

from .container import Container, get_container
from ..repositories import (
    DocumentRepository,
    NoteRepository,
    ProjectRepository,
    UserRepository,
    HistoryRepository
)
from ..ports import (
    LLMPort,
    EmbeddingPort,
    VectorStorePort,
    GraphStorePort
)

# Security
security = HTTPBearer(auto_error=False)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-key")
JWT_ALGORITHM = "HS256"


# ==================== Authentication ====================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict[str, Any]:
    """
    Get current authenticated user.

    In development mode, returns a mock user if no token is provided.
    In production, validates JWT token.
    """
    container = get_container()

    # Development mode: allow requests without token
    if container.config.environment.value == "development":
        if not credentials:
            return {
                "user_id": "dev-user",
                "email": "dev@example.com",
                "role": "admin"
            }

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        return {
            "user_id": payload.get("sub"),
            "email": payload.get("email"),
            "role": payload.get("role", "user")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_admin_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Require admin role"""
    if current_user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ==================== Container ====================

def get_di_container() -> Container:
    """Get DI container as dependency"""
    return get_container()


# ==================== Repositories ====================

async def get_document_repository(
    container: Container = Depends(get_di_container)
) -> DocumentRepository:
    """Get document repository"""
    return container.document_repository


async def get_note_repository(
    container: Container = Depends(get_di_container)
) -> NoteRepository:
    """Get note repository"""
    return container.note_repository


async def get_project_repository(
    container: Container = Depends(get_di_container)
) -> ProjectRepository:
    """Get project repository"""
    return container.project_repository


async def get_user_repository(
    container: Container = Depends(get_di_container)
) -> UserRepository:
    """Get user repository"""
    return container.user_repository


async def get_history_repository(
    container: Container = Depends(get_di_container)
) -> HistoryRepository:
    """Get history repository"""
    return container.history_repository


# ==================== Ports ====================

async def get_llm(
    container: Container = Depends(get_di_container)
) -> LLMPort:
    """Get LLM port"""
    return container.llm


async def get_embedding(
    container: Container = Depends(get_di_container)
) -> EmbeddingPort:
    """Get embedding port"""
    return container.embedding


async def get_vector_store(
    container: Container = Depends(get_di_container)
) -> VectorStorePort:
    """Get vector store port"""
    return container.vector_store


async def get_graph_store(
    container: Container = Depends(get_di_container)
) -> GraphStorePort:
    """Get graph store port"""
    return container.graph_store


# ==================== Service Dependencies ====================

# Note: These are placeholders for when services are refactored
# to use the new architecture

async def get_rag_service(
    container: Container = Depends(get_di_container)
):
    """
    Get RAG service.

    Currently returns a compatibility wrapper that works with existing code.
    Will be replaced with a proper service using ports/adapters.
    """
    # Import here to avoid circular dependencies
    from ..services.rag_service import RAGService

    # Create RAG service with container dependencies
    # This is a transitional implementation
    return RAGService()


async def get_document_service(
    container: Container = Depends(get_di_container),
    document_repository: DocumentRepository = Depends(get_document_repository)
):
    """Get document service"""
    # Placeholder for document service
    # TODO: Implement DocumentService using repository
    return {
        "repository": document_repository,
        "container": container
    }


async def get_search_service(
    container: Container = Depends(get_di_container),
    vector_store: VectorStorePort = Depends(get_vector_store),
    embedding: EmbeddingPort = Depends(get_embedding)
):
    """Get search service"""
    # Placeholder for search service
    return {
        "vector_store": vector_store,
        "embedding": embedding
    }
