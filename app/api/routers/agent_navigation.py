"""
Agent Navigation API Router
검색 전 확인을 위한 문서/섹션 후보 제공 API
"""
import time
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_current_user
from ..services.document_map_service import get_document_map_service
from ..services.agent_work_service import get_agent_work_service, SearchScope
from ..services.document_category_service import get_document_category_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-navigation", tags=["Agent Navigation"])


# ============================================================================
# Request/Response Models
# ============================================================================

class SectionCandidateResponse(BaseModel):
    """Section candidate in response."""
    section_path: str = Field(..., description="Section path (e.g., '2.1')")
    section_title: str = Field(..., description="Section title")
    page_start: int = Field(..., description="Start page number")
    page_end: int = Field(..., description="End page number")
    relevance_score: float = Field(0.0, description="Relevance score (0-1)")
    level: int = Field(1, description="Section nesting level")


class DocumentCandidateResponse(BaseModel):
    """Document candidate in response."""
    pdf_id: str = Field(..., description="Document ID")
    document_name: str = Field(..., description="Document name")
    document_type: str = Field(..., description="Document type (manual, report, etc.)")
    total_pages: int = Field(0, description="Total pages")
    relevance_score: float = Field(0.0, description="Relevance score (0-1)")
    sections: List[SectionCandidateResponse] = Field(default_factory=list, description="Relevant sections")
    keywords: List[str] = Field(default_factory=list, description="Document keywords")


class GetCandidatesRequest(BaseModel):
    """Request for document/section candidates."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    top_k: int = Field(5, ge=1, le=20, description="Maximum number of documents")
    min_score: float = Field(0.1, ge=0.0, le=1.0, description="Minimum relevance score")


class GetCandidatesResponse(BaseModel):
    """Response with document/section candidates."""
    candidates: List[DocumentCandidateResponse] = Field(default_factory=list)
    suggested_scope: Optional[dict] = Field(None, description="Suggested scope based on history")
    total_candidates: int = Field(0)


class ScopeSelectionRequest(BaseModel):
    """Request to confirm search scope selection."""
    query: str = Field(..., description="Original query")
    selected_documents: List[str] = Field(default_factory=list, description="Selected document IDs")
    selected_sections: List[str] = Field(default_factory=list, description="Selected section paths")


class ScopeSelectionResponse(BaseModel):
    """Response after scope selection."""
    scope: dict = Field(..., description="Confirmed search scope")
    saved_to_history: bool = Field(False, description="Whether saved to search history")


class DocumentMapResponse(BaseModel):
    """Response with document map."""
    documents: List[dict] = Field(default_factory=list)
    total_documents: int = Field(0)


# ============================================================================
# Category-based Models (Agent-Driven RAG with Categories)
# ============================================================================

class CategoryMatchRequest(BaseModel):
    """Request for category matching."""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    max_categories: int = Field(5, ge=1, le=10, description="Maximum categories")
    max_subcategories: int = Field(3, ge=1, le=5, description="Maximum subcategories per category")
    max_documents: int = Field(5, ge=1, le=10, description="Maximum documents per subcategory")
    min_score: float = Field(0.1, ge=0.0, le=1.0, description="Minimum relevance score")


class SectionInfoResponse(BaseModel):
    """Section information in response."""
    section_id: str = Field(..., description="Section ID")
    title: str = Field(..., description="Section title")
    level: int = Field(1, description="Section level")
    page_start: int = Field(1, description="Start page")
    page_end: int = Field(1, description="End page")
    keywords: List[str] = Field(default_factory=list, description="Keywords")


class DocumentInfoResponse(BaseModel):
    """Document information in response."""
    pdf_id: str = Field(..., description="Document ID")
    document_name: str = Field(..., description="Document name")
    document_type: str = Field(..., description="Document type")
    total_pages: int = Field(0, description="Total pages")
    language: str = Field("auto", description="Document language")
    keywords: List[str] = Field(default_factory=list, description="Keywords")
    sections: List[SectionInfoResponse] = Field(default_factory=list, description="Sections")
    relevance_score: float = Field(0.0, description="Relevance score")


class SubCategoryResponse(BaseModel):
    """Subcategory in response."""
    id: str = Field(..., description="Subcategory ID")
    name: str = Field(..., description="Subcategory name")
    description: str = Field("", description="Description")
    keywords: List[str] = Field(default_factory=list, description="Keywords")
    documents: List[DocumentInfoResponse] = Field(default_factory=list, description="Documents")
    document_count: int = Field(0, description="Total document count")
    relevance_score: float = Field(0.0, description="Relevance score")


class CategoryResponse(BaseModel):
    """Category in response."""
    id: str = Field(..., description="Category ID")
    name: str = Field(..., description="Category name (English)")
    name_ko: str = Field(..., description="Category name (Korean)")
    name_ja: str = Field(..., description="Category name (Japanese)")
    icon: str = Field("Folder", description="Icon name")
    description: str = Field("", description="Description")
    subcategories: List[SubCategoryResponse] = Field(default_factory=list, description="Subcategories")
    subcategory_count: int = Field(0, description="Total subcategory count")
    document_count: int = Field(0, description="Total document count")
    relevance_score: float = Field(0.0, description="Relevance score")


class CategoryMatchResponse(BaseModel):
    """Response for category matching."""
    query: str = Field(..., description="Original query")
    extracted_keywords: List[str] = Field(default_factory=list, description="Extracted keywords")
    categories: List[CategoryResponse] = Field(default_factory=list, description="Matched categories")
    total_documents: int = Field(0, description="Total matched documents")
    total_sections: int = Field(0, description="Total matched sections")


class AllCategoriesResponse(BaseModel):
    """Response for all categories overview."""
    categories: List[CategoryResponse] = Field(default_factory=list, description="All categories")
    total_categories: int = Field(0, description="Total category count")


# ============================================================================
# Endpoints
# ============================================================================

@router.post(
    "/candidates",
    response_model=SuccessResponse[GetCandidatesResponse],
    summary="검색 후보 문서/섹션 조회",
    description="쿼리에 기반하여 검색 범위로 선택할 수 있는 문서와 섹션 후보를 반환합니다."
)
async def get_candidates(
    request: GetCandidatesRequest,
    current_user: dict = Depends(get_current_user)
):
    """Get document/section candidates for scope selection."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        # Get document candidates
        doc_map_service = get_document_map_service()
        candidates = await doc_map_service.get_document_candidates(
            query=request.query,
            top_k=request.top_k,
            min_score=request.min_score
        )

        # Get suggested scope from history
        agent_work_service = get_agent_work_service()
        suggested = await agent_work_service.get_suggested_scope(user_id, request.query)

        # Build response
        candidate_responses = []
        for doc in candidates:
            sections = [
                SectionCandidateResponse(
                    section_path=s.section_path,
                    section_title=s.section_title,
                    page_start=s.page_start,
                    page_end=s.page_end,
                    relevance_score=s.relevance_score,
                    level=s.level
                )
                for s in doc.sections
            ]

            candidate_responses.append(DocumentCandidateResponse(
                pdf_id=doc.pdf_id,
                document_name=doc.document_name,
                document_type=doc.document_type,
                total_pages=doc.total_pages,
                relevance_score=doc.relevance_score,
                sections=sections,
                keywords=doc.keywords[:10]
            ))

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=GetCandidatesResponse(
                candidates=candidate_responses,
                suggested_scope=suggested.to_dict() if suggested else None,
                total_candidates=len(candidate_responses)
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get candidates: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve candidates")


@router.post(
    "/select-scope",
    response_model=SuccessResponse[ScopeSelectionResponse],
    summary="검색 범위 선택 확정",
    description="사용자가 선택한 검색 범위를 확정하고 기록합니다."
)
async def select_scope(
    request: ScopeSelectionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Confirm search scope selection and save to history."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        user_id = current_user.get("user_id") or current_user.get("id")

        # Create scope object
        scope = SearchScope(
            documents=request.selected_documents,
            sections=request.selected_sections
        )

        # Save to history
        agent_work_service = get_agent_work_service()
        saved = await agent_work_service.add_search_history(
            user_id=user_id,
            query=request.query,
            selected_scope=scope
        )

        # Update session state
        await agent_work_service.update_session_state(
            user_id=user_id,
            query=request.query,
            selected_scope=scope
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=ScopeSelectionResponse(
                scope=scope.to_dict(),
                saved_to_history=saved
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to select scope: {e}")
        raise HTTPException(status_code=500, detail="Failed to save scope selection")


@router.get(
    "/document-map",
    response_model=SuccessResponse[DocumentMapResponse],
    summary="문서 맵 조회",
    description="전체 문서 계층 구조 맵을 반환합니다."
)
async def get_document_map(
    pdf_id: Optional[str] = Query(None, description="특정 문서 ID"),
    current_user: dict = Depends(get_current_user)
):
    """Get document map for navigation."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        doc_map_service = get_document_map_service()
        doc_map = await doc_map_service.get_document_map(pdf_id)

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=DocumentMapResponse(
                documents=doc_map.get("documents", []),
                total_documents=len(doc_map.get("documents", []))
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get document map: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document map")


@router.get(
    "/search-keyword",
    response_model=SuccessResponse[DocumentMapResponse],
    summary="키워드 검색",
    description="키워드로 문서를 검색합니다."
)
async def search_by_keyword(
    keyword: str = Query(..., min_length=1, max_length=100, description="검색 키워드"),
    include_sections: bool = Query(True, description="섹션 포함 여부"),
    current_user: dict = Depends(get_current_user)
):
    """Search documents by keyword."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        doc_map_service = get_document_map_service()
        results = await doc_map_service.search_by_keyword(
            keyword=keyword,
            include_sections=include_sections
        )

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=DocumentMapResponse(
                documents=results,
                total_documents=len(results)
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to search by keyword: {e}")
        raise HTTPException(status_code=500, detail="Keyword search failed")


@router.post(
    "/refresh",
    response_model=SuccessResponse[dict],
    summary="문서 맵 새로고침",
    description="특정 문서 또는 전체 문서 맵을 새로고침합니다."
)
async def refresh_document_map(
    pdf_id: Optional[str] = Query(None, description="특정 문서 ID (없으면 전체)"),
    current_user: dict = Depends(get_current_user)
):
    """Refresh document map."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        doc_map_service = get_document_map_service()

        if pdf_id:
            success = await doc_map_service.refresh_document(pdf_id)
        else:
            success = await doc_map_service.initialize()

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data={"success": success, "pdf_id": pdf_id},
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to refresh document map: {e}")
        raise HTTPException(status_code=500, detail="Document map refresh failed")


@router.get(
    "/stats",
    response_model=SuccessResponse[dict],
    summary="통계 조회",
    description="문서 맵 서비스 통계를 반환합니다."
)
async def get_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get document map service statistics."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        doc_map_service = get_document_map_service()
        stats = await doc_map_service.get_stats()

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=stats,
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve statistics")


# ============================================================================
# Category-based Endpoints (Agent-Driven RAG with Categories)
# ============================================================================

@router.post(
    "/categories/match",
    response_model=SuccessResponse[CategoryMatchResponse],
    summary="쿼리 기반 카테고리 매칭",
    description="사용자 쿼리에서 키워드를 추출하고 관련 카테고리와 문서를 반환합니다."
)
async def match_categories(
    request: CategoryMatchRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Match user query to relevant categories.

    This is the main endpoint for Agent-Driven RAG pre-search confirmation.
    It extracts keywords from the query and returns categorized documents/sections.
    """
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        category_service = get_document_category_service()
        result = await category_service.match_query_to_categories(
            query=request.query,
            max_categories=request.max_categories,
            max_subcategories=request.max_subcategories,
            max_documents_per_subcategory=request.max_documents,
            min_score=request.min_score
        )

        # Convert to response models
        categories_response = []
        for cat in result.categories:
            subcategories_response = []
            for sub in cat.subcategories:
                documents_response = []
                for doc in sub.documents:
                    sections_response = [
                        SectionInfoResponse(
                            section_id=s.section_id,
                            title=s.title,
                            level=s.level,
                            page_start=s.page_start,
                            page_end=s.page_end,
                            keywords=s.keywords
                        )
                        for s in doc.sections
                    ]
                    documents_response.append(DocumentInfoResponse(
                        pdf_id=doc.pdf_id,
                        document_name=doc.document_name,
                        document_type=doc.document_type,
                        total_pages=doc.total_pages,
                        language=doc.language,
                        keywords=doc.keywords,
                        sections=sections_response,
                        relevance_score=doc.relevance_score
                    ))
                subcategories_response.append(SubCategoryResponse(
                    id=sub.id,
                    name=sub.name,
                    description=sub.description,
                    keywords=sub.keywords,
                    documents=documents_response,
                    document_count=len(documents_response),
                    relevance_score=sub.relevance_score
                ))
            categories_response.append(CategoryResponse(
                id=cat.id,
                name=cat.name,
                name_ko=cat.name_ko,
                name_ja=cat.name_ja,
                icon=cat.icon,
                description=cat.description,
                subcategories=subcategories_response,
                subcategory_count=len(subcategories_response),
                document_count=sum(len(s.documents) for s in subcategories_response),
                relevance_score=cat.relevance_score
            ))

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=CategoryMatchResponse(
                query=result.query,
                extracted_keywords=result.extracted_keywords,
                categories=categories_response,
                total_documents=result.total_documents,
                total_sections=result.total_sections
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to match categories: {e}")
        raise HTTPException(status_code=500, detail="Category matching failed")


@router.get(
    "/categories",
    response_model=SuccessResponse[AllCategoriesResponse],
    summary="전체 카테고리 목록 조회",
    description="모든 사용 가능한 카테고리 목록을 반환합니다."
)
async def get_all_categories(
    current_user: dict = Depends(get_current_user)
):
    """Get all available categories."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        category_service = get_document_category_service()
        categories = await category_service.get_all_categories()

        # Convert to response
        categories_response = []
        for cat in categories:
            subcategories_response = [
                SubCategoryResponse(
                    id=sub.id,
                    name=sub.name,
                    description=sub.description,
                    keywords=sub.keywords,
                    documents=[],
                    document_count=0,
                    relevance_score=0
                )
                for sub in cat.subcategories
            ]
            categories_response.append(CategoryResponse(
                id=cat.id,
                name=cat.name,
                name_ko=cat.name_ko,
                name_ja=cat.name_ja,
                icon=cat.icon,
                description=cat.description,
                subcategories=subcategories_response,
                subcategory_count=len(subcategories_response),
                document_count=0,
                relevance_score=0
            ))

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=AllCategoriesResponse(
                categories=categories_response,
                total_categories=len(categories_response)
            ),
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve categories")


@router.post(
    "/categories/refresh",
    response_model=SuccessResponse[dict],
    summary="카테고리 캐시 새로고침",
    description="카테고리 캐시를 강제로 새로고침합니다."
)
async def refresh_categories(
    current_user: dict = Depends(get_current_user)
):
    """Refresh category cache."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        category_service = get_document_category_service()
        success = await category_service.refresh()

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data={"success": success, "message": "Category cache refreshed"},
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to refresh categories: {e}")
        raise HTTPException(status_code=500, detail="Category refresh failed")


@router.get(
    "/categories/stats",
    response_model=SuccessResponse[dict],
    summary="카테고리 통계 조회",
    description="카테고리 서비스 통계를 반환합니다."
)
async def get_category_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get category service statistics."""
    start_time = time.time()
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    try:
        category_service = get_document_category_service()
        stats = await category_service.get_stats()

        processing_time = int((time.time() - start_time) * 1000)

        return SuccessResponse(
            data=stats,
            meta=MetaInfo(
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
                processing_time_ms=processing_time
            )
        )

    except Exception as e:
        logger.error(f"Failed to get category stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve category statistics")
