"""
FAQ API Router

Endpoints for FAQ items, popular queries, and feedback.
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_user
from ..models.query_log import (
    FAQListResponse, FAQCategoryResponse, PopularQueriesResponse,
    FAQFeedbackRequest, FAQItemCreate
)
from ..infrastructure.postgres.query_log_repository import QueryLogRepository

router = APIRouter(prefix="/faq", tags=["FAQ"])


# Dependency injection placeholder
# In production, this would be properly injected via FastAPI dependencies
_faq_repository: Optional[QueryLogRepository] = None


def set_faq_repository(repository: QueryLogRepository):
    """Set the FAQ repository instance"""
    global _faq_repository
    _faq_repository = repository


def get_faq_repository() -> QueryLogRepository:
    """Get FAQ repository instance"""
    if _faq_repository is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FAQ service not initialized"
        )
    return _faq_repository


# ============================================
# Public Endpoints
# ============================================

@router.get("", response_model=FAQListResponse)
async def get_faq_items(
    category: Optional[str] = Query(None, description="Filter by category"),
    language: str = Query("ko", description="Content language: en, ko, ja"),
    limit: int = Query(50, ge=1, le=100, description="Maximum items to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    include_dynamic: bool = Query(True, description="Include AI-generated FAQ items")
):
    """
    Get FAQ items for display.

    Combines static FAQ items with dynamically generated items from popular queries.
    Items are sorted by: pinned status, display order, and view count.
    """
    repository = get_faq_repository()

    items, total = await repository.get_faq_items(
        language=language,
        category=category,
        limit=limit,
        offset=offset,
        include_dynamic=include_dynamic
    )

    # Transform items for response
    faq_items = []
    for item in items:
        if item.get('question') and item.get('answer'):
            faq_items.append({
                'id': str(item['id']),
                'source_type': item['source_type'],
                'question': item['question'],
                'answer': item['answer'],
                'category': item['category'],
                'tags': item.get('tags') or [],
                'view_count': item.get('view_count', 0),
                'helpful_count': item.get('helpful_count', 0),
                'not_helpful_count': item.get('not_helpful_count', 0),
                'is_pinned': item.get('is_pinned', False),
                'created_at': item['created_at'].isoformat() if item.get('created_at') else None
            })

    return FAQListResponse(
        status="success",
        data={
            "items": faq_items,
            "total": total,
            "has_more": offset + limit < total
        }
    )


@router.get("/categories", response_model=FAQCategoryResponse)
async def get_faq_categories():
    """
    Get list of FAQ categories with counts.

    Returns all categories including a special 'all' category with total count.
    """
    repository = get_faq_repository()
    categories = await repository.get_faq_categories()

    # Add localized names
    category_names = {
        'all': {'ko': '전체', 'ja': 'すべて', 'en': 'All'},
        'openframe': {'ko': 'OpenFrame', 'ja': 'OpenFrame', 'en': 'OpenFrame'},
        'ofcobol': {'ko': 'OFCOBOL', 'ja': 'OFCOBOL', 'en': 'OFCOBOL'},
        'ofasm': {'ko': 'OFASM', 'ja': 'OFASM', 'en': 'OFASM'},
        'ims': {'ko': 'IMS 이슈', 'ja': 'IMS問題', 'en': 'IMS Issues'},
        'rag': {'ko': '지식 검색', 'ja': '知識検索', 'en': 'Knowledge Search'},
        'general': {'ko': '일반', 'ja': '一般', 'en': 'General'},
    }

    result = []
    for cat in categories:
        cat_id = cat['id']
        names = category_names.get(cat_id, {'ko': cat_id, 'ja': cat_id, 'en': cat_id})
        result.append({
            'id': cat_id,
            'name': names['en'],
            'name_ko': names['ko'],
            'name_ja': names['ja'],
            'count': cat['count']
        })

    return FAQCategoryResponse(
        status="success",
        data={"categories": result}
    )


@router.post("/{faq_id}/view")
async def record_faq_view(faq_id: UUID):
    """
    Record a view for an FAQ item.

    Increments the view counter for analytics and popularity scoring.
    """
    repository = get_faq_repository()
    await repository.increment_faq_view(faq_id)
    return {"status": "success", "message": "View recorded"}


@router.post("/{faq_id}/feedback")
async def record_faq_feedback(
    faq_id: UUID,
    request: FAQFeedbackRequest
):
    """
    Record feedback (helpful/not helpful) for an FAQ item.

    This feedback affects the FAQ item's quality score and ranking.
    """
    repository = get_faq_repository()
    await repository.record_faq_feedback(faq_id, request.is_helpful)
    return {
        "status": "success",
        "message": "Feedback recorded",
        "is_helpful": request.is_helpful
    }


# ============================================
# Admin Endpoints (Requires Authentication)
# ============================================

@router.get("/popular", response_model=PopularQueriesResponse)
async def get_popular_queries(
    days: int = Query(30, ge=1, le=365, description="Look back period in days"),
    category: Optional[str] = Query(None, description="Filter by category"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    min_frequency: int = Query(3, ge=1, description="Minimum query frequency"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    Get popular queries from the last N days.

    Admin endpoint for reviewing popular questions that could become FAQ items.
    Queries are ranked by popularity score which considers:
    - Frequency count
    - Recency (more recent = higher score)
    - Unique user count
    - Helpfulness ratio (if feedback available)
    """
    repository = get_faq_repository()

    queries, total = await repository.get_popular_queries(
        limit=limit,
        offset=offset,
        category=category,
        agent_type=agent_type,
        min_frequency=min_frequency,
        days=days
    )

    # Format for response
    formatted_queries = []
    for q in queries:
        formatted_queries.append({
            'id': str(q['id']),
            'query': q['representative_query'],
            'answer': q.get('representative_answer'),
            'frequency_count': q['frequency_count'],
            'unique_users': q['unique_users_count'],
            'popularity_score': round(q['popularity_score'], 2),
            'is_faq_eligible': q['is_faq_eligible'],
            'agent_type': q.get('agent_type'),
            'category': q.get('category'),
            'last_asked': q['last_asked_at'].isoformat() if q.get('last_asked_at') else None,
            'first_asked': q['first_asked_at'].isoformat() if q.get('first_asked_at') else None
        })

    return PopularQueriesResponse(
        status="success",
        data={
            "queries": formatted_queries,
            "total": total,
            "period_days": days
        }
    )


@router.get("/statistics")
async def get_faq_statistics(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user)
):
    """
    Get FAQ and query statistics for admin dashboard.

    Returns aggregated statistics about query patterns and FAQ performance.
    """
    repository = get_faq_repository()
    stats = await repository.get_query_statistics(days=days)

    return {
        "status": "success",
        "data": stats
    }


@router.post("/sync-dynamic")
async def sync_dynamic_faq_items(
    min_frequency: int = Query(3, ge=1, description="Minimum frequency for FAQ eligibility"),
    current_user: dict = Depends(get_current_user)
):
    """
    Manually trigger sync of dynamic FAQ items from popular queries.

    Creates new FAQ items from query aggregates that meet the frequency threshold.
    This is also done automatically, but can be triggered manually by admins.
    """
    # Check if user has admin role
    user_role = current_user.get('role', 'user')
    if user_role not in ['admin', 'leader']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or leader role required"
        )

    repository = get_faq_repository()
    count = await repository.sync_dynamic_faq_items(min_frequency=min_frequency)

    return {
        "status": "success",
        "message": f"Created {count} new dynamic FAQ items",
        "count": count
    }


@router.post("")
async def create_faq_item(
    request: FAQItemCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new FAQ item (admin only).

    Allows administrators to manually create curated FAQ items.
    """
    user_role = current_user.get('role', 'user')
    if user_role not in ['admin', 'leader']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or leader role required"
        )

    repository = get_faq_repository()
    faq_id = await repository.create_faq_item(request.model_dump())

    return {
        "status": "success",
        "message": "FAQ item created",
        "data": {"id": str(faq_id)}
    }
