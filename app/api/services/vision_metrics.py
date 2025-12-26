"""
Vision Metrics and Logging

Comprehensive metrics collection and structured logging for Vision LLM services.
Provides observability, debugging support, and performance insights.
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from collections import defaultdict
import threading
import json

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics collected"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class VisionOperation(str, Enum):
    """Vision operation types for metrics"""
    QUERY = "query"
    ANALYZE_IMAGE = "analyze_image"
    ANALYZE_DOCUMENT = "analyze_document"
    EXTRACT_CHART = "extract_chart"
    EXTRACT_TABLE = "extract_table"
    ROUTE_DECISION = "route_decision"
    CACHE_LOOKUP = "cache_lookup"
    PREPROCESS_IMAGE = "preprocess_image"


@dataclass
class MetricPoint:
    """A single metric data point"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class OperationMetrics:
    """Metrics for a single operation"""
    operation: VisionOperation
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: float = 0.0
    success: bool = True
    error_code: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    image_count: int = 0
    cache_hit: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class VisionMetricsCollector:
    """
    Collects and manages Vision LLM metrics.

    Features:
    1. Operation timing and counting
    2. Success/failure tracking
    3. Token usage monitoring
    4. Cache hit rate tracking
    5. Provider/model breakdown

    Usage:
        metrics = VisionMetricsCollector()

        # Time an operation
        with metrics.measure_operation(VisionOperation.QUERY, provider="openai"):
            result = await process_query()

        # Get metrics summary
        summary = metrics.get_summary()
    """

    def __init__(
        self,
        flush_interval_seconds: int = 60,
        max_history_size: int = 10000,
    ):
        """
        Initialize metrics collector.

        Args:
            flush_interval_seconds: Interval to flush metrics
            max_history_size: Maximum number of records to keep
        """
        self.flush_interval = flush_interval_seconds
        self.max_history_size = max_history_size

        # Metric storage
        self._operations: List[OperationMetrics] = []
        self._counters: Dict[str, int] = defaultdict(int)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = defaultdict(list)

        # Thread safety
        self._lock = threading.Lock()

        # Callbacks for metric export
        self._export_callbacks: List[Callable] = []

    @contextmanager
    def measure_operation(
        self,
        operation: VisionOperation,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **metadata,
    ):
        """
        Context manager to measure an operation.

        Usage:
            with metrics.measure_operation(VisionOperation.QUERY) as op:
                result = await do_query()
                op.input_tokens = 1000
                op.output_tokens = 500
        """
        op_metrics = OperationMetrics(
            operation=operation,
            start_time=datetime.utcnow(),
            provider=provider,
            model=model,
            metadata=metadata,
        )

        start_time = time.time()

        try:
            yield op_metrics
            op_metrics.success = True
        except Exception as e:
            op_metrics.success = False
            op_metrics.error_code = type(e).__name__
            raise
        finally:
            op_metrics.end_time = datetime.utcnow()
            op_metrics.duration_ms = (time.time() - start_time) * 1000
            self._record_operation(op_metrics)

    def record_operation(
        self,
        operation: VisionOperation,
        duration_ms: float,
        success: bool = True,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        image_count: int = 0,
        cache_hit: bool = False,
        error_code: Optional[str] = None,
        **metadata,
    ) -> None:
        """Record an operation manually."""
        op_metrics = OperationMetrics(
            operation=operation,
            start_time=datetime.utcnow() - timedelta(milliseconds=duration_ms),
            end_time=datetime.utcnow(),
            duration_ms=duration_ms,
            success=success,
            error_code=error_code,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_count=image_count,
            cache_hit=cache_hit,
            metadata=metadata,
        )
        self._record_operation(op_metrics)

    def _record_operation(self, op: OperationMetrics) -> None:
        """Internal method to record operation."""
        with self._lock:
            self._operations.append(op)

            # Trim history if needed
            if len(self._operations) > self.max_history_size:
                self._operations = self._operations[-self.max_history_size:]

            # Update counters
            self._counters[f"{op.operation.value}_total"] += 1
            if op.success:
                self._counters[f"{op.operation.value}_success"] += 1
            else:
                self._counters[f"{op.operation.value}_error"] += 1

            if op.cache_hit:
                self._counters["cache_hits"] += 1
            else:
                self._counters["cache_misses"] += 1

            # Update histograms
            self._histograms[f"{op.operation.value}_duration_ms"].append(op.duration_ms)

            # Provider/model specific
            if op.provider:
                self._counters[f"provider_{op.provider}_total"] += 1
            if op.model:
                self._counters[f"model_{op.model}_total"] += 1

            # Token tracking
            self._counters["total_input_tokens"] += op.input_tokens
            self._counters["total_output_tokens"] += op.output_tokens
            self._counters["total_images_processed"] += op.image_count

        # Log the operation
        self._log_operation(op)

    def _log_operation(self, op: OperationMetrics) -> None:
        """Log operation with structured data."""
        log_data = {
            "operation": op.operation.value,
            "duration_ms": round(op.duration_ms, 2),
            "success": op.success,
            "provider": op.provider,
            "model": op.model,
            "input_tokens": op.input_tokens,
            "output_tokens": op.output_tokens,
            "image_count": op.image_count,
            "cache_hit": op.cache_hit,
        }

        if op.error_code:
            log_data["error_code"] = op.error_code

        if op.success:
            logger.info(
                f"Vision operation completed: {op.operation.value}",
                extra={"vision_metrics": log_data},
            )
        else:
            logger.warning(
                f"Vision operation failed: {op.operation.value}",
                extra={"vision_metrics": log_data},
            )

    def increment(self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter."""
        with self._lock:
            key = self._build_key(name, tags)
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        with self._lock:
            key = self._build_key(name, tags)
            self._gauges[key] = value

    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram value."""
        with self._lock:
            key = self._build_key(name, tags)
            self._histograms[key].append(value)
            # Keep last 1000 values
            if len(self._histograms[key]) > 1000:
                self._histograms[key] = self._histograms[key][-1000:]

    def _build_key(self, name: str, tags: Optional[Dict[str, str]]) -> str:
        """Build metric key with tags."""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def get_summary(self, period_minutes: int = 60) -> Dict[str, Any]:
        """Get metrics summary for a time period."""
        cutoff = datetime.utcnow() - timedelta(minutes=period_minutes)

        with self._lock:
            recent_ops = [op for op in self._operations if op.start_time >= cutoff]

        # Calculate summary
        total_ops = len(recent_ops)
        successful_ops = sum(1 for op in recent_ops if op.success)
        failed_ops = total_ops - successful_ops

        # Group by operation type
        by_operation = defaultdict(lambda: {"count": 0, "success": 0, "total_ms": 0})
        for op in recent_ops:
            by_operation[op.operation.value]["count"] += 1
            if op.success:
                by_operation[op.operation.value]["success"] += 1
            by_operation[op.operation.value]["total_ms"] += op.duration_ms

        # Calculate averages
        for key in by_operation:
            count = by_operation[key]["count"]
            if count > 0:
                by_operation[key]["avg_ms"] = by_operation[key]["total_ms"] / count
                by_operation[key]["success_rate"] = by_operation[key]["success"] / count

        # Group by provider
        by_provider = defaultdict(int)
        by_model = defaultdict(int)
        for op in recent_ops:
            if op.provider:
                by_provider[op.provider] += 1
            if op.model:
                by_model[op.model] += 1

        # Token usage
        total_input_tokens = sum(op.input_tokens for op in recent_ops)
        total_output_tokens = sum(op.output_tokens for op in recent_ops)
        total_images = sum(op.image_count for op in recent_ops)

        # Cache stats
        cache_hits = sum(1 for op in recent_ops if op.cache_hit)
        cache_hit_rate = cache_hits / total_ops if total_ops > 0 else 0

        # Latency percentiles
        durations = sorted([op.duration_ms for op in recent_ops])
        n = len(durations)

        return {
            "period_minutes": period_minutes,
            "timestamp": datetime.utcnow().isoformat(),
            "operations": {
                "total": total_ops,
                "successful": successful_ops,
                "failed": failed_ops,
                "success_rate": successful_ops / total_ops if total_ops > 0 else 0,
            },
            "by_operation": dict(by_operation),
            "by_provider": dict(by_provider),
            "by_model": dict(by_model),
            "tokens": {
                "input": total_input_tokens,
                "output": total_output_tokens,
                "total": total_input_tokens + total_output_tokens,
            },
            "images": {
                "total_processed": total_images,
            },
            "cache": {
                "hits": cache_hits,
                "misses": total_ops - cache_hits,
                "hit_rate": cache_hit_rate,
            },
            "latency": {
                "avg_ms": sum(durations) / n if n > 0 else 0,
                "p50_ms": durations[n // 2] if n > 0 else 0,
                "p95_ms": durations[int(n * 0.95)] if n >= 20 else (durations[-1] if n > 0 else 0),
                "p99_ms": durations[int(n * 0.99)] if n >= 100 else (durations[-1] if n > 0 else 0),
            },
        }

    def get_counters(self) -> Dict[str, int]:
        """Get all counter values."""
        with self._lock:
            return dict(self._counters)

    def get_gauges(self) -> Dict[str, float]:
        """Get all gauge values."""
        with self._lock:
            return dict(self._gauges)

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._operations.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


class VisionLogger:
    """
    Structured logger for Vision operations.

    Provides consistent logging format and context management.
    """

    def __init__(self, name: str = "vision"):
        self.logger = logging.getLogger(f"kms.{name}")
        self._context: Dict[str, Any] = {}

    def set_context(self, **kwargs) -> None:
        """Set persistent context for all log messages."""
        self._context.update(kwargs)

    def clear_context(self) -> None:
        """Clear logging context."""
        self._context.clear()

    @contextmanager
    def operation_context(self, operation: str, **kwargs):
        """Context manager for operation-specific logging."""
        old_context = self._context.copy()
        self._context["operation"] = operation
        self._context.update(kwargs)
        try:
            yield
        finally:
            self._context = old_context

    def _format_extra(self, **kwargs) -> Dict[str, Any]:
        """Format extra data for log message."""
        extra = {**self._context, **kwargs}
        return {"vision_log": extra}

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, extra=self._format_extra(**kwargs))

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message, extra=self._format_extra(**kwargs))

    def error(self, message: str, exc_info: bool = False, **kwargs) -> None:
        """Log error message."""
        self.logger.error(message, exc_info=exc_info, extra=self._format_extra(**kwargs))

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message, extra=self._format_extra(**kwargs))

    def log_query(
        self,
        query: str,
        routing_decision: str,
        provider: str,
        model: str,
        duration_ms: float,
        success: bool,
        **kwargs,
    ) -> None:
        """Log a query operation."""
        self.info(
            f"Vision query completed: {routing_decision}",
            query=query[:100],
            provider=provider,
            model=model,
            duration_ms=round(duration_ms, 2),
            success=success,
            **kwargs,
        )

    def log_image_processing(
        self,
        image_count: int,
        total_size_bytes: int,
        duration_ms: float,
        **kwargs,
    ) -> None:
        """Log image processing operation."""
        self.info(
            f"Processed {image_count} images",
            image_count=image_count,
            total_size_mb=round(total_size_bytes / (1024 * 1024), 2),
            duration_ms=round(duration_ms, 2),
            **kwargs,
        )

    def log_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        **kwargs,
    ) -> None:
        """Log cost information."""
        self.info(
            f"API cost: ${cost_usd:.4f}",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            **kwargs,
        )

    def log_cache_hit(self, cache_type: str, key: str, **kwargs) -> None:
        """Log cache hit."""
        self.debug(
            f"Cache hit: {cache_type}",
            cache_type=cache_type,
            cache_key=key[:50],
            **kwargs,
        )

    def log_cache_miss(self, cache_type: str, key: str, **kwargs) -> None:
        """Log cache miss."""
        self.debug(
            f"Cache miss: {cache_type}",
            cache_type=cache_type,
            cache_key=key[:50],
            **kwargs,
        )


# Singleton instances
_metrics: Optional[VisionMetricsCollector] = None
_logger: Optional[VisionLogger] = None


def get_vision_metrics() -> VisionMetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = VisionMetricsCollector()
    return _metrics


def get_vision_logger() -> VisionLogger:
    """Get global vision logger."""
    global _logger
    if _logger is None:
        _logger = VisionLogger()
    return _logger
