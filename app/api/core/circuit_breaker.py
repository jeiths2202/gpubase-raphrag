"""
Circuit Breaker Pattern
Prevents cascading failures by failing fast when external services are down.
"""
import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, TypeVar, Generic, Callable, Awaitable, Union
from enum import Enum
from functools import wraps
from datetime import datetime, timedelta
import threading

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    # Thresholds
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes to close from half-open
    # Timing
    reset_timeout_seconds: float = 30.0  # Time before trying half-open
    call_timeout_seconds: float = 10.0   # Timeout for individual calls
    # Metrics window
    window_size_seconds: float = 60.0    # Rolling window for failure counting
    # Fallback
    fallback_value: Any = None


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    fallback_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_state_change: Optional[datetime] = None
    current_state: CircuitState = CircuitState.CLOSED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "fallback_calls": self.fallback_calls,
            "state_changes": self.state_changes,
            "success_rate": self.successful_calls / max(self.total_calls, 1),
            "current_state": self.current_state.value,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success_time": self.last_success_time.isoformat() if self.last_success_time else None,
        }


class CircuitBreakerError(Exception):
    """Raised when circuit is open"""

    def __init__(self, breaker_name: str, state: CircuitState, retry_after: Optional[float] = None):
        self.breaker_name = breaker_name
        self.state = state
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker '{breaker_name}' is {state.value}")


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Failing fast, calls rejected immediately
    - HALF_OPEN: Testing recovery, limited calls allowed

    Example:
        breaker = CircuitBreaker("notion_api", config)

        try:
            result = await breaker.call(notion_client.get_page, page_id)
        except CircuitBreakerError:
            # Service is down, use fallback
            result = cached_result
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        on_state_change: Optional[Callable[[str, CircuitState, CircuitState], None]] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._on_state_change = on_state_change

        # State
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change_time: float = time.time()

        # Rolling window for failures
        self._failure_timestamps: list[float] = []

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Stats
        self._stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        """Current circuit state"""
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get current statistics"""
        self._stats.current_state = self._state
        return self._stats

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args,
        fallback: Optional[Callable[..., Awaitable[T]]] = None,
        **kwargs
    ) -> T:
        """
        Execute function through circuit breaker.

        Args:
            func: Async function to call
            *args: Function arguments
            fallback: Optional fallback function
            **kwargs: Function keyword arguments

        Returns:
            Function result or fallback result

        Raises:
            CircuitBreakerError: If circuit is open and no fallback
        """
        async with self._lock:
            self._stats.total_calls += 1

            # Check if we should transition to half-open
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    await self._transition_to(CircuitState.HALF_OPEN)
                else:
                    self._stats.rejected_calls += 1
                    retry_after = self._get_retry_after()

                    if fallback:
                        self._stats.fallback_calls += 1
                        return await fallback(*args, **kwargs)

                    raise CircuitBreakerError(self.name, self._state, retry_after)

        # Execute the call
        try:
            result = await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=self.config.call_timeout_seconds
            )
            await self._on_success()
            return result

        except asyncio.TimeoutError:
            await self._on_failure()
            if fallback:
                self._stats.fallback_calls += 1
                return await fallback(*args, **kwargs)
            raise

        except Exception as e:
            await self._on_failure()

            if fallback:
                self._stats.fallback_calls += 1
                return await fallback(*args, **kwargs)
            raise

    async def _on_success(self):
        """Handle successful call"""
        async with self._lock:
            self._stats.successful_calls += 1
            self._stats.last_success_time = datetime.utcnow()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def _on_failure(self):
        """Handle failed call"""
        async with self._lock:
            self._stats.failed_calls += 1
            self._stats.last_failure_time = datetime.utcnow()
            self._last_failure_time = time.time()

            # Add to rolling window
            now = time.time()
            self._failure_timestamps.append(now)

            # Clean old timestamps
            cutoff = now - self.config.window_size_seconds
            self._failure_timestamps = [
                ts for ts in self._failure_timestamps if ts > cutoff
            ]

            if self._state == CircuitState.HALF_OPEN:
                # Single failure in half-open returns to open
                await self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                # Count failures in window
                failures_in_window = len(self._failure_timestamps)
                if failures_in_window >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)

    async def _transition_to(self, new_state: CircuitState):
        """Transition to new state"""
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.time()
        self._stats.state_changes += 1
        self._stats.last_state_change = datetime.utcnow()

        # Reset counters based on new state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._failure_timestamps = []
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
        elif new_state == CircuitState.OPEN:
            self._success_count = 0

        logger.warning(
            f"Circuit breaker '{self.name}' state change: {old_state.value} -> {new_state.value}"
        )

        if self._on_state_change:
            try:
                self._on_state_change(self.name, old_state, new_state)
            except Exception as e:
                logger.error(f"State change callback error: {e}")

    def _should_attempt_reset(self) -> bool:
        """Check if enough time passed to try half-open"""
        elapsed = time.time() - self._last_state_change_time
        return elapsed >= self.config.reset_timeout_seconds

    def _get_retry_after(self) -> float:
        """Get seconds until retry might succeed"""
        elapsed = time.time() - self._last_state_change_time
        return max(0, self.config.reset_timeout_seconds - elapsed)

    async def force_open(self):
        """Force circuit to open state"""
        async with self._lock:
            await self._transition_to(CircuitState.OPEN)

    async def force_close(self):
        """Force circuit to closed state"""
        async with self._lock:
            await self._transition_to(CircuitState.CLOSED)

    async def reset(self):
        """Reset circuit breaker to initial state"""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._failure_timestamps = []
            self._last_failure_time = None
            self._last_state_change_time = time.time()


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Example:
        registry = CircuitBreakerRegistry()

        # Get or create breaker for a service
        breaker = registry.get_or_create("notion_api")

        # Execute through breaker
        result = await breaker.call(api_call)

        # Get all stats
        all_stats = registry.get_all_stats()
    """

    _instance: Optional["CircuitBreakerRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers: Dict[str, CircuitBreaker] = {}
                    cls._instance._async_lock = asyncio.Lock()
        return cls._instance

    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        on_state_change: Optional[Callable] = None
    ) -> CircuitBreaker:
        """Get existing or create new circuit breaker"""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config, on_state_change)
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        return self._breakers.get(name)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all circuit breakers"""
        return {
            name: breaker.stats.to_dict()
            for name, breaker in self._breakers.items()
        }

    def get_open_circuits(self) -> list[str]:
        """Get names of open circuit breakers"""
        return [
            name for name, breaker in self._breakers.items()
            if breaker.state == CircuitState.OPEN
        ]

    async def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            await breaker.reset()

    @classmethod
    def get_instance(cls) -> "CircuitBreakerRegistry":
        """Get singleton instance"""
        return cls()

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)"""
        with cls._lock:
            cls._instance = None


def circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
    fallback: Optional[Callable] = None
):
    """
    Decorator to apply circuit breaker to async function.

    Usage:
        @circuit_breaker("notion_api", fallback=get_cached_data)
        async def fetch_notion_page(page_id: str):
            return await notion_client.get_page(page_id)
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        registry = CircuitBreakerRegistry.get_instance()
        breaker = registry.get_or_create(name, config)

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await breaker.call(func, *args, fallback=fallback, **kwargs)

        # Expose breaker for inspection
        wrapper.circuit_breaker = breaker
        return wrapper

    return decorator


# Pre-configured circuit breakers for common services
CONNECTOR_CIRCUIT_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    success_threshold=2,
    reset_timeout_seconds=30.0,
    call_timeout_seconds=15.0,
    window_size_seconds=60.0
)

LLM_CIRCUIT_CONFIG = CircuitBreakerConfig(
    failure_threshold=3,
    success_threshold=2,
    reset_timeout_seconds=60.0,
    call_timeout_seconds=120.0,
    window_size_seconds=120.0
)

EMBEDDING_CIRCUIT_CONFIG = CircuitBreakerConfig(
    failure_threshold=5,
    success_threshold=3,
    reset_timeout_seconds=30.0,
    call_timeout_seconds=30.0,
    window_size_seconds=60.0
)


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry"""
    return CircuitBreakerRegistry.get_instance()
