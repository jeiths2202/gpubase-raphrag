"""
Knowledge Article API Router
Handles knowledge article CRUD, workflow, and recommendations
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_user
from ..models.auth import UserRole, can_review
from ..models.knowledge_article import (
    KnowledgeArticle, KnowledgeStatus, KnowledgeCategory, SupportedLanguage,
    CreateKnowledgeRequest, UpdateKnowledgeRequest, ReviewActionRequest,
    KnowledgeSearchRequest, KnowledgeListResponse, KnowledgeDetailResponse,
    TopContributorsListResponse, RecommendationResponse
)
from ..services.knowledge_article_service import get_knowledge_service
from ..services.notification_service import get_notification_service

router = APIRouter(prefix="/knowledge", tags=["Knowledge Articles"])


def get_service():
    return get_knowledge_service()


def get_notif_service():
    return get_notification_service()


# ==================== CRUD Operations ====================

@router.post("", response_model=dict)
async def create_knowledge_article(
    request: CreateKnowledgeRequest,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    Create a new knowledge article (Draft status).
    Any authenticated user can create.
    """
    article = await service.create_article(
        request=request,
        author_id=current_user["id"],
        author_name=current_user.get("username", "Unknown"),
        author_department=current_user.get("department")
    )

    return {
        "status": "success",
        "data": {
            "article": article.model_dump()
        },
        "message": "지식 문서가 생성되었습니다."
    }


@router.get("", response_model=dict)
async def list_knowledge_articles(
    query: Optional[str] = Query(None, description="Search query"),
    category: Optional[KnowledgeCategory] = Query(None),
    status: Optional[KnowledgeStatus] = Query(None),
    author_id: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    language: SupportedLanguage = Query(SupportedLanguage.KOREAN),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    List knowledge articles with filtering.
    Published articles visible to all, others based on role.
    """
    search_request = KnowledgeSearchRequest(
        query=query,
        category=category,
        status=status,
        author_id=author_id,
        tags=tags.split(",") if tags else None,
        language=language,
        page=page,
        limit=limit
    )

    articles, total = await service.list_articles(
        request=search_request,
        user_id=current_user["id"],
        user_role=current_user.get("role", "user")
    )

    return {
        "status": "success",
        "data": {
            "articles": [a.model_dump() for a in articles],
            "total": total,
            "page": page,
            "limit": limit
        }
    }


@router.get("/my", response_model=dict)
async def list_my_articles(
    status: Optional[KnowledgeStatus] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """List current user's knowledge articles"""
    search_request = KnowledgeSearchRequest(
        author_id=current_user["id"],
        status=status,
        page=page,
        limit=limit
    )

    articles, total = await service.list_articles(
        request=search_request,
        user_id=current_user["id"],
        user_role=current_user.get("role", "user")
    )

    return {
        "status": "success",
        "data": {
            "articles": [a.model_dump() for a in articles],
            "total": total,
            "page": page,
            "limit": limit
        }
    }


@router.get("/pending-reviews", response_model=dict)
async def list_pending_reviews(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    List articles pending review for current user.
    Only for reviewers (senior, leader, admin).
    """
    user_role = current_user.get("role", "user")
    if not can_review(user_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "검수 권한이 없습니다."}
        )

    articles, total = await service.list_pending_reviews(
        reviewer_id=current_user["id"],
        page=page,
        limit=limit
    )

    return {
        "status": "success",
        "data": {
            "articles": [a.model_dump() for a in articles],
            "total": total,
            "page": page,
            "limit": limit
        }
    }


@router.get("/categories", response_model=dict)
async def get_categories(
    language: str = Query("ko", description="Language code (ko, ja, en)"),
    service = Depends(get_service)
):
    """Get all knowledge categories with localized names"""
    categories = await service.get_categories(language)
    return {
        "status": "success",
        "data": {
            "categories": categories
        }
    }


@router.get("/top-contributors", response_model=dict)
async def get_top_contributors(
    limit: int = Query(10, ge=1, le=50),
    period: str = Query("all_time", description="all_time, monthly, weekly"),
    service = Depends(get_service)
):
    """Get top knowledge contributors by recommendation count"""
    contributors = await service.get_top_contributors(limit=limit, period=period)

    return {
        "status": "success",
        "data": {
            "contributors": [c.model_dump() for c in contributors],
            "period": period
        }
    }


@router.get("/{article_id}", response_model=dict)
async def get_knowledge_article(
    article_id: str,
    language: SupportedLanguage = Query(SupportedLanguage.KOREAN),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get knowledge article by ID with optional translation"""
    article = await service.get_article(article_id)

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "지식 문서를 찾을 수 없습니다."}
        )

    # Check visibility
    user_role = current_user.get("role", "user")
    if article.status != KnowledgeStatus.PUBLISHED:
        if article.author_id != current_user["id"] and not can_review(user_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": "접근 권한이 없습니다."}
            )

    # Increment view count for published articles
    if article.status == KnowledgeStatus.PUBLISHED:
        await service.increment_view_count(article_id)

    # Get translation if available
    current_translation = article.translations.get(language.value)

    # Check if user has recommended
    has_recommended = await service.has_recommended(article_id, current_user["id"])

    return {
        "status": "success",
        "data": {
            "article": article.model_dump(),
            "current_translation": current_translation.model_dump() if current_translation else None,
            "user_recommended": has_recommended
        }
    }


@router.put("/{article_id}", response_model=dict)
async def update_knowledge_article(
    article_id: str,
    request: UpdateKnowledgeRequest,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Update knowledge article (author only, draft/rejected status only)"""
    article = await service.update_article(
        article_id=article_id,
        request=request,
        user_id=current_user["id"]
    )

    if not article:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UPDATE_FAILED", "message": "문서를 수정할 수 없습니다. 권한이 없거나 수정 가능한 상태가 아닙니다."}
        )

    return {
        "status": "success",
        "data": {
            "article": article.model_dump()
        },
        "message": "지식 문서가 수정되었습니다."
    }


@router.delete("/{article_id}", response_model=dict)
async def delete_knowledge_article(
    article_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Delete knowledge article (author or admin only)"""
    success = await service.delete_article(
        article_id=article_id,
        user_id=current_user["id"],
        user_role=current_user.get("role", "user")
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "DELETE_FAILED", "message": "문서를 삭제할 수 없습니다."}
        )

    return {
        "status": "success",
        "message": "지식 문서가 삭제되었습니다."
    }


# ==================== Workflow Operations ====================

@router.post("/{article_id}/submit", response_model=dict)
async def submit_for_review(
    article_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service),
    notif_service = Depends(get_notif_service)
):
    """
    Submit knowledge article for review.
    Automatically assigns a reviewer and sends notifications.
    """
    article = await service.submit_for_review(
        article_id=article_id,
        user_id=current_user["id"]
    )

    if not article:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SUBMIT_FAILED", "message": "검수 요청에 실패했습니다. 권한이 없거나 제출 가능한 상태가 아닙니다."}
        )

    # Send notifications to reviewers
    await notif_service.notify_reviewers(
        knowledge_id=article.id,
        knowledge_title=article.title,
        author_name=article.author_name,
        assigned_reviewer_id=article.reviewer_id
    )

    return {
        "status": "success",
        "data": {
            "article": article.model_dump(),
            "reviewer_assigned": article.reviewer_name
        },
        "message": f"검수가 요청되었습니다. 검수자: {article.reviewer_name or '배정 중'}"
    }


@router.post("/{article_id}/review", response_model=dict)
async def review_article(
    article_id: str,
    request: ReviewActionRequest,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service),
    notif_service = Depends(get_notif_service)
):
    """
    Review knowledge article (approve, reject, or request changes).
    Only assigned reviewer can review.
    """
    user_role = current_user.get("role", "user")
    if not can_review(user_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "PERMISSION_DENIED", "message": "검수 권한이 없습니다."}
        )

    article = await service.review_article(
        article_id=article_id,
        reviewer_id=current_user["id"],
        reviewer_name=current_user.get("username", "Unknown"),
        action=request.action,
        comment=request.comment
    )

    if not article:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "REVIEW_FAILED", "message": "검수에 실패했습니다. 권한이 없거나 검수 가능한 상태가 아닙니다."}
        )

    # Notify author about review result
    await notif_service.notify_author_review_result(
        author_id=article.author_id,
        knowledge_id=article.id,
        knowledge_title=article.title,
        action=request.action,
        reviewer_name=current_user.get("username", "Unknown"),
        comment=request.comment
    )

    action_messages = {
        "approve": "승인되었습니다.",
        "reject": "반려되었습니다.",
        "request_changes": "수정이 요청되었습니다."
    }

    return {
        "status": "success",
        "data": {
            "article": article.model_dump()
        },
        "message": f"지식 문서가 {action_messages.get(request.action, '처리되었습니다.')}"
    }


# ==================== Recommendation Operations ====================

@router.post("/{article_id}/recommend", response_model=dict)
async def recommend_article(
    article_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Add recommendation to a published article"""
    success, count = await service.recommend_article(
        article_id=article_id,
        user_id=current_user["id"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "RECOMMEND_FAILED", "message": "추천에 실패했습니다. 이미 추천했거나 게시된 문서가 아닙니다."}
        )

    return {
        "status": "success",
        "data": {
            "knowledge_id": article_id,
            "recommendation_count": count,
            "user_recommended": True
        },
        "message": "추천되었습니다."
    }


@router.delete("/{article_id}/recommend", response_model=dict)
async def remove_recommendation(
    article_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Remove recommendation from an article"""
    success, count = await service.remove_recommendation(
        article_id=article_id,
        user_id=current_user["id"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "REMOVE_RECOMMEND_FAILED", "message": "추천 취소에 실패했습니다."}
        )

    return {
        "status": "success",
        "data": {
            "knowledge_id": article_id,
            "recommendation_count": count,
            "user_recommended": False
        },
        "message": "추천이 취소되었습니다."
    }
