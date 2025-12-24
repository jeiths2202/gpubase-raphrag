"""
Documents API Router
문서 관리 API
"""
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.document import (
    DocumentListItem,
    DocumentDetail,
    DocumentUploadResponse,
    DocumentDeleteResponse,
    DocumentStatus,
    ChunkInfo,
    UploadStatusResponse,
    UploadProgress,
    UploadStep,
)
from ..core.deps import get_current_user, get_document_service
from ..core.config import api_settings

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get(
    "",
    response_model=PaginatedResponse[dict],
    summary="문서 목록 조회",
    description="업로드된 문서 목록을 페이지네이션하여 조회합니다."
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    limit: int = Query(default=20, ge=1, le=100, description="페이지당 항목 수"),
    search: Optional[str] = Query(default=None, description="문서명 검색"),
    status: Optional[str] = Query(default=None, description="상태 필터"),
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """List all documents with pagination"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await doc_service.list_documents(
        page=page,
        limit=limit,
        search=search,
        status=status
    )

    documents = [DocumentListItem(**doc) for doc in result["documents"]]

    return PaginatedResponse(
        data={"documents": documents},
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


@router.post(
    "",
    response_model=SuccessResponse[DocumentUploadResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="문서 업로드",
    description="PDF 문서를 업로드하고 처리를 시작합니다."
)
async def upload_document(
    file: UploadFile = File(..., description="PDF 파일 (최대 50MB)"),
    name: Optional[str] = Form(default=None, description="문서 표시명"),
    language: str = Form(default="auto", description="문서 언어"),
    tags: str = Form(default="", description="태그 (쉼표 구분)"),
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """Upload and process a PDF document"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Validate file
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCUMENT_INVALID_FORMAT",
                "message": "지원하지 않는 파일 형식입니다. PDF 파일만 업로드 가능합니다."
            }
        )

    # Check file size
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > api_settings.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCUMENT_TOO_LARGE",
                "message": f"파일 크기가 제한을 초과했습니다. (최대: {api_settings.MAX_UPLOAD_SIZE_MB}MB)",
                "details": {
                    "max_size_mb": api_settings.MAX_UPLOAD_SIZE_MB,
                    "actual_size_mb": round(file_size_mb, 2)
                }
            }
        )

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Start upload processing
    result = await doc_service.upload_document(
        file_content=content,
        filename=file.filename,
        display_name=name,
        language=language,
        tags=tag_list
    )

    return SuccessResponse(
        data=DocumentUploadResponse(
            document_id=result["document_id"],
            filename=result["filename"],
            status=DocumentStatus.PROCESSING,
            message="문서 업로드가 시작되었습니다. 처리 완료까지 약 2-5분 소요됩니다.",
            task_id=result["task_id"]
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/upload-status/{task_id}",
    response_model=SuccessResponse[UploadStatusResponse],
    summary="업로드 상태 조회",
    description="문서 업로드 및 처리 진행 상태를 조회합니다."
)
async def get_upload_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """Get document upload/processing status"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await doc_service.get_upload_status(task_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "TASK_NOT_FOUND", "message": "작업을 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=UploadStatusResponse(
            task_id=task_id,
            document_id=result["document_id"],
            status=DocumentStatus(result["status"]),
            progress=UploadProgress(
                current_step=result["current_step"],
                steps=[UploadStep(**step) for step in result["steps"]],
                overall_progress=result["overall_progress"]
            ),
            started_at=result["started_at"],
            estimated_completion=result.get("estimated_completion")
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/{document_id}",
    response_model=SuccessResponse[DocumentDetail],
    summary="문서 상세 조회",
    description="문서의 상세 정보를 조회합니다."
)
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """Get document details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await doc_service.get_document(document_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=DocumentDetail(**result),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/{document_id}",
    response_model=SuccessResponse[DocumentDeleteResponse],
    summary="문서 삭제",
    description="문서와 관련된 모든 데이터(청크, 엔티티)를 삭제합니다."
)
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """Delete a document and all related data"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await doc_service.delete_document(document_id)

    if not result:
        raise HTTPException(
            status_code=404,
            detail={"code": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=DocumentDeleteResponse(
            document_id=document_id,
            message="문서가 성공적으로 삭제되었습니다.",
            deleted_chunks=result["deleted_chunks"],
            deleted_entities=result["deleted_entities"]
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/{document_id}/chunks",
    response_model=PaginatedResponse[dict],
    summary="문서 청크 목록",
    description="문서의 청크 목록을 조회합니다."
)
async def get_document_chunks(
    document_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """Get chunks for a document"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await doc_service.get_document_chunks(document_id, page, limit)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "DOCUMENT_NOT_FOUND", "message": "문서를 찾을 수 없습니다."}
        )

    chunks = [ChunkInfo(**chunk) for chunk in result["chunks"]]

    return PaginatedResponse(
        data={"chunks": chunks},
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
