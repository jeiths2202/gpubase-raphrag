"""
Admin Traces API

Admin-only endpoints for querying trace data.
"""
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from ..core.deps import get_admin_user
from ..infrastructure.postgres.trace_repository import TraceRepository
from ..core.container import Container


router = APIRouter(prefix="/admin/traces", tags=["Admin - Traces"])


# ============================================================================
# Response Models
# ============================================================================

class TraceResponse(BaseModel):
    trace_id: UUID
    user_id: str
    original_prompt: str
    model_name: str
    total_latency_ms: Optional[int]
    response_quality_flag: str
    error_code: Optional[str]
    created_at: datetime


class TraceDetailResponse(BaseModel):
    trace: dict
    spans: List[dict]


class LatencyStatsResponse(BaseModel):
    operation_type: str
    p50_ms: int
    p95_ms: int
    p99_ms: int
    lookback_days: int


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/",
    response_model=List[TraceResponse],
    summary="Query traces (admin only)",
    description="Get list of traces with filters. Requires admin role."
)
async def query_traces(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    min_latency_ms: Optional[int] = Query(None, description="Minimum latency in ms"),
    quality_flag: Optional[str] = Query(None, description="Quality flag: NORMAL, USER_NEGATIVE, EMPTY, LOW_CONFIDENCE, ERROR"),
    error_code: Optional[str] = Query(None, description="Filter by error code"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    admin_user: dict = Depends(get_admin_user)
) -> List[TraceResponse]:
    """
    Query traces with filters.

    Admin only endpoint for debugging and analytics.
    """
    container = Container.get_instance()
    repository: TraceRepository = container.get("trace_repository")

    traces = await repository.query_traces(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        min_latency_ms=min_latency_ms,
        quality_flag=quality_flag,
        error_code=error_code,
        limit=limit,
        offset=offset
    )

    return [TraceResponse(**t) for t in traces]


@router.get(
    "/{trace_id}",
    response_model=TraceDetailResponse,
    summary="Get trace details (admin only)"
)
async def get_trace_detail(
    trace_id: UUID,
    admin_user: dict = Depends(get_admin_user)
) -> TraceDetailResponse:
    """
    Get full trace with all spans.

    Returns detailed trace data including all child spans.
    """
    container = Container.get_instance()
    repository: TraceRepository = container.get("trace_repository")

    trace_data = await repository.get_trace_by_id(trace_id)

    if not trace_data:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")

    return TraceDetailResponse(**trace_data)


@router.get(
    "/metrics/latency",
    response_model=LatencyStatsResponse,
    summary="Get latency statistics (admin only)"
)
async def get_latency_stats(
    operation_type: str = Query("total", description="Operation type: total, embedding, retrieval, generation"),
    lookback_days: int = Query(7, ge=1, le=90, description="Lookback period in days"),
    admin_user: dict = Depends(get_admin_user)
) -> LatencyStatsResponse:
    """
    Get latency statistics (P50, P95, P99) for operation type.

    Used to determine latency thresholds for flagging slow requests.
    """
    if operation_type not in ["total", "embedding", "retrieval", "generation"]:
        raise HTTPException(status_code=400, detail="Invalid operation_type")

    container = Container.get_instance()
    repository: TraceRepository = container.get("trace_repository")

    stats = await repository.get_latency_statistics(operation_type, lookback_days)

    return LatencyStatsResponse(
        operation_type=operation_type,
        p50_ms=stats['p50'],
        p95_ms=stats['p95'],
        p99_ms=stats['p99'],
        lookback_days=lookback_days
    )
