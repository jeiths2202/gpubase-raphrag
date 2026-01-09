"""
IMS Chat Router - AI Chat endpoints for IMS issues

Provides chat endpoints for conversing with AI about crawled IMS issues.
Chat context is LIMITED to searched/crawled issues only.
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
from ..services.ims_rag_integration import get_ims_rag_service, IMSRAGIntegrationService

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
