"""
Prometheus-Compatible Metrics
Counters, Gauges, Histograms for observability.
"""
import time
import threading
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Tuple
from enum import Enum
from collections import defaultdict
from contextlib import contextmanager, asynccontextmanager
import logging
import json

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Prometheus metric types"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricLabel:
    """Label for metric dimensions"""
    name: str
    value: str


class Counter:
    """
    Prometheus-style counter metric.
    Monotonically increasing value.

    Example:
        requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"]
        )
        requests_total.inc(method="GET", endpoint="/api/query", status="200")
    """

    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None
    ):
        self.name = name
        self.description = description
        self.labels = labels or []
        self._values: Dict[Tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0, **labels):
        """Increment counter"""
        if value < 0:
            raise ValueError("Counter can only be incremented")

        label_key = self._make_label_key(labels)
        with self._lock:
            self._values[label_key] += value

    def get(self, **labels) -> float:
        """Get counter value"""
        label_key = self._make_label_key(labels)
        with self._lock:
            return self._values.get(label_key, 0.0)

    def _make_label_key(self, labels: Dict[str, str]) -> Tuple:
        """Create hashable label key"""
        return tuple(sorted(labels.items()))

    def collect(self) -> List[Dict[str, Any]]:
        """Collect all values for export"""
        with self._lock:
            return [
                {
                    "name": self.name,
                    "type": MetricType.COUNTER.value,
                    "description": self.description,
                    "labels": dict(label_key),
                    "value": value
                }
                for label_key, value in self._values.items()
            ]


class Gauge:
    """
    Prometheus-style gauge metric.
    Value that can go up or down.

    Example:
        active_sessions = Gauge(
            "active_sessions",
            "Number of active sessions"
        )
        active_sessions.set(100)
        active_sessions.inc()
        active_sessions.dec()
    """

    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None
    ):
        self.name = name
        self.description = description
        self.labels = labels or []
        self._values: Dict[Tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels):
        """Set gauge value"""
        label_key = self._make_label_key(labels)
        with self._lock:
            self._values[label_key] = value

    def inc(self, value: float = 1.0, **labels):
        """Increment gauge"""
        label_key = self._make_label_key(labels)
        with self._lock:
            self._values[label_key] += value

    def dec(self, value: float = 1.0, **labels):
        """Decrement gauge"""
        label_key = self._make_label_key(labels)
        with self._lock:
            self._values[label_key] -= value

    def get(self, **labels) -> float:
        """Get gauge value"""
        label_key = self._make_label_key(labels)
        with self._lock:
            return self._values.get(label_key, 0.0)

    def _make_label_key(self, labels: Dict[str, str]) -> Tuple:
        return tuple(sorted(labels.items()))

    def collect(self) -> List[Dict[str, Any]]:
        """Collect all values for export"""
        with self._lock:
            return [
                {
                    "name": self.name,
                    "type": MetricType.GAUGE.value,
                    "description": self.description,
                    "labels": dict(label_key),
                    "value": value
                }
                for label_key, value in self._values.items()
            ]


class Histogram:
    """
    Prometheus-style histogram metric.
    Tracks distribution of values in buckets.

    Example:
        request_duration = Histogram(
            "http_request_duration_seconds",
            "Request duration in seconds",
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        )
        request_duration.observe(0.25)
    """

    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None
    ):
        self.name = name
        self.description = description
        self.labels = labels or []
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)

        # Per-label-key: bucket counts, sum, count
        self._bucket_counts: Dict[Tuple, Dict[float, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._sums: Dict[Tuple, float] = defaultdict(float)
        self._counts: Dict[Tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels):
        """Observe a value"""
        label_key = self._make_label_key(labels)

        with self._lock:
            # Increment buckets
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[label_key][bucket] += 1

            # Increment +Inf bucket
            self._bucket_counts[label_key][float('inf')] += 1

            # Update sum and count
            self._sums[label_key] += value
            self._counts[label_key] += 1

    @contextmanager
    def time(self, **labels):
        """Context manager to time operations"""
        start = time.time()
        yield
        self.observe(time.time() - start, **labels)

    @asynccontextmanager
    async def async_time(self, **labels):
        """Async context manager to time operations"""
        start = time.time()
        yield
        self.observe(time.time() - start, **labels)

    def _make_label_key(self, labels: Dict[str, str]) -> Tuple:
        return tuple(sorted(labels.items()))

    def get_percentile(self, percentile: float, **labels) -> float:
        """Estimate percentile from histogram (approximate)"""
        label_key = self._make_label_key(labels)

        with self._lock:
            total = self._counts.get(label_key, 0)
            if total == 0:
                return 0.0

            target = total * (percentile / 100.0)
            cumulative = 0

            bucket_counts = self._bucket_counts.get(label_key, {})
            prev_bucket = 0.0

            for bucket in self.buckets:
                count = bucket_counts.get(bucket, 0)
                if cumulative + count >= target:
                    # Linear interpolation
                    fraction = (target - cumulative) / max(count, 1)
                    return prev_bucket + (bucket - prev_bucket) * fraction
                cumulative += count
                prev_bucket = bucket

            return self.buckets[-1] if self.buckets else 0.0

    def collect(self) -> List[Dict[str, Any]]:
        """Collect all values for export"""
        with self._lock:
            results = []
            for label_key in self._counts.keys():
                bucket_values = {}
                cumulative = 0
                for bucket in self.buckets:
                    cumulative += self._bucket_counts[label_key].get(bucket, 0)
                    bucket_values[str(bucket)] = cumulative

                # Add +Inf
                bucket_values["+Inf"] = self._counts[label_key]

                results.append({
                    "name": self.name,
                    "type": MetricType.HISTOGRAM.value,
                    "description": self.description,
                    "labels": dict(label_key),
                    "buckets": bucket_values,
                    "sum": self._sums[label_key],
                    "count": self._counts[label_key]
                })
            return results


class MetricsRegistry:
    """
    Central registry for all metrics.

    Example:
        registry = MetricsRegistry.get_instance()

        # Register metrics
        registry.counter("requests_total", "Total requests")
        registry.histogram("request_duration", "Request duration")

        # Use metrics
        registry.get("requests_total").inc()

        # Export
        prometheus_text = registry.export_prometheus()
    """

    _instance: Optional["MetricsRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._metrics: Dict[str, Any] = {}
                    cls._instance._collectors: List[Callable] = []
        return cls._instance

    def counter(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None
    ) -> Counter:
        """Create and register a counter"""
        if name not in self._metrics:
            self._metrics[name] = Counter(name, description, labels)
        return self._metrics[name]

    def gauge(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None
    ) -> Gauge:
        """Create and register a gauge"""
        if name not in self._metrics:
            self._metrics[name] = Gauge(name, description, labels)
        return self._metrics[name]

    def histogram(
        self,
        name: str,
        description: str,
        labels: Optional[List[str]] = None,
        buckets: Optional[List[float]] = None
    ) -> Histogram:
        """Create and register a histogram"""
        if name not in self._metrics:
            self._metrics[name] = Histogram(name, description, labels, buckets)
        return self._metrics[name]

    def get(self, name: str) -> Optional[Any]:
        """Get metric by name"""
        return self._metrics.get(name)

    def register_collector(self, collector: Callable[[], List[Dict[str, Any]]]):
        """Register external collector function"""
        self._collectors.append(collector)

    def collect_all(self) -> List[Dict[str, Any]]:
        """Collect all metrics"""
        results = []

        # Collect from registered metrics
        for metric in self._metrics.values():
            results.extend(metric.collect())

        # Collect from external collectors
        for collector in self._collectors:
            try:
                results.extend(collector())
            except Exception as e:
                logger.error(f"Collector error: {e}")

        return results

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format"""
        lines = []
        metrics = self.collect_all()

        # Group by name
        by_name: Dict[str, List[Dict]] = defaultdict(list)
        for m in metrics:
            by_name[m["name"]].append(m)

        for name, samples in by_name.items():
            if not samples:
                continue

            # HELP and TYPE
            first = samples[0]
            lines.append(f"# HELP {name} {first.get('description', '')}")
            lines.append(f"# TYPE {name} {first['type']}")

            for sample in samples:
                labels = sample.get("labels", {})
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())

                if sample["type"] == MetricType.HISTOGRAM.value:
                    # Histogram format
                    for bucket, count in sample.get("buckets", {}).items():
                        bucket_labels = f'{label_str},le="{bucket}"' if label_str else f'le="{bucket}"'
                        lines.append(f"{name}_bucket{{{bucket_labels}}} {count}")
                    sum_labels = f"{{{label_str}}}" if label_str else ""
                    lines.append(f"{name}_sum{sum_labels} {sample.get('sum', 0)}")
                    lines.append(f"{name}_count{sum_labels} {sample.get('count', 0)}")
                else:
                    # Counter/Gauge format
                    label_part = f"{{{label_str}}}" if label_str else ""
                    lines.append(f"{name}{label_part} {sample['value']}")

        return "\n".join(lines)

    def export_json(self) -> str:
        """Export metrics as JSON"""
        return json.dumps(self.collect_all(), indent=2, default=str)

    @classmethod
    def get_instance(cls) -> "MetricsRegistry":
        """Get singleton instance"""
        return cls()

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)"""
        with cls._lock:
            cls._instance = None


# ==================== Pre-defined Metrics ====================

def get_metrics_registry() -> MetricsRegistry:
    """Get the global metrics registry"""
    return MetricsRegistry.get_instance()


def init_default_metrics() -> MetricsRegistry:
    """Initialize default application metrics"""
    registry = get_metrics_registry()

    # HTTP metrics
    registry.counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"]
    )
    registry.histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    # RAG metrics
    registry.counter(
        "rag_queries_total",
        "Total RAG queries",
        ["status", "source"]
    )
    registry.histogram(
        "rag_query_duration_seconds",
        "RAG query duration in seconds",
        ["stage"],  # embedding, retrieval, generation
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
    )
    registry.gauge(
        "rag_context_tokens",
        "Tokens in RAG context",
        ["query_type"]
    )

    # Document metrics
    registry.counter(
        "documents_processed_total",
        "Total documents processed",
        ["status", "type"]
    )
    registry.gauge(
        "documents_active",
        "Active documents in system",
        ["source"]
    )

    # Session metrics
    registry.gauge(
        "sessions_active",
        "Active sessions"
    )
    registry.gauge(
        "session_documents_count",
        "Documents per session",
        ["session_id"]
    )

    # Cache metrics
    registry.counter(
        "cache_hits_total",
        "Cache hit count",
        ["cache_name"]
    )
    registry.counter(
        "cache_misses_total",
        "Cache miss count",
        ["cache_name"]
    )
    registry.gauge(
        "cache_size_bytes",
        "Cache size in bytes",
        ["cache_name"]
    )

    # Circuit breaker metrics
    registry.gauge(
        "circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=half-open, 2=open)",
        ["name"]
    )
    registry.counter(
        "circuit_breaker_trips_total",
        "Circuit breaker trip count",
        ["name"]
    )

    # LLM metrics
    registry.counter(
        "llm_requests_total",
        "Total LLM API requests",
        ["model", "status"]
    )
    registry.histogram(
        "llm_request_duration_seconds",
        "LLM request duration",
        ["model"],
        buckets=[1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
    )
    registry.counter(
        "llm_tokens_total",
        "Total LLM tokens",
        ["model", "type"]  # type: prompt, completion
    )

    # Embedding metrics
    registry.counter(
        "embeddings_generated_total",
        "Total embeddings generated",
        ["status"]
    )
    registry.histogram(
        "embedding_batch_size",
        "Embedding batch sizes",
        buckets=[1, 5, 10, 25, 50, 100]
    )

    return registry


# Initialize on import
_default_registry = init_default_metrics()
