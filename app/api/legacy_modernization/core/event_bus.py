"""Event Bus for inter-agent communication (Redis Streams or in-memory fallback).

Features:
- 10 named streams (orchestrator, domain experts, reviewer, qa, etc.)
- Consumer group based subscription (at-least-once delivery) when Redis available
- In-memory queue fallback when Redis unavailable
- Audit trail dual-write (every message -> audit stream)
- Dead letter stream for failed processing
"""

import json
import logging
from collections import defaultdict
from typing import Any, AsyncGenerator, Optional

from ..core.errors import EventBusError
from ..core.protocol import AgentMessage

logger = logging.getLogger(__name__)


# Named streams for each agent role / purpose
STREAMS: dict[str, str] = {
    "orchestrator": "stream:orchestrator",
    "domain_expert": "stream:domain_expert",
    "legacy_knowledge": "stream:legacy_knowledge",
    "reviewer": "stream:reviewer",
    "qa": "stream:qa",
    "e2e_test": "stream:e2e_test",
    "risk_intel": "stream:risk_intel",
    "competitor_intel": "stream:competitor_intel",
    "audit": "stream:audit",
    "deadletter": "stream:deadletter",
}


class EventBus:
    """에이전트 간 통신 버스 (Redis Streams or in-memory fallback)."""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._use_memory: bool = False
        self._memory_streams: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        self._msg_counter: int = 0

    async def _get_redis(self) -> Any:
        if self._use_memory:
            return None
        if self._redis is None:
            try:
                import asyncio
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_timeout=2,
                    socket_connect_timeout=2,
                )
                await asyncio.wait_for(self._redis.ping(), timeout=3)
                logger.info("EventBus: connected to Redis at %s", self._redis_url)
            except Exception:
                logger.warning("EventBus: Redis unavailable, using in-memory fallback")
                self._use_memory = True
                if self._redis:
                    try:
                        await self._redis.close()
                    except Exception:
                        pass
                self._redis = None
                return None
        return self._redis

    @staticmethod
    def stream_key(stream: str) -> str:
        """스트림 이름 -> Redis key 변환."""
        return STREAMS.get(stream, f"stream:{stream}")

    async def publish(self, stream: str, message: AgentMessage) -> str:
        """메시지 발행 -> 감사 추적 동시 기록.

        Returns:
            Message ID (Redis Stream ID or in-memory counter).
        """
        r = await self._get_redis()
        stream_key = self.stream_key(stream)

        if r:
            try:
                msg_id = await r.xadd(
                    stream_key,
                    {"data": message.model_dump_json()},
                )
            except Exception as exc:
                raise EventBusError(f"Failed to publish to {stream_key}: {exc}") from exc

            # 감사 추적 동시 기록 (audit stream)
            try:
                await r.xadd(
                    STREAMS["audit"],
                    {
                        "data": json.dumps({
                            "msg_id": msg_id,
                            "sender": message.sender.role.value,
                            "recipient": message.recipient.role.value,
                            "type": message.message_type.value,
                            "correlation_id": message.correlation_id,
                            "timestamp": message.timestamp.isoformat(),
                        }),
                    },
                )
            except Exception:
                logger.warning("Failed to write audit for msg %s", msg_id, exc_info=True)
        else:
            # In-memory fallback
            self._msg_counter += 1
            msg_id = f"mem-{self._msg_counter}"
            self._memory_streams[stream_key].append(
                (msg_id, {"data": message.model_dump_json()})
            )

        logger.debug(
            "Published %s -> %s [%s]",
            message.sender.role.value, stream_key, msg_id,
        )
        return msg_id

    async def subscribe(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 1,
        block_ms: int = 5000,
    ) -> AsyncGenerator[tuple[str, AgentMessage], None]:
        """Consumer Group 기반 구독 (at-least-once delivery)."""
        r = await self._get_redis()
        stream_key = self.stream_key(stream)

        if not r:
            # In-memory: yield any queued messages then return
            messages = self._memory_streams.get(stream_key, [])
            while messages:
                msg_id, data = messages.pop(0)
                try:
                    raw = data.get("data", "{}")
                    message = AgentMessage.model_validate_json(raw)
                    yield (msg_id, message)
                except Exception as exc:
                    logger.error("Failed to process in-memory msg %s: %s", msg_id, exc)
            return

        # Redis consumer group
        try:
            await r.xgroup_create(stream_key, consumer_group, id="0", mkstream=True)
        except Exception:
            pass  # BUSYGROUP -- already exists

        while True:
            try:
                messages = await r.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {stream_key: ">"},
                    count=count,
                    block=block_ms,
                )
            except Exception as exc:
                logger.error("xreadgroup error on %s: %s", stream_key, exc)
                raise EventBusError(f"Subscribe error on {stream_key}: {exc}") from exc

            if not messages:
                continue

            for _, msg_list in messages:
                for msg_id, data in msg_list:
                    try:
                        raw = data.get("data", "{}")
                        message = AgentMessage.model_validate_json(raw)
                        yield (msg_id, message)
                        await r.xack(stream_key, consumer_group, msg_id)
                    except Exception as exc:
                        logger.error(
                            "Failed to process msg %s from %s: %s",
                            msg_id, stream_key, exc,
                        )
                        await self._send_to_deadletter(r, stream_key, msg_id, data, str(exc))
                        await r.xack(stream_key, consumer_group, msg_id)

    async def read_pending(
        self,
        stream: str,
        consumer_group: str,
        consumer_name: str,
        count: int = 10,
    ) -> list[tuple[str, dict]]:
        """미처리 pending 메시지 조회 (재시도용)."""
        r = await self._get_redis()
        if not r:
            return []
        stream_key = self.stream_key(stream)
        try:
            messages = await r.xreadgroup(
                consumer_group,
                consumer_name,
                {stream_key: "0"},
                count=count,
            )
            result = []
            for _, msg_list in messages:
                for msg_id, data in msg_list:
                    result.append((msg_id, data))
            return result
        except Exception:
            return []

    async def stream_length(self, stream: str) -> int:
        """스트림 길이 조회."""
        r = await self._get_redis()
        if not r:
            stream_key = self.stream_key(stream)
            return len(self._memory_streams.get(stream_key, []))
        stream_key = self.stream_key(stream)
        try:
            return await r.xlen(stream_key)
        except Exception:
            return 0

    async def trim_stream(self, stream: str, maxlen: int = 10000) -> int:
        """스트림 크기 제한 (오래된 메시지 제거)."""
        r = await self._get_redis()
        if not r:
            return 0
        stream_key = self.stream_key(stream)
        try:
            return await r.xtrim(stream_key, maxlen=maxlen, approximate=True)
        except Exception:
            return 0

    async def _send_to_deadletter(
        self,
        redis: Any,
        source_stream: str,
        msg_id: str,
        data: dict,
        error: str,
    ) -> None:
        """처리 실패 메시지를 dead letter stream으로 이동."""
        try:
            await redis.xadd(
                STREAMS["deadletter"],
                {
                    "source_stream": source_stream,
                    "original_msg_id": msg_id,
                    "data": json.dumps(data) if isinstance(data, dict) else str(data),
                    "error": error,
                },
            )
        except Exception:
            logger.error("Failed to write to deadletter stream", exc_info=True)

    async def close(self) -> None:
        """Redis 연결 해제."""
        if self._redis:
            await self._redis.close()
            self._redis = None
