"""
Analytics Dashboard Repository

Data access layer for analytics dashboard data.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from app.api.models.analytics_dashboard import TimeGranularity

logger = logging.getLogger(__name__)


class AnalyticsDashboardRepository:
    """Repository for analytics dashboard data access"""

    def __init__(self, db_pool=None):
        self.db_pool = db_pool

    async def _execute_query(
        self,
        query: str,
        params: tuple = (),
        fetch_one: bool = False
    ) -> Any:
        """Execute a database query"""
        if not self.db_pool:
            return {} if fetch_one else []

        try:
            async with self.db_pool.acquire() as conn:
                if fetch_one:
                    row = await conn.fetchrow(query, *params)
                    return dict(row) if row else {}
                else:
                    rows = await conn.fetch(query, *params)
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return {} if fetch_one else []

    # ============================================
    # Query Analytics
    # ============================================

    async def get_query_overview(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get query overview statistics"""
        user_filter = "AND user_id = $3" if user_id else ""
        params = [start_date, end_date]
        if user_id:
            params.append(user_id)

        query = f"""
            SELECT
                COUNT(*) as total_queries,
                COUNT(DISTINCT query_hash) as unique_queries,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(*) FILTER (WHERE was_answered = FALSE) as unanswered_count,
                AVG(response_time_ms) as avg_response_time_ms
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            {user_filter}
        """

        return await self._execute_query(query, tuple(params), fetch_one=True)

    async def get_popular_queries(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get most popular queries"""
        user_filter = "AND user_id = $4" if user_id else ""
        params = [start_date, end_date, limit]
        if user_id:
            params.append(user_id)

        query = f"""
            SELECT
                query_hash,
                query_text,
                COUNT(*) as count,
                AVG(response_time_ms) as avg_response_time_ms,
                AVG(CASE WHEN feedback_type = 'thumbs_up' THEN 1.0
                         WHEN feedback_type = 'thumbs_down' THEN 0.0
                         ELSE NULL END) as avg_satisfaction,
                MAX(created_at) as last_asked_at
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            {user_filter}
            GROUP BY query_hash, query_text
            ORDER BY count DESC
            LIMIT $3
        """

        return await self._execute_query(query, tuple(params))

    async def get_search_trends(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: TimeGranularity,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get search trends over time"""
        if granularity == TimeGranularity.HOURLY:
            time_bucket = "DATE_TRUNC('hour', created_at)"
        elif granularity == TimeGranularity.WEEKLY:
            time_bucket = "DATE_TRUNC('week', created_at)"
        elif granularity == TimeGranularity.MONTHLY:
            time_bucket = "DATE_TRUNC('month', created_at)"
        else:
            time_bucket = "DATE_TRUNC('day', created_at)"

        user_filter = "AND user_id = $3" if user_id else ""
        params = [start_date, end_date]
        if user_id:
            params.append(user_id)

        query = f"""
            SELECT
                {time_bucket} as timestamp,
                COUNT(*) as query_count,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(response_time_ms) as avg_response_time_ms
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            {user_filter}
            GROUP BY {time_bucket}
            ORDER BY timestamp
        """

        return await self._execute_query(query, tuple(params))

    async def get_unanswered_queries(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get unanswered queries"""
        query = """
            SELECT
                query_hash,
                query_text,
                occurrence_count,
                failure_reasons,
                first_asked_at,
                last_asked_at
            FROM unanswered_queries
            WHERE is_resolved = FALSE
            AND last_asked_at >= $1
            AND last_asked_at <= $2
            ORDER BY occurrence_count DESC
            LIMIT $3
        """

        return await self._execute_query(query, (start_date, end_date, limit))

    async def insert_query_analytics(self, data: Dict[str, Any]) -> None:
        """Insert query analytics record"""
        query = """
            INSERT INTO query_analytics (
                query_hash, query_text, user_id, conversation_id,
                response_time_ms, was_answered, answer_source, sources_count,
                evaluation_id, faithfulness_score, context_relevance_score,
                answer_relevancy_score, overall_quality_score
            ) VALUES (
                $1, $2, $3, $4::UUID,
                $5, $6, $7, $8,
                $9::UUID, $10, $11, $12, $13
            )
        """

        params = (
            data.get("query_hash"),
            data.get("query_text"),
            data.get("user_id"),
            data.get("conversation_id"),
            data.get("response_time_ms"),
            data.get("was_answered", True),
            data.get("answer_source"),
            data.get("sources_count", 0),
            data.get("evaluation_id"),
            data.get("faithfulness_score"),
            data.get("context_relevance_score"),
            data.get("answer_relevancy_score"),
            data.get("overall_quality_score")
        )

        await self._execute_query(query, params)

    async def update_popular_query_cache(
        self,
        query_hash: str,
        query_text: str
    ) -> None:
        """Update popular queries cache"""
        query = """
            INSERT INTO popular_queries_cache (
                query_hash, query_text, total_count, period_count,
                first_asked_at, last_asked_at
            ) VALUES (
                $1, $2, 1, 1, NOW(), NOW()
            )
            ON CONFLICT (query_hash) DO UPDATE SET
                total_count = popular_queries_cache.total_count + 1,
                period_count = popular_queries_cache.period_count + 1,
                last_asked_at = NOW(),
                last_updated_at = NOW()
        """

        await self._execute_query(query, (query_hash, query_text))

    async def track_unanswered_query(
        self,
        query_hash: str,
        query_text: str,
        failure_reason: Optional[str] = None
    ) -> None:
        """Track an unanswered query"""
        query = """
            INSERT INTO unanswered_queries (
                query_hash, query_text, occurrence_count,
                failure_reasons, first_asked_at, last_asked_at
            ) VALUES (
                $1, $2, 1,
                CASE WHEN $3 IS NOT NULL THEN jsonb_build_array($3) ELSE '[]'::JSONB END,
                NOW(), NOW()
            )
            ON CONFLICT (query_hash) DO UPDATE SET
                occurrence_count = unanswered_queries.occurrence_count + 1,
                failure_reasons = CASE
                    WHEN $3 IS NOT NULL AND NOT (unanswered_queries.failure_reasons ? $3)
                    THEN unanswered_queries.failure_reasons || jsonb_build_array($3)
                    ELSE unanswered_queries.failure_reasons
                END,
                last_asked_at = NOW()
        """

        await self._execute_query(query, (query_hash, query_text, failure_reason))

    # ============================================
    # Quality Analytics
    # ============================================

    async def get_quality_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get quality metrics for a period"""
        query = """
            SELECT
                AVG(faithfulness_score) FILTER (WHERE faithfulness_score IS NOT NULL) as avg_faithfulness,
                AVG(context_relevance_score) FILTER (WHERE context_relevance_score IS NOT NULL) as avg_context_relevance,
                AVG(answer_relevancy_score) FILTER (WHERE answer_relevancy_score IS NOT NULL) as avg_answer_relevancy,
                AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL) as avg_overall_quality,
                COUNT(*) FILTER (WHERE overall_quality_score IS NOT NULL) as evaluation_count,
                COUNT(*) FILTER (WHERE overall_quality_score >= 0.8) as excellent,
                COUNT(*) FILTER (WHERE overall_quality_score >= 0.6 AND overall_quality_score < 0.8) as good,
                COUNT(*) FILTER (WHERE overall_quality_score >= 0.4 AND overall_quality_score < 0.6) as fair,
                COUNT(*) FILTER (WHERE overall_quality_score < 0.4) as poor
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
        """

        result = await self._execute_query(query, (start_date, end_date), fetch_one=True)

        # Add quality distribution
        result["quality_distribution"] = {
            "excellent": result.get("excellent", 0),
            "good": result.get("good", 0),
            "fair": result.get("fair", 0),
            "poor": result.get("poor", 0)
        }

        return result

    async def get_quality_trends(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get quality trends over time"""
        query = """
            SELECT
                DATE_TRUNC('day', created_at) as timestamp,
                AVG(faithfulness_score) FILTER (WHERE faithfulness_score IS NOT NULL) as avg_faithfulness,
                AVG(context_relevance_score) FILTER (WHERE context_relevance_score IS NOT NULL) as avg_context_relevance,
                AVG(answer_relevancy_score) FILTER (WHERE answer_relevancy_score IS NOT NULL) as avg_answer_relevancy,
                AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL) as avg_overall_quality,
                COUNT(*) FILTER (WHERE overall_quality_score IS NOT NULL) as evaluation_count
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY timestamp
        """

        return await self._execute_query(query, (start_date, end_date))

    # ============================================
    # Usage Analytics
    # ============================================

    async def get_usage_overview(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get usage overview"""
        query = """
            SELECT
                COUNT(*) as total_queries,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT conversation_id) as total_conversations,
                AVG(response_time_ms) as avg_response_time_ms
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
        """

        return await self._execute_query(query, (start_date, end_date), fetch_one=True)

    async def get_hourly_usage(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get hourly usage pattern"""
        query = """
            SELECT
                EXTRACT(HOUR FROM created_at)::INTEGER as hour,
                COUNT(*) as query_count,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(response_time_ms) as avg_response_time_ms
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY EXTRACT(HOUR FROM created_at)
            ORDER BY hour
        """

        return await self._execute_query(query, (start_date, end_date))

    async def get_daily_usage(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get daily usage statistics"""
        query = """
            SELECT
                DATE_TRUNC('day', created_at) as date,
                COUNT(*) as query_count,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(response_time_ms) as avg_response_time_ms,
                CASE
                    WHEN COUNT(*) FILTER (WHERE feedback_type IS NOT NULL) > 0
                    THEN COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::FLOAT /
                         COUNT(*) FILTER (WHERE feedback_type IS NOT NULL)
                    ELSE NULL
                END as satisfaction_rate
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY DATE_TRUNC('day', created_at)
            ORDER BY date
        """

        return await self._execute_query(query, (start_date, end_date))

    async def get_top_users(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top users by activity"""
        query = """
            SELECT
                user_id,
                COUNT(*) as total_queries,
                COUNT(DISTINCT conversation_id) as total_conversations,
                AVG(response_time_ms) as avg_response_time_ms,
                AVG(CASE WHEN feedback_type = 'thumbs_up' THEN 1.0
                         WHEN feedback_type = 'thumbs_down' THEN 0.0
                         ELSE NULL END) as avg_satisfaction,
                MAX(created_at) as last_active_at
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            GROUP BY user_id
            ORDER BY total_queries DESC
            LIMIT $3
        """

        return await self._execute_query(query, (start_date, end_date, limit))

    async def update_user_activity_summary(self, user_id: str) -> None:
        """Update user activity summary"""
        query = """
            INSERT INTO user_activity_summary (
                user_id, total_queries, total_conversations,
                thumbs_up_given, thumbs_down_given,
                first_active_at, last_active_at
            )
            SELECT
                $1,
                COUNT(*),
                COUNT(DISTINCT conversation_id),
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up'),
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down'),
                MIN(created_at),
                MAX(created_at)
            FROM query_analytics
            WHERE user_id = $1
            ON CONFLICT (user_id) DO UPDATE SET
                total_queries = EXCLUDED.total_queries,
                total_conversations = EXCLUDED.total_conversations,
                thumbs_up_given = EXCLUDED.thumbs_up_given,
                thumbs_down_given = EXCLUDED.thumbs_down_given,
                last_active_at = EXCLUDED.last_active_at,
                last_updated_at = NOW()
        """

        await self._execute_query(query, (user_id,))

    # ============================================
    # Content Analytics
    # ============================================

    async def get_content_overview(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get content effectiveness overview"""
        query = """
            SELECT
                COUNT(DISTINCT doc_id) as documents_cited,
                COUNT(*) as total_citations,
                AVG(relevance_score) as avg_relevance_score,
                CASE
                    WHEN COUNT(*) FILTER (WHERE was_helpful IS NOT NULL) > 0
                    THEN COUNT(*) FILTER (WHERE was_helpful = TRUE)::FLOAT /
                         COUNT(*) FILTER (WHERE was_helpful IS NOT NULL)
                    ELSE NULL
                END as overall_helpfulness
            FROM document_citation_analytics
            WHERE cited_at >= $1 AND cited_at <= $2
        """

        result = await self._execute_query(query, (start_date, end_date), fetch_one=True)

        # If document_citation_analytics is empty, get total documents count
        if result.get("documents_cited", 0) == 0:
            fallback_query = """
                SELECT
                    (SELECT COUNT(*) FROM documents) as total_documents,
                    (SELECT COUNT(*) FROM text_chunks) as total_chunks,
                    0 as documents_cited,
                    0 as total_citations,
                    NULL as avg_relevance_score,
                    NULL as overall_helpfulness
            """
            result = await self._execute_query(fallback_query, (), fetch_one=True)

        return result

    async def get_top_cited_documents(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most cited documents"""
        query = """
            SELECT
                doc_id,
                doc_name,
                COUNT(*) as citation_count,
                COUNT(DISTINCT query_hash) as unique_queries,
                AVG(relevance_score) as avg_relevance_score,
                CASE
                    WHEN COUNT(*) FILTER (WHERE was_helpful IS NOT NULL) > 0
                    THEN COUNT(*) FILTER (WHERE was_helpful = TRUE)::FLOAT /
                         COUNT(*) FILTER (WHERE was_helpful IS NOT NULL)
                    ELSE NULL
                END as helpfulness_rate,
                MAX(cited_at) as last_cited_at
            FROM document_citation_analytics
            WHERE cited_at >= $1 AND cited_at <= $2
            GROUP BY doc_id, doc_name
            ORDER BY citation_count DESC
            LIMIT $3
        """

        return await self._execute_query(query, (start_date, end_date, limit))

    async def get_most_helpful_documents(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most helpful documents"""
        query = """
            SELECT
                doc_id,
                doc_name,
                COUNT(*) as citation_count,
                COUNT(DISTINCT query_hash) as unique_queries,
                AVG(relevance_score) as avg_relevance_score,
                CASE
                    WHEN COUNT(*) FILTER (WHERE was_helpful IS NOT NULL) > 0
                    THEN COUNT(*) FILTER (WHERE was_helpful = TRUE)::FLOAT /
                         COUNT(*) FILTER (WHERE was_helpful IS NOT NULL)
                    ELSE NULL
                END as helpfulness_rate,
                MAX(cited_at) as last_cited_at
            FROM document_citation_analytics
            WHERE cited_at >= $1 AND cited_at <= $2
            AND was_helpful IS NOT NULL
            GROUP BY doc_id, doc_name
            HAVING COUNT(*) FILTER (WHERE was_helpful IS NOT NULL) > 0
            ORDER BY helpfulness_rate DESC NULLS LAST, citation_count DESC
            LIMIT $3
        """

        return await self._execute_query(query, (start_date, end_date, limit))

    async def get_content_gaps(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get identified content gaps"""
        query = """
            SELECT
                topic,
                query_examples,
                query_count,
                current_coverage_score,
                recommendation
            FROM content_gaps
            WHERE status = 'identified'
            ORDER BY query_count DESC
            LIMIT $1
        """

        return await self._execute_query(query, (limit,))

    async def insert_citation_analytics(self, data: Dict[str, Any]) -> None:
        """Insert citation analytics record"""
        query = """
            INSERT INTO document_citation_analytics (
                doc_id, doc_name, chunk_id,
                query_hash, query_text, user_id,
                relevance_score, position_in_results, was_helpful
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """

        params = (
            data.get("doc_id"),
            data.get("doc_name"),
            data.get("chunk_id"),
            data.get("query_hash"),
            data.get("query_text"),
            data.get("user_id"),
            data.get("relevance_score"),
            data.get("position_in_results"),
            data.get("was_helpful")
        )

        await self._execute_query(query, params)

    # ============================================
    # Performance Analytics
    # ============================================

    async def get_latency_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get latency metrics"""
        query = """
            SELECT
                AVG(response_time_ms) as avg_ms,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms) as p50_ms,
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY response_time_ms) as p90_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms) as p95_ms,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY response_time_ms) as p99_ms,
                MAX(response_time_ms) as max_ms,
                MIN(response_time_ms) as min_ms
            FROM system_performance_metrics
            WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
        """

        return await self._execute_query(query, (start_date, end_date), fetch_one=True)

    async def get_throughput_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get throughput metrics"""
        query = """
            WITH hourly_counts AS (
                SELECT
                    DATE_TRUNC('hour', metric_timestamp) as hour,
                    COUNT(*) as count
                FROM system_performance_metrics
                WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
                GROUP BY DATE_TRUNC('hour', metric_timestamp)
            )
            SELECT
                (SELECT COUNT(*) FROM system_performance_metrics
                 WHERE metric_timestamp >= $1 AND metric_timestamp <= $2) as total_requests,
                (SELECT MAX(count)::FLOAT / 3600 FROM hourly_counts) as peak_rps
        """

        return await self._execute_query(query, (start_date, end_date), fetch_one=True)

    async def get_error_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get error metrics"""
        query = """
            SELECT
                COUNT(*) FILTER (WHERE is_error = TRUE) as total_errors,
                CASE
                    WHEN COUNT(*) > 0
                    THEN COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / COUNT(*)
                    ELSE 0.0
                END as error_rate
            FROM system_performance_metrics
            WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
        """

        result = await self._execute_query(query, (start_date, end_date), fetch_one=True)

        # Get error breakdown by type
        type_query = """
            SELECT error_type, COUNT(*) as count
            FROM system_performance_metrics
            WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
            AND is_error = TRUE AND error_type IS NOT NULL
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
        """

        type_rows = await self._execute_query(type_query, (start_date, end_date))
        result["error_by_type"] = {row["error_type"]: row["count"] for row in type_rows}

        # Get error breakdown by endpoint
        endpoint_query = """
            SELECT endpoint, COUNT(*) as count
            FROM system_performance_metrics
            WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
            AND is_error = TRUE
            GROUP BY endpoint
            ORDER BY count DESC
            LIMIT 10
        """

        endpoint_rows = await self._execute_query(endpoint_query, (start_date, end_date))
        result["error_by_endpoint"] = {row["endpoint"]: row["count"] for row in endpoint_rows}

        return result

    async def get_component_health(self) -> List[Dict[str, Any]]:
        """Get component health status"""
        # This would typically check various system components
        # For now, return basic health based on recent performance
        query = """
            SELECT
                endpoint as component_name,
                CASE
                    WHEN COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / NULLIF(COUNT(*), 0) > 0.1 THEN 'degraded'
                    WHEN COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / NULLIF(COUNT(*), 0) > 0.3 THEN 'unhealthy'
                    ELSE 'healthy'
                END as status,
                AVG(response_time_ms) as latency_ms,
                COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / NULLIF(COUNT(*), 0) as error_rate,
                MAX(metric_timestamp) as last_check_at
            FROM system_performance_metrics
            WHERE metric_timestamp >= NOW() - INTERVAL '1 hour'
            GROUP BY endpoint
            ORDER BY error_rate DESC NULLS LAST
            LIMIT 20
        """

        return await self._execute_query(query, ())

    async def get_performance_trends(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get performance trends over time"""
        query = """
            SELECT
                DATE_TRUNC('hour', metric_timestamp) as timestamp,
                AVG(response_time_ms) as avg_latency_ms,
                COUNT(*) * 60.0 / EXTRACT(EPOCH FROM (MAX(metric_timestamp) - MIN(metric_timestamp) + INTERVAL '1 second'))
                    as requests_per_minute,
                CASE
                    WHEN COUNT(*) > 0
                    THEN COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / COUNT(*)
                    ELSE 0.0
                END as error_rate,
                COUNT(DISTINCT user_id) as active_users
            FROM system_performance_metrics
            WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
            GROUP BY DATE_TRUNC('hour', metric_timestamp)
            ORDER BY timestamp
        """

        return await self._execute_query(query, (start_date, end_date))

    async def insert_performance_metric(self, data: Dict[str, Any]) -> None:
        """Insert performance metric record"""
        query = """
            INSERT INTO system_performance_metrics (
                endpoint, method, status_code, response_time_ms,
                is_error, error_type, error_message,
                user_id, request_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """

        params = (
            data.get("endpoint"),
            data.get("method"),
            data.get("status_code"),
            data.get("response_time_ms"),
            data.get("is_error", False),
            data.get("error_type"),
            data.get("error_message"),
            data.get("user_id"),
            data.get("request_id")
        )

        await self._execute_query(query, params)

    # ============================================
    # Dashboard Summary
    # ============================================

    async def get_dashboard_summary(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get dashboard summary data"""
        # Try query_analytics first
        query = """
            SELECT
                COUNT(*) as total_queries,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(response_time_ms) as avg_response_time_ms,
                AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL) as avg_quality_score,
                CASE
                    WHEN COUNT(*) FILTER (WHERE feedback_type IS NOT NULL) > 0
                    THEN COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::FLOAT /
                         COUNT(*) FILTER (WHERE feedback_type IS NOT NULL)
                    ELSE NULL
                END as satisfaction_rate
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
        """

        result = await self._execute_query(query, (start_date, end_date), fetch_one=True)

        # If query_analytics is empty, fallback to query_log
        if result.get("total_queries", 0) == 0:
            fallback_query = """
                SELECT
                    COUNT(*) as total_queries,
                    COUNT(DISTINCT user_id) as unique_users,
                    AVG(execution_time_ms) as avg_response_time_ms,
                    NULL as avg_quality_score,
                    CASE
                        WHEN COUNT(*) > 0
                        THEN COUNT(*) FILTER (WHERE success = TRUE)::FLOAT / COUNT(*)
                        ELSE NULL
                    END as satisfaction_rate
                FROM query_log
                WHERE created_at >= $1 AND created_at <= $2
            """
            result = await self._execute_query(fallback_query, (start_date, end_date), fetch_one=True)

        # Get error rate from performance metrics or query_log
        error_query = """
            SELECT
                CASE
                    WHEN COUNT(*) > 0
                    THEN COUNT(*) FILTER (WHERE is_error = TRUE)::FLOAT / COUNT(*)
                    ELSE 0.0
                END as error_rate
            FROM system_performance_metrics
            WHERE metric_timestamp >= $1 AND metric_timestamp <= $2
        """

        error_result = await self._execute_query(error_query, (start_date, end_date), fetch_one=True)

        # If no performance metrics, calculate from query_log
        if error_result.get("error_rate", 0.0) == 0:
            fallback_error_query = """
                SELECT
                    CASE
                        WHEN COUNT(*) > 0
                        THEN COUNT(*) FILTER (WHERE success = FALSE)::FLOAT / COUNT(*)
                        ELSE 0.0
                    END as error_rate
                FROM query_log
                WHERE created_at >= $1 AND created_at <= $2
            """
            error_result = await self._execute_query(fallback_error_query, (start_date, end_date), fetch_one=True)

        result["error_rate"] = error_result.get("error_rate", 0.0)

        # Get recent quality scores
        scores_query = """
            SELECT overall_quality_score
            FROM query_analytics
            WHERE created_at >= $1 AND created_at <= $2
            AND overall_quality_score IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 10
        """

        scores = await self._execute_query(scores_query, (start_date, end_date))
        result["recent_quality_scores"] = [s["overall_quality_score"] for s in scores]

        return result

    # ============================================
    # Aggregation Functions
    # ============================================

    async def aggregate_hourly_analytics(self) -> None:
        """Call the aggregation function for hourly stats"""
        query = "SELECT aggregate_hourly_analytics()"
        await self._execute_query(query, ())

    async def aggregate_daily_analytics(self) -> None:
        """Aggregate daily analytics"""
        yesterday = (datetime.utcnow() - timedelta(days=1)).date()

        query = """
            INSERT INTO analytics_daily_aggregates (
                date_timestamp,
                total_queries, unique_queries, unique_users,
                avg_response_time_ms, p50_response_time_ms, p90_response_time_ms,
                avg_faithfulness, avg_context_relevance, avg_answer_relevancy, avg_overall_quality,
                evaluations_count,
                quality_excellent_count, quality_good_count, quality_fair_count, quality_poor_count,
                thumbs_up_count, thumbs_down_count, satisfaction_rate,
                unanswered_count, unanswered_rate,
                total_conversations
            )
            SELECT
                $1::DATE,
                COUNT(*),
                COUNT(DISTINCT query_hash),
                COUNT(DISTINCT user_id),
                AVG(response_time_ms),
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms),
                PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY response_time_ms),
                AVG(faithfulness_score) FILTER (WHERE faithfulness_score IS NOT NULL),
                AVG(context_relevance_score) FILTER (WHERE context_relevance_score IS NOT NULL),
                AVG(answer_relevancy_score) FILTER (WHERE answer_relevancy_score IS NOT NULL),
                AVG(overall_quality_score) FILTER (WHERE overall_quality_score IS NOT NULL),
                COUNT(*) FILTER (WHERE overall_quality_score IS NOT NULL),
                COUNT(*) FILTER (WHERE overall_quality_score >= 0.8),
                COUNT(*) FILTER (WHERE overall_quality_score >= 0.6 AND overall_quality_score < 0.8),
                COUNT(*) FILTER (WHERE overall_quality_score >= 0.4 AND overall_quality_score < 0.6),
                COUNT(*) FILTER (WHERE overall_quality_score < 0.4),
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up'),
                COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down'),
                CASE
                    WHEN COUNT(*) FILTER (WHERE feedback_type IS NOT NULL) > 0
                    THEN COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::FLOAT /
                         COUNT(*) FILTER (WHERE feedback_type IS NOT NULL)
                    ELSE NULL
                END,
                COUNT(*) FILTER (WHERE was_answered = FALSE),
                CASE
                    WHEN COUNT(*) > 0
                    THEN COUNT(*) FILTER (WHERE was_answered = FALSE)::FLOAT / COUNT(*)
                    ELSE 0.0
                END,
                COUNT(DISTINCT conversation_id)
            FROM query_analytics
            WHERE DATE(created_at) = $1
            ON CONFLICT (date_timestamp) DO UPDATE SET
                total_queries = EXCLUDED.total_queries,
                unique_queries = EXCLUDED.unique_queries,
                unique_users = EXCLUDED.unique_users,
                avg_response_time_ms = EXCLUDED.avg_response_time_ms,
                p50_response_time_ms = EXCLUDED.p50_response_time_ms,
                p90_response_time_ms = EXCLUDED.p90_response_time_ms,
                avg_faithfulness = EXCLUDED.avg_faithfulness,
                avg_context_relevance = EXCLUDED.avg_context_relevance,
                avg_answer_relevancy = EXCLUDED.avg_answer_relevancy,
                avg_overall_quality = EXCLUDED.avg_overall_quality,
                evaluations_count = EXCLUDED.evaluations_count,
                quality_excellent_count = EXCLUDED.quality_excellent_count,
                quality_good_count = EXCLUDED.quality_good_count,
                quality_fair_count = EXCLUDED.quality_fair_count,
                quality_poor_count = EXCLUDED.quality_poor_count,
                thumbs_up_count = EXCLUDED.thumbs_up_count,
                thumbs_down_count = EXCLUDED.thumbs_down_count,
                satisfaction_rate = EXCLUDED.satisfaction_rate,
                unanswered_count = EXCLUDED.unanswered_count,
                unanswered_rate = EXCLUDED.unanswered_rate,
                total_conversations = EXCLUDED.total_conversations
        """

        await self._execute_query(query, (yesterday,))
