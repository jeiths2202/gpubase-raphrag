"""
Vision Health Monitor

Monitors the health and performance of Vision LLM services.
Provides real-time status, alerts, and performance metrics.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import threading
from collections import deque

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """Component types being monitored"""
    OPENAI_VISION = "openai_vision"
    ANTHROPIC_VISION = "anthropic_vision"
    IMAGE_PREPROCESSOR = "image_preprocessor"
    VISION_CACHE = "vision_cache"
    VISION_ROUTER = "vision_router"
    DOCUMENT_ANALYZER = "document_analyzer"


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    component: ComponentType
    status: HealthStatus
    latency_ms: float
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Performance metrics for a component"""
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    error_rate: float = 0.0
    requests_per_minute: float = 0.0
    success_count: int = 0
    error_count: int = 0


@dataclass
class ComponentHealth:
    """Health state of a component"""
    component: ComponentType
    status: HealthStatus
    last_check: datetime
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    metrics: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    recent_latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    recent_errors: List[str] = field(default_factory=list)


class VisionHealthMonitor:
    """
    Monitors health of Vision LLM services.

    Features:
    1. Periodic health checks for all components
    2. Performance metrics tracking
    3. Alerting on degradation
    4. Circuit breaker pattern support

    Usage:
        monitor = VisionHealthMonitor()
        monitor.start_monitoring()

        # Get current health
        health = monitor.get_health_summary()

        # Check specific component
        status = monitor.get_component_health(ComponentType.OPENAI_VISION)
    """

    # Health check thresholds
    LATENCY_WARNING_MS = 5000
    LATENCY_CRITICAL_MS = 15000
    ERROR_RATE_WARNING = 0.05  # 5%
    ERROR_RATE_CRITICAL = 0.20  # 20%
    CONSECUTIVE_FAILURES_UNHEALTHY = 3

    def __init__(
        self,
        check_interval_seconds: int = 60,
        enable_alerts: bool = True,
        alert_callback: Optional[Callable] = None,
    ):
        """
        Initialize health monitor.

        Args:
            check_interval_seconds: Interval between health checks
            enable_alerts: Enable health alerts
            alert_callback: Callback for alerts
        """
        self.check_interval = check_interval_seconds
        self.enable_alerts = enable_alerts
        self.alert_callback = alert_callback

        # Component health states
        self._component_health: Dict[ComponentType, ComponentHealth] = {}
        for component in ComponentType:
            self._component_health[component] = ComponentHealth(
                component=component,
                status=HealthStatus.UNKNOWN,
                last_check=datetime.now(timezone.utc),
            )

        # Monitoring state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

        # Alert tracking
        self._last_alert_status: Dict[ComponentType, HealthStatus] = {}

    async def start_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Vision health monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Vision health monitoring stopped")

    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await self.run_health_checks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(self.check_interval)

    async def run_health_checks(self) -> Dict[ComponentType, HealthCheckResult]:
        """Run health checks for all components."""
        results = {}

        # Run checks in parallel
        checks = [
            self._check_openai_vision(),
            self._check_anthropic_vision(),
            self._check_image_preprocessor(),
            self._check_vision_cache(),
            self._check_vision_router(),
            self._check_document_analyzer(),
        ]

        completed = await asyncio.gather(*checks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Health check exception: {result}")
                continue
            if isinstance(result, HealthCheckResult):
                results[result.component] = result
                self._update_component_health(result)

        # Check for alerts
        if self.enable_alerts:
            self._check_alerts()

        return results

    async def _check_openai_vision(self) -> HealthCheckResult:
        """Check OpenAI Vision API health."""
        component = ComponentType.OPENAI_VISION
        start = time.time()

        try:
            from app.api.services.vision_llm_factory import get_vision_llm_factory

            factory = get_vision_llm_factory()

            # Try to get provider info (doesn't make API call)
            providers = factory.get_supported_providers()
            openai_info = providers.get("openai", {})

            latency = (time.time() - start) * 1000

            if openai_info.get("requires_api_key"):
                # Check if API key is configured
                from app.api.core.settings import get_settings
                settings = get_settings()

                if not settings.vision.api_key:
                    return HealthCheckResult(
                        component=component,
                        status=HealthStatus.DEGRADED,
                        latency_ms=latency,
                        message="OpenAI API key not configured",
                    )

            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="OpenAI Vision available",
                details={"models": openai_info.get("models", [])},
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"OpenAI Vision check failed: {str(e)}",
            )

    async def _check_anthropic_vision(self) -> HealthCheckResult:
        """Check Anthropic Vision API health."""
        component = ComponentType.ANTHROPIC_VISION
        start = time.time()

        try:
            from app.api.services.vision_llm_factory import get_vision_llm_factory

            factory = get_vision_llm_factory()
            providers = factory.get_supported_providers()
            anthropic_info = providers.get("anthropic", {})

            latency = (time.time() - start) * 1000

            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Anthropic Vision available",
                details={"models": anthropic_info.get("models", [])},
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Anthropic Vision check failed: {str(e)}",
            )

    async def _check_image_preprocessor(self) -> HealthCheckResult:
        """Check image preprocessor health."""
        component = ComponentType.IMAGE_PREPROCESSOR
        start = time.time()

        try:
            from app.api.services.image_preprocessor import ImagePreprocessor

            preprocessor = ImagePreprocessor()
            # Check if PIL is available
            config = preprocessor.get_config()

            latency = (time.time() - start) * 1000

            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Image preprocessor ready",
                details=config,
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Image preprocessor check failed: {str(e)}",
            )

    async def _check_vision_cache(self) -> HealthCheckResult:
        """Check vision cache health."""
        component = ComponentType.VISION_CACHE
        start = time.time()

        try:
            from app.api.services.vision_cache import get_vision_cache

            cache = get_vision_cache()
            stats = cache.get_stats()

            latency = (time.time() - start) * 1000

            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Vision cache operational",
                details=stats,
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"Vision cache check failed: {str(e)}",
            )

    async def _check_vision_router(self) -> HealthCheckResult:
        """Check vision router health."""
        component = ComponentType.VISION_ROUTER
        start = time.time()

        try:
            from app.api.services.enhanced_query_router import EnhancedQueryRouter

            router = EnhancedQueryRouter()
            config = router.get_routing_config()

            latency = (time.time() - start) * 1000

            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Vision router ready",
                details=config,
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=f"Vision router check failed: {str(e)}",
            )

    async def _check_document_analyzer(self) -> HealthCheckResult:
        """Check document analyzer health."""
        component = ComponentType.DOCUMENT_ANALYZER
        start = time.time()

        try:
            from app.api.services.document_analyzer import DocumentAnalyzer

            analyzer = DocumentAnalyzer()
            supported = analyzer.get_supported_types()

            latency = (time.time() - start) * 1000

            return HealthCheckResult(
                component=component,
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Document analyzer ready",
                details={"supported_types": supported},
            )

        except Exception as e:
            latency = (time.time() - start) * 1000
            return HealthCheckResult(
                component=component,
                status=HealthStatus.DEGRADED,
                latency_ms=latency,
                message=f"Document analyzer check failed: {str(e)}",
            )

    def _update_component_health(self, result: HealthCheckResult) -> None:
        """Update component health state from check result."""
        with self._lock:
            health = self._component_health[result.component]
            health.last_check = result.timestamp
            health.status = result.status

            # Update latency tracking
            health.recent_latencies.append(result.latency_ms)

            if result.status == HealthStatus.HEALTHY:
                health.last_success = result.timestamp
                health.consecutive_failures = 0
            else:
                health.last_failure = result.timestamp
                health.consecutive_failures += 1
                health.recent_errors.append(result.message)
                # Keep only last 10 errors
                health.recent_errors = health.recent_errors[-10:]

            # Update metrics
            self._update_metrics(health)

    def _update_metrics(self, health: ComponentHealth) -> None:
        """Update performance metrics for a component."""
        if not health.recent_latencies:
            return

        latencies = sorted(health.recent_latencies)
        n = len(latencies)

        health.metrics.avg_latency_ms = sum(latencies) / n
        health.metrics.p50_latency_ms = latencies[n // 2]
        health.metrics.p95_latency_ms = latencies[int(n * 0.95)] if n >= 20 else latencies[-1]
        health.metrics.p99_latency_ms = latencies[int(n * 0.99)] if n >= 100 else latencies[-1]

        total = health.metrics.success_count + health.metrics.error_count
        if total > 0:
            health.metrics.error_rate = health.metrics.error_count / total

    def _check_alerts(self) -> None:
        """Check for health alerts."""
        for component, health in self._component_health.items():
            last_status = self._last_alert_status.get(component, HealthStatus.UNKNOWN)

            # Alert on status change
            if health.status != last_status:
                if health.status in [HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]:
                    self._send_alert(
                        component,
                        health.status,
                        f"{component.value} is {health.status.value}",
                        health,
                    )

                self._last_alert_status[component] = health.status

    def _send_alert(
        self,
        component: ComponentType,
        status: HealthStatus,
        message: str,
        health: ComponentHealth,
    ) -> None:
        """Send health alert."""
        logger.warning(f"Health Alert: {message}")

        if self.alert_callback:
            try:
                self.alert_callback(
                    component=component,
                    status=status,
                    message=message,
                    metrics=health.metrics,
                )
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary."""
        with self._lock:
            components = {}
            overall_status = HealthStatus.HEALTHY

            for component, health in self._component_health.items():
                components[component.value] = {
                    "status": health.status.value,
                    "last_check": health.last_check.isoformat(),
                    "latency_ms": health.metrics.avg_latency_ms,
                    "consecutive_failures": health.consecutive_failures,
                }

                # Determine overall status
                if health.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif health.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED

            return {
                "status": overall_status.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "components": components,
            }

    def get_component_health(self, component: ComponentType) -> Dict[str, Any]:
        """Get detailed health for a specific component."""
        with self._lock:
            health = self._component_health.get(component)
            if not health:
                return {"error": "Component not found"}

            return {
                "component": component.value,
                "status": health.status.value,
                "last_check": health.last_check.isoformat(),
                "last_success": health.last_success.isoformat() if health.last_success else None,
                "last_failure": health.last_failure.isoformat() if health.last_failure else None,
                "consecutive_failures": health.consecutive_failures,
                "metrics": {
                    "avg_latency_ms": health.metrics.avg_latency_ms,
                    "p50_latency_ms": health.metrics.p50_latency_ms,
                    "p95_latency_ms": health.metrics.p95_latency_ms,
                    "p99_latency_ms": health.metrics.p99_latency_ms,
                    "error_rate": health.metrics.error_rate,
                },
                "recent_errors": health.recent_errors[-5:],
            }

    def record_request(
        self,
        component: ComponentType,
        success: bool,
        latency_ms: float,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a request for metrics tracking."""
        with self._lock:
            health = self._component_health.get(component)
            if not health:
                return

            health.recent_latencies.append(latency_ms)

            if success:
                health.metrics.success_count += 1
            else:
                health.metrics.error_count += 1
                if error_message:
                    health.recent_errors.append(error_message)
                    health.recent_errors = health.recent_errors[-10:]

            self._update_metrics(health)

    def is_healthy(self, component: Optional[ComponentType] = None) -> bool:
        """Check if component(s) are healthy."""
        with self._lock:
            if component:
                health = self._component_health.get(component)
                return health and health.status == HealthStatus.HEALTHY

            # Check all critical components
            critical = [
                ComponentType.OPENAI_VISION,
                ComponentType.VISION_ROUTER,
            ]
            return all(
                self._component_health[c].status != HealthStatus.UNHEALTHY
                for c in critical
            )


# Singleton instance
_monitor: Optional[VisionHealthMonitor] = None


def get_vision_health_monitor() -> VisionHealthMonitor:
    """Get global health monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = VisionHealthMonitor()
    return _monitor


async def start_health_monitoring() -> None:
    """Start the global health monitor."""
    monitor = get_vision_health_monitor()
    await monitor.start_monitoring()


async def stop_health_monitoring() -> None:
    """Stop the global health monitor."""
    monitor = get_vision_health_monitor()
    await monitor.stop_monitoring()
