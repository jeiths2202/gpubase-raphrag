"""
VLM Image Description Cache Service

Caches VLM-generated image descriptions to avoid redundant API calls.
Uses image content hash as cache key.

Features:
- SHA256 hash-based deduplication
- TTL-based expiration
- In-memory cache with optional Redis backend
- Cache statistics and monitoring
"""
import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from collections import OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry for VLM description."""
    description: str
    alt_text: str
    confidence: float
    embedding: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > ttl_seconds

    def touch(self):
        """Update access statistics."""
        self.access_count += 1
        self.last_accessed = time.time()


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    total_entries: int = 0
    total_bytes_saved: int = 0  # Approximate bytes saved by cache hits

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "total_entries": self.total_entries,
            "hit_rate": round(self.hit_rate * 100, 2),
            "total_bytes_saved": self.total_bytes_saved
        }


class VLMImageCache:
    """
    In-memory cache for VLM image descriptions.

    Uses LRU eviction when max size is reached.
    Supports TTL-based expiration.
    """

    def __init__(
        self,
        max_size: int = None,
        ttl_seconds: int = None,
        enabled: bool = True
    ):
        """
        Initialize cache.

        Args:
            max_size: Maximum number of entries (default: 1000)
            ttl_seconds: Time-to-live in seconds (default: 3600 = 1 hour)
            enabled: Whether caching is enabled
        """
        self.max_size = max_size or int(os.getenv("VLM_CACHE_MAX_SIZE", "1000"))
        self.ttl_seconds = ttl_seconds or int(os.getenv("VLM_CACHE_TTL", "3600"))
        self.enabled = enabled

        # LRU cache using OrderedDict
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()
        self._lock = asyncio.Lock()

    @staticmethod
    def compute_hash(image_data: bytes) -> str:
        """
        Compute SHA256 hash of image data.

        Args:
            image_data: Raw image bytes

        Returns:
            Hex string of SHA256 hash
        """
        return hashlib.sha256(image_data).hexdigest()

    async def get(
        self,
        image_data: bytes,
        include_embedding: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached description for image.

        Args:
            image_data: Raw image bytes
            include_embedding: Whether to include embedding in result

        Returns:
            Cached result dict or None if not found/expired
        """
        if not self.enabled:
            return None

        image_hash = self.compute_hash(image_data)

        async with self._lock:
            entry = self._cache.get(image_hash)

            if entry is None:
                self._stats.misses += 1
                return None

            # Check expiration
            if entry.is_expired(self.ttl_seconds):
                self._cache.pop(image_hash, None)
                self._stats.misses += 1
                self._stats.evictions += 1
                self._stats.total_entries = len(self._cache)
                logger.debug(f"Cache entry expired: {image_hash[:16]}...")
                return None

            # Cache hit - move to end (most recently used)
            self._cache.move_to_end(image_hash)
            entry.touch()
            self._stats.hits += 1
            self._stats.total_bytes_saved += len(image_data)

            logger.debug(
                f"Cache hit: {image_hash[:16]}... "
                f"(access_count: {entry.access_count})"
            )

            result = {
                "description": entry.description,
                "alt_text": entry.alt_text,
                "confidence": entry.confidence,
                "cached": True,
                "cache_age_seconds": int(time.time() - entry.created_at)
            }

            if include_embedding and entry.embedding:
                result["embedding"] = entry.embedding

            return result

    async def set(
        self,
        image_data: bytes,
        description: str,
        alt_text: str = "",
        confidence: float = 0.0,
        embedding: Optional[List[float]] = None
    ) -> str:
        """
        Cache description for image.

        Args:
            image_data: Raw image bytes
            description: VLM-generated description
            alt_text: Short alt text
            confidence: Confidence score
            embedding: Optional pre-computed embedding

        Returns:
            Image hash key
        """
        if not self.enabled:
            return self.compute_hash(image_data)

        image_hash = self.compute_hash(image_data)

        async with self._lock:
            # Evict oldest entries if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                self._stats.evictions += 1
                logger.debug(f"Cache evicted: {oldest_key[:16]}...")

            # Add new entry
            self._cache[image_hash] = CacheEntry(
                description=description,
                alt_text=alt_text,
                confidence=confidence,
                embedding=embedding
            )
            self._stats.total_entries = len(self._cache)

            logger.debug(
                f"Cache set: {image_hash[:16]}... "
                f"(description: {len(description)} chars)"
            )

        return image_hash

    async def get_or_generate(
        self,
        image_data: bytes,
        generator_func,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get from cache or generate using provided function.

        Args:
            image_data: Raw image bytes
            generator_func: Async function to generate description
            context: Optional context for generation

        Returns:
            Description result (from cache or freshly generated)
        """
        # Try cache first
        cached = await self.get(image_data)
        if cached:
            return cached

        # Generate new description
        result = await generator_func(image_data, context)

        # Cache the result if successful
        if result.get("description"):
            await self.set(
                image_data=image_data,
                description=result.get("description", ""),
                alt_text=result.get("alt_text", ""),
                confidence=result.get("confidence", 0.0),
                embedding=result.get("embedding")
            )

        return result

    async def invalidate(self, image_data: bytes) -> bool:
        """
        Remove specific entry from cache.

        Args:
            image_data: Raw image bytes

        Returns:
            True if entry was removed, False if not found
        """
        image_hash = self.compute_hash(image_data)

        async with self._lock:
            if image_hash in self._cache:
                del self._cache[image_hash]
                self._stats.total_entries = len(self._cache)
                return True
            return False

    async def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.total_entries = 0
            logger.info(f"Cache cleared: {count} entries removed")
            return count

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired(self.ttl_seconds)
            ]

            for key in expired_keys:
                del self._cache[key]
                self._stats.evictions += 1

            self._stats.total_entries = len(self._cache)

            if expired_keys:
                logger.info(f"Cache cleanup: {len(expired_keys)} expired entries removed")

            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._stats.to_dict()

    async def get_entries_info(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get information about cached entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of entry info dicts
        """
        async with self._lock:
            entries = []
            for i, (hash_key, entry) in enumerate(self._cache.items()):
                if i >= limit:
                    break
                entries.append({
                    "hash": hash_key[:16] + "...",
                    "description_length": len(entry.description),
                    "confidence": entry.confidence,
                    "access_count": entry.access_count,
                    "age_seconds": int(time.time() - entry.created_at),
                    "has_embedding": entry.embedding is not None
                })
            return entries


# Global cache instance
_global_cache: Optional[VLMImageCache] = None


def get_vlm_image_cache() -> VLMImageCache:
    """Get or create global VLM image cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = VLMImageCache()
    return _global_cache


def reset_vlm_image_cache():
    """Reset global cache (useful for testing)."""
    global _global_cache
    _global_cache = None
