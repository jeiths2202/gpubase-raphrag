"""
Session Document API Router
Handles file upload and text paste for chat session context
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status

from ..core.deps import get_current_user
from ..models.session_document import (
    SessionDocumentType, SessionDocumentStatus,
    SessionDocumentUploadResponse, SessionDocumentListItem
)
from ..services.session_document_service import get_session_document_service

router = APIRouter(prefix="/session-documents", tags=["Session Documents"])


def get_service():
    return get_session_document_service()


@router.post("/upload", response_model=dict)
async def upload_file(
    session_id: str = Form(..., description="Chat session ID"),
    file: UploadFile = File(..., description="File to upload"),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    Upload a file for the current chat session.
    The file will be parsed, chunked, and embedded for priority RAG retrieval.

    Supported formats: PDF, TXT, MD, DOCX, PNG, JPG, etc.
    """
    # Validate file size (10MB limit for session docs)
    content = await file.read()
    max_size = 10 * 1024 * 1024  # 10MB

    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "FILE_TOO_LARGE", "message": "파일 크기는 10MB를 초과할 수 없습니다."}
        )

    # Get MIME type
    mime_type = file.content_type
    if not mime_type or mime_type == "application/octet-stream":
        # Infer from filename
        filename = file.filename or "unknown"
        ext = filename.lower().split('.')[-1] if '.' in filename else ""
        mime_map = {
            "pdf": "application/pdf",
            "txt": "text/plain",
            "md": "text/markdown",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc": "application/msword",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        mime_type = mime_map.get(ext, "application/octet-stream")

    try:
        doc = await service.upload_file(
            session_id=session_id,
            file_content=content,
            filename=file.filename or "uploaded_file",
            mime_type=mime_type,
            user_id=current_user.get("id")
        )

        return {
            "status": "success",
            "data": {
                "document_id": doc.id,
                "session_id": doc.session_id,
                "filename": doc.filename,
                "status": doc.status.value,
                "file_size": doc.file_size
            },
            "message": "파일이 업로드되었습니다. 처리 중입니다."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "UPLOAD_FAILED", "message": str(e)}
        )


@router.post("/paste", response_model=dict)
async def paste_text(
    session_id: str = Form(..., description="Chat session ID"),
    content: str = Form(..., description="Text content to paste"),
    title: Optional[str] = Form(None, description="Optional title for the text"),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    Paste text content for the current chat session.
    The text will be chunked and embedded for priority RAG retrieval.
    """
    if not content or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_CONTENT", "message": "텍스트 내용이 비어있습니다."}
        )

    # Limit text size (500KB)
    max_size = 500 * 1024
    if len(content.encode('utf-8')) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "CONTENT_TOO_LARGE", "message": "텍스트 크기는 500KB를 초과할 수 없습니다."}
        )

    try:
        doc = await service.upload_text(
            session_id=session_id,
            text_content=content,
            title=title,
            user_id=current_user.get("id")
        )

        return {
            "status": "success",
            "data": {
                "document_id": doc.id,
                "session_id": doc.session_id,
                "filename": doc.filename,
                "status": doc.status.value,
                "word_count": len(content.split())
            },
            "message": "텍스트가 추가되었습니다."
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PASTE_FAILED", "message": str(e)}
        )


@router.get("", response_model=dict)
async def list_session_documents(
    session_id: str = Query(..., description="Chat session ID"),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """List all documents for a chat session"""
    documents = service.list_session_documents(session_id)

    return {
        "status": "success",
        "data": {
            "documents": [d.model_dump() for d in documents],
            "count": len(documents)
        }
    }


@router.get("/{document_id}", response_model=dict)
async def get_session_document(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get details of a specific session document"""
    doc = service.get_document(document_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "문서를 찾을 수 없습니다."}
        )

    return {
        "status": "success",
        "data": {
            "document": {
                "id": doc.id,
                "session_id": doc.session_id,
                "document_type": doc.document_type.value,
                "filename": doc.filename,
                "status": doc.status.value,
                "chunk_count": doc.chunk_count,
                "word_count": len(doc.text_content.split()) if doc.text_content else 0,
                "created_at": doc.created_at.isoformat(),
                "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
                "error_message": doc.error_message,
                "metadata": doc.metadata
            }
        }
    }


@router.get("/{document_id}/status", response_model=dict)
async def get_document_status(
    document_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get processing status of a session document"""
    doc = service.get_document(document_id)

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "문서를 찾을 수 없습니다."}
        )

    return {
        "status": "success",
        "data": {
            "document_id": doc.id,
            "status": doc.status.value,
            "chunk_count": doc.chunk_count,
            "ready": doc.status == SessionDocumentStatus.READY,
            "error": doc.error_message
        }
    }


@router.delete("/{document_id}", response_model=dict)
async def delete_session_document(
    document_id: str,
    session_id: str = Query(..., description="Chat session ID"),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Delete a document from the session"""
    success = service.delete_session_document(session_id, document_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "문서를 찾을 수 없거나 삭제 권한이 없습니다."}
        )

    return {
        "status": "success",
        "message": "문서가 삭제되었습니다."
    }


@router.post("/search", response_model=dict)
async def search_session_documents(
    session_id: str = Form(..., description="Chat session ID"),
    query: str = Form(..., description="Search query"),
    top_k: int = Form(5, ge=1, le=20),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Search session documents for relevant content"""
    results = await service.search_session(
        session_id=session_id,
        query=query,
        top_k=top_k
    )

    return {
        "status": "success",
        "data": {
            "results": [r.model_dump() for r in results],
            "count": len(results),
            "query": query
        }
    }


@router.get("/session/{session_id}/context", response_model=dict)
async def get_session_context(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get the context for a chat session"""
    context = service.get_session_context(session_id)

    if not context:
        return {
            "status": "success",
            "data": {
                "session_id": session_id,
                "has_documents": False,
                "document_count": 0,
                "total_chunks": 0
            }
        }

    return {
        "status": "success",
        "data": {
            "session_id": context.session_id,
            "has_documents": len(context.document_ids) > 0,
            "document_count": len(context.document_ids),
            "document_ids": context.document_ids,
            "total_chunks": context.total_chunks,
            "active": context.active,
            "created_at": context.created_at.isoformat(),
            "expires_at": context.expires_at.isoformat() if context.expires_at else None
        }
    }


@router.delete("/session/{session_id}", response_model=dict)
async def clear_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Clear all documents for a session"""
    service.clear_session(session_id)

    return {
        "status": "success",
        "message": "세션의 모든 문서가 삭제되었습니다."
    }


@router.get("/stats", response_model=dict)
async def get_service_stats(
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get session document service statistics (admin only)"""
    # Check admin role
    if current_user.get("role") not in ["admin", "leader"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "권한이 없습니다."}
        )

    stats = service.get_stats()

    return {
        "status": "success",
        "data": stats
    }
