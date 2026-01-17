"""
Admin Dashboard Pydantic Models
Request/Response models for all dashboard endpoints
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from uuid import UUID


# ============================================================================
# ENUMS
# ============================================================================

class HealthStatus(str, Enum):
    """System health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


class AuditSeverity(str, Enum):
    """Audit log severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditCategory(str, Enum):
    """Audit log categories"""
    USER_MANAGEMENT = "USER_MANAGEMENT"
    CONTENT = "CONTENT"
    SYSTEM = "SYSTEM"
    SECURITY = "SECURITY"
    GOVERNANCE = "GOVERNANCE"
    AGENT = "AGENT"


class TimeGranularity(str, Enum):
    """Time series granularity"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ============================================================================
# EXECUTIVE DASHBOARD MODELS
# ============================================================================

class UserMetricsSummary(BaseModel):
    """User statistics summary"""
    total_users: int = Field(..., description="Total registered users")
    active_users: int = Field(..., description="Currently active users")
    new_users_7d: int = Field(..., description="New users in last 7 days")
    new_users_30d: int = Field(..., description="New users in last 30 days")
    users_by_role: Dict[str, int] = Field(default_factory=dict, description="Users grouped by role")
    users_by_status: Dict[str, int] = Field(default_factory=dict, description="Users grouped by status")


class TokenMetricsSummary(BaseModel):
    """Token usage summary"""
    total_tokens_today: int = Field(0, description="Total tokens used today")
    total_tokens_7d: int = Field(0, description="Total tokens in last 7 days")
    total_tokens_30d: int = Field(0, description="Total tokens in last 30 days")
    avg_tokens_per_request: float = Field(0.0, description="Average tokens per request")
    estimated_cost_today: float = Field(0.0, description="Estimated cost today (USD)")
    estimated_cost_30d: float = Field(0.0, description="Estimated cost last 30 days (USD)")
    top_endpoints: List[Dict[str, Any]] = Field(default_factory=list)
    top_users: List[Dict[str, Any]] = Field(default_factory=list)


class QueryMetricsSummary(BaseModel):
    """Query execution summary"""
    total_queries_today: int = Field(0, description="Total queries today")
    total_queries_7d: int = Field(0, description="Total queries in last 7 days")
    success_rate: float = Field(0.0, description="Query success rate (0-1)")
    avg_latency_ms: int = Field(0, description="Average latency in ms")
    p95_latency_ms: int = Field(0, description="95th percentile latency")
    queries_by_strategy: Dict[str, int] = Field(default_factory=dict)
    queries_by_agent: Dict[str, int] = Field(default_factory=dict)


class SystemHealthSummary(BaseModel):
    """System health overview"""
    status: HealthStatus = Field(HealthStatus.HEALTHY)
    components: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.now)
    uptime_seconds: int = Field(0)


class TrendDataPoint(BaseModel):
    """Single data point for time series"""
    timestamp: datetime
    value: float
    label: Optional[str] = None


class ExecutiveDashboardResponse(BaseModel):
    """Complete executive dashboard response"""
    users: UserMetricsSummary
    tokens: TokenMetricsSummary
    queries: QueryMetricsSummary
    system_health: SystemHealthSummary

    # Trend data for charts
    user_trend: List[TrendDataPoint] = Field(default_factory=list)
    query_trend: List[TrendDataPoint] = Field(default_factory=list)
    token_trend: List[TrendDataPoint] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_schema_extra = {
            "example": {
                "users": {
                    "total_users": 150,
                    "active_users": 120,
                    "new_users_7d": 12,
                    "new_users_30d": 45,
                    "users_by_role": {"admin": 3, "user": 147}
                },
                "tokens": {
                    "total_tokens_today": 2500000,
                    "estimated_cost_today": 125.50
                },
                "queries": {
                    "total_queries_today": 450,
                    "success_rate": 0.98,
                    "avg_latency_ms": 1250
                },
                "system_health": {
                    "status": "healthy",
                    "active_alerts": []
                },
                "generated_at": "2026-01-11T10:30:00Z"
            }
        }


# ============================================================================
# TOKEN GOVERNANCE MODELS
# ============================================================================

class TokenUsageTrend(BaseModel):
    """Token usage trend data point"""
    date: date
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    estimated_cost: float = 0.0


class UserTokenUsage(BaseModel):
    """Per-user token usage"""
    user_id: str
    email: str
    display_name: Optional[str] = None
    total_tokens: int = 0
    request_count: int = 0
    avg_tokens_per_request: float = 0.0
    total_cost: float = 0.0


class EndpointTokenUsage(BaseModel):
    """Per-endpoint token usage"""
    endpoint: str
    total_tokens: int = 0
    request_count: int = 0
    avg_tokens: float = 0.0
    avg_latency_ms: int = 0


class TokenGovernanceOverview(BaseModel):
    """Token governance overview response"""
    total_tokens: int = Field(0, description="Total tokens in period")
    total_requests: int = Field(0, description="Total API requests")
    avg_tokens_per_request: float = Field(0.0)
    total_cost: float = Field(0.0, description="Total estimated cost (USD)")

    daily_trend: List[TokenUsageTrend] = Field(default_factory=list)
    top_users: List[UserTokenUsage] = Field(default_factory=list)
    top_endpoints: List[EndpointTokenUsage] = Field(default_factory=list)
    by_agent_type: Dict[str, int] = Field(default_factory=dict)
    by_model: Dict[str, int] = Field(default_factory=dict)


# ============================================================================
# USER MANAGEMENT MODELS
# ============================================================================

class UserListItem(BaseModel):
    """User list item for admin view"""
    id: str
    email: str
    display_name: Optional[str] = None
    role: str
    status: str
    is_active: bool = True
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    query_count_30d: int = 0
    token_usage_30d: int = 0


class UserDetailResponse(BaseModel):
    """Detailed user information for admin"""
    id: str
    email: str
    display_name: Optional[str] = None
    role: str
    status: str
    department: Optional[str] = None
    language: str = "ko"
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    # Activity metrics
    total_queries: int = 0
    total_tokens: int = 0
    total_sessions: int = 0

    # Recent activity
    recent_activity: List[Dict[str, Any]] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    """Request to update user"""
    role: Optional[str] = Field(None, pattern=r'^(admin|leader|senior|user|guest)$')
    status: Optional[str] = Field(None, pattern=r'^(active|inactive|suspended|pending)$')
    is_active: Optional[bool] = None
    display_name: Optional[str] = None
    department: Optional[str] = None


# ============================================================================
# AUDIT LOG MODELS
# ============================================================================

class AuditLogEntry(BaseModel):
    """Audit log entry"""
    id: str
    timestamp: datetime
    user_id: str
    user_email: str
    user_role: str
    action: str
    action_category: AuditCategory
    severity: AuditSeverity
    resource_type: str
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None


class AuditLogQuery(BaseModel):
    """Audit log query parameters"""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    user_id: Optional[str] = None
    action_category: Optional[AuditCategory] = None
    severity: Optional[AuditSeverity] = None
    resource_type: Optional[str] = None
    success: Optional[bool] = None
    page: int = Field(1, ge=1)
    limit: int = Field(50, ge=1, le=500)


class AuditLogResponse(BaseModel):
    """Paginated audit log response"""
    entries: List[AuditLogEntry]
    total: int
    page: int
    limit: int
    has_more: bool


class AuditLogStats(BaseModel):
    """Audit log statistics"""
    total_events: int
    events_by_category: Dict[str, int]
    events_by_severity: Dict[str, int]
    events_by_user: List[Dict[str, Any]]
    recent_security_events: List[AuditLogEntry]


# ============================================================================
# AGENT PERFORMANCE MODELS
# ============================================================================

class AgentPerformanceMetrics(BaseModel):
    """Single agent performance metrics"""
    agent_type: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    success_rate: float = Field(0.0, ge=0.0, le=1.0)
    avg_execution_time_ms: int = 0
    p95_execution_time_ms: int = 0
    avg_confidence_score: Optional[float] = None
    total_tokens: int = 0
    total_retries: int = 0


class AgentPerformanceTrend(BaseModel):
    """Agent performance trend data point"""
    date: date
    agent_type: str
    executions: int = 0
    success_rate: float = 0.0
    avg_latency_ms: int = 0


class AgentPerformanceOverview(BaseModel):
    """Agent performance overview response"""
    total_executions_today: int = 0
    overall_success_rate: float = 0.0
    agents: List[AgentPerformanceMetrics] = Field(default_factory=list)
    trend: List[AgentPerformanceTrend] = Field(default_factory=list)
    error_breakdown: Dict[str, int] = Field(default_factory=dict)


# ============================================================================
# HEALTH MONITORING MODELS
# ============================================================================

class ComponentHealth(BaseModel):
    """Individual component health"""
    name: str
    status: HealthStatus
    latency_ms: Optional[int] = None
    message: Optional[str] = None
    last_check: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SystemHealthResponse(BaseModel):
    """System health response"""
    overall_status: HealthStatus
    components: List[ComponentHealth]
    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    resource_usage: Dict[str, float] = Field(default_factory=dict)
    uptime_seconds: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class HealthHistoryPoint(BaseModel):
    """Health history data point"""
    timestamp: datetime
    status: HealthStatus
    component_statuses: Dict[str, str]


# ============================================================================
# RAG METRICS MODELS
# ============================================================================

class RAGStrategyMetrics(BaseModel):
    """RAG strategy performance metrics"""
    strategy: str
    total_queries: int = 0
    success_rate: float = 0.0
    avg_retrieval_time_ms: int = 0
    avg_generation_time_ms: int = 0
    avg_result_count: float = 0.0
    avg_similarity_score: float = 0.0
    avg_confidence_score: float = 0.0


class RAGQualityMetrics(BaseModel):
    """RAG quality indicators"""
    avg_user_rating: Optional[float] = None
    thumbs_up_count: int = 0
    thumbs_down_count: int = 0
    satisfaction_rate: Optional[float] = None
    queries_with_sources_pct: float = 0.0


class RAGMetricsOverview(BaseModel):
    """RAG metrics overview response"""
    total_queries: int = 0
    overall_success_rate: float = 0.0
    strategies: List[RAGStrategyMetrics] = Field(default_factory=list)
    quality: RAGQualityMetrics = Field(default_factory=RAGQualityMetrics)
    trend: List[Dict[str, Any]] = Field(default_factory=list)
    top_knowledge_sources: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# COMMON MODELS
# ============================================================================

class DateRangeQuery(BaseModel):
    """Common date range query parameters"""
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days: int = Field(7, ge=1, le=90, description="Number of days to look back")
    granularity: TimeGranularity = TimeGranularity.DAILY


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    items: List[Any]
    total: int
    page: int
    limit: int
    has_more: bool


class ExportRequest(BaseModel):
    """Export request parameters"""
    format: str = Field("csv", pattern=r'^(csv|json|xlsx)$')
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    include_fields: Optional[List[str]] = None
