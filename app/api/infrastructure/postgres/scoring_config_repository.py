"""
PostgreSQL Scoring Configuration Repository

Production-ready implementation for scoring configuration persistence.
Supports configuration versioning, history tracking, and rollback.
"""
import logging
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from asyncpg import Pool

from ...models.scoring_config import (
    ScoringConfig,
    ScoringConfigHistory,
)

logger = logging.getLogger(__name__)


class PostgresScoringConfigRepository:
    """
    PostgreSQL implementation for scoring configuration storage.

    Features:
    - Active configuration management
    - Configuration history tracking
    - Rollback support
    - JSONB storage for nested config data
    """

    # SQL for table creation
    CREATE_TABLES_SQL = """
    CREATE TABLE IF NOT EXISTS scoring_configs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(100) NOT NULL DEFAULT 'default',
        description TEXT,
        config_data JSONB NOT NULL,
        is_active BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        created_by UUID,
        UNIQUE(name, is_active) WHERE is_active = TRUE
    );

    CREATE TABLE IF NOT EXISTS scoring_config_history (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        config_id UUID REFERENCES scoring_configs(id) ON DELETE CASCADE,
        config_data JSONB NOT NULL,
        changed_at TIMESTAMPTZ DEFAULT NOW(),
        changed_by UUID,
        reason TEXT,
        version INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_scoring_configs_active
        ON scoring_configs(is_active) WHERE is_active = TRUE;
    CREATE INDEX IF NOT EXISTS idx_scoring_config_history_config_id
        ON scoring_config_history(config_id);
    CREATE INDEX IF NOT EXISTS idx_scoring_config_history_changed_at
        ON scoring_config_history(changed_at DESC);
    """

    def __init__(self, pool: Pool):
        """
        Initialize PostgreSQL scoring config repository.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool
        self._table_checked = False

    async def ensure_tables_exist(self) -> None:
        """Create tables if they don't exist."""
        if self._table_checked:
            return

        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLES_SQL)
            self._table_checked = True
            logger.info("Scoring config tables ensured")

    async def get_active_config(self) -> Optional[ScoringConfig]:
        """
        Get the currently active scoring configuration.

        Returns:
            Active ScoringConfig or None if not found
        """
        await self.ensure_tables_exist()

        query = """
            SELECT config_data FROM scoring_configs
            WHERE is_active = TRUE
            LIMIT 1
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query)

        if not row:
            return None

        try:
            config_data = row["config_data"]
            if isinstance(config_data, str):
                config_data = json.loads(config_data)
            return ScoringConfig(**config_data)
        except Exception as e:
            logger.error(f"Failed to parse stored config: {e}")
            return None

    async def save_config(
        self,
        config: ScoringConfig,
        user_id: Optional[UUID] = None,
        reason: Optional[str] = None
    ) -> UUID:
        """
        Save a new configuration as active.

        Args:
            config: ScoringConfig to save
            user_id: User making the change
            reason: Reason for the change

        Returns:
            ID of the saved configuration
        """
        await self.ensure_tables_exist()

        config_id = uuid4()
        config_data = config.model_dump()

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Deactivate current active config
                await conn.execute("""
                    UPDATE scoring_configs
                    SET is_active = FALSE, updated_at = NOW()
                    WHERE is_active = TRUE
                """)

                # Get next version number
                version = await conn.fetchval("""
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM scoring_config_history
                """)

                # Insert new config
                await conn.execute("""
                    INSERT INTO scoring_configs (id, name, config_data, is_active, created_by)
                    VALUES ($1, 'default', $2, TRUE, $3)
                """, config_id, json.dumps(config_data), user_id)

                # Record history
                await conn.execute("""
                    INSERT INTO scoring_config_history
                    (config_id, config_data, changed_by, reason, version)
                    VALUES ($1, $2, $3, $4, $5)
                """, config_id, json.dumps(config_data), user_id, reason, version)

        logger.info(f"Saved scoring config {config_id} (version {version})")
        return config_id

    async def update_config(
        self,
        config: ScoringConfig,
        user_id: Optional[UUID] = None,
        reason: Optional[str] = None
    ) -> bool:
        """
        Update the active configuration.

        Args:
            config: Updated ScoringConfig
            user_id: User making the change
            reason: Reason for the change

        Returns:
            True if updated, False if no active config exists
        """
        await self.ensure_tables_exist()

        config_data = config.model_dump()

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Get current active config
                row = await conn.fetchrow("""
                    SELECT id FROM scoring_configs WHERE is_active = TRUE
                """)

                if not row:
                    # No active config, create one
                    await self.save_config(config, user_id, reason)
                    return True

                config_id = row["id"]

                # Get next version
                version = await conn.fetchval("""
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM scoring_config_history
                    WHERE config_id = $1
                """, config_id)

                # Update config
                await conn.execute("""
                    UPDATE scoring_configs
                    SET config_data = $1, updated_at = NOW()
                    WHERE id = $2
                """, json.dumps(config_data), config_id)

                # Record history
                await conn.execute("""
                    INSERT INTO scoring_config_history
                    (config_id, config_data, changed_by, reason, version)
                    VALUES ($1, $2, $3, $4, $5)
                """, config_id, json.dumps(config_data), user_id, reason, version)

        logger.info(f"Updated scoring config {config_id} (version {version})")
        return True

    async def get_history(
        self,
        limit: int = 20,
        offset: int = 0
    ) -> List[ScoringConfigHistory]:
        """
        Get configuration change history.

        Args:
            limit: Maximum number of entries
            offset: Offset for pagination

        Returns:
            List of ScoringConfigHistory entries
        """
        await self.ensure_tables_exist()

        query = """
            SELECT h.id, h.config_id, h.config_data, h.changed_at,
                   h.changed_by, h.reason, h.version
            FROM scoring_config_history h
            ORDER BY h.changed_at DESC
            LIMIT $1 OFFSET $2
        """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, limit, offset)

        result = []
        for row in rows:
            try:
                config_data = row["config_data"]
                if isinstance(config_data, str):
                    config_data = json.loads(config_data)

                result.append(ScoringConfigHistory(
                    id=row["id"],
                    config_id=row["config_id"],
                    config=ScoringConfig(**config_data),
                    changed_at=row["changed_at"],
                    changed_by=row["changed_by"],
                    reason=row["reason"],
                    version=row["version"]
                ))
            except Exception as e:
                logger.warning(f"Failed to parse history entry: {e}")
                continue

        return result

    async def get_history_entry(self, history_id: UUID) -> Optional[ScoringConfigHistory]:
        """
        Get a specific history entry.

        Args:
            history_id: History entry ID

        Returns:
            ScoringConfigHistory or None
        """
        await self.ensure_tables_exist()

        query = """
            SELECT id, config_id, config_data, changed_at, changed_by, reason, version
            FROM scoring_config_history
            WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, history_id)

        if not row:
            return None

        try:
            config_data = row["config_data"]
            if isinstance(config_data, str):
                config_data = json.loads(config_data)

            return ScoringConfigHistory(
                id=row["id"],
                config_id=row["config_id"],
                config=ScoringConfig(**config_data),
                changed_at=row["changed_at"],
                changed_by=row["changed_by"],
                reason=row["reason"],
                version=row["version"]
            )
        except Exception as e:
            logger.error(f"Failed to parse history entry: {e}")
            return None

    async def rollback_to_version(
        self,
        history_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Optional[ScoringConfig]:
        """
        Rollback to a specific configuration version.

        Args:
            history_id: History entry ID to rollback to
            user_id: User performing rollback

        Returns:
            Rolled back ScoringConfig or None if failed
        """
        await self.ensure_tables_exist()

        # Get the history entry
        entry = await self.get_history_entry(history_id)
        if not entry:
            return None

        # Save as new active config
        await self.save_config(
            config=entry.config,
            user_id=user_id,
            reason=f"Rollback to version {entry.version}"
        )

        return entry.config

    async def delete_old_history(self, keep_count: int = 100) -> int:
        """
        Delete old history entries, keeping the most recent ones.

        Args:
            keep_count: Number of recent entries to keep

        Returns:
            Number of deleted entries
        """
        await self.ensure_tables_exist()

        query = """
            DELETE FROM scoring_config_history
            WHERE id NOT IN (
                SELECT id FROM scoring_config_history
                ORDER BY changed_at DESC
                LIMIT $1
            )
        """

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, keep_count)

        count = int(result.split()[-1]) if result else 0
        if count > 0:
            logger.info(f"Deleted {count} old scoring config history entries")
        return count

    async def config_exists(self) -> bool:
        """Check if any configuration exists."""
        await self.ensure_tables_exist()

        query = "SELECT EXISTS(SELECT 1 FROM scoring_configs WHERE is_active = TRUE)"

        async with self._pool.acquire() as conn:
            return await conn.fetchval(query)
