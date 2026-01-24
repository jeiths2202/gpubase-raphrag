"""
PostgreSQL User Term Preference Repository

Repository for managing user-specific term clarification preferences,
enabling "remember my choice" functionality.
"""
import logging
from typing import Optional, List, Dict, Any, Tuple

from asyncpg import Pool

logger = logging.getLogger(__name__)


class PostgresUserTermPreferenceRepository:
    """
    PostgreSQL repository for user term preferences.

    Handles persistence of:
    - User-specific term clarification choices
    - Preference usage tracking
    - Permanent vs temporary preferences
    """

    def __init__(self, pool: Pool):
        """
        Initialize with asyncpg connection pool.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool
        self._initialized = False

    async def _ensure_table(self) -> None:
        """Ensure the user_term_preferences table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'user_term_preferences'
                )
            """)

            if not result:
                logger.warning("user_term_preferences table does not exist - run migration 025")
                raise RuntimeError("user_term_preferences table not found. Run migration 025_query_clarification.sql")

            self._initialized = True
            logger.info("User term preference repository initialized")

    async def get_user_preference(
        self,
        user_id: str,
        term_normalized: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a user's preference for a specific term.

        Args:
            user_id: User UUID
            term_normalized: Normalized term

        Returns:
            Preference data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_id, term_normalized, selected_entity_id,
                       selected_entity_name, is_permanent, usage_count,
                       created_at, updated_at
                FROM user_term_preferences
                WHERE user_id = $1::uuid AND term_normalized = $2
            """, user_id, term_normalized.lower().strip())

            if row:
                return self._row_to_dict(row)
            return None

    async def get_user_preferences(
        self,
        user_id: str,
        terms_normalized: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get all of a user's term preferences, optionally filtered by terms.

        Args:
            user_id: User UUID
            terms_normalized: Optional list of terms to filter

        Returns:
            Dictionary mapping term_normalized -> preference data
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            if terms_normalized:
                # 특정 용어들에 대한 선호도만 조회
                normalized_terms = [t.lower().strip() for t in terms_normalized]
                rows = await conn.fetch("""
                    SELECT id, user_id, term_normalized, selected_entity_id,
                           selected_entity_name, is_permanent, usage_count,
                           created_at, updated_at
                    FROM user_term_preferences
                    WHERE user_id = $1::uuid AND term_normalized = ANY($2)
                """, user_id, normalized_terms)
            else:
                # 모든 선호도 조회
                rows = await conn.fetch("""
                    SELECT id, user_id, term_normalized, selected_entity_id,
                           selected_entity_name, is_permanent, usage_count,
                           created_at, updated_at
                    FROM user_term_preferences
                    WHERE user_id = $1::uuid
                    ORDER BY usage_count DESC
                """, user_id)

            return {
                row["term_normalized"]: self._row_to_dict(row)
                for row in rows
            }

    async def save_preference(
        self,
        user_id: str,
        term_normalized: str,
        selected_entity_id: str,
        selected_entity_name: str,
        is_permanent: bool = True
    ) -> int:
        """
        Save or update a user's term preference.

        Args:
            user_id: User UUID
            term_normalized: Normalized term
            selected_entity_id: Selected entity ID
            selected_entity_name: Selected entity name
            is_permanent: Whether to save permanently

        Returns:
            Preference ID
        """
        await self._ensure_table()

        term_normalized = term_normalized.lower().strip()

        async with self._pool.acquire() as conn:
            # Upsert: insert or update on conflict
            row = await conn.fetchrow("""
                INSERT INTO user_term_preferences
                (user_id, term_normalized, selected_entity_id, selected_entity_name, is_permanent, usage_count)
                VALUES ($1::uuid, $2, $3, $4, $5, 1)
                ON CONFLICT (user_id, term_normalized)
                DO UPDATE SET
                    selected_entity_id = EXCLUDED.selected_entity_id,
                    selected_entity_name = EXCLUDED.selected_entity_name,
                    is_permanent = EXCLUDED.is_permanent,
                    usage_count = user_term_preferences.usage_count + 1,
                    updated_at = NOW()
                RETURNING id
            """, user_id, term_normalized, selected_entity_id, selected_entity_name, is_permanent)

            logger.info(
                f"Saved preference: user={user_id[:8]}..., term={term_normalized}, "
                f"entity={selected_entity_id}, permanent={is_permanent}"
            )
            return row['id']

    async def increment_usage(
        self,
        user_id: str,
        term_normalized: str
    ) -> bool:
        """
        Increment usage count for a preference.

        Args:
            user_id: User UUID
            term_normalized: Normalized term

        Returns:
            True if updated
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE user_term_preferences
                SET usage_count = usage_count + 1, updated_at = NOW()
                WHERE user_id = $1::uuid AND term_normalized = $2
            """, user_id, term_normalized.lower().strip())

            return "UPDATE 1" in result

    async def delete_preference(
        self,
        user_id: str,
        term_normalized: str
    ) -> bool:
        """
        Delete a user's preference for a term.

        Args:
            user_id: User UUID
            term_normalized: Normalized term

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM user_term_preferences
                WHERE user_id = $1::uuid AND term_normalized = $2
            """, user_id, term_normalized.lower().strip())

            return "DELETE 1" in result

    async def delete_all_user_preferences(self, user_id: str) -> int:
        """
        Delete all preferences for a user.

        Args:
            user_id: User UUID

        Returns:
            Number of deleted preferences
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM user_term_preferences WHERE user_id = $1::uuid
            """, user_id)

            try:
                return int(result.split()[1])
            except (IndexError, ValueError):
                return 0

    async def list_user_preferences(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List all preferences for a user with pagination.

        Args:
            user_id: User UUID
            page: Page number (1-based)
            page_size: Results per page

        Returns:
            Tuple of (preferences list, total count)
        """
        await self._ensure_table()

        offset = (page - 1) * page_size

        async with self._pool.acquire() as conn:
            # Get total count
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM user_term_preferences WHERE user_id = $1::uuid
            """, user_id)

            # Get paginated results
            rows = await conn.fetch("""
                SELECT id, user_id, term_normalized, selected_entity_id,
                       selected_entity_name, is_permanent, usage_count,
                       created_at, updated_at
                FROM user_term_preferences
                WHERE user_id = $1::uuid
                ORDER BY usage_count DESC, updated_at DESC
                LIMIT $2 OFFSET $3
            """, user_id, page_size, offset)

            return [self._row_to_dict(row) for row in rows], total

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row["id"],
            "user_id": str(row["user_id"]),
            "term_normalized": row["term_normalized"],
            "selected_entity_id": row["selected_entity_id"],
            "selected_entity_name": row["selected_entity_name"],
            "is_permanent": row["is_permanent"],
            "usage_count": row["usage_count"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# =============================================================================
# Singleton Management
# =============================================================================

_user_term_preference_repository: Optional[PostgresUserTermPreferenceRepository] = None


async def get_user_term_preference_repository(
    pool: Optional[Pool] = None
) -> PostgresUserTermPreferenceRepository:
    """
    Get or create user term preference repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresUserTermPreferenceRepository instance
    """
    global _user_term_preference_repository

    if _user_term_preference_repository is None:
        if pool is None:
            raise ValueError("Pool required for first initialization")

        _user_term_preference_repository = PostgresUserTermPreferenceRepository(pool)
        await _user_term_preference_repository._ensure_table()
        logger.info("User term preference repository initialized")

    return _user_term_preference_repository


def set_user_term_preference_repository(repo: PostgresUserTermPreferenceRepository) -> None:
    """Set the user term preference repository singleton."""
    global _user_term_preference_repository
    _user_term_preference_repository = repo
