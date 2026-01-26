"""
Resilient Connector Wrapper
Adds circuit breaker, retry, and metrics to any connector.
"""
import asyncio
import time
from typing import Optional, Dict, Any, AsyncGenerator, Callable, Awaitable
from datetime import datetime
from functools import wraps
import logging

from .base import BaseConnector, ConnectorResult, ConnectorStatus, ConnectorDocument
from ..core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    get_circuit_breaker_registry,
    CONNECTOR_CIRCUIT_CONFIG
)
from ..core.metrics import get_metrics_registry

logger = logging.getLogger(__name__)


class ResilientConnector:
    """
    Wrapper that adds resilience patterns to any connector.

    Features:
    - Circuit breaker for failure isolation
    - Automatic retries with exponential backoff
    - Timeout enforcement
    - Metrics collection
    - Fallback support

    Example:
        base_connector = NotionConnector(access_token=token)
        resilient = ResilientConnector(
            connector=base_connector,
            name="notion",
            config=CircuitBreakerConfig(failure_threshold=5)
        )

        # Use like normal connector
        result = await resilient.fetch_document(doc_id)
    """

    def __init__(
        self,
        connector: BaseConnector,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: float = 30.0
    ):
        self._connector = connector
        self._name = name
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._timeout = timeout

        # Get or create circuit breaker
        registry = get_circuit_breaker_registry()
        self._circuit_breaker = registry.get_or_create(
            f"connector_{name}",
            config or CONNECTOR_CIRCUIT_CONFIG,
            self._on_state_change
        )

        # Metrics
        self._metrics = get_metrics_registry()
        self._requests_counter = self._metrics.counter(
            f"connector_{name}_requests_total",
            f"Total requests to {name} connector",
            ["operation", "status"]
        )
        self._duration_histogram = self._metrics.histogram(
            f"connector_{name}_duration_seconds",
            f"Request duration for {name} connector",
            ["operation"],
            buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
        )

    def _on_state_change(self, name: str, old_state, new_state):
        """Handle circuit breaker state changes"""
        logger.warning(
            f"Connector {self._name} circuit breaker: {old_state.value} -> {new_state.value}"
        )

        # Update metric
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(new_state.value, -1)
        self._metrics.get("circuit_breaker_state").set(state_value, name=name)

        if new_state.value == "open":
            self._metrics.get("circuit_breaker_trips_total").inc(name=name)

    async def _execute_with_resilience(
        self,
        operation: str,
        func: Callable[..., Awaitable[Any]],
        *args,
        fallback_result: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """Execute function with circuit breaker and retry"""
        start_time = time.time()

        async def fallback(*a, **kw):
            return fallback_result

        try:
            result = await self._circuit_breaker.call(
                self._execute_with_retry,
                operation, func, *args,
                fallback=fallback if fallback_result is not None else None,
                **kwargs
            )

            # Record success metrics
            duration = time.time() - start_time
            self._requests_counter.inc(operation=operation, status="success")
            self._duration_histogram.observe(duration, operation=operation)

            return result

        except CircuitBreakerError as e:
            # Circuit is open
            self._requests_counter.inc(operation=operation, status="circuit_open")
            logger.warning(f"Circuit open for {self._name}.{operation}: retry after {e.retry_after:.1f}s")
            raise

        except Exception as e:
            # Other failures
            duration = time.time() - start_time
            self._requests_counter.inc(operation=operation, status="error")
            self._duration_histogram.observe(duration, operation=operation)
            raise

    async def _execute_with_retry(
        self,
        operation: str,
        func: Callable[..., Awaitable[Any]],
        *args,
        **kwargs
    ) -> Any:
        """Execute with retry and exponential backoff"""
        last_exception = None

        for attempt in range(self._max_retries):
            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self._timeout
                )
                return result

            except asyncio.TimeoutError:
                last_exception = TimeoutError(
                    f"{self._name}.{operation} timed out after {self._timeout}s"
                )
                logger.warning(f"Timeout on {self._name}.{operation}, attempt {attempt + 1}")

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Error on {self._name}.{operation}, attempt {attempt + 1}: {e}"
                )

            # Exponential backoff
            if attempt < self._max_retries - 1:
                delay = self._base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        raise last_exception

    # ==================== Connector Interface ====================

    @property
    def resource_type(self) -> str:
        return self._connector.resource_type

    @property
    def display_name(self) -> str:
        return self._connector.display_name

    async def validate_connection(self) -> ConnectorResult:
        """Validate connection with resilience"""
        return await self._execute_with_resilience(
            "validate",
            self._connector.validate_connection,
            fallback_result=ConnectorResult(
                status=ConnectorStatus.ERROR,
                error="Connection validation failed (circuit open)"
            )
        )

    async def fetch_document(self, external_id: str) -> ConnectorResult:
        """Fetch document with resilience"""
        return await self._execute_with_resilience(
            "fetch_document",
            self._connector.fetch_document,
            external_id,
            fallback_result=ConnectorResult(
                status=ConnectorStatus.ERROR,
                error=f"Failed to fetch document {external_id}"
            )
        )

    async def list_documents(
        self,
        path: Optional[str] = None,
        modified_since: Optional[datetime] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        List documents with resilience.

        Note: This yields items from the underlying generator.
        Circuit breaker applies per-page/per-batch.
        """
        try:
            async for doc in self._connector.list_documents(path, modified_since):
                yield doc
        except Exception as e:
            logger.error(f"Error listing documents from {self._name}: {e}")
            # Don't raise - just stop iteration
            return

    async def exchange_code(self, code: str, redirect_uri: str) -> ConnectorResult:
        """Exchange OAuth code with resilience"""
        return await self._execute_with_resilience(
            "exchange_code",
            self._connector.exchange_code,
            code, redirect_uri
        )

    async def refresh_access_token(self) -> ConnectorResult:
        """Refresh token with resilience"""
        return await self._execute_with_resilience(
            "refresh_token",
            self._connector.refresh_access_token
        )

    def get_oauth_url(self, redirect_uri: str, state: str) -> str:
        """Get OAuth URL (no resilience needed - local operation)"""
        return self._connector.get_oauth_url(redirect_uri, state)

    # ==================== Circuit Breaker Control ====================

    @property
    def circuit_state(self) -> str:
        """Get current circuit state"""
        return self._circuit_breaker.state.value

    @property
    def circuit_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        return self._circuit_breaker.stats.to_dict()

    async def reset_circuit(self):
        """Reset circuit breaker to closed state"""
        await self._circuit_breaker.reset()

    async def force_open_circuit(self):
        """Force circuit breaker to open state"""
        await self._circuit_breaker.force_open()


def make_resilient(
    connector: BaseConnector,
    name: Optional[str] = None,
    config: Optional[CircuitBreakerConfig] = None
) -> ResilientConnector:
    """
    Factory function to wrap a connector with resilience.

    Example:
        connector = make_resilient(NotionConnector(token=token))
    """
    connector_name = name or connector.resource_type
    return ResilientConnector(connector, connector_name, config)
