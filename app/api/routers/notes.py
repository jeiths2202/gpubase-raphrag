"""
Notes API Router
노트 및 메모 관리 API
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Body

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.note import (
    NoteType,
    NoteSource,
    CreateNoteRequest,
    UpdateNoteRequest,
    CreateFolderRequest,
    UpdateFolderRequest,
    SaveAIResponseRequest,
    ExportNotesRequest,
    SearchNotesRequest,
    NoteFolder,
    NoteListItem,
    NoteDetail,
    NoteExportResult,
    NoteSearchResult,
    NoteStats,
)
from ..core.deps import get_current_user, get_note_service

router = APIRouter(prefix="/notes", tags=["Notes"])


# ==================== Note CRUD ====================

@router.post(
    "",
    response_model=SuccessResponse[NoteDetail],
    summary="노트 생성",
    description="새로운 노트를 생성합니다."
)
async def create_note(
    request: CreateNoteRequest,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Create a new note"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.create_note(
        title=request.title,
        content=request.content,
        note_type=request.note_type,
        folder_id=request.folder_id,
        project_id=request.project_id,
        tags=request.tags,
        source=request.source,
        source_reference=request.source_reference,
        color=request.color,
        user_id=current_user.get("user_id", "anonymous")
    )

    return SuccessResponse(
        data=NoteDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "",
    response_model=PaginatedResponse[dict],
    summary="노트 목록 조회",
    description="노트 목록을 페이지네이션하여 조회합니다."
)
async def list_notes(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    folder_id: Optional[str] = Query(default=None, description="폴더 ID"),
    project_id: Optional[str] = Query(default=None, description="프로젝트 ID"),
    note_type: Optional[NoteType] = Query(default=None, description="노트 유형"),
    tags: Optional[str] = Query(default=None, description="태그 (쉼표 구분)"),
    pinned_only: bool = Query(default=False, description="고정된 노트만"),
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """List notes with filtering"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    result = await note_service.list_notes(
        user_id=current_user.get("user_id"),
        page=page,
        limit=limit,
        folder_id=folder_id,
        project_id=project_id,
        note_type=note_type,
        tags=tag_list,
        pinned_only=pinned_only
    )

    return PaginatedResponse(
        data={"notes": result["notes"]},
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
    "/stats",
    response_model=SuccessResponse[NoteStats],
    summary="노트 통계",
    description="노트 사용 통계를 조회합니다."
)
async def get_note_stats(
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Get note statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.get_stats(current_user.get("user_id"))

    return SuccessResponse(
        data=NoteStats(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/tags",
    response_model=SuccessResponse[dict],
    summary="태그 목록",
    description="사용 중인 모든 태그를 조회합니다."
)
async def list_tags(
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """List all tags"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.list_tags(current_user.get("user_id"))

    return SuccessResponse(
        data={"tags": result},
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/{note_id}",
    response_model=SuccessResponse[NoteDetail],
    summary="노트 상세 조회",
    description="노트의 상세 정보를 조회합니다."
)
async def get_note(
    note_id: str,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Get note details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.get_note(note_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOTE_NOT_FOUND", "message": "노트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=NoteDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.put(
    "/{note_id}",
    response_model=SuccessResponse[NoteDetail],
    summary="노트 수정",
    description="노트를 수정합니다."
)
async def update_note(
    note_id: str,
    request: UpdateNoteRequest,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Update a note"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.update_note(
        note_id=note_id,
        title=request.title,
        content=request.content,
        folder_id=request.folder_id,
        tags=request.tags,
        color=request.color,
        is_pinned=request.is_pinned
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOTE_NOT_FOUND", "message": "노트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=NoteDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{note_id}",
    response_model=SuccessResponse[dict],
    summary="노트 삭제",
    description="노트를 삭제합니다."
)
async def delete_note(
    note_id: str,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Delete a note"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.delete_note(note_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOTE_NOT_FOUND", "message": "노트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"note_id": note_id, "message": "노트가 삭제되었습니다."},
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/{note_id}/pin",
    response_model=SuccessResponse[dict],
    summary="노트 고정/해제",
    description="노트를 고정하거나 해제합니다."
)
async def toggle_pin(
    note_id: str,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Toggle note pin status"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.toggle_pin(note_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOTE_NOT_FOUND", "message": "노트를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"note_id": note_id, "is_pinned": result["is_pinned"]},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== AI Response Save ====================

@router.post(
    "/from-ai-response",
    response_model=SuccessResponse[NoteDetail],
    summary="AI 응답 저장",
    description="AI 응답을 노트로 저장합니다."
)
async def save_ai_response(
    request: SaveAIResponseRequest,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Save AI response as a note"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.save_ai_response(
        query_id=request.query_id,
        title=request.title,
        folder_id=request.folder_id,
        project_id=request.project_id,
        tags=request.tags,
        user_id=current_user.get("user_id", "anonymous")
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "QUERY_NOT_FOUND", "message": "쿼리를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=NoteDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Folders ====================

@router.post(
    "/folders",
    response_model=SuccessResponse[NoteFolder],
    summary="폴더 생성",
    description="새로운 폴더를 생성합니다."
)
async def create_folder(
    request: CreateFolderRequest,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Create a new folder"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.create_folder(
        name=request.name,
        parent_id=request.parent_id,
        project_id=request.project_id,
        color=request.color,
        icon=request.icon,
        user_id=current_user.get("user_id", "anonymous")
    )

    return SuccessResponse(
        data=NoteFolder(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/folders",
    response_model=SuccessResponse[dict],
    summary="폴더 목록 조회",
    description="폴더 목록을 트리 구조로 조회합니다."
)
async def list_folders(
    project_id: Optional[str] = Query(default=None, description="프로젝트 ID"),
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """List folders in tree structure"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.list_folders(
        user_id=current_user.get("user_id"),
        project_id=project_id
    )

    return SuccessResponse(
        data={"folders": result},
        meta=MetaInfo(request_id=request_id)
    )


@router.put(
    "/folders/{folder_id}",
    response_model=SuccessResponse[NoteFolder],
    summary="폴더 수정",
    description="폴더를 수정합니다."
)
async def update_folder(
    folder_id: str,
    request: UpdateFolderRequest,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Update a folder"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.update_folder(
        folder_id=folder_id,
        name=request.name,
        parent_id=request.parent_id,
        color=request.color,
        icon=request.icon
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "FOLDER_NOT_FOUND", "message": "폴더를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=NoteFolder(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/folders/{folder_id}",
    response_model=SuccessResponse[dict],
    summary="폴더 삭제",
    description="폴더와 하위 노트를 삭제합니다."
)
async def delete_folder(
    folder_id: str,
    move_to_root: bool = Query(default=True, description="하위 노트를 루트로 이동"),
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Delete a folder"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.delete_folder(folder_id, move_to_root=move_to_root)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "FOLDER_NOT_FOUND", "message": "폴더를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data={"folder_id": folder_id, "message": "폴더가 삭제되었습니다.", **result},
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Search ====================

@router.post(
    "/search",
    response_model=SuccessResponse[dict],
    summary="노트 검색",
    description="노트를 검색합니다."
)
async def search_notes(
    request: SearchNotesRequest,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Search notes"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.search_notes(
        user_id=current_user.get("user_id"),
        query=request.query,
        folder_id=request.folder_id,
        project_id=request.project_id,
        tags=request.tags,
        note_type=request.note_type,
        date_from=request.date_from,
        date_to=request.date_to,
        page=page,
        limit=limit
    )

    return SuccessResponse(
        data={
            "results": result["results"],
            "total": result["total"],
            "query": request.query
        },
        meta=MetaInfo(request_id=request_id)
    )


# ==================== Export ====================

@router.post(
    "/export",
    response_model=SuccessResponse[NoteExportResult],
    summary="노트 내보내기",
    description="노트를 다양한 형식으로 내보냅니다."
)
async def export_notes(
    request: ExportNotesRequest,
    current_user: dict = Depends(get_current_user),
    note_service = Depends(get_note_service)
):
    """Export notes to various formats"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await note_service.export_notes(
        note_ids=request.note_ids,
        format=request.format,
        include_metadata=request.include_metadata
    )

    return SuccessResponse(
        data=NoteExportResult(**result),
        meta=MetaInfo(request_id=request_id)
    )
