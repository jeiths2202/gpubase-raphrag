"""
Admin Dashboard Router
API endpoints for the admin dashboard
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_admin_user
from .models import (
    ExecutiveDashboardResponse,
    TokenGovernanceOverview,
    AgentPerformanceOverview,
    SystemHealthResponse,
    RAGMetricsOverview,
    AuditLogResponse,
    AuditLogStats,
    AuditCategory,
    AuditSeverity,
)
from .service import get_admin_dashboard_service, AdminDashboardService

router = APIRouter(prefix="/admin/analytics", tags=["Admin Dashboard"])


def get_request_id() -> str:
    """Generate unique request ID"""
    return f"req_{uuid.uuid4().hex[:12]}"


# ============================================================================
# EXECUTIVE DASHBOARD
# ============================================================================

@router.get(
    "/executive",
    response_model=SuccessResponse[ExecutiveDashboardResponse],
    summary="Executive Dashboard Overview",
    description="Get high-level KPIs and system overview for the admin dashboard"
)
async def get_executive_dashboard(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get executive dashboard with:
    - User statistics (total, active, new users)
    - Token usage summary
    - Query metrics
    - System health status
    - Trend data for charts
    """
    request_id = get_request_id()

    try:
        dashboard_data = await service.get_executive_dashboard(days=days)

        return SuccessResponse(
            data=dashboard_data,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "DASHBOARD_ERROR", "message": f"Failed to load dashboard: {str(e)}"}
        )


# ============================================================================
# TOKEN GOVERNANCE
# ============================================================================

@router.get(
    "/token-governance",
    response_model=SuccessResponse[TokenGovernanceOverview],
    summary="Token Governance Overview",
    description="Get token usage statistics, costs, and governance metrics"
)
async def get_token_governance(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get token governance data:
    - Total token usage and costs
    - Daily usage trends
    - Top users by token consumption
    - Top endpoints by usage
    - Usage breakdown by agent type and model
    """
    request_id = get_request_id()

    try:
        token_data = await service.get_token_governance(days=days)

        return SuccessResponse(
            data=token_data,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "TOKEN_GOVERNANCE_ERROR", "message": f"Failed to load token data: {str(e)}"}
        )


# ============================================================================
# AGENT PERFORMANCE
# ============================================================================

@router.get(
    "/agent-performance",
    response_model=SuccessResponse[AgentPerformanceOverview],
    summary="Agent Performance Metrics",
    description="Get performance metrics for all AI agents"
)
async def get_agent_performance(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get agent performance data:
    - Per-agent execution counts
    - Success/failure rates
    - Average and P95 latencies
    - Retry statistics
    - Performance trends
    """
    request_id = get_request_id()

    try:
        agent_data = await service.get_agent_performance(days=days)

        return SuccessResponse(
            data=agent_data,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "AGENT_PERFORMANCE_ERROR", "message": f"Failed to load agent data: {str(e)}"}
        )


# ============================================================================
# HEALTH MONITORING
# ============================================================================

@router.get(
    "/health-monitoring",
    response_model=SuccessResponse[SystemHealthResponse],
    summary="System Health Monitoring",
    description="Get detailed system health status and component health"
)
async def get_health_monitoring(
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get health monitoring data:
    - Overall system health status
    - Individual component health (DB, LLMs, etc.)
    - Active alerts
    - Resource usage
    - System uptime
    """
    request_id = get_request_id()

    try:
        health_data = await service.get_health_monitoring()

        return SuccessResponse(
            data=health_data,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "HEALTH_MONITORING_ERROR", "message": f"Failed to load health data: {str(e)}"}
        )


# ============================================================================
# RAG METRICS
# ============================================================================

@router.get(
    "/rag-metrics",
    response_model=SuccessResponse[RAGMetricsOverview],
    summary="RAG Quality Metrics",
    description="Get RAG system quality and performance metrics"
)
async def get_rag_metrics(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get RAG metrics:
    - Per-strategy performance (vector, graph, hybrid)
    - Retrieval and generation times
    - Quality scores (confidence, similarity)
    - User satisfaction metrics
    """
    request_id = get_request_id()

    try:
        rag_data = await service.get_rag_metrics(days=days)

        return SuccessResponse(
            data=rag_data,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "RAG_METRICS_ERROR", "message": f"Failed to load RAG data: {str(e)}"}
        )


# ============================================================================
# AUDIT LOGS
# ============================================================================

@router.get(
    "/audit-logs",
    response_model=SuccessResponse[dict],
    summary="Audit Logs",
    description="Get paginated audit logs with filtering"
)
async def get_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    action_category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_date: Optional[datetime] = Query(None, description="Filter from date"),
    end_date: Optional[datetime] = Query(None, description="Filter to date"),
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get audit logs with filters:
    - User ID filter
    - Action category filter
    - Severity filter
    - Date range filter
    - Pagination support
    """
    request_id = get_request_id()

    try:
        audit_data = await service.get_audit_logs(
            page=page,
            limit=limit,
            user_id=user_id,
            action_category=action_category,
            severity=severity,
            start_date=start_date,
            end_date=end_date
        )

        return SuccessResponse(
            data=audit_data,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "AUDIT_LOGS_ERROR", "message": f"Failed to load audit logs: {str(e)}"}
        )


@router.get(
    "/audit-stats",
    response_model=SuccessResponse[AuditLogStats],
    summary="Audit Log Statistics",
    description="Get aggregated audit log statistics"
)
async def get_audit_stats(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    admin_user: dict = Depends(get_admin_user),
    service: AdminDashboardService = Depends(get_admin_dashboard_service)
):
    """
    Get audit statistics:
    - Total events
    - Events by category
    - Events by severity
    - Top users by activity
    - Recent security events
    """
    request_id = get_request_id()

    try:
        stats = await service.get_audit_stats(hours=hours)

        return SuccessResponse(
            data=stats,
            meta=MetaInfo(request_id=request_id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "AUDIT_STATS_ERROR", "message": f"Failed to load audit stats: {str(e)}"}
        )
