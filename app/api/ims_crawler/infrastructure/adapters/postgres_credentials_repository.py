"""
PostgreSQL Credentials Repository - Concrete implementation

Stores encrypted user credentials in PostgreSQL.
Uses asyncpg for async database operations.
"""

import asyncpg
from typing import Optional
from uuid import UUID
from datetime import datetime

from ...domain.entities import UserCredentials
from ..ports.credentials_repository_port import CredentialsRepositoryPort


class PostgreSQLCredentialsRepository(CredentialsRepositoryPort):
    """
    PostgreSQL implementation of credentials repository.

    Uses asyncpg connection pool for efficient database access.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize repository with connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self.pool = pool

    async def save(self, credentials: UserCredentials) -> None:
        """
        Save or update user credentials.

        Uses UPSERT (INSERT ... ON CONFLICT UPDATE) for idempotent saves.

        Args:
            credentials: UserCredentials entity to save

        Raises:
            asyncpg.PostgresError: If database operation fails
        """
        query = """
            INSERT INTO ims_user_credentials (
                id, user_id, ims_base_url,
                encrypted_username, encrypted_password,
                is_validated, last_validated_at, validation_error,
                created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (user_id)
            DO UPDATE SET
                ims_base_url = EXCLUDED.ims_base_url,
                encrypted_username = EXCLUDED.encrypted_username,
                encrypted_password = EXCLUDED.encrypted_password,
                is_validated = EXCLUDED.is_validated,
                last_validated_at = EXCLUDED.last_validated_at,
                validation_error = EXCLUDED.validation_error,
                updated_at = EXCLUDED.updated_at
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                credentials.id,
                credentials.user_id,
                credentials.ims_base_url,
                credentials.encrypted_username,
                credentials.encrypted_password,
                credentials.is_validated,
                credentials.last_validated_at,
                credentials.validation_error,
                credentials.created_at,
                credentials.updated_at,
            )

    async def find_by_user_id(self, user_id: UUID) -> Optional[UserCredentials]:
        """
        Find credentials by user ID.

        Args:
            user_id: User's UUID

        Returns:
            UserCredentials entity if found, None otherwise

        Raises:
            asyncpg.PostgresError: If database operation fails
        """
        query = """
            SELECT
                id, user_id, ims_base_url,
                encrypted_username, encrypted_password,
                is_validated, last_validated_at, validation_error,
                created_at, updated_at
            FROM ims_user_credentials
            WHERE user_id = $1
        """

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, user_id)

            if not row:
                return None

            return UserCredentials(
                id=row['id'],
                user_id=row['user_id'],
                ims_base_url=row['ims_base_url'],
                encrypted_username=row['encrypted_username'],
                encrypted_password=row['encrypted_password'],
                is_validated=row['is_validated'],
                last_validated_at=row['last_validated_at'],
                validation_error=row['validation_error'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
            )

    async def delete_by_user_id(self, user_id: UUID) -> None:
        """
        Delete credentials by user ID.

        Args:
            user_id: User's UUID

        Raises:
            asyncpg.PostgresError: If database operation fails
        """
        query = "DELETE FROM ims_user_credentials WHERE user_id = $1"

        async with self.pool.acquire() as conn:
            await conn.execute(query, user_id)


# Factory function for dependency injection
async def create_credentials_repository(database_url: str) -> PostgreSQLCredentialsRepository:
    """
    Create credentials repository with connection pool.

    Args:
        database_url: PostgreSQL connection string

    Returns:
        Configured PostgreSQLCredentialsRepository

    Example:
        >>> repo = await create_credentials_repository(
        ...     "postgresql://user:pass@localhost/db"
        ... )
    """
    pool = await asyncpg.create_pool(
        database_url,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    return PostgreSQLCredentialsRepository(pool)
