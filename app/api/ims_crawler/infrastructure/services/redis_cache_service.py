"""
Redis-based cache service implementation
"""
import json
import pickle
from typing import Optional, Any
from datetime import timedelta
import redis.asyncio as redis
from redis.asyncio import Redis

from ...domain.ports.cache_port import CachePort


class RedisCacheService(CachePort):
    """Redis implementation of cache service"""

    def __init__(
        self,
        redis_client: Redis,
        key_prefix: str = "ims:",
        default_ttl: timedelta = timedelta(hours=1)
    ):
        """
        Initialize Redis cache service

        Args:
            redis_client: Redis async client
            key_prefix: Prefix for all cache keys
            default_ttl: Default time to live
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl

    def _make_key(self, key: str) -> str:
        """Create prefixed cache key"""
        return f"{self.key_prefix}{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache"""
        try:
            full_key = self._make_key(key)
            value = await self.redis.get(full_key)

            if value is None:
                return None

            # Try JSON first (for simple types)
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Fall back to pickle for complex objects
                return pickle.loads(value)

        except Exception as e:
            print(f"Cache get error for key {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """Set value in Redis cache"""
        try:
            full_key = self._make_key(key)
            expiration = ttl or self.default_ttl

            # Try JSON first (more efficient and readable)
            try:
                serialized = json.dumps(value)
            except (TypeError, ValueError):
                # Fall back to pickle for complex objects
                serialized = pickle.dumps(value)

            await self.redis.set(
                full_key,
                serialized,
                ex=int(expiration.total_seconds())
            )
            return True

        except Exception as e:
            print(f"Cache set error for key {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete value from Redis cache"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.delete(full_key)
            return result > 0

        except Exception as e:
            print(f"Cache delete error for key {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache"""
        try:
            full_key = self._make_key(key)
            result = await self.redis.exists(full_key)
            return result > 0

        except Exception as e:
            print(f"Cache exists error for key {key}: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern"""
        try:
            full_pattern = self._make_key(pattern)
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=full_pattern,
                    count=100
                )

                if keys:
                    deleted += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            return deleted

        except Exception as e:
            print(f"Cache clear pattern error for {pattern}: {e}")
            return 0

    async def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for key"""
        try:
            full_key = self._make_key(key)
            ttl = await self.redis.ttl(full_key)

            # -2 means key doesn't exist, -1 means no expiration
            if ttl < 0:
                return None

            return ttl

        except Exception as e:
            print(f"Cache get_ttl error for key {key}: {e}")
            return None

    async def close(self):
        """Close Redis connection"""
        await self.redis.close()


class InMemoryCacheService(CachePort):
    """
    In-memory cache fallback (when Redis is unavailable)
    Simple dictionary-based cache for development/testing
    """

    def __init__(self, default_ttl: timedelta = timedelta(hours=1)):
        self.cache: dict = {}
        self.default_ttl = default_ttl

    async def get(self, key: str) -> Optional[Any]:
        """Get value from memory cache"""
        return self.cache.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[timedelta] = None
    ) -> bool:
        """Set value in memory cache"""
        self.cache[key] = value
        return True

    async def delete(self, key: str) -> bool:
        """Delete value from memory cache"""
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in memory cache"""
        return key in self.cache

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern (simple wildcard)"""
        # Simple pattern matching (only supports suffix wildcard)
        if pattern.endswith('*'):
            prefix = pattern[:-1]
            keys_to_delete = [k for k in self.cache.keys() if k.startswith(prefix)]
        else:
            keys_to_delete = [k for k in self.cache.keys() if k == pattern]

        for key in keys_to_delete:
            del self.cache[key]

        return len(keys_to_delete)

    async def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL (not supported in memory cache)"""
        return None

    async def close(self):
        """Close connection (no-op for memory cache)"""
        self.cache.clear()
