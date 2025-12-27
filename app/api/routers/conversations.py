"""
Conversations API Router

Provides endpoints for conversation management including:
- Conversation CRUD operations
- Message operations
- Regenerate and fork functionality
- Search and statistics

All endpoints require authentication and enforce user ownership.
"""
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query

from ..models.base import SuccessResponse, MetaInfo, PaginatedResponse
from ..models.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationDetail,
    ConversationListItem,
    ConversationSearchRequest,
    ConversationSearchResult,
    MessageCreate,
    MessageResponse,
    MessageFeedback,
    RegenerateRequest,
    RegenerateResponse,
    ConversationForkRequest,
    ConversationForkResponse,
    SummaryResponse,
)
from ..core.deps import get_current_user
from ..services.conversation_service import get_conversation_service, ConversationService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def _generate_request_id() -> str:
    """Generate a unique request ID."""
    return f"req_{uuid.uuid4().hex[:12]}"


# ==================== Conversation CRUD ====================

@router.get(
    "",
    response_model=PaginatedResponse[ConversationListItem],
    summary="대화 목록",
    description="사용자의 대화 목록을 조회합니다."
)
async def list_conversations(
    skip: int = Query(0, ge=0, description="건너뛸 항목 수"),
    limit: int = Query(50, ge=1, le=100, description="최대 조회 수"),
    include_archived: bool = Query(False, description="보관된 대화 포함 여부"),
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    List conversations for the authenticated user.

    Returns paginated list of conversations ordered by updated_at DESC.
    """
    request_id = _generate_request_id()

    conversations = await service.list_conversations(
        user_id=current_user["id"],
        skip=skip,
        limit=limit,
        include_archived=include_archived
    )

    # Get total count for pagination
    stats = await service.get_user_stats(current_user["id"])
    total = stats["active_conversations"]
    if include_archived:
        total += stats["archived_conversations"]

    return PaginatedResponse(
        data=conversations,
        meta=MetaInfo(request_id=request_id),
        pagination={
            "total": total,
            "skip": skip,
            "limit": limit,
            "has_more": skip + len(conversations) < total
        }
    )


@router.post(
    "",
    response_model=SuccessResponse[ConversationDetail],
    status_code=status.HTTP_201_CREATED,
    summary="대화 생성",
    description="새 대화를 생성합니다."
)
async def create_conversation(
    request: ConversationCreate,
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Create a new conversation.

    Returns the created conversation with initial empty message list.
    """
    request_id = _generate_request_id()

    conversation = await service.create_conversation(
        user_id=current_user["id"],
        title=request.title,
        project_id=request.project_id,
        session_id=request.session_id,
        strategy=request.strategy or "auto",
        language=request.language or "auto",
        metadata=request.metadata
    )

    # Get full detail
    detail = await service.get_conversation(
        conversation_id=conversation.id,
        user_id=current_user["id"],
        include_messages=True
    )

    return SuccessResponse(
        data=detail,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/{conversation_id}",
    response_model=SuccessResponse[ConversationDetail],
    summary="대화 상세",
    description="대화 상세 정보와 메시지를 조회합니다."
)
async def get_conversation(
    conversation_id: str,
    include_messages: bool = Query(True, description="메시지 포함 여부"),
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Get conversation detail with messages.

    Only the conversation owner can access their conversations.
    """
    request_id = _generate_request_id()

    detail = await service.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user["id"],
        include_messages=include_messages
    )

    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CONVERSATION_NOT_FOUND",
                "message": "대화를 찾을 수 없습니다."
            }
        )

    return SuccessResponse(
        data=detail,
        meta=MetaInfo(request_id=request_id)
    )


@router.patch(
    "/{conversation_id}",
    response_model=SuccessResponse[ConversationDetail],
    summary="대화 수정",
    description="대화 제목, 상태 등을 수정합니다."
)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdate,
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Update conversation properties.

    Only the conversation owner can update their conversations.
    """
    request_id = _generate_request_id()

    updated = await service.update_conversation(
        conversation_id=conversation_id,
        user_id=current_user["id"],
        update=request
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CONVERSATION_NOT_FOUND",
                "message": "대화를 찾을 수 없습니다."
            }
        )

    # Get full detail
    detail = await service.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user["id"],
        include_messages=True
    )

    return SuccessResponse(
        data=detail,
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{conversation_id}",
    response_model=SuccessResponse[dict],
    summary="대화 삭제",
    description="대화를 삭제합니다 (기본: soft delete)."
)
async def delete_conversation(
    conversation_id: str,
    hard_delete: bool = Query(False, description="영구 삭제 여부"),
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Delete a conversation.

    By default, performs soft delete (can be restored).
    Set hard_delete=true for permanent deletion.
    """
    request_id = _generate_request_id()

    deleted = await service.delete_conversation(
        conversation_id=conversation_id,
        user_id=current_user["id"],
        hard_delete=hard_delete
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CONVERSATION_NOT_FOUND",
                "message": "대화를 찾을 수 없습니다."
            }
        )

    return SuccessResponse(
        data={"deleted": True, "conversation_id": conversation_id},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Message Operations ====================

@router.post(
    "/{conversation_id}/messages",
    response_model=SuccessResponse[MessageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="메시지 추가",
    description="대화에 메시지를 추가합니다."
)
async def add_message(
    conversation_id: str,
    request: MessageCreate,
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Add a message to a conversation.

    For user messages, this will store the message and optionally
    trigger context-aware processing.

    For system messages, admin privileges may be required.
    """
    request_id = _generate_request_id()

    try:
        if request.role.value == "user":
            message = await service.add_user_message(
                conversation_id=conversation_id,
                user_id=current_user["id"],
                content=request.content,
                parent_message_id=str(request.parent_message_id) if request.parent_message_id else None
            )
        elif request.role.value == "assistant":
            # Direct assistant message creation (typically internal use)
            message = await service.add_assistant_message(
                conversation_id=conversation_id,
                content=request.content,
                parent_message_id=str(request.parent_message_id) if request.parent_message_id else None,
                model=request.model
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_MESSAGE_ROLE",
                    "message": "시스템 메시지는 API로 직접 추가할 수 없습니다."
                }
            )

        response = MessageResponse(
            id=uuid.UUID(message.id),
            conversation_id=uuid.UUID(message.conversation_id),
            parent_message_id=uuid.UUID(message.parent_message_id) if message.parent_message_id else None,
            role=request.role,
            content=message.content,
            total_tokens=message.total_tokens,
            model=message.model,
            sources=message.sources,
            is_regenerated=message.is_regenerated,
            regeneration_count=message.regeneration_count,
            is_active_branch=message.is_active_branch,
            branch_depth=message.branch_depth,
            created_at=message.created_at,
            updated_at=message.updated_at
        )

        return SuccessResponse(
            data=response,
            meta=MetaInfo(request_id=request_id)
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ACCESS_DENIED",
                "message": str(e)
            }
        )


@router.get(
    "/{conversation_id}/messages",
    response_model=SuccessResponse[List[MessageResponse]],
    summary="메시지 목록",
    description="대화의 메시지 목록을 조회합니다."
)
async def get_messages(
    conversation_id: str,
    include_inactive_branches: bool = Query(False, description="비활성 브랜치 포함"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Get messages in a conversation.

    By default, returns only active branch messages.
    Set include_inactive_branches=true to include regenerated alternatives.
    """
    request_id = _generate_request_id()

    # Verify access
    detail = await service.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user["id"],
        include_messages=False
    )

    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CONVERSATION_NOT_FOUND",
                "message": "대화를 찾을 수 없습니다."
            }
        )

    # Get messages through repository
    messages = await service._repository.get_messages(
        conversation_id=conversation_id,
        include_inactive_branches=include_inactive_branches,
        skip=skip,
        limit=limit
    )

    response_messages = [
        service._entity_to_message_response(m) for m in messages
    ]

    return SuccessResponse(
        data=response_messages,
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/{conversation_id}/messages/{message_id}/feedback",
    response_model=SuccessResponse[dict],
    summary="피드백 추가",
    description="메시지에 피드백을 추가합니다."
)
async def add_feedback(
    conversation_id: str,
    message_id: str,
    request: MessageFeedback,
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Add feedback to a message.

    Feedback helps improve response quality over time.
    """
    request_id = _generate_request_id()

    # Verify conversation access
    detail = await service.get_conversation(
        conversation_id=conversation_id,
        user_id=current_user["id"],
        include_messages=False
    )

    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CONVERSATION_NOT_FOUND",
                "message": "대화를 찾을 수 없습니다."
            }
        )

    success = await service.add_feedback(
        message_id=message_id,
        user_id=current_user["id"],
        score=request.score,
        text=request.text
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "MESSAGE_NOT_FOUND",
                "message": "메시지를 찾을 수 없습니다."
            }
        )

    return SuccessResponse(
        data={"success": True, "message_id": message_id},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Regenerate & Fork ====================

@router.post(
    "/{conversation_id}/regenerate",
    response_model=SuccessResponse[RegenerateResponse],
    summary="응답 재생성",
    description="어시스턴트 응답을 재생성합니다."
)
async def regenerate_response(
    conversation_id: str,
    request: RegenerateRequest,
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Regenerate an assistant response.

    Creates a new response from the same prompt, marking the original
    as an inactive branch. Both versions are preserved.
    """
    request_id = _generate_request_id()

    try:
        # For now, regeneration requires calling RAG service externally
        # This endpoint expects the new content to be provided
        # In production, this would integrate with RAG service

        # Placeholder: In real implementation, call RAG service here
        # For now, we'll require the caller to provide new_content
        # via a modified request model or query param

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "code": "NOT_IMPLEMENTED",
                "message": "재생성 기능은 RAG 서비스 통합 후 사용 가능합니다. POST /query?conversation_id=... 를 사용하세요."
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "REGENERATE_FAILED",
                "message": str(e)
            }
        )


@router.post(
    "/{conversation_id}/fork",
    response_model=SuccessResponse[ConversationForkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="대화 분기",
    description="특정 시점에서 대화를 분기합니다."
)
async def fork_conversation(
    conversation_id: str,
    request: ConversationForkRequest,
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Fork a conversation from a specific message.

    Creates a new conversation containing messages up to the fork point.
    Both original and forked conversations are preserved independently.
    """
    request_id = _generate_request_id()

    try:
        fork_response = await service.fork_conversation(
            conversation_id=conversation_id,
            from_message_id=str(request.from_message_id),
            user_id=current_user["id"],
            new_title=request.new_title
        )

        return SuccessResponse(
            data=fork_response,
            meta=MetaInfo(request_id=request_id)
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "FORK_FAILED",
                "message": str(e)
            }
        )


# ==================== Search ====================

@router.get(
    "/search",
    response_model=SuccessResponse[List[ConversationSearchResult]],
    summary="대화 검색",
    description="대화 내용을 검색합니다."
)
async def search_conversations(
    q: str = Query(..., min_length=2, max_length=200, description="검색어"),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Search conversations by content.

    Performs full-text search across all message content
    in the user's conversations.
    """
    request_id = _generate_request_id()

    results = await service.search_conversations(
        user_id=current_user["id"],
        query=q,
        limit=limit
    )

    search_results = [
        ConversationSearchResult(
            conversation=conv,
            relevance_score=score
        )
        for conv, score in results
    ]

    return SuccessResponse(
        data=search_results,
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Statistics ====================

@router.get(
    "/stats",
    response_model=SuccessResponse[dict],
    summary="통계 조회",
    description="사용자의 대화 통계를 조회합니다."
)
async def get_stats(
    current_user: dict = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service)
):
    """
    Get conversation statistics for the current user.

    Returns counts of conversations, messages, and total tokens.
    """
    request_id = _generate_request_id()

    stats = await service.get_user_stats(current_user["id"])

    return SuccessResponse(
        data=stats,
        meta=MetaInfo(request_id=request_id)
    )
