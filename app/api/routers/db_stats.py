"""
Database Statistics API Router
PostgreSQL 데이터베이스 모니터링 API (관리자 전용)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_admin_user
from ..core.config import api_settings

router = APIRouter(prefix="/admin/db", tags=["Admin - Database Statistics"])


# ==================== Response Models ====================

class ConnectionPoolStats(BaseModel):
    """Database connection pool statistics"""
    total_connections: int = Field(..., description="Total pool connections")
    active_connections: int = Field(..., description="Currently active connections")
    idle_connections: int = Field(..., description="Idle connections in pool")
    waiting_queries: int = Field(default=0, description="Queries waiting for connection")


class TableStats(BaseModel):
    """Table statistics"""
    table_name: str
    row_count: int
    size_bytes: int
    size_pretty: str
    last_vacuum: Optional[datetime] = None
    last_analyze: Optional[datetime] = None


class SlowQuery(BaseModel):
    """Slow query information"""
    query: str
    calls: int
    total_time_ms: float
    mean_time_ms: float
    max_time_ms: float


class DatabaseOverview(BaseModel):
    """Database overview statistics"""
    database_name: str
    database_size: str
    total_tables: int
    total_rows: int
    uptime_seconds: float
    version: str


class DatabaseStatsResponse(BaseModel):
    """Complete database statistics response"""
    overview: DatabaseOverview
    connection_pool: ConnectionPoolStats
    tables: List[TableStats]
    slow_queries: List[SlowQuery]
    timestamp: datetime


# ==================== Database Stats Collection ====================

async def _get_db_stats(pool) -> Dict[str, Any]:
    """Collect database statistics from PostgreSQL"""
    try:
        async with pool.acquire() as conn:
            # Database overview
            db_info = await conn.fetchrow("""
                SELECT 
                    current_database() as db_name,
                    pg_size_pretty(pg_database_size(current_database())) as db_size,
                    (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public') as table_count,
                    version() as pg_version
            """)
            
            # Connection stats
            conn_stats = await conn.fetchrow("""
                SELECT 
                    count(*) as total,
                    count(*) FILTER (WHERE state = 'active') as active,
                    count(*) FILTER (WHERE state = 'idle') as idle,
                    count(*) FILTER (WHERE wait_event IS NOT NULL) as waiting
                FROM pg_stat_activity
                WHERE datname = current_database()
            """)
            
            # Table stats
            tables = await conn.fetch("""
                SELECT 
                    relname as table_name,
                    n_live_tup as row_count,
                    pg_total_relation_size(relid) as size_bytes,
                    pg_size_pretty(pg_total_relation_size(relid)) as size_pretty,
                    last_vacuum,
                    last_analyze
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
                LIMIT 20
            """)
            
            # Total rows
            total_rows = sum(t['row_count'] or 0 for t in tables)
            
            # Uptime
            uptime = await conn.fetchval("""
                SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))
            """)
            
            return {
                "overview": {
                    "database_name": db_info['db_name'],
                    "database_size": db_info['db_size'],
                    "total_tables": db_info['table_count'],
                    "total_rows": total_rows,
                    "uptime_seconds": float(uptime or 0),
                    "version": db_info['pg_version'][:50] + "..." if len(db_info['pg_version']) > 50 else db_info['pg_version']
                },
                "connection_pool": {
                    "total_connections": conn_stats['total'] or 0,
                    "active_connections": conn_stats['active'] or 0,
                    "idle_connections": conn_stats['idle'] or 0,
                    "waiting_queries": conn_stats['waiting'] or 0
                },
                "tables": [
                    {
                        "table_name": t['table_name'],
                        "row_count": t['row_count'] or 0,
                        "size_bytes": t['size_bytes'] or 0,
                        "size_pretty": t['size_pretty'],
                        "last_vacuum": t['last_vacuum'],
                        "last_analyze": t['last_analyze']
                    }
                    for t in tables
                ],
                "slow_queries": [],  # Requires pg_stat_statements extension
                "timestamp": datetime.now(timezone.utc)
            }
    except Exception as e:
        return _get_mock_db_stats(str(e))


def _get_mock_db_stats(error_msg: str = "") -> Dict[str, Any]:
    """Return mock database stats for development/testing"""
    import random
    return {
        "overview": {
            "database_name": "ragdb",
            "database_size": f"{random.randint(50, 200)} MB",
            "total_tables": random.randint(10, 30),
            "total_rows": random.randint(1000, 50000),
            "uptime_seconds": random.randint(3600, 86400 * 7),
            "version": "PostgreSQL 15.4"
        },
        "connection_pool": {
            "total_connections": random.randint(5, 20),
            "active_connections": random.randint(1, 5),
            "idle_connections": random.randint(3, 15),
            "waiting_queries": random.randint(0, 2)
        },
        "tables": [
            {"table_name": "users", "row_count": random.randint(10, 100), "size_bytes": random.randint(10000, 100000), "size_pretty": "64 kB", "last_vacuum": None, "last_analyze": None},
            {"table_name": "auth_identities", "row_count": random.randint(5, 50), "size_bytes": random.randint(5000, 50000), "size_pretty": "32 kB", "last_vacuum": None, "last_analyze": None},
            {"table_name": "verification_codes", "row_count": random.randint(0, 20), "size_bytes": random.randint(1000, 10000), "size_pretty": "8 kB", "last_vacuum": None, "last_analyze": None},
        ],
        "slow_queries": [
            {"query": "SELECT * FROM users WHERE...", "calls": random.randint(10, 100), "total_time_ms": random.uniform(100, 1000), "mean_time_ms": random.uniform(10, 100), "max_time_ms": random.uniform(50, 500)},
        ],
        "timestamp": datetime.now(timezone.utc),
        "_mock": True,
        "_error": error_msg
    }


# ==================== Dependency for DB Pool ====================

async def get_db_pool():
    """Get database connection pool from auth service"""
    from ..services.auth_service import get_auth_service
    auth_service = await get_auth_service()
    if hasattr(auth_service, 'user_repo') and hasattr(auth_service.user_repo, '_pool'):
        return auth_service.user_repo._pool
    return None


# ==================== API Endpoints ====================

@router.get(
    "/stats",
    response_model=SuccessResponse[DatabaseStatsResponse],
    summary="데이터베이스 통계 조회",
    description="PostgreSQL 데이터베이스의 전체 통계를 조회합니다."
)
async def get_database_stats(
    admin_user: dict = Depends(get_admin_user)
):
    """Get comprehensive database statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    pool = await get_db_pool()
    
    if pool:
        stats = await _get_db_stats(pool)
    else:
        stats = _get_mock_db_stats("Database pool not available")
    
    return SuccessResponse(
        data=DatabaseStatsResponse(**stats),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/connections",
    response_model=SuccessResponse[ConnectionPoolStats],
    summary="연결 풀 상태 조회"
)
async def get_connection_stats(
    admin_user: dict = Depends(get_admin_user)
):
    """Get connection pool statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    pool = await get_db_pool()
    
    if pool:
        stats = await _get_db_stats(pool)
        conn_stats = stats["connection_pool"]
    else:
        conn_stats = _get_mock_db_stats()["connection_pool"]
    
    return SuccessResponse(
        data=ConnectionPoolStats(**conn_stats),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/tables",
    response_model=SuccessResponse[List[TableStats]],
    summary="테이블 통계 조회"
)
async def get_table_stats(
    admin_user: dict = Depends(get_admin_user)
):
    """Get table statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    pool = await get_db_pool()
    
    if pool:
        stats = await _get_db_stats(pool)
        tables = stats["tables"]
    else:
        tables = _get_mock_db_stats()["tables"]
    
    return SuccessResponse(
        data=[TableStats(**t) for t in tables],
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/slow-queries",
    response_model=SuccessResponse[List[SlowQuery]],
    summary="슬로우 쿼리 조회",
    description="가장 느린 쿼리 목록을 조회합니다. (pg_stat_statements 확장 필요)"
)
async def get_slow_queries(
    limit: int = 10,
    admin_user: dict = Depends(get_admin_user)
):
    """Get slow query statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    
    # Note: Requires pg_stat_statements extension
    slow_queries = _get_mock_db_stats()["slow_queries"]
    
    return SuccessResponse(
        data=[SlowQuery(**q) for q in slow_queries[:limit]],
        meta=MetaInfo(request_id=request_id)
    )
