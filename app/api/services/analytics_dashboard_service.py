"""
Real-time Analytics Dashboard Service

Provides analytics for:
- Query analysis (popular questions, trends, unanswered rate)
- Response quality metrics (Faithfulness, Relevancy averages)
- Usage patterns (hourly/daily usage, user analysis)
- Content effectiveness (document citations, usefulness)
- System performance (latency, throughput, error rate)
"""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from app.api.models.analytics_dashboard import (
    TimeGranularity, TrendDirection, MetricType,
    PopularQuery, SearchTrend, UnansweredQuery, QueryAnalytics,
    QualityMetric, QualityDistribution, QualityTrend, ResponseQualityAnalytics,
    HourlyUsage, DailyUsage, UserSegment, UserActivity, UsagePatternAnalytics,
    DocumentCitation, ChunkEffectiveness, ContentGap, ContentEffectivenessAnalytics,
    LatencyMetric, ThroughputMetric, ErrorMetric, ComponentHealth,
    PerformanceTrend, SystemPerformanceAnalytics,
    DashboardSummary, AnalyticsRequest
)

logger = logging.getLogger(__name__)


class AnalyticsDashboardService:
    """Service for real-time analytics dashboard"""

    def __init__(self, repository=None):
        self.repository = repository
        self._cache = {}
        self._cache_ttl = 60  # 1 minute cache

    def _hash_query(self, query: str) -> str:
        """Generate hash for query text"""
        normalized = query.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _calculate_trend(
        self,
        current: float,
        previous: float
    ) -> tuple[TrendDirection, float]:
        """Calculate trend direction and percentage"""
        if previous == 0:
            if current > 0:
                return TrendDirection.UP, 100.0
            return TrendDirection.STABLE, 0.0

        change_percent = ((current - previous) / previous) * 100

        if change_percent > 5:
            return TrendDirection.UP, change_percent
        elif change_percent < -5:
            return TrendDirection.DOWN, change_percent
        return TrendDirection.STABLE, change_percent

    # ============================================
    # Query Analytics
    # ============================================

    async def get_query_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        granularity: TimeGranularity = TimeGranularity.DAILY,
        limit: int = 10,
        user_id: Optional[str] = None
    ) -> QueryAnalytics:
        """Get comprehensive query analytics"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        try:
            # Get overview stats
            overview = await self.repository.get_query_overview(
                start_date, end_date, user_id
            ) if self.repository else {}

            # Get popular queries
            popular_raw = await self.repository.get_popular_queries(
                start_date, end_date, limit, user_id
            ) if self.repository else []

            popular_queries = [
                PopularQuery(
                    query=q.get("query_text", ""),
                    query_hash=q.get("query_hash", ""),
                    count=int(q.get("count", 0)),
                    avg_response_time_ms=float(q.get("avg_response_time_ms") or 0),
                    avg_satisfaction=float(q.get("avg_satisfaction") or 0),
                    last_asked_at=q.get("last_asked_at"),
                    trend=TrendDirection.STABLE,
                    trend_percentage=0.0
                )
                for q in popular_raw
            ]

            # Get search trends
            trends_raw = await self.repository.get_search_trends(
                start_date, end_date, granularity, user_id
            ) if self.repository else []

            search_trends = [
                SearchTrend(
                    timestamp=t.get("timestamp"),
                    query_count=int(t.get("query_count") or 0),
                    unique_users=int(t.get("unique_users") or 0),
                    avg_response_time_ms=float(t.get("avg_response_time_ms") or 0)
                )
                for t in trends_raw
            ]

            # Get unanswered queries
            unanswered_raw = await self.repository.get_unanswered_queries(
                start_date, end_date, limit
            ) if self.repository else []

            top_unanswered = [
                UnansweredQuery(
                    query=u.get("query_text", ""),
                    query_hash=u.get("query_hash", ""),
                    count=int(u.get("occurrence_count") or 1),
                    first_asked_at=u.get("first_asked_at") or datetime.utcnow(),
                    last_asked_at=u.get("last_asked_at") or datetime.utcnow(),
                    failure_reasons=u.get("failure_reasons") or []
                )
                for u in unanswered_raw
            ]

            total_queries = int(overview.get("total_queries", 0))
            unanswered_count = int(overview.get("unanswered_count", 0))

            return QueryAnalytics(
                period_start=start_date,
                period_end=end_date,
                granularity=granularity,
                total_queries=total_queries,
                unique_queries=int(overview.get("unique_queries", 0)),
                unique_users=int(overview.get("unique_users", 0)),
                popular_queries=popular_queries,
                search_trends=search_trends,
                unanswered_count=unanswered_count,
                unanswered_rate=unanswered_count / total_queries if total_queries > 0 else 0.0,
                top_unanswered=top_unanswered,
                query_categories=overview.get("query_categories", {})
            )

        except Exception as e:
            logger.error(f"Error getting query analytics: {e}")
            return QueryAnalytics(
                period_start=start_date,
                period_end=end_date,
                granularity=granularity
            )

    async def record_query(
        self,
        query: str,
        user_id: str,
        response_time_ms: int,
        was_answered: bool = True,
        answer_source: Optional[str] = None,
        sources_count: int = 0,
        evaluation_scores: Optional[Dict[str, float]] = None,
        conversation_id: Optional[UUID] = None
    ) -> None:
        """Record a query for analytics"""
        try:
            query_hash = self._hash_query(query)

            data = {
                "query_hash": query_hash,
                "query_text": query,
                "user_id": user_id,
                "response_time_ms": response_time_ms,
                "was_answered": was_answered,
                "answer_source": answer_source,
                "sources_count": sources_count,
                "conversation_id": str(conversation_id) if conversation_id else None
            }

            if evaluation_scores:
                data.update({
                    "faithfulness_score": evaluation_scores.get("faithfulness"),
                    "context_relevance_score": evaluation_scores.get("context_relevance"),
                    "answer_relevancy_score": evaluation_scores.get("answer_relevancy"),
                    "overall_quality_score": evaluation_scores.get("overall")
                })

            if self.repository:
                await self.repository.insert_query_analytics(data)

            # Update popular queries cache
            if self.repository:
                await self.repository.update_popular_query_cache(query_hash, query)

            # Track unanswered if applicable
            if not was_answered and self.repository:
                await self.repository.track_unanswered_query(query_hash, query)

        except Exception as e:
            logger.error(f"Error recording query: {e}")

    # ============================================
    # Response Quality Analytics
    # ============================================

    async def get_quality_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_trends: bool = True
    ) -> ResponseQualityAnalytics:
        """Get response quality analytics"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        # Previous period for comparison
        period_length = (end_date - start_date).days
        prev_start = start_date - timedelta(days=period_length)
        prev_end = start_date

        try:
            # Current period metrics
            current = await self.repository.get_quality_metrics(
                start_date, end_date
            ) if self.repository else {}

            # Previous period metrics
            previous = await self.repository.get_quality_metrics(
                prev_start, prev_end
            ) if self.repository else {}

            # Build quality metrics
            def build_metric(name: str, current_val: float, prev_val: float, count: int) -> QualityMetric:
                trend, pct = self._calculate_trend(current_val, prev_val)
                return QualityMetric(
                    metric_name=name,
                    current_value=current_val,
                    previous_value=prev_val,
                    trend=trend,
                    trend_percentage=pct,
                    sample_count=count
                )

            count = int(current.get("evaluation_count", 0))

            avg_faithfulness = build_metric(
                "Faithfulness",
                float(current.get("avg_faithfulness") or 0),
                float(previous.get("avg_faithfulness") or 0),
                count
            )

            avg_context_relevance = build_metric(
                "Context Relevance",
                float(current.get("avg_context_relevance") or 0),
                float(previous.get("avg_context_relevance") or 0),
                count
            )

            avg_answer_relevancy = build_metric(
                "Answer Relevancy",
                float(current.get("avg_answer_relevancy") or 0),
                float(previous.get("avg_answer_relevancy") or 0),
                count
            )

            avg_overall = build_metric(
                "Overall Score",
                float(current.get("avg_overall_quality") or 0),
                float(previous.get("avg_overall_quality") or 0),
                count
            )

            # Quality distribution
            dist = current.get("quality_distribution", {})
            quality_distribution = QualityDistribution(
                excellent_count=int(dist.get("excellent", 0)),
                good_count=int(dist.get("good", 0)),
                fair_count=int(dist.get("fair", 0)),
                poor_count=int(dist.get("poor", 0))
            )

            # Quality trends
            quality_trends = []
            if include_trends and self.repository:
                trends_raw = await self.repository.get_quality_trends(start_date, end_date)
                quality_trends = [
                    QualityTrend(
                        timestamp=t.get("timestamp"),
                        faithfulness=float(t.get("avg_faithfulness") or 0),
                        context_relevance=float(t.get("avg_context_relevance") or 0),
                        answer_relevancy=float(t.get("avg_answer_relevancy") or 0),
                        overall_score=float(t.get("avg_overall_quality") or 0),
                        sample_count=int(t.get("evaluation_count") or 0)
                    )
                    for t in trends_raw
                ]

            return ResponseQualityAnalytics(
                period_start=start_date,
                period_end=end_date,
                avg_faithfulness=avg_faithfulness,
                avg_context_relevance=avg_context_relevance,
                avg_answer_relevancy=avg_answer_relevancy,
                avg_overall_score=avg_overall,
                quality_distribution=quality_distribution,
                quality_trends=quality_trends,
                common_issues=current.get("common_issues", []),
                total_evaluations=count
            )

        except Exception as e:
            logger.error(f"Error getting quality analytics: {e}")
            return ResponseQualityAnalytics(
                period_start=start_date,
                period_end=end_date,
                avg_faithfulness=QualityMetric(metric_name="Faithfulness", current_value=0.0),
                avg_context_relevance=QualityMetric(metric_name="Context Relevance", current_value=0.0),
                avg_answer_relevancy=QualityMetric(metric_name="Answer Relevancy", current_value=0.0),
                avg_overall_score=QualityMetric(metric_name="Overall Score", current_value=0.0)
            )

    # ============================================
    # Usage Pattern Analytics
    # ============================================

    async def get_usage_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> UsagePatternAnalytics:
        """Get usage pattern analytics"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=7)

        try:
            # Overview
            overview = await self.repository.get_usage_overview(
                start_date, end_date
            ) if self.repository else {}

            # Hourly usage
            hourly_raw = await self.repository.get_hourly_usage(
                start_date, end_date
            ) if self.repository else []

            hourly_usage = [
                HourlyUsage(
                    hour=int(h.get("hour", 0)),
                    query_count=int(h.get("query_count") or 0),
                    unique_users=int(h.get("unique_users") or 0),
                    avg_response_time_ms=float(h.get("avg_response_time_ms") or 0)
                )
                for h in hourly_raw
            ]

            # Peak hours
            peak_hours = sorted(
                hourly_usage,
                key=lambda h: h.query_count,
                reverse=True
            )[:3]
            peak_hour_list = [h.hour for h in peak_hours]

            # Daily usage
            daily_raw = await self.repository.get_daily_usage(
                start_date, end_date
            ) if self.repository else []

            daily_usage = [
                DailyUsage(
                    date=d.get("date"),
                    query_count=int(d.get("query_count") or 0),
                    unique_users=int(d.get("unique_users") or 0),
                    new_users=int(d.get("new_users") or 0),
                    returning_users=int(d.get("returning_users") or 0),
                    avg_queries_per_user=float(d.get("avg_queries_per_user") or 0),
                    satisfaction_rate=float(d.get("satisfaction_rate") or 0)
                )
                for d in daily_raw
            ]

            # Top users
            users_raw = await self.repository.get_top_users(
                start_date, end_date, limit
            ) if self.repository else []

            top_users = [
                UserActivity(
                    user_id=u.get("user_id", ""),
                    username=u.get("username"),
                    total_queries=int(u.get("total_queries") or 0),
                    total_conversations=int(u.get("total_conversations") or 0),
                    avg_queries_per_session=float(u.get("avg_queries_per_session") or 0),
                    avg_response_satisfaction=float(u.get("avg_satisfaction") or 0),
                    most_active_hour=u.get("most_active_hour"),
                    last_active_at=u.get("last_active_at")
                )
                for u in users_raw
            ]

            total_queries = int(overview.get("total_queries", 0))
            total_users = int(overview.get("unique_users", 0))

            return UsagePatternAnalytics(
                period_start=start_date,
                period_end=end_date,
                total_queries=total_queries,
                total_users=total_users,
                total_conversations=int(overview.get("total_conversations", 0)),
                avg_queries_per_user=total_queries / total_users if total_users > 0 else 0,
                hourly_usage=hourly_usage,
                daily_usage=daily_usage,
                peak_hours=peak_hour_list,
                top_users=top_users,
                avg_session_duration_min=float(overview.get("avg_session_duration_min") or 0),
                avg_queries_per_session=float(overview.get("avg_queries_per_session") or 0)
            )

        except Exception as e:
            logger.error(f"Error getting usage analytics: {e}")
            return UsagePatternAnalytics(
                period_start=start_date,
                period_end=end_date
            )

    # ============================================
    # Content Effectiveness Analytics
    # ============================================

    async def get_content_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> ContentEffectivenessAnalytics:
        """Get content effectiveness analytics"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        try:
            # Overview
            overview = await self.repository.get_content_overview(
                start_date, end_date
            ) if self.repository else {}

            # Top cited documents
            cited_raw = await self.repository.get_top_cited_documents(
                start_date, end_date, limit
            ) if self.repository else []

            top_cited = [
                DocumentCitation(
                    doc_id=d.get("doc_id", ""),
                    doc_name=d.get("doc_name", "Unknown"),
                    citation_count=int(d.get("citation_count") or 0),
                    unique_queries=int(d.get("unique_queries") or 0),
                    avg_relevance_score=float(d.get("avg_relevance_score") or 0),
                    helpfulness_rate=float(d.get("helpfulness_rate") or 0),
                    last_cited_at=d.get("last_cited_at")
                )
                for d in cited_raw
            ]

            # Most helpful documents
            helpful_raw = await self.repository.get_most_helpful_documents(
                start_date, end_date, limit
            ) if self.repository else []

            most_helpful = [
                DocumentCitation(
                    doc_id=d.get("doc_id", ""),
                    doc_name=d.get("doc_name", "Unknown"),
                    citation_count=int(d.get("citation_count") or 0),
                    unique_queries=int(d.get("unique_queries") or 0),
                    avg_relevance_score=float(d.get("avg_relevance_score") or 0),
                    helpfulness_rate=float(d.get("helpfulness_rate") or 0),
                    last_cited_at=d.get("last_cited_at")
                )
                for d in helpful_raw
            ]

            # Content gaps
            gaps_raw = await self.repository.get_content_gaps(limit) if self.repository else []

            content_gaps = [
                ContentGap(
                    topic=g.get("topic", ""),
                    query_examples=g.get("query_examples", []),
                    query_count=int(g.get("query_count") or 0),
                    current_coverage_score=float(g.get("current_coverage_score") or 0),
                    recommendation=g.get("recommendation", "")
                )
                for g in gaps_raw
            ]

            return ContentEffectivenessAnalytics(
                period_start=start_date,
                period_end=end_date,
                total_documents=int(overview.get("total_documents", 0)),
                total_chunks=int(overview.get("total_chunks", 0)),
                documents_cited=int(overview.get("documents_cited", 0)),
                avg_citations_per_doc=float(overview.get("avg_citations_per_doc") or 0),
                top_cited_documents=top_cited,
                most_helpful_documents=most_helpful,
                content_gaps=content_gaps,
                overall_helpfulness=float(overview.get("overall_helpfulness") or 0),
                citation_accuracy_rate=float(overview.get("citation_accuracy_rate") or 0)
            )

        except Exception as e:
            logger.error(f"Error getting content analytics: {e}")
            return ContentEffectivenessAnalytics(
                period_start=start_date,
                period_end=end_date
            )

    async def record_citation(
        self,
        doc_id: str,
        doc_name: str,
        query: str,
        user_id: str,
        relevance_score: float,
        position: int,
        chunk_id: Optional[str] = None,
        was_helpful: Optional[bool] = None
    ) -> None:
        """Record a document citation for analytics"""
        try:
            query_hash = self._hash_query(query)

            data = {
                "doc_id": doc_id,
                "doc_name": doc_name,
                "chunk_id": chunk_id,
                "query_hash": query_hash,
                "query_text": query,
                "user_id": user_id,
                "relevance_score": relevance_score,
                "position_in_results": position,
                "was_helpful": was_helpful
            }

            if self.repository:
                await self.repository.insert_citation_analytics(data)

        except Exception as e:
            logger.error(f"Error recording citation: {e}")

    # ============================================
    # System Performance Analytics
    # ============================================

    async def get_performance_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_trends: bool = True
    ) -> SystemPerformanceAnalytics:
        """Get system performance analytics"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(hours=24)

        try:
            # Latency metrics
            latency_raw = await self.repository.get_latency_metrics(
                start_date, end_date
            ) if self.repository else {}

            latency = LatencyMetric(
                avg_ms=float(latency_raw.get("avg_ms") or 0),
                p50_ms=float(latency_raw.get("p50_ms") or 0),
                p90_ms=float(latency_raw.get("p90_ms") or 0),
                p95_ms=float(latency_raw.get("p95_ms") or 0),
                p99_ms=float(latency_raw.get("p99_ms") or 0),
                max_ms=float(latency_raw.get("max_ms") or 0),
                min_ms=float(latency_raw.get("min_ms") or 0)
            )

            # Throughput
            throughput_raw = await self.repository.get_throughput_metrics(
                start_date, end_date
            ) if self.repository else {}

            period_seconds = (end_date - start_date).total_seconds()
            total_requests = int(throughput_raw.get("total_requests", 0))

            throughput = ThroughputMetric(
                requests_per_second=total_requests / period_seconds if period_seconds > 0 else 0,
                requests_per_minute=total_requests / (period_seconds / 60) if period_seconds > 0 else 0,
                peak_rps=float(throughput_raw.get("peak_rps") or 0),
                total_requests=total_requests
            )

            # Errors
            error_raw = await self.repository.get_error_metrics(
                start_date, end_date
            ) if self.repository else {}

            errors = ErrorMetric(
                total_errors=int(error_raw.get("total_errors", 0)),
                error_rate=float(error_raw.get("error_rate") or 0),
                error_by_type=error_raw.get("error_by_type", {}),
                error_by_endpoint=error_raw.get("error_by_endpoint", {})
            )

            # Component health
            health_raw = await self.repository.get_component_health() if self.repository else []

            component_health = [
                ComponentHealth(
                    component_name=h.get("component_name", ""),
                    status=h.get("status", "unknown"),
                    latency_ms=float(h.get("latency_ms") or 0),
                    error_rate=float(h.get("error_rate") or 0),
                    last_check_at=h.get("last_check_at") or datetime.utcnow(),
                    details=h.get("details", {})
                )
                for h in health_raw
            ]

            # Performance trends
            performance_trends = []
            if include_trends and self.repository:
                trends_raw = await self.repository.get_performance_trends(start_date, end_date)
                performance_trends = [
                    PerformanceTrend(
                        timestamp=t.get("timestamp"),
                        latency_ms=float(t.get("avg_latency_ms") or 0),
                        throughput_rpm=float(t.get("requests_per_minute") or 0),
                        error_rate=float(t.get("error_rate") or 0),
                        active_users=int(t.get("active_users") or 0)
                    )
                    for t in trends_raw
                ]

            return SystemPerformanceAnalytics(
                period_start=start_date,
                period_end=end_date,
                latency=latency,
                throughput=throughput,
                errors=errors,
                component_health=component_health,
                performance_trends=performance_trends
            )

        except Exception as e:
            logger.error(f"Error getting performance analytics: {e}")
            return SystemPerformanceAnalytics(
                period_start=start_date,
                period_end=end_date
            )

    async def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: int,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Record a request for performance analytics"""
        try:
            data = {
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "response_time_ms": response_time_ms,
                "is_error": status_code >= 400,
                "error_type": error_type,
                "error_message": error_message,
                "user_id": user_id,
                "request_id": request_id
            }

            if self.repository:
                await self.repository.insert_performance_metric(data)

        except Exception as e:
            logger.error(f"Error recording request: {e}")

    # ============================================
    # Dashboard Summary
    # ============================================

    async def get_dashboard_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> DashboardSummary:
        """Get complete dashboard summary"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=1)

        # Previous period for comparison
        period_length = (end_date - start_date).days or 1
        prev_start = start_date - timedelta(days=period_length)
        prev_end = start_date

        try:
            # Current period stats
            current = await self.repository.get_dashboard_summary(
                start_date, end_date
            ) if self.repository else {}

            # Previous period stats
            previous = await self.repository.get_dashboard_summary(
                prev_start, prev_end
            ) if self.repository else {}

            # Calculate trends
            query_trend, query_pct = self._calculate_trend(
                float(current.get("total_queries", 0)),
                float(previous.get("total_queries", 0))
            )

            quality_trend, quality_pct = self._calculate_trend(
                float(current.get("avg_quality_score") or 0),
                float(previous.get("avg_quality_score") or 0)
            )

            # Get top queries
            popular_raw = await self.repository.get_popular_queries(
                start_date, end_date, 5
            ) if self.repository else []

            top_queries = [
                PopularQuery(
                    query=q.get("query_text", ""),
                    query_hash=q.get("query_hash", ""),
                    count=int(q.get("count", 0)),
                    avg_response_time_ms=float(q.get("avg_response_time_ms") or 0),
                    avg_satisfaction=float(q.get("avg_satisfaction") or 0),
                    last_asked_at=q.get("last_asked_at")
                )
                for q in popular_raw
            ]

            return DashboardSummary(
                generated_at=datetime.utcnow(),
                period_start=start_date,
                period_end=end_date,
                total_queries=int(current.get("total_queries", 0)),
                total_users=int(current.get("unique_users", 0)),
                avg_response_time_ms=float(current.get("avg_response_time_ms") or 0),
                avg_quality_score=float(current.get("avg_quality_score") or 0),
                satisfaction_rate=float(current.get("satisfaction_rate") or 0),
                error_rate=float(current.get("error_rate") or 0),
                queries_trend=query_trend,
                queries_change_percent=query_pct,
                quality_trend=quality_trend,
                quality_change_percent=quality_pct,
                active_alerts=current.get("active_alerts", []),
                top_issues=current.get("top_issues", []),
                top_queries=top_queries,
                recent_quality_scores=current.get("recent_quality_scores", [])
            )

        except Exception as e:
            logger.error(f"Error getting dashboard summary: {e}")
            return DashboardSummary(
                period_start=start_date,
                period_end=end_date
            )

    # ============================================
    # Aggregation Jobs
    # ============================================

    async def aggregate_hourly_stats(self) -> None:
        """Aggregate stats for the previous hour"""
        try:
            if self.repository:
                await self.repository.aggregate_hourly_analytics()
            logger.info("Hourly analytics aggregation completed")
        except Exception as e:
            logger.error(f"Error aggregating hourly stats: {e}")

    async def aggregate_daily_stats(self) -> None:
        """Aggregate stats for the previous day"""
        try:
            if self.repository:
                await self.repository.aggregate_daily_analytics()
            logger.info("Daily analytics aggregation completed")
        except Exception as e:
            logger.error(f"Error aggregating daily stats: {e}")

    async def update_user_activity_summary(self, user_id: str) -> None:
        """Update user activity summary"""
        try:
            if self.repository:
                await self.repository.update_user_activity_summary(user_id)
        except Exception as e:
            logger.error(f"Error updating user activity summary: {e}")
