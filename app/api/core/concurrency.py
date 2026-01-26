"""
Concurrency Utilities
Thread-safe and async-safe patterns for shared state management.
"""
import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, TypeVar, Generic, Callable, Awaitable
from functools import wraps
import logging
import time
from contextlib import asynccontextmanager
from collections import OrderedDict

logger = logging.getLogger(__name__)

T = TypeVar('T')


class AsyncLockManager:
    """
    Manages named async locks for fine-grained locking.

    Provides per-key locking to avoid global lock contention.

    Example:
        lock_manager = AsyncLockManager()

        async with lock_manager.acquire("session:123"):
            # Only one coroutine can access session:123
            await process_session("123")
    """

    def __init__(self, max_locks: int = 10000):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_counts: Dict[str, int] = {}
        self._meta_lock = asyncio.Lock()
        self._max_locks = max_locks

    @asynccontextmanager
    async def acquire(self, key: str, timeout: Optional[float] = None):
        """
        Acquire lock for a specific key.

        Args:
            key: Lock identifier
            timeout: Optional timeout in seconds

        Yields:
            None (context manager)
        """
        lock = await self._get_or_create_lock(key)

        try:
            if timeout:
                try:
                    await asyncio.wait_for(lock.acquire(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Could not acquire lock for {key} within {timeout}s")
            else:
                await lock.acquire()

            yield
        finally:
            lock.release()
            await self._release_lock(key)

    async def _get_or_create_lock(self, key: str) -> asyncio.Lock:
        """Get existing lock or create new one"""
        async with self._meta_lock:
            if key not in self._locks:
                # Cleanup old locks if too many
                if len(self._locks) >= self._max_locks:
                    await self._cleanup_unused_locks()

                self._locks[key] = asyncio.Lock()
                self._lock_counts[key] = 0

            self._lock_counts[key] += 1
            return self._locks[key]

    async def _release_lock(self, key: str):
        """Decrement lock reference count"""
        async with self._meta_lock:
            if key in self._lock_counts:
                self._lock_counts[key] -= 1

    async def _cleanup_unused_locks(self):
        """Remove locks with zero reference count"""
        to_remove = [
            key for key, count in self._lock_counts.items()
            if count <= 0
        ]
        for key in to_remove[:len(to_remove) // 2]:  # Remove half
            del self._locks[key]
            del self._lock_counts[key]

    @property
    def lock_count(self) -> int:
        """Number of active locks"""
        return len(self._locks)


class ThreadSafeSingleton:
    """
    Thread-safe singleton base class.

    Usage:
        class MyService(ThreadSafeSingleton):
            def _initialize(self):
                # Called once during first instantiation
                self.data = {}
    """

    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                # Double-check locking
                if cls not in cls._instances:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instances[cls] = instance
        return cls._instances[cls]

    def __init__(self, *args, **kwargs):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._initialize(*args, **kwargs)
                    self._initialized = True

    def _initialize(self, *args, **kwargs):
        """Override to initialize instance"""
        pass

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing)"""
        with cls._lock:
            if cls in cls._instances:
                del cls._instances[cls]


class AsyncSingleton:
    """
    Async-safe singleton with lazy initialization.

    Usage:
        class MyAsyncService(AsyncSingleton):
            async def _async_initialize(self):
                self.client = await create_client()
    """

    _instances: Dict[type, Any] = {}
    _locks: Dict[type, asyncio.Lock] = {}
    _meta_lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls, *args, **kwargs):
        """Get or create singleton instance asynchronously"""
        if cls not in cls._instances:
            async with cls._meta_lock:
                if cls not in cls._locks:
                    cls._locks[cls] = asyncio.Lock()

            async with cls._locks[cls]:
                if cls not in cls._instances:
                    instance = cls.__new__(cls)
                    await instance._async_initialize(*args, **kwargs)
                    cls._instances[cls] = instance

        return cls._instances[cls]

    async def _async_initialize(self, *args, **kwargs):
        """Override for async initialization"""
        pass

    @classmethod
    async def reset_instance(cls):
        """Reset singleton instance (for testing)"""
        async with cls._meta_lock:
            if cls in cls._instances:
                del cls._instances[cls]


@dataclass
class LockStats:
    """Statistics for lock usage"""
    acquisitions: int = 0
    contentions: int = 0
    total_wait_time_ms: float = 0
    max_wait_time_ms: float = 0


class InstrumentedLock:
    """
    Async lock with instrumentation for monitoring.

    Tracks:
    - Number of acquisitions
    - Contention events
    - Wait times
    """

    def __init__(self, name: str = "unnamed"):
        self._lock = asyncio.Lock()
        self._name = name
        self._stats = LockStats()

    @asynccontextmanager
    async def acquire(self, timeout: Optional[float] = None):
        """Acquire lock with instrumentation"""
        start_time = time.time()
        was_contended = self._lock.locked()

        if was_contended:
            self._stats.contentions += 1

        try:
            if timeout:
                await asyncio.wait_for(self._lock.acquire(), timeout=timeout)
            else:
                await self._lock.acquire()

            wait_time = (time.time() - start_time) * 1000
            self._stats.acquisitions += 1
            self._stats.total_wait_time_ms += wait_time
            self._stats.max_wait_time_ms = max(self._stats.max_wait_time_ms, wait_time)

            yield
        finally:
            self._lock.release()

    @property
    def stats(self) -> LockStats:
        """Get lock statistics"""
        return self._stats

    @property
    def is_locked(self) -> bool:
        """Check if lock is held"""
        return self._lock.locked()


def synchronized(lock_attr: str = "_lock"):
    """
    Decorator to synchronize async method on instance lock.

    Usage:
        class MyService:
            def __init__(self):
                self._lock = asyncio.Lock()

            @synchronized()
            async def critical_section(self):
                # Protected by self._lock
                pass
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(self, *args, **kwargs) -> T:
            lock = getattr(self, lock_attr, None)
            if lock is None:
                # Create lock if not exists
                lock = asyncio.Lock()
                setattr(self, lock_attr, lock)

            async with lock:
                return await func(self, *args, **kwargs)

        return wrapper
    return decorator


# Global lock managers
_session_locks = AsyncLockManager(max_locks=10000)
_user_locks = AsyncLockManager(max_locks=5000)
_document_locks = AsyncLockManager(max_locks=20000)


def get_session_lock_manager() -> AsyncLockManager:
    """Get session-scoped lock manager"""
    return _session_locks


def get_user_lock_manager() -> AsyncLockManager:
    """Get user-scoped lock manager"""
    return _user_locks


def get_document_lock_manager() -> AsyncLockManager:
    """Get document-scoped lock manager"""
    return _document_locks
