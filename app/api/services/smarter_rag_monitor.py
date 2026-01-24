"""
Smarter RAG Monitoring Service

Smarter RAG 시스템의 실시간 모니터링 및 메트릭 수집.

Metrics:
- Verified Knowledge Store 통계
- Learning LLM 상태
- Training 현황
- 응답 전략 분포
- 피드백 트렌드
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class SmarterRAGMetrics:
    """Smarter RAG 메트릭"""
    timestamp: datetime = field(default_factory=datetime.now)

    # Verified Knowledge Store
    vk_total_count: int = 0
    vk_active_count: int = 0
    vk_trained_count: int = 0
    vk_pending_training: int = 0
    vk_pending_unlearn: int = 0
    vk_avg_feedback_score: float = 0.0

    # Learning LLM
    llm_enabled: bool = False
    llm_loaded: bool = False
    llm_current_adapter: Optional[str] = None
    llm_available_adapters: int = 0

    # Training
    training_last_run: Optional[datetime] = None
    training_last_status: Optional[str] = None
    training_total_batches: int = 0
    training_successful_batches: int = 0

    # Response Strategy Distribution (last 24h)
    strategy_verified_knowledge: int = 0
    strategy_learning_llm: int = 0
    strategy_vector: int = 0
    strategy_graph: int = 0
    strategy_hybrid: int = 0
    strategy_code: int = 0

    # Feedback Trends (last 24h)
    feedback_thumbs_up: int = 0
    feedback_thumbs_down: int = 0
    feedback_ratio: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        if self.training_last_run:
            result["training_last_run"] = self.training_last_run.isoformat()
        return result


class SmarterRAGMonitor:
    """
    Smarter RAG 모니터링 서비스

    실시간으로 시스템 상태를 모니터링하고 메트릭을 수집합니다.
    """

    def __init__(self):
        self._metrics_cache: Optional[SmarterRAGMetrics] = None
        self._cache_ttl = 30  # seconds
        self._last_fetch_time: Optional[datetime] = None
        self._strategy_counter: Dict[str, int] = defaultdict(int)
        self._feedback_counter: Dict[str, int] = defaultdict(int)

    async def get_metrics(self, force_refresh: bool = False) -> SmarterRAGMetrics:
        """
        현재 메트릭 조회

        Args:
            force_refresh: 캐시 무시하고 새로 수집

        Returns:
            현재 메트릭
        """
        now = datetime.now()

        # Check cache
        if not force_refresh and self._metrics_cache and self._last_fetch_time:
            if (now - self._last_fetch_time).total_seconds() < self._cache_ttl:
                return self._metrics_cache

        # Collect new metrics
        metrics = SmarterRAGMetrics(timestamp=now)

        # 1. Verified Knowledge Stats
        await self._collect_vk_metrics(metrics)

        # 2. Learning LLM Status
        await self._collect_llm_metrics(metrics)

        # 3. Training Status
        await self._collect_training_metrics(metrics)

        # 4. Strategy Distribution
        self._collect_strategy_metrics(metrics)

        # 5. Feedback Trends
        await self._collect_feedback_metrics(metrics)

        # Update cache
        self._metrics_cache = metrics
        self._last_fetch_time = now

        return metrics

    async def _collect_vk_metrics(self, metrics: SmarterRAGMetrics):
        """Verified Knowledge 메트릭 수집"""
        try:
            from .verified_knowledge_service import get_verified_knowledge_service
            vk_service = get_verified_knowledge_service()

            if vk_service:
                stats = await vk_service.get_stats()
                metrics.vk_total_count = stats.get("total_count", 0)
                metrics.vk_active_count = stats.get("active_count", 0)
                metrics.vk_trained_count = stats.get("trained_count", 0)
                metrics.vk_pending_training = stats.get("pending_training_count", 0)
                metrics.vk_pending_unlearn = stats.get("unlearn_pending_count", 0)
                metrics.vk_avg_feedback_score = stats.get("avg_feedback_score", 0.0)
        except Exception as e:
            logger.warning(f"Failed to collect VK metrics: {e}")

    async def _collect_llm_metrics(self, metrics: SmarterRAGMetrics):
        """Learning LLM 메트릭 수집"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()

            if llm_service:
                status = llm_service.get_status()
                metrics.llm_enabled = status.get("enabled", False)
                metrics.llm_loaded = status.get("is_loaded", False)
                metrics.llm_current_adapter = status.get("current_adapter")
                metrics.llm_available_adapters = len(status.get("available_adapters", []))
        except Exception as e:
            logger.warning(f"Failed to collect LLM metrics: {e}")

    async def _collect_training_metrics(self, metrics: SmarterRAGMetrics):
        """Training 메트릭 수집"""
        try:
            from .verified_knowledge_service import get_verified_knowledge_service
            vk_service = get_verified_knowledge_service()

            if vk_service:
                # Get recent batches
                batches = await vk_service.get_training_batches(limit=100)
                metrics.training_total_batches = len(batches)
                metrics.training_successful_batches = sum(
                    1 for b in batches if b.get("status") == "completed"
                )

                # Get last run info
                if batches:
                    latest = batches[0]
                    metrics.training_last_status = latest.get("status")
                    if latest.get("completed_at"):
                        metrics.training_last_run = datetime.fromisoformat(
                            latest["completed_at"].replace("Z", "+00:00")
                        )
        except Exception as e:
            logger.warning(f"Failed to collect training metrics: {e}")

    def _collect_strategy_metrics(self, metrics: SmarterRAGMetrics):
        """Strategy 분포 메트릭 수집 (인메모리 카운터 기반)"""
        metrics.strategy_verified_knowledge = self._strategy_counter.get("verified_knowledge", 0)
        metrics.strategy_learning_llm = self._strategy_counter.get("learning_llm", 0)
        metrics.strategy_vector = self._strategy_counter.get("vector", 0)
        metrics.strategy_graph = self._strategy_counter.get("graph", 0)
        metrics.strategy_hybrid = self._strategy_counter.get("hybrid", 0)
        metrics.strategy_code = self._strategy_counter.get("code", 0)

    async def _collect_feedback_metrics(self, metrics: SmarterRAGMetrics):
        """Feedback 트렌드 메트릭 수집"""
        try:
            from ..repositories.user_feedback_repository import get_user_feedback_repository
            repo = get_user_feedback_repository()

            if repo:
                # Get 24h feedback stats
                since = datetime.now() - timedelta(hours=24)
                stats = await repo.get_feedback_stats(since=since)

                metrics.feedback_thumbs_up = stats.get("thumbs_up", 0)
                metrics.feedback_thumbs_down = stats.get("thumbs_down", 0)

                total = metrics.feedback_thumbs_up + metrics.feedback_thumbs_down
                if total > 0:
                    metrics.feedback_ratio = metrics.feedback_thumbs_up / total
        except Exception as e:
            logger.warning(f"Failed to collect feedback metrics: {e}")

    def record_strategy(self, strategy: str):
        """응답 전략 기록"""
        self._strategy_counter[strategy] += 1

    def record_feedback(self, feedback_type: str):
        """피드백 기록"""
        self._feedback_counter[feedback_type] += 1

    def reset_counters(self):
        """카운터 초기화 (일별 리셋용)"""
        self._strategy_counter.clear()
        self._feedback_counter.clear()

    async def get_health_status(self) -> Dict[str, Any]:
        """
        시스템 헬스 상태 조회

        Returns:
            헬스 상태 정보
        """
        metrics = await self.get_metrics()

        # Determine overall health
        issues = []

        # Check VK health
        if metrics.vk_pending_training > 100:
            issues.append("High pending training count")

        if metrics.vk_pending_unlearn > 50:
            issues.append("High pending unlearn count")

        # Check LLM health
        if metrics.llm_enabled and not metrics.llm_loaded:
            issues.append("Learning LLM enabled but not loaded")

        # Check feedback health
        if metrics.feedback_ratio < 0.5 and (metrics.feedback_thumbs_up + metrics.feedback_thumbs_down) > 10:
            issues.append("Low feedback ratio (< 50%)")

        status = "healthy" if not issues else "degraded"

        return {
            "status": status,
            "issues": issues,
            "metrics_summary": {
                "vk_active": metrics.vk_active_count,
                "vk_trained": metrics.vk_trained_count,
                "llm_ready": metrics.llm_enabled and metrics.llm_loaded,
                "feedback_ratio": f"{metrics.feedback_ratio * 100:.1f}%",
            },
            "timestamp": datetime.now().isoformat(),
        }

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """
        대시보드용 데이터 조회

        Returns:
            대시보드에 표시할 데이터
        """
        metrics = await self.get_metrics()

        return {
            "overview": {
                "verified_knowledge": {
                    "total": metrics.vk_total_count,
                    "active": metrics.vk_active_count,
                    "trained": metrics.vk_trained_count,
                    "pending_training": metrics.vk_pending_training,
                    "pending_unlearn": metrics.vk_pending_unlearn,
                    "avg_score": f"{metrics.vk_avg_feedback_score * 100:.1f}%",
                },
                "learning_llm": {
                    "enabled": metrics.llm_enabled,
                    "loaded": metrics.llm_loaded,
                    "adapter": metrics.llm_current_adapter,
                    "available_adapters": metrics.llm_available_adapters,
                },
                "training": {
                    "total_batches": metrics.training_total_batches,
                    "successful": metrics.training_successful_batches,
                    "last_run": metrics.training_last_run.isoformat() if metrics.training_last_run else None,
                    "last_status": metrics.training_last_status,
                },
            },
            "strategy_distribution": {
                "verified_knowledge": metrics.strategy_verified_knowledge,
                "learning_llm": metrics.strategy_learning_llm,
                "vector": metrics.strategy_vector,
                "graph": metrics.strategy_graph,
                "hybrid": metrics.strategy_hybrid,
                "code": metrics.strategy_code,
            },
            "feedback_trends": {
                "thumbs_up": metrics.feedback_thumbs_up,
                "thumbs_down": metrics.feedback_thumbs_down,
                "ratio": f"{metrics.feedback_ratio * 100:.1f}%",
            },
            "timestamp": datetime.now().isoformat(),
        }


# ============================================
# Singleton Instance
# ============================================

_monitor: Optional[SmarterRAGMonitor] = None


def get_smarter_rag_monitor() -> SmarterRAGMonitor:
    """Get Smarter RAG monitor singleton"""
    global _monitor
    if _monitor is None:
        _monitor = SmarterRAGMonitor()
    return _monitor


def initialize_smarter_rag_monitor() -> SmarterRAGMonitor:
    """Initialize Smarter RAG monitor"""
    global _monitor
    _monitor = SmarterRAGMonitor()
    logger.info("Smarter RAG monitor initialized")
    return _monitor
