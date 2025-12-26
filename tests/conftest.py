"""
Pytest Configuration and Shared Fixtures

Provides common fixtures for backend testing without
external dependencies (GPU, databases, external APIs).
"""
import os
import sys
import pytest
from typing import Generator, Dict, Any
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables before importing app modules
os.environ["APP_ENV"] = "testing"
os.environ["DEBUG"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-minimum-32-characters-for-testing"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"


# ==================== Mock Service Fixtures ====================

@pytest.fixture
def mock_auth_service():
    """Provide mock auth service"""
    from tests.mocks import MockAuthService
    service = MockAuthService()
    yield service
    service.reset()


@pytest.fixture
def mock_rag_service():
    """Provide mock RAG service"""
    from tests.mocks import MockRAGService
    service = MockRAGService()
    yield service
    service.reset()


@pytest.fixture
def mock_document_service():
    """Provide mock document service"""
    from tests.mocks import MockDocumentService
    service = MockDocumentService()
    yield service
    service.reset()


# ==================== Adapter Fixtures ====================

@pytest.fixture
def mock_llm_adapter():
    """Provide mock LLM adapter"""
    from app.api.adapters.mock import MockLLMAdapter
    adapter = MockLLMAdapter(simulate_delay=False)
    yield adapter
    adapter.reset()


@pytest.fixture
def mock_embedding_adapter():
    """Provide mock embedding adapter"""
    from app.api.adapters.mock import MockEmbeddingAdapter
    adapter = MockEmbeddingAdapter()
    yield adapter


@pytest.fixture
def mock_vector_store_adapter():
    """Provide mock vector store adapter"""
    from app.api.adapters.mock import MockVectorStoreAdapter
    adapter = MockVectorStoreAdapter()
    yield adapter


@pytest.fixture
def mock_graph_store_adapter():
    """Provide mock graph store adapter"""
    from app.api.adapters.mock import MockGraphStoreAdapter
    adapter = MockGraphStoreAdapter()
    yield adapter


# ==================== FastAPI Test Client ====================

@pytest.fixture
def test_app():
    """Create test FastAPI application with mocked dependencies"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.main import app

    # Override settings for testing
    app.state.testing = True

    return app


@pytest.fixture
def client(test_app) -> Generator:
    """Provide FastAPI test client"""
    from fastapi.testclient import TestClient

    with TestClient(test_app) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client, mock_auth_service) -> Generator:
    """Provide authenticated test client"""
    import asyncio

    # Create access token for test user
    user = {
        "id": "user_001",
        "username": "testuser",
        "role": "user"
    }
    token = asyncio.get_event_loop().run_until_complete(
        mock_auth_service.create_access_token(user)
    )

    # Add authorization header
    client.headers["Authorization"] = f"Bearer {token}"

    yield client


@pytest.fixture
def admin_client(client, mock_auth_service) -> Generator:
    """Provide admin authenticated test client"""
    import asyncio

    # Create access token for admin user
    user = {
        "id": "user_admin",
        "username": "admin",
        "role": "admin"
    }
    token = asyncio.get_event_loop().run_until_complete(
        mock_auth_service.create_access_token(user)
    )

    # Add authorization header
    client.headers["Authorization"] = f"Bearer {token}"

    yield client


# ==================== Test Data Fixtures ====================

@pytest.fixture
def sample_user() -> Dict[str, Any]:
    """Provide sample user data"""
    return {
        "id": "user_test_001",
        "username": "testuser",
        "email": "testuser@example.com",
        "role": "user",
        "is_active": True,
    }


@pytest.fixture
def sample_admin_user() -> Dict[str, Any]:
    """Provide sample admin user data"""
    return {
        "id": "user_admin_001",
        "username": "admin",
        "email": "admin@example.com",
        "role": "admin",
        "is_active": True,
    }


@pytest.fixture
def sample_document() -> Dict[str, Any]:
    """Provide sample document data"""
    return {
        "id": "doc_test_001",
        "filename": "test_document.pdf",
        "original_name": "Test Document.pdf",
        "file_size": 1024000,
        "mime_type": "application/pdf",
        "document_type": "pdf",
        "status": "completed",
        "chunks_count": 10,
        "language": "en",
        "created_at": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_query() -> Dict[str, str]:
    """Provide sample query data"""
    return {
        "query": "What is machine learning?",
        "language": "en",
    }


@pytest.fixture
def sample_korean_query() -> Dict[str, str]:
    """Provide sample Korean query data"""
    return {
        "query": "이 차트를 분석해주세요",
        "language": "ko",
    }


@pytest.fixture
def sample_visual_query() -> Dict[str, str]:
    """Provide sample visual query data"""
    return {
        "query": "Analyze this chart and explain the trends",
        "language": "en",
    }


# ==================== Model Fixtures ====================

@pytest.fixture
def document_visual_profile():
    """Provide sample DocumentVisualProfile"""
    from app.api.models.vision import DocumentVisualProfile

    return DocumentVisualProfile(
        document_id="doc_visual_001",
        mime_type="application/pdf",
        extension=".pdf",
        image_count=5,
        has_charts=True,
        has_tables=True,
        visual_complexity_score=0.7,
    )


@pytest.fixture
def routing_decision():
    """Provide sample RoutingDecision"""
    from app.api.models.vision import RoutingDecision

    return RoutingDecision(
        selected_llm="vision",
        reasoning="Visual content detected",
        confidence=0.85,
        query_type="hybrid",
    )


# ==================== Async Fixtures ====================

@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ==================== Environment Fixtures ====================

@pytest.fixture(autouse=True)
def test_environment():
    """Set up test environment variables"""
    original_env = os.environ.copy()

    # Set test environment
    os.environ["APP_ENV"] = "testing"
    os.environ["DEBUG"] = "false"
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-minimum-32-characters-for-testing"

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


# ==================== Cleanup Fixtures ====================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Clean up after each test"""
    yield
    # Add any cleanup logic here if needed


# ==================== Markers ====================

def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests (fast, no external deps)")
    config.addinivalue_line("markers", "integration: Integration tests (may require setup)")
    config.addinivalue_line("markers", "slow: Slow tests (optional, skipped by default)")
    config.addinivalue_line("markers", "vision: Vision-related tests")
    config.addinivalue_line("markers", "auth: Authentication tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
