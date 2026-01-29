"""
OpenCode Execution Log Repository

PostgreSQL repository for logging OpenCode Agent executions.
Provides audit trail and analytics for document-grounded AI responses.
"""
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID

import asyncpg
from asyncpg import Pool

from ...core.logging_framework import AppLogger, LogCategory


class OpenCodeExecutionLogRepository:
    """PostgreSQL repository for OpenCode execution logs"""

    def __init__(self, pool: Pool):
        """
        Initialize OpenCode execution log repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
        self.logger = AppLogger("opencode_execution_log_repository")

    async def ensure_table_exists(self) -> None:
        """Create the opencode_execution_log table if it doesn't exist"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS opencode_execution_log (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    run_id VARCHAR(64) NOT NULL,
                    user_id VARCHAR(64),
                    session_id VARCHAR(64),
                    query TEXT NOT NULL,
                    language VARCHAR(10) DEFAULT 'auto',
                    status VARCHAR(20) NOT NULL,
                    answer TEXT,
                    sources JSONB DEFAULT '[]'::jsonb,
                    steps_executed INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    hallucination_checked BOOLEAN DEFAULT FALSE,
                    vision_used BOOLEAN DEFAULT FALSE,
                    execution_time_ms REAL,
                    verification_checklist JSONB,
                    step_history JSONB DEFAULT '[]'::jsonb,
                    hallucination_check JSONB,
                    metadata JSONB DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );

                -- Indexes for common queries
                CREATE INDEX IF NOT EXISTS idx_opencode_log_run_id ON opencode_execution_log(run_id);
                CREATE INDEX IF NOT EXISTS idx_opencode_log_user_id ON opencode_execution_log(user_id);
                CREATE INDEX IF NOT EXISTS idx_opencode_log_session_id ON opencode_execution_log(session_id);
                CREATE INDEX IF NOT EXISTS idx_opencode_log_status ON opencode_execution_log(status);
                CREATE INDEX IF NOT EXISTS idx_opencode_log_created_at ON opencode_execution_log(created_at);
            """)
            self.logger.info("OpenCode execution log table ensured")

    async def log_execution(
        self,
        run_id: str,
        user_id: Optional[str],
        session_id: str,
        query: str,
        language: str,
        status: str,
        answer: str,
        sources: List[Dict[str, Any]],
        steps_executed: int,
        retry_count: int,
        hallucination_checked: bool,
        vision_used: bool,
        execution_time_ms: float,
        verification_checklist: Dict[str, bool],
        step_history: List[Dict[str, Any]],
        hallucination_check: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """
        Log an OpenCode execution.

        Args:
            run_id: Unique execution run ID
            user_id: User ID (if authenticated)
            session_id: Session ID
            query: User query
            language: Query language
            status: Execution status (SUCCESS, BLOCKED, RETRY)
            answer: Generated answer
            sources: List of source references
            steps_executed: Number of steps executed
            retry_count: Number of retries
            hallucination_checked: Whether hallucination check was performed
            vision_used: Whether Vision LLM was used
            execution_time_ms: Total execution time in milliseconds
            verification_checklist: Verification checklist results
            step_history: Detailed step execution history
            hallucination_check: Hallucination check results
            metadata: Additional metadata

        Returns:
            UUID of the inserted log entry
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO opencode_execution_log (
                    run_id, user_id, session_id, query, language,
                    status, answer, sources, steps_executed, retry_count,
                    hallucination_checked, vision_used, execution_time_ms,
                    verification_checklist, step_history, hallucination_check, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                RETURNING id
                """,
                run_id,
                user_id,
                session_id,
                query,
                language,
                status,
                answer,
                json.dumps(sources),
                steps_executed,
                retry_count,
                hallucination_checked,
                vision_used,
                execution_time_ms,
                json.dumps(verification_checklist) if verification_checklist else None,
                json.dumps(step_history) if step_history else None,
                json.dumps(hallucination_check) if hallucination_check else None,
                json.dumps(metadata) if metadata else None,
            )
            return row['id']

    async def get_execution_by_run_id(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get execution log by run ID.

        Args:
            run_id: Execution run ID

        Returns:
            Execution log dictionary or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM opencode_execution_log WHERE run_id = $1
                """,
                run_id
            )
            return dict(row) if row else None

    async def get_executions_by_session(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get executions for a session.

        Args:
            session_id: Session ID
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Tuple of (executions list, total count)
        """
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM opencode_execution_log WHERE session_id = $1",
                session_id
            )

            rows = await conn.fetch(
                """
                SELECT id, run_id, query, status, steps_executed, retry_count,
                       hallucination_checked, vision_used, execution_time_ms, created_at
                FROM opencode_execution_log
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                session_id, limit, offset
            )

        return [dict(r) for r in rows], total or 0

    async def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get OpenCode execution statistics.

        Args:
            days: Look back period in days

        Returns:
            Statistics dictionary
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        async with self.pool.acquire() as conn:
            # Total executions
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM opencode_execution_log WHERE created_at >= $1",
                cutoff_date
            )

            # Success rate
            success_count = await conn.fetchval(
                "SELECT COUNT(*) FROM opencode_execution_log WHERE created_at >= $1 AND status = 'SUCCESS'",
                cutoff_date
            )

            # Average execution time
            avg_time = await conn.fetchval(
                "SELECT AVG(execution_time_ms) FROM opencode_execution_log WHERE created_at >= $1",
                cutoff_date
            )

            # Hallucination detection rate
            hallucination_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM opencode_execution_log
                WHERE created_at >= $1 AND hallucination_checked = true
                """,
                cutoff_date
            )

            # Vision usage rate
            vision_count = await conn.fetchval(
                "SELECT COUNT(*) FROM opencode_execution_log WHERE created_at >= $1 AND vision_used = true",
                cutoff_date
            )

            # Retry distribution
            retry_stats = await conn.fetch(
                """
                SELECT retry_count, COUNT(*) as count
                FROM opencode_execution_log
                WHERE created_at >= $1
                GROUP BY retry_count
                ORDER BY retry_count
                """,
                cutoff_date
            )

            # Status distribution
            status_stats = await conn.fetch(
                """
                SELECT status, COUNT(*) as count
                FROM opencode_execution_log
                WHERE created_at >= $1
                GROUP BY status
                ORDER BY count DESC
                """,
                cutoff_date
            )

        return {
            'total_executions': total or 0,
            'success_rate': (success_count / total * 100) if total else 0,
            'avg_execution_time_ms': float(avg_time or 0),
            'hallucination_check_rate': (hallucination_count / total * 100) if total else 0,
            'vision_usage_rate': (vision_count / total * 100) if total else 0,
            'retry_distribution': [dict(r) for r in retry_stats],
            'status_distribution': [dict(r) for r in status_stats],
            'period_days': days,
        }

    async def get_verification_failures(
        self,
        days: int = 7,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent executions with verification failures.

        Args:
            days: Look back period
            limit: Maximum results

        Returns:
            List of failed verification executions
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, run_id, query, status, verification_checklist,
                       hallucination_check, execution_time_ms, created_at
                FROM opencode_execution_log
                WHERE created_at >= $1
                  AND (
                    status != 'SUCCESS'
                    OR (hallucination_check->>'is_hallucination')::boolean = true
                  )
                ORDER BY created_at DESC
                LIMIT $2
                """,
                cutoff_date, limit
            )

        return [dict(r) for r in rows]


# Singleton instance
_opencode_log_repository: Optional[OpenCodeExecutionLogRepository] = None


async def get_opencode_log_repository() -> OpenCodeExecutionLogRepository:
    """Get or create the OpenCode execution log repository singleton"""
    global _opencode_log_repository
    if _opencode_log_repository is None:
        from ...core.deps import get_postgres_pool
        pool = await get_postgres_pool()
        _opencode_log_repository = OpenCodeExecutionLogRepository(pool)
        await _opencode_log_repository.ensure_table_exists()
    return _opencode_log_repository
