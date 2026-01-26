"""
PostgreSQL Trace Repository

Async CRUD operations for traces and trace_spans tables.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from uuid import UUID

import asyncpg
from asyncpg import Pool

from ...core.logging_framework import AppLogger, LogCategory


class TraceRepository:
    """PostgreSQL repository for trace data"""

    def __init__(self, pool: Pool):
        """
        Initialize trace repository.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
        self.logger = AppLogger("trace_repository")

    async def batch_insert_traces(
        self,
        traces: List[Dict[str, Any]],
        spans: List[Dict[str, Any]]
    ):
        """
        Batch insert traces and spans in a transaction.

        Args:
            traces: List of trace data dictionaries
            spans: List of span data dictionaries

        Raises:
            asyncpg.PostgresError: If database operation fails
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Insert traces
                if traces:
                    await conn.executemany(
                        """
                        INSERT INTO traces (
                            trace_id, user_id, session_id, conversation_id,
                            original_prompt, normalized_prompt,
                            model_name, model_version, inference_params,
                            start_time, end_time, total_latency_ms,
                            embedding_latency_ms, retrieval_latency_ms, generation_latency_ms,
                            response_content, response_length,
                            input_tokens, output_tokens, total_tokens,
                            response_quality_flag, error_code, error_message, error_stacktrace,
                            strategy, language, rag_confidence_score, rag_result_count,
                            metadata
                        ) VALUES (
                            $1, $2, $3, $4,
                            $5, $6,
                            $7, $8, $9,
                            $10, $11, $12,
                            $13, $14, $15,
                            $16, $17,
                            $18, $19, $20,
                            $21, $22, $23, $24,
                            $25, $26, $27, $28,
                            $29
                        )
                        ON CONFLICT (trace_id) DO NOTHING
                        """,
                        [
                            (
                                t['trace_id'], t['user_id'], t.get('session_id'), t.get('conversation_id'),
                                t['original_prompt'], t.get('normalized_prompt'),
                                t['model_name'], t.get('model_version'), t.get('inference_params'),
                                t['start_time'], t.get('end_time'), t.get('total_latency_ms'),
                                t.get('embedding_latency_ms'), t.get('retrieval_latency_ms'), t.get('generation_latency_ms'),
                                t.get('response_content'), t.get('response_length'),
                                t.get('input_tokens', 0), t.get('output_tokens', 0), t.get('total_tokens', 0),
                                t.get('response_quality_flag', 'NORMAL'), t.get('error_code'), t.get('error_message'), t.get('error_stacktrace'),
                                t.get('strategy', 'auto'), t.get('language', 'auto'), t.get('rag_confidence_score'), t.get('rag_result_count'),
                                t.get('metadata', {})
                            )
                            for t in traces
                        ]
                    )

                # Insert spans
                if spans:
                    await conn.executemany(
                        """
                        INSERT INTO trace_spans (
                            span_id, trace_id, parent_span_id,
                            span_name, span_type,
                            start_time, end_time, latency_ms,
                            status, error_message, metadata
                        ) VALUES (
                            $1, $2, $3,
                            $4, $5,
                            $6, $7, $8,
                            $9, $10, $11
                        )
                        ON CONFLICT (span_id) DO NOTHING
                        """,
                        [
                            (
                                s['span_id'], s['trace_id'], s.get('parent_span_id'),
                                s['span_name'], s['span_type'],
                                s['start_time'], s.get('end_time'), s.get('latency_ms'),
                                s.get('status', 'OK'), s.get('error_message'), s.get('metadata', {})
                            )
                            for s in spans
                        ]
                    )

    async def get_trace_by_id(self, trace_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get trace with all spans.

        Args:
            trace_id: Trace UUID

        Returns:
            Dictionary with 'trace' and 'spans' keys, or None if not found
        """
        async with self.pool.acquire() as conn:
            # Get trace
            trace_row = await conn.fetchrow(
                "SELECT * FROM traces WHERE trace_id = $1",
                trace_id
            )
            if not trace_row:
                return None

            # Get spans
            span_rows = await conn.fetch(
                """
                SELECT * FROM trace_spans
                WHERE trace_id = $1
                ORDER BY created_at
                """,
                trace_id
            )

            return {
                'trace': dict(trace_row),
                'spans': [dict(row) for row in span_rows]
            }

    async def query_traces(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_latency_ms: Optional[int] = None,
        quality_flag: Optional[str] = None,
        error_code: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Query traces with filters (admin only).

        Args:
            user_id: Filter by user ID
            start_date: Filter by start date (inclusive)
            end_date: Filter by end date (inclusive)
            min_latency_ms: Filter by minimum latency
            quality_flag: Filter by quality flag
            error_code: Filter by error code
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of trace dictionaries
        """
        query = "SELECT * FROM traces WHERE 1=1"
        params = []
        param_idx = 1

        if user_id:
            query += f" AND user_id = ${param_idx}"
            params.append(user_id)
            param_idx += 1

        if start_date:
            query += f" AND created_at >= ${param_idx}"
            params.append(start_date)
            param_idx += 1

        if end_date:
            query += f" AND created_at <= ${param_idx}"
            params.append(end_date)
            param_idx += 1

        if min_latency_ms:
            query += f" AND total_latency_ms >= ${param_idx}"
            params.append(min_latency_ms)
            param_idx += 1

        if quality_flag:
            query += f" AND response_quality_flag = ${param_idx}"
            params.append(quality_flag)
            param_idx += 1

        if error_code:
            query += f" AND error_code = ${param_idx}"
            params.append(error_code)
            param_idx += 1

        query += f" ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_latency_statistics(
        self,
        operation_type: str,  # "embedding", "retrieval", "generation", "total"
        lookback_days: int = 7
    ) -> Dict[str, int]:
        """
        Calculate P50, P95, P99 latencies for operation type.

        Args:
            operation_type: Type of operation to analyze
            lookback_days: Number of days to look back

        Returns:
            Dictionary with p50, p95, p99 latency values in milliseconds
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        if operation_type == "total":
            column = "total_latency_ms"
            table = "traces"
        else:
            column = f"{operation_type}_latency_ms"
            table = "traces"

        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                f"""
                SELECT
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {column}) as p50,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY {column}) as p95,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY {column}) as p99
                FROM {table}
                WHERE created_at >= $1 AND {column} IS NOT NULL
                """,
                cutoff_date
            )

            return {
                'p50': int(result['p50']) if result['p50'] else 0,
                'p95': int(result['p95']) if result['p95'] else 0,
                'p99': int(result['p99']) if result['p99'] else 0
            }
