"""
Product Context Memory Service

LangGraph Store 기반의 제품 라우팅 컨텍스트 영속 서비스.
Agentic RAG의 Auto 모드에서 이전 대화의 제품 컨텍스트를 기억합니다.

Deep Agents의 Long-term Memory 패턴 활용:
- InMemoryStore (개발용) 또는 PostgresStore (프로덕션) 사용
- 사용자/세션별 네임스페이스 분리
"""
import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# LangGraph Store import
try:
    from langgraph.store.memory import InMemoryStore
    STORE_AVAILABLE = True
except ImportError:
    STORE_AVAILABLE = False
    logger.warning("LangGraph store not available, product context memory disabled")


@dataclass
class ProductContext:
    """제품 라우팅 컨텍스트"""
    product_id: str
    query: str
    confidence: float
    timestamp: float = field(default_factory=time.time)


class ProductContextMemory:
    """
    제품 라우팅 컨텍스트를 영속 저장하는 메모리 서비스.

    LangGraph Store를 활용하여 사용자별/세션별로
    이전에 라우팅된 제품 정보를 저장하고 조회합니다.

    네임스페이스 구조:
      ("product_context", {user_id}, {session_id}) → key: "history"
      ("product_context", {user_id}, "global")     → key: "recent"
    """

    # 최대 저장 컨텍스트 수
    MAX_SESSION_HISTORY = 10
    MAX_GLOBAL_RECENT = 5
    # 글로벌 컨텍스트 유효 시간 (초) - 1시간
    GLOBAL_CONTEXT_TTL = 3600

    def __init__(self, store=None):
        if store is not None:
            self._store = store
        elif STORE_AVAILABLE:
            self._store = InMemoryStore()
        else:
            self._store = None
            logger.warning("No store available, product context memory is disabled")

    @property
    def available(self) -> bool:
        return self._store is not None

    def save_product_context(
        self,
        user_id: str,
        session_id: str,
        product_id: str,
        query: str,
        confidence: float = 1.0,
    ) -> None:
        """
        제품 라우팅 결과를 저장합니다.

        Args:
            user_id: 사용자 ID
            session_id: 세션/대화 ID
            product_id: 라우팅된 제품 ID
            query: 사용자 질문
            confidence: 라우팅 confidence
        """
        if not self.available:
            return

        try:
            now = time.time()
            entry = {
                "product_id": product_id,
                "query": query[:200],  # 쿼리 길이 제한
                "confidence": confidence,
                "timestamp": now,
            }

            # 1. 세션별 이력 저장
            namespace = ("product_context", user_id, session_id)
            existing = self._store.get(namespace, "history")
            history: List[Dict] = []
            if existing and hasattr(existing, 'value'):
                history = existing.value.get("entries", [])
            elif isinstance(existing, dict):
                history = existing.get("entries", [])

            history.append(entry)
            # 최대 개수 유지
            if len(history) > self.MAX_SESSION_HISTORY:
                history = history[-self.MAX_SESSION_HISTORY:]

            self._store.put(namespace, "history", {"entries": history})

            # 2. 사용자 글로벌 최근 제품 저장
            global_ns = ("product_context", user_id, "global")
            g_existing = self._store.get(global_ns, "recent")
            recent: List[Dict] = []
            if g_existing and hasattr(g_existing, 'value'):
                recent = g_existing.value.get("entries", [])
            elif isinstance(g_existing, dict):
                recent = g_existing.get("entries", [])

            # TTL 초과 항목 제거
            recent = [r for r in recent if now - r.get("timestamp", 0) < self.GLOBAL_CONTEXT_TTL]
            recent.append(entry)
            if len(recent) > self.MAX_GLOBAL_RECENT:
                recent = recent[-self.MAX_GLOBAL_RECENT:]

            self._store.put(global_ns, "recent", {"entries": recent})

            logger.debug(
                f"[ProductContextMemory] Saved: user={user_id}, "
                f"session={session_id}, product={product_id}, conf={confidence:.2f}"
            )
        except Exception as e:
            logger.error(f"[ProductContextMemory] Failed to save: {e}")

    def get_session_product(
        self,
        user_id: str,
        session_id: str,
    ) -> Optional[str]:
        """
        현재 세션에서 가장 최근에 라우팅된 제품 ID를 반환합니다.

        Args:
            user_id: 사용자 ID
            session_id: 세션/대화 ID

        Returns:
            가장 최근 product_id 또는 None
        """
        if not self.available:
            return None

        try:
            namespace = ("product_context", user_id, session_id)
            existing = self._store.get(namespace, "history")
            entries: List[Dict] = []
            if existing and hasattr(existing, 'value'):
                entries = existing.value.get("entries", [])
            elif isinstance(existing, dict):
                entries = existing.get("entries", [])

            if entries:
                return entries[-1].get("product_id")
            return None
        except Exception as e:
            logger.error(f"[ProductContextMemory] Failed to get session product: {e}")
            return None

    def get_session_history(
        self,
        user_id: str,
        session_id: str,
    ) -> List[ProductContext]:
        """
        현재 세션의 전체 제품 라우팅 이력을 반환합니다.

        Returns:
            ProductContext 리스트 (시간순)
        """
        if not self.available:
            return []

        try:
            namespace = ("product_context", user_id, session_id)
            existing = self._store.get(namespace, "history")
            entries: List[Dict] = []
            if existing and hasattr(existing, 'value'):
                entries = existing.value.get("entries", [])
            elif isinstance(existing, dict):
                entries = existing.get("entries", [])

            return [
                ProductContext(
                    product_id=e["product_id"],
                    query=e.get("query", ""),
                    confidence=e.get("confidence", 0.0),
                    timestamp=e.get("timestamp", 0.0),
                )
                for e in entries
            ]
        except Exception as e:
            logger.error(f"[ProductContextMemory] Failed to get session history: {e}")
            return []

    def get_recent_product(
        self,
        user_id: str,
    ) -> Optional[str]:
        """
        사용자의 글로벌 최근 제품을 반환합니다 (세션 무관).

        TTL 내의 가장 최근 제품을 반환합니다.
        """
        if not self.available:
            return None

        try:
            global_ns = ("product_context", user_id, "global")
            existing = self._store.get(global_ns, "recent")
            entries: List[Dict] = []
            if existing and hasattr(existing, 'value'):
                entries = existing.value.get("entries", [])
            elif isinstance(existing, dict):
                entries = existing.get("entries", [])

            now = time.time()
            valid = [
                e for e in entries
                if now - e.get("timestamp", 0) < self.GLOBAL_CONTEXT_TTL
            ]

            if valid:
                return valid[-1].get("product_id")
            return None
        except Exception as e:
            logger.error(f"[ProductContextMemory] Failed to get recent product: {e}")
            return None

    def get_frequent_products(
        self,
        user_id: str,
        top_k: int = 3,
    ) -> List[str]:
        """
        사용자가 자주 질문하는 제품 목록 (빈도순).
        """
        if not self.available:
            return []

        try:
            global_ns = ("product_context", user_id, "global")
            existing = self._store.get(global_ns, "recent")
            entries: List[Dict] = []
            if existing and hasattr(existing, 'value'):
                entries = existing.value.get("entries", [])
            elif isinstance(existing, dict):
                entries = existing.get("entries", [])

            # 빈도 카운트
            counts: Dict[str, int] = {}
            for e in entries:
                pid = e.get("product_id", "")
                if pid:
                    counts[pid] = counts.get(pid, 0) + 1

            sorted_products = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            return [pid for pid, _ in sorted_products[:top_k]]
        except Exception as e:
            logger.error(f"[ProductContextMemory] Failed to get frequent products: {e}")
            return []


# =============================================================================
# Singleton
# =============================================================================

_instance: Optional[ProductContextMemory] = None


def get_product_context_memory(store=None) -> ProductContextMemory:
    """Get singleton ProductContextMemory"""
    global _instance
    if _instance is None:
        _instance = ProductContextMemory(store=store)
    return _instance
