"""
Admin API Router
관리자 전용 API - 사용자 관리, 대시보드 통계, 토큰 통계, 유저별 리소스 사용량
"""
import uuid
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, EmailStr
import asyncpg

from ..models.base import SuccessResponse, MetaInfo
from ..core.deps import get_current_user, get_admin_user, get_auth_service, get_token_stats_service
from ..core.config import api_settings

router = APIRouter(prefix="/admin", tags=["Admin"])


# Request/Response Models
class UserListResponse(BaseModel):
    """User list response"""
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: Optional[str] = None


class UserUpdateRequest(BaseModel):
    """User update request"""
    role: Optional[str] = Field(None, pattern=r'^(admin|user)$')
    is_active: Optional[bool] = None
    email: Optional[EmailStr] = None


class UserStatsResponse(BaseModel):
    """User statistics response"""
    total_users: int
    active_users: int
    inactive_users: int
    admin_users: int
    regular_users: int
    pending_verification: int


class DashboardStats(BaseModel):
    """Dashboard statistics"""
    users: UserStatsResponse
    system: dict


# ============= User Usage Models =============

class UserUsageResponse(BaseModel):
    """User usage summary response"""
    user_id: str
    total_queries: int
    total_tokens: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    last_activity: Optional[datetime] = None


class UserUsageTrendItem(BaseModel):
    """Daily usage trend item"""
    date: str
    queries: int
    tokens: int
    cost: float


class UserAgentUsage(BaseModel):
    """Agent usage breakdown"""
    agent_type: str
    query_count: int
    token_count: int
    percentage: float


class PasswordResetResponse(BaseModel):
    """Password reset response"""
    message: str
    temporary_password: Optional[str] = None


class UserFullUpdateRequest(BaseModel):
    """Full user update request for admin"""
    role: Optional[str] = Field(None, pattern=r'^(admin|leader|senior|user|guest)$')
    status: Optional[str] = Field(None, pattern=r'^(active|inactive|pending|suspended)$')
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None


@router.get(
    "/users",
    response_model=SuccessResponse[dict],
    summary="사용자 목록 조회",
    description="모든 사용자 목록을 조회합니다. (관리자 전용)"
)
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """List all users with pagination"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    result = await auth_service.list_users(page=page, limit=limit, search=search)

    return SuccessResponse(
        data=result,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/users/{user_id}",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 상세 조회",
    description="특정 사용자의 상세 정보를 조회합니다. (관리자 전용)"
)
async def get_user(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    user = await auth_service.get_user(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=UserListResponse(**user),
        meta=MetaInfo(request_id=request_id)
    )


@router.patch(
    "/users/{user_id}",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 정보 수정",
    description="사용자의 역할, 활성화 상태 등을 수정합니다. (관리자 전용)"
)
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Update user details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Build update dict
    updates = {}
    if request.role is not None:
        updates["role"] = request.role
    if request.is_active is not None:
        updates["is_active"] = request.is_active
    if request.email is not None:
        updates["email"] = request.email

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_UPDATES", "message": "수정할 내용이 없습니다."}
        )

    user = await auth_service.update_user(user_id, updates)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    return SuccessResponse(
        data=UserListResponse(**user),
        meta=MetaInfo(request_id=request_id)
    )


@router.delete(
    "/users/{user_id}",
    response_model=SuccessResponse[dict],
    summary="사용자 삭제",
    description="사용자를 삭제합니다. 기본 관리자 계정은 삭제할 수 없습니다. (관리자 전용)"
)
async def delete_user(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Delete a user"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Prevent self-deletion
    if admin_user["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SELF_DELETE", "message": "자신의 계정은 삭제할 수 없습니다."}
        )

    success = await auth_service.delete_user(user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "DELETE_FAILED", "message": "사용자를 삭제할 수 없습니다. 기본 관리자 계정이거나 존재하지 않는 사용자입니다."}
        )

    return SuccessResponse(
        data={"message": "사용자가 삭제되었습니다.", "deleted_user_id": user_id},
        meta=MetaInfo(request_id=request_id)
    )


@router.post(
    "/users/{user_id}/toggle-active",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 활성화/비활성화",
    description="사용자의 활성화 상태를 토글합니다. (관리자 전용)"
)
async def toggle_user_active(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Toggle user active status"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Get current user
    user = await auth_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    # Toggle active status
    new_status = not user.get("is_active", True)
    updated = await auth_service.update_user(user_id, {"is_active": new_status})

    return SuccessResponse(
        data=UserListResponse(**updated),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/stats",
    response_model=SuccessResponse[UserStatsResponse],
    summary="사용자 통계",
    description="사용자 관련 통계를 조회합니다. (관리자 전용)"
)
async def get_user_stats(
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    stats = await auth_service.get_user_stats()

    return SuccessResponse(
        data=UserStatsResponse(**stats),
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/dashboard",
    response_model=SuccessResponse[dict],
    summary="대시보드 통계",
    description="관리자 대시보드용 통계를 조회합니다. (관리자 전용)"
)
async def get_dashboard_stats(
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get dashboard statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    user_stats = await auth_service.get_user_stats()

    # System info (mock for now)
    system_stats = {
        "uptime": "Running",
        "api_version": "1.0.0",
        "environment": "development"
    }

    return SuccessResponse(
        data={
            "users": user_stats,
            "system": system_stats
        },
        meta=MetaInfo(request_id=request_id)
    )


# ============= Token Statistics Endpoints =============

@router.get(
    "/tokens/overview",
    response_model=SuccessResponse[dict],
    summary="토큰 통계 개요",
    description="토큰 사용에 대한 전반적인 통계를 조회합니다. (관리자 전용)"
)
async def get_token_overview(
    admin_user: dict = Depends(get_admin_user),
    token_stats_service = Depends(get_token_stats_service)
):
    """Get overall token statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    overview = await token_stats_service.get_token_overview()

    return SuccessResponse(
        data=overview,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/tokens/daily",
    response_model=SuccessResponse[list],
    summary="일별 토큰 통계",
    description="최근 N일간의 일별 토큰 발행 통계를 조회합니다. (관리자 전용)"
)
async def get_daily_token_stats(
    days: int = Query(7, ge=1, le=30, description="조회할 일수"),
    admin_user: dict = Depends(get_admin_user),
    token_stats_service = Depends(get_token_stats_service)
):
    """Get daily token statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    daily_stats = await token_stats_service.get_daily_stats(days=days)

    return SuccessResponse(
        data=daily_stats,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/tokens/users",
    response_model=SuccessResponse[list],
    summary="유저별 토큰 통계",
    description="각 사용자별 토큰 사용 통계를 조회합니다. (관리자 전용)"
)
async def get_user_token_stats(
    admin_user: dict = Depends(get_admin_user),
    token_stats_service = Depends(get_token_stats_service)
):
    """Get per-user token statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    user_stats = await token_stats_service.get_user_token_stats()

    return SuccessResponse(
        data=user_stats,
        meta=MetaInfo(request_id=request_id)
    )


@router.get(
    "/tokens/endpoints",
    response_model=SuccessResponse[list],
    summary="엔드포인트별 토큰 통계",
    description="각 API 엔드포인트별 토큰 사용 통계를 조회합니다. (관리자 전용)"
)
async def get_endpoint_token_stats(
    admin_user: dict = Depends(get_admin_user),
    token_stats_service = Depends(get_token_stats_service)
):
    """Get per-endpoint token statistics"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    endpoint_stats = await token_stats_service.get_endpoint_stats()

    return SuccessResponse(
        data=endpoint_stats,
        meta=MetaInfo(request_id=request_id)
    )


# ============= User Resource Usage Endpoints =============

async def _get_db_pool():
    """Get database connection pool"""
    dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    return pool


# Cost estimation: $0.002 per 1K tokens (Nemotron pricing estimate)
TOKEN_COST_PER_1K = 0.002


@router.get(
    "/users/{user_id}/usage",
    response_model=SuccessResponse[UserUsageResponse],
    summary="유저별 리소스 사용량",
    description="특정 사용자의 리소스 사용량 요약을 조회합니다. (관리자 전용)"
)
async def get_user_usage(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user resource usage summary"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Verify user exists
    user = await auth_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    pool = await _get_db_pool()
    try:
        async with pool.acquire() as conn:
            # Get usage summary from query_log
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total_queries,
                    COALESCE(SUM(input_tokens), 0) as input_tokens,
                    COALESCE(SUM(output_tokens), 0) as output_tokens,
                    MAX(created_at) as last_activity
                FROM query_log
                WHERE user_id = $1
            """, user_id)

            total_queries = row['total_queries'] or 0
            input_tokens = row['input_tokens'] or 0
            output_tokens = row['output_tokens'] or 0
            total_tokens = input_tokens + output_tokens
            estimated_cost = (total_tokens / 1000) * TOKEN_COST_PER_1K

            return SuccessResponse(
                data=UserUsageResponse(
                    user_id=user_id,
                    total_queries=total_queries,
                    total_tokens=total_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_cost=round(estimated_cost, 4),
                    last_activity=row['last_activity']
                ),
                meta=MetaInfo(request_id=request_id)
            )
    finally:
        await pool.close()


@router.get(
    "/users/{user_id}/usage/trend",
    response_model=SuccessResponse[List[UserUsageTrendItem]],
    summary="유저별 일별 사용 추이",
    description="특정 사용자의 일별 리소스 사용 추이를 조회합니다. (관리자 전용)"
)
async def get_user_usage_trend(
    user_id: str,
    days: int = Query(7, ge=1, le=30, description="조회할 일수"),
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user daily usage trend"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Verify user exists
    user = await auth_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    pool = await _get_db_pool()
    try:
        async with pool.acquire() as conn:
            start_date = datetime.now(timezone.utc) - timedelta(days=days)

            rows = await conn.fetch("""
                SELECT
                    DATE(created_at) as date,
                    COUNT(*) as queries,
                    COALESCE(SUM(input_tokens + output_tokens), 0) as tokens
                FROM query_log
                WHERE user_id = $1 AND created_at >= $2
                GROUP BY DATE(created_at)
                ORDER BY date
            """, user_id, start_date)

            # Fill in missing dates with zeros
            trend_data = []
            date_map = {row['date']: row for row in rows}

            for i in range(days):
                date = (datetime.now(timezone.utc) - timedelta(days=days-1-i)).date()
                if date in date_map:
                    row = date_map[date]
                    tokens = row['tokens'] or 0
                    trend_data.append(UserUsageTrendItem(
                        date=str(date),
                        queries=row['queries'],
                        tokens=tokens,
                        cost=round((tokens / 1000) * TOKEN_COST_PER_1K, 4)
                    ))
                else:
                    trend_data.append(UserUsageTrendItem(
                        date=str(date),
                        queries=0,
                        tokens=0,
                        cost=0.0
                    ))

            return SuccessResponse(
                data=trend_data,
                meta=MetaInfo(request_id=request_id)
            )
    finally:
        await pool.close()


@router.get(
    "/users/{user_id}/usage/by-agent",
    response_model=SuccessResponse[List[UserAgentUsage]],
    summary="유저별 에이전트 사용량",
    description="특정 사용자의 에이전트별 리소스 사용량을 조회합니다. (관리자 전용)"
)
async def get_user_usage_by_agent(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Get user usage breakdown by agent type"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Verify user exists
    user = await auth_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    pool = await _get_db_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    COALESCE(agent_type, 'unknown') as agent_type,
                    COUNT(*) as query_count,
                    COALESCE(SUM(input_tokens + output_tokens), 0) as token_count
                FROM query_log
                WHERE user_id = $1
                GROUP BY agent_type
                ORDER BY query_count DESC
            """, user_id)

            # Calculate total for percentage
            total_queries = sum(row['query_count'] for row in rows) or 1

            agent_usage = [
                UserAgentUsage(
                    agent_type=row['agent_type'],
                    query_count=row['query_count'],
                    token_count=row['token_count'] or 0,
                    percentage=round((row['query_count'] / total_queries) * 100, 1)
                )
                for row in rows
            ]

            return SuccessResponse(
                data=agent_usage,
                meta=MetaInfo(request_id=request_id)
            )
    finally:
        await pool.close()


@router.post(
    "/users/{user_id}/password-reset",
    response_model=SuccessResponse[PasswordResetResponse],
    summary="비밀번호 초기화",
    description="사용자의 비밀번호를 임시 비밀번호로 초기화합니다. (관리자 전용)"
)
async def reset_user_password(
    user_id: str,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Reset user password to temporary password"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Verify user exists
    user = await auth_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
        )

    # Generate temporary password (12 characters: letters + digits + special chars)
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    temp_password = ''.join(secrets.choice(alphabet) for _ in range(12))

    # Update password in database
    pool = await _get_db_pool()
    try:
        import bcrypt
        password_hash = bcrypt.hashpw(temp_password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET password_hash = $1 WHERE id = $2
            """, password_hash, uuid.UUID(user_id))

        return SuccessResponse(
            data=PasswordResetResponse(
                message="비밀번호가 초기화되었습니다.",
                temporary_password=temp_password
            ),
            meta=MetaInfo(request_id=request_id)
        )
    finally:
        await pool.close()


@router.put(
    "/users/{user_id}",
    response_model=SuccessResponse[UserListResponse],
    summary="사용자 정보 전체 수정",
    description="사용자의 모든 정보를 수정합니다. (관리자 전용)"
)
async def update_user_full(
    user_id: str,
    request: UserFullUpdateRequest,
    admin_user: dict = Depends(get_admin_user),
    auth_service = Depends(get_auth_service)
):
    """Full update user details"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    # Build update dict
    updates = {}
    if request.role is not None:
        updates["role"] = request.role
    if request.status is not None:
        # Map status string to is_active
        updates["is_active"] = request.status == "active"
    if request.email is not None:
        updates["email"] = request.email
    if request.display_name is not None:
        updates["display_name"] = request.display_name
    if request.department is not None:
        updates["department"] = request.department

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_UPDATES", "message": "수정할 내용이 없습니다."}
        )

    # Use direct DB update for full control
    pool = await _get_db_pool()
    try:
        async with pool.acquire() as conn:
            # Build dynamic update query
            set_clauses = []
            values = []
            param_idx = 1

            if request.role is not None:
                set_clauses.append(f"role = ${param_idx}")
                values.append(request.role)
                param_idx += 1

            if request.status is not None:
                set_clauses.append(f"status = ${param_idx}")
                values.append(request.status)
                param_idx += 1

            if request.email is not None:
                set_clauses.append(f"email = ${param_idx}")
                values.append(request.email)
                param_idx += 1

            if request.display_name is not None:
                set_clauses.append(f"display_name = ${param_idx}")
                values.append(request.display_name)
                param_idx += 1

            if request.department is not None:
                set_clauses.append(f"department = ${param_idx}")
                values.append(request.department)
                param_idx += 1

            values.append(uuid.UUID(user_id))

            row = await conn.fetchrow(f"""
                UPDATE users
                SET {', '.join(set_clauses)}
                WHERE id = ${param_idx}
                RETURNING id, email, display_name, role, status, created_at
            """, *values)

            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "USER_NOT_FOUND", "message": "사용자를 찾을 수 없습니다."}
                )

            return SuccessResponse(
                data=UserListResponse(
                    id=str(row['id']),
                    username=row['display_name'],
                    email=row['email'],
                    role=row['role'],
                    is_active=row['status'] == 'active',
                    is_verified=row['status'] != 'pending',
                    created_at=row['created_at'].isoformat() if row['created_at'] else None
                ),
                meta=MetaInfo(request_id=request_id)
            )
    finally:
        await pool.close()


# ============= Data Cleanup Endpoints =============

class OrphanedDataResponse(BaseModel):
    """Orphaned data cleanup response"""
    orphaned_image_embeddings: int
    orphaned_text_chunks: int
    orphaned_document_ids: List[str]


class CleanupResult(BaseModel):
    """Cleanup operation result"""
    deleted_image_embeddings: int
    deleted_text_chunks: int
    cleaned_document_ids: List[str]
    message: str


@router.get(
    "/cleanup/orphaned-data",
    response_model=SuccessResponse[OrphanedDataResponse],
    summary="고아 데이터 확인",
    description="documents 테이블에 없지만 image_embeddings, text_chunks에 남아있는 고아 데이터를 확인합니다."
)
async def check_orphaned_data(
    admin_user: dict = Depends(get_admin_user)
):
    """Check for orphaned data that needs cleanup"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    pool = await _get_db_pool()
    try:
        async with pool.acquire() as conn:
            # Find orphaned image_embeddings (document_id not in documents table)
            orphaned_images = await conn.fetch("""
                SELECT DISTINCT ie.document_id, COUNT(*) as count
                FROM image_embeddings ie
                LEFT JOIN documents d ON ie.document_id = d.id
                WHERE d.id IS NULL
                GROUP BY ie.document_id
            """)

            # Find orphaned text_chunks
            orphaned_chunks = await conn.fetch("""
                SELECT DISTINCT tc.document_id, COUNT(*) as count
                FROM text_chunks tc
                LEFT JOIN documents d ON tc.document_id = d.id
                WHERE d.id IS NULL
                GROUP BY tc.document_id
            """)

            orphaned_doc_ids = list(set(
                [row['document_id'] for row in orphaned_images] +
                [row['document_id'] for row in orphaned_chunks]
            ))

            total_orphaned_images = sum(row['count'] for row in orphaned_images)
            total_orphaned_chunks = sum(row['count'] for row in orphaned_chunks)

            return SuccessResponse(
                data=OrphanedDataResponse(
                    orphaned_image_embeddings=total_orphaned_images,
                    orphaned_text_chunks=total_orphaned_chunks,
                    orphaned_document_ids=orphaned_doc_ids
                ),
                meta=MetaInfo(request_id=request_id)
            )
    finally:
        await pool.close()


@router.delete(
    "/cleanup/orphaned-data",
    response_model=SuccessResponse[CleanupResult],
    summary="고아 데이터 삭제",
    description="documents 테이블에 없는 고아 데이터(image_embeddings, text_chunks)를 삭제합니다."
)
async def cleanup_orphaned_data(
    document_id: Optional[str] = Query(
        default=None,
        description="특정 document_id만 정리 (미지정시 모든 고아 데이터 삭제)"
    ),
    admin_user: dict = Depends(get_admin_user)
):
    """Delete orphaned data from image_embeddings and text_chunks"""
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    pool = await _get_db_pool()
    try:
        async with pool.acquire() as conn:
            deleted_images = 0
            deleted_chunks = 0
            cleaned_doc_ids = []

            if document_id:
                # Clean specific document_id
                # First check if document exists
                doc_exists = await conn.fetchval(
                    "SELECT COUNT(*) FROM documents WHERE id = $1",
                    document_id
                )
                if doc_exists > 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={
                            "code": "DOCUMENT_EXISTS",
                            "message": f"문서 {document_id}가 존재합니다. 일반 삭제를 사용하세요."
                        }
                    )

                # Delete image_embeddings
                result = await conn.execute(
                    "DELETE FROM image_embeddings WHERE document_id = $1",
                    document_id
                )
                deleted_images = int(result.split()[-1]) if result else 0

                # Delete text_chunks
                result = await conn.execute(
                    "DELETE FROM text_chunks WHERE document_id = $1",
                    document_id
                )
                deleted_chunks = int(result.split()[-1]) if result else 0

                if deleted_images > 0 or deleted_chunks > 0:
                    cleaned_doc_ids.append(document_id)
            else:
                # Clean all orphaned data
                # Get orphaned document_ids first
                orphaned_doc_ids = await conn.fetch("""
                    SELECT DISTINCT document_id FROM (
                        SELECT ie.document_id FROM image_embeddings ie
                        LEFT JOIN documents d ON ie.document_id = d.id
                        WHERE d.id IS NULL
                        UNION
                        SELECT tc.document_id FROM text_chunks tc
                        LEFT JOIN documents d ON tc.document_id = d.id
                        WHERE d.id IS NULL
                    ) AS orphans
                """)

                for row in orphaned_doc_ids:
                    doc_id = row['document_id']

                    # Delete image_embeddings
                    result = await conn.execute(
                        "DELETE FROM image_embeddings WHERE document_id = $1",
                        doc_id
                    )
                    deleted_images += int(result.split()[-1]) if result else 0

                    # Delete text_chunks
                    result = await conn.execute(
                        "DELETE FROM text_chunks WHERE document_id = $1",
                        doc_id
                    )
                    deleted_chunks += int(result.split()[-1]) if result else 0

                    cleaned_doc_ids.append(doc_id)

            message = f"정리 완료: {deleted_images}개 이미지 임베딩, {deleted_chunks}개 텍스트 청크 삭제"

            return SuccessResponse(
                data=CleanupResult(
                    deleted_image_embeddings=deleted_images,
                    deleted_text_chunks=deleted_chunks,
                    cleaned_document_ids=cleaned_doc_ids,
                    message=message
                ),
                meta=MetaInfo(request_id=request_id)
            )
    finally:
        await pool.close()
