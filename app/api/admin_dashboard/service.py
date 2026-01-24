"""
Admin Dashboard Service
Aggregates data from existing services for dashboard presentation
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Optional, Dict, List, Any
from collections import defaultdict
import asyncpg

from .models import (
    ExecutiveDashboardResponse,
    UserMetricsSummary,
    TokenMetricsSummary,
    QueryMetricsSummary,
    SystemHealthSummary,
    TrendDataPoint,
    TokenGovernanceOverview,
    TokenUsageTrend,
    UserTokenUsage,
    EndpointTokenUsage,
    AgentPerformanceOverview,
    AgentPerformanceMetrics,
    AgentPerformanceTrend,
    RAGMetricsOverview,
    RAGStrategyMetrics,
    RAGQualityMetrics,
    SystemHealthResponse,
    ComponentHealth,
    AuditLogEntry,
    AuditLogStats,
    HealthStatus,
    AuditSeverity,
    AuditCategory,
)

logger = logging.getLogger(__name__)


class AdminDashboardService:
    """
    Admin Dashboard Service
    Aggregates data from multiple sources for dashboard presentation
    """

    # Cost estimates per 1K tokens (USD)
    COST_PER_1K_INPUT = 0.002
    COST_PER_1K_OUTPUT = 0.003

    def __init__(
        self,
        db_pool: Optional[asyncpg.Pool] = None,
        auth_service=None,
        health_service=None,
        audit_service=None,
        metrics_registry=None,
    ):
        self._pool = db_pool
        self._auth_service = auth_service
        self._health_service = health_service
        self._audit_service = audit_service
        self._metrics_registry = metrics_registry
        self._start_time = datetime.now(timezone.utc)
        # Table existence cache (checked once per service lifetime)
        self._table_cache: Dict[str, bool] = {}

    # =========================================================================
    # EXECUTIVE DASHBOARD
    # =========================================================================

    async def get_executive_dashboard(self, days: int = 7) -> ExecutiveDashboardResponse:
        """Get complete executive dashboard data"""
        import time
        total_start = time.perf_counter()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        # Pre-cache table existence to avoid repeated checks
        cache_start = time.perf_counter()
        await self._ensure_table_cache()
        print(f"[PERF] Table cache: {(time.perf_counter() - cache_start)*1000:.1f}ms", flush=True)

        # Gather all data concurrently using asyncio.gather for parallel execution
        gather_start = time.perf_counter()
        (
            users,
            tokens,
            queries,
            system_health,
            user_trend,
            query_trend,
            token_trend
        ) = await asyncio.gather(
            self._timed_call("user_metrics", self._get_user_metrics()),
            self._timed_call("token_metrics", self._get_token_metrics(start_date, end_date)),
            self._timed_call("query_metrics", self._get_query_metrics(start_date, end_date)),
            self._timed_call("system_health", self._get_system_health_summary()),
            self._timed_call("user_trend", self._get_user_trend(days)),
            self._timed_call("query_trend", self._get_query_trend(days)),
            self._timed_call("token_trend", self._get_token_trend(days))
        )
        print(f"[PERF] All gather completed: {(time.perf_counter() - gather_start)*1000:.1f}ms", flush=True)
        print(f"[PERF] Total executive dashboard: {(time.perf_counter() - total_start)*1000:.1f}ms", flush=True)

        return ExecutiveDashboardResponse(
            users=users,
            tokens=tokens,
            queries=queries,
            system_health=system_health,
            user_trend=user_trend,
            query_trend=query_trend,
            token_trend=token_trend,
            generated_at=datetime.now(timezone.utc)
        )

    async def _get_user_metrics(self) -> UserMetricsSummary:
        """Get user statistics"""
        try:
            if self._auth_service:
                stats = await self._auth_service.get_user_stats()
                return UserMetricsSummary(
                    total_users=stats.get("total_users", 0),
                    active_users=stats.get("active_users", 0),
                    new_users_7d=stats.get("new_users_7d", 0),
                    new_users_30d=stats.get("new_users_30d", 0),
                    users_by_role=stats.get("users_by_role", {}),
                    users_by_status=stats.get("users_by_status", {})
                )
        except Exception as e:
            logger.error(f"Error getting user metrics: {e}")

        # Fallback to direct DB query
        if self._pool:
            try:
                async with self._pool.acquire() as conn:
                    # Total and active users
                    row = await conn.fetchrow("""
                        SELECT
                            COUNT(*) as total,
                            COUNT(*) FILTER (WHERE status = 'active') as active,
                            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as new_7d,
                            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') as new_30d
                        FROM users
                    """)

                    # Users by role
                    role_rows = await conn.fetch("""
                        SELECT role, COUNT(*) as count
                        FROM users
                        GROUP BY role
                    """)

                    # Users by status
                    status_rows = await conn.fetch("""
                        SELECT status, COUNT(*) as count
                        FROM users
                        GROUP BY status
                    """)

                    return UserMetricsSummary(
                        total_users=row["total"] or 0,
                        active_users=row["active"] or 0,
                        new_users_7d=row["new_7d"] or 0,
                        new_users_30d=row["new_30d"] or 0,
                        users_by_role={r["role"]: r["count"] for r in role_rows},
                        users_by_status={s["status"]: s["count"] for s in status_rows}
                    )
            except Exception as e:
                logger.error(f"Error querying user metrics from DB: {e}")

        return UserMetricsSummary(
            total_users=0, active_users=0, new_users_7d=0, new_users_30d=0
        )

    async def _get_token_metrics(
        self, start_date: datetime, end_date: datetime
    ) -> TokenMetricsSummary:
        """Get token usage statistics"""
        if not self._pool:
            return TokenMetricsSummary()

        try:
            async with self._pool.acquire() as conn:
                # Check if token_usage_log table exists and has data
                use_token_usage_log = False
                if self._table_exists('token_usage_log'):
                    # Check if table has any data
                    count = await conn.fetchval("SELECT COUNT(*) FROM token_usage_log LIMIT 1")
                    use_token_usage_log = count > 0

                if not use_token_usage_log:
                    # Use query_log as fallback
                    return await self._get_token_metrics_from_query_log(conn, start_date, end_date)

                # Query token_usage_log
                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                week_ago = end_date - timedelta(days=7)
                month_ago = end_date - timedelta(days=30)

                row = await conn.fetchrow("""
                    SELECT
                        COALESCE(SUM(total_tokens) FILTER (WHERE timestamp >= $1), 0) as today,
                        COALESCE(SUM(total_tokens) FILTER (WHERE timestamp >= $2), 0) as week,
                        COALESCE(SUM(total_tokens), 0) as month,
                        COALESCE(AVG(total_tokens), 0) as avg_per_request,
                        COALESCE(SUM(estimated_cost) FILTER (WHERE timestamp >= $1), 0) as cost_today,
                        COALESCE(SUM(estimated_cost), 0) as cost_month
                    FROM token_usage_log
                    WHERE timestamp >= $3
                """, today_start, week_ago, month_ago)

                # Top endpoints
                top_endpoints = await conn.fetch("""
                    SELECT endpoint, SUM(total_tokens) as tokens, COUNT(*) as requests
                    FROM token_usage_log
                    WHERE timestamp >= $1
                    GROUP BY endpoint
                    ORDER BY tokens DESC
                    LIMIT 5
                """, start_date)

                return TokenMetricsSummary(
                    total_tokens_today=int(row["today"] or 0),
                    total_tokens_7d=int(row["week"] or 0),
                    total_tokens_30d=int(row["month"] or 0),
                    avg_tokens_per_request=float(row["avg_per_request"] or 0),
                    estimated_cost_today=float(row["cost_today"] or 0),
                    estimated_cost_30d=float(row["cost_month"] or 0),
                    top_endpoints=[
                        {"endpoint": e["endpoint"], "tokens": e["tokens"], "requests": e["requests"]}
                        for e in top_endpoints
                    ]
                )
        except Exception as e:
            logger.error(f"Error getting token metrics: {e}")
            return TokenMetricsSummary()

    async def _get_token_metrics_from_query_log(
        self, conn, start_date: datetime, end_date: datetime
    ) -> TokenMetricsSummary:
        """Fallback: get token metrics from query_log table"""
        try:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            week_ago = end_date - timedelta(days=7)
            month_ago = end_date - timedelta(days=30)

            row = await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(input_tokens + output_tokens) FILTER (WHERE created_at >= $1), 0) as today,
                    COALESCE(SUM(input_tokens + output_tokens) FILTER (WHERE created_at >= $2), 0) as week,
                    COALESCE(SUM(input_tokens + output_tokens), 0) as month,
                    COALESCE(AVG(input_tokens + output_tokens), 0) as avg_per_request
                FROM query_log
                WHERE created_at >= $3
            """, today_start, week_ago, month_ago)

            total_today = int(row["today"] or 0)
            total_month = int(row["month"] or 0)

            # Top endpoints by agent_type (fallback from query_log)
            top_endpoints = await conn.fetch("""
                SELECT
                    COALESCE(agent_type, 'general') as endpoint,
                    SUM(input_tokens + output_tokens) as tokens,
                    COUNT(*) as requests
                FROM query_log
                WHERE created_at >= $1
                GROUP BY agent_type
                ORDER BY tokens DESC
                LIMIT 5
            """, start_date)

            return TokenMetricsSummary(
                total_tokens_today=total_today,
                total_tokens_7d=int(row["week"] or 0),
                total_tokens_30d=total_month,
                avg_tokens_per_request=float(row["avg_per_request"] or 0),
                estimated_cost_today=self._estimate_cost(total_today),
                estimated_cost_30d=self._estimate_cost(total_month),
                top_endpoints=[
                    {"endpoint": e["endpoint"], "tokens": int(e["tokens"] or 0), "requests": int(e["requests"] or 0)}
                    for e in top_endpoints
                ]
            )
        except Exception as e:
            logger.error(f"Error getting token metrics from query_log: {e}")
            return TokenMetricsSummary()

    async def _get_query_metrics(
        self, start_date: datetime, end_date: datetime
    ) -> QueryMetricsSummary:
        """Get query execution statistics"""
        if not self._pool:
            return QueryMetricsSummary()

        try:
            async with self._pool.acquire() as conn:
                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

                row = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE created_at >= $1) as today,
                        COUNT(*) FILTER (WHERE created_at >= $2) as week,
                        AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate,
                        AVG(execution_time_ms) as avg_latency,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms) as p95
                    FROM query_log
                    WHERE created_at >= $3
                """, today_start, end_date - timedelta(days=7), start_date)

                # Queries by strategy (if column exists)
                by_strategy = {}
                try:
                    strategy_rows = await conn.fetch("""
                        SELECT strategy, COUNT(*) as count
                        FROM query_log
                        WHERE created_at >= $1 AND strategy IS NOT NULL
                        GROUP BY strategy
                    """, start_date)
                    by_strategy = {r["strategy"]: r["count"] for r in strategy_rows}
                except Exception:
                    pass

                # Queries by agent
                by_agent = {}
                try:
                    agent_rows = await conn.fetch("""
                        SELECT agent_type, COUNT(*) as count
                        FROM query_log
                        WHERE created_at >= $1 AND agent_type IS NOT NULL
                        GROUP BY agent_type
                    """, start_date)
                    by_agent = {r["agent_type"]: r["count"] for r in agent_rows}
                except Exception:
                    pass

                return QueryMetricsSummary(
                    total_queries_today=int(row["today"] or 0),
                    total_queries_7d=int(row["week"] or 0),
                    success_rate=float(row["success_rate"] or 0),
                    avg_latency_ms=int(row["avg_latency"] or 0),
                    p95_latency_ms=int(row["p95"] or 0),
                    queries_by_strategy=by_strategy,
                    queries_by_agent=by_agent
                )
        except Exception as e:
            logger.error(f"Error getting query metrics: {e}")
            return QueryMetricsSummary()

    async def _get_system_health_summary(self) -> SystemHealthSummary:
        """Get system health summary"""
        try:
            if self._health_service:
                health_data = await self._health_service.check_all()
                status_map = {
                    "healthy": HealthStatus.HEALTHY,
                    "degraded": HealthStatus.DEGRADED,
                    "unhealthy": HealthStatus.UNHEALTHY
                }
                return SystemHealthSummary(
                    status=status_map.get(health_data.get("status", "healthy"), HealthStatus.HEALTHY),
                    components=health_data.get("services", {}),
                    active_alerts=[],
                    last_updated=datetime.now(timezone.utc),
                    uptime_seconds=int((datetime.now(timezone.utc) - self._start_time).total_seconds())
                )
        except Exception as e:
            logger.error(f"Error getting health status: {e}")

        return SystemHealthSummary(
            status=HealthStatus.HEALTHY,
            uptime_seconds=int((datetime.now(timezone.utc) - self._start_time).total_seconds())
        )

    async def _get_user_trend(self, days: int) -> List[TrendDataPoint]:
        """Get user registration trend"""
        if not self._pool:
            return []

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DATE(created_at) as date, COUNT(*) as count
                    FROM users
                    WHERE created_at >= NOW() - $1 * INTERVAL '1 day'
                    GROUP BY DATE(created_at)
                    ORDER BY date
                """, days)

                return [
                    TrendDataPoint(
                        timestamp=datetime.combine(r["date"], datetime.min.time()),
                        value=r["count"],
                        label="New Users"
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Error getting user trend: {e}")
            return []

    async def _get_query_trend(self, days: int) -> List[TrendDataPoint]:
        """Get query volume trend"""
        if not self._pool:
            return []

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT DATE(created_at) as date, COUNT(*) as count
                    FROM query_log
                    WHERE created_at >= NOW() - $1 * INTERVAL '1 day'
                    GROUP BY DATE(created_at)
                    ORDER BY date
                """, days)

                return [
                    TrendDataPoint(
                        timestamp=datetime.combine(r["date"], datetime.min.time()),
                        value=r["count"],
                        label="Queries"
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Error getting query trend: {e}")
            return []

    async def _get_token_trend(self, days: int) -> List[TrendDataPoint]:
        """Get token usage trend"""
        if not self._pool:
            return []

        try:
            async with self._pool.acquire() as conn:
                # Check if token_usage_log exists and has data
                use_token_usage_log = False
                if self._table_exists('token_usage_log'):
                    count = await conn.fetchval("SELECT COUNT(*) FROM token_usage_log LIMIT 1")
                    use_token_usage_log = count > 0

                if use_token_usage_log:
                    rows = await conn.fetch("""
                        SELECT DATE(timestamp) as date, SUM(total_tokens) as total
                        FROM token_usage_log
                        WHERE timestamp >= NOW() - $1 * INTERVAL '1 day'
                        GROUP BY DATE(timestamp)
                        ORDER BY date
                    """, days)
                else:
                    # Fallback to query_log
                    rows = await conn.fetch("""
                        SELECT DATE(created_at) as date,
                               SUM(input_tokens + output_tokens) as total
                        FROM query_log
                        WHERE created_at >= NOW() - $1 * INTERVAL '1 day'
                        GROUP BY DATE(created_at)
                        ORDER BY date
                    """, days)

                return [
                    TrendDataPoint(
                        timestamp=datetime.combine(r["date"], datetime.min.time()),
                        value=float(r["total"] or 0),
                        label="Tokens"
                    )
                    for r in rows
                ]
        except Exception as e:
            logger.error(f"Error getting token trend: {e}")
            return []

    # =========================================================================
    # TOKEN GOVERNANCE
    # =========================================================================

    async def get_token_governance(self, days: int = 7) -> TokenGovernanceOverview:
        """Get token governance overview"""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        if not self._pool:
            return TokenGovernanceOverview()

        try:
            async with self._pool.acquire() as conn:
                # Check table (using cache)
                if self._table_exists('token_usage_log'):
                    return await self._get_token_governance_from_usage_log(conn, start_date, end_date)
                else:
                    return await self._get_token_governance_from_query_log(conn, start_date, end_date)

        except Exception as e:
            logger.error(f"Error getting token governance: {e}")
            return TokenGovernanceOverview()

    async def _get_token_governance_from_usage_log(
        self, conn, start_date: datetime, end_date: datetime
    ) -> TokenGovernanceOverview:
        """Get token governance from token_usage_log"""
        # Overall totals
        totals = await conn.fetchrow("""
            SELECT
                COALESCE(SUM(total_tokens), 0) as total,
                COUNT(*) as requests,
                COALESCE(AVG(total_tokens), 0) as avg,
                COALESCE(SUM(estimated_cost), 0) as cost
            FROM token_usage_log
            WHERE timestamp BETWEEN $1 AND $2
        """, start_date, end_date)

        # Daily trend
        daily_rows = await conn.fetch("""
            SELECT
                DATE(timestamp) as date,
                SUM(total_tokens) as total,
                SUM(input_tokens) as input,
                SUM(output_tokens) as output,
                COUNT(*) as requests,
                SUM(estimated_cost) as cost
            FROM token_usage_log
            WHERE timestamp BETWEEN $1 AND $2
            GROUP BY DATE(timestamp)
            ORDER BY date
        """, start_date, end_date)

        # Top users
        top_users = await conn.fetch("""
            SELECT
                t.user_id,
                u.email,
                u.display_name,
                SUM(t.total_tokens) as total,
                COUNT(*) as requests,
                AVG(t.total_tokens) as avg,
                SUM(t.estimated_cost) as cost
            FROM token_usage_log t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.timestamp BETWEEN $1 AND $2
            GROUP BY t.user_id, u.email, u.display_name
            ORDER BY total DESC
            LIMIT 10
        """, start_date, end_date)

        # Top endpoints
        top_endpoints = await conn.fetch("""
            SELECT
                endpoint,
                SUM(total_tokens) as total,
                COUNT(*) as requests,
                AVG(total_tokens) as avg,
                AVG(execution_time_ms) as latency
            FROM token_usage_log
            WHERE timestamp BETWEEN $1 AND $2
            GROUP BY endpoint
            ORDER BY total DESC
            LIMIT 10
        """, start_date, end_date)

        # By agent type
        by_agent = await conn.fetch("""
            SELECT agent_type, SUM(total_tokens) as total
            FROM token_usage_log
            WHERE timestamp BETWEEN $1 AND $2 AND agent_type IS NOT NULL
            GROUP BY agent_type
        """, start_date, end_date)

        return TokenGovernanceOverview(
            total_tokens=int(totals["total"] or 0),
            total_requests=int(totals["requests"] or 0),
            avg_tokens_per_request=float(totals["avg"] or 0),
            total_cost=float(totals["cost"] or 0),
            daily_trend=[
                TokenUsageTrend(
                    date=r["date"],
                    total_tokens=int(r["total"] or 0),
                    input_tokens=int(r["input"] or 0),
                    output_tokens=int(r["output"] or 0),
                    request_count=int(r["requests"] or 0),
                    estimated_cost=float(r["cost"] or 0)
                )
                for r in daily_rows
            ],
            top_users=[
                UserTokenUsage(
                    user_id=str(u["user_id"]),
                    email=u["email"] or "Unknown",
                    display_name=u["display_name"],
                    total_tokens=int(u["total"] or 0),
                    request_count=int(u["requests"] or 0),
                    avg_tokens_per_request=float(u["avg"] or 0),
                    total_cost=float(u["cost"] or 0)
                )
                for u in top_users
            ],
            top_endpoints=[
                EndpointTokenUsage(
                    endpoint=e["endpoint"],
                    total_tokens=int(e["total"] or 0),
                    request_count=int(e["requests"] or 0),
                    avg_tokens=float(e["avg"] or 0),
                    avg_latency_ms=int(e["latency"] or 0)
                )
                for e in top_endpoints
            ],
            by_agent_type={a["agent_type"]: int(a["total"]) for a in by_agent}
        )

    async def _get_token_governance_from_query_log(
        self, conn, start_date: datetime, end_date: datetime
    ) -> TokenGovernanceOverview:
        """Fallback: Get token governance from query_log"""
        # Overall totals
        totals = await conn.fetchrow("""
            SELECT
                COALESCE(SUM(input_tokens + output_tokens), 0) as total,
                COUNT(*) as requests,
                COALESCE(AVG(input_tokens + output_tokens), 0) as avg
            FROM query_log
            WHERE created_at BETWEEN $1 AND $2
        """, start_date, end_date)

        total_tokens = int(totals["total"] or 0)

        # Daily trend
        daily_rows = await conn.fetch("""
            SELECT
                DATE(created_at) as date,
                SUM(input_tokens + output_tokens) as total,
                SUM(input_tokens) as input,
                SUM(output_tokens) as output,
                COUNT(*) as requests
            FROM query_log
            WHERE created_at BETWEEN $1 AND $2
            GROUP BY DATE(created_at)
            ORDER BY date
        """, start_date, end_date)

        return TokenGovernanceOverview(
            total_tokens=total_tokens,
            total_requests=int(totals["requests"] or 0),
            avg_tokens_per_request=float(totals["avg"] or 0),
            total_cost=self._estimate_cost(total_tokens),
            daily_trend=[
                TokenUsageTrend(
                    date=r["date"],
                    total_tokens=int(r["total"] or 0),
                    input_tokens=int(r["input"] or 0),
                    output_tokens=int(r["output"] or 0),
                    request_count=int(r["requests"] or 0),
                    estimated_cost=self._estimate_cost(int(r["total"] or 0))
                )
                for r in daily_rows
            ]
        )

    # =========================================================================
    # AGENT PERFORMANCE
    # =========================================================================

    async def get_agent_performance(self, days: int = 7) -> AgentPerformanceOverview:
        """Get agent performance overview"""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        if not self._pool:
            return AgentPerformanceOverview()

        try:
            async with self._pool.acquire() as conn:
                # Check if agent_execution_traces exists (using cache)
                if not self._table_exists('agent_execution_traces'):
                    # Use query_log as fallback
                    return await self._get_agent_performance_from_query_log(conn, start_date, end_date)

                # Get per-agent metrics
                agent_rows = await conn.fetch("""
                    SELECT
                        agent_type,
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status = 'COMPLETED') as success,
                        COUNT(*) FILTER (WHERE status = 'FAILED') as failed,
                        AVG(total_latency_ms) as avg_latency,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_latency_ms) as p95,
                        SUM(retry_count) as retries
                    FROM agent_execution_traces
                    WHERE created_at BETWEEN $1 AND $2
                    GROUP BY agent_type
                """, start_date, end_date)

                agents = []
                total_executions = 0
                total_success = 0

                for r in agent_rows:
                    total = int(r["total"] or 0)
                    success = int(r["success"] or 0)
                    total_executions += total
                    total_success += success

                    agents.append(AgentPerformanceMetrics(
                        agent_type=r["agent_type"],
                        total_executions=total,
                        successful_executions=success,
                        failed_executions=int(r["failed"] or 0),
                        success_rate=success / total if total > 0 else 0.0,
                        avg_execution_time_ms=int(r["avg_latency"] or 0),
                        p95_execution_time_ms=int(r["p95"] or 0),
                        total_retries=int(r["retries"] or 0)
                    ))

                # Trend data
                trend_rows = await conn.fetch("""
                    SELECT
                        DATE(created_at) as date,
                        agent_type,
                        COUNT(*) as executions,
                        AVG(CASE WHEN status = 'COMPLETED' THEN 1.0 ELSE 0.0 END) as success_rate,
                        AVG(total_latency_ms) as avg_latency
                    FROM agent_execution_traces
                    WHERE created_at BETWEEN $1 AND $2
                    GROUP BY DATE(created_at), agent_type
                    ORDER BY date
                """, start_date, end_date)

                trend = [
                    AgentPerformanceTrend(
                        date=r["date"],
                        agent_type=r["agent_type"],
                        executions=int(r["executions"] or 0),
                        success_rate=float(r["success_rate"] or 0),
                        avg_latency_ms=int(r["avg_latency"] or 0)
                    )
                    for r in trend_rows
                ]

                return AgentPerformanceOverview(
                    total_executions_today=total_executions,
                    overall_success_rate=total_success / total_executions if total_executions > 0 else 0.0,
                    agents=agents,
                    trend=trend
                )

        except Exception as e:
            logger.error(f"Error getting agent performance: {e}")
            return AgentPerformanceOverview()

    async def _get_agent_performance_from_query_log(
        self, conn, start_date: datetime, end_date: datetime
    ) -> AgentPerformanceOverview:
        """Fallback: Get agent performance from query_log"""
        try:
            agent_rows = await conn.fetch("""
                SELECT
                    COALESCE(agent_type, 'unknown') as agent_type,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE success = true) as success,
                    COUNT(*) FILTER (WHERE success = false) as failed,
                    AVG(execution_time_ms) as avg_latency,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms) as p95
                FROM query_log
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY agent_type
            """, start_date, end_date)

            agents = []
            total_executions = 0
            total_success = 0

            for r in agent_rows:
                total = int(r["total"] or 0)
                success = int(r["success"] or 0)
                total_executions += total
                total_success += success

                agents.append(AgentPerformanceMetrics(
                    agent_type=r["agent_type"],
                    total_executions=total,
                    successful_executions=success,
                    failed_executions=int(r["failed"] or 0),
                    success_rate=success / total if total > 0 else 0.0,
                    avg_execution_time_ms=int(r["avg_latency"] or 0),
                    p95_execution_time_ms=int(r["p95"] or 0)
                ))

            return AgentPerformanceOverview(
                total_executions_today=total_executions,
                overall_success_rate=total_success / total_executions if total_executions > 0 else 0.0,
                agents=agents
            )
        except Exception as e:
            logger.error(f"Error getting agent performance from query_log: {e}")
            return AgentPerformanceOverview()

    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================

    async def get_health_monitoring(self) -> SystemHealthResponse:
        """Get detailed health monitoring data"""
        components = []

        # Get health from health service if available
        if self._health_service:
            try:
                health_data = await self._health_service.check_all()
                services = health_data.get("services", {})

                for name, data in services.items():
                    status_str = data.get("status", "healthy")
                    status = HealthStatus.HEALTHY
                    if status_str == "degraded":
                        status = HealthStatus.DEGRADED
                    elif status_str == "unhealthy":
                        status = HealthStatus.UNHEALTHY

                    components.append(ComponentHealth(
                        name=name,
                        status=status,
                        latency_ms=data.get("response_time_ms"),
                        message=data.get("error"),
                        metadata=data
                    ))

                overall = health_data.get("status", "healthy")
                overall_status = HealthStatus.HEALTHY
                if overall == "degraded":
                    overall_status = HealthStatus.DEGRADED
                elif overall == "unhealthy":
                    overall_status = HealthStatus.UNHEALTHY

                return SystemHealthResponse(
                    overall_status=overall_status,
                    components=components,
                    uptime_seconds=int((datetime.now(timezone.utc) - self._start_time).total_seconds())
                )
            except Exception as e:
                logger.error(f"Error getting health data: {e}")

        return SystemHealthResponse(
            overall_status=HealthStatus.HEALTHY,
            components=components,
            uptime_seconds=int((datetime.now(timezone.utc) - self._start_time).total_seconds())
        )

    # =========================================================================
    # RAG METRICS
    # =========================================================================

    async def get_rag_metrics(self, days: int = 7) -> RAGMetricsOverview:
        """Get RAG performance metrics"""
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        if not self._pool:
            return RAGMetricsOverview()

        try:
            async with self._pool.acquire() as conn:
                # Check for rag_performance_daily table (using cache)
                if self._table_exists('rag_performance_daily'):
                    return await self._get_rag_metrics_from_daily(conn, start_date, end_date)
                else:
                    return await self._get_rag_metrics_from_query_log(conn, start_date, end_date)

        except Exception as e:
            logger.error(f"Error getting RAG metrics: {e}")
            return RAGMetricsOverview()

    async def _get_rag_metrics_from_daily(
        self, conn, start_date: datetime, end_date: datetime
    ) -> RAGMetricsOverview:
        """Get RAG metrics from daily aggregates"""
        rows = await conn.fetch("""
            SELECT
                strategy,
                SUM(total_queries) as queries,
                AVG(avg_retrieval_time_ms) as retrieval,
                AVG(avg_generation_time_ms) as generation,
                AVG(avg_result_count) as results,
                AVG(avg_similarity_score) as similarity,
                AVG(avg_confidence_score) as confidence,
                SUM(thumbs_up_count) as thumbs_up,
                SUM(thumbs_down_count) as thumbs_down
            FROM rag_performance_daily
            WHERE metric_date BETWEEN $1 AND $2
            GROUP BY strategy
        """, start_date.date(), end_date.date())

        strategies = []
        total_queries = 0

        for r in rows:
            queries = int(r["queries"] or 0)
            total_queries += queries
            strategies.append(RAGStrategyMetrics(
                strategy=r["strategy"],
                total_queries=queries,
                avg_retrieval_time_ms=int(r["retrieval"] or 0),
                avg_generation_time_ms=int(r["generation"] or 0),
                avg_result_count=float(r["results"] or 0),
                avg_similarity_score=float(r["similarity"] or 0),
                avg_confidence_score=float(r["confidence"] or 0)
            ))

        return RAGMetricsOverview(
            total_queries=total_queries,
            strategies=strategies
        )

    async def _get_rag_metrics_from_query_log(
        self, conn, start_date: datetime, end_date: datetime
    ) -> RAGMetricsOverview:
        """Fallback: Get RAG metrics from query_log"""
        try:
            rows = await conn.fetch("""
                SELECT
                    COALESCE(strategy, 'hybrid') as strategy,
                    COUNT(*) as queries,
                    AVG(execution_time_ms) as avg_time,
                    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate
                FROM query_log
                WHERE created_at BETWEEN $1 AND $2
                GROUP BY strategy
            """, start_date, end_date)

            strategies = []
            total_queries = 0

            for r in rows:
                queries = int(r["queries"] or 0)
                total_queries += queries
                strategies.append(RAGStrategyMetrics(
                    strategy=r["strategy"],
                    total_queries=queries,
                    success_rate=float(r["success_rate"] or 0),
                    avg_retrieval_time_ms=int(r["avg_time"] or 0) // 2,  # Estimate
                    avg_generation_time_ms=int(r["avg_time"] or 0) // 2
                ))

            return RAGMetricsOverview(
                total_queries=total_queries,
                strategies=strategies
            )
        except Exception as e:
            logger.error(f"Error getting RAG metrics from query_log: {e}")
            return RAGMetricsOverview()

    # =========================================================================
    # AUDIT LOGS
    # =========================================================================

    async def get_audit_logs(
        self,
        page: int = 1,
        limit: int = 50,
        user_id: Optional[str] = None,
        action_category: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get paginated audit logs"""
        # Try database first
        if self._pool:
            try:
                return await self._get_audit_logs_from_db(
                    page, limit, user_id, action_category, severity, start_date, end_date
                )
            except Exception as e:
                logger.error(f"Error getting audit logs from DB: {e}")

        # Fallback to in-memory audit service
        if self._audit_service:
            try:
                from ..services.audit_service import AuditSearchCriteria
                criteria = AuditSearchCriteria(
                    user_id=user_id,
                    limit=limit,
                    offset=(page - 1) * limit
                )
                events = self._audit_service.search(criteria)
                return {
                    "entries": [e.to_dict() for e in events],
                    "total": len(events),
                    "page": page,
                    "limit": limit,
                    "has_more": len(events) == limit
                }
            except Exception as e:
                logger.error(f"Error getting audit logs from service: {e}")

        return {"entries": [], "total": 0, "page": page, "limit": limit, "has_more": False}

    async def _get_audit_logs_from_db(
        self,
        page: int,
        limit: int,
        user_id: Optional[str],
        action_category: Optional[str],
        severity: Optional[str],
        start_date: Optional[datetime],
        end_date: Optional[datetime]
    ) -> Dict[str, Any]:
        """Get audit logs from database"""
        # Check if table exists (using cache)
        if not self._table_exists('admin_audit_logs'):
            return {"entries": [], "total": 0, "page": page, "limit": limit, "has_more": False}

        async with self._pool.acquire() as conn:

            # Build query
            conditions = []
            params = []
            param_idx = 1

            if user_id:
                conditions.append(f"user_id = ${param_idx}")
                params.append(user_id)
                param_idx += 1

            if action_category:
                conditions.append(f"action_category = ${param_idx}")
                params.append(action_category)
                param_idx += 1

            if severity:
                conditions.append(f"severity = ${param_idx}")
                params.append(severity)
                param_idx += 1

            if start_date:
                conditions.append(f"timestamp >= ${param_idx}")
                params.append(start_date)
                param_idx += 1

            if end_date:
                conditions.append(f"timestamp <= ${param_idx}")
                params.append(end_date)
                param_idx += 1

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # Count total
            count_query = f"SELECT COUNT(*) FROM admin_audit_logs WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get entries
            offset = (page - 1) * limit
            query = f"""
                SELECT * FROM admin_audit_logs
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)

            entries = [
                {
                    "id": str(r["id"]),
                    "timestamp": r["timestamp"].isoformat(),
                    "user_id": str(r["user_id"]),
                    "user_email": r["user_email"],
                    "user_role": r["user_role"],
                    "action": r["action"],
                    "action_category": r["action_category"],
                    "severity": r["severity"],
                    "resource_type": r["resource_type"],
                    "resource_id": r["resource_id"],
                    "success": r["success"],
                    "error_message": r["error_message"]
                }
                for r in rows
            ]

            return {
                "entries": entries,
                "total": total,
                "page": page,
                "limit": limit,
                "has_more": offset + len(entries) < total
            }

    async def get_audit_stats(self, hours: int = 24) -> AuditLogStats:
        """Get audit log statistics"""
        if self._audit_service:
            try:
                stats = self._audit_service.get_stats(hours)
                return AuditLogStats(
                    total_events=stats.total_events,
                    events_by_category=stats.events_by_type,
                    events_by_severity=stats.events_by_severity,
                    events_by_user=[
                        {"user_id": k, "count": v}
                        for k, v in stats.events_by_user.items()
                    ],
                    recent_security_events=[
                        AuditLogEntry(
                            id=e.id,
                            timestamp=e.timestamp,
                            user_id=e.user_id or "",
                            user_email=e.user_email or "",
                            user_role="",
                            action=e.action,
                            action_category=AuditCategory.SECURITY,
                            severity=AuditSeverity(e.severity.value),
                            resource_type=e.resource_type or "",
                            success=True
                        )
                        for e in stats.recent_security_events[:10]
                    ]
                )
            except Exception as e:
                logger.error(f"Error getting audit stats: {e}")

        return AuditLogStats(
            total_events=0,
            events_by_category={},
            events_by_severity={},
            events_by_user=[],
            recent_security_events=[]
        )

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _ensure_table_cache(self) -> None:
        """Pre-cache table existence checks to avoid repeated queries"""
        if self._table_cache:
            return  # Already cached

        if not self._pool:
            return

        tables_to_check = [
            'token_usage_log',
            'agent_execution_traces',
            'rag_performance_daily',
            'admin_audit_logs'
        ]

        try:
            async with self._pool.acquire() as conn:
                for table in tables_to_check:
                    exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = $1
                        )
                    """, table)
                    self._table_cache[table] = exists
        except Exception as e:
            logger.error(f"Error caching table existence: {e}")

    def _table_exists(self, table_name: str) -> bool:
        """Check if table exists using cache"""
        return self._table_cache.get(table_name, False)

    async def _timed_call(self, name: str, coro):
        """Wrapper to time async calls"""
        import time
        start = time.perf_counter()
        result = await coro
        elapsed = (time.perf_counter() - start) * 1000
        print(f"[PERF] {name}: {elapsed:.1f}ms", flush=True)
        return result

    def _estimate_cost(self, total_tokens: int) -> float:
        """Estimate cost based on token count (assumes 50/50 input/output split)"""
        input_tokens = total_tokens // 2
        output_tokens = total_tokens - input_tokens
        return round(
            (input_tokens / 1000 * self.COST_PER_1K_INPUT) +
            (output_tokens / 1000 * self.COST_PER_1K_OUTPUT),
            4
        )


# Singleton instance
_dashboard_service: Optional[AdminDashboardService] = None


def get_admin_dashboard_service() -> AdminDashboardService:
    """Get or create dashboard service singleton"""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = AdminDashboardService()
    return _dashboard_service


def init_admin_dashboard_service(
    db_pool: Optional[asyncpg.Pool] = None,
    auth_service=None,
    health_service=None,
    audit_service=None,
    metrics_registry=None
) -> AdminDashboardService:
    """Initialize dashboard service with dependencies"""
    global _dashboard_service
    _dashboard_service = AdminDashboardService(
        db_pool=db_pool,
        auth_service=auth_service,
        health_service=health_service,
        audit_service=audit_service,
        metrics_registry=metrics_registry
    )
    return _dashboard_service
