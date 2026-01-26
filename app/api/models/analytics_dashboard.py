"""
Real-time Analytics Dashboard Models

Provides models for:
- Query analytics (popular questions, trends, unanswered rate)
- Response quality metrics (Faithfulness, Relevancy averages)
- Usage patterns (hourly/daily usage, user analysis)
- Content effectiveness (document citations, usefulness)
- System performance (latency, throughput, error rate)
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================
# Enums
# ============================================

class TimeGranularity(str, Enum):
    """Time granularity for analytics"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class MetricType(str, Enum):
    """Type of metric for tracking"""
    QUERY_COUNT = "query_count"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    SATISFACTION_RATE = "satisfaction_rate"
    FAITHFULNESS = "faithfulness"
    RELEVANCY = "relevancy"


class TrendDirection(str, Enum):
    """Trend direction indicator"""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


# ============================================
# Query Analytics Models
# ============================================

class PopularQuery(BaseModel):
    """Popular query with count and trend"""
    query: str = Field(..., description="질문 텍스트")
    query_hash: str = Field(..., description="질문 해시")
    count: int = Field(..., ge=0, description="질문 횟수")
    avg_response_time_ms: float = Field(default=0.0, description="평균 응답 시간 (ms)")
    avg_satisfaction: float = Field(default=0.0, ge=0.0, le=1.0, description="평균 만족도")
    last_asked_at: Optional[datetime] = Field(None, description="마지막 질문 시간")
    trend: TrendDirection = Field(default=TrendDirection.STABLE, description="트렌드")
    trend_percentage: float = Field(default=0.0, description="트렌드 변화율 (%)")


class SearchTrend(BaseModel):
    """Search trend data point"""
    timestamp: datetime = Field(..., description="시간")
    query_count: int = Field(default=0, ge=0, description="질문 수")
    unique_users: int = Field(default=0, ge=0, description="고유 사용자 수")
    avg_response_time_ms: float = Field(default=0.0, description="평균 응답 시간")


class UnansweredQuery(BaseModel):
    """Query that couldn't be answered"""
    query: str = Field(..., description="미답변 질문")
    query_hash: str = Field(..., description="질문 해시")
    count: int = Field(default=1, ge=1, description="발생 횟수")
    first_asked_at: datetime = Field(..., description="최초 질문 시간")
    last_asked_at: datetime = Field(..., description="마지막 질문 시간")
    failure_reasons: List[str] = Field(default_factory=list, description="실패 사유 목록")


class QueryAnalytics(BaseModel):
    """Comprehensive query analytics"""
    period_start: datetime = Field(..., description="기간 시작")
    period_end: datetime = Field(..., description="기간 종료")
    granularity: TimeGranularity = Field(default=TimeGranularity.DAILY)

    # Overview
    total_queries: int = Field(default=0, ge=0, description="총 질문 수")
    unique_queries: int = Field(default=0, ge=0, description="고유 질문 수")
    unique_users: int = Field(default=0, ge=0, description="고유 사용자 수")

    # Popular queries
    popular_queries: List[PopularQuery] = Field(default_factory=list, description="인기 질문 Top N")

    # Trends
    search_trends: List[SearchTrend] = Field(default_factory=list, description="검색 트렌드")

    # Unanswered
    unanswered_count: int = Field(default=0, ge=0, description="미답변 수")
    unanswered_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="미답변 비율")
    top_unanswered: List[UnansweredQuery] = Field(default_factory=list, description="주요 미답변 질문")

    # Query categories (if categorized)
    query_categories: Dict[str, int] = Field(default_factory=dict, description="카테고리별 질문 수")


# ============================================
# Response Quality Models
# ============================================

class QualityMetric(BaseModel):
    """Individual quality metric"""
    metric_name: str = Field(..., description="메트릭 이름")
    current_value: float = Field(..., ge=0.0, le=1.0, description="현재 값")
    previous_value: float = Field(default=0.0, ge=0.0, le=1.0, description="이전 값")
    trend: TrendDirection = Field(default=TrendDirection.STABLE)
    trend_percentage: float = Field(default=0.0, description="변화율 (%)")
    sample_count: int = Field(default=0, ge=0, description="샘플 수")


class QualityDistribution(BaseModel):
    """Quality score distribution"""
    excellent_count: int = Field(default=0, ge=0, description="우수 (>=0.8)")
    good_count: int = Field(default=0, ge=0, description="양호 (>=0.6)")
    fair_count: int = Field(default=0, ge=0, description="보통 (>=0.4)")
    poor_count: int = Field(default=0, ge=0, description="미흡 (<0.4)")

    @property
    def total(self) -> int:
        return self.excellent_count + self.good_count + self.fair_count + self.poor_count


class QualityTrend(BaseModel):
    """Quality trend data point"""
    timestamp: datetime
    faithfulness: float = Field(default=0.0, ge=0.0, le=1.0)
    context_relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    answer_relevancy: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sample_count: int = Field(default=0, ge=0)


class ResponseQualityAnalytics(BaseModel):
    """Response quality analytics"""
    period_start: datetime
    period_end: datetime

    # Core metrics
    avg_faithfulness: QualityMetric = Field(..., description="평균 Faithfulness")
    avg_context_relevance: QualityMetric = Field(..., description="평균 Context Relevance")
    avg_answer_relevancy: QualityMetric = Field(..., description="평균 Answer Relevancy")
    avg_overall_score: QualityMetric = Field(..., description="평균 전체 점수")

    # Distribution
    quality_distribution: QualityDistribution = Field(default_factory=QualityDistribution)

    # Trends
    quality_trends: List[QualityTrend] = Field(default_factory=list)

    # Issues
    common_issues: List[Dict[str, Any]] = Field(default_factory=list, description="주요 품질 이슈")

    # Evaluation count
    total_evaluations: int = Field(default=0, ge=0)


# ============================================
# Usage Pattern Models
# ============================================

class HourlyUsage(BaseModel):
    """Hourly usage statistics"""
    hour: int = Field(..., ge=0, le=23, description="시간 (0-23)")
    query_count: int = Field(default=0, ge=0)
    unique_users: int = Field(default=0, ge=0)
    avg_response_time_ms: float = Field(default=0.0)


class DailyUsage(BaseModel):
    """Daily usage statistics"""
    date: datetime
    query_count: int = Field(default=0, ge=0)
    unique_users: int = Field(default=0, ge=0)
    new_users: int = Field(default=0, ge=0)
    returning_users: int = Field(default=0, ge=0)
    avg_queries_per_user: float = Field(default=0.0)
    avg_session_duration_min: float = Field(default=0.0)
    satisfaction_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class UserSegment(BaseModel):
    """User segment analysis"""
    segment_name: str = Field(..., description="세그먼트 이름")
    user_count: int = Field(default=0, ge=0)
    query_count: int = Field(default=0, ge=0)
    avg_queries_per_user: float = Field(default=0.0)
    satisfaction_rate: float = Field(default=0.0)
    top_query_types: List[str] = Field(default_factory=list)


class UserActivity(BaseModel):
    """Individual user activity summary"""
    user_id: str
    username: Optional[str] = None
    total_queries: int = Field(default=0, ge=0)
    total_conversations: int = Field(default=0, ge=0)
    avg_queries_per_session: float = Field(default=0.0)
    avg_response_satisfaction: float = Field(default=0.0)
    most_active_hour: Optional[int] = Field(None, ge=0, le=23)
    last_active_at: Optional[datetime] = None
    top_query_topics: List[str] = Field(default_factory=list)


class UsagePatternAnalytics(BaseModel):
    """Usage pattern analytics"""
    period_start: datetime
    period_end: datetime

    # Overview
    total_queries: int = Field(default=0, ge=0)
    total_users: int = Field(default=0, ge=0)
    total_conversations: int = Field(default=0, ge=0)
    avg_queries_per_user: float = Field(default=0.0)

    # Time-based patterns
    hourly_usage: List[HourlyUsage] = Field(default_factory=list, description="시간대별 사용량")
    daily_usage: List[DailyUsage] = Field(default_factory=list, description="일별 사용량")
    peak_hours: List[int] = Field(default_factory=list, description="피크 시간대")

    # User analysis
    user_segments: List[UserSegment] = Field(default_factory=list, description="사용자 세그먼트")
    top_users: List[UserActivity] = Field(default_factory=list, description="상위 사용자")

    # Session analysis
    avg_session_duration_min: float = Field(default=0.0)
    avg_queries_per_session: float = Field(default=0.0)


# ============================================
# Content Effectiveness Models
# ============================================

class DocumentCitation(BaseModel):
    """Document citation statistics"""
    doc_id: str = Field(..., description="문서 ID")
    doc_name: str = Field(..., description="문서 이름")
    doc_type: Optional[str] = Field(None, description="문서 타입")
    citation_count: int = Field(default=0, ge=0, description="인용 횟수")
    unique_queries: int = Field(default=0, ge=0, description="관련 고유 질문 수")
    avg_relevance_score: float = Field(default=0.0, ge=0.0, le=1.0, description="평균 관련성 점수")
    helpfulness_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="유용성 평가")
    last_cited_at: Optional[datetime] = Field(None, description="마지막 인용 시간")
    trend: TrendDirection = Field(default=TrendDirection.STABLE)


class ChunkEffectiveness(BaseModel):
    """Individual chunk effectiveness"""
    chunk_id: str
    doc_id: str
    doc_name: str
    content_preview: str = Field(..., max_length=200)
    citation_count: int = Field(default=0, ge=0)
    avg_position: float = Field(default=0.0, description="평균 검색 순위")
    helpfulness_rate: float = Field(default=0.0)
    feedback_positive: int = Field(default=0, ge=0)
    feedback_negative: int = Field(default=0, ge=0)


class ContentGap(BaseModel):
    """Content gap identified from queries"""
    topic: str = Field(..., description="주제/토픽")
    query_examples: List[str] = Field(default_factory=list, description="관련 질문 예시")
    query_count: int = Field(default=0, ge=0, description="관련 질문 수")
    current_coverage_score: float = Field(default=0.0, ge=0.0, le=1.0, description="현재 커버리지")
    recommendation: str = Field(default="", description="개선 권장사항")


class ContentEffectivenessAnalytics(BaseModel):
    """Content effectiveness analytics"""
    period_start: datetime
    period_end: datetime

    # Overview
    total_documents: int = Field(default=0, ge=0)
    total_chunks: int = Field(default=0, ge=0)
    documents_cited: int = Field(default=0, ge=0)
    avg_citations_per_doc: float = Field(default=0.0)

    # Document rankings
    top_cited_documents: List[DocumentCitation] = Field(default_factory=list, description="인용 빈도 상위 문서")
    least_cited_documents: List[DocumentCitation] = Field(default_factory=list, description="인용 빈도 하위 문서")
    most_helpful_documents: List[DocumentCitation] = Field(default_factory=list, description="유용성 상위 문서")

    # Chunk analysis
    top_chunks: List[ChunkEffectiveness] = Field(default_factory=list, description="효과적인 청크")
    underperforming_chunks: List[ChunkEffectiveness] = Field(default_factory=list, description="저성과 청크")

    # Content gaps
    content_gaps: List[ContentGap] = Field(default_factory=list, description="콘텐츠 갭")

    # Usefulness metrics
    overall_helpfulness: float = Field(default=0.0, ge=0.0, le=1.0)
    citation_accuracy_rate: float = Field(default=0.0, ge=0.0, le=1.0)


# ============================================
# System Performance Models
# ============================================

class LatencyMetric(BaseModel):
    """Response latency metrics"""
    avg_ms: float = Field(default=0.0, ge=0.0, description="평균 응답 시간 (ms)")
    p50_ms: float = Field(default=0.0, ge=0.0, description="중앙값 (ms)")
    p90_ms: float = Field(default=0.0, ge=0.0, description="90th percentile (ms)")
    p95_ms: float = Field(default=0.0, ge=0.0, description="95th percentile (ms)")
    p99_ms: float = Field(default=0.0, ge=0.0, description="99th percentile (ms)")
    max_ms: float = Field(default=0.0, ge=0.0, description="최대 응답 시간 (ms)")
    min_ms: float = Field(default=0.0, ge=0.0, description="최소 응답 시간 (ms)")


class ThroughputMetric(BaseModel):
    """Throughput metrics"""
    requests_per_second: float = Field(default=0.0, ge=0.0, description="초당 요청 수")
    requests_per_minute: float = Field(default=0.0, ge=0.0, description="분당 요청 수")
    peak_rps: float = Field(default=0.0, ge=0.0, description="피크 RPS")
    total_requests: int = Field(default=0, ge=0, description="총 요청 수")


class ErrorMetric(BaseModel):
    """Error metrics"""
    total_errors: int = Field(default=0, ge=0, description="총 에러 수")
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="에러율")
    error_by_type: Dict[str, int] = Field(default_factory=dict, description="타입별 에러 수")
    error_by_endpoint: Dict[str, int] = Field(default_factory=dict, description="엔드포인트별 에러 수")


class ComponentHealth(BaseModel):
    """Individual component health status"""
    component_name: str = Field(..., description="컴포넌트 이름")
    status: str = Field(..., description="상태 (healthy/degraded/unhealthy)")
    latency_ms: float = Field(default=0.0, ge=0.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    last_check_at: datetime
    details: Dict[str, Any] = Field(default_factory=dict)


class PerformanceTrend(BaseModel):
    """Performance trend data point"""
    timestamp: datetime
    latency_ms: float = Field(default=0.0, ge=0.0)
    throughput_rpm: float = Field(default=0.0, ge=0.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    active_users: int = Field(default=0, ge=0)


class SystemPerformanceAnalytics(BaseModel):
    """System performance analytics"""
    period_start: datetime
    period_end: datetime

    # Latency
    latency: LatencyMetric = Field(default_factory=LatencyMetric, description="응답 지연시간")

    # Throughput
    throughput: ThroughputMetric = Field(default_factory=ThroughputMetric, description="처리량")

    # Errors
    errors: ErrorMetric = Field(default_factory=ErrorMetric, description="에러")

    # Component health
    component_health: List[ComponentHealth] = Field(default_factory=list, description="컴포넌트 상태")

    # Trends
    performance_trends: List[PerformanceTrend] = Field(default_factory=list, description="성능 트렌드")

    # Resource utilization (optional)
    cpu_usage_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    memory_usage_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    gpu_usage_percent: Optional[float] = Field(None, ge=0.0, le=100.0)


# ============================================
# Dashboard Summary Models
# ============================================

class DashboardWidget(BaseModel):
    """Generic dashboard widget data"""
    widget_id: str
    widget_type: str  # chart, metric, table, etc.
    title: str
    data: Any
    last_updated: datetime


class DashboardSummary(BaseModel):
    """Complete dashboard summary"""
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period_start: datetime
    period_end: datetime

    # Key metrics overview
    total_queries: int = Field(default=0, ge=0)
    total_users: int = Field(default=0, ge=0)
    avg_response_time_ms: float = Field(default=0.0)
    avg_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    satisfaction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    # Trends compared to previous period
    queries_trend: TrendDirection = Field(default=TrendDirection.STABLE)
    queries_change_percent: float = Field(default=0.0)
    quality_trend: TrendDirection = Field(default=TrendDirection.STABLE)
    quality_change_percent: float = Field(default=0.0)

    # Alerts/Issues
    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)
    top_issues: List[str] = Field(default_factory=list)

    # Quick stats
    top_queries: List[PopularQuery] = Field(default_factory=list)
    recent_quality_scores: List[float] = Field(default_factory=list)


# ============================================
# Request/Response Models
# ============================================

class AnalyticsRequest(BaseModel):
    """Request for analytics data"""
    start_date: Optional[datetime] = Field(None, description="시작 날짜")
    end_date: Optional[datetime] = Field(None, description="종료 날짜")
    granularity: TimeGranularity = Field(default=TimeGranularity.DAILY)
    user_id: Optional[str] = Field(None, description="특정 사용자 필터")
    limit: int = Field(default=10, ge=1, le=100, description="결과 수 제한")
    include_trends: bool = Field(default=True, description="트렌드 포함 여부")


class AnalyticsExportRequest(BaseModel):
    """Request to export analytics data"""
    analytics_type: str = Field(..., description="analytics type: query, quality, usage, content, performance")
    start_date: datetime
    end_date: datetime
    format: str = Field(default="json", description="export format: json, csv")
    include_details: bool = Field(default=False)
