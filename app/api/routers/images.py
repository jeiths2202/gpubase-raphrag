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


class CrossModalSearchRequest(BaseModel):
    """Request for cross-modal search (image-to-text or image-to-image)"""
    image_base64: str = Field(..., description="Base64 encoded query image")
    search_type: str = Field(
        default="text",
        description="Search type: 'text' (find related text), 'image' (find similar images)"
    )
    limit: int = Field(default=5, ge=1, le=20, description="Maximum results")
    min_similarity: float = Field(
        default=0.3, ge=0.0, le=1.0,
        description="Minimum similarity threshold"
    )
    use_clip: bool = Field(default=True, description="Use CLIP for visual similarity")
    use_vlm: bool = Field(default=True, description="Use VLM for semantic similarity")


class CrossModalTextResult(BaseModel):
    """Text search result from image query"""
    chunk_id: str
    document_id: str
    content: str
    similarity: float
    source: Optional[str] = None
    page_number: Optional[int] = None


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


class CrossModalSearchResponse(BaseModel):
    """Response for cross-modal search"""
    search_type: str
    text_results: Optional[List[CrossModalTextResult]] = None
    image_results: Optional[List[ImageMetadata]] = None
    total: int
    query_description: Optional[str] = None  # VLM-generated description of query image


class TableExtractionRequest(BaseModel):
    """Request for table extraction from image"""
    image_base64: str = Field(..., description="Base64 encoded image containing table")
    output_format: str = Field(
        default="markdown",
        description="Output format: 'markdown', 'json', 'csv'"
    )
    include_headers: bool = Field(default=True, description="Extract headers separately")
    context: Optional[str] = Field(None, description="Document context for better extraction")


class TableData(BaseModel):
    """Extracted table data"""
    table_id: str
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    caption: Optional[str] = None
    markdown: Optional[str] = None
    csv: Optional[str] = None
    json_data: Optional[List[dict]] = None
    confidence: float = 0.0


class TableExtractionResponse(BaseModel):
    """Response for table extraction"""
    success: bool
    table: Optional[TableData] = None
    error: Optional[str] = None


class ChartAnalysisRequest(BaseModel):
    """Request for chart/diagram analysis"""
    image_base64: str = Field(..., description="Base64 encoded chart/diagram image")
    analysis_type: str = Field(
        default="full",
        description="Analysis type: 'full', 'data_only', 'description_only'"
    )
    context: Optional[str] = Field(None, description="Document context")


class ChartData(BaseModel):
    """Extracted chart data"""
    chart_type: str  # bar, line, pie, scatter, diagram, flowchart, etc.
    title: Optional[str] = None
    description: str
    data_points: Optional[List[dict]] = None  # [{label, value}, ...]
    x_axis: Optional[str] = None
    y_axis: Optional[str] = None
    legend: Optional[List[str]] = None
    insights: Optional[List[str]] = None  # AI-generated insights
    confidence: float = 0.0


class ChartAnalysisResponse(BaseModel):
    """Response for chart analysis"""
    success: bool
    chart: Optional[ChartData] = None
    error: Optional[str] = None


class StructuredQARequest(BaseModel):
    """Request for QA on structured data (table/chart)"""
    question: str = Field(..., description="Question about the table/chart")
    image_base64: Optional[str] = Field(None, description="Image containing table/chart")
    table_data: Optional[TableData] = Field(None, description="Pre-extracted table data")
    chart_data: Optional[ChartData] = Field(None, description="Pre-extracted chart data")
    language: str = Field(default="ko", description="Response language")


class StructuredQAResponse(BaseModel):
    """Response for structured QA"""
    answer: str
    confidence: float
    evidence: Optional[str] = None  # Supporting data from table/chart
    sql_equivalent: Optional[str] = None  # SQL-like query representation


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


# ==================== Cross-Modal Search Endpoints ====================

async def get_clip_service():
    """Get CLIP embedding service."""
    try:
        from app.api.services.clip_embedding_service import get_clip_embedding_service
        return get_clip_embedding_service()
    except Exception as e:
        logger.warning(f"CLIP service not available: {e}")
        return None


async def get_vlm_service():
    """Get VLM service for image description."""
    try:
        from app.api.services.ollama_vlm_service import get_ollama_vlm_service
        return get_ollama_vlm_service()
    except Exception as e:
        logger.warning(f"VLM service not available: {e}")
        return None


@router.post("/cross-modal/search", response_model=CrossModalSearchResponse)
async def cross_modal_search(
    request: CrossModalSearchRequest,
    user=Depends(get_current_user),
):
    """
    Cross-modal search: Find text or images using an image as query.

    - **search_type='text'**: Find related text passages (image-to-text)
    - **search_type='image'**: Find similar images (image-to-image)

    Uses CLIP embeddings for visual similarity and VLM for semantic understanding.
    """
    try:
        # Decode query image
        image_bytes = base64.b64decode(request.image_base64)

        # Get VLM description of the query image
        query_description = None
        vlm_service = await get_vlm_service()
        if vlm_service and request.use_vlm:
            try:
                desc_result = await vlm_service.describe_image(image_bytes)
                query_description = desc_result.get("description", "")
            except Exception as e:
                logger.warning(f"VLM description failed: {e}")

        if request.search_type == "text":
            # Image-to-text search
            results = await _search_text_by_image(
                image_bytes=image_bytes,
                query_description=query_description,
                limit=request.limit,
                min_similarity=request.min_similarity,
                use_clip=request.use_clip,
            )

            return CrossModalSearchResponse(
                search_type="text",
                text_results=results,
                total=len(results),
                query_description=query_description,
            )

        elif request.search_type == "image":
            # Image-to-image search
            results = await _search_images_by_image(
                image_bytes=image_bytes,
                limit=request.limit,
                min_similarity=request.min_similarity,
                use_clip=request.use_clip,
            )

            return CrossModalSearchResponse(
                search_type="image",
                image_results=results,
                total=len(results),
                query_description=query_description,
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid search_type: {request.search_type}. Use 'text' or 'image'."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cross-modal search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _search_text_by_image(
    image_bytes: bytes,
    query_description: Optional[str],
    limit: int,
    min_similarity: float,
    use_clip: bool,
) -> List[CrossModalTextResult]:
    """Search text passages using image query."""
    results = []

    # Strategy 1: Use VLM description to search text
    if query_description:
        try:
            from app.api.services.rag_service import rag_service
            search_results = await rag_service.search(
                query=query_description,
                limit=limit,
                strategy="hybrid",
            )
            for r in search_results:
                results.append(CrossModalTextResult(
                    chunk_id=r.get("chunk_id", ""),
                    document_id=r.get("doc_id", ""),
                    content=r.get("content", "")[:500],
                    similarity=r.get("score", 0.0),
                    source=r.get("source"),
                    page_number=r.get("page_number"),
                ))
        except Exception as e:
            logger.warning(f"Text search by description failed: {e}")

    # Strategy 2: Use CLIP embedding for cross-modal search
    if use_clip and not results:
        clip_service = await get_clip_service()
        if clip_service:
            try:
                # Get CLIP embedding of query image
                query_embedding = await clip_service.embed_image(image_bytes)

                # Search text chunks with similar CLIP embeddings
                # (requires text chunks to have CLIP embeddings stored)
                from app.api.services.multimodal_embedding import TextEmbeddingService
                text_service = TextEmbeddingService()

                # Use the query description for text embedding comparison
                if query_description:
                    # This is a simplified approach - in production you'd want
                    # to use stored CLIP text embeddings
                    pass

            except Exception as e:
                logger.warning(f"CLIP cross-modal search failed: {e}")

    return results[:limit]


async def _search_images_by_image(
    image_bytes: bytes,
    limit: int,
    min_similarity: float,
    use_clip: bool,
) -> List[ImageMetadata]:
    """Search similar images using image query."""
    results = []

    clip_service = await get_clip_service()
    if clip_service and use_clip:
        try:
            # Get CLIP embedding of query image
            query_embedding = await clip_service.embed_image(image_bytes)

            # Get multimodal service for image repository access
            multimodal_service = await get_multimodal_service()
            if multimodal_service:
                # Search for similar images
                similar_images = await multimodal_service.search_similar_images(
                    embedding=query_embedding,
                    limit=limit,
                    min_similarity=min_similarity,
                )

                for img in similar_images:
                    results.append(ImageMetadata(
                        image_id=img.get("image_id", ""),
                        document_id=img.get("document_id", ""),
                        page_number=img.get("page_number"),
                        description=img.get("description"),
                        similarity=img.get("similarity"),
                    ))

        except Exception as e:
            logger.warning(f"CLIP image-to-image search failed: {e}")

    return results[:limit]


# ==================== Table/Chart Extraction Endpoints ====================

@router.post("/table/extract", response_model=TableExtractionResponse)
async def extract_table(
    request: TableExtractionRequest,
    user=Depends(get_current_user),
):
    """
    Extract structured table data from an image.

    Uses VLM to analyze table images and extract:
    - Headers
    - Row data
    - Output in markdown, JSON, or CSV format
    """
    try:
        # Decode image
        image_bytes = base64.b64decode(request.image_base64)

        vlm_service = await get_vlm_service()
        if not vlm_service:
            raise HTTPException(
                status_code=503,
                detail="VLM service not available for table extraction"
            )

        # Extract table using VLM
        table_data = await _extract_table_with_vlm(
            vlm_service=vlm_service,
            image_bytes=image_bytes,
            context=request.context,
            output_format=request.output_format,
        )

        return TableExtractionResponse(
            success=True,
            table=table_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Table extraction error: {e}")
        return TableExtractionResponse(
            success=False,
            error=str(e),
        )


async def _extract_table_with_vlm(
    vlm_service,
    image_bytes: bytes,
    context: Optional[str],
    output_format: str,
) -> TableData:
    """Extract table data using VLM."""
    import uuid

    # Construct prompt for table extraction
    prompt = """이 이미지에서 테이블을 분석하고 추출해주세요.

다음 JSON 형식으로 응답하세요:
{
    "headers": ["헤더1", "헤더2", ...],
    "rows": [["값1", "값2", ...], ...],
    "caption": "테이블 설명 (있는 경우)"
}

테이블이 없으면 빈 배열을 반환하세요."""

    if context:
        prompt = f"문서 컨텍스트: {context}\n\n{prompt}"

    # Call VLM
    result = await vlm_service.describe_image(
        image_data=image_bytes,
        prompt=prompt,
    )

    response_text = result.get("description", "")

    # Parse JSON from response
    headers = []
    rows = []
    caption = None

    try:
        import json
        import re

        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*"headers"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            headers = parsed.get("headers", [])
            rows = parsed.get("rows", [])
            caption = parsed.get("caption")
    except Exception as e:
        logger.warning(f"Failed to parse table JSON: {e}")
        # Fallback: try to parse markdown table from response
        headers, rows = _parse_markdown_table(response_text)

    # Generate output formats
    table_id = f"table_{uuid.uuid4().hex[:8]}"
    markdown = _table_to_markdown(headers, rows)
    csv_output = _table_to_csv(headers, rows) if output_format == "csv" else None
    json_data = _table_to_json(headers, rows) if output_format == "json" else None

    return TableData(
        table_id=table_id,
        headers=headers,
        rows=rows,
        caption=caption,
        markdown=markdown,
        csv=csv_output,
        json_data=json_data,
        confidence=result.get("confidence", 0.8) if headers else 0.0,
    )


def _parse_markdown_table(text: str):
    """Parse markdown table format."""
    import re
    lines = text.strip().split('\n')
    headers = []
    rows = []

    for i, line in enumerate(lines):
        if '|' in line:
            cells = [c.strip() for c in line.split('|') if c.strip()]
            if cells:
                # Skip separator line (contains only dashes)
                if all(re.match(r'^-+$', c) for c in cells):
                    continue
                if not headers:
                    headers = cells
                else:
                    rows.append(cells)

    return headers, rows


def _table_to_markdown(headers: List[str], rows: List[List[str]]) -> str:
    """Convert table to markdown format."""
    if not headers and not rows:
        return ""

    lines = []

    # Headers
    if headers:
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    # Rows
    for row in rows:
        # Pad row if necessary
        padded_row = row + [""] * (len(headers) - len(row)) if headers else row
        lines.append("| " + " | ".join(padded_row[:len(headers)] if headers else padded_row) + " |")

    return "\n".join(lines)


def _table_to_csv(headers: List[str], rows: List[List[str]]) -> str:
    """Convert table to CSV format."""
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    if headers:
        writer.writerow(headers)
    for row in rows:
        writer.writerow(row)

    return output.getvalue()


def _table_to_json(headers: List[str], rows: List[List[str]]) -> List[dict]:
    """Convert table to JSON format (list of dicts)."""
    if not headers:
        return [{"row": row} for row in rows]

    result = []
    for row in rows:
        item = {}
        for i, header in enumerate(headers):
            item[header] = row[i] if i < len(row) else ""
        result.append(item)

    return result


@router.post("/chart/analyze", response_model=ChartAnalysisResponse)
async def analyze_chart(
    request: ChartAnalysisRequest,
    user=Depends(get_current_user),
):
    """
    Analyze a chart or diagram image.

    Extracts:
    - Chart type (bar, line, pie, scatter, diagram, flowchart)
    - Data points and values
    - Axis labels
    - AI-generated insights
    """
    try:
        image_bytes = base64.b64decode(request.image_base64)

        vlm_service = await get_vlm_service()
        if not vlm_service:
            raise HTTPException(
                status_code=503,
                detail="VLM service not available for chart analysis"
            )

        chart_data = await _analyze_chart_with_vlm(
            vlm_service=vlm_service,
            image_bytes=image_bytes,
            context=request.context,
            analysis_type=request.analysis_type,
        )

        return ChartAnalysisResponse(
            success=True,
            chart=chart_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chart analysis error: {e}")
        return ChartAnalysisResponse(
            success=False,
            error=str(e),
        )


async def _analyze_chart_with_vlm(
    vlm_service,
    image_bytes: bytes,
    context: Optional[str],
    analysis_type: str,
) -> ChartData:
    """Analyze chart using VLM."""

    # Construct prompt based on analysis type
    if analysis_type == "description_only":
        prompt = "이 차트/다이어그램의 내용을 자세히 설명해주세요."
    elif analysis_type == "data_only":
        prompt = """이 차트의 데이터를 추출해주세요.

JSON 형식으로 응답:
{
    "chart_type": "bar/line/pie/scatter/diagram",
    "data_points": [{"label": "라벨", "value": 값}, ...],
    "x_axis": "X축 라벨",
    "y_axis": "Y축 라벨"
}"""
    else:  # full analysis
        prompt = """이 차트/다이어그램을 상세히 분석해주세요.

다음을 포함해서 JSON 형식으로 응답:
{
    "chart_type": "bar/line/pie/scatter/diagram/flowchart",
    "title": "차트 제목",
    "description": "차트 설명",
    "data_points": [{"label": "라벨", "value": 값}, ...],
    "x_axis": "X축 라벨",
    "y_axis": "Y축 라벨",
    "legend": ["범례1", "범례2"],
    "insights": ["인사이트1", "인사이트2"]
}"""

    if context:
        prompt = f"문서 컨텍스트: {context}\n\n{prompt}"

    result = await vlm_service.describe_image(
        image_data=image_bytes,
        prompt=prompt,
    )

    response_text = result.get("description", "")

    # Parse response
    chart_type = "unknown"
    title = None
    description = response_text
    data_points = None
    x_axis = None
    y_axis = None
    legend = None
    insights = None

    try:
        import json
        import re

        json_match = re.search(r'\{[^{}]*"chart_type"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            chart_type = parsed.get("chart_type", "unknown")
            title = parsed.get("title")
            description = parsed.get("description", response_text)
            data_points = parsed.get("data_points")
            x_axis = parsed.get("x_axis")
            y_axis = parsed.get("y_axis")
            legend = parsed.get("legend")
            insights = parsed.get("insights")
    except Exception as e:
        logger.warning(f"Failed to parse chart JSON: {e}")
        # Use description-only fallback
        description = response_text

    return ChartData(
        chart_type=chart_type,
        title=title,
        description=description,
        data_points=data_points,
        x_axis=x_axis,
        y_axis=y_axis,
        legend=legend,
        insights=insights,
        confidence=result.get("confidence", 0.8),
    )


@router.post("/structured-qa", response_model=StructuredQAResponse)
async def structured_qa(
    request: StructuredQARequest,
    user=Depends(get_current_user),
):
    """
    Answer questions about tables or charts.

    Supports:
    - Questions about table data (aggregation, filtering, comparison)
    - Questions about chart trends and insights
    - Multi-language responses
    """
    try:
        vlm_service = await get_vlm_service()
        if not vlm_service:
            raise HTTPException(
                status_code=503,
                detail="VLM service not available for structured QA"
            )

        # Build context from provided data
        context_parts = []

        if request.table_data:
            context_parts.append(f"테이블 데이터:\n{request.table_data.markdown or _table_to_markdown(request.table_data.headers, request.table_data.rows)}")

        if request.chart_data:
            context_parts.append(f"차트 정보:\n- 유형: {request.chart_data.chart_type}\n- 설명: {request.chart_data.description}")
            if request.chart_data.data_points:
                context_parts.append(f"- 데이터: {request.chart_data.data_points}")

        if request.image_base64:
            # Extract from image first
            image_bytes = base64.b64decode(request.image_base64)

            # Try table extraction
            table_result = await _extract_table_with_vlm(
                vlm_service=vlm_service,
                image_bytes=image_bytes,
                context=None,
                output_format="markdown",
            )
            if table_result.headers or table_result.rows:
                context_parts.append(f"추출된 테이블:\n{table_result.markdown}")

        if not context_parts:
            raise HTTPException(
                status_code=400,
                detail="No data provided. Provide image_base64, table_data, or chart_data."
            )

        # Build QA prompt
        language_instruction = {
            "ko": "한국어로 답변하세요.",
            "en": "Answer in English.",
            "ja": "日本語で回答してください。",
        }.get(request.language, "한국어로 답변하세요.")

        prompt = f"""{chr(10).join(context_parts)}

질문: {request.question}

{language_instruction}

다음 형식으로 답변:
1. 답변: [직접적인 답변]
2. 근거: [데이터에서 찾은 근거]"""

        # Get answer from VLM (using text completion)
        result = await vlm_service.describe_image(
            image_data=request.image_base64 and base64.b64decode(request.image_base64) or b'\x89PNG\r\n\x1a\n',  # dummy image if none provided
            prompt=prompt,
        )

        response_text = result.get("description", "")

        # Parse response
        answer = response_text
        evidence = None

        # Try to extract structured parts
        if "답변:" in response_text:
            parts = response_text.split("답변:")
            if len(parts) > 1:
                answer_part = parts[1]
                if "근거:" in answer_part:
                    answer, evidence = answer_part.split("근거:", 1)
                    answer = answer.strip()
                    evidence = evidence.strip()
                else:
                    answer = answer_part.strip()

        return StructuredQAResponse(
            answer=answer,
            confidence=result.get("confidence", 0.8),
            evidence=evidence,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Structured QA error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
