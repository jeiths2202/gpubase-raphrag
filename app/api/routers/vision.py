"""
Vision Query API Router

Provides endpoints for vision-aware document queries,
image analysis, and visual content extraction.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.core.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["vision"])


# ==================== Request/Response Models ====================

class VisionQueryRequest(BaseModel):
    """Request for vision-aware query"""
    query: str = Field(..., description="User query text")
    document_ids: Optional[List[str]] = Field(
        default=None,
        description="Specific document IDs to query"
    )
    language: str = Field(
        default="auto",
        description="Response language (auto, en, ko, ja)"
    )
    force_vision: bool = Field(
        default=False,
        description="Force use of Vision LLM"
    )
    force_text: bool = Field(
        default=False,
        description="Force use of Text LLM"
    )
    include_images: bool = Field(
        default=True,
        description="Include image references in response"
    )
    max_images: int = Field(
        default=5,
        description="Maximum images to process"
    )


class ImageAnalysisRequest(BaseModel):
    """Request for direct image analysis"""
    prompt: str = Field(..., description="Analysis prompt/question")
    language: str = Field(default="auto", description="Response language")
    extract_data: bool = Field(
        default=True,
        description="Extract structured data (charts, tables)"
    )


class DocumentAnalysisRequest(BaseModel):
    """Request for document visual analysis"""
    document_id: str = Field(..., description="Document ID to analyze")
    include_images: bool = Field(default=True, description="Include image analysis")
    force_reanalyze: bool = Field(default=False, description="Force re-analysis")


class ChartDataResponse(BaseModel):
    """Extracted chart data"""
    chart_type: str
    title: str
    description: str
    data_points: List[Dict[str, Any]] = []


class TableDataResponse(BaseModel):
    """Extracted table data"""
    headers: List[str]
    rows: List[List[str]]
    title: Optional[str] = None


class VisualInfoResponse(BaseModel):
    """Extracted visual information"""
    charts: List[ChartDataResponse] = []
    tables: List[TableDataResponse] = []
    images_analyzed: int = 0


class VisionQueryResponse(BaseModel):
    """Response for vision query"""
    query_id: str
    answer: str
    sources: List[str]
    confidence: float
    model_used: str
    visual_info: Optional[VisualInfoResponse] = None
    language: str
    routing_decision: Dict[str, Any]


class DocumentProfileResponse(BaseModel):
    """Document visual profile"""
    document_id: str
    is_visual: bool
    visual_complexity_score: float
    image_count: int
    has_charts: bool
    has_tables: bool
    has_diagrams: bool
    requires_vision_llm: bool
    processing_recommendation: str


class RoutingExplanation(BaseModel):
    """Routing decision explanation"""
    selected_llm: str
    reasoning: str
    confidence: float
    query_signals: Dict[str, Any]
    document_signals: Dict[str, Any]


# ==================== Endpoints ====================

@router.post("/query", response_model=VisionQueryResponse)
async def vision_query(
    request: VisionQueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Execute a vision-aware query.

    Automatically routes to Vision LLM or Text LLM based on:
    - Query visual signals (chart, graph, diagram keywords)
    - Document visual profiles
    - Retrieved context visual content

    Returns:
        VisionQueryResponse with answer and extracted visual data
    """
    try:
        # Import here to avoid circular imports
        from app.api.pipeline.vision_orchestrator import (
            get_vision_pipeline_orchestrator,
        )

        orchestrator = get_vision_pipeline_orchestrator()

        # Process query
        result = await orchestrator.process_query(
            query=request.query,
            document_ids=request.document_ids,
            language=request.language,
            force_vision=request.force_vision,
            force_text=request.force_text,
        )

        # Convert to response model
        visual_info = None
        if result.visual_info:
            visual_info = VisualInfoResponse(
                charts=[
                    ChartDataResponse(
                        chart_type=c.chart_type,
                        title=c.title,
                        description=c.description,
                        data_points=c.data_points,
                    )
                    for c in (result.visual_info.charts or [])
                ],
                tables=[
                    TableDataResponse(
                        headers=t.headers,
                        rows=t.rows,
                        title=t.title,
                    )
                    for t in (result.visual_info.tables or [])
                ],
                images_analyzed=len(result.visual_info.charts or []) + len(result.visual_info.tables or []),
            )

        return VisionQueryResponse(
            query_id=str(uuid4()),
            answer=result.answer,
            sources=result.sources,
            confidence=result.confidence,
            model_used=result.model_used,
            visual_info=visual_info,
            language=result.language,
            routing_decision={
                "selected_llm": result.model_used.split("/")[0] if "/" in result.model_used else "text",
                "used_vision": "vision" in result.model_used.lower() or "gpt-4o" in result.model_used.lower(),
            },
        )

    except Exception as e:
        logger.error(f"Vision query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def vision_query_stream(
    request: VisionQueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Execute a vision-aware query with streaming response.

    Returns Server-Sent Events (SSE) stream.
    """
    try:
        from app.api.pipeline.vision_orchestrator import (
            get_vision_pipeline_orchestrator,
        )

        orchestrator = get_vision_pipeline_orchestrator()

        async def generate():
            async for chunk in orchestrator.process_query_stream(
                query=request.query,
                document_ids=request.document_ids,
                language=request.language,
                force_vision=request.force_vision,
                force_text=request.force_text,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
        )

    except Exception as e:
        logger.error(f"Vision query stream failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/image")
async def analyze_image(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    language: str = Form(default="auto"),
    extract_data: bool = Form(default=True),
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze a single image directly.

    Upload an image and get AI analysis with optional
    structured data extraction.
    """
    try:
        from app.api.pipeline.vision_orchestrator import (
            get_vision_pipeline_orchestrator,
        )
        from app.api.services.image_preprocessor import ImagePreprocessor

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported image type: {image.content_type}"
            )

        # Read image data
        image_data = await image.read()

        # Preprocess image
        preprocessor = ImagePreprocessor()
        processed = await preprocessor.preprocess_single(
            image_data,
            image.filename,
        )

        # Analyze with Vision LLM
        orchestrator = get_vision_pipeline_orchestrator()
        result = await orchestrator.answer_with_images(
            query=prompt,
            images=[processed],
            language=language,
        )

        return {
            "analysis": result.answer,
            "confidence": result.confidence,
            "model_used": result.model_used,
            "language": result.language,
            "visual_info": result.visual_info.to_dict() if result.visual_info else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/document", response_model=DocumentProfileResponse)
async def analyze_document(
    request: DocumentAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze a document's visual profile.

    Determines visual complexity, identifies charts/tables/diagrams,
    and provides routing recommendations.
    """
    try:
        from app.api.pipeline.vision_orchestrator import (
            get_vision_pipeline_orchestrator,
        )

        orchestrator = get_vision_pipeline_orchestrator()

        # Analyze document
        profile = await orchestrator.analyze_document(
            document_id=request.document_id,
            include_images=request.include_images,
        )

        # Determine recommendation
        if profile.requires_vision_llm:
            if profile.visual_complexity_score >= 0.7:
                recommendation = "Vision LLM required for accurate analysis"
            elif profile.has_charts or profile.has_diagrams:
                recommendation = "Vision LLM recommended for visual elements"
            else:
                recommendation = "Vision LLM optional but beneficial"
        else:
            recommendation = "Text LLM sufficient for this document"

        return DocumentProfileResponse(
            document_id=request.document_id,
            is_visual=profile.requires_vision_llm,
            visual_complexity_score=profile.visual_complexity_score,
            image_count=profile.image_count,
            has_charts=profile.has_charts,
            has_tables=profile.has_tables,
            has_diagrams=profile.has_diagrams,
            requires_vision_llm=profile.requires_vision_llm,
            processing_recommendation=recommendation,
        )

    except Exception as e:
        logger.error(f"Document analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/routing/explain", response_model=RoutingExplanation)
async def explain_routing(
    request: VisionQueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Explain routing decision without executing query.

    Useful for understanding why Vision or Text LLM is selected.
    """
    try:
        from app.api.services.enhanced_query_router import EnhancedQueryRouter

        router = EnhancedQueryRouter()

        # Get routing explanation
        explanation = router.explain_routing(
            query=request.query,
            language=request.language,
        )

        vision_decision = explanation.get("vision_routing", {})
        routing_decision = vision_decision.get("routing_decision", {})

        return RoutingExplanation(
            selected_llm=routing_decision.get("selected_llm", "text"),
            reasoning=routing_decision.get("reasoning", ""),
            confidence=routing_decision.get("confidence", 0.0),
            query_signals={
                "is_visual": vision_decision.get("query_analysis", {}).get("is_visual_query", False),
                "visual_aspects": vision_decision.get("query_analysis", {}).get("visual_aspects", []),
                "detected_language": vision_decision.get("detected_language", "en"),
            },
            document_signals={
                "total_docs": vision_decision.get("document_analysis", {}).get("total_docs", 0),
                "visual_docs": vision_decision.get("document_analysis", {}).get("visual_docs", 0),
                "visual_ratio": vision_decision.get("document_analysis", {}).get("visual_ratio", 0.0),
            },
        )

    except Exception as e:
        logger.error(f"Routing explanation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_vision_stats(
    current_user: dict = Depends(get_current_user),
):
    """
    Get Vision LLM usage statistics.
    """
    try:
        from app.api.services.vision_cache import get_vision_cache

        cache = get_vision_cache()
        stats = cache.get_stats()

        return {
            "cache_stats": stats,
            "routing_config": {
                "visual_query_threshold": 0.3,
                "visual_doc_ratio_threshold": 0.3,
                "supported_languages": ["en", "ko", "ja"],
            },
            "supported_providers": ["openai", "anthropic"],
        }

    except Exception as e:
        logger.error(f"Failed to get vision stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cache")
async def clear_vision_cache(
    cache_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Clear vision cache.

    Args:
        cache_type: Optional specific cache to clear (profiles, responses, images)
    """
    try:
        from app.api.services.vision_cache import get_vision_cache

        cache = get_vision_cache()

        if cache_type:
            if cache_type == "profiles":
                cache.document_profiles.clear()
            elif cache_type == "responses":
                cache.query_responses.clear()
            elif cache_type == "images":
                cache.image_analysis.clear()
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown cache type: {cache_type}"
                )
            message = f"Cleared {cache_type} cache"
        else:
            cache.clear_all()
            message = "Cleared all vision caches"

        return {"message": message}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
