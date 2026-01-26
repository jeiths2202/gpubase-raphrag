"""
Learning LLM Service

QLoRA 파인튜닝된 모델을 통한 추론 서비스.
Verified Knowledge Store에서 학습된 지식을 기반으로 응답을 생성합니다.

Priority Order (Smarter RAG):
1. Verified Knowledge Store - 정확히 일치하는 검증된 답변 (similarity >= 0.85)
2. Learning LLM - 학습된 패턴 기반 새로운 응답 생성 (similarity 0.5-0.85)
3. General RAG - 문서 기반 검색 및 생성

Adapter Modes:
- vLLM (권장): 외부 vLLM 컨테이너 연결 (GPU 메모리 효율, 동적 LoRA 로딩)
- Local: 로컬 BitsAndBytes 로딩 (GPU 직접 접근 필요)
"""
import os
import logging
import asyncio
from typing import Optional, Dict, Any, Tuple, AsyncGenerator
from pathlib import Path

logger = logging.getLogger(__name__)


class LearningLLMService:
    """
    Learning LLM 서비스

    QLoRA 파인튜닝된 모델을 사용하여 학습된 도메인 지식 기반 응답을 생성합니다.

    Supports two adapter modes:
    - vLLM (기본): 외부 vLLM 컨테이너에 연결 (권장)
    - Local: 로컬 GPU에서 BitsAndBytes로 로딩
    """

    def __init__(
        self,
        base_model: str = "Qwen/Qwen2.5-7B-Instruct",
        adapter_dir: str = "/opt/kms/models/qlora_adapters",
        auto_load: bool = False,
        enabled: bool = True,
        use_vllm: bool = True,  # vLLM 어댑터 사용 (기본값)
        vllm_url: Optional[str] = None,
        vllm_model: str = "learning",  # vLLM LoRA 어댑터 이름
    ):
        self.base_model = base_model
        self.adapter_dir = Path(adapter_dir)
        self.auto_load = auto_load
        self.enabled = enabled
        self.use_vllm = use_vllm
        self.vllm_url = vllm_url or os.getenv(
            "LEARNING_LLM_URL",
            "http://learning-llm-graphrag:8000/v1"
        )
        self.vllm_model = vllm_model

        self._adapter = None
        self._is_initialized = False
        self._initialization_lock = asyncio.Lock()

        # Confidence thresholds
        self.min_confidence_threshold = 0.6  # Learning LLM 응답 사용 최소 신뢰도
        self.high_confidence_threshold = 0.8  # 고신뢰도 응답 (RAG 스킵 가능)

    async def initialize(self) -> bool:
        """
        서비스 초기화 (어댑터 로드)

        Returns:
            초기화 성공 여부
        """
        if not self.enabled:
            logger.info("Learning LLM service is disabled")
            return False

        async with self._initialization_lock:
            if self._is_initialized:
                return True

            try:
                # vLLM 모드: 외부 컨테이너 연결
                if self.use_vllm:
                    from ..adapters.learning_llm.vllm_adapter import VLLMAdapter

                    self._adapter = VLLMAdapter(
                        base_url=self.vllm_url,
                        model=self.vllm_model,
                    )

                    # 연결 확인
                    loaded = await self._adapter.load()
                    if loaded:
                        self._is_initialized = True
                        logger.info(f"Learning LLM initialized with vLLM: {self.vllm_url} (model: {self.vllm_model})")
                        return True
                    else:
                        logger.warning(f"Failed to connect to vLLM server: {self.vllm_url}")
                        return False

                # Local 모드: 로컬 GPU에서 로딩
                # Check if adapters exist
                if not self.adapter_dir.exists():
                    logger.warning(f"Adapter directory not found: {self.adapter_dir}")
                    return False

                adapters = list(self.adapter_dir.glob("qlora_*"))
                if not adapters:
                    logger.info("No trained adapters available yet")
                    return False

                if self.auto_load:
                    # Import adapter
                    from ..adapters.learning_llm.adapter import LearningLLMAdapter

                    self._adapter = LearningLLMAdapter(
                        base_model=self.base_model,
                    )

                    # Load latest adapter
                    loaded = await self._adapter.load()
                    if loaded:
                        self._is_initialized = True
                        logger.info(f"Learning LLM initialized with local adapter: {self._adapter.current_adapter}")
                        return True
                    else:
                        logger.warning("Failed to load Learning LLM adapter")
                        return False
                else:
                    # Lazy loading - will load on first request
                    self._is_initialized = True
                    logger.info("Learning LLM service initialized (lazy loading enabled)")
                    return True

            except Exception as e:
                logger.error(f"Failed to initialize Learning LLM: {e}")
                return False

    async def _ensure_loaded(self) -> bool:
        """어댑터가 로드되었는지 확인하고, 필요시 로드"""
        if self._adapter and self._adapter.is_loaded:
            return True

        if not self._is_initialized:
            await self.initialize()

        if self._adapter is None:
            if self.use_vllm:
                from ..adapters.learning_llm.vllm_adapter import VLLMAdapter
                self._adapter = VLLMAdapter(
                    base_url=self.vllm_url,
                    model=self.vllm_model,
                )
            else:
                from ..adapters.learning_llm.adapter import LearningLLMAdapter
                self._adapter = LearningLLMAdapter(base_model=self.base_model)

        if not self._adapter.is_loaded:
            return await self._adapter.load()

        return self._adapter.is_loaded

    async def generate(
        self,
        question: str,
        context: Optional[str] = None,
        verified_knowledge_hint: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> Optional[Dict[str, Any]]:
        """
        Learning LLM으로 응답 생성

        Args:
            question: 사용자 질문
            context: 추가 컨텍스트 (관련 Verified Knowledge 등)
            verified_knowledge_hint: 관련 검증된 지식 힌트
            max_tokens: 최대 생성 토큰
            temperature: 샘플링 온도

        Returns:
            생성된 응답 및 메타데이터, 또는 None (실패 시)
        """
        if not self.enabled:
            return None

        try:
            if not await self._ensure_loaded():
                logger.warning("Learning LLM not loaded, skipping generation")
                return None

            # Build context with verified knowledge hint
            full_context = context or ""
            if verified_knowledge_hint:
                full_context = f"Related verified knowledge:\n{verified_knowledge_hint}\n\n{full_context}"

            # Generate response
            response = await self._adapter.generate(
                question=question,
                context=full_context if full_context else None,
                max_new_tokens=max_tokens,
                temperature=temperature,
            )

            if not response or len(response.strip()) < 10:
                return None

            return {
                "answer": response,
                "source": "learning_llm",
                "adapter": self._adapter.current_adapter,
                "model": self.base_model,
            }

        except Exception as e:
            logger.error(f"Learning LLM generation failed: {e}")
            return None

    async def generate_stream(
        self,
        question: str,
        context: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """
        스트리밍 응답 생성

        Yields:
            생성된 토큰들
        """
        if not self.enabled:
            return

        try:
            if not await self._ensure_loaded():
                return

            async for token in self._adapter.generate_stream(
                question=question,
                context=context,
                max_new_tokens=max_tokens,
                temperature=temperature,
            ):
                yield token

        except Exception as e:
            logger.error(f"Learning LLM streaming failed: {e}")

    async def can_answer(
        self,
        question: str,
        verified_knowledge_service=None,
    ) -> Tuple[bool, Optional[str], float]:
        """
        Learning LLM이 이 질문에 답할 수 있는지 확인

        Verified Knowledge Store에서 관련 지식이 있는지 확인하여
        학습된 도메인인지 판단합니다.

        Args:
            question: 사용자 질문
            verified_knowledge_service: VK 서비스 (관련 지식 검색용)

        Returns:
            (can_answer, related_knowledge_hint, confidence)
        """
        if not self.enabled or not self._is_initialized:
            return False, None, 0.0

        try:
            # Check if there's related verified knowledge (lower threshold)
            if verified_knowledge_service:
                related = await verified_knowledge_service.search(
                    query=question,
                    limit=3,
                    min_similarity=0.5,  # Lower threshold for "related" knowledge
                )

                if related:
                    # Calculate confidence based on similarity and count
                    avg_similarity = sum(r.get("similarity", 0.5) for r in related) / len(related)
                    knowledge_count_factor = min(len(related) / 3, 1.0)
                    confidence = avg_similarity * 0.7 + knowledge_count_factor * 0.3

                    # Build hint from related knowledge
                    hints = []
                    for r in related[:2]:
                        if "question" in r and "answer" in r:
                            hints.append(f"Q: {r['question'][:100]}\nA: {r['answer'][:200]}")

                    hint = "\n\n".join(hints) if hints else None

                    return confidence >= self.min_confidence_threshold, hint, confidence

            # If no VK service, check if adapter is loaded (basic check)
            if self._adapter and self._adapter.is_loaded:
                return True, None, 0.5  # Default confidence when no VK context

            return False, None, 0.0

        except Exception as e:
            logger.error(f"Error checking if Learning LLM can answer: {e}")
            return False, None, 0.0

    async def reload_adapter(self, adapter_name: Optional[str] = None) -> bool:
        """
        어댑터 리로드 (새 학습 완료 후)

        Args:
            adapter_name: 특정 어댑터 이름 (None이면 최신)

        Returns:
            리로드 성공 여부
        """
        if not self._adapter:
            return await self.initialize()

        return await self._adapter.reload_adapter(adapter_name) if adapter_name else await self._adapter.load()

    async def unload(self):
        """어댑터 언로드 (메모리 해제)"""
        if self._adapter:
            await self._adapter.unload()
            self._adapter = None
        self._is_initialized = False
        logger.info("Learning LLM unloaded")

    def get_status(self) -> Dict[str, Any]:
        """서비스 상태 반환"""
        adapter_status = self._adapter.get_status() if self._adapter else None

        # Check available adapters
        available_adapters = []
        if self.adapter_dir.exists():
            available_adapters = [p.name for p in sorted(self.adapter_dir.glob("qlora_*"), reverse=True)]

        return {
            "enabled": self.enabled,
            "is_initialized": self._is_initialized,
            "is_loaded": self._adapter.is_loaded if self._adapter else False,
            "adapter_mode": "vllm" if self.use_vllm else "local",
            "vllm_url": self.vllm_url if self.use_vllm else None,
            "vllm_model": self.vllm_model if self.use_vllm else None,
            "base_model": self.base_model,
            "adapter_dir": str(self.adapter_dir),
            "current_adapter": self._adapter.current_adapter if self._adapter else None,
            "available_adapters": available_adapters[:10],  # Last 10
            "adapter_details": adapter_status,
            "thresholds": {
                "min_confidence": self.min_confidence_threshold,
                "high_confidence": self.high_confidence_threshold,
            }
        }


# ============================================
# Singleton Instance
# ============================================

_learning_llm_service: Optional[LearningLLMService] = None


def get_learning_llm_service() -> Optional[LearningLLMService]:
    """Get Learning LLM service singleton"""
    global _learning_llm_service
    return _learning_llm_service


async def initialize_learning_llm_service(
    base_model: str = "Qwen/Qwen2.5-7B-Instruct",
    adapter_dir: str = "/opt/kms/models/qlora_adapters",
    auto_load: bool = False,
    enabled: bool = True,
    use_vllm: bool = True,
    vllm_url: Optional[str] = None,
    vllm_model: str = "learning",
) -> LearningLLMService:
    """
    Initialize Learning LLM service

    Args:
        base_model: Base model for QLoRA
        adapter_dir: Directory containing trained adapters
        auto_load: Whether to load model immediately
        enabled: Whether the service is enabled
        use_vllm: Whether to use vLLM adapter (recommended)
        vllm_url: vLLM server URL (default: LEARNING_LLM_URL env)
        vllm_model: vLLM model/adapter name (default: "learning")

    Returns:
        Initialized service
    """
    global _learning_llm_service

    _learning_llm_service = LearningLLMService(
        base_model=base_model,
        adapter_dir=adapter_dir,
        auto_load=auto_load,
        enabled=enabled,
        use_vllm=use_vllm,
        vllm_url=vllm_url,
        vllm_model=vllm_model,
    )

    await _learning_llm_service.initialize()

    mode = "vLLM" if use_vllm else "local"
    logger.info(f"Learning LLM service initialized (enabled={enabled}, mode={mode})")
    return _learning_llm_service
