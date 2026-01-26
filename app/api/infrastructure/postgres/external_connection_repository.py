"""
PostgreSQL External Connection Repository

Stores external resource connections (OAuth tokens, sync status, etc.)
for Notion, GitHub, Google Drive, OneNote, and Confluence integrations.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg
from asyncpg import Pool

logger = logging.getLogger(__name__)


def _json_serializer(obj):
    """JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class PostgresExternalConnectionRepository:
    """
    PostgreSQL repository for external connections.

    Handles persistence of:
    - OAuth/API tokens (encrypted)
    - Connection status and sync state
    - Resource-specific configuration
    """

    def __init__(self, pool: Pool):
        """
        Initialize with asyncpg connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self):
        """Ensure the external_connections table exists."""
        if self._initialized:
            return

        # Table should be created by migration, but verify it exists
        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'external_connections'
                )
            """)

            if not result:
                logger.warning("external_connections table does not exist - run migration 020")
                # Create table as fallback
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS external_connections (
                        id VARCHAR(50) PRIMARY KEY,
                        user_id UUID NOT NULL,
                        resource_type VARCHAR(50) NOT NULL,
                        status VARCHAR(50) DEFAULT 'not_connected',
                        auth_type VARCHAR(20) DEFAULT 'oauth2',
                        access_token TEXT,
                        refresh_token TEXT,
                        api_token TEXT,
                        token_expires_at TIMESTAMP WITH TIME ZONE,
                        sync_status VARCHAR(50) DEFAULT 'pending',
                        sync_error TEXT,
                        last_sync_at TIMESTAMP WITH TIME ZONE,
                        next_sync_at TIMESTAMP WITH TIME ZONE,
                        document_count INTEGER DEFAULT 0,
                        chunk_count INTEGER DEFAULT 0,
                        resource_config JSONB DEFAULT '{}',
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ext_conn_user_id
                    ON external_connections(user_id)
                """)
                await conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_ext_conn_user_resource
                    ON external_connections(user_id, resource_type)
                """)

            self._initialized = True
            logger.info("External connection repository initialized")

    async def create(
        self,
        id: str,
        user_id: str,
        resource_type: str,
        auth_type: str = "oauth2",
        status: str = "not_connected",
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        api_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        resource_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new external connection.

        Args:
            id: Connection ID
            user_id: User UUID (string)
            resource_type: Type of external resource
            auth_type: Authentication type
            status: Connection status
            access_token: Encrypted access token
            refresh_token: Encrypted refresh token
            api_token: Encrypted API token
            token_expires_at: Token expiration time
            resource_config: Resource-specific configuration

        Returns:
            Connection ID
        """
        await self._ensure_table()

        config_json = json.dumps(resource_config or {}, default=_json_serializer)

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO external_connections
                (id, user_id, resource_type, auth_type, status,
                 access_token, refresh_token, api_token, token_expires_at,
                 resource_config, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, NOW(), NOW())
            """, id, user_id, resource_type, auth_type, status,
                access_token, refresh_token, api_token, token_expires_at, config_json)

        logger.info(f"Created external connection: {id}")
        return id

    async def get(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a connection by ID.

        Args:
            connection_id: Connection ID

        Returns:
            Connection data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM external_connections WHERE id = $1",
                connection_id
            )

            if row:
                return self._row_to_dict(row)
            return None

    async def get_by_user(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all connections for a user.

        Args:
            user_id: User UUID (string)

        Returns:
            List of connection data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM external_connections
                   WHERE user_id = $1::uuid
                   ORDER BY created_at DESC""",
                user_id
            )

            return [self._row_to_dict(row) for row in rows]

    async def get_by_user_and_type(
        self,
        user_id: str,
        resource_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get connection by user and resource type.

        Args:
            user_id: User UUID (string)
            resource_type: Type of external resource

        Returns:
            Connection data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT * FROM external_connections
                   WHERE user_id = $1::uuid AND resource_type = $2""",
                user_id, resource_type
            )

            if row:
                return self._row_to_dict(row)
            return None

    async def update(
        self,
        connection_id: str,
        **kwargs
    ) -> bool:
        """
        Update a connection.

        Args:
            connection_id: Connection ID
            **kwargs: Fields to update

        Returns:
            True if updated
        """
        await self._ensure_table()

        if not kwargs:
            return False

        # Build dynamic UPDATE query
        updates = []
        params = [connection_id]
        param_idx = 2

        allowed_fields = {
            "status", "access_token", "refresh_token", "api_token",
            "token_expires_at", "sync_status", "sync_error",
            "last_sync_at", "next_sync_at", "document_count",
            "chunk_count", "resource_config"
        }

        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue

            if key == "resource_config" and isinstance(value, dict):
                updates.append(f"resource_config = ${param_idx}::jsonb")
                params.append(json.dumps(value, default=_json_serializer))
            else:
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
            param_idx += 1

        if not updates:
            return False

        updates.append("updated_at = NOW()")
        query = f"UPDATE external_connections SET {', '.join(updates)} WHERE id = $1"

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def update_tokens(
        self,
        connection_id: str,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        status: Optional[str] = None,
        resource_config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update OAuth tokens for a connection.

        Args:
            connection_id: Connection ID
            access_token: Encrypted access token
            refresh_token: Encrypted refresh token
            token_expires_at: Token expiration time
            status: New connection status
            resource_config: Updated resource config

        Returns:
            True if updated
        """
        await self._ensure_table()

        updates = ["updated_at = NOW()"]
        params = [connection_id]
        param_idx = 2

        if access_token is not None:
            updates.append(f"access_token = ${param_idx}")
            params.append(access_token)
            param_idx += 1

        if refresh_token is not None:
            updates.append(f"refresh_token = ${param_idx}")
            params.append(refresh_token)
            param_idx += 1

        if token_expires_at is not None:
            updates.append(f"token_expires_at = ${param_idx}")
            params.append(token_expires_at)
            param_idx += 1

        if status is not None:
            updates.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if resource_config is not None:
            updates.append(f"resource_config = ${param_idx}::jsonb")
            params.append(json.dumps(resource_config, default=_json_serializer))
            param_idx += 1

        query = f"UPDATE external_connections SET {', '.join(updates)} WHERE id = $1"

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def update_sync_status(
        self,
        connection_id: str,
        sync_status: str,
        sync_error: Optional[str] = None,
        last_sync_at: Optional[datetime] = None,
        document_count: Optional[int] = None,
        chunk_count: Optional[int] = None
    ) -> bool:
        """
        Update sync status for a connection.

        Args:
            connection_id: Connection ID
            sync_status: New sync status
            sync_error: Error message (if any)
            last_sync_at: Last sync timestamp
            document_count: Number of synced documents
            chunk_count: Number of chunks

        Returns:
            True if updated
        """
        await self._ensure_table()

        updates = ["sync_status = $2", "sync_error = $3", "updated_at = NOW()"]
        params = [connection_id, sync_status, sync_error]
        param_idx = 4

        if last_sync_at is not None:
            updates.append(f"last_sync_at = ${param_idx}")
            params.append(last_sync_at)
            param_idx += 1

        if document_count is not None:
            updates.append(f"document_count = ${param_idx}")
            params.append(document_count)
            param_idx += 1

        if chunk_count is not None:
            updates.append(f"chunk_count = ${param_idx}")
            params.append(chunk_count)
            param_idx += 1

        query = f"UPDATE external_connections SET {', '.join(updates)} WHERE id = $1"

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def delete(self, connection_id: str) -> bool:
        """
        Delete a connection.

        Args:
            connection_id: Connection ID

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM external_connections WHERE id = $1",
                connection_id
            )
            return "DELETE 1" in result

    async def get_all_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all connections as a dictionary (for cache loading).

        Returns:
            Dictionary of connection_id -> connection data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM external_connections")

            return {
                row['id']: self._row_to_dict(row)
                for row in rows
            }

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row["id"],
            "user_id": str(row["user_id"]),
            "resource_type": row["resource_type"],
            "status": row["status"],
            "auth_type": row["auth_type"],
            "access_token": row["access_token"],
            "refresh_token": row["refresh_token"],
            "api_token": row["api_token"],
            "token_expires_at": row["token_expires_at"],
            "sync_status": row["sync_status"],
            "sync_error": row["sync_error"],
            "last_sync_at": row["last_sync_at"],
            "next_sync_at": row["next_sync_at"],
            "document_count": row["document_count"],
            "chunk_count": row["chunk_count"],
            "resource_config": row["resource_config"] or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        }


# Singleton instance
_connection_repository: Optional[PostgresExternalConnectionRepository] = None


async def get_external_connection_repository(
    pool: Optional[Pool] = None
) -> PostgresExternalConnectionRepository:
    """
    Get or create external connection repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresExternalConnectionRepository instance
    """
    global _connection_repository

    if _connection_repository is None:
        if pool is None:
            import asyncpg
            from ...core.config import api_settings

            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"
            pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)

        _connection_repository = PostgresExternalConnectionRepository(pool)
        await _connection_repository._ensure_table()
        logger.info("External connection repository initialized")

    return _connection_repository
