"""
PostgreSQL Term Candidate Repository

Repository for managing auto-extracted term candidates from documents
that require admin review before becoming active ambiguous terms.
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from asyncpg import Pool

logger = logging.getLogger(__name__)


class PostgresTermCandidateRepository:
    """
    Repository for term candidates extracted from documents.

    Handles:
    - Storing auto-extracted term candidates
    - Admin review workflow (pending → approved/rejected)
    - Duplicate detection and occurrence counting
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
        """Ensure the term_candidates table exists."""
        if self._initialized:
            return

        async with self._pool.acquire() as conn:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'term_candidates'
                )
            """)

            if not result:
                logger.warning("term_candidates table does not exist - run migration 026")
                raise RuntimeError(
                    "term_candidates table not found. "
                    "Run migration 026_clarification_ml_extension.sql"
                )

            self._initialized = True
            logger.info("Term candidate repository initialized")

    async def create(
        self,
        term: str,
        source_document_id: Optional[str] = None,
        source_document_name: Optional[str] = None,
        extraction_context: Optional[str] = None,
        extraction_method: str = "pattern",
        confidence_score: float = 0.5,
        suggested_category: Optional[str] = None,
    ) -> int:
        """
        Create a new term candidate or merge with existing.

        Uses the merge_term_candidate function to handle duplicates
        by incrementing occurrence_count.

        Args:
            term: Extracted term text
            source_document_id: Source document ID
            source_document_name: Source document name
            extraction_context: Surrounding context text
            extraction_method: How the term was extracted (pattern, ner, frequency)
            confidence_score: Confidence score (0.0-1.0)
            suggested_category: Suggested category

        Returns:
            Created or merged candidate ID
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            candidate_id = await conn.fetchval("""
                SELECT merge_term_candidate($1, $2, $3, $4, $5, $6, $7)
            """, term, source_document_id, source_document_name,
                extraction_context, extraction_method,
                confidence_score, suggested_category)

            logger.debug(f"Term candidate created/merged: {term} (id: {candidate_id})")
            return candidate_id

    async def create_batch(
        self,
        candidates: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Create multiple term candidates efficiently.

        Args:
            candidates: List of candidate dicts with keys:
                term, source_document_id, source_document_name,
                extraction_context, extraction_method,
                confidence_score, suggested_category

        Returns:
            List of created/merged candidate IDs
        """
        await self._ensure_table()

        result_ids = []
        async with self._pool.acquire() as conn:
            for candidate in candidates:
                candidate_id = await conn.fetchval("""
                    SELECT merge_term_candidate($1, $2, $3, $4, $5, $6, $7)
                """,
                    candidate.get("term"),
                    candidate.get("source_document_id"),
                    candidate.get("source_document_name"),
                    candidate.get("extraction_context"),
                    candidate.get("extraction_method", "pattern"),
                    candidate.get("confidence_score", 0.5),
                    candidate.get("suggested_category"),
                )
                result_ids.append(candidate_id)

        logger.info(f"Created/merged {len(result_ids)} term candidates")
        return result_ids

    async def get_by_id(self, candidate_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a term candidate by ID.

        Args:
            candidate_id: Candidate ID

        Returns:
            Candidate data or None
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, term, term_normalized, source_document_id,
                       source_document_name, extraction_context, extraction_method,
                       confidence_score, suggested_category, occurrence_count,
                       status, reviewed_by, reviewed_at, approved_term_id,
                       rejection_reason, created_at, updated_at
                FROM term_candidates
                WHERE id = $1
            """, candidate_id)

            if row:
                return self._row_to_dict(row)
            return None

    async def list(
        self,
        status: Optional[str] = None,
        extraction_method: Optional[str] = None,
        min_confidence: Optional[float] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List term candidates with filtering and pagination.

        Args:
            status: Filter by status (pending, approved, rejected, merged)
            extraction_method: Filter by extraction method
            min_confidence: Minimum confidence score
            page: Page number (1-based)
            page_size: Results per page

        Returns:
            Tuple of (candidates list, total count)
        """
        await self._ensure_table()

        conditions = []
        params = []
        param_idx = 1

        if status is not None:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        if extraction_method is not None:
            conditions.append(f"extraction_method = ${param_idx}")
            params.append(extraction_method)
            param_idx += 1

        if min_confidence is not None:
            conditions.append(f"confidence_score >= ${param_idx}")
            params.append(min_confidence)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        offset = (page - 1) * page_size

        async with self._pool.acquire() as conn:
            # Get total count
            count_query = f"SELECT COUNT(*) FROM term_candidates WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            query = f"""
                SELECT id, term, term_normalized, source_document_id,
                       source_document_name, extraction_context, extraction_method,
                       confidence_score, suggested_category, occurrence_count,
                       status, reviewed_by, reviewed_at, approved_term_id,
                       rejection_reason, created_at, updated_at
                FROM term_candidates
                WHERE {where_clause}
                ORDER BY confidence_score DESC, occurrence_count DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """
            params.extend([page_size, offset])
            rows = await conn.fetch(query, *params)

            return [self._row_to_dict(row) for row in rows], total

    async def list_pending_with_similarity(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List pending candidates with similarity info against existing terms.

        Uses the v_pending_term_candidates view for efficient lookup.

        Args:
            page: Page number (1-based)
            page_size: Results per page

        Returns:
            Tuple of (candidates with similarity info, total count)
        """
        await self._ensure_table()

        offset = (page - 1) * page_size

        async with self._pool.acquire() as conn:
            # Get total count
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM v_pending_term_candidates"
            )

            # Get paginated results from view
            rows = await conn.fetch("""
                SELECT id, term, term_normalized, source_document_name,
                       extraction_context, extraction_method, confidence_score,
                       suggested_category, occurrence_count, created_at,
                       match_status, similar_term_id, similar_term
                FROM v_pending_term_candidates
                LIMIT $1 OFFSET $2
            """, page_size, offset)

            return [dict(row) for row in rows], total

    async def approve(
        self,
        candidate_id: int,
        reviewed_by: str,
        approved_term_id: Optional[int] = None,
    ) -> bool:
        """
        Approve a term candidate.

        Args:
            candidate_id: Candidate ID to approve
            reviewed_by: Admin user ID who approved
            approved_term_id: Link to created/merged ambiguous_term (optional)

        Returns:
            True if approved
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE term_candidates
                SET status = 'approved',
                    reviewed_by = $2,
                    reviewed_at = NOW(),
                    approved_term_id = $3
                WHERE id = $1 AND status = 'pending'
            """, candidate_id, reviewed_by, approved_term_id)

            success = "UPDATE 1" in result
            if success:
                logger.info(f"Term candidate {candidate_id} approved by {reviewed_by[:8]}...")
            return success

    async def reject(
        self,
        candidate_id: int,
        reviewed_by: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Reject a term candidate.

        Args:
            candidate_id: Candidate ID to reject
            reviewed_by: Admin user ID who rejected
            reason: Rejection reason

        Returns:
            True if rejected
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE term_candidates
                SET status = 'rejected',
                    reviewed_by = $2,
                    reviewed_at = NOW(),
                    rejection_reason = $3
                WHERE id = $1 AND status = 'pending'
            """, candidate_id, reviewed_by, reason)

            success = "UPDATE 1" in result
            if success:
                logger.info(f"Term candidate {candidate_id} rejected by {reviewed_by[:8]}...")
            return success

    async def mark_merged(
        self,
        candidate_id: int,
        reviewed_by: str,
        merged_into_term_id: int,
    ) -> bool:
        """
        Mark a candidate as merged into existing ambiguous term.

        Args:
            candidate_id: Candidate ID
            reviewed_by: Admin user ID
            merged_into_term_id: Existing ambiguous_term ID it was merged into

        Returns:
            True if marked as merged
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE term_candidates
                SET status = 'merged',
                    reviewed_by = $2,
                    reviewed_at = NOW(),
                    approved_term_id = $3
                WHERE id = $1 AND status = 'pending'
            """, candidate_id, reviewed_by, merged_into_term_id)

            success = "UPDATE 1" in result
            if success:
                logger.info(
                    f"Term candidate {candidate_id} merged into term {merged_into_term_id}"
                )
            return success

    async def find_by_term(self, term: str) -> List[Dict[str, Any]]:
        """
        Find candidates by term (normalized match).

        Args:
            term: Term to search for

        Returns:
            List of matching candidates
        """
        await self._ensure_table()

        term_normalized = term.lower().strip()

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, term, term_normalized, source_document_id,
                       source_document_name, extraction_context, extraction_method,
                       confidence_score, suggested_category, occurrence_count,
                       status, reviewed_by, reviewed_at, approved_term_id,
                       rejection_reason, created_at, updated_at
                FROM term_candidates
                WHERE term_normalized = $1
                ORDER BY created_at DESC
            """, term_normalized)

            return [self._row_to_dict(row) for row in rows]

    async def delete(self, candidate_id: int) -> bool:
        """
        Delete a term candidate.

        Args:
            candidate_id: Candidate ID to delete

        Returns:
            True if deleted
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM term_candidates WHERE id = $1",
                candidate_id
            )
            return "DELETE 1" in result

    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about term candidates.

        Returns:
            Dict with status counts, method counts, avg confidence, etc.
        """
        await self._ensure_table()

        async with self._pool.acquire() as conn:
            # Status counts
            status_counts = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM term_candidates
                GROUP BY status
            """)

            # Method counts
            method_counts = await conn.fetch("""
                SELECT extraction_method, COUNT(*) as count
                FROM term_candidates
                GROUP BY extraction_method
            """)

            # Average confidence by status
            avg_confidence = await conn.fetch("""
                SELECT status, AVG(confidence_score) as avg_confidence
                FROM term_candidates
                GROUP BY status
            """)

            # Total count
            total = await conn.fetchval("SELECT COUNT(*) FROM term_candidates")

            return {
                "total": total,
                "by_status": {row["status"]: row["count"] for row in status_counts},
                "by_method": {row["extraction_method"]: row["count"] for row in method_counts},
                "avg_confidence_by_status": {
                    row["status"]: float(row["avg_confidence"]) if row["avg_confidence"] else 0.0
                    for row in avg_confidence
                },
            }

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": row["id"],
            "term": row["term"],
            "term_normalized": row["term_normalized"],
            "source_document_id": row["source_document_id"],
            "source_document_name": row["source_document_name"],
            "extraction_context": row["extraction_context"],
            "extraction_method": row["extraction_method"],
            "confidence_score": float(row["confidence_score"]) if row["confidence_score"] else 0.5,
            "suggested_category": row["suggested_category"],
            "occurrence_count": row["occurrence_count"],
            "status": row["status"],
            "reviewed_by": str(row["reviewed_by"]) if row["reviewed_by"] else None,
            "reviewed_at": row["reviewed_at"],
            "approved_term_id": row["approved_term_id"],
            "rejection_reason": row["rejection_reason"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


# =============================================================================
# Singleton Management
# =============================================================================

_term_candidate_repository: Optional[PostgresTermCandidateRepository] = None


async def get_term_candidate_repository(
    pool: Optional[Pool] = None
) -> PostgresTermCandidateRepository:
    """
    Get or create term candidate repository singleton.

    Args:
        pool: Optional asyncpg pool (uses default if not provided)

    Returns:
        PostgresTermCandidateRepository instance
    """
    global _term_candidate_repository

    if _term_candidate_repository is None:
        if pool is None:
            raise ValueError("Pool required for first initialization")

        _term_candidate_repository = PostgresTermCandidateRepository(pool)
        await _term_candidate_repository._ensure_table()
        logger.info("Term candidate repository initialized")

    return _term_candidate_repository


def set_term_candidate_repository(repo: PostgresTermCandidateRepository) -> None:
    """Set the term candidate repository singleton."""
    global _term_candidate_repository
    _term_candidate_repository = repo
