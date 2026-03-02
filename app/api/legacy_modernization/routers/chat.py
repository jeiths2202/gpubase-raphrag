"""Chat & Notes API Router for Legacy Modernization AI Assistant.

Endpoints:
- POST /api/v1/legacy/chat/stream  — SSE streaming chat
- GET  /api/v1/legacy/notes        — List notes
- POST /api/v1/legacy/notes        — Create note
- DELETE /api/v1/legacy/notes/{id} — Delete note
"""

import json
import logging
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ...core.deps import get_current_user
from ..services.chat_service import get_chat_service
from .chat_schemas import ModernizationChatRequest, NoteCreateRequest, NoteResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legacy", tags=["Legacy Modernization Chat"])


# ============================================================================
# Chat endpoint
# ============================================================================

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


# ============================================================================
# Notes endpoints (uses NoteRepository via PostgreSQL)
# ============================================================================

def _get_note_repository():
    """Get NoteRepository from DI container."""
    try:
        from ...core.container import Container
        container = Container.get_instance()
        return container.get("note_repository")
    except Exception as e:
        logger.error(f"NoteRepository not available: {e}")
        return None


@router.get(
    "/notes",
    response_model=List[NoteResponse],
    summary="List modernization notes",
)
async def list_notes(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """List notes for the current user (filtered to modernization source)."""
    repo = _get_note_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Note service unavailable")

    user_id = current_user.get("user_id", current_user.get("id", "anonymous"))
    notes = await repo.get_by_user(user_id=user_id, skip=skip, limit=limit)

    # Filter to modernization notes (tagged with 'modernization')
    mod_notes = [n for n in notes if "modernization" in (n.tags or [])]

    return [
        NoteResponse(
            id=n.id,
            content=n.content,
            tags=n.tags or [],
            created_at=n.created_at.isoformat() if n.created_at else "",
            updated_at=n.updated_at.isoformat() if n.updated_at else "",
        )
        for n in mod_notes
    ]


@router.post(
    "/notes",
    response_model=NoteResponse,
    summary="Create a modernization note",
)
async def create_note(
    body: NoteCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new note tagged with 'modernization'."""
    repo = _get_note_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Note service unavailable")

    user_id = current_user.get("user_id", current_user.get("id", "anonymous"))

    from ...repositories.note_repository import NoteEntity

    tags = list(set((body.tags or []) + ["modernization"]))

    entity = NoteEntity(
        id=str(uuid4()),
        title=body.content[:50],  # Use first 50 chars as title
        content=body.content,
        user_id=user_id,
        tags=tags,
    )

    created = await repo.create(entity)

    return NoteResponse(
        id=created.id,
        content=created.content,
        tags=created.tags or [],
        created_at=created.created_at.isoformat() if created.created_at else "",
        updated_at=created.updated_at.isoformat() if created.updated_at else "",
    )


@router.delete(
    "/notes/{note_id}",
    summary="Delete a modernization note",
)
async def delete_note(
    note_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a note by ID."""
    repo = _get_note_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Note service unavailable")

    # Verify the note belongs to the user
    note = await repo.get_by_id(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    user_id = current_user.get("user_id", current_user.get("id", "anonymous"))
    if note.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    await repo.delete(note_id)
    return {"deleted": True, "note_id": note_id}
