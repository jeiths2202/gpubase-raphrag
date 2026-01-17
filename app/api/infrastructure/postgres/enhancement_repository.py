"""
PostgreSQL Enhancement Repository Implementation

Provides persistent storage for enhancement requests with:
- Full CRUD operations
- Filtering and pagination
- Timeline and comment management
- Dashboard statistics
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

import asyncpg
from asyncpg import Pool, Connection

from ...models.enhancement import (
    EnhancementStatus, EnhancementType, EnhancementPriority,
    EnhancementListItem, EnhancementDetail, AttachmentInfo,
    TimelineEvent, Comment, AIAnalysisResult, ArchitectureProposal,
    ImplementationPlan, EnhancementDashboardStats
)

logger = logging.getLogger(__name__)


class PostgresEnhancementRepository:
    """
    PostgreSQL implementation for enhancement request storage.

    Features:
    - Connection pooling for performance
    - JSONB for complex nested data (timeline, comments, analysis)
    - Efficient filtering and full-text search
    - Dashboard statistics aggregation
    """

    # SQL for table creation
    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS enhancements (
        id UUID PRIMARY KEY,
        title VARCHAR(200) NOT NULL,
        description TEXT NOT NULL,
        type VARCHAR(50),
        priority VARCHAR(20),
        status VARCHAR(50) NOT NULL DEFAULT 'submitted',
        author_id VARCHAR(100) NOT NULL,
        author_name VARCHAR(200) NOT NULL,
        ai_analyzed BOOLEAN DEFAULT FALSE,
        attachments_count INTEGER DEFAULT 0,

        -- Complex data stored as JSONB
        attachments JSONB DEFAULT '[]',
        ai_analysis JSONB,
        architecture_proposal JSONB,
        implementation_plan JSONB,
        timeline JSONB DEFAULT '[]',
        comments JSONB DEFAULT '[]',
        assigned_agents JSONB DEFAULT '[]',

        -- Additional fields
        estimated_effort VARCHAR(100),
        actual_effort VARCHAR(100),
        impact_score FLOAT,

        -- Timestamps
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_enhancements_status ON enhancements(status);
    CREATE INDEX IF NOT EXISTS idx_enhancements_type ON enhancements(type);
    CREATE INDEX IF NOT EXISTS idx_enhancements_priority ON enhancements(priority);
    CREATE INDEX IF NOT EXISTS idx_enhancements_author ON enhancements(author_id);
    CREATE INDEX IF NOT EXISTS idx_enhancements_created ON enhancements(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_enhancements_ai_analyzed ON enhancements(ai_analyzed);

    -- Full-text search index
    CREATE INDEX IF NOT EXISTS idx_enhancements_search
    ON enhancements USING gin(to_tsvector('english', title || ' ' || description));
    """

    def __init__(self, pool: Pool):
        """
        Initialize PostgreSQL repository.

        Args:
            pool: asyncpg connection pool
        """
        self._pool = pool

    @classmethod
    async def create(
        cls,
        dsn: str,
        *,
        min_size: int = 5,
        max_size: int = 20,
        **kwargs
    ) -> "PostgresEnhancementRepository":
        """
        Factory method to create repository with connection pool.

        Args:
            dsn: PostgreSQL connection string
            min_size: Minimum pool connections
            max_size: Maximum pool connections
        """
        pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=60,
            **kwargs
        )
        repo = cls(pool)
        await repo._ensure_table_exists()
        return repo

    @classmethod
    def from_pool(cls, pool: Pool) -> "PostgresEnhancementRepository":
        """Create repository from existing pool."""
        return cls(pool)

    async def _ensure_table_exists(self) -> None:
        """Create table if it doesn't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLE_SQL)
            logger.info("Enhancement table ensured")

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()

    # ==================== CRUD Operations ====================

    async def create(self, enhancement: EnhancementDetail) -> EnhancementDetail:
        """
        Create a new enhancement.

        Args:
            enhancement: The enhancement to create

        Returns:
            The created enhancement
        """
        query = """
            INSERT INTO enhancements (
                id, title, description, type, priority, status,
                author_id, author_name, ai_analyzed, attachments_count,
                attachments, ai_analysis, architecture_proposal,
                implementation_plan, timeline, comments, assigned_agents,
                estimated_effort, actual_effort, impact_score,
                created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21, $22
            )
            RETURNING *
        """

        async with self._pool.acquire() as conn:
            await conn.fetchrow(
                query,
                UUID(enhancement.id),
                enhancement.title,
                enhancement.description,
                enhancement.type.value if enhancement.type else None,
                enhancement.priority.value if enhancement.priority else None,
                enhancement.status.value,
                enhancement.author_id,
                enhancement.author_name,
                enhancement.ai_analyzed,
                enhancement.attachments_count,
                json.dumps([a.model_dump(mode="json") for a in enhancement.attachments]),
                json.dumps(enhancement.ai_analysis.model_dump(mode="json")) if enhancement.ai_analysis else None,
                json.dumps(enhancement.architecture_proposal.model_dump(mode="json")) if enhancement.architecture_proposal else None,
                json.dumps(enhancement.implementation_plan.model_dump(mode="json")) if enhancement.implementation_plan else None,
                json.dumps([t.model_dump(mode="json") for t in enhancement.timeline]),
                json.dumps([c.model_dump(mode="json") for c in enhancement.comments]),
                json.dumps(enhancement.assigned_agents),
                enhancement.estimated_effort,
                enhancement.actual_effort,
                enhancement.impact_score,
                enhancement.created_at,
                enhancement.updated_at
            )

        logger.info(f"Created enhancement {enhancement.id}")
        return enhancement

    async def get(self, enhancement_id: str) -> Optional[EnhancementDetail]:
        """
        Get an enhancement by ID.

        Args:
            enhancement_id: The enhancement ID

        Returns:
            The enhancement or None if not found
        """
        query = "SELECT * FROM enhancements WHERE id = $1"

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, UUID(enhancement_id))

        if row:
            return self._row_to_detail(row)
        return None

    async def update(self, enhancement: EnhancementDetail) -> EnhancementDetail:
        """
        Update an existing enhancement.

        Args:
            enhancement: The enhancement with updated data

        Returns:
            The updated enhancement
        """
        query = """
            UPDATE enhancements SET
                title = $2,
                description = $3,
                type = $4,
                priority = $5,
                status = $6,
                ai_analyzed = $7,
                attachments_count = $8,
                attachments = $9,
                ai_analysis = $10,
                architecture_proposal = $11,
                implementation_plan = $12,
                timeline = $13,
                comments = $14,
                assigned_agents = $15,
                estimated_effort = $16,
                actual_effort = $17,
                impact_score = $18,
                updated_at = $19
            WHERE id = $1
        """

        async with self._pool.acquire() as conn:
            await conn.execute(
                query,
                UUID(enhancement.id),
                enhancement.title,
                enhancement.description,
                enhancement.type.value if enhancement.type else None,
                enhancement.priority.value if enhancement.priority else None,
                enhancement.status.value,
                enhancement.ai_analyzed,
                enhancement.attachments_count,
                json.dumps([a.model_dump(mode="json") for a in enhancement.attachments]),
                json.dumps(enhancement.ai_analysis.model_dump(mode="json")) if enhancement.ai_analysis else None,
                json.dumps(enhancement.architecture_proposal.model_dump(mode="json")) if enhancement.architecture_proposal else None,
                json.dumps(enhancement.implementation_plan.model_dump(mode="json")) if enhancement.implementation_plan else None,
                json.dumps([t.model_dump(mode="json") for t in enhancement.timeline]),
                json.dumps([c.model_dump(mode="json") for c in enhancement.comments]),
                json.dumps(enhancement.assigned_agents),
                enhancement.estimated_effort,
                enhancement.actual_effort,
                enhancement.impact_score,
                enhancement.updated_at
            )

        logger.debug(f"Updated enhancement {enhancement.id}")
        return enhancement

    async def delete(self, enhancement_id: str) -> bool:
        """
        Delete an enhancement.

        Args:
            enhancement_id: The enhancement ID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM enhancements WHERE id = $1"

        async with self._pool.acquire() as conn:
            result = await conn.execute(query, UUID(enhancement_id))

        deleted = result == "DELETE 1"
        if deleted:
            logger.info(f"Deleted enhancement {enhancement_id}")
        return deleted

    # ==================== List and Search ====================

    async def list(
        self,
        page: int = 1,
        limit: int = 20,
        status: Optional[EnhancementStatus] = None,
        type_filter: Optional[EnhancementType] = None,
        priority: Optional[EnhancementPriority] = None,
        author_id: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[EnhancementListItem], int]:
        """
        List enhancements with filtering and pagination.

        Args:
            page: Page number (1-indexed)
            limit: Items per page
            status: Filter by status
            type_filter: Filter by type
            priority: Filter by priority
            author_id: Filter by author
            search: Full-text search query

        Returns:
            Tuple of (items, total_count)
        """
        # Build WHERE clause
        conditions = []
        params = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status.value)
            param_idx += 1

        if type_filter:
            conditions.append(f"type = ${param_idx}")
            params.append(type_filter.value)
            param_idx += 1

        if priority:
            conditions.append(f"priority = ${param_idx}")
            params.append(priority.value)
            param_idx += 1

        if author_id:
            conditions.append(f"author_id = ${param_idx}")
            params.append(author_id)
            param_idx += 1

        if search:
            conditions.append(
                f"to_tsvector('english', title || ' ' || description) @@ plainto_tsquery('english', ${param_idx})"
            )
            params.append(search)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        # Count query
        count_query = f"SELECT COUNT(*) FROM enhancements WHERE {where_clause}"

        # Data query with pagination
        offset = (page - 1) * limit
        data_query = f"""
            SELECT id, title, type, priority, status, author_id, author_name,
                   created_at, updated_at, ai_analyzed, attachments_count
            FROM enhancements
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query, *params[:-2])
            rows = await conn.fetch(data_query, *params)

        items = [self._row_to_list_item(row) for row in rows]

        return items, total

    async def list_all(self) -> List[Dict[str, Any]]:
        """
        Get all enhancements as dictionaries.

        Returns:
            List of enhancement dictionaries
        """
        query = "SELECT * FROM enhancements ORDER BY created_at DESC"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query)

        return [self._row_to_dict(row) for row in rows]

    # ==================== Statistics ====================

    async def get_dashboard_stats(self) -> EnhancementDashboardStats:
        """
        Get dashboard statistics.

        Returns:
            Dashboard statistics
        """
        query = """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE ai_analyzed = TRUE) as ai_analyzed_count,
                COUNT(*) FILTER (WHERE status IN ('verified', 'released', 'closed')) as implemented_count,

                -- Status counts
                COUNT(*) FILTER (WHERE status = 'submitted') as status_submitted,
                COUNT(*) FILTER (WHERE status = 'analyzing') as status_analyzing,
                COUNT(*) FILTER (WHERE status = 'analyzed') as status_analyzed,
                COUNT(*) FILTER (WHERE status = 'architecture_review') as status_architecture_review,
                COUNT(*) FILTER (WHERE status = 'approved') as status_approved,
                COUNT(*) FILTER (WHERE status = 'rejected') as status_rejected,
                COUNT(*) FILTER (WHERE status = 'implementing') as status_implementing,
                COUNT(*) FILTER (WHERE status = 'code_review') as status_code_review,
                COUNT(*) FILTER (WHERE status = 'testing') as status_testing,
                COUNT(*) FILTER (WHERE status = 'verified') as status_verified,
                COUNT(*) FILTER (WHERE status = 'released') as status_released,
                COUNT(*) FILTER (WHERE status = 'closed') as status_closed,

                -- Type counts
                COUNT(*) FILTER (WHERE type = 'feature') as type_feature,
                COUNT(*) FILTER (WHERE type = 'bug_fix') as type_bug_fix,
                COUNT(*) FILTER (WHERE type = 'improvement') as type_improvement,
                COUNT(*) FILTER (WHERE type = 'refactor') as type_refactor,
                COUNT(*) FILTER (WHERE type = 'documentation') as type_documentation,
                COUNT(*) FILTER (WHERE type = 'security') as type_security,
                COUNT(*) FILTER (WHERE type = 'performance') as type_performance,

                -- Priority counts
                COUNT(*) FILTER (WHERE priority = 'critical') as priority_critical,
                COUNT(*) FILTER (WHERE priority = 'high') as priority_high,
                COUNT(*) FILTER (WHERE priority = 'medium') as priority_medium,
                COUNT(*) FILTER (WHERE priority = 'low') as priority_low
            FROM enhancements
        """

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query)

        by_status = {}
        for status in EnhancementStatus:
            count = row.get(f"status_{status.value}", 0)
            if count > 0:
                by_status[status.value] = count

        by_type = {}
        for etype in EnhancementType:
            count = row.get(f"type_{etype.value}", 0)
            if count > 0:
                by_type[etype.value] = count

        by_priority = {}
        for priority in EnhancementPriority:
            count = row.get(f"priority_{priority.value}", 0)
            if count > 0:
                by_priority[priority.value] = count

        return EnhancementDashboardStats(
            total_requests=row["total"],
            by_status=by_status,
            by_type=by_type,
            by_priority=by_priority,
            ai_analyzed_count=row["ai_analyzed_count"],
            implemented_count=row["implemented_count"]
        )

    # ==================== Helper Methods ====================

    def _row_to_detail(self, row: asyncpg.Record) -> EnhancementDetail:
        """Convert database row to EnhancementDetail."""
        # Parse JSONB fields
        attachments = []
        if row["attachments"]:
            for a in json.loads(row["attachments"]):
                attachments.append(AttachmentInfo(**a))

        timeline = []
        if row["timeline"]:
            for t in json.loads(row["timeline"]):
                timeline.append(TimelineEvent(**t))

        comments = []
        if row["comments"]:
            for c in json.loads(row["comments"]):
                comments.append(Comment(**c))

        ai_analysis = None
        if row["ai_analysis"]:
            ai_analysis = AIAnalysisResult(**json.loads(row["ai_analysis"]))

        architecture_proposal = None
        if row["architecture_proposal"]:
            architecture_proposal = ArchitectureProposal(**json.loads(row["architecture_proposal"]))

        implementation_plan = None
        if row["implementation_plan"]:
            implementation_plan = ImplementationPlan(**json.loads(row["implementation_plan"]))

        assigned_agents = []
        if row["assigned_agents"]:
            assigned_agents = json.loads(row["assigned_agents"])

        return EnhancementDetail(
            id=str(row["id"]),
            title=row["title"],
            description=row["description"],
            type=EnhancementType(row["type"]) if row["type"] else None,
            priority=EnhancementPriority(row["priority"]) if row["priority"] else None,
            status=EnhancementStatus(row["status"]),
            author_id=row["author_id"],
            author_name=row["author_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            ai_analyzed=row["ai_analyzed"],
            attachments_count=row["attachments_count"],
            attachments=attachments,
            ai_analysis=ai_analysis,
            architecture_proposal=architecture_proposal,
            implementation_plan=implementation_plan,
            timeline=timeline,
            comments=comments,
            assigned_agents=assigned_agents,
            estimated_effort=row["estimated_effort"],
            actual_effort=row["actual_effort"],
            impact_score=row["impact_score"]
        )

    def _row_to_list_item(self, row: asyncpg.Record) -> EnhancementListItem:
        """Convert database row to EnhancementListItem."""
        return EnhancementListItem(
            id=str(row["id"]),
            title=row["title"],
            type=EnhancementType(row["type"]) if row["type"] else None,
            priority=EnhancementPriority(row["priority"]) if row["priority"] else None,
            status=EnhancementStatus(row["status"]),
            author_id=row["author_id"],
            author_name=row["author_name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            ai_analyzed=row["ai_analyzed"],
            attachments_count=row["attachments_count"]
        )

    def _row_to_dict(self, row: asyncpg.Record) -> Dict[str, Any]:
        """Convert database row to dictionary."""
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "description": row["description"],
            "type": row["type"],
            "priority": row["priority"],
            "status": row["status"],
            "author_id": row["author_id"],
            "author_name": row["author_name"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "ai_analyzed": row["ai_analyzed"],
            "attachments_count": row["attachments_count"],
            "attachments": json.loads(row["attachments"]) if row["attachments"] else [],
            "ai_analysis": json.loads(row["ai_analysis"]) if row["ai_analysis"] else None,
            "architecture_proposal": json.loads(row["architecture_proposal"]) if row["architecture_proposal"] else None,
            "implementation_plan": json.loads(row["implementation_plan"]) if row["implementation_plan"] else None,
            "timeline": json.loads(row["timeline"]) if row["timeline"] else [],
            "comments": json.loads(row["comments"]) if row["comments"] else [],
            "assigned_agents": json.loads(row["assigned_agents"]) if row["assigned_agents"] else [],
            "estimated_effort": row["estimated_effort"],
            "actual_effort": row["actual_effort"],
            "impact_score": row["impact_score"]
        }
