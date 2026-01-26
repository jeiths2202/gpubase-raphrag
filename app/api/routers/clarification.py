"""
Query Clarification API Router

API endpoints for the query clarification system that handles
ambiguous term detection and user preference management.

Phase 2 additions:
- Term candidate management (auto-extracted terms from documents)
- Entity embedding generation for ML recommendations
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.deps import get_current_user
from ..models.clarification import (
    ClarificationCheckRequest,
    ClarificationCheckResponse,
    ClarificationApplyRequest,
    ClarificationApplyResponse,
    AmbiguousTermListResponse,
    UserPreferenceListResponse,
    AmbiguousTerm,
    UserTermPreference,
    AmbiguousTermCreate,
    AmbiguousTermUpdate,
    # Phase 2: Term Candidates
    TermCandidate,
    TermCandidateListResponse,
    TermCandidateApproveRequest,
    TermCandidateMergeRequest,
    TermCandidateRejectRequest,
    TermCandidateStatistics,
    GenerateEmbeddingsResponse,
    PossibleEntity,
)
from ..services.query_clarification_service import get_query_clarification_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/clarification",
    tags=["Clarification"],
)


# =============================================================================
# User Endpoints
# =============================================================================

@router.post(
    "/check",
    response_model=ClarificationCheckResponse,
    summary="Check if query needs clarification",
    description="""
    Check if a user's query contains ambiguous terms that need clarification.

    This endpoint:
    1. Analyzes the query for ambiguous terms (e.g., "MFS", "WebAdmin")
    2. Checks if the user has saved preferences for these terms
    3. Returns whether clarification is needed and detected terms

    If all detected terms have user preferences with "remember" enabled,
    the query is auto-resolved and `needs_clarification` will be False.
    """,
)
async def check_needs_clarification(
    request: ClarificationCheckRequest,
    current_user: dict = Depends(get_current_user),
) -> ClarificationCheckResponse:
    """
    Check if query needs clarification for ambiguous terms.

    Args:
        request: Query to check
        current_user: Authenticated user

    Returns:
        ClarificationCheckResponse with detected terms and resolution status
    """
    try:
        service = get_query_clarification_service()
        user_id = current_user.get("user_id", current_user.get("id", ""))

        response = await service.check_needs_clarification(request, user_id)

        logger.debug(
            f"Clarification check: query='{request.query[:50]}...', "
            f"needs_clarification={response.needs_clarification}, "
            f"detected_terms={len(response.detected_terms)}"
        )

        return response

    except RuntimeError as e:
        # Service not initialized
        logger.warning(f"Clarification service not available: {e}")
        # 서비스 미초기화 시 명확화 필요 없음으로 응답 (graceful fallback)
        return ClarificationCheckResponse(
            needs_clarification=False,
            detected_terms=[],
            resolved_query=request.query,
            auto_resolved_count=0,
            message="Clarification service not available",
        )
    except Exception as e:
        logger.error(f"Error checking clarification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check clarification: {str(e)}"
        )


@router.post(
    "/apply",
    response_model=ClarificationApplyResponse,
    summary="Apply user's clarification selections",
    description="""
    Apply user's selections for ambiguous terms to resolve the query.

    This endpoint:
    1. Takes user's selections for each ambiguous term
    2. Optionally saves preferences if "remember" is enabled
    3. Returns the resolved query with clarified terms

    The resolved query replaces ambiguous terms with their selected meanings.
    For example: "MFS 에러" → "JEUS MFS 에러"
    """,
)
async def apply_clarification(
    request: ClarificationApplyRequest,
    current_user: dict = Depends(get_current_user),
) -> ClarificationApplyResponse:
    """
    Apply user's clarification selections to resolve query.

    Args:
        request: Query and user's term selections
        current_user: Authenticated user

    Returns:
        ClarificationApplyResponse with resolved query
    """
    try:
        service = get_query_clarification_service()
        user_id = current_user.get("user_id", current_user.get("id", ""))

        response = await service.apply_user_selections(request, user_id)

        logger.info(
            f"Clarification applied: user={user_id[:8]}..., "
            f"selections={len(request.selections)}, "
            f"preferences_saved={response.preferences_saved}"
        )

        return response

    except RuntimeError as e:
        logger.warning(f"Clarification service not available: {e}")
        # Graceful fallback: 원본 쿼리 반환
        return ClarificationApplyResponse(
            success=True,
            resolved_query=request.query,
            applied_selections=[],
            preferences_saved=0,
            message="Clarification service not available - using original query",
        )
    except Exception as e:
        logger.error(f"Error applying clarification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply clarification: {str(e)}"
        )


@router.get(
    "/preferences",
    response_model=UserPreferenceListResponse,
    summary="Get user's term preferences",
    description="Get all saved term preferences for the current user.",
)
async def get_user_preferences(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
) -> UserPreferenceListResponse:
    """
    Get user's saved term preferences.

    Args:
        page: Page number (1-based)
        page_size: Results per page
        current_user: Authenticated user

    Returns:
        List of user's term preferences
    """
    try:
        service = get_query_clarification_service()
        repo = service.user_preference_repo
        user_id = current_user.get("user_id", current_user.get("id", ""))

        preferences, total = await repo.list_user_preferences(
            user_id, page, page_size
        )

        return UserPreferenceListResponse(
            preferences=[
                UserTermPreference(
                    id=p["id"],
                    user_id=p["user_id"],
                    term_normalized=p["term_normalized"],
                    selected_entity_id=p["selected_entity_id"],
                    selected_entity_name=p["selected_entity_name"],
                    is_permanent=p["is_permanent"],
                    usage_count=p["usage_count"],
                    created_at=p["created_at"],
                    updated_at=p["updated_at"],
                )
                for p in preferences
            ],
            total=total,
        )

    except Exception as e:
        logger.error(f"Error getting user preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get preferences: {str(e)}"
        )


@router.delete(
    "/preferences/{term_normalized}",
    summary="Delete a term preference",
    description="Delete a specific term preference for the current user.",
)
async def delete_user_preference(
    term_normalized: str,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Delete a user's term preference.

    Args:
        term_normalized: Normalized term to delete preference for
        current_user: Authenticated user

    Returns:
        Success status
    """
    try:
        service = get_query_clarification_service()
        repo = service.user_preference_repo
        user_id = current_user.get("user_id", current_user.get("id", ""))

        deleted = await repo.delete_preference(user_id, term_normalized)

        if deleted:
            return {"success": True, "message": f"Preference for '{term_normalized}' deleted"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Preference for '{term_normalized}' not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting preference: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete preference: {str(e)}"
        )


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.get(
    "/admin/terms",
    response_model=AmbiguousTermListResponse,
    summary="List ambiguous terms (Admin)",
    description="List all admin-defined ambiguous terms. Requires admin privileges.",
)
async def list_ambiguous_terms(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
) -> AmbiguousTermListResponse:
    """
    List all ambiguous terms (admin only).

    Args:
        category: Filter by category
        is_active: Filter by active status
        page: Page number
        page_size: Results per page
        current_user: Authenticated admin user

    Returns:
        List of ambiguous terms
    """
    # Admin 권한 확인
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )

        repo = await get_ambiguous_term_repository()
        terms, total = await repo.list(category, is_active, page, page_size)

        return AmbiguousTermListResponse(
            terms=[
                AmbiguousTerm(
                    id=t["id"],
                    term=t["term"],
                    term_normalized=t["term_normalized"],
                    category=t["category"],
                    possible_entities=t["possible_entities"],
                    match_patterns=t["match_patterns"],
                    priority=t["priority"],
                    is_active=t["is_active"],
                    created_at=t["created_at"],
                    updated_at=t["updated_at"],
                )
                for t in terms
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Error listing ambiguous terms: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list terms: {str(e)}"
        )


@router.post(
    "/admin/terms",
    response_model=AmbiguousTerm,
    status_code=status.HTTP_201_CREATED,
    summary="Create ambiguous term (Admin)",
    description="Create a new ambiguous term definition. Requires admin privileges.",
)
async def create_ambiguous_term(
    request: AmbiguousTermCreate,
    current_user: dict = Depends(get_current_user),
) -> AmbiguousTerm:
    """
    Create a new ambiguous term (admin only).

    Args:
        request: Term creation request
        current_user: Authenticated admin user

    Returns:
        Created term
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )

        repo = await get_ambiguous_term_repository()

        # possible_entities를 dict 리스트로 변환
        entities = [e.model_dump() for e in request.possible_entities]

        term_id = await repo.create(
            term=request.term,
            possible_entities=entities,
            category=request.category,
            match_patterns=request.match_patterns,
            priority=request.priority,
            is_active=request.is_active,
        )

        # 생성된 용어 조회
        term_data = await repo.get_by_normalized_term(request.term.lower().strip())

        if not term_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve created term"
            )

        return AmbiguousTerm(
            id=term_data["id"],
            term=term_data["term"],
            term_normalized=term_data["term_normalized"],
            category=term_data["category"],
            possible_entities=term_data["possible_entities"],
            match_patterns=term_data["match_patterns"],
            priority=term_data["priority"],
            is_active=term_data["is_active"],
            created_at=term_data["created_at"],
            updated_at=term_data["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating ambiguous term: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create term: {str(e)}"
        )


@router.put(
    "/admin/terms/{term_id}",
    response_model=dict,
    summary="Update ambiguous term (Admin)",
    description="Update an existing ambiguous term. Requires admin privileges.",
)
async def update_ambiguous_term(
    term_id: int,
    request: AmbiguousTermUpdate,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Update an ambiguous term (admin only).

    Args:
        term_id: Term ID to update
        request: Update request
        current_user: Authenticated admin user

    Returns:
        Success status
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )

        repo = await get_ambiguous_term_repository()

        # 업데이트할 필드 준비
        updates = {}
        if request.term is not None:
            updates["term"] = request.term
        if request.category is not None:
            updates["category"] = request.category
        if request.possible_entities is not None:
            updates["possible_entities"] = [e.model_dump() for e in request.possible_entities]
        if request.match_patterns is not None:
            updates["match_patterns"] = request.match_patterns
        if request.priority is not None:
            updates["priority"] = request.priority
        if request.is_active is not None:
            updates["is_active"] = request.is_active

        if not updates:
            return {"success": True, "message": "No updates provided"}

        updated = await repo.update(term_id, **updates)

        if updated:
            return {"success": True, "message": f"Term {term_id} updated"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Term {term_id} not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating ambiguous term: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update term: {str(e)}"
        )


@router.delete(
    "/admin/terms/{term_id}",
    summary="Delete ambiguous term (Admin)",
    description="Delete an ambiguous term. Requires admin privileges.",
)
async def delete_ambiguous_term(
    term_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Delete an ambiguous term (admin only).

    Args:
        term_id: Term ID to delete
        current_user: Authenticated admin user

    Returns:
        Success status
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )

        repo = await get_ambiguous_term_repository()
        deleted = await repo.delete(term_id)

        if deleted:
            return {"success": True, "message": f"Term {term_id} deleted"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Term {term_id} not found"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ambiguous term: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete term: {str(e)}"
        )


# =============================================================================
# Phase 2: Term Candidate Endpoints
# =============================================================================

@router.get(
    "/admin/candidates",
    response_model=TermCandidateListResponse,
    summary="List term candidates (Admin)",
    description="""
    List auto-extracted term candidates awaiting admin review.

    Candidates are extracted from uploaded documents using:
    - Pattern matching (product names, acronyms)
    - Frequency analysis (commonly occurring terms)
    - Context analysis (terms near technical keywords)

    Returns candidates with similarity info against existing ambiguous terms.
    """,
)
async def list_term_candidates(
    status_filter: Optional[str] = None,
    extraction_method: Optional[str] = None,
    min_confidence: Optional[float] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
) -> TermCandidateListResponse:
    """
    List term candidates (admin only).

    Args:
        status_filter: Filter by status (pending, approved, rejected, merged)
        extraction_method: Filter by extraction method (pattern, frequency, context)
        min_confidence: Minimum confidence score
        page: Page number
        page_size: Results per page
        current_user: Authenticated admin user

    Returns:
        List of term candidates
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.term_candidate_repository import (
            get_term_candidate_repository
        )
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        repo = await get_term_candidate_repository(pool)

        # 기본적으로 pending 상태에 대해 유사성 정보 포함
        if status_filter == "pending" or status_filter is None:
            candidates, total = await repo.list_pending_with_similarity(page, page_size)
        else:
            candidates, total = await repo.list(
                status=status_filter,
                extraction_method=extraction_method,
                min_confidence=min_confidence,
                page=page,
                page_size=page_size,
            )

        return TermCandidateListResponse(
            candidates=[TermCandidate(**c) for c in candidates],
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Error listing term candidates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list candidates: {str(e)}"
        )


@router.get(
    "/admin/candidates/statistics",
    response_model=TermCandidateStatistics,
    summary="Get term candidate statistics (Admin)",
    description="Get statistics about term candidates by status and extraction method.",
)
async def get_term_candidate_statistics(
    current_user: dict = Depends(get_current_user),
) -> TermCandidateStatistics:
    """
    Get term candidate statistics (admin only).

    Args:
        current_user: Authenticated admin user

    Returns:
        Statistics about term candidates
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.term_candidate_repository import (
            get_term_candidate_repository
        )
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        repo = await get_term_candidate_repository(pool)

        stats = await repo.get_statistics()
        return TermCandidateStatistics(**stats)

    except Exception as e:
        logger.error(f"Error getting candidate statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@router.get(
    "/admin/candidates/{candidate_id}",
    response_model=TermCandidate,
    summary="Get term candidate by ID (Admin)",
    description="Get detailed information about a specific term candidate.",
)
async def get_term_candidate(
    candidate_id: int,
    current_user: dict = Depends(get_current_user),
) -> TermCandidate:
    """
    Get a term candidate by ID (admin only).

    Args:
        candidate_id: Candidate ID
        current_user: Authenticated admin user

    Returns:
        Term candidate details
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.term_candidate_repository import (
            get_term_candidate_repository
        )
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        repo = await get_term_candidate_repository(pool)

        candidate = await repo.get_by_id(candidate_id)
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate {candidate_id} not found"
            )

        return TermCandidate(**candidate)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting term candidate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get candidate: {str(e)}"
        )


@router.post(
    "/admin/candidates/{candidate_id}/approve",
    response_model=AmbiguousTerm,
    summary="Approve term candidate (Admin)",
    description="""
    Approve a term candidate and create a new ambiguous term.

    Requires providing at least 2 possible entities for the new term.
    The candidate status changes to 'approved' and links to the new term.
    """,
)
async def approve_term_candidate(
    candidate_id: int,
    request: TermCandidateApproveRequest,
    current_user: dict = Depends(get_current_user),
) -> AmbiguousTerm:
    """
    Approve a term candidate and create ambiguous term (admin only).

    Args:
        candidate_id: Candidate ID to approve
        request: Approval request with entity configuration
        current_user: Authenticated admin user

    Returns:
        Created ambiguous term
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.term_candidate_repository import (
            get_term_candidate_repository
        )
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        candidate_repo = await get_term_candidate_repository(pool)
        term_repo = await get_ambiguous_term_repository(pool)

        # 후보 조회
        candidate = await candidate_repo.get_by_id(candidate_id)
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate {candidate_id} not found"
            )

        if candidate["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Candidate is already {candidate['status']}"
            )

        user_id = current_user.get("user_id", current_user.get("id", ""))

        # 새 ambiguous_term 생성
        entities = [e.model_dump() for e in request.possible_entities]
        term_id = await term_repo.create(
            term=candidate["term"],
            possible_entities=entities,
            category=request.category or candidate.get("suggested_category"),
            match_patterns=request.match_patterns,
            priority=request.priority,
            is_active=True,
        )

        # 후보 승인 처리
        await candidate_repo.approve(candidate_id, user_id, term_id)

        # 생성된 용어 조회
        term_data = await term_repo.get_by_id(term_id)

        logger.info(f"Term candidate {candidate_id} approved as term {term_id}")

        return AmbiguousTerm(
            id=term_data["id"],
            term=term_data["term"],
            term_normalized=term_data["term_normalized"],
            category=term_data["category"],
            possible_entities=[PossibleEntity(**e) for e in term_data["possible_entities"]],
            match_patterns=term_data["match_patterns"],
            priority=term_data["priority"],
            is_active=term_data["is_active"],
            created_at=term_data["created_at"],
            updated_at=term_data["updated_at"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving term candidate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve candidate: {str(e)}"
        )


@router.post(
    "/admin/candidates/{candidate_id}/merge",
    response_model=dict,
    summary="Merge term candidate into existing term (Admin)",
    description="""
    Merge a term candidate into an existing ambiguous term.

    Optionally adds the candidate term as a new match pattern for the target term.
    """,
)
async def merge_term_candidate(
    candidate_id: int,
    request: TermCandidateMergeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Merge a term candidate into existing ambiguous term (admin only).

    Args:
        candidate_id: Candidate ID to merge
        request: Merge request with target term ID
        current_user: Authenticated admin user

    Returns:
        Success status
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.term_candidate_repository import (
            get_term_candidate_repository
        )
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        candidate_repo = await get_term_candidate_repository(pool)
        term_repo = await get_ambiguous_term_repository(pool)

        # 후보 조회
        candidate = await candidate_repo.get_by_id(candidate_id)
        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate {candidate_id} not found"
            )

        if candidate["status"] != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Candidate is already {candidate['status']}"
            )

        # 대상 용어 조회
        target_term = await term_repo.get_by_id(request.target_term_id)
        if not target_term:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target term {request.target_term_id} not found"
            )

        user_id = current_user.get("user_id", current_user.get("id", ""))

        # match_pattern 추가 (옵션)
        if request.add_match_pattern:
            current_patterns = target_term.get("match_patterns", [])
            candidate_term = candidate["term"]
            if candidate_term not in current_patterns:
                updated_patterns = current_patterns + [candidate_term]
                await term_repo.update(request.target_term_id, match_patterns=updated_patterns)

        # 후보 병합 처리
        await candidate_repo.mark_merged(candidate_id, user_id, request.target_term_id)

        logger.info(
            f"Term candidate {candidate_id} merged into term {request.target_term_id}"
        )

        return {
            "success": True,
            "message": f"Candidate merged into term {request.target_term_id}",
            "target_term_id": request.target_term_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error merging term candidate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to merge candidate: {str(e)}"
        )


@router.post(
    "/admin/candidates/{candidate_id}/reject",
    response_model=dict,
    summary="Reject term candidate (Admin)",
    description="Reject a term candidate with optional reason.",
)
async def reject_term_candidate(
    candidate_id: int,
    request: TermCandidateRejectRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Reject a term candidate (admin only).

    Args:
        candidate_id: Candidate ID to reject
        request: Rejection request with optional reason
        current_user: Authenticated admin user

    Returns:
        Success status
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.term_candidate_repository import (
            get_term_candidate_repository
        )
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        repo = await get_term_candidate_repository(pool)

        user_id = current_user.get("user_id", current_user.get("id", ""))

        rejected = await repo.reject(candidate_id, user_id, request.reason)

        if rejected:
            return {"success": True, "message": f"Candidate {candidate_id} rejected"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Candidate {candidate_id} not found or already processed"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting term candidate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject candidate: {str(e)}"
        )


# =============================================================================
# Phase 2: Entity Embedding Endpoints
# =============================================================================

@router.post(
    "/admin/terms/{term_id}/generate-embeddings",
    response_model=GenerateEmbeddingsResponse,
    summary="Generate entity embeddings for term (Admin)",
    description="""
    Generate embedding vectors for all entities of an ambiguous term.

    This enables ML-based entity recommendations based on query similarity.
    Embeddings are stored in the entity_embeddings column.
    """,
)
async def generate_term_embeddings(
    term_id: int,
    current_user: dict = Depends(get_current_user),
) -> GenerateEmbeddingsResponse:
    """
    Generate entity embeddings for a term (admin only).

    Args:
        term_id: Ambiguous term ID
        current_user: Authenticated admin user

    Returns:
        Status of embedding generation
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )
        from ..services.entity_embedding_service import get_entity_embedding_service
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        term_repo = await get_ambiguous_term_repository(pool)

        # 용어 조회
        term_data = await term_repo.get_by_id(term_id)
        if not term_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Term {term_id} not found"
            )

        # 엔티티를 모델로 변환
        possible_entities = [
            PossibleEntity(**e) for e in term_data.get("possible_entities", [])
        ]

        if not possible_entities:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Term has no possible entities"
            )

        # 임베딩 서비스 가져오기
        try:
            embedding_service = get_entity_embedding_service()
        except RuntimeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Entity embedding service not available"
            )

        # 임베딩 생성
        entity_embeddings = await embedding_service.generate_all_entity_embeddings(
            possible_entities
        )

        # DB에 저장
        success = await term_repo.update_entity_embeddings(term_id, entity_embeddings)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save embeddings"
            )

        logger.info(
            f"Generated embeddings for term {term_id}: "
            f"{len(entity_embeddings)} entities"
        )

        return GenerateEmbeddingsResponse(
            term_id=term_id,
            entities_processed=len(entity_embeddings),
            success=True,
            message=f"Generated embeddings for {len(entity_embeddings)} entities",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embeddings: {str(e)}"
        )


@router.post(
    "/admin/terms/generate-all-embeddings",
    response_model=dict,
    summary="Generate embeddings for all terms (Admin)",
    description="Generate embedding vectors for all active ambiguous terms.",
)
async def generate_all_term_embeddings(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Generate embeddings for all active terms (admin only).

    Args:
        current_user: Authenticated admin user

    Returns:
        Summary of embedding generation
    """
    role = current_user.get("role", "")
    if role not in ["admin", "super_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        from ..infrastructure.postgres.ambiguous_term_repository import (
            get_ambiguous_term_repository
        )
        from ..services.entity_embedding_service import get_entity_embedding_service
        from ..core.deps import get_postgres_pool

        pool = await get_postgres_pool()
        term_repo = await get_ambiguous_term_repository(pool)

        # 임베딩 서비스 가져오기
        try:
            embedding_service = get_entity_embedding_service()
        except RuntimeError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Entity embedding service not available"
            )

        # 모든 활성 용어 조회
        all_terms = await term_repo.get_all_active()

        processed = 0
        failed = 0
        skipped = 0

        for term_data in all_terms:
            term_id = term_data["id"]
            possible_entities = [
                PossibleEntity(**e) for e in term_data.get("possible_entities", [])
            ]

            if not possible_entities:
                skipped += 1
                continue

            # 이미 임베딩이 있으면 건너뛰기
            if term_data.get("entity_embeddings"):
                skipped += 1
                continue

            try:
                entity_embeddings = await embedding_service.generate_all_entity_embeddings(
                    possible_entities
                )
                await term_repo.update_entity_embeddings(term_id, entity_embeddings)
                processed += 1
            except Exception as e:
                logger.warning(f"Failed to generate embeddings for term {term_id}: {e}")
                failed += 1

        logger.info(
            f"Bulk embedding generation: processed={processed}, failed={failed}, skipped={skipped}"
        )

        return {
            "success": True,
            "processed": processed,
            "failed": failed,
            "skipped": skipped,
            "message": f"Processed {processed} terms, {failed} failed, {skipped} skipped",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk embedding generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate embeddings: {str(e)}"
        )
