"""Analysis API Router — POST /analyze, GET /status, GET /stream, GET /results, GET /products.

Endpoints:
  GET    /api/v1/legacy/products                         — List available products
  POST   /api/v1/legacy/analyze                          — Start analysis (single file)
  GET    /api/v1/legacy/analyze/{id}/status               — Get progress
  GET    /api/v1/legacy/analyze/{id}/stream               — SSE event stream
  GET    /api/v1/legacy/analyze/{id}/results              — Get full results
  POST   /api/v1/legacy/analyze/batch                     — Start batch analysis (multi-file)
  GET    /api/v1/legacy/analyze/batch/{id}/status         — Batch progress
  GET    /api/v1/legacy/analyze/batch/{id}/stream         — Batch SSE stream
  GET    /api/v1/legacy/analyze/batch/{id}/results        — Batch results
"""

import json
import logging
import math
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..capabilities.registry import get_product_registry
from ..services.analysis_service import get_analysis_service
from .schemas import (
    AnalysisDetailResponse,
    AnalysisListItem,
    AnalysisListResponse,
    AnalysisRequest,
    AnalysisResponse,
    AnalysisResultsResponse,
    AnalysisStatusResponse,
    BatchAnalysisRequest,
    BatchAnalysisResponse,
    BatchResultsResponse,
    BatchStatusResponse,
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


# ---------------------------------------------------------------------------
# Batch Analysis Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/analyze/batch",
    response_model=BatchAnalysisResponse,
    summary="Start multi-file batch analysis",
    description="Upload multiple legacy source files for concurrent analysis.",
)
async def start_batch_analysis(
    request: BatchAnalysisRequest,
) -> BatchAnalysisResponse:
    """Start a batch analysis session for multiple files."""
    service = get_analysis_service()

    files = [
        {"file_name": f.file_name, "source_code": f.source_code}
        for f in request.files
    ]

    result = await service.start_batch_analysis(
        files=files,
        tenant_id="default",
        target_product=request.target_product,
        target_version=request.target_version,
        vendors=request.vendors,
        options=request.options.model_dump(),
    )

    return BatchAnalysisResponse(**result)


@router.get(
    "/analyze/batch/{batch_id}/status",
    response_model=BatchStatusResponse,
    summary="Get batch analysis progress",
    description="Returns per-file progress and overall batch status.",
)
async def get_batch_status(batch_id: str) -> BatchStatusResponse:
    """Get the current status of a batch analysis."""
    service = get_analysis_service()
    status = await service.get_batch_status(batch_id)

    if status is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    return BatchStatusResponse(**status)


@router.get(
    "/analyze/batch/{batch_id}/stream",
    summary="Batch SSE event stream",
    description="Real-time per-file progress updates via Server-Sent Events.",
)
async def stream_batch_analysis(batch_id: str) -> StreamingResponse:
    """Stream batch analysis events via SSE.

    Events:
      - file_progress: per-file progress update
      - file_completed: individual file finished
      - file_failed: individual file failed
      - batch_completed: all files done
    """
    service = get_analysis_service()

    async def event_generator():
        async for event in service.stream_batch_events(batch_id):
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
    "/analyze/batch/{batch_id}/results",
    response_model=BatchResultsResponse,
    summary="Get batch analysis results",
    description="Summary + per-file results with incompatibility reports.",
)
async def get_batch_results(batch_id: str) -> BatchResultsResponse:
    """Get the complete batch analysis results."""
    service = get_analysis_service()
    results = await service.get_batch_results(batch_id)

    if results is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    return BatchResultsResponse(**results)


# ---------------------------------------------------------------------------
# Persisted Analysis Endpoints (Data Table & Detail Popup)
# ---------------------------------------------------------------------------


_legacy_repo_instance = None


async def _get_legacy_repo():
    """Get the legacy analysis repository singleton (with table initialization)."""
    global _legacy_repo_instance
    if _legacy_repo_instance is not None:
        return _legacy_repo_instance

    try:
        from ...core.deps import get_postgres_pool
        from ...infrastructure.postgres.legacy_analysis_repository import LegacyAnalysisRepository
        pool = await get_postgres_pool()
        if not pool:
            raise HTTPException(status_code=503, detail="Database not available")
        repo = LegacyAnalysisRepository(pool)
        await repo.initialize()
        _legacy_repo_instance = repo
        logger.info("Legacy analysis repository initialized for router")
        return repo
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to initialize legacy analysis repository: %s", exc)
        raise HTTPException(status_code=503, detail=f"Database not available: {exc}")


@router.get(
    "/analyses",
    response_model=AnalysisListResponse,
    summary="List persisted analysis results",
    description="Paginated list for Data Table display. Supports sorting and filtering.",
)
async def list_persisted_analyses(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Sort column"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    asset_type: Optional[str] = Query(None, description="Filter by asset type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    user_id: str = Query("default", description="User ID"),
) -> AnalysisListResponse:
    """Get paginated analysis results for Data Table."""
    repo = await _get_legacy_repo()

    items, total = await repo.list_analyses(
        user_id=user_id,
        page=page,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        asset_type=asset_type,
        status=status,
    )

    total_pages = math.ceil(total / limit) if total > 0 else 0

    return AnalysisListResponse(
        items=[AnalysisListItem(**item) for item in items],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisDetailResponse,
    summary="Get persisted analysis detail",
    description="Full analysis detail for popup page, including reports and incompatibility data.",
)
async def get_persisted_analysis(analysis_id: str) -> AnalysisDetailResponse:
    """Get full analysis detail for the popup detail page."""
    repo = await _get_legacy_repo()
    detail = await repo.get_analysis(analysis_id)

    if not detail:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return AnalysisDetailResponse(**detail)


@router.delete(
    "/analyses/{analysis_id}",
    summary="Delete a persisted analysis",
    description="Remove an analysis result from the database.",
)
async def delete_persisted_analysis(
    analysis_id: str,
    user_id: str = Query("default", description="User ID"),
) -> Dict[str, Any]:
    """Delete a persisted analysis result."""
    repo = await _get_legacy_repo()
    deleted = await repo.delete_analysis(analysis_id, user_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found or not owned by user")

    return {"success": True, "deleted_id": analysis_id}
