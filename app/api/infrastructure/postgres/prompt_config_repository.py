"""
PostgreSQL Prompt Configuration Repository

Data access layer for prompt management.
Supports CRUD operations, versioning, and history tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID, uuid4
from pathlib import Path

from asyncpg import Pool

from ...models.prompt_config import (
    PromptConfigDB,
    PromptHistoryDB,
    PromptCategory,
)

logger = logging.getLogger(__name__)


class PromptConfigRepository:
    """
    PostgreSQL implementation for prompt configuration storage.

    Features:
    - Prompt CRUD operations
    - Version history tracking
    - Rollback support
    - File system sync
    """

    # SQL for table creation
    CREATE_TABLES_SQL = """
    CREATE TABLE IF NOT EXISTS prompt_configs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        prompt_id VARCHAR(100) NOT NULL,
        language VARCHAR(10) DEFAULT 'en',
        category VARCHAR(50) NOT NULL,
        name VARCHAR(200) NOT NULL,
        description TEXT,
        content TEXT NOT NULL,
        is_readonly BOOLEAN DEFAULT FALSE,
        source_file VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        updated_by UUID,
        CONSTRAINT unique_prompt_language UNIQUE (prompt_id, language)
    );

    CREATE TABLE IF NOT EXISTS prompt_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        prompt_id VARCHAR(100) NOT NULL,
        language VARCHAR(10) DEFAULT 'en',
        version_number INTEGER NOT NULL,
        content TEXT NOT NULL,
        change_reason TEXT,
        changed_at TIMESTAMPTZ DEFAULT NOW(),
        changed_by UUID,
        CONSTRAINT unique_prompt_version UNIQUE (prompt_id, language, version_number)
    );

    CREATE INDEX IF NOT EXISTS idx_prompt_configs_category ON prompt_configs(category);
    CREATE INDEX IF NOT EXISTS idx_prompt_configs_prompt_id ON prompt_configs(prompt_id);
    CREATE INDEX IF NOT EXISTS idx_prompt_history_lookup ON prompt_history(prompt_id, language);
    CREATE INDEX IF NOT EXISTS idx_prompt_history_changed_at ON prompt_history(changed_at DESC);
    """

    def __init__(self, pool: Pool):
        """Initialize repository with connection pool."""
        self._pool = pool
        self._table_checked = False

    async def ensure_tables_exist(self) -> None:
        """Create tables if they don't exist."""
        if self._table_checked:
            return

        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLES_SQL)
            self._table_checked = True
            logger.info("Prompt config tables ensured")

    async def list_prompts(
        self,
        category: Optional[PromptCategory] = None,
        language: Optional[str] = None
    ) -> List[PromptConfigDB]:
        """
        List all prompts with optional filtering.

        Args:
            category: Filter by category
            language: Filter by language

        Returns:
            List of PromptConfigDB
        """
        await self.ensure_tables_exist()

        query = "SELECT * FROM prompt_configs WHERE 1=1"
        params = []
        param_idx = 1

        if category:
            query += f" AND category = ${param_idx}"
            params.append(category.value if isinstance(category, PromptCategory) else category)
            param_idx += 1

        if language:
            query += f" AND language = ${param_idx}"
            params.append(language)
            param_idx += 1

        query += " ORDER BY category, name"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [PromptConfigDB(**dict(row)) for row in rows]

    async def get_prompt(self, prompt_id: str, language: str = "en") -> Optional[PromptConfigDB]:
        """
        Get a specific prompt by ID and language.

        Args:
            prompt_id: Prompt identifier
            language: Language code

        Returns:
            PromptConfigDB or None
        """
        await self.ensure_tables_exist()

        query = """
            SELECT * FROM prompt_configs
            WHERE prompt_id = $1 AND language = $2
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, prompt_id, language)

        if not row:
            return None

        return PromptConfigDB(**dict(row))

    async def create_prompt(
        self,
        prompt_id: str,
        category: str,
        name: str,
        content: str,
        language: str = "en",
        description: Optional[str] = None,
        source_file: Optional[str] = None,
        is_readonly: bool = False
    ) -> PromptConfigDB:
        """
        Create a new prompt.

        Args:
            prompt_id: Unique identifier
            category: Prompt category
            name: Display name
            content: Prompt content
            language: Language code
            description: Optional description
            source_file: Original file path
            is_readonly: Read-only flag

        Returns:
            Created PromptConfigDB
        """
        await self.ensure_tables_exist()

        id = uuid4()
        now = datetime.now(timezone.utc)

        query = """
            INSERT INTO prompt_configs
            (id, prompt_id, language, category, name, description, content,
             is_readonly, source_file, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query, id, prompt_id, language, category, name, description,
                content, is_readonly, source_file, now, now
            )

        logger.info(f"Created prompt: {prompt_id} ({language})")
        return PromptConfigDB(**dict(row))

    async def update_prompt(
        self,
        prompt_id: str,
        language: str,
        content: str,
        user_id: Optional[UUID] = None
    ) -> Optional[PromptConfigDB]:
        """
        Update prompt content.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            content: New content
            user_id: User making the change

        Returns:
            Updated PromptConfigDB or None
        """
        await self.ensure_tables_exist()

        query = """
            UPDATE prompt_configs
            SET content = $1, updated_at = NOW(), updated_by = $2
            WHERE prompt_id = $3 AND language = $4
            RETURNING *
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, content, user_id, prompt_id, language)

        if not row:
            return None

        logger.info(f"Updated prompt: {prompt_id} ({language})")
        return PromptConfigDB(**dict(row))

    async def save_history(
        self,
        prompt_id: str,
        language: str,
        content: str,
        reason: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> PromptHistoryDB:
        """
        Save current version to history.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            content: Content to save
            reason: Change reason
            user_id: User making the change

        Returns:
            Created PromptHistoryDB
        """
        await self.ensure_tables_exist()

        # Get next version number
        version_query = """
            SELECT COALESCE(MAX(version_number), 0) + 1 as next_version
            FROM prompt_history
            WHERE prompt_id = $1 AND language = $2
        """

        async with self._pool.acquire() as conn:
            version_row = await conn.fetchrow(version_query, prompt_id, language)
            version_number = version_row["next_version"]

            id = uuid4()
            now = datetime.now(timezone.utc)

            query = """
                INSERT INTO prompt_history
                (id, prompt_id, language, version_number, content, change_reason, changed_at, changed_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
            """

            row = await conn.fetchrow(
                query, id, prompt_id, language, version_number,
                content, reason, now, user_id
            )

        logger.info(f"Saved history: {prompt_id} ({language}) v{version_number}")
        return PromptHistoryDB(**dict(row))

    async def get_history(
        self,
        prompt_id: str,
        language: str = "en",
        limit: int = 20
    ) -> List[PromptHistoryDB]:
        """
        Get version history for a prompt.

        Args:
            prompt_id: Prompt identifier
            language: Language code
            limit: Maximum entries to return

        Returns:
            List of PromptHistoryDB
        """
        await self.ensure_tables_exist()

        query = """
            SELECT * FROM prompt_history
            WHERE prompt_id = $1 AND language = $2
            ORDER BY version_number DESC
            LIMIT $3
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, prompt_id, language, limit)

        return [PromptHistoryDB(**dict(row)) for row in rows]

    async def get_version(self, version_id: UUID) -> Optional[PromptHistoryDB]:
        """
        Get a specific version by ID.

        Args:
            version_id: History entry ID

        Returns:
            PromptHistoryDB or None
        """
        await self.ensure_tables_exist()

        query = "SELECT * FROM prompt_history WHERE id = $1"

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, version_id)

        if not row:
            return None

        return PromptHistoryDB(**dict(row))

    async def count_versions(self, prompt_id: str, language: str = "en") -> int:
        """
        Count versions for a prompt.

        Args:
            prompt_id: Prompt identifier
            language: Language code

        Returns:
            Number of versions
        """
        await self.ensure_tables_exist()

        query = """
            SELECT COUNT(*) FROM prompt_history
            WHERE prompt_id = $1 AND language = $2
        """

        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, prompt_id, language)

    async def prompt_exists(self, prompt_id: str, language: str = "en") -> bool:
        """Check if a prompt exists."""
        await self.ensure_tables_exist()

        query = """
            SELECT EXISTS(
                SELECT 1 FROM prompt_configs
                WHERE prompt_id = $1 AND language = $2
            )
        """

        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, prompt_id, language)


# Global repository instance
_repository_instance: Optional[PromptConfigRepository] = None


def get_repository() -> PromptConfigRepository:
    """Get the repository instance."""
    global _repository_instance
    if _repository_instance is None:
        raise RuntimeError("Repository not initialized. Call init_repository() first.")
    return _repository_instance


def init_repository(pool: Pool) -> PromptConfigRepository:
    """Initialize the repository with a connection pool."""
    global _repository_instance
    _repository_instance = PromptConfigRepository(pool)
    return _repository_instance
