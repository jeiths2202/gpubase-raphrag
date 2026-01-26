"""
Trace Writer Service

Buffered background writes to PostgreSQL using asyncio.
"""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from ...core.logging_framework import AppLogger, LogCategory
from ...core.trace_context import TraceContext, Span
from ..postgres.trace_repository import TraceRepository


class TraceWriter:
    """
    Buffered trace writer with background async writes.

    Uses background task queue for non-blocking persistence.
    Batches writes for efficiency (100 traces or 5 seconds).
    """

    def __init__(
        self,
        repository: TraceRepository,
        batch_size: int = 100,
        batch_timeout_seconds: float = 5.0
    ):
        self.repository = repository
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout_seconds
        self.logger = AppLogger("trace_writer")

        # Internal buffer
        self._trace_buffer: List[Dict[str, Any]] = []
        self._span_buffer: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start background flush timer"""
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
        self.logger.info("TraceWriter started", category=LogCategory.BUSINESS)

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
        self.logger.info("TraceWriter stopped", category=LogCategory.BUSINESS)

    async def submit_trace(
        self,
        trace_data: Dict[str, Any],
        spans: List[Span]
    ):
        """Submit trace and spans to buffer"""
        async with self._lock:
            self._trace_buffer.append(trace_data)
            self._span_buffer.extend([self._span_to_dict(s) for s in spans])

            # Flush if buffer full
            if len(self._trace_buffer) >= self.batch_size:
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
            if not self._trace_buffer:
                return

            traces_to_write = self._trace_buffer[:]
            spans_to_write = self._span_buffer[:]
            self._trace_buffer.clear()
            self._span_buffer.clear()

        # Write to database (async, retry on failure)
        try:
            await self.repository.batch_insert_traces(traces_to_write, spans_to_write)
            self.logger.debug(
                f"Flushed {len(traces_to_write)} traces, {len(spans_to_write)} spans",
                category=LogCategory.DATABASE
            )
        except Exception as e:
            self.logger.error(
                f"Failed to write traces to database: {e}",
                category=LogCategory.ERROR,
                exc_info=True
            )
            # TODO: Dead-letter queue for failed writes

    def _span_to_dict(self, span: Span) -> Dict[str, Any]:
        """Convert Span to dictionary for database"""
        return {
            'span_id': span.span_id,
            'trace_id': span.trace_id,
            'parent_span_id': span.parent_span_id,
            'span_name': span.span_name,
            'span_type': span.span_type.value,
            'start_time': span.start_time,
            'end_time': span.end_time,
            'latency_ms': span.latency_ms,
            'status': span.status,
            'error_message': span.error_message,
            'metadata': span.metadata
        }


# Global singleton
_trace_writer: Optional[TraceWriter] = None


def get_trace_writer() -> TraceWriter:
    """Get global trace writer instance"""
    global _trace_writer
    if _trace_writer is None:
        raise RuntimeError("TraceWriter not initialized. Call initialize_trace_writer() first.")
    return _trace_writer


def initialize_trace_writer(repository: TraceRepository) -> TraceWriter:
    """Initialize global trace writer"""
    global _trace_writer
    _trace_writer = TraceWriter(repository)
    return _trace_writer
