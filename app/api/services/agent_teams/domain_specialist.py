"""
Pattern C: Domain Specialist Team

관련 제품 클러스터의 QLoRA 어댑터들이 동시에 답변 생성.
최고 confidence 답변을 선택.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 관련 제품 클러스터 (하나를 질문하면 관련 제품도 동시 검색)
PRODUCT_CLUSTERS: Dict[str, List[str]] = {
    "openframe_base": ["openframe_base", "openframe_batch", "openframe_osc"],
    "openframe_batch": ["openframe_batch", "openframe_base"],
    "openframe_osc": ["openframe_osc", "openframe_base", "openframe_osi"],
    "openframe_osi": ["openframe_osi", "openframe_osc", "openframe_base"],
    "openframe_hidb": ["openframe_hidb", "openframe_base", "openframe_ndb"],
    "openframe_ndb": ["openframe_ndb", "openframe_base", "openframe_hidb"],
    "openframe_tacf": ["openframe_tacf", "openframe_base"],
    "tibero7": ["tibero7"],
    "jeus": ["jeus", "webtob"],
    "webtob": ["webtob", "jeus"],
    "tmax": ["tmax"],
    "ofasm": ["ofasm", "openframe_base"],
    "ofcobol": ["ofcobol", "openframe_base"],
}


@dataclass
class SpecialistAnswer:
    """하나의 전문가 어댑터 답변"""
    adapter_name: str
    product: str
    answer: str
    confidence: float
    latency_ms: int = 0
    mentioned_codes: List[str] = field(default_factory=list)
    mentioned_terms: List[str] = field(default_factory=list)


class DomainSpecialistTeam:
    """
    여러 제품별 QLoRA 어댑터를 병렬로 실행.
    confidence 기반으로 최적 답변 선택.
    """

    def __init__(
        self,
        max_parallel: int = 3,
        winner_threshold: float = 0.6,
    ):
        self._max_parallel = max_parallel
        self._winner_threshold = winner_threshold

    def get_specialist_products(
        self, primary_product: str, routed_products: List[str]
    ) -> List[str]:
        """
        전문가 어댑터 후보 목록 반환.
        클러스터 + 라우팅된 제품을 합치고 max_parallel로 제한.
        """
        cluster = PRODUCT_CLUSTERS.get(primary_product, [primary_product])
        combined = list(dict.fromkeys(cluster + routed_products))
        return combined[:self._max_parallel]

    async def generate_specialist_answers(
        self,
        query: str,
        context: str,
        specialist_products: List[str],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> List[SpecialistAnswer]:
        """
        여러 전문가 어댑터로 병렬 답변 생성.

        Returns:
            confidence 내림차순 정렬된 답변 리스트
        """
        from ...adapters.learning_llm.vllm_adapter import get_vllm_adapter

        adapter = get_vllm_adapter()
        if not adapter:
            logger.warning("VLLMAdapter not available for specialist team")
            return []

        sem = asyncio.Semaphore(self._max_parallel)

        async def _generate_one(product: str) -> Optional[SpecialistAnswer]:
            async with sem:
                start = time.time()
                try:
                    response = await adapter.generate_with_confidence(
                        question=query,
                        context=context,
                        max_new_tokens=max_tokens,
                        temperature=temperature,
                        product=product,
                    )
                    return SpecialistAnswer(
                        adapter_name=product,
                        product=product,
                        answer=response.answer,
                        confidence=response.confidence,
                        latency_ms=int((time.time() - start) * 1000),
                        mentioned_codes=getattr(response, 'mentioned_codes', []),
                        mentioned_terms=getattr(response, 'mentioned_terms', []),
                    )
                except Exception as e:
                    logger.warning(f"Specialist {product} failed: {e}")
                    return None

        tasks = [_generate_one(p) for p in specialist_products]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        answers = []
        for r in results:
            if isinstance(r, SpecialistAnswer) and r.answer:
                answers.append(r)

        answers.sort(key=lambda a: a.confidence, reverse=True)
        return answers

    def select_winner(
        self, answers: List[SpecialistAnswer]
    ) -> Optional[SpecialistAnswer]:
        """confidence 기반 승자 선택"""
        if not answers:
            return None
        if len(answers) == 1:
            return answers[0]
        return answers[0] if answers[0].confidence >= self._winner_threshold else answers[0]
