"""
Query Router Service

다단계 확인 질문 라우터.
기존 ProductRouterService를 래핑하여 다단계 확인 로직(확정/되묻기/매칭없음)을 추가합니다.
ManualRegistryService에서 동적 제품 목록을 사용합니다.

LLM Prompt Router (2026-02-23):
- 1차: vLLM(openframe_common) 기반 LLM 라우터 (의미 기반 제품 판별)
- 2차: 키워드 라우터 (기존 ProductRouterService) — LLM 실패/타임아웃 시 fallback
"""
import logging
import re
from typing import Dict, List, Optional, TYPE_CHECKING

from ..models.agentic_rag import (
    RouterResult,
    RouterDecision,
    ClarificationCandidate,
)
from .product_router_service import (
    get_product_router_service,
    ProductRouterService,
)

if TYPE_CHECKING:
    from .llm_prompt_router_service import LLMPromptRouterService

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
        llm_router: Optional["LLMPromptRouterService"] = None,
    ):
        self.product_router = product_router or get_product_router_service()
        self.llm_router = llm_router
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
            "ofpli": {
                "ja": "OFPLI (PL/I変換)",
                "ko": "OFPLI (PL/I 변환)",
                "en": "OFPLI (PL/I Migration)",
            },
            "jeus": {
                "ja": "JEUS 8 (Webアプリケーションサーバー)",
                "ko": "JEUS 8 (웹 애플리케이션 서버)",
                "en": "JEUS 8 (Web Application Server)",
            },
            "webtob": {
                "ja": "WebtoB (Webサーバー)",
                "ko": "WebtoB (웹 서버)",
                "en": "WebtoB (Web Server)",
            },
            "ofgw": {
                "ja": "OFGW (OpenFrameゲートウェイ)",
                "ko": "OFGW (OpenFrame 게이트웨이)",
                "en": "OFGW (OpenFrame Gateway)",
            },
            "ofmanager": {
                "ja": "OFManager (OpenFrame管理ツール)",
                "ko": "OFManager (OpenFrame 관리도구)",
                "en": "OFManager (OpenFrame Management Tool)",
            },
            "ofminer": {
                "ja": "OFMiner (マイグレーション分析)",
                "ko": "OFMiner (마이그레이션 분석)",
                "en": "OFMiner (Migration Analysis)",
            },
            "ofstudio": {
                "ja": "OFStudio (OpenFrame IDE)",
                "ko": "OFStudio (OpenFrame IDE)",
                "en": "OFStudio (OpenFrame IDE)",
            },
            "prosort": {
                "ja": "ProSort (ソート/マージ)",
                "ko": "ProSort (정렬/병합)",
                "en": "ProSort (Sort/Merge)",
            },
            "prosync": {
                "ja": "ProSync (データ同期)",
                "ko": "ProSync (데이터 동기화)",
                "en": "ProSync (Data Synchronization)",
            },
            "protrieve": {
                "ja": "ProTrieve (レポートジェネレーター)",
                "ko": "ProTrieve (리포트 생성기)",
                "en": "ProTrieve (Report Generator)",
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

    async def classify(
        self,
        query: str,
        language: str = "ja",
        history: Optional[List] = None,
    ) -> RouterResult:
        """
        다단계 확인 분류 (LLM 우선 + 키워드 fallback)

        1차: LLM Prompt Router (vLLM 기반, 의미론적 제품 판별)
        2차: 키워드 라우터 (기존 ProductRouterService, LLM 실패 시 fallback)
        """
        # ===== 1차: LLM Prompt Router (우선) =====
        if self.llm_router and self.llm_router.enabled:
            try:
                from ..core.config import get_api_settings
                min_conf = get_api_settings().LLM_PROMPT_ROUTER_MIN_CONFIDENCE

                llm_result = await self.llm_router.route(
                    query, language, history,
                )
                if llm_result and llm_result.confidence >= min_conf:
                    logger.info(
                        f"LLM router accepted: {llm_result.product} "
                        f"(conf={llm_result.confidence:.2f})"
                    )
                    return llm_result
                elif llm_result:
                    logger.info(
                        f"LLM router low confidence: {llm_result.product} "
                        f"(conf={llm_result.confidence:.2f} < {min_conf}), "
                        f"falling back to keyword"
                    )
            except Exception as e:
                logger.warning(f"LLM router failed, falling back to keyword: {e}")

        # ===== 2차: 키워드 라우터 (fallback) =====
        return self._classify_keyword(query, language, history)

    def _classify_keyword(
        self,
        query: str,
        language: str = "ja",
        history: Optional[List] = None,
    ) -> RouterResult:
        """키워드 기반 다단계 확인 분류 (기존 로직)"""
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
    """Get singleton QueryRouter instance (LLM router 자동 주입)"""
    global _query_router_instance
    if _query_router_instance is None:
        llm_router = None
        try:
            from .llm_prompt_router_service import get_llm_prompt_router_service
            llm_router = get_llm_prompt_router_service()
        except Exception:
            pass
        _query_router_instance = QueryRouter(llm_router=llm_router)
    return _query_router_instance


def initialize_query_router(
    product_router: Optional[ProductRouterService] = None,
    llm_router: Optional["LLMPromptRouterService"] = None,
) -> QueryRouter:
    """Initialize QueryRouter with explicit dependencies"""
    global _query_router_instance
    if llm_router is None:
        try:
            from .llm_prompt_router_service import get_llm_prompt_router_service
            llm_router = get_llm_prompt_router_service()
        except Exception:
            pass
    _query_router_instance = QueryRouter(
        product_router=product_router,
        llm_router=llm_router,
    )
    return _query_router_instance
