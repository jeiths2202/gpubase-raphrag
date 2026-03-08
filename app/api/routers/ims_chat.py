"""
IMS Chat Router - AI Chat endpoints for IMS issues

Provides chat endpoints for conversing with AI about crawled IMS issues.
Chat context is LIMITED to searched/crawled issues only.

Semantic Search endpoints use BGE-M3 IR model for natural language search
over 21K+ embedded IMS issues.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID
import json
import logging

from ..core.deps import get_current_user
from ..models.ims_chat import (
    IMSChatRequest,
    IMSChatResponse,
    IMSChatStreamEvent,
    IMSChatConversation,
    IMSChatMessage,
    IMSChatConversationCreate,
    IMSChatHistoryRequest
)
from ..models.ims_semantic import (
    IMSSearchRequest,
    IMSSearchResponse,
    IMSSemanticChatRequest,
    IMSSummaryRequest,
    IMSSummaryResponse,
    IMSKnowledgeCreateRequest,
    IMSKnowledgeCreateResponse,
    IssueContent,
    RelatedIssuesResponse,
)
from ..services.ims_rag_integration import get_ims_rag_service, IMSRAGIntegrationService
from ..services.ims_semantic_search_service import (
    get_ims_semantic_search_service,
    IMSServiceUnavailableError,
    IMSLLMTimeoutError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ims-chat", tags=["IMS Chat"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequestBody(BaseModel):
    """Request body for chat endpoint"""
    question: str = Field(..., min_length=1, description="User's question about IMS issues")
    issue_ids: List[UUID] = Field(..., min_length=1, description="List of IMS issue IDs to use as context")
    conversation_id: Optional[UUID] = Field(None, description="Existing conversation ID to continue")
    language: str = Field("auto", description="Response language: auto, ko, ja, en")
    stream: bool = Field(True, description="Whether to stream the response")
    max_context_issues: int = Field(10, ge=1, le=50, description="Maximum issues to include in context")


class ConversationListResponse(BaseModel):
    """Response for listing conversations"""
    conversations: List[IMSChatConversation]
    total: int


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/", response_model=IMSChatResponse)
async def chat(
    request: ChatRequestBody,
    current_user: dict = Depends(get_current_user),
    service: IMSRAGIntegrationService = Depends(get_ims_rag_service)
):
    """
    Chat with AI about crawled IMS issues.

    The AI's knowledge is LIMITED to the provided issue_ids only.
    Use this endpoint after searching/crawling IMS issues.

    **Workflow**:
    1. Search/crawl IMS issues using `/api/v1/ims-crawler/jobs` or `/api/v1/ims-search/`
    2. Get the issue IDs from the search results
    3. Use this endpoint to chat about those specific issues

    **Example**:
    ```json
    {
        "question": "mscasmc 토큰 오류 해결 방법은?",
        "issue_ids": ["uuid-1", "uuid-2", "uuid-3"],
        "stream": false
    }
    ```

    **Note**: For streaming responses, set `stream: true` and use the `/stream` endpoint.
    """
    user_id = UUID(current_user["id"])

    try:
        # Convert to internal request model
        chat_request = IMSChatRequest(
            question=request.question,
            issue_ids=request.issue_ids,
            conversation_id=request.conversation_id,
            language=request.language,
            stream=False,  # Non-streaming endpoint
            max_context_issues=request.max_context_issues
        )

        response = await service.chat(chat_request, user_id)
        return response

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat failed: {str(e)}"
        )


@router.post("/stream")
async def chat_stream(
    request: ChatRequestBody,
    current_user: dict = Depends(get_current_user),
    service: IMSRAGIntegrationService = Depends(get_ims_rag_service)
):
    """
    Chat with AI about crawled IMS issues (streaming response).

    Returns Server-Sent Events (SSE) stream with the following event types:
    - `start`: Chat started, includes conversation_id and message_id
    - `token`: Response token (incremental content)
    - `sources`: Referenced IMS issues
    - `done`: Chat completed
    - `error`: Error occurred

    **Usage with EventSource**:
    ```javascript
    const eventSource = new EventSource('/api/v1/ims-chat/stream');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(data);
    };
    ```
    """
    user_id = UUID(current_user["id"])

    # Convert to internal request model
    chat_request = IMSChatRequest(
        question=request.question,
        issue_ids=request.issue_ids,
        conversation_id=request.conversation_id,
        language=request.language,
        stream=True,
        max_context_issues=request.max_context_issues
    )

    async def generate_sse():
        """Generate SSE events."""
        try:
            async for event in service.chat_stream(chat_request, user_id):
                event_data = json.dumps(event.data, ensure_ascii=False)
                yield f"event: {event.event}\ndata: {event_data}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    service: IMSRAGIntegrationService = Depends(get_ims_rag_service)
):
    """
    List recent chat conversations.

    Returns conversations sorted by last update time (newest first).
    """
    try:
        conversations = service.list_conversations(limit=limit)
        return ConversationListResponse(
            conversations=conversations,
            total=len(conversations)
        )
    except Exception as e:
        logger.error(f"List conversations error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list conversations: {str(e)}"
        )


@router.get("/conversations/{conversation_id}", response_model=IMSChatConversation)
async def get_conversation(
    conversation_id: UUID,
    current_user: dict = Depends(get_current_user),
    service: IMSRAGIntegrationService = Depends(get_ims_rag_service)
):
    """
    Get a specific conversation with full message history.
    """
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=List[IMSChatMessage])
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    service: IMSRAGIntegrationService = Depends(get_ims_rag_service)
):
    """
    Get messages for a specific conversation with pagination.
    """
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )

    messages = conversation.messages[offset:offset + limit]
    return messages


# ============================================================================
# Semantic Search Endpoints (BGE-M3 기반 자연어 검색)
# ============================================================================

@router.post("/search", response_model=IMSSearchResponse)
async def semantic_search(
    request: IMSSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    BGE-M3 임베딩 기반 IMS 이슈 시맨틱 검색.

    자연어 질의를 벡터로 변환하여 21K+ IMS 이슈에서 유사 이슈를 검색합니다.
    issue_id를 미리 알 필요 없이 자연어만으로 검색 가능.
    """
    service = get_ims_semantic_search_service()
    try:
        return await service.semantic_search(
            query=request.query,
            limit=request.limit,
            product_filter=request.product_filter,
        )
    except IMSServiceUnavailableError as e:
        logger.error(f"Semantic search service unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Search service unavailable: {str(e)}",
        )
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.post("/chat/semantic")
async def semantic_chat(
    request: IMSSemanticChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    시맨틱 검색 기반 채팅 (SSE streaming).

    자연어 질문 → BGE-M3 검색 → 이슈 컨텍스트 로드 → LLM 스트리밍 응답.
    issue_ids 없이 자연어 질문만으로 관련 이슈를 자동 검색하여 답변합니다.

    **SSE Events**: search_start, search_results, context_loaded, token, sources, done
    """
    service = get_ims_semantic_search_service()

    async def generate_sse():
        try:
            async for event in service.chat_with_search(request):
                event_data = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {event['event']}\ndata: {event_data}\n\n"
        except Exception as e:
            logger.error(f"Semantic chat SSE error: {e}")
            error_data = json.dumps({"message": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/issues/{ims_id}", response_model=IssueContent)
async def get_issue_detail(
    ims_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    IMS 이슈 상세 내용 조회 (텍스트 파일 기반).

    이슈 메타데이터, 상세 내용, 조치 이력, 참조된 관련 이슈/URL 정보를 반환합니다.
    """
    if not ims_id.isdigit() or len(ims_id) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IMS ID format: {ims_id}",
        )
    service = get_ims_semantic_search_service()
    issue = service.get_issue_content(ims_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IMS issue {ims_id} not found",
        )
    return issue


@router.get("/issues/{ims_id}/related", response_model=RelatedIssuesResponse)
async def get_related_issues(
    ims_id: str,
    depth: int = 1,
    current_user: dict = Depends(get_current_user),
):
    """
    IMS 이슈 내 참조된 관련 이슈 목록 (multi-depth).

    이슈 본문에서 IMS#XXXXXX 패턴을 추출하여 관련 이슈 정보를 반환합니다.
    depth 파라미터로 탐색 깊이를 조절합니다 (기본 1, 최대 3).
    """
    if not ims_id.isdigit() or len(ims_id) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid IMS ID format: {ims_id}",
        )
    depth = min(max(depth, 1), 3)  # 1~3 범위 제한
    service = get_ims_semantic_search_service()
    issue = service.get_issue_content(ims_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IMS issue {ims_id} not found",
        )
    return service.get_related_issues(ims_id, depth=depth)


@router.post("/issues/summarize", response_model=IMSSummaryResponse)
async def summarize_issue(
    request: IMSSummaryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    LLM 기반 IMS 이슈 요약.

    이슈 내용을 분석하여 핵심 요약, 주요 포인트, 해결 방법을 생성합니다.
    """
    service = get_ims_semantic_search_service()
    try:
        result = await service.summarize_issue(request)
    except IMSLLMTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"LLM service timed out: {str(e)}",
        )
    except IMSServiceUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service unavailable: {str(e)}",
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"IMS issue {request.ims_id} not found",
        )
    return result


@router.post("/knowledge/create", response_model=IMSKnowledgeCreateResponse)
async def create_knowledge(
    request: IMSKnowledgeCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    IMS 이슈 기반 지식 문서 생성.

    하나 이상의 IMS 이슈 내용을 분석하여 재사용 가능한 지식 문서(Markdown)를 생성합니다.
    """
    service = get_ims_semantic_search_service()
    try:
        result = await service.create_knowledge(request)
    except IMSLLMTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"LLM service timed out: {str(e)}",
        )
    except IMSServiceUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM service unavailable: {str(e)}",
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid IMS issues found for the provided IDs",
        )
    return result
