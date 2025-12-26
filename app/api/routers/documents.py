"""
Documents API Router
문서 관리 API with Multimodal Support
Supports: PDF, Word, Excel, PowerPoint, Text, Markdown, CSV, JSON, Images
"""
import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status

from ..models.base import SuccessResponse, PaginatedResponse, PaginationMeta, MetaInfo
from ..models.document import (
    DocumentListItem,
    DocumentDetail,
    DocumentUploadResponse,
    DocumentDeleteResponse,
    DocumentStatus,
    DocumentType,
    ProcessingMode,
    ChunkInfo,
    UploadStatusResponse,
    UploadProgress,
    UploadStep,
    EXTENSION_TO_MIME,
    SUPPORTED_MIME_TYPES,
)
from ..core.deps import get_current_user, get_document_service
from ..core.config import api_settings

router = APIRouter(prefix="/documents", tags=["Documents"])

# Supported file extensions
SUPPORTED_EXTENSIONS = list(EXTENSION_TO_MIME.keys())
SUPPORTED_EXTENSIONS_STR = ", ".join(SUPPORTED_EXTENSIONS)


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
    description=f"""문서를 업로드하고 처리를 시작합니다.

지원 형식: {SUPPORTED_EXTENSIONS_STR}

VLM(Vision Language Model) 옵션을 활성화하면 이미지, 도표, 차트 등에서
정보를 추출하고 더 정확한 문서 이해가 가능합니다."""
)
async def upload_document(
    file: UploadFile = File(..., description=f"업로드 파일 (최대 {api_settings.MAX_UPLOAD_SIZE_MB}MB). 지원 형식: {SUPPORTED_EXTENSIONS_STR}"),
    name: Optional[str] = Form(default=None, description="문서 표시명"),
    language: str = Form(default="auto", description="문서 언어 (auto, ko, en, ja, zh)"),
    tags: str = Form(default="", description="태그 (쉼표 구분)"),
    processing_mode: str = Form(
        default="text_only",
        description="처리 모드: text_only(텍스트만), vlm_enhanced(VLM 보조), multimodal(전체 멀티모달), ocr(스캔 문서)"
    ),
    enable_vlm: bool = Form(default=False, description="VLM 기반 추출 활성화"),
    extract_tables: bool = Form(default=True, description="표 추출 여부"),
    extract_images: bool = Form(default=True, description="이미지 추출 및 분석 여부"),
    current_user: dict = Depends(get_current_user),
    doc_service = Depends(get_document_service)
):
    """
    Upload and process a document.

    Supports multiple file formats including:
    - **PDF** (.pdf): Document files with text, images, tables
    - **Word** (.doc, .docx): Microsoft Word documents
    - **Excel** (.xls, .xlsx): Spreadsheets with multiple sheets
    - **PowerPoint** (.ppt, .pptx): Presentation slides
    - **Text** (.txt, .md, .csv, .json): Plain text formats
    - **Images** (.png, .jpg, .jpeg, .gif, .bmp, .tiff, .webp): Image files

    Processing modes:
    - **text_only**: Traditional text extraction
    - **vlm_enhanced**: VLM-assisted extraction for better understanding
    - **multimodal**: Full multimodal processing with image analysis
    - **ocr**: OCR mode for scanned documents
    """
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Get file extension
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()

    # Validate file format
    if ext not in EXTENSION_TO_MIME:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "DOCUMENT_INVALID_FORMAT",
                "message": f"지원하지 않는 파일 형식입니다. 지원 형식: {SUPPORTED_EXTENSIONS_STR}",
                "details": {
                    "provided_extension": ext,
                    "supported_extensions": SUPPORTED_EXTENSIONS
                }
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

    # Validate processing mode
    valid_modes = ["text_only", "vlm_enhanced", "multimodal", "ocr"]
    if processing_mode not in valid_modes:
        processing_mode = "text_only"

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    # Determine MIME type
    mime_type = EXTENSION_TO_MIME.get(ext, "application/octet-stream")
    doc_type = SUPPORTED_MIME_TYPES.get(mime_type, DocumentType.TEXT)

    # Start upload processing
    result = await doc_service.upload_document(
        file_content=content,
        filename=filename,
        display_name=name,
        language=language,
        tags=tag_list,
        processing_mode=processing_mode,
        enable_vlm=enable_vlm,
        extract_tables=extract_tables,
        extract_images=extract_images
    )

    # Determine message based on document type
    if doc_type == DocumentType.IMAGE:
        message = "이미지 업로드가 시작되었습니다. VLM 분석이 진행됩니다."
    elif enable_vlm or processing_mode in ["vlm_enhanced", "multimodal"]:
        message = "문서 업로드가 시작되었습니다. VLM 기반 분석으로 인해 처리 시간이 다소 길어질 수 있습니다."
    else:
        message = "문서 업로드가 시작되었습니다. 처리 완료까지 약 2-5분 소요됩니다."

    return SuccessResponse(
        data=DocumentUploadResponse(
            document_id=result["document_id"],
            filename=result["filename"],
            status=DocumentStatus.PROCESSING,
            message=message,
            task_id=result["task_id"]
        ),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/supported-formats",
    response_model=SuccessResponse[dict],
    summary="지원 형식 조회",
    description="업로드 가능한 파일 형식 목록을 조회합니다."
)
async def get_supported_formats(
    current_user: dict = Depends(get_current_user)
):
    """Get list of supported file formats."""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    formats = {
        "pdf": {
            "extensions": [".pdf"],
            "description": "PDF 문서",
            "vlm_supported": True
        },
        "word": {
            "extensions": [".doc", ".docx"],
            "description": "Microsoft Word 문서",
            "vlm_supported": True
        },
        "excel": {
            "extensions": [".xls", ".xlsx"],
            "description": "Microsoft Excel 스프레드시트",
            "vlm_supported": False
        },
        "powerpoint": {
            "extensions": [".ppt", ".pptx"],
            "description": "Microsoft PowerPoint 프레젠테이션",
            "vlm_supported": True
        },
        "text": {
            "extensions": [".txt", ".md", ".markdown"],
            "description": "텍스트 파일",
            "vlm_supported": False
        },
        "data": {
            "extensions": [".csv", ".json"],
            "description": "데이터 파일",
            "vlm_supported": False
        },
        "image": {
            "extensions": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"],
            "description": "이미지 파일 (VLM 분석)",
            "vlm_supported": True
        },
        "html": {
            "extensions": [".html", ".htm"],
            "description": "HTML 문서",
            "vlm_supported": False
        }
    }

    return SuccessResponse(
        data={
            "formats": formats,
            "max_file_size_mb": api_settings.MAX_UPLOAD_SIZE_MB,
            "processing_modes": [
                {"mode": "text_only", "description": "텍스트만 추출 (기본)"},
                {"mode": "vlm_enhanced", "description": "VLM 보조 추출 (이미지/도표 이해)"},
                {"mode": "multimodal", "description": "전체 멀티모달 처리"},
                {"mode": "ocr", "description": "스캔 문서용 OCR"}
            ]
        },
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
