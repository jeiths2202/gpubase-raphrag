"""
Trace Context Management

Provides TraceContext class and span management utilities for E2E message tracing.
"""
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from enum import Enum


class SpanType(str, Enum):
    """Span type enumeration for different operation types"""
    ROOT = "ROOT"
    EMBEDDING = "EMBEDDING"
    RETRIEVAL = "RETRIEVAL"
    GENERATION = "GENERATION"
    STREAMING = "STREAMING"
    CLASSIFICATION = "CLASSIFICATION"


@dataclass
class Span:
    """
    Individual span representing a single operation within a trace.

    Attributes:
        span_id: Unique identifier for this span
        trace_id: Global trace ID this span belongs to
        parent_span_id: Parent span ID (None for root span)
        span_name: Human-readable name for this span
        span_type: Type of operation (ROOT, EMBEDDING, etc.)
        start_time: When the span started
        end_time: When the span ended (None if still running)
        latency_ms: Duration in milliseconds (computed on end)
        status: Status of the span (OK, ERROR, TIMEOUT, CANCELLED)
        error_message: Error message if status is ERROR
        metadata: Additional span-specific data
    """
    span_id: UUID
    trace_id: UUID
    parent_span_id: Optional[UUID]
    span_name: str
    span_type: SpanType
    start_time: datetime
    end_time: Optional[datetime] = None
    latency_ms: Optional[int] = None
    status: str = "OK"
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceContext:
    """
    Trace context for managing the lifecycle of a request trace.

    Maintains a hierarchical structure of spans with parent-child relationships.
    Supports context manager pattern for automatic span lifecycle management.

    Attributes:
        trace_id: Global unique trace identifier
        root_span_id: ID of the root span (represents entire request)
        current_span_id: ID of the currently active span
        span_stack: Stack of span IDs for nested span tracking
        spans: Dictionary of all spans in this trace
    """
    trace_id: UUID
    root_span_id: UUID
    current_span_id: UUID
    span_stack: List[UUID] = field(default_factory=list)
    spans: Dict[UUID, Span] = field(default_factory=dict)

    @classmethod
    def create(cls) -> "TraceContext":
        """
        Create new trace context with root span.

        Returns:
            TraceContext: New trace context with initialized root span
        """
        trace_id = uuid4()
        root_span_id = uuid4()
        root_span = Span(
            span_id=root_span_id,
            trace_id=trace_id,
            parent_span_id=None,
            span_name="request",
            span_type=SpanType.ROOT,
            start_time=datetime.now(timezone.utc)
        )
        return cls(
            trace_id=trace_id,
            root_span_id=root_span_id,
            current_span_id=root_span_id,
            span_stack=[root_span_id],
            spans={root_span_id: root_span}
        )

    @contextmanager
    def create_span(
        self,
        name: str,
        span_type: SpanType,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Context manager for creating and managing child span lifecycle.

        Automatically handles:
        - Span creation with proper parent-child relationship
        - Pushing/popping span stack for nesting
        - Recording start/end times
        - Calculating latency
        - Error handling and status updates

        Args:
            name: Human-readable span name
            span_type: Type of operation (EMBEDDING, RETRIEVAL, etc.)
            metadata: Optional span-specific metadata

        Yields:
            Span: The created span object

        Example:
            with trace_ctx.create_span("embedding", SpanType.EMBEDDING):
                # Embedding operation here
                result = await embed_query(text)
        """
        span_id = uuid4()
        span = Span(
            span_id=span_id,
            trace_id=self.trace_id,
            parent_span_id=self.current_span_id,
            span_name=name,
            span_type=span_type,
            start_time=datetime.now(timezone.utc),
            metadata=metadata or {}
        )

        # Push to stack
        self.span_stack.append(span_id)
        self.spans[span_id] = span
        prev_span_id = self.current_span_id
        self.current_span_id = span_id

        try:
            yield span
        except Exception as e:
            # Record error in span
            span.status = "ERROR"
            span.error_message = str(e)
            raise
        finally:
            # End span
            span.end_time = datetime.now(timezone.utc)
            span.latency_ms = int(
                (span.end_time - span.start_time).total_seconds() * 1000
            )

            # Pop from stack
            self.span_stack.pop()
            self.current_span_id = prev_span_id

    def end_root_span(self):
        """
        End the root span and calculate total latency.

        Should be called when the request is complete, before
        persisting the trace to the database.
        """
        root_span = self.spans[self.root_span_id]
        if root_span.end_time is None:
            root_span.end_time = datetime.now(timezone.utc)
            root_span.latency_ms = int(
                (root_span.end_time - root_span.start_time).total_seconds() * 1000
            )

    def get_all_spans(self) -> List[Span]:
        """
        Get all spans in this trace as a list.

        Returns:
            List[Span]: All spans, ordered by creation time
        """
        return [span for span in self.spans.values()]
