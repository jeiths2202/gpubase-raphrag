"""Analysis API Router — POST /analyze, GET /status, GET /stream, GET /results, GET /products.

Endpoints:
  GET    /api/v1/legacy/products                    — List available products
  POST   /api/v1/legacy/analyze                     — Start analysis
  GET    /api/v1/legacy/analyze/{id}/status          — Get progress
  GET    /api/v1/legacy/analyze/{id}/stream          — SSE event stream
  GET    /api/v1/legacy/analyze/{id}/results         — Get full results
"""

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..capabilities.registry import get_product_registry
from ..services.analysis_service import get_analysis_service
from .schemas import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisResultsResponse,
    AnalysisStatusResponse,
    ProductFamilyItem,
    ProductListResponse,
    ProductVersionItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legacy", tags=["Legacy Modernization"])


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List available OpenFrame products",
    description="Returns all available OpenFrame products grouped by family, optionally filtered by asset type.",
)
async def list_products(
    asset_type: Optional[str] = Query(
        None, description="Filter by asset type (e.g., 'cobol', 'jcl', 'map', 'assembler')",
    ),
    lang: str = Query("en", description="Language for display names (en, ko, ja)"),
) -> ProductListResponse:
    """List available OpenFrame products for the version selector."""
    registry = get_product_registry()
    families = registry.list_families()

    result_families = []
    total = 0
    for fam in families:
        versions = fam.versions
        if asset_type:
            versions = [v for v in versions if asset_type in v.asset_types]
        if not versions:
            continue

        display_attr = {
            "ko": "display_name_ko",
            "ja": "display_name_ja",
        }.get(lang, "display_name")

        result_families.append(ProductFamilyItem(
            family=fam.family,
            display_name=fam.display_name,
            versions=[
                ProductVersionItem(
                    product=v.product,
                    version=v.version,
                    display_name=getattr(v, display_attr, v.display_name),
                    asset_types=v.asset_types,
                )
                for v in versions
            ],
        ))
        total += len(versions)

    return ProductListResponse(families=result_families, total_products=total)


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Start legacy code analysis",
    description="Upload legacy source code for multi-agent analysis pipeline.",
)
async def start_analysis(
    request: AnalysisRequest,
) -> AnalysisResponse:
    """Start a new analysis session.

    Accepts source code inline (JSON body) and kicks off the
    8-agent analysis pipeline. Optionally specify target_product and
    target_version for version-specific compatibility analysis.
    """
    service = get_analysis_service()

    result = await service.start_analysis(
        file_name=request.file_name,
        source_code=request.source_code,
        tenant_id="default",  # TODO: extract from auth token
        vendors=request.vendors,
        options=request.options.model_dump(),
        target_product=request.target_product,
        target_version=request.target_version,
    )

    if result.get("status") == "validation_error":
        raise HTTPException(status_code=400, detail=result["message"])

    return AnalysisResponse(
        analysis_id=result["analysis_id"],
        status=result["status"],
        message=result["message"],
        estimated_duration_minutes=result.get("estimated_duration_minutes"),
    )


@router.get(
    "/analyze/{analysis_id}/status",
    response_model=AnalysisStatusResponse,
    summary="Get analysis progress",
    description="Returns current pipeline status and progress percentage.",
)
async def get_analysis_status(
    analysis_id: str,
) -> AnalysisStatusResponse:
    """Get the current status of an analysis session."""
    service = get_analysis_service()
    status = await service.get_status(analysis_id)

    if status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Analysis not found")

    return AnalysisStatusResponse(**status)


@router.get(
    "/analyze/{analysis_id}/stream",
    summary="SSE event stream",
    description="Real-time progress updates via Server-Sent Events.",
)
async def stream_analysis(analysis_id: str) -> StreamingResponse:
    """Stream real-time analysis events via SSE.

    Events:
      - status_change: pipeline state changed
      - completed: analysis finished
      - failed: analysis failed
      - blocked: QA VETO issued
    """
    service = get_analysis_service()

    async def event_generator():
        async for event in service.stream_events(analysis_id):
            event_type = event.get("event", "message")
            data = json.dumps(event.get("data", {}), default=str)
            yield f"event: {event_type}\ndata: {data}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/analyze/{analysis_id}/results",
    response_model=AnalysisResultsResponse,
    summary="Get analysis results",
    description="Full workspace state, generated reports, and audit trail.",
)
async def get_analysis_results(
    analysis_id: str,
) -> AnalysisResultsResponse:
    """Get the complete analysis results."""
    service = get_analysis_service()
    results = await service.get_results(analysis_id)

    if "error" in results:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return AnalysisResultsResponse(**results)
