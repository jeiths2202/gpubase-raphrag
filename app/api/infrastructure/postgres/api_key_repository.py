"""
PostgreSQL API Key Repository Implementation

Production-ready PostgreSQL implementation for API key management.

Features:
- Async operations using asyncpg
- Secure key hashing with SHA256
- Rate limiting support
- Usage tracking
"""
import logging
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

import asyncpg
from asyncpg import Pool

from ...models.api_key import (
    ApiKeyCreate,
    ApiKeyUpdate,
    ApiKeyResponse,
    ApiKeyCreatedResponse,
    ApiKeyValidationResult,
    ApiKeyUsageStats,
    RateLimitStatus,
)

logger = logging.getLogger(__name__)


class PostgresApiKeyRepository:
    """
    PostgreSQL implementation of API Key Repository.

    SECURITY:
    - SHA256 for key hashing (fast lookups, secure storage)
    - Key shown only once at creation
    - Rate limiting per minute/hour/day
    - Usage logging for analytics
    """

    # API key prefix for identification
    KEY_PREFIX = "kms_"

    def __init__(self, pool: Pool):
        """
        Initialize PostgreSQL API key repository.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

    @staticmethod
    def _generate_api_key() -> Tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            Tuple of (full_key, key_prefix, key_hash)
        """
        # Generate 32 random bytes -> 64 hex chars
        random_part = secrets.token_hex(32)
        full_key = f"kms_{random_part}"
        key_prefix = full_key[:8]  # First 8 chars for display (e.g., "kms_abc1")
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        return full_key, key_prefix, key_hash

    @staticmethod
    def _hash_key(api_key: str) -> str:
        """Hash an API key for comparison."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create(
        self,
        data: ApiKeyCreate,
        owner_id: Optional[UUID] = None
    ) -> ApiKeyCreatedResponse:
        """
        Create a new API key.

        Args:
            data: API key creation data
            owner_id: Optional owner user ID

        Returns:
            Created API key with the full key (shown only once)
        """
        full_key, key_prefix, key_hash = self._generate_api_key()

        # Calculate expiration if specified
        expires_at = None
        if data.expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

        query = """
            INSERT INTO api_keys (
                name, description, key_prefix, key_hash, owner_id,
                allowed_endpoints, allowed_agent_types,
                rate_limit_per_minute, rate_limit_per_hour, rate_limit_per_day,
                expires_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, name
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                data.name,
                data.description,
                key_prefix,
                key_hash,
                owner_id,
                data.allowed_endpoints,
                data.allowed_agent_types,
                data.rate_limit_per_minute,
                data.rate_limit_per_hour,
                data.rate_limit_per_day,
                expires_at
            )

        logger.info(f"Created API key: {key_prefix}... for {data.name}")

        return ApiKeyCreatedResponse(
            id=row["id"],
            name=row["name"],
            key=full_key,
            key_prefix=key_prefix
        )

    async def validate(self, api_key: str) -> ApiKeyValidationResult:
        """
        Validate an API key and return its permissions.

        Args:
            api_key: The full API key to validate

        Returns:
            Validation result with permissions or error
        """
        if not api_key or not api_key.startswith(self.KEY_PREFIX):
            return ApiKeyValidationResult(
                is_valid=False,
                error="Invalid API key format"
            )

        key_hash = self._hash_key(api_key)

        query = """
            SELECT id, owner_id, allowed_endpoints, allowed_agent_types,
                   rate_limit_per_minute, rate_limit_per_hour, rate_limit_per_day,
                   is_active, expires_at
            FROM api_keys
            WHERE key_hash = $1
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, key_hash)

        if not row:
            return ApiKeyValidationResult(
                is_valid=False,
                error="API key not found"
            )

        if not row["is_active"]:
            return ApiKeyValidationResult(
                is_valid=False,
                error="API key is disabled"
            )

        if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
            return ApiKeyValidationResult(
                is_valid=False,
                error="API key has expired"
            )

        return ApiKeyValidationResult(
            is_valid=True,
            api_key_id=row["id"],
            owner_id=row["owner_id"],
            allowed_endpoints=row["allowed_endpoints"] or [],
            allowed_agent_types=row["allowed_agent_types"] or [],
            rate_limit_per_minute=row["rate_limit_per_minute"],
            rate_limit_per_hour=row["rate_limit_per_hour"],
            rate_limit_per_day=row["rate_limit_per_day"]
        )

    async def check_rate_limit(
        self,
        api_key_id: UUID
    ) -> Tuple[bool, Optional[RateLimitStatus]]:
        """
        Check if API key is within rate limits.

        Args:
            api_key_id: API key ID to check

        Returns:
            Tuple of (is_allowed, rate_limit_status)
        """
        now = datetime.now(timezone.utc)
        minute_start = now.replace(second=0, microsecond=0)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        query = """
            WITH limits AS (
                SELECT rate_limit_per_minute, rate_limit_per_hour, rate_limit_per_day
                FROM api_keys WHERE id = $1
            ),
            counts AS (
                SELECT
                    COALESCE(SUM(CASE WHEN window_type = 'minute' AND window_start = $2 THEN request_count END), 0) as minute_count,
                    COALESCE(SUM(CASE WHEN window_type = 'hour' AND window_start = $3 THEN request_count END), 0) as hour_count,
                    COALESCE(SUM(CASE WHEN window_type = 'day' AND window_start = $4 THEN request_count END), 0) as day_count
                FROM api_key_rate_limits
                WHERE api_key_id = $1
            )
            SELECT limits.*, counts.*
            FROM limits, counts
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, api_key_id, minute_start, hour_start, day_start)

        if not row:
            return True, None

        minute_remaining = max(0, row["rate_limit_per_minute"] - row["minute_count"])
        hour_remaining = max(0, row["rate_limit_per_hour"] - row["hour_count"])
        day_remaining = max(0, row["rate_limit_per_day"] - row["day_count"])

        is_allowed = minute_remaining > 0 and hour_remaining > 0 and day_remaining > 0

        status = RateLimitStatus(
            minute_remaining=minute_remaining,
            minute_reset_at=minute_start + timedelta(minutes=1),
            hour_remaining=hour_remaining,
            hour_reset_at=hour_start + timedelta(hours=1),
            day_remaining=day_remaining,
            day_reset_at=day_start + timedelta(days=1)
        )

        return is_allowed, status

    async def increment_rate_limit(self, api_key_id: UUID) -> None:
        """
        Increment rate limit counters for an API key.

        Args:
            api_key_id: API key ID
        """
        now = datetime.now(timezone.utc)
        minute_start = now.replace(second=0, microsecond=0)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        query = """
            INSERT INTO api_key_rate_limits (api_key_id, window_type, window_start, request_count)
            VALUES ($1, $2, $3, 1)
            ON CONFLICT (api_key_id, window_type, window_start)
            DO UPDATE SET request_count = api_key_rate_limits.request_count + 1
        """

        async with self._pool.acquire() as conn:
            await conn.execute(query, api_key_id, "minute", minute_start)
            await conn.execute(query, api_key_id, "hour", hour_start)
            await conn.execute(query, api_key_id, "day", day_start)

    async def record_usage(
        self,
        api_key_id: UUID,
        endpoint: str,
        method: str,
        agent_type: Optional[str] = None,
        tokens_used: int = 0,
        response_time_ms: int = 0,
        status_code: int = 200,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Record API key usage for analytics.

        Args:
            api_key_id: API key ID
            endpoint: Endpoint accessed
            method: HTTP method
            agent_type: Agent type used
            tokens_used: Tokens consumed
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code
            client_ip: Client IP address
            user_agent: Client user agent
            error_message: Error message if any
        """
        query = """
            INSERT INTO api_key_usage_log (
                api_key_id, endpoint, method, agent_type,
                tokens_used, response_time_ms, status_code,
                client_ip, user_agent, error_message
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """

        update_query = """
            UPDATE api_keys
            SET total_requests = total_requests + 1,
                total_tokens_used = total_tokens_used + $2,
                last_used_at = NOW()
            WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                api_key_id, endpoint, method, agent_type,
                tokens_used, response_time_ms, status_code,
                client_ip, user_agent, error_message
            )
            await conn.execute(update_query, api_key_id, tokens_used)

    async def get_by_id(self, api_key_id: UUID) -> Optional[ApiKeyResponse]:
        """Get API key by ID."""
        query = """
            SELECT * FROM api_keys WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, api_key_id)

        if not row:
            return None

        return self._row_to_response(row)

    async def list_by_owner(
        self,
        owner_id: UUID,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False
    ) -> Tuple[List[ApiKeyResponse], int]:
        """
        List API keys owned by a user.

        Args:
            owner_id: Owner user ID
            page: Page number (1-based)
            page_size: Items per page
            include_inactive: Include inactive keys

        Returns:
            Tuple of (keys list, total count)
        """
        offset = (page - 1) * page_size

        where_clause = "WHERE owner_id = $1"
        if not include_inactive:
            where_clause += " AND is_active = TRUE"

        count_query = f"SELECT COUNT(*) FROM api_keys {where_clause}"
        list_query = f"""
            SELECT * FROM api_keys
            {where_clause}
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query, owner_id)
            rows = await conn.fetch(list_query, owner_id, page_size, offset)

        return [self._row_to_response(row) for row in rows], total

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False
    ) -> Tuple[List[ApiKeyResponse], int]:
        """
        List all API keys (admin only).

        Args:
            page: Page number (1-based)
            page_size: Items per page
            include_inactive: Include inactive keys

        Returns:
            Tuple of (keys list, total count)
        """
        offset = (page - 1) * page_size

        where_clause = "WHERE is_active = TRUE" if not include_inactive else ""

        count_query = f"SELECT COUNT(*) FROM api_keys {where_clause}"
        list_query = f"""
            SELECT * FROM api_keys
            {where_clause}
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query)
            rows = await conn.fetch(list_query, page_size, offset)

        return [self._row_to_response(row) for row in rows], total

    async def update(
        self,
        api_key_id: UUID,
        data: ApiKeyUpdate
    ) -> Optional[ApiKeyResponse]:
        """Update an API key."""
        updates = []
        values = []
        param_num = 1

        if data.name is not None:
            updates.append(f"name = ${param_num}")
            values.append(data.name)
            param_num += 1

        if data.description is not None:
            updates.append(f"description = ${param_num}")
            values.append(data.description)
            param_num += 1

        if data.allowed_endpoints is not None:
            updates.append(f"allowed_endpoints = ${param_num}")
            values.append(data.allowed_endpoints)
            param_num += 1

        if data.allowed_agent_types is not None:
            updates.append(f"allowed_agent_types = ${param_num}")
            values.append(data.allowed_agent_types)
            param_num += 1

        if data.rate_limit_per_minute is not None:
            updates.append(f"rate_limit_per_minute = ${param_num}")
            values.append(data.rate_limit_per_minute)
            param_num += 1

        if data.rate_limit_per_hour is not None:
            updates.append(f"rate_limit_per_hour = ${param_num}")
            values.append(data.rate_limit_per_hour)
            param_num += 1

        if data.rate_limit_per_day is not None:
            updates.append(f"rate_limit_per_day = ${param_num}")
            values.append(data.rate_limit_per_day)
            param_num += 1

        if data.is_active is not None:
            updates.append(f"is_active = ${param_num}")
            values.append(data.is_active)
            param_num += 1

        if not updates:
            return await self.get_by_id(api_key_id)

        values.append(api_key_id)
        query = f"""
            UPDATE api_keys
            SET {', '.join(updates)}
            WHERE id = ${param_num}
            RETURNING *
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)

        if not row:
            return None

        return self._row_to_response(row)

    async def delete(self, api_key_id: UUID) -> bool:
        """Delete an API key (soft delete by setting is_active=False)."""
        query = """
            UPDATE api_keys
            SET is_active = FALSE
            WHERE id = $1
            RETURNING id
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, api_key_id)

        return row is not None

    async def hard_delete(self, api_key_id: UUID) -> bool:
        """Permanently delete an API key and its usage logs."""
        query = "DELETE FROM api_keys WHERE id = $1 RETURNING id"

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, api_key_id)

        return row is not None

    async def cleanup_old_rate_limits(self, older_than_hours: int = 24) -> int:
        """
        Clean up old rate limit entries.

        Args:
            older_than_hours: Delete entries older than this

        Returns:
            Number of deleted entries
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)

        query = """
            DELETE FROM api_key_rate_limits
            WHERE window_start < $1
        """

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, cutoff)

        # Parse "DELETE X" result
        count = int(result.split()[-1]) if result else 0
        return count

    @staticmethod
    def _row_to_response(row: asyncpg.Record) -> ApiKeyResponse:
        """Convert database row to response model."""
        return ApiKeyResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            key_prefix=row["key_prefix"],
            owner_id=row["owner_id"],
            allowed_endpoints=row["allowed_endpoints"] or [],
            allowed_agent_types=row["allowed_agent_types"] or [],
            rate_limit_per_minute=row["rate_limit_per_minute"],
            rate_limit_per_hour=row["rate_limit_per_hour"],
            rate_limit_per_day=row["rate_limit_per_day"],
            total_requests=row["total_requests"],
            total_tokens_used=row["total_tokens_used"],
            last_used_at=row["last_used_at"],
            is_active=row["is_active"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
