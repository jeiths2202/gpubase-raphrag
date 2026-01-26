"""
Query Log Writer Service

Buffered background writes to PostgreSQL for AI agent query logging.
Similar pattern to TraceWriter for async, non-blocking persistence.
"""
import asyncio
from typing import List, Dict, Any, Optional

from ...core.logging_framework import AppLogger, LogCategory
from ..postgres.query_log_repository import QueryLogRepository


class QueryLogWriter:
    """
    Buffered query log writer with background async writes.

    Uses background task queue for non-blocking persistence.
    Batches writes for efficiency (50 queries or 10 seconds).
    Also updates query aggregates for FAQ generation.
    Auto-syncs FAQ items when eligible queries are detected.
    """

    def __init__(
        self,
        repository: QueryLogRepository,
        batch_size: int = 50,
        batch_timeout_seconds: float = 10.0,
        faq_sync_interval: int = 5  # Sync FAQ every N flushes
    ):
        """
        Initialize query log writer.

        Args:
            repository: QueryLogRepository instance
            batch_size: Number of queries before auto-flush
            batch_timeout_seconds: Seconds before auto-flush
            faq_sync_interval: How often to sync FAQ items (every N flushes)
        """
        self.repository = repository
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout_seconds
        self.faq_sync_interval = faq_sync_interval
        self.logger = AppLogger("query_log_writer")

        # Internal buffer
        self._query_buffer: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._flush_count = 0  # Track flush count for FAQ sync

    async def start(self):
        """Start background flush timer"""
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        self.logger.info("QueryLogWriter started", category=LogCategory.BUSINESS)

    async def stop(self):
        """Stop background flush and flush remaining"""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_buffer()
        self.logger.info("QueryLogWriter stopped", category=LogCategory.BUSINESS)

    async def submit_query(self, query_data: Dict[str, Any]):
        """
        Submit query to buffer for background persistence.

        Args:
            query_data: Dictionary containing query information:
                - user_id: Optional user identifier
                - session_id: Optional session identifier
                - conversation_id: Optional conversation UUID
                - query_text: The actual query text (required)
                - agent_type: Type of agent (required)
                - intent_type: Classified intent type
                - category: Query category
                - language: Query language
                - execution_time_ms: Execution time in milliseconds
                - input_tokens: Number of input tokens
                - output_tokens: Number of output tokens
                - success: Whether the query succeeded
                - response_summary: Summary of the response
        """
        async with self._lock:
            self._query_buffer.append(query_data)

            # Flush if buffer full
            if len(self._query_buffer) >= self.batch_size:
                await self._flush_buffer()

    async def _periodic_flush(self):
        """Periodic flush every N seconds"""
        while self._running:
            try:
                await asyncio.sleep(self.batch_timeout)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    f"Periodic flush failed: {e}",
                    category=LogCategory.ERROR,
                    exc_info=True
                )

    async def _flush_buffer(self):
        """Flush buffer to database"""
        async with self._lock:
            if not self._query_buffer:
                return

            queries_to_write = self._query_buffer[:]
            self._query_buffer.clear()

        # Write to database (async)
        try:
            # Batch insert query logs
            count = await self.repository.batch_insert_query_logs(queries_to_write)

            # Update aggregates for each query
            for query in queries_to_write:
                try:
                    await self.repository.update_or_create_aggregate(
                        query_text=query['query_text'],
                        answer_text=query.get('response_summary'),
                        agent_type=query['agent_type'],
                        intent_type=query.get('intent_type'),
                        category=query.get('category'),
                        user_id=query.get('user_id')
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to update aggregate: {e}",
                        category=LogCategory.DATABASE
                    )

            self.logger.debug(
                f"Flushed {count} queries to database",
                category=LogCategory.DATABASE
            )

            # Increment flush count and sync FAQ if interval reached
            self._flush_count += 1
            if self._flush_count >= self.faq_sync_interval:
                self._flush_count = 0
                await self._sync_faq_items()

        except Exception as e:
            self.logger.error(
                f"Failed to write queries to database: {e}",
                category=LogCategory.ERROR,
                exc_info=True
            )
            # TODO: Dead-letter queue for failed writes

    async def _sync_faq_items(self):
        """
        Sync dynamic FAQ items from eligible query aggregates.

        Creates FAQ entries for queries that have been asked 3+ times.
        This runs periodically to ensure FAQ stays up to date.
        """
        try:
            count = await self.repository.sync_dynamic_faq_items(min_frequency=3)
            if count > 0:
                self.logger.info(
                    f"Auto-synced {count} new FAQ items from popular queries",
                    category=LogCategory.BUSINESS
                )
        except Exception as e:
            self.logger.warning(
                f"Failed to sync FAQ items: {e}",
                category=LogCategory.DATABASE
            )


# Global singleton instance
_query_log_writer: Optional[QueryLogWriter] = None


def get_query_log_writer() -> Optional[QueryLogWriter]:
    """
    Get global query log writer instance.

    Returns:
        QueryLogWriter instance or None if not initialized
    """
    return _query_log_writer


def initialize_query_log_writer(repository: QueryLogRepository) -> QueryLogWriter:
    """
    Initialize global query log writer.

    Args:
        repository: QueryLogRepository instance

    Returns:
        Initialized QueryLogWriter instance
    """
    global _query_log_writer
    _query_log_writer = QueryLogWriter(repository)
    return _query_log_writer


async def start_query_log_writer():
    """Start the global query log writer if initialized"""
    if _query_log_writer:
        await _query_log_writer.start()


async def stop_query_log_writer():
    """Stop the global query log writer if initialized"""
    if _query_log_writer:
        await _query_log_writer.stop()
