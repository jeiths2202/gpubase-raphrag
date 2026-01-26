"""
Web Source API Router
Handles URL-based document sources for RAG
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..core.deps import get_current_user
from ..models.web_source import (
    WebSourceCreate, WebSourceBulkCreate, WebSourceStatus,
    RefreshRequest, WebSourceListItem
)
from ..services.web_content_service import get_web_content_service

router = APIRouter(prefix="/web-sources", tags=["Web Sources"])


def get_service():
    return get_web_content_service()


@router.post("", response_model=dict)
async def create_web_source(
    request: WebSourceCreate,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    Create a new web source from URL.
    Automatically fetches and processes the content.
    """
    web_source = await service.create_web_source(
        request=request,
        user_id=current_user["id"]
    )

    return {
        "status": "success",
        "data": {
            "web_source": web_source.model_dump()
        },
        "message": "웹 소스가 생성되었습니다. 처리가 진행 중입니다."
    }


@router.post("/bulk", response_model=dict)
async def create_bulk_web_sources(
    request: WebSourceBulkCreate,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    Create multiple web sources from URLs.
    Maximum 20 URLs per request.
    """
    web_sources = await service.create_bulk_web_sources(
        request=request,
        user_id=current_user["id"]
    )

    return {
        "status": "success",
        "data": {
            "web_sources": [ws.model_dump() for ws in web_sources],
            "count": len(web_sources)
        },
        "message": f"{len(web_sources)}개의 웹 소스가 생성되었습니다."
    }


@router.get("", response_model=dict)
async def list_web_sources(
    status_filter: Optional[WebSourceStatus] = Query(None, alias="status"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """List web sources with optional filtering"""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    sources, total = await service.list_web_sources(
        user_id=current_user["id"],
        status=status_filter,
        domain=domain,
        tags=tag_list,
        page=page,
        limit=limit
    )

    return {
        "status": "success",
        "data": {
            "web_sources": [s.model_dump() for s in sources],
            "total": total,
            "page": page,
            "limit": limit
        }
    }


@router.get("/search", response_model=dict)
async def search_web_sources(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Search web sources by content or metadata"""
    results = await service.search_web_sources(query=q, limit=limit)

    return {
        "status": "success",
        "data": {
            "results": [r.model_dump() for r in results],
            "count": len(results),
            "query": q
        }
    }


@router.get("/{web_source_id}", response_model=dict)
async def get_web_source(
    web_source_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get web source details by ID"""
    web_source = await service.get_web_source(web_source_id)

    if not web_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "웹 소스를 찾을 수 없습니다."}
        )

    return {
        "status": "success",
        "data": {
            "web_source": web_source.model_dump()
        }
    }


@router.post("/{web_source_id}/refresh", response_model=dict)
async def refresh_web_source(
    web_source_id: str,
    request: RefreshRequest = RefreshRequest(),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """
    Refresh web source content.
    Re-fetches the URL and updates if content has changed.
    """
    success, message = await service.refresh_web_source(
        web_source_id=web_source_id,
        force=request.force
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "REFRESH_FAILED", "message": message}
        )

    return {
        "status": "success",
        "data": {
            "web_source_id": web_source_id
        },
        "message": message
    }


@router.delete("/{web_source_id}", response_model=dict)
async def delete_web_source(
    web_source_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Delete a web source and its associated data"""
    success = await service.delete_web_source(
        web_source_id=web_source_id,
        user_id=current_user["id"]
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "웹 소스를 찾을 수 없거나 삭제 권한이 없습니다."}
        )

    return {
        "status": "success",
        "message": "웹 소스가 삭제되었습니다."
    }


@router.get("/{web_source_id}/content", response_model=dict)
async def get_web_source_content(
    web_source_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get extracted text content from web source"""
    web_source = await service.get_web_source(web_source_id)

    if not web_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "웹 소스를 찾을 수 없습니다."}
        )

    if web_source.status != WebSourceStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "NOT_READY",
                "message": f"웹 소스가 아직 준비되지 않았습니다. 현재 상태: {web_source.status}"
            }
        )

    return {
        "status": "success",
        "data": {
            "web_source_id": web_source_id,
            "url": web_source.url,
            "title": web_source.metadata.title,
            "content": web_source.extracted_text,
            "word_count": web_source.stats.word_count,
            "char_count": web_source.stats.char_count
        }
    }


@router.get("/{web_source_id}/links", response_model=dict)
async def get_web_source_links(
    web_source_id: str,
    internal_only: bool = Query(False, description="Only show internal links"),
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get extracted links from web source"""
    web_source = await service.get_web_source(web_source_id)

    if not web_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "웹 소스를 찾을 수 없습니다."}
        )

    links = web_source.extracted_links
    if internal_only:
        links = [l for l in links if l.is_internal]

    return {
        "status": "success",
        "data": {
            "web_source_id": web_source_id,
            "links": [l.model_dump() for l in links],
            "count": len(links)
        }
    }


@router.get("/{web_source_id}/images", response_model=dict)
async def get_web_source_images(
    web_source_id: str,
    current_user: dict = Depends(get_current_user),
    service = Depends(get_service)
):
    """Get extracted images from web source"""
    web_source = await service.get_web_source(web_source_id)

    if not web_source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "웹 소스를 찾을 수 없습니다."}
        )

    return {
        "status": "success",
        "data": {
            "web_source_id": web_source_id,
            "images": [img.model_dump() for img in web_source.extracted_images],
            "count": len(web_source.extracted_images)
        }
    }
