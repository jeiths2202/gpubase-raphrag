"""Chat API Router — POST /api/v1/legacy/chat/stream

SSE streaming chat endpoint for Legacy Modernization AI Assistant.
Routes to HOST (vLLM), OpenFrame (Agentic RAG), or ALL (both).
"""

import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...core.deps import get_current_user
from ..services.chat_service import get_chat_service
from .chat_schemas import ModernizationChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legacy", tags=["Legacy Modernization Chat"])


@router.post(
    "/chat/stream",
    summary="Modernization AI chat (SSE streaming)",
    description="Stream chat responses from HOST analysis, OpenFrame RAG, or both.",
)
async def stream_chat(
    request: ModernizationChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """SSE streaming chat for Legacy Modernization AI Assistant."""
    user_id = current_user.get("user_id", "anonymous")
    logger.info(
        f"Legacy chat from user {user_id}, "
        f"system_type={request.system_type}, lang={request.language}"
    )

    async def generate():
        try:
            service = get_chat_service()
            async for event in service.stream_chat(request, user_id=user_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Legacy chat stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
