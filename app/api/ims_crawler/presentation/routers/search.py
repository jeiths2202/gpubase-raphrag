"""
IMS Search Router - Natural language search with hybrid BM25 + semantic search

Endpoints for searching IMS issues using NL queries with hybrid search support.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from uuid import UUID
import time

from ....core.deps import get_current_user
from ...application.use_cases import SearchIssuesUseCase
from ...infrastructure.dependencies import get_search_issues_use_case, get_issue_repository
from ...infrastructure.adapters import PostgreSQLIssueRepository


router = APIRouter(prefix="/ims-search", tags=["IMS Crawler"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SearchRequest(BaseModel):
    """Request model for IMS issue search"""
    query: str = Field(..., min_length=1, description="Natural language search query")
    max_results: int = Field(default=50, ge=1, le=500, description="Maximum results")
    include_attachments: bool = Field(default=True, description="Include attachment text in search")
    include_related: bool = Field(default=False, description="Crawl related issues")
    search_strategy: Literal['semantic', 'hybrid', 'recent'] = Field(
        default='hybrid',
        description="Search strategy: 'hybrid' (BM25 30% + Semantic 70%, default), 'semantic' (pure vector), 'recent' (chronological)"
    )
    use_semantic_search: Optional[bool] = Field(
        default=None,
        description="Deprecated: use search_strategy instead"
    )


class IssueSearchResult(BaseModel):
    """Single issue search result"""
    id: UUID
    ims_id: str
    title: str
    description: str
    status: str
    priority: str
    reporter: str
    assignee: Optional[str]
    project_key: str
    labels: List[str]
    created_at: str
    updated_at: str
    similarity_score: Optional[float] = None  # For semantic search results
    hybrid_score: Optional[float] = None  # For hybrid search results (BM25 30% + Semantic 70%)


class SearchResponse(BaseModel):
    """Response model for search results"""
    total_results: int
    query_used: str
    search_intent: Optional[str] = None
    results: List[IssueSearchResult]
    execution_time_ms: float


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=SearchResponse)
async def search_issues(
    request: SearchRequest,
    current_user: dict = Depends(get_current_user),
    use_case: SearchIssuesUseCase = Depends(get_search_issues_use_case)
):
    """
    Search IMS issues using natural language query with hybrid search.

    Workflow:
    1. Parse NL query using NVIDIA NIM → SearchIntent
    2. Execute search based on strategy:
       - 'hybrid' (default): BM25 30% + Semantic 70% with CJK tokenization
       - 'semantic': Pure vector similarity search
       - 'recent': Chronological order
    3. Optionally crawl related issues
    4. Return ranked results

    **Example Queries**:
    - "Show me critical bugs from last week"
    - "Find issues assigned to John with status open"
    - "Search for authentication problems in mobile project"
    - "인증 문제" (Korean: authentication problems with hybrid search)
    """
    start_time = time.time()
    user_id = UUID(current_user["id"])

    try:
        # Execute search via use case
        intent, issues = await use_case.search(
            query=request.query,
            user_id=user_id,
            max_results=request.max_results,
            search_strategy=request.search_strategy,
            use_semantic=request.use_semantic_search  # Backward compatibility
        )

        # Convert domain entities to response models
        results = [
            IssueSearchResult(
                id=issue.id,
                ims_id=issue.ims_id,
                title=issue.title,
                description=issue.description,
                status=issue.status.value,
                priority=issue.priority.value,
                reporter=issue.reporter,
                assignee=issue.assignee,
                project_key=issue.project_key,
                labels=issue.labels,
                created_at=issue.created_at.isoformat(),
                updated_at=issue.updated_at.isoformat(),
                similarity_score=getattr(issue, 'similarity_score', None),
                hybrid_score=issue.custom_fields.get('hybrid_score') if hasattr(issue, 'custom_fields') else None
            )
            for issue in issues
        ]

        execution_time_ms = (time.time() - start_time) * 1000

        return SearchResponse(
            total_results=len(results),
            query_used=request.query,
            search_intent=intent.original_query,
            results=results,
            execution_time_ms=execution_time_ms
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/recent", response_model=List[IssueSearchResult])
async def get_recent_issues(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    repository: PostgreSQLIssueRepository = Depends(get_issue_repository)
):
    """
    Get recently crawled issues for the current user.

    Returns most recently crawled issues sorted by crawl_date descending.
    """
    user_id = UUID(current_user["id"])

    try:
        # Query repository for recent issues
        issues = await repository.find_by_user_id(user_id, limit)

        # Convert domain entities to response models
        results = [
            IssueSearchResult(
                id=issue.id,
                ims_id=issue.ims_id,
                title=issue.title,
                description=issue.description,
                status=issue.status.value,
                priority=issue.priority.value,
                reporter=issue.reporter,
                assignee=issue.assignee,
                project_key=issue.project_key,
                labels=issue.labels,
                created_at=issue.created_at.isoformat(),
                updated_at=issue.updated_at.isoformat()
            )
            for issue in issues
        ]

        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve recent issues: {str(e)}"
        )


@router.get("/{issue_id}", response_model=IssueSearchResult)
async def get_issue_details(
    issue_id: UUID,
    current_user: dict = Depends(get_current_user),
    repository: PostgreSQLIssueRepository = Depends(get_issue_repository)
):
    """
    Get detailed information for a specific issue.

    Includes full description, comments, attachments, and related issues.
    """
    user_id = UUID(current_user["id"])

    try:
        # Query repository for issue
        issue = await repository.find_by_id(issue_id)

        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue {issue_id} not found"
            )

        # Validate user owns this issue
        if issue.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this issue"
            )

        # Convert domain entity to response model
        return IssueSearchResult(
            id=issue.id,
            ims_id=issue.ims_id,
            title=issue.title,
            description=issue.description,
            status=issue.status.value,
            priority=issue.priority.value,
            reporter=issue.reporter,
            assignee=issue.assignee,
            project_key=issue.project_key,
            labels=issue.labels,
            created_at=issue.created_at.isoformat(),
            updated_at=issue.updated_at.isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve issue details: {str(e)}"
        )
