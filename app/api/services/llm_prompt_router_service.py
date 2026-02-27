"""
LLM Prompt Router Service

vLLM 기반 프롬프트 라우터 Agent.
모든 쿼리를 LLM으로 먼저 판별하고, 실패 시 None을 반환하여 키워드 fallback을 유도합니다.

Architecture:
    사용자 질문 → LLM (openframe_common 어댑터) → JSON 파싱 → RouterResult
    실패/타임아웃/파싱에러 → None → 키워드 라우터(ProductRouterService)로 fallback
"""
import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional

import aiohttp

from ..core.config import get_api_settings
from ..models.agentic_rag import (
    RouterResult,
    RouterDecision,
)

logger = logging.getLogger(__name__)


class LLMPromptRouterService:
    """
    vLLM 기반 프롬프트 라우터 Agent.

    ManualRegistryService에서 19개 제품 카탈로그를 동적 생성하고,
    vLLM(openframe_common 어댑터)에 질문+카탈로그를 전송하여 제품을 판별합니다.

    실패 시 None을 반환하여 기존 키워드 라우터로 fallback합니다.
    """

    def __init__(self):
        self._catalog: Optional[str] = None
        self._product_ids: Optional[List[str]] = None

    @property
    def enabled(self) -> bool:
        settings = get_api_settings()
        return settings.LLM_PROMPT_ROUTER_ENABLED

    async def route(
        self,
        query: str,
        language: str = "ja",
        history: Optional[List] = None,
    ) -> Optional[RouterResult]:
        """
        LLM으로 제품 라우팅.

        성공 시 RouterResult(CONFIRMED), 실패 시 None(fallback 시그널).
        """
        if not self.enabled:
            return None

        settings = get_api_settings()
        timeout = settings.LLM_PROMPT_ROUTER_TIMEOUT

        try:
            start = time.time()

            # 카탈로그 프롬프트 빌드 (1회 캐시)
            catalog = self._build_catalog_prompt()
            if not catalog:
                logger.warning("LLM router: catalog is empty, skipping")
                return None

            # 라우팅 프롬프트 구성
            system_prompt, user_prompt = self._build_routing_prompt(
                query, language, catalog, history,
            )

            # vLLM 호출 (non-streaming)
            raw_response = await self._call_vllm(
                system_prompt, user_prompt, timeout,
            )

            elapsed_ms = int((time.time() - start) * 1000)

            if not raw_response:
                logger.warning(f"LLM router: empty response ({elapsed_ms}ms)")
                return None

            # JSON 파싱
            result = self._parse_response(raw_response)
            if result:
                logger.info(
                    f"LLM router: {result.product} "
                    f"(conf={result.confidence:.2f}, {elapsed_ms}ms)"
                )
            else:
                logger.warning(
                    f"LLM router: parse failed ({elapsed_ms}ms), "
                    f"raw={raw_response[:200]}"
                )
            return result

        except asyncio.TimeoutError:
            logger.warning(f"LLM router: timeout ({timeout}s)")
            return None
        except Exception as e:
            logger.warning(f"LLM router: error: {e}")
            return None

    def _build_catalog_prompt(self) -> str:
        """ManualRegistryService에서 19개 제품 카탈로그 동적 생성 (1회 캐시)"""
        if self._catalog is not None:
            return self._catalog

        try:
            from .manual_registry_service import get_manual_registry_service
            registry = get_manual_registry_service()
            products = registry.get_all_products()
        except Exception as e:
            logger.warning(f"LLM router: failed to load registry: {e}")
            self._catalog = ""
            return ""

        lines: List[str] = []
        product_ids: List[str] = []
        for pid, product in sorted(products.items()):
            keywords = ", ".join(product.keywords[:10]) if product.keywords else ""
            line = f"- {pid}: {product.display_name}"
            if keywords:
                line += f" (keywords: {keywords})"
            lines.append(line)
            product_ids.append(pid)

        self._catalog = "\n".join(lines)
        self._product_ids = product_ids
        return self._catalog

    def _build_routing_prompt(
        self,
        query: str,
        language: str,
        catalog: str,
        history: Optional[List] = None,
    ) -> tuple:
        """시스템 프롬프트 + 사용자 프롬프트 구성"""
        system_prompt = (
            "You are a product routing classifier for TmaxSoft OpenFrame KMS.\n"
            "Given a user query about mainframe migration products, identify which product(s) "
            "the query is about.\n\n"
            "## Available Products\n"
            f"{catalog}\n\n"
            "## Rules\n"
            "1. Analyze the query semantically - consider implied products even if not explicitly named.\n"
            "2. For batch job questions → likely MVS OpenFrame (mvs_openframe_7.1)\n"
            "3. For COBOL questions → likely OFCOBOL (ofcobol_4)\n"
            "4. For database/SQL questions → likely Tibero (tibero_7fixset01)\n"
            "5. For online transaction questions → likely MVS OpenFrame (mvs_openframe_7.1) or XSP\n"
            "6. For JCL/JES questions → likely MVS OpenFrame (mvs_openframe_7.1)\n"
            "7. For web server questions → likely WebtoB or JEUS\n"
            "8. For middleware questions → likely Tmax\n"
            "9. If the query mentions a specific manager command (tjesmgr, tacfmgr, oscmgr, etc.), "
            "it is MVS OpenFrame.\n"
            "10. Any tool starting with 'osc' prefix (osctdlrm, osctdlinit, oscboot, oscdown, oscmcsvr, "
            "oscsiggen, osccobprep, etc.) belongs to OSC (Online SC) which is MVS OpenFrame.\n"
            "11. Return confidence 0.0 if you cannot determine the product at all.\n\n"
            "## Response Format\n"
            "Respond ONLY with a JSON object (no markdown, no explanation):\n"
            '{"products": [{"id": "<product_id>", "confidence": <0.0-1.0>, "reason": "<brief reason>"}]}\n'
        )

        # 히스토리에서 최근 컨텍스트 추출 (있으면)
        history_context = ""
        if history:
            recent = []
            for msg in history[-4:]:  # 최근 4개 메시지
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                if role and content:
                    recent.append(f"{role}: {content[:100]}")
            if recent:
                history_context = "\n\nRecent conversation:\n" + "\n".join(recent)

        user_prompt = f"Query ({language}): {query}{history_context}"

        return system_prompt, user_prompt

    async def _call_vllm(
        self,
        system_prompt: str,
        user_prompt: str,
        timeout: int,
    ) -> Optional[str]:
        """vLLM OpenAI-compatible API 호출 (non-streaming, openframe_common 어댑터)"""
        from ..adapters.learning_llm.vllm_adapter import MULTI_LORA_BASE_URL

        base_url = MULTI_LORA_BASE_URL
        # openframe_common 어댑터 사용 (가장 범용적인 어댑터)
        model_name = "openframe_common"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": 256,
            "temperature": 0.1,
            "top_p": 0.9,
        }

        chat_url = f"{base_url}/chat/completions"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                chat_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.warning(
                        f"LLM router vLLM error: {resp.status} - {error_text[:200]}"
                    )
                    return None

                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    def _parse_response(self, raw: str) -> Optional[RouterResult]:
        """JSON 파싱 → RouterResult. 파싱 실패 시 None."""
        # JSON 블록 추출 (마크다운 코드블록 대응)
        text = raw.strip()
        if text.startswith("```"):
            # ```json\n{...}\n``` 형태 처리
            lines = text.split("\n")
            json_lines = [
                l for l in lines
                if not l.strip().startswith("```")
            ]
            text = "\n".join(json_lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # JSON이 텍스트에 포함된 경우 추출 시도
            match = re.search(r'\{[^{}]*"products"[^{}]*\[.*?\]\s*\}', text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    return None
            else:
                return None

        products = data.get("products", [])
        if not products:
            return None

        # 유효한 product_id만 필터
        valid_ids = set(self._product_ids or [])
        valid_products = [
            p for p in products
            if p.get("id") in valid_ids and p.get("confidence", 0) > 0
        ]

        if not valid_products:
            # product_id가 정확히 매칭되지 않을 경우, 부분 매칭 시도
            for p in products:
                pid = p.get("id", "")
                for valid_id in valid_ids:
                    if pid in valid_id or valid_id in pid:
                        p["id"] = valid_id
                        valid_products.append(p)
                        break
                if valid_products:
                    break

        if not valid_products:
            return None

        # 가장 높은 confidence의 제품 선택
        top = max(valid_products, key=lambda p: p.get("confidence", 0))
        confidence = min(max(float(top.get("confidence", 0)), 0.0), 1.0)

        if confidence <= 0:
            return None

        return RouterResult(
            decision=RouterDecision.CONFIRMED,
            product=top["id"],
            confidence=confidence,
            candidates=[],
            all_scores={p["id"]: p.get("confidence", 0) for p in valid_products},
        )


# =============================================================================
# Singleton
# =============================================================================

_llm_prompt_router_instance: Optional[LLMPromptRouterService] = None


def get_llm_prompt_router_service() -> LLMPromptRouterService:
    """Get singleton LLMPromptRouterService instance"""
    global _llm_prompt_router_instance
    if _llm_prompt_router_instance is None:
        _llm_prompt_router_instance = LLMPromptRouterService()
    return _llm_prompt_router_instance
