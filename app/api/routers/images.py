"""
Images API Router for Multimodal RAG

Provides endpoints for:
- Image search by text query
- Image retrieval by ID
- Document images listing
- Image upload and processing

SECURITY: Content-Disposition filenames are sanitized to prevent header injection.
"""

import base64
import logging
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


# ==================== Request/Response Models ====================

class ImageSearchRequest(BaseModel):
    """Request for image search"""
    query: str = Field(..., description="Text query to search for images")
    limit: int = Field(default=5, ge=1, le=20, description="Maximum results")
    min_similarity: float = Field(
        default=0.1, ge=0.0, le=1.0,
        description="Minimum similarity threshold (text-to-image typically 0.1-0.4)"
    )
    document_id: Optional[str] = Field(
        default=None,
        description="Filter by document ID"
    )


class ImageMetadata(BaseModel):
    """Image metadata response"""
    image_id: str
    document_id: str
    page_number: Optional[int] = None
    description: Optional[str] = None
    alt_text: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: str = "image/png"
    similarity: Optional[float] = None


class ImageSearchResponse(BaseModel):
    """Response for image search"""
    images: List[ImageMetadata]
    total: int
    query: str


class ImageDataResponse(BaseModel):
    """Response with image data"""
    image_id: str
    document_id: str
    page_number: Optional[int] = None
    description: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: str
    image_base64: str


class DocumentImagesResponse(BaseModel):
    """Response for document images listing"""
    document_id: str
    images: List[ImageMetadata]
    total: int


# ==================== Dependency Injection ====================

async def get_multimodal_service():
    """Get multimodal RAG service from DI container."""
    try:
        from app.api.core.deps import get_multimodal_rag_service
        return await get_multimodal_rag_service()
    except Exception as e:
        logger.warning(f"MultimodalRAGService not available: {e}")
        return None


# ==================== Endpoints ====================

@router.post("/search", response_model=ImageSearchResponse)
async def search_images(
    request: ImageSearchRequest,
    user=Depends(get_current_user),
):
    """
    Search for images by text query.

    Uses semantic similarity to find relevant images from the document
    knowledge base. Images are matched based on their VLM-generated
    descriptions and embeddings.
    """
    service = await get_multimodal_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Multimodal service not available"
        )

    try:
        results = await service.search_images(
            query=request.query,
            limit=request.limit,
            min_similarity=request.min_similarity,
            document_id=request.document_id,
            include_data=False,
        )

        images = [
            ImageMetadata(
                image_id=r["image_id"],
                document_id=r["document_id"],
                page_number=r.get("page_number"),
                description=r.get("description"),
                similarity=r.get("similarity"),
            )
            for r in results
        ]

        return ImageSearchResponse(
            images=images,
            total=len(images),
            query=request.query,
        )

    except Exception as e:
        logger.error(f"Image search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{image_id}", response_model=ImageDataResponse)
async def get_image(
    image_id: str,
    user=Depends(get_current_user),
):
    """
    Get a specific image by ID.

    Returns the image metadata along with the base64-encoded image data.
    """
    service = await get_multimodal_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Multimodal service not available"
        )

    try:
        result = await service.get_image(image_id, include_data=True)

        if not result:
            raise HTTPException(status_code=404, detail="Image not found")

        return ImageDataResponse(
            image_id=result["image_id"],
            document_id=result["document_id"],
            page_number=result.get("page_number"),
            description=result.get("description"),
            width=result.get("width"),
            height=result.get("height"),
            mime_type=result.get("mime_type", "image/png"),
            image_base64=result.get("image_base64", ""),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get image error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{image_id}/raw")
async def get_image_raw(
    image_id: str,
    user=Depends(get_current_user),
):
    """
    Get raw image data for display.

    Returns the actual image bytes with appropriate content type.
    """
    service = await get_multimodal_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Multimodal service not available"
        )

    try:
        result = await service.get_image(image_id, include_data=True)

        if not result:
            raise HTTPException(status_code=404, detail="Image not found")

        if not result.get("image_base64"):
            raise HTTPException(status_code=404, detail="Image data not available")

        # Decode base64 to bytes
        image_bytes = base64.b64decode(result["image_base64"])
        mime_type = result.get("mime_type", "image/png")

        # SECURITY: Sanitize filename to prevent HTTP header injection
        # Only allow alphanumeric, hyphens, underscores, and dots
        safe_filename = re.sub(r'[^\w\-.]', '_', image_id)

        return Response(
            content=image_bytes,
            media_type=mime_type,
            headers={
                "Content-Disposition": f'inline; filename="{safe_filename}.png"',
                "Cache-Control": "public, max-age=86400",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get raw image error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/document/{document_id}", response_model=DocumentImagesResponse)
async def get_document_images(
    document_id: str,
    include_data: bool = Query(default=False, description="Include base64 data"),
    user=Depends(get_current_user),
):
    """
    Get all images from a specific document.

    Returns metadata for all images extracted from the document,
    optionally with base64-encoded image data.
    """
    service = await get_multimodal_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Multimodal service not available"
        )

    try:
        results = await service.get_document_images(
            document_id=document_id,
            include_data=include_data,
        )

        images = [
            ImageMetadata(
                image_id=r["image_id"],
                document_id=document_id,
                page_number=r.get("page_number"),
                description=r.get("description"),
                alt_text=r.get("alt_text"),
                width=r.get("width"),
                height=r.get("height"),
                mime_type=r.get("mime_type", "image/png"),
            )
            for r in results
        ]

        return DocumentImagesResponse(
            document_id=document_id,
            images=images,
            total=len(images),
        )

    except Exception as e:
        logger.error(f"Get document images error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
