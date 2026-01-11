"""
PostgreSQL Query Log Repository

Async CRUD operations for query_log, query_aggregates, and faq_items tables.
"""
import hashlib
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID

import asyncpg
from asyncpg import Pool

from ...core.logging_framework import AppLogger, LogCategory


class QueryLogRepository:
    """PostgreSQL repository for query log and FAQ data"""

    def __init__(self, pool: Pool):
        """
        Initialize query log repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
        self.logger = AppLogger("query_log_repository")

    @staticmethod
    def normalize_query(query: str) -> str:
        """
        Normalize query for grouping similar queries.

        Args:
            query: Original query text

        Returns:
            Normalized query string
        """
        # Lowercase and strip
        normalized = query.lower().strip()
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
        # Remove common filler words (Korean, Japanese, English)
        filler_patterns = [
            r'\b(please|can you|could you|i want to|i need to)\b',
            r'(해주세요|해줘|알려줘|알려주세요|해 주세요)',
            r'(ください|教えて|お願い)',
        ]
        for pattern in filler_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        # Clean up again
        normalized = ' '.join(normalized.split())
        return normalized

    @staticmethod
    def hash_query(normalized: str) -> str:
        """
        Create SHA-256 hash for deduplication.

        Args:
            normalized: Normalized query string

        Returns:
            SHA-256 hash string
        """
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    @staticmethod
    def sanitize_query(query: str) -> str:
        """
        Remove potentially sensitive information from query.

        Args:
            query: Original query text

        Returns:
            Sanitized query string
        """
        # Remove email addresses
        query = re.sub(r'\b[\w.-]+@[\w.-]+\.\w+\b', '[EMAIL]', query)
        # Remove potential user IDs (various formats)
        query = re.sub(r'\b[A-Z]{2,3}[0-9]{5,8}\b', '[USER_ID]', query)
        # Remove potential file paths
        query = re.sub(r'[/\\](?:home|users?|usr)[/\\]\w+', '[PATH]', query, flags=re.IGNORECASE)
        # Remove potential IP addresses
        query = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', query)
        return query

    async def insert_query_log(self, data: Dict[str, Any]) -> UUID:
        """
        Insert a new query log entry.

        Args:
            data: Query log data dictionary

        Returns:
            UUID of the inserted record
        """
        normalized = self.normalize_query(data['query_text'])
        query_hash = self.hash_query(normalized)
        sanitized = self.sanitize_query(data['query_text'])

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO query_log (
                    user_id, session_id, conversation_id,
                    query_text, query_normalized, query_hash,
                    agent_type, intent_type, category, language,
                    execution_time_ms, input_tokens, output_tokens,
                    success, response_summary, is_public
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                RETURNING id
                """,
                data.get('user_id'),
                data.get('session_id'),
                data.get('conversation_id'),
                sanitized,
                normalized,
                query_hash,
                data['agent_type'],
                data.get('intent_type'),
                data.get('category'),
                data.get('language', 'auto'),
                data.get('execution_time_ms'),
                data.get('input_tokens', 0),
                data.get('output_tokens', 0),
                data.get('success', True),
                data.get('response_summary'),
                True  # is_public default to True for auto FAQ
            )
            return row['id']

    async def batch_insert_query_logs(self, queries: List[Dict[str, Any]]) -> int:
        """
        Batch insert multiple query log entries.

        Args:
            queries: List of query log data dictionaries

        Returns:
            Number of inserted records
        """
        if not queries:
            return 0

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                records = []
                for data in queries:
                    normalized = self.normalize_query(data['query_text'])
                    query_hash = self.hash_query(normalized)
                    sanitized = self.sanitize_query(data['query_text'])
                    records.append((
                        data.get('user_id'),
                        data.get('session_id'),
                        data.get('conversation_id'),
                        sanitized,
                        normalized,
                        query_hash,
                        data['agent_type'],
                        data.get('intent_type'),
                        data.get('category'),
                        data.get('language', 'auto'),
                        data.get('execution_time_ms'),
                        data.get('input_tokens', 0),
                        data.get('output_tokens', 0),
                        data.get('success', True),
                        data.get('response_summary'),
                        True
                    ))

                await conn.executemany(
                    """
                    INSERT INTO query_log (
                        user_id, session_id, conversation_id,
                        query_text, query_normalized, query_hash,
                        agent_type, intent_type, category, language,
                        execution_time_ms, input_tokens, output_tokens,
                        success, response_summary, is_public
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    """,
                    records
                )
                return len(records)

    async def update_or_create_aggregate(
        self,
        query_text: str,
        answer_text: Optional[str],
        agent_type: str,
        intent_type: Optional[str] = None,
        category: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> UUID:
        """
        Update aggregate statistics or create new entry (UPSERT).

        Args:
            query_text: Original query text
            answer_text: Response text for representative answer
            agent_type: Type of agent that handled the query
            intent_type: Classified intent type
            category: Query category
            user_id: User ID for unique user tracking

        Returns:
            UUID of the aggregate record
        """
        normalized = self.normalize_query(query_text)
        query_hash = self.hash_query(normalized)
        sanitized = self.sanitize_query(query_text)

        async with self.pool.acquire() as conn:
            # Use UPSERT to handle both insert and update
            row = await conn.fetchrow(
                """
                INSERT INTO query_aggregates (
                    query_normalized, query_hash,
                    representative_query, representative_answer,
                    frequency_count, last_asked_at, first_asked_at,
                    unique_users_count,
                    agent_type, intent_type, category
                ) VALUES ($1, $2, $3, $4, 1, NOW(), NOW(), 1, $5, $6, $7)
                ON CONFLICT (query_hash) DO UPDATE SET
                    frequency_count = query_aggregates.frequency_count + 1,
                    last_asked_at = NOW(),
                    unique_users_count = CASE
                        WHEN $8::VARCHAR IS NOT NULL AND NOT EXISTS (
                            SELECT 1 FROM query_log
                            WHERE query_hash = $2 AND user_id = $8
                        ) THEN query_aggregates.unique_users_count + 1
                        ELSE query_aggregates.unique_users_count
                    END,
                    -- Update representative answer if new one is longer/better
                    representative_answer = CASE
                        WHEN $4 IS NOT NULL AND (
                            query_aggregates.representative_answer IS NULL
                            OR LENGTH($4) > LENGTH(query_aggregates.representative_answer)
                        ) THEN $4
                        ELSE query_aggregates.representative_answer
                    END,
                    updated_at = NOW()
                RETURNING id
                """,
                normalized,
                query_hash,
                sanitized,
                answer_text[:2000] if answer_text else None,
                agent_type,
                intent_type,
                category,
                user_id
            )
            return row['id']

    async def get_popular_queries(
        self,
        limit: int = 20,
        offset: int = 0,
        category: Optional[str] = None,
        agent_type: Optional[str] = None,
        min_frequency: int = 3,
        days: int = 30
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get popular queries sorted by popularity score.

        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            category: Filter by category
            agent_type: Filter by agent type
            min_frequency: Minimum frequency threshold
            days: Look back period in days

        Returns:
            Tuple of (list of query aggregates, total count)
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        where_clauses = ["last_asked_at >= $1", "frequency_count >= $2"]
        params: List[Any] = [cutoff_date, min_frequency]

        if category:
            where_clauses.append(f"category = ${len(params) + 1}")
            params.append(category)

        if agent_type:
            where_clauses.append(f"agent_type = ${len(params) + 1}")
            params.append(agent_type)

        where_sql = " AND ".join(where_clauses)

        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM query_aggregates WHERE {where_sql}",
                *params
            )

            rows = await conn.fetch(
                f"""
                SELECT
                    id, query_normalized, representative_query, representative_answer,
                    frequency_count, last_asked_at, first_asked_at, unique_users_count,
                    agent_type, intent_type, category,
                    popularity_score, is_faq_eligible
                FROM query_aggregates
                WHERE {where_sql}
                ORDER BY popularity_score DESC, frequency_count DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params, limit, offset
            )

        return [dict(r) for r in rows], total

    async def get_faq_items(
        self,
        language: str = "en",
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        include_dynamic: bool = True
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get FAQ items for display.

        Args:
            language: Language code (en, ko, ja)
            category: Filter by category (None or 'all' for all)
            limit: Maximum number of results
            offset: Offset for pagination
            include_dynamic: Include dynamic FAQ items from popular queries

        Returns:
            Tuple of (list of FAQ items, total count)
        """
        # Determine language columns
        lang_suffix = language if language in ['en', 'ko', 'ja'] else 'en'
        question_col = f"question_{lang_suffix}"
        answer_col = f"answer_{lang_suffix}"

        where_clauses = ["is_active = true"]
        params: List[Any] = []

        if category and category != 'all':
            where_clauses.append(f"category = ${len(params) + 1}")
            params.append(category)

        if not include_dynamic:
            where_clauses.append("source_type != 'dynamic'")

        where_sql = " AND ".join(where_clauses)

        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM faq_items WHERE {where_sql}",
                *params
            )

            rows = await conn.fetch(
                f"""
                SELECT
                    id, source_type, query_aggregate_id, category, tags,
                    {question_col} as question,
                    {answer_col} as answer,
                    view_count, helpful_count, not_helpful_count,
                    is_pinned, display_order, created_at
                FROM faq_items
                WHERE {where_sql}
                ORDER BY is_pinned DESC, display_order ASC, view_count DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params, limit, offset
            )

        return [dict(r) for r in rows], total

    async def get_faq_categories(self) -> List[Dict[str, Any]]:
        """
        Get FAQ categories with counts.

        Returns:
            List of categories with counts
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT category, COUNT(*) as count
                FROM faq_items
                WHERE is_active = true
                GROUP BY category
                ORDER BY count DESC
                """
            )

        # Add 'all' category with total count
        total = sum(r['count'] for r in rows)
        categories = [{'id': 'all', 'name': 'All', 'count': total}]
        categories.extend([
            {'id': r['category'], 'name': r['category'], 'count': r['count']}
            for r in rows
        ])
        return categories

    async def increment_faq_view(self, faq_id: UUID) -> None:
        """
        Increment view count for FAQ item.

        Args:
            faq_id: FAQ item UUID
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE faq_items SET view_count = view_count + 1 WHERE id = $1",
                faq_id
            )

    async def record_faq_feedback(
        self,
        faq_id: UUID,
        is_helpful: bool
    ) -> None:
        """
        Record feedback for FAQ item.

        Args:
            faq_id: FAQ item UUID
            is_helpful: Whether the answer was helpful
        """
        column = "helpful_count" if is_helpful else "not_helpful_count"
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE faq_items SET {column} = {column} + 1 WHERE id = $1",
                faq_id
            )

    async def create_faq_item(self, data: Dict[str, Any]) -> UUID:
        """
        Create a new FAQ item.

        Args:
            data: FAQ item data

        Returns:
            UUID of the created item
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO faq_items (
                    source_type, query_aggregate_id,
                    question_en, question_ko, question_ja,
                    answer_en, answer_ko, answer_ja,
                    category, tags, display_order, is_active, is_pinned
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id
                """,
                data.get('source_type', 'curated'),
                data.get('query_aggregate_id'),
                data.get('question_en'),
                data.get('question_ko'),
                data.get('question_ja'),
                data.get('answer_en'),
                data.get('answer_ko'),
                data.get('answer_ja'),
                data['category'],
                json.dumps(data.get('tags', [])),
                data.get('display_order', 0),
                data.get('is_active', True),
                data.get('is_pinned', False)
            )
            return row['id']

    async def sync_dynamic_faq_items(self, min_frequency: int = 3) -> int:
        """
        Sync dynamic FAQ items from eligible query aggregates.

        Creates FAQ items from popular queries that are FAQ eligible.

        Args:
            min_frequency: Minimum frequency for eligibility

        Returns:
            Number of new FAQ items created
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Get eligible aggregates not yet in FAQ
                rows = await conn.fetch(
                    """
                    SELECT qa.id, qa.representative_query, qa.representative_answer,
                           qa.category, qa.agent_type
                    FROM query_aggregates qa
                    WHERE qa.is_faq_eligible = true
                      AND qa.frequency_count >= $1
                      AND NOT EXISTS (
                          SELECT 1 FROM faq_items fi
                          WHERE fi.query_aggregate_id = qa.id
                      )
                    ORDER BY qa.popularity_score DESC
                    LIMIT 50
                    """,
                    min_frequency
                )

                if not rows:
                    return 0

                # Create FAQ items
                count = 0
                for row in rows:
                    await conn.execute(
                        """
                        INSERT INTO faq_items (
                            source_type, query_aggregate_id,
                            question_ko, answer_ko,
                            category, is_active
                        ) VALUES ('dynamic', $1, $2, $3, $4, true)
                        """,
                        row['id'],
                        row['representative_query'],
                        row['representative_answer'] or 'Answer pending...',
                        row['category'] or row['agent_type'] or 'general'
                    )
                    count += 1

                return count

    async def get_query_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get query statistics for admin dashboard.

        Args:
            days: Look back period

        Returns:
            Statistics dictionary
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        async with self.pool.acquire() as conn:
            # Total queries
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM query_log WHERE created_at >= $1",
                cutoff_date
            )

            # Unique users
            unique_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id) FROM query_log
                WHERE created_at >= $1 AND user_id IS NOT NULL
                """,
                cutoff_date
            )

            # Average execution time
            avg_time = await conn.fetchval(
                """
                SELECT AVG(execution_time_ms) FROM query_log
                WHERE created_at >= $1 AND execution_time_ms IS NOT NULL
                """,
                cutoff_date
            )

            # Success rate
            success_count = await conn.fetchval(
                "SELECT COUNT(*) FROM query_log WHERE created_at >= $1 AND success = true",
                cutoff_date
            )

            # Top categories
            top_categories = await conn.fetch(
                """
                SELECT category, COUNT(*) as count
                FROM query_log
                WHERE created_at >= $1 AND category IS NOT NULL
                GROUP BY category
                ORDER BY count DESC
                LIMIT 10
                """,
                cutoff_date
            )

            # Top agent types
            top_agents = await conn.fetch(
                """
                SELECT agent_type, COUNT(*) as count
                FROM query_log
                WHERE created_at >= $1
                GROUP BY agent_type
                ORDER BY count DESC
                """,
                cutoff_date
            )

        return {
            'total_queries': total or 0,
            'unique_users': unique_users or 0,
            'avg_execution_time_ms': float(avg_time or 0),
            'success_rate': (success_count / total * 100) if total else 0,
            'top_categories': [dict(r) for r in top_categories],
            'top_agent_types': [dict(r) for r in top_agents],
            'period_days': days
        }
