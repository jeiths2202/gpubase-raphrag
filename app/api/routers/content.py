"""
Content Generation API Router
AI 기반 콘텐츠 생성 API
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.content import (
    ContentType,
    ContentStatus,
    GenerateContentRequest,
    GeneratedContent,
    ContentListItem,
    GenerateContentResponse,
    ContentDetailResponse,
    SummaryContent,
    FAQContent,
    FAQItem,
    StudyGuideContent,
    StudyGuideSection,
    QuizQuestion,
    BriefingContent,
    BriefingSection,
    TimelineContent,
    TimelineEvent,
    TOCContent,
    TOCItem,
    KeyTopicsContent,
    KeyTopic,
)
from ..core.deps import get_current_user, get_content_service

router = APIRouter(prefix="/content", tags=["Content Generation"])


@router.post(
    "/generate",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="콘텐츠 생성",
    description="문서를 분석하여 AI 기반 콘텐츠를 생성합니다."
)
async def generate_content(
    request: GenerateContentRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate AI-based content from documents"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await content_service.start_generation(
        document_ids=request.document_ids,
        content_type=request.content_type,
        language=request.language,
        options=request.options,
        user_id=current_user.get("user_id", "anonymous")
    )

    # Start background generation
    background_tasks.add_task(
        content_service.generate_content_async,
        result["content_id"]
    )

    return SuccessResponse(
        data=GenerateContentResponse(
            content_id=result["content_id"],
            content_type=request.content_type,
            status=ContentStatus.GENERATING,
            message=f"{request.content_type.value} 생성이 시작되었습니다."
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "",
    response_model=PaginatedResponse[dict],
    summary="생성된 콘텐츠 목록",
    description="생성된 콘텐츠 목록을 조회합니다."
)
async def list_contents(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    content_type: Optional[ContentType] = Query(default=None),
    status: Optional[ContentStatus] = Query(default=None),
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """List generated contents"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await content_service.list_contents(
        user_id=current_user.get("user_id"),
        page=page,
        limit=limit,
        content_type=content_type,
        status=status
    )

    return PaginatedResponse(
        data={"contents": result["contents"]},
        meta=MetaInfo(request_id=request_id),
        pagination=PaginationMeta(
            page=page,
            limit=limit,
            total_items=result["total"],
            total_pages=(result["total"] + limit - 1) // limit,
            has_next=page * limit < result["total"],
            has_prev=page > 1
        )
    )


@router.get(
    "/{content_id}",
    response_model=SuccessResponse[ContentDetailResponse],
    summary="콘텐츠 상세 조회",
    description="생성된 콘텐츠의 상세 정보를 조회합니다."
)
async def get_content(
    content_id: str,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Get content details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await content_service.get_content(content_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONTENT_NOT_FOUND", "message": "콘텐츠를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=ContentDetailResponse(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{content_id}",
    response_model=SuccessResponse[dict],
    summary="콘텐츠 삭제",
    description="생성된 콘텐츠를 삭제합니다."
)
async def delete_content(
    content_id: str,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Delete generated content"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await content_service.delete_content(content_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONTENT_NOT_FOUND", "message": "콘텐츠를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"content_id": content_id, "message": "콘텐츠가 삭제되었습니다."},
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/{content_id}/status",
    response_model=SuccessResponse[dict],
    summary="콘텐츠 생성 상태",
    description="콘텐츠 생성 진행 상태를 조회합니다."
)
async def get_content_status(
    content_id: str,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Get content generation status"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await content_service.get_content_status(content_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONTENT_NOT_FOUND", "message": "콘텐츠를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=result,
        meta=MetaInfo(request_id=request_id)
    )


# Convenience endpoints for each content type
@router.post(
    "/summary",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="문서 요약 생성",
    description="문서를 요약합니다."
)
async def generate_summary(
    document_ids: list[str],
    length: str = Query(default="medium", description="short, medium, long"),
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate document summary"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.SUMMARY,
        language=language,
        options={"length": length}
    )
    return await generate_content(request, background_tasks, current_user, content_service)


@router.post(
    "/faq",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="FAQ 생성",
    description="문서 기반 FAQ를 생성합니다."
)
async def generate_faq(
    document_ids: list[str],
    max_questions: int = Query(default=10, ge=3, le=30),
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate FAQ from documents"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.FAQ,
        language=language,
        options={"max_questions": max_questions}
    )
    return await generate_content(request, background_tasks, current_user, content_service)


@router.post(
    "/study-guide",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="학습 가이드 생성",
    description="문서 기반 학습 가이드를 생성합니다."
)
async def generate_study_guide(
    document_ids: list[str],
    include_quiz: bool = Query(default=True),
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate study guide from documents"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.STUDY_GUIDE,
        language=language,
        options={"include_quiz": include_quiz}
    )
    return await generate_content(request, background_tasks, current_user, content_service)


@router.post(
    "/briefing",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="브리핑 문서 생성",
    description="문서 기반 브리핑 문서를 생성합니다."
)
async def generate_briefing(
    document_ids: list[str],
    audience: str = Query(default="general", description="executive, technical, general"),
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate briefing document"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.BRIEFING,
        language=language,
        options={"audience": audience}
    )
    return await generate_content(request, background_tasks, current_user, content_service)


@router.post(
    "/timeline",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="타임라인 생성",
    description="문서에서 시간순 이벤트를 추출합니다."
)
async def generate_timeline(
    document_ids: list[str],
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate timeline from documents"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.TIMELINE,
        language=language,
        options={}
    )
    return await generate_content(request, background_tasks, current_user, content_service)


@router.post(
    "/toc",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="목차 생성",
    description="문서의 목차를 생성합니다."
)
async def generate_toc(
    document_ids: list[str],
    max_depth: int = Query(default=3, ge=1, le=5),
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Generate table of contents"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.TOC,
        language=language,
        options={"max_depth": max_depth}
    )
    return await generate_content(request, background_tasks, current_user, content_service)


@router.post(
    "/key-topics",
    response_model=SuccessResponse[GenerateContentResponse],
    summary="핵심 주제 추출",
    description="문서에서 핵심 주제를 추출합니다."
)
async def extract_key_topics(
    document_ids: list[str],
    max_topics: int = Query(default=10, ge=3, le=20),
    language: str = Query(default="auto"),
    background_tasks: BackgroundTasks = None,
    current_user: dict = Depends(get_current_user),
    content_service = Depends(get_content_service)
):
    """Extract key topics from documents"""
    request = GenerateContentRequest(
        document_ids=document_ids,
        content_type=ContentType.KEY_TOPICS,
        language=language,
        options={"max_topics": max_topics}
    )
    return await generate_content(request, background_tasks, current_user, content_service)
