"""
History API Router
질의 히스토리 관리 API
"""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.history import (
    HistoryListItem,
    HistoryDetail,
    ConversationListItem,
    ConversationCreate,
    ConversationDetail,
)
from ..core.deps import get_current_user, get_history_service

router = APIRouter(prefix="/history", tags=["History"])


@router.get(
    "",
    response_model=PaginatedResponse[dict],
    summary="질의 히스토리 목록",
    description="질의 히스토리를 페이지네이션하여 조회합니다."
)
async def list_history(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    conversation_id: Optional[str] = Query(default=None, description="대화 세션 필터"),
    strategy: Optional[str] = Query(default=None, description="전략 필터"),
    from_date: Optional[str] = Query(default=None, description="시작 날짜 (ISO 8601)"),
    to_date: Optional[str] = Query(default=None, description="종료 날짜 (ISO 8601)"),
    current_user: dict = Depends(get_current_user),
    history_service = Depends(get_history_service)
):
    """List query history with filters"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await history_service.list_history(
        user_id=current_user["id"],
        page=page,
        limit=limit,
        conversation_id=conversation_id,
        strategy=strategy,
        from_date=from_date,
        to_date=to_date
    )

    history_items = [HistoryListItem(**item) for item in result["history"]]

    return PaginatedResponse(
        data={"history": history_items},
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
    "/{query_id}",
    response_model=SuccessResponse[HistoryDetail],
    summary="질의 상세 조회",
    description="특정 질의의 상세 정보를 조회합니다."
)
async def get_history_detail(
    query_id: str,
    current_user: dict = Depends(get_current_user),
    history_service = Depends(get_history_service)
):
    """Get query history detail"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await history_service.get_history_detail(query_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "HISTORY_NOT_FOUND", "message": "질의 기록을 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=HistoryDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{query_id}",
    response_model=SuccessResponse[dict],
    summary="질의 히스토리 삭제",
    description="특정 질의 기록을 삭제합니다."
)
async def delete_history(
    query_id: str,
    current_user: dict = Depends(get_current_user),
    history_service = Depends(get_history_service)
):
    """Delete a query history entry"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    success = await history_service.delete_history(query_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail={"code": "HISTORY_NOT_FOUND", "message": "질의 기록을 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"message": "질의 기록이 삭제되었습니다.", "query_id": query_id},
        meta=MetaInfo(request_id=request_id)
    )


# Conversations endpoints
conversations_router = APIRouter(prefix="/conversations", tags=["Conversations"])


@conversations_router.get(
    "",
    response_model=PaginatedResponse[dict],
    summary="대화 세션 목록",
    description="대화 세션 목록을 조회합니다."
)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    history_service = Depends(get_history_service)
):
    """List conversation sessions"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await history_service.list_conversations(
        user_id=current_user["id"],
        page=page,
        limit=limit
    )

    conversations = [ConversationListItem(**conv) for conv in result["conversations"]]

    return PaginatedResponse(
        data={"conversations": conversations},
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


@conversations_router.post(
    "",
    response_model=SuccessResponse[ConversationListItem],
    summary="대화 세션 생성",
    description="새로운 대화 세션을 생성합니다."
)
async def create_conversation(
    request: ConversationCreate,
    current_user: dict = Depends(get_current_user),
    history_service = Depends(get_history_service)
):
    """Create a new conversation session"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await history_service.create_conversation(
        user_id=current_user["id"],
        title=request.title
    )

    return SuccessResponse(
        data=ConversationListItem(**result),
        meta=MetaInfo(request_id=request_id)
    )


@conversations_router.delete(
    "/{conversation_id}",
    response_model=SuccessResponse[dict],
    summary="대화 세션 삭제",
    description="대화 세션과 포함된 모든 히스토리를 삭제합니다."
)
async def delete_conversation(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    history_service = Depends(get_history_service)
):
    """Delete a conversation and all its history"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await history_service.delete_conversation(conversation_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONVERSATION_NOT_FOUND", "message": "대화 세션을 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={
            "message": "대화 세션이 삭제되었습니다.",
            "conversation_id": conversation_id,
            "deleted_queries": result.get("deleted_queries", 0)
        },
        meta=MetaInfo(request_id=request_id)
    )
