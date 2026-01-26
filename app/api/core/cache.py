"""
Bounded Cache with TTL
Memory-safe caching with size limits and expiration.
"""
import asyncio
import threading
import time
import sys
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, TypeVar, Generic, Callable, Tuple, List
from collections import OrderedDict
from enum import Enum
import logging
import heapq
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

T = TypeVar('T')
K = TypeVar('K')
V = TypeVar('V')


class EvictionPolicy(str, Enum):
    """Cache eviction policies"""
    LRU = "lru"           # Least Recently Used
    LFU = "lfu"           # Least Frequently Used
    FIFO = "fifo"         # First In First Out
    TTL = "ttl"           # Oldest TTL first


@dataclass
class CacheConfig:
    """Configuration for bounded cache"""
    max_size: int = 10000           # Maximum number of entries
    max_memory_mb: float = 100.0    # Maximum memory in MB
    default_ttl_seconds: float = 3600.0  # Default TTL (1 hour)
    eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    cleanup_interval_seconds: float = 60.0  # Background cleanup interval


@dataclass
class CacheEntry(Generic[V]):
    """Entry in the cache"""
    value: V
    created_at: float
    expires_at: float
    last_accessed: float
    access_count: int = 0
    size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def ttl_remaining(self) -> float:
        return max(0, self.expires_at - time.time())


@dataclass
class CacheStats:
    """Cache statistics"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expired: int = 0
    current_size: int = 0
    current_memory_bytes: int = 0
    max_size: int = 0
    max_memory_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expired": self.expired,
            "hit_rate": round(self.hit_rate, 4),
            "current_size": self.current_size,
            "current_memory_mb": round(self.current_memory_bytes / (1024 * 1024), 2),
            "max_size": self.max_size,
            "max_memory_mb": round(self.max_memory_bytes / (1024 * 1024), 2),
        }


class BoundedCache(Generic[K, V]):
    """
    Thread-safe bounded cache with TTL and memory limits.

    Features:
    - Maximum entry count limit
    - Maximum memory limit
    - TTL-based expiration
    - Multiple eviction policies (LRU, LFU, FIFO, TTL)
    - Background cleanup
    - Comprehensive statistics

    Example:
        cache = BoundedCache[str, dict](
            name="embeddings",
            config=CacheConfig(max_size=1000, max_memory_mb=50)
        )

        # Set with default TTL
        cache.set("key1", {"embedding": [...]})

        # Set with custom TTL
        cache.set("key2", {"embedding": [...]}, ttl=7200)

        # Get value
        value = cache.get("key1")
    """

    def __init__(
        self,
        name: str,
        config: Optional[CacheConfig] = None
    ):
        self.name = name
        self.config = config or CacheConfig()

        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats(
            max_size=self.config.max_size,
            max_memory_bytes=int(self.config.max_memory_mb * 1024 * 1024)
        )

        # For LFU tracking
        self._frequency_heap: List[Tuple[int, float, K]] = []

        # Background cleanup
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """
        Get value from cache.

        Args:
            key: Cache key
            default: Default value if not found

        Returns:
            Cached value or default
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return default

            if entry.is_expired:
                self._remove_entry(key)
                self._stats.misses += 1
                self._stats.expired += 1
                return default

            # Update access info
            entry.last_accessed = time.time()
            entry.access_count += 1

            # Move to end for LRU
            if self.config.eviction_policy == EvictionPolicy.LRU:
                self._cache.move_to_end(key)

            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL in seconds (uses default if not provided)

        Returns:
            True if set successfully
        """
        ttl = ttl if ttl is not None else self.config.default_ttl_seconds
        now = time.time()

        # Estimate size
        size_bytes = self._estimate_size(value)

        with self._lock:
            # Check if we need to evict
            self._ensure_capacity(size_bytes)

            # Create entry
            entry = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + ttl,
                last_accessed=now,
                access_count=1,
                size_bytes=size_bytes
            )

            # Remove old entry if exists
            if key in self._cache:
                old_entry = self._cache[key]
                self._stats.current_memory_bytes -= old_entry.size_bytes
                self._stats.current_size -= 1

            # Add new entry
            self._cache[key] = entry
            self._stats.current_size += 1
            self._stats.current_memory_bytes += size_bytes

            return True

    def delete(self, key: K) -> bool:
        """Delete entry from cache"""
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                return True
            return False

    def exists(self, key: K) -> bool:
        """Check if key exists and is not expired"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired:
                self._remove_entry(key)
                self._stats.expired += 1
                return False
            return True

    def clear(self):
        """Clear all entries"""
        with self._lock:
            self._cache.clear()
            self._stats.current_size = 0
            self._stats.current_memory_bytes = 0

    def _remove_entry(self, key: K):
        """Remove entry and update stats"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._stats.current_size -= 1
            self._stats.current_memory_bytes -= entry.size_bytes

    def _ensure_capacity(self, needed_bytes: int):
        """Evict entries if necessary to make room"""
        # Check size limit
        while (self._stats.current_size >= self.config.max_size and
               len(self._cache) > 0):
            self._evict_one()

        # Check memory limit
        max_bytes = int(self.config.max_memory_mb * 1024 * 1024)
        while (self._stats.current_memory_bytes + needed_bytes > max_bytes and
               len(self._cache) > 0):
            self._evict_one()

    def _evict_one(self):
        """Evict one entry based on policy"""
        if not self._cache:
            return

        key_to_evict: Optional[K] = None

        if self.config.eviction_policy == EvictionPolicy.LRU:
            # First item is least recently used
            key_to_evict = next(iter(self._cache))

        elif self.config.eviction_policy == EvictionPolicy.FIFO:
            # First item is oldest
            key_to_evict = next(iter(self._cache))

        elif self.config.eviction_policy == EvictionPolicy.TTL:
            # Find entry with shortest remaining TTL
            min_ttl = float('inf')
            for key, entry in self._cache.items():
                if entry.ttl_remaining < min_ttl:
                    min_ttl = entry.ttl_remaining
                    key_to_evict = key

        elif self.config.eviction_policy == EvictionPolicy.LFU:
            # Find least frequently used
            min_count = float('inf')
            for key, entry in self._cache.items():
                if entry.access_count < min_count:
                    min_count = entry.access_count
                    key_to_evict = key

        if key_to_evict is not None:
            self._remove_entry(key_to_evict)
            self._stats.evictions += 1

    def _estimate_size(self, value: V) -> int:
        """Estimate memory size of value"""
        try:
            return sys.getsizeof(value)
        except TypeError:
            # Fallback for complex objects
            if isinstance(value, dict):
                return sum(
                    sys.getsizeof(k) + sys.getsizeof(v)
                    for k, v in value.items()
                )
            elif isinstance(value, (list, tuple)):
                return sum(sys.getsizeof(item) for item in value)
            else:
                return 1000  # Default estimate

    def cleanup_expired(self) -> int:
        """Remove all expired entries"""
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]

            for key in expired_keys:
                self._remove_entry(key)

            self._stats.expired += len(expired_keys)
            return len(expired_keys)

    @property
    def stats(self) -> CacheStats:
        """Get cache statistics"""
        return self._stats

    @property
    def size(self) -> int:
        """Current cache size"""
        return self._stats.current_size

    async def start_background_cleanup(self):
        """Start background cleanup task"""
        if self._cleanup_task is None:
            self._shutdown = False
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_background_cleanup(self):
        """Stop background cleanup task"""
        self._shutdown = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.config.cleanup_interval_seconds)
                expired = self.cleanup_expired()
                if expired > 0:
                    logger.debug(f"Cache '{self.name}': cleaned up {expired} expired entries")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")


class AsyncBoundedCache(Generic[K, V]):
    """
    Async-safe bounded cache.

    Same features as BoundedCache but with async lock.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CacheConfig] = None
    ):
        self.name = name
        self.config = config or CacheConfig()

        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stats = CacheStats(
            max_size=self.config.max_size,
            max_memory_bytes=int(self.config.max_memory_mb * 1024 * 1024)
        )

        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutdown = False

    async def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Get value from cache"""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return default

            if entry.is_expired:
                await self._remove_entry(key)
                self._stats.misses += 1
                self._stats.expired += 1
                return default

            entry.last_accessed = time.time()
            entry.access_count += 1

            if self.config.eviction_policy == EvictionPolicy.LRU:
                self._cache.move_to_end(key)

            self._stats.hits += 1
            return entry.value

    async def set(
        self,
        key: K,
        value: V,
        ttl: Optional[float] = None
    ) -> bool:
        """Set value in cache"""
        ttl = ttl if ttl is not None else self.config.default_ttl_seconds
        now = time.time()
        size_bytes = self._estimate_size(value)

        async with self._lock:
            await self._ensure_capacity(size_bytes)

            entry = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + ttl,
                last_accessed=now,
                access_count=1,
                size_bytes=size_bytes
            )

            if key in self._cache:
                old_entry = self._cache[key]
                self._stats.current_memory_bytes -= old_entry.size_bytes
                self._stats.current_size -= 1

            self._cache[key] = entry
            self._stats.current_size += 1
            self._stats.current_memory_bytes += size_bytes

            return True

    async def delete(self, key: K) -> bool:
        """Delete entry from cache"""
        async with self._lock:
            if key in self._cache:
                await self._remove_entry(key)
                return True
            return False

    async def _remove_entry(self, key: K):
        """Remove entry and update stats"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._stats.current_size -= 1
            self._stats.current_memory_bytes -= entry.size_bytes

    async def _ensure_capacity(self, needed_bytes: int):
        """Evict entries if necessary"""
        while (self._stats.current_size >= self.config.max_size and
               len(self._cache) > 0):
            await self._evict_one()

        max_bytes = int(self.config.max_memory_mb * 1024 * 1024)
        while (self._stats.current_memory_bytes + needed_bytes > max_bytes and
               len(self._cache) > 0):
            await self._evict_one()

    async def _evict_one(self):
        """Evict one entry based on policy"""
        if not self._cache:
            return

        key_to_evict = next(iter(self._cache))
        await self._remove_entry(key_to_evict)
        self._stats.evictions += 1

    def _estimate_size(self, value: V) -> int:
        """Estimate memory size"""
        try:
            return sys.getsizeof(value)
        except TypeError:
            return 1000

    async def cleanup_expired(self) -> int:
        """Remove expired entries"""
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired
            ]
            for key in expired_keys:
                await self._remove_entry(key)
            self._stats.expired += len(expired_keys)
            return len(expired_keys)

    @property
    def stats(self) -> CacheStats:
        return self._stats


# ==================== Cache Registry ====================

class CacheRegistry:
    """
    Central registry for all caches.

    Example:
        registry = CacheRegistry.get_instance()

        # Create caches
        embeddings = registry.get_or_create(
            "embeddings",
            CacheConfig(max_size=5000, max_memory_mb=200)
        )

        # Get stats for all caches
        all_stats = registry.get_all_stats()
    """

    _instance: Optional["CacheRegistry"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._caches: Dict[str, BoundedCache] = {}
                    cls._instance._async_caches: Dict[str, AsyncBoundedCache] = {}
        return cls._instance

    def get_or_create(
        self,
        name: str,
        config: Optional[CacheConfig] = None
    ) -> BoundedCache:
        """Get or create sync cache"""
        if name not in self._caches:
            self._caches[name] = BoundedCache(name, config)
        return self._caches[name]

    def get_or_create_async(
        self,
        name: str,
        config: Optional[CacheConfig] = None
    ) -> AsyncBoundedCache:
        """Get or create async cache"""
        if name not in self._async_caches:
            self._async_caches[name] = AsyncBoundedCache(name, config)
        return self._async_caches[name]

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all caches"""
        stats = {}
        for name, cache in self._caches.items():
            stats[name] = cache.stats.to_dict()
        for name, cache in self._async_caches.items():
            stats[f"{name}_async"] = cache.stats.to_dict()
        return stats

    def cleanup_all(self) -> Dict[str, int]:
        """Cleanup expired entries in all caches"""
        results = {}
        for name, cache in self._caches.items():
            results[name] = cache.cleanup_expired()
        return results

    @classmethod
    def get_instance(cls) -> "CacheRegistry":
        return cls()

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None


def get_cache_registry() -> CacheRegistry:
    """Get the global cache registry"""
    return CacheRegistry.get_instance()


# ==================== Pre-configured Caches ====================

# Embedding cache - high memory usage
EMBEDDING_CACHE_CONFIG = CacheConfig(
    max_size=5000,
    max_memory_mb=200.0,
    default_ttl_seconds=86400,  # 24 hours
    eviction_policy=EvictionPolicy.LRU
)

# Session cache - shorter TTL
SESSION_CACHE_CONFIG = CacheConfig(
    max_size=1000,
    max_memory_mb=50.0,
    default_ttl_seconds=7200,  # 2 hours
    eviction_policy=EvictionPolicy.LRU
)

# Document cache
DOCUMENT_CACHE_CONFIG = CacheConfig(
    max_size=2000,
    max_memory_mb=100.0,
    default_ttl_seconds=3600,  # 1 hour
    eviction_policy=EvictionPolicy.LRU
)

# Query result cache - short TTL
QUERY_CACHE_CONFIG = CacheConfig(
    max_size=500,
    max_memory_mb=25.0,
    default_ttl_seconds=300,  # 5 minutes
    eviction_policy=EvictionPolicy.TTL
)
