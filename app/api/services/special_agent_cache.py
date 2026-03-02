"""
Special Agent Redis Cache Service

Special Agent 검색 파이프라인 전용 Redis 캐시.
Redis 미연결 시 graceful degradation (캐시 없이 정상 동작).
"""
import hashlib
import logging
from typing import Optional, List

import redis.asyncio as redis

logger = logging.getLogger("kms.special_agent_cache")


class SpecialAgentCache:
    """Special Agent 전용 Redis 캐시. Redis 없으면 graceful skip."""

    def __init__(self, redis_url: str):
        self._redis: Optional[redis.Redis] = None
        self._redis_url = redis_url
        self._available = False

    async def initialize(self):
        """Redis 연결 시도. 실패 시 캐시 비활성화."""
        try:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            self._available = True
            logger.info("SpecialAgentCache: Redis connected")
        except Exception as e:
            logger.warning(f"SpecialAgentCache: Redis unavailable ({e}), caching disabled")
            self._available = False

    async def get(self, key: str) -> Optional[str]:
        if not self._available:
            return None
        try:
            return await self._redis.get(key)
        except Exception:
            return None

    async def set(self, key: str, value: str, ttl_seconds: int = 86400):
        if not self._available:
            return
        try:
            await self._redis.set(key, value, ex=ttl_seconds)
        except Exception:
            pass

    async def close(self):
        if self._redis:
            await self._redis.aclose()

    @staticmethod
    def make_key(prefix: str, query: str, products: Optional[List[str]] = None) -> str:
        content = query.strip().lower()
        if products:
            content += "|" + ",".join(sorted(products))
        h = hashlib.md5(content.encode()).hexdigest()[:12]
        return f"{prefix}:{h}"


# Singleton
_instance: Optional[SpecialAgentCache] = None


def get_special_agent_cache() -> SpecialAgentCache:
    global _instance
    if _instance is None:
        from ..core.config import get_api_settings
        settings = get_api_settings()
        _instance = SpecialAgentCache(settings.REDIS_URL)
    return _instance
