"""
PostgreSQL Ambiguous Term Repository

Repository for managing admin-defined ambiguous terms that require
user clarification before database search.
"""
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from asyncpg import Pool

logger = logging.getLogger(__name__)


class PostgresAmbiguousTermRepository:
    """
    PostgreSQL repository for ambiguous terms.

    Handles persistence of:
    - Admin-defined ambiguous terms
    - Possible entities/meanings for each term
    - Match patterns and priorities
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
        """Ensure the ambiguous_terms table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'ambiguous_terms'
                )
            """)

            if not result:
                logger.warning("ambiguous_terms table does not exist - run migration 025")
                # 마이그레이션이 필요함을 알림
                raise RuntimeError("ambiguous_terms table not found. Run migration 025_query_clarification.sql")

            self._initialized = True
            logger.info("Ambiguous term repository initialized")

    async def get_all_active(self) -> List[Dict[str, Any]]:
        """
        Get all active ambiguous terms.

        Returns:
            List of active ambiguous terms ordered by priority
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, term, term_normalized, category, possible_entities,
                       match_patterns, priority, is_active, entity_embeddings,
                       created_at, updated_at
                FROM ambiguous_terms
                WHERE is_active = TRUE
                ORDER BY priority DESC, term
            """)

            return [self._row_to_dict(row) for row in rows]

    async def get_by_normalized_term(self, term_normalized: str) -> Optional[Dict[str, Any]]:
        """
        Get an ambiguous term by its normalized form.

        Args:
            term_normalized: Normalized term to look up

        Returns:
            Ambiguous term data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, term, term_normalized, category, possible_entities,
                       match_patterns, priority, is_active, entity_embeddings,
                       created_at, updated_at
                FROM ambiguous_terms
                WHERE term_normalized = $1 AND is_active = TRUE
            """, term_normalized.lower().strip())

            if row:
                return self._row_to_dict(row)
            return None

    async def find_matching_terms(self, query: str) -> List[Dict[str, Any]]:
        """
        Find all ambiguous terms that match words in the query.

        Args:
            query: User query to search for ambiguous terms

        Returns:
            List of matching ambiguous terms with position info
        """
        await self._ensure_table()

        # 쿼리에서 단어 추출 (소문자 정규화)
        query_lower = query.lower()
        words = set(query_lower.split())

        async with self._pool.acquire() as conn:
            # 모든 활성 용어 가져오기 (entity_embeddings 포함 for ML recommendations)
            rows = await conn.fetch("""
                SELECT id, term, term_normalized, category, possible_entities,
                       match_patterns, priority, is_active, entity_embeddings,
                       created_at, updated_at
                FROM ambiguous_terms
                WHERE is_active = TRUE
                ORDER BY priority DESC
            """)

            matches = []
            for row in rows:
                term_data = self._row_to_dict(row)
                normalized = term_data['term_normalized']

                # 정규화된 용어가 쿼리 단어에 있는지 확인
                if normalized in words:
                    # 위치 찾기
                    pos = query_lower.find(normalized)
                    if pos >= 0:
                        term_data['position_start'] = pos
                        term_data['position_end'] = pos + len(normalized)
                        matches.append(term_data)
                        continue

                # match_patterns 확인
                for pattern in term_data.get('match_patterns', []):
                    pattern_lower = pattern.lower()
                    if pattern_lower in query_lower:
                        pos = query_lower.find(pattern_lower)
                        if pos >= 0:
                            term_data['position_start'] = pos
                            term_data['position_end'] = pos + len(pattern_lower)
                            matches.append(term_data)
                            break

            return matches

    async def create(
        self,
        term: str,
        possible_entities: List[Dict[str, Any]],
        category: Optional[str] = None,
        match_patterns: Optional[List[str]] = None,
        priority: int = 0,
        is_active: bool = True
    ) -> int:
        """
        Create a new ambiguous term.

        Args:
            term: Term text
            possible_entities: List of possible entity meanings
            category: Optional category
            match_patterns: Optional match patterns
            priority: Priority (0-1000)
            is_active: Active status

        Returns:
            Created term ID
        """
        await self._ensure_table()

        term_normalized = term.lower().strip()
        entities_json = json.dumps(possible_entities)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO ambiguous_terms
                (term, term_normalized, category, possible_entities, match_patterns, priority, is_active)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                RETURNING id
            """, term, term_normalized, category, entities_json,
                match_patterns or [], priority, is_active)

            logger.info(f"Created ambiguous term: {term} (id: {row['id']})")
            return row['id']

    async def update(self, term_id: int, **kwargs) -> bool:
        """
        Update an ambiguous term.

        Args:
            term_id: Term ID to update
            **kwargs: Fields to update

        Returns:
            True if updated
        """
        await self._ensure_table()

        if not kwargs:
            return False

        updates = []
        params = [term_id]
        param_idx = 2

        allowed_fields = {
            "term", "category", "possible_entities", "match_patterns",
            "priority", "is_active", "entity_embeddings"
        }

        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue

            if key == "term":
                updates.append(f"term = ${param_idx}")
                params.append(value)
                param_idx += 1
                updates.append(f"term_normalized = ${param_idx}")
                params.append(value.lower().strip())
                param_idx += 1
            elif key == "possible_entities":
                updates.append(f"possible_entities = ${param_idx}::jsonb")
                params.append(json.dumps(value))
                param_idx += 1
            elif key == "match_patterns":
                updates.append(f"match_patterns = ${param_idx}")
                params.append(value or [])
                param_idx += 1
            elif key == "entity_embeddings":
                updates.append(f"entity_embeddings = ${param_idx}::jsonb")
                params.append(json.dumps(value) if value else None)
                param_idx += 1
            else:
                updates.append(f"{key} = ${param_idx}")
                params.append(value)
                param_idx += 1

        if not updates:
            return False

        query = f"""
            UPDATE ambiguous_terms
            SET {', '.join(updates)}, updated_at = NOW()
            WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return "UPDATE 1" in result

    async def delete(self, term_id: int) -> bool:
        """
        Delete an ambiguous term.

        Args:
            term_id: Term ID to delete

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM ambiguous_terms WHERE id = $1",
                term_id
            )
            return "DELETE 1" in result

    async def update_entity_embeddings(
        self,
        term_id: int,
        entity_embeddings: Dict[str, List[float]],
    ) -> bool:
        """
        Update entity embeddings for a term (Phase 2: ML recommendations).

        Args:
            term_id: Term ID to update
            entity_embeddings: Dict mapping entity_id → embedding vector

        Returns:
            True if updated
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE ambiguous_terms
                SET entity_embeddings = $2::jsonb, updated_at = NOW()
                WHERE id = $1
            """, term_id, json.dumps(entity_embeddings))

            success = "UPDATE 1" in result
            if success:
                logger.info(
                    f"Updated entity embeddings for term {term_id}: "
                    f"{len(entity_embeddings)} entities"
                )
            return success

    async def get_by_id(self, term_id: int) -> Optional[Dict[str, Any]]:
        """
        Get an ambiguous term by ID.

        Args:
            term_id: Term ID to look up

        Returns:
            Ambiguous term data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, term, term_normalized, category, possible_entities,
                       match_patterns, priority, is_active, entity_embeddings,
                       created_at, updated_at
                FROM ambiguous_terms
                WHERE id = $1
            """, term_id)

            if row:
                return self._row_to_dict(row)
            return None

    async def list(
        self,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List ambiguous terms with filtering and pagination.

        Args:
            category: Filter by category
            is_active: Filter by active status
            page: Page number (1-based)
            page_size: Results per page

        Returns:
            Tuple of (terms list, total count)
        """
        await self._ensure_table()

        conditions = []
        params = []
        param_idx = 1

        if category is not None:
            conditions.append(f"category = ${param_idx}")
            params.append(category)
            param_idx += 1

        if is_active is not None:
            conditions.append(f"is_active = ${param_idx}")
            params.append(is_active)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        offset = (page - 1) * page_size

        async with self._pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM ambiguous_terms WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            query = f"""
                SELECT id, term, term_normalized, category, possible_entities,
                       match_patterns, priority, is_active, entity_embeddings,
                       created_at, updated_at
                FROM ambiguous_terms
                WHERE {where_clause}
                ORDER BY priority DESC, term
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([page_size, offset])
            rows = await conn.fetch(query, *params)

            return [self._row_to_dict(row) for row in rows], total

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        # Handle possible_entities - may be string or already parsed
        possible_entities = row["possible_entities"]
        if isinstance(possible_entities, str):
            possible_entities = json.loads(possible_entities)

        # Handle entity_embeddings (Phase 2)
        entity_embeddings = row.get("entity_embeddings")
        if isinstance(entity_embeddings, str):
            entity_embeddings = json.loads(entity_embeddings)

        return {
            "id": row["id"],
            "term": row["term"],
            "term_normalized": row["term_normalized"],
            "category": row["category"],
            "possible_entities": possible_entities or [],
            "match_patterns": list(row["match_patterns"]) if row["match_patterns"] else [],
            "priority": row["priority"],
            "is_active": row["is_active"],
            "entity_embeddings": entity_embeddings,  # Phase 2: ML embeddings
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# =============================================================================
# Singleton Management
# =============================================================================

_ambiguous_term_repository: Optional[PostgresAmbiguousTermRepository] = None


async def get_ambiguous_term_repository(
    pool: Optional[Pool] = None
) -> PostgresAmbiguousTermRepository:
    """
    Get or create ambiguous term repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresAmbiguousTermRepository instance
    """
    global _ambiguous_term_repository

    if _ambiguous_term_repository is None:
        if pool is None:
            raise ValueError("Pool required for first initialization")

        _ambiguous_term_repository = PostgresAmbiguousTermRepository(pool)
        await _ambiguous_term_repository._ensure_table()
        logger.info("Ambiguous term repository initialized")

    return _ambiguous_term_repository


def set_ambiguous_term_repository(repo: PostgresAmbiguousTermRepository) -> None:
    """Set the ambiguous term repository singleton."""
    global _ambiguous_term_repository
    _ambiguous_term_repository = repo
