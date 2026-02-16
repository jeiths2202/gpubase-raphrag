"""
Query Router Service

다단계 확인 질문 라우터.
기존 ProductRouterService를 래핑하여 다단계 확인 로직(확정/되묻기/매칭없음)을 추가합니다.
ManualRegistryService에서 동적 제품 목록을 사용합니다.
"""
import logging
import re
from typing import Dict, List, Optional

from ..models.agentic_rag import (
    RouterResult,
    RouterDecision,
    ClarificationCandidate,
)
from .product_router_service import (
    get_product_router_service,
    ProductRouterService,
)

logger = logging.getLogger(__name__)


class QueryRouter:
    """
    다단계 확인 질문 라우터

    판정 기준:
    - 확정 라우팅: top_score >= 0.8 AND (top_score - 2nd_score) >= 0.3
    - 되묻기: 0.35 <= top_score < 0.8 OR score_gap < 0.3
    - 매칭 없음: top_score < 0.35
    """

    CONFIRM_THRESHOLD = 0.8
    CLARIFY_THRESHOLD = 0.35
    SCORE_GAP_THRESHOLD = 0.3

    def __init__(
        self,
        product_router: Optional[ProductRouterService] = None,
    ):
        self.product_router = product_router or get_product_router_service()
        self._display_names: Optional[Dict[str, Dict[str, str]]] = None

    def _get_display_names(self) -> Dict[str, Dict[str, str]]:
        """ManualRegistry에서 제품 표시명 가져오기 (캐시)"""
        if self._display_names is not None:
            return self._display_names

        self._display_names = {}
        try:
            from .manual_registry_service import get_manual_registry_service
            registry = get_manual_registry_service()
            for pid, product in registry.get_all_products().items():
                self._display_names[pid] = {
                    "ja": product.display_name,
                    "ko": product.display_name,
                    "en": product.display_name,
                }
        except Exception:
            pass

        # 구 ProductId 하위 호환 표시명
        _legacy_names = {
            "openframe_mvs": {
                "ja": "OpenFrame MVS (TJES, JCL, TACF, OSC)",
                "ko": "OpenFrame MVS (TJES, JCL, TACF, OSC)",
                "en": "OpenFrame MVS (TJES, JCL, TACF, OSC)",
            },
            "openframe_base": {
                "ja": "OpenFrame Base (データセット, カタログ, ボリューム)",
                "ko": "OpenFrame Base (데이터셋, 카탈로그, 볼륨)",
                "en": "OpenFrame Base (Dataset, Catalog, Volume)",
            },
            "msp_openframe": {
                "ja": "MSP OpenFrame (JES2/JES3, SMS, HSM)",
                "ko": "MSP OpenFrame (JES2/JES3, SMS, HSM)",
                "en": "MSP OpenFrame (JES2/JES3, SMS, HSM)",
            },
            "vos3_openframe": {
                "ja": "VOS3 OpenFrame (ACOS, NEC)",
                "ko": "VOS3 OpenFrame (ACOS, NEC)",
                "en": "VOS3 OpenFrame (ACOS, NEC)",
            },
            "tibero7": {
                "ja": "Tibero 7 (データベース)",
                "ko": "Tibero 7 (데이터베이스)",
                "en": "Tibero 7 (Database)",
            },
            "ofasm": {
                "ja": "OFASM (アセンブラ変換)",
                "ko": "OFASM (어셈블러 변환)",
                "en": "OFASM (Assembler Migration)",
            },
            "ofcobol": {
                "ja": "OFCOBOL (COBOL変換)",
                "ko": "OFCOBOL (COBOL 변환)",
                "en": "OFCOBOL (COBOL Migration)",
            },
            "xsp_openframe": {
                "ja": "XSP OpenFrame",
                "ko": "XSP OpenFrame",
                "en": "XSP OpenFrame",
            },
            "tmax": {
                "ja": "Tmax (ミドルウェア)",
                "ko": "Tmax (미들웨어)",
                "en": "Tmax (Middleware)",
            },
        }
        for k, v in _legacy_names.items():
            if k not in self._display_names:
                self._display_names[k] = v

        return self._display_names

    # 후속 질문 감지 패턴 (짧은 질문 + 대명사/후속어)
    _FOLLOWUP_PATTERNS = re.compile(
        r"(それ|これ|その|この|あれ|あの|もう少し|もっと|詳しく|具体的に|"
        r"about that|more detail|explain more|can you|"
        r"더\s*자세히|좀\s*더|그것|이것|위의)",
        re.IGNORECASE,
    )
    _FOLLOWUP_MAX_CHARS = 50

    def classify(
        self,
        query: str,
        language: str = "ja",
        history: Optional[List] = None,
    ) -> RouterResult:
        """다단계 확인 분류 (history fallback 포함)"""
        # 1단계: 기존 ProductRouterService로 점수 계산
        classification = self.product_router.classify(query)
        all_scores = classification.all_scores

        sorted_scores = sorted(
            all_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        if not sorted_scores or sorted_scores[0][1] == 0:
            # 후속 질문인 경우 history에서 제품 추론
            fallback = self._infer_product_from_history(query, history)
            if fallback:
                return fallback
            return RouterResult(
                decision=RouterDecision.NO_MATCH,
                confidence=0.0,
                candidates=[],
                all_scores=all_scores,
            )

        top_product, top_score = sorted_scores[0]
        second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
        score_gap = top_score - second_score

        # 2단계: 판정
        if top_score >= self.CONFIRM_THRESHOLD and score_gap >= self.SCORE_GAP_THRESHOLD:
            return RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=top_product,
                confidence=top_score,
                candidates=[],
                all_scores=all_scores,
            )

        if top_score >= self.CLARIFY_THRESHOLD:
            candidates = [
                ClarificationCandidate(
                    product=prod,
                    confidence=score,
                    reason=self._get_match_reason(query, prod, language),
                    matched_keywords=classification.matched_keywords
                    if prod == top_product else [],
                )
                for prod, score in sorted_scores[:3]
                if score >= 0.2
            ]
            return RouterResult(
                decision=RouterDecision.CLARIFICATION_NEEDED,
                product=top_product,
                confidence=top_score,
                candidates=candidates,
                all_scores=all_scores,
            )

        # NO_MATCH 시 후속 질문 fallback
        fallback = self._infer_product_from_history(query, history)
        if fallback:
            return fallback

        return RouterResult(
            decision=RouterDecision.NO_MATCH,
            confidence=top_score,
            candidates=[],
            all_scores=all_scores,
        )

    def _infer_product_from_history(
        self,
        query: str,
        history: Optional[List],
    ) -> Optional[RouterResult]:
        """후속 질문 시 history에서 직전 대화의 제품을 추론"""
        if not history:
            return None
        # 짧은 쿼리 + 후속 패턴 감지
        if len(query) > self._FOLLOWUP_MAX_CHARS:
            return None
        if not self._FOLLOWUP_PATTERNS.search(query):
            return None

        # history에서 마지막 assistant 메시지의 product 추출
        product = self._extract_product_from_history(history)
        if not product:
            return None

        logger.info(f"Follow-up detected: inferred product={product} from history")
        return RouterResult(
            decision=RouterDecision.CONFIRMED,
            product=product,
            confidence=0.75,
            candidates=[],
            all_scores={},
        )

    def _extract_product_from_history(self, history: List) -> Optional[str]:
        """history 리스트에서 마지막 assistant 응답의 제품 정보를 추출"""
        for msg in reversed(history):
            role = None
            product = None
            # dict 또는 Pydantic model 양쪽 지원
            if isinstance(msg, dict):
                role = msg.get("role")
                product = msg.get("product")
            elif hasattr(msg, "role"):
                role = msg.role
                product = getattr(msg, "product", None)

            if role == "assistant" and product:
                return product

        # product 필드가 없으면 마지막 assistant 콘텐츠를 keyword 매칭으로 재시도
        for msg in reversed(history):
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
            if role == "assistant" and content:
                result = self.product_router.classify(content[:200])
                if result.all_scores:
                    top = max(result.all_scores.items(), key=lambda x: x[1])
                    if top[1] >= 0.6:
                        return top[0]
                break

        return None

    def _get_match_reason(
        self,
        query: str,
        product: str,
        language: str = "ja",
    ) -> str:
        """제품 매칭 이유 생성"""
        lang = language if language in ("ja", "ko", "en") else "ja"
        display_names = self._get_display_names()
        names = display_names.get(product, {})
        return names.get(lang, product)


# =============================================================================
# Singleton
# =============================================================================

_query_router_instance: Optional[QueryRouter] = None


def get_query_router() -> QueryRouter:
    """Get singleton QueryRouter instance"""
    global _query_router_instance
    if _query_router_instance is None:
        _query_router_instance = QueryRouter()
    return _query_router_instance


def initialize_query_router(
    product_router: Optional[ProductRouterService] = None,
) -> QueryRouter:
    """Initialize QueryRouter with explicit dependencies"""
    global _query_router_instance
    _query_router_instance = QueryRouter(product_router=product_router)
    return _query_router_instance
