"""
Example Router Using Use Cases
Demonstrates how to use the Use Case pattern in FastAPI routes.

This is an EXAMPLE file showing the recommended pattern.
Actual implementation would be in the routers/ directory.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

from .base import UseCaseContext
from .mindmap import MindmapInput, MindmapOutput
from .query import QueryInput, QueryOutput
from .document import DocumentInput, DocumentOutput
from .factory import (
    get_generate_mindmap_use_case,
    get_execute_query_use_case,
    get_upload_document_use_case,
    GenerateMindmapUseCase,
    ExecuteQueryUseCase,
    UploadDocumentUseCase
)
from ..core.dependencies import get_current_user

router = APIRouter(prefix="/v2", tags=["Use Case Examples"])


# ==================== Request/Response Models ====================

class GenerateMindmapRequest(BaseModel):
    """Request for mindmap generation"""
    document_id: str = Field(..., description="Document ID to generate mindmap from")
    max_depth: int = Field(default=3, ge=1, le=5)
    max_nodes_per_level: int = Field(default=5, ge=1, le=10)
    language: str = Field(default="ko")
    focus_topics: Optional[List[str]] = None


class QueryRequest(BaseModel):
    """Request for RAG query"""
    question: str = Field(..., min_length=1, max_length=2000)
    strategy: str = Field(default="hybrid")
    top_k: int = Field(default=5, ge=1, le=20)
    session_id: Optional[str] = None


class UploadDocumentRequest(BaseModel):
    """Request for document upload"""
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=10)
    project_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


# ==================== Endpoints ====================

@router.post("/mindmap/generate")
async def generate_mindmap(
    request: GenerateMindmapRequest,
    current_user: dict = Depends(get_current_user),
    use_case: GenerateMindmapUseCase = Depends(get_generate_mindmap_use_case)
):
    """
    Generate mindmap from document using Use Case pattern.

    Benefits:
    - Clean separation of concerns
    - All LLM calls encapsulated in use case
    - Fully testable with mock dependencies
    - Consistent error handling
    """
    # 1. Create context from request
    context = UseCaseContext(
        user_id=current_user.get("user_id", ""),
        user_email=current_user.get("email"),
        user_role=current_user.get("role", "user")
    )

    # 2. Create input DTO
    input_dto = MindmapInput(
        document_id=request.document_id,
        max_depth=request.max_depth,
        max_nodes_per_level=request.max_nodes_per_level,
        language=request.language,
        focus_topics=request.focus_topics
    )

    # 3. Execute use case
    result = await use_case.execute(input_dto, context)

    # 4. Handle result
    if result.is_failure:
        raise HTTPException(
            status_code=400 if result.error_code != "GENERATION_FAILED" else 500,
            detail={
                "code": result.error_code,
                "message": result.error_message,
                "errors": result.errors
            }
        )

    # 5. Return success response
    return {
        "success": True,
        "data": result.data.to_dict(),
        "meta": {
            "execution_id": result.execution_id,
            "execution_time_ms": result.execution_time_ms
        }
    }


@router.post("/query")
async def execute_query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
    use_case: ExecuteQueryUseCase = Depends(get_execute_query_use_case)
):
    """
    Execute RAG query using Use Case pattern.

    The use case handles:
    - Document retrieval (vector search, graph query)
    - Context building
    - LLM answer generation
    - History recording
    """
    context = UseCaseContext(
        user_id=current_user.get("user_id", ""),
        user_email=current_user.get("email"),
        user_role=current_user.get("role", "user")
    )

    input_dto = QueryInput(
        question=request.question,
        strategy=request.strategy,
        top_k=request.top_k,
        session_id=request.session_id
    )

    result = await use_case.execute(input_dto, context)

    if result.is_failure:
        raise HTTPException(
            status_code=500,
            detail={
                "code": result.error_code,
                "message": result.error_message
            }
        )

    return {
        "success": True,
        "data": result.data.to_dict(),
        "meta": {
            "execution_id": result.execution_id,
            "execution_time_ms": result.execution_time_ms
        }
    }


@router.post("/documents")
async def upload_document(
    request: UploadDocumentRequest,
    current_user: dict = Depends(get_current_user),
    use_case: UploadDocumentUseCase = Depends(get_upload_document_use_case)
):
    """
    Upload document using Use Case pattern.

    The use case handles:
    - Validation
    - Duplicate checking
    - Storage
    - Event publishing
    """
    context = UseCaseContext(
        user_id=current_user.get("user_id", ""),
        user_email=current_user.get("email"),
        user_role=current_user.get("role", "user")
    )

    input_dto = DocumentInput(
        name=request.name,
        content=request.content,
        project_id=request.project_id,
        tags=request.tags
    )

    result = await use_case.execute(input_dto, context)

    if result.is_failure:
        status_code = 400
        if result.error_code == "DUPLICATE_DOCUMENT":
            status_code = 409

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": result.error_code,
                "message": result.error_message,
                "errors": result.errors
            }
        )

    return {
        "success": True,
        "data": result.data.to_dict(),
        "meta": {
            "execution_id": result.execution_id,
            "execution_time_ms": result.execution_time_ms
        }
    }


# ==================== Example Test ====================
"""
Example test showing how to test use cases with mocks:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.usecases.mindmap import GenerateMindmapUseCase, MindmapInput
from app.api.usecases.base import UseCaseContext
from app.api.adapters.mock import MockLLMAdapter
from app.api.infrastructure.memory import MemoryDocumentRepository
from app.api.repositories.document_repository import DocumentEntity

@pytest.fixture
def mock_llm():
    llm = MockLLMAdapter()
    llm.set_response_template('''
    {
        "central_concept": "Test Concept",
        "concepts": [
            {"id": "c1", "label": "Sub Concept 1", "level": 1, "children": []}
        ]
    }
    ''')
    return llm

@pytest.fixture
def document_repo():
    repo = MemoryDocumentRepository()
    return repo

@pytest.fixture
def use_case(mock_llm, document_repo):
    return GenerateMindmapUseCase(
        llm=mock_llm,
        document_repository=document_repo
    )

@pytest.mark.asyncio
async def test_generate_mindmap_success(use_case, document_repo):
    # Arrange
    doc = DocumentEntity(
        id="doc_123",
        name="Test Document",
        content="This is test content for mindmap generation."
    )
    await document_repo.create(doc)

    input_data = MindmapInput(document_id="doc_123")
    context = UseCaseContext(user_id="user_123")

    # Act
    result = await use_case.execute(input_data, context)

    # Assert
    assert result.is_success
    assert result.data.document_id == "doc_123"
    assert result.data.total_nodes >= 1

@pytest.mark.asyncio
async def test_generate_mindmap_document_not_found(use_case):
    # Arrange
    input_data = MindmapInput(document_id="nonexistent")
    context = UseCaseContext(user_id="user_123")

    # Act
    result = await use_case.execute(input_data, context)

    # Assert
    assert result.is_failure
    assert result.error_code == "NOT_FOUND"
```
"""
