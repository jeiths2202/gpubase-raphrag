"""
Agentic RAG Service (Orchestrator)

제품별 Agent 기반 RAG 시스템의 메인 오케스트레이터.
QueryRouter → ProductAgent → QueryTypeClassifier → TemplateResponse/LLM+Verification 파이프라인을 조율합니다.
동적 제품(str) 기반으로 동작합니다.
"""
import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..core.logging_framework import get_logger
from ..models.agentic_rag import (
    AgenticRAGRequest,
    AgenticRAGResponse,
    AgenticRAGHealth,
    QueryType,
    RouterResult,
    RouterDecision,
    VerifiedSentence,
)
from ..models.openframe_rag import (
    ConfidenceLevel,
    ProductSources,
    VectorSource,
)
from .query_router_service import QueryRouter, get_query_router
from .product_agent_service import (
    BaseProductAgent,
    get_product_agent,
    get_all_product_agents,
)
from .structured_knowledge_store import SearchResult, ProductSearchContext
from .query_type_classifier import QueryTypeClassifier, get_query_type_classifier
from .template_response_builder import TemplateResponseBuilder, get_template_response_builder
from .response_verifier import ResponseVerifier, get_response_verifier
from .product_context_memory import ProductContextMemory, get_product_context_memory

logger = get_logger("kms.agentic_rag")

# 동적 product_id → VLLMAdapter가 인식하는 제품명 매핑
_DYNAMIC_TO_ADAPTER_MAP = {
    "mvs_openframe_7.1": "openframe_base",
    "msp_openframe_7.3": "msp_openframe",
    "vos3_openframe_2.0": "openframe_vos3",
    "xsp_openframe_7.3": "xsp_openframe",
    "tibero_7fixset01": "tibero7",
    "tmax_6.0": "tmax",
    "ofasm_4": "ofasm",
    "ofcobol_4": "ofcobol",
    "jeus_8.5": "jeus",
    "jeus_8": "jeus",
    "webtob_5.0": "webtob",
    "protrieve_7": "protrieve",
    "ofstudio_7": "ofstudio",
    "ofmanager_7": "ofmanager",
    "openframe_aim_7": "openframe_aim",
    "openframe_tacf_7": "openframe_tacf",
    "openframe_hidb_7": "openframe_hidb",
    "openframe_ndb_7": "openframe_ndb",
    "openframe_osi_7": "openframe_osi",
}


class AgenticRAGService:
    """
    Agentic RAG 오케스트레이터

    파이프라인:
    1. QueryRouter.classify() → 제품 확정/되묻기/매칭없음
    2. ProductAgent.search() → 구조화 검색 (LLM 없음)
    3. QueryTypeClassifier.classify() → 정형/비정형 판별
    4a. 정형 → TemplateResponseBuilder.build() (환각 0%)
    4b. 비정형 → LLM 생성 + ResponseVerifier.verify()
    """

    def __init__(
        self,
        query_router: Optional[QueryRouter] = None,
        query_type_classifier: Optional[QueryTypeClassifier] = None,
        template_builder: Optional[TemplateResponseBuilder] = None,
        response_verifier: Optional[ResponseVerifier] = None,
        product_memory: Optional[ProductContextMemory] = None,
    ):
        self.query_router = query_router or get_query_router()
        self.query_type_classifier = query_type_classifier or get_query_type_classifier()
        self.template_builder = template_builder or get_template_response_builder()
        self.response_verifier = response_verifier or get_response_verifier()
        self.product_memory = product_memory or get_product_context_memory()
        self._product_patterns: Optional[List[tuple]] = None

    def _get_product_patterns(self) -> List[tuple]:
        """ManualRegistry에서 동적 라우팅 패턴 로드"""
        if self._product_patterns is not None:
            return self._product_patterns
        try:
            from .manual_registry_service import get_manual_registry_service
            registry = get_manual_registry_service()
            self._product_patterns = registry.get_routing_patterns()
        except Exception:
            self._product_patterns = []
        return self._product_patterns

    def _detect_products_in_query(self, query: str) -> List[str]:
        """쿼리에서 언급된 모든 제품 감지"""
        detected: List[str] = []
        query_lower = query.lower()
        for pattern, pid in self._get_product_patterns():
            if re.search(pattern, query_lower):
                if pid not in detected:
                    detected.append(pid)
        return detected

    def _resolve_search_products(
        self,
        request: AgenticRAGRequest,
    ) -> tuple:
        """
        통합 제품 해석. (product_ids, router_result) 반환.

        Case 1: selected_product → [selected_product], CONFIRMED
        Case 2: products 리스트 → products, CONFIRMED
        Case 3: product != "auto" → [product], CONFIRMED
        Case 4: Auto 모드 → classify() 기반 해석 + Long-term Memory 보강
        """
        # Case 1~3: 명시적 제품 선택
        effective = request.effective_products
        if effective:
            return effective, RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=effective[0],
                confidence=1.0,
            )

        # Case 4: Auto 모드 → QueryRouter
        router_result = self.query_router.classify(
            request.message, request.language or "ja",
            history=request.history,
        )

        if router_result.decision == RouterDecision.CONFIRMED:
            # 확정 + 쿼리에서 추가 제품 감지
            products = [router_result.product]
            additional = [
                p for p in self._detect_products_in_query(request.message)
                if p != router_result.product
            ]
            products.extend(additional)
            return products, router_result

        if router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            # 후보가 1개이거나, top과 2nd 간의 차이가 큰 경우 자동 확정
            candidates = router_result.candidates
            if (
                router_result.product
                and router_result.confidence >= 0.6
                and (len(candidates) <= 1
                     or (len(candidates) >= 2
                         and candidates[0].confidence - candidates[1].confidence >= 0.3))
            ):
                logger.info(
                    f"[AgenticRAG] Auto-confirming single/dominant candidate: "
                    f"{router_result.product} (conf={router_result.confidence:.2f})"
                )
                products = [router_result.product]
                additional = [
                    p for p in self._detect_products_in_query(request.message)
                    if p != router_result.product
                ]
                products.extend(additional)
                return products, RouterResult(
                    decision=RouterDecision.CONFIRMED,
                    product=router_result.product,
                    confidence=router_result.confidence,
                    candidates=router_result.candidates,
                    all_scores=router_result.all_scores,
                )
            return [], router_result

        # NO_MATCH → 1차: all_scores에서 점수가 있는 제품 사용 (router가 일부 매칭)
        if router_result.all_scores:
            top_products = sorted(
                router_result.all_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            fallback = [p for p, s in top_products[:5] if s > 0]
            if fallback:
                return fallback, router_result

        # NO_MATCH → 2차: Long-term Memory에서 최근 제품 컨텍스트 보강
        # (router 점수가 전혀 없을 때만 → 후속 질문, 대명사 사용 등)
        memory_product = self._resolve_from_memory(request)
        if memory_product:
            logger.info(
                f"[AgenticRAG] Memory-based product resolution: {memory_product}"
            )
            return [memory_product], RouterResult(
                decision=RouterDecision.CONFIRMED,
                product=memory_product,
                confidence=0.6,  # 메모리 기반이므로 중간 confidence
            )

        return [], router_result

    def _resolve_from_memory(self, request: AgenticRAGRequest) -> Optional[str]:
        """
        Long-term Memory에서 최근 제품 컨텍스트를 조회하여 제품을 해석.

        후속 질문 패턴 (それは?, 詳しく, 그거, that 등) 에서 특히 효과적.
        """
        if not self.product_memory or not self.product_memory.available:
            return None

        user_id = getattr(request, "user_id", None) or "anonymous"
        session_id = getattr(request, "session_id", None) or "default"

        # 1. 현재 세션의 최근 제품 확인
        session_product = self.product_memory.get_session_product(user_id, session_id)
        if session_product:
            return session_product

        # 2. 사용자 글로벌 최근 제품 확인
        recent_product = self.product_memory.get_recent_product(user_id)
        if recent_product:
            return recent_product

        return None

    async def _multi_product_search(
        self,
        query: str,
        product_ids: List[str],
        query_type: Optional[QueryType],
        top_k_per_product: Optional[int] = None,
        max_total: int = 8,
    ) -> ProductSearchContext:
        """복수 Product Agent 병렬 검색 + 결과 병합."""
        # per-product top_k 자동 조절
        if top_k_per_product is None:
            n = len(product_ids)
            if n <= 2:
                top_k_per_product = 5
            elif n <= 5:
                top_k_per_product = 3
            else:
                top_k_per_product = 2

        agents = []
        for pid in product_ids:
            agent = get_product_agent(pid)
            if agent:
                agents.append((pid, agent))

        if not agents:
            return ProductSearchContext(product=product_ids[0] if product_ids else "auto")

        sem = asyncio.Semaphore(5)

        async def _search_one(pid: str, agent: BaseProductAgent) -> List[SearchResult]:
            async with sem:
                ctx = await agent.search(query=query, query_type=query_type, top_k=top_k_per_product)
                for r in ctx.structured_results:
                    r.product = pid
                return ctx.structured_results

        tasks = [_search_one(pid, agent) for pid, agent in agents]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[SearchResult] = []
        for result in results_lists:
            if isinstance(result, list):
                all_results.extend(result)

        all_results.sort(key=lambda r: r.relevance_score, reverse=True)

        # fingerprint dedup
        deduped: List[SearchResult] = []
        seen_fp: set = set()
        for r in all_results:
            raw_fp = r.content[:120].strip().lower()
            fp = re.sub(r"[^a-z0-9\u3040-\u9fff\uac00-\ud7af]", "", raw_fp)
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            deduped.append(r)
            if len(deduped) >= max_total:
                break

        merged = ProductSearchContext(product=product_ids[0] if product_ids else "auto")
        merged.structured_results = deduped
        logger.info(
            f"Multi-product search: {product_ids} → "
            f"{len(all_results)} total, {len(deduped)} after dedup"
        )
        return merged

    async def health_check(self) -> AgenticRAGHealth:
        """서비스 상태 확인"""
        agents = get_all_product_agents()
        agent_status = {
            pid: agent.is_available
            for pid, agent in agents.items()
        }

        knowledge_stats: Dict[str, int] = {}
        for pid, agent in agents.items():
            try:
                stats = agent.get_stats()
                knowledge_stats[pid] = sum(stats.values())
            except Exception:
                knowledge_stats[pid] = 0

        return AgenticRAGHealth(
            available=True,
            message="Agentic RAG service is running",
            agents=agent_status,
            knowledge_store_status=knowledge_stats,
            supported_products=list(agents.keys()),
        )

    async def chat(self, request: AgenticRAGRequest) -> AgenticRAGResponse:
        """동기식 채팅 처리"""
        start = time.time()

        # 1. 통합 제품 해석
        product_ids, router_result = self._resolve_search_products(request)

        # Long-term Memory에 제품 라우팅 결과 저장
        if product_ids and self.product_memory and self.product_memory.available:
            user_id = getattr(request, "user_id", None) or "anonymous"
            session_id = getattr(request, "session_id", None) or "default"
            self.product_memory.save_product_context(
                user_id=user_id,
                session_id=session_id,
                product_id=product_ids[0],
                query=request.message,
                confidence=router_result.confidence,
            )

        # 되묻기 필요
        if not product_ids and router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            return AgenticRAGResponse(
                success=True,
                response="",
                product=router_result.product or "auto",
                query_type=QueryType.FREEFORM,
                router_result=router_result,
                confidence=ConfidenceLevel.LOW,
                processing_time_ms=int((time.time() - start) * 1000),
            )

        # 매칭 없음
        if not product_ids:
            return AgenticRAGResponse(
                success=True,
                response="該当する製品を特定できませんでした。質問を具体的にしていただくか、製品を選択してください。",
                product="auto",
                query_type=QueryType.FREEFORM,
                router_result=router_result,
                confidence=ConfidenceLevel.LOW,
                processing_time_ms=int((time.time() - start) * 1000),
            )

        primary_product = product_ids[0]

        # 2. 질문 유형 분류
        query_type = self.query_type_classifier.classify(request.message)

        # 3. 통합 검색
        search_context = await self._multi_product_search(
            query=request.message,
            product_ids=product_ids,
            query_type=query_type,
        )

        # 4. 응답 생성
        if query_type != QueryType.FREEFORM and search_context.structured_results:
            template_response = self.template_builder.build(
                query=request.message,
                query_type=query_type,
                results=search_context.structured_results,
                language=request.language or "ja",
            )
            if template_response:
                return AgenticRAGResponse(
                    success=True,
                    response=template_response,
                    product=primary_product,
                    query_type=query_type,
                    router_result=router_result,
                    confidence=ConfidenceLevel.HIGH,
                    sources=self._build_sources(search_context.structured_results),
                    processing_time_ms=int((time.time() - start) * 1000),
                )

        # 비정형 질문 또는 템플릿 실패: LLM 생성
        llm_response = await self._generate_with_llm(
            request.message,
            primary_product,
            search_context,
            request.language or "ja",
            history=request.history,
        )

        # LLM 응답에 테이블 보충
        if llm_response and search_context.structured_results:
            table_supplement = self._build_table_supplement(search_context.structured_results)
            if table_supplement:
                llm_response += table_supplement

        verification = None
        if llm_response and search_context.structured_results:
            verification = self.response_verifier.verify(
                llm_response,
                search_context.structured_results,
            )

        confidence = self._calculate_confidence(verification)

        return AgenticRAGResponse(
            success=True,
            response=llm_response or "情報が見つかりませんでした。質問を変更してお試しください。",
            product=primary_product,
            query_type=query_type,
            router_result=router_result,
            verification=verification,
            sources=self._build_sources(search_context.structured_results),
            confidence=confidence,
            processing_time_ms=int((time.time() - start) * 1000),
        )

    async def stream_chat(
        self,
        request: AgenticRAGRequest,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """SSE 스트리밍 채팅"""
        start = time.time()

        # 1. 통합 제품 해석
        product_ids, router_result = self._resolve_search_products(request)

        primary_product = product_ids[0] if product_ids else "auto"

        # Long-term Memory에 제품 라우팅 결과 저장
        if product_ids and self.product_memory and self.product_memory.available:
            user_id = getattr(request, "user_id", None) or "anonymous"
            session_id = getattr(request, "session_id", None) or "default"
            self.product_memory.save_product_context(
                user_id=user_id,
                session_id=session_id,
                product_id=primary_product,
                query=request.message,
                confidence=router_result.confidence,
            )

        # 분류 결과 전송 (products 리스트 포함)
        yield {
            "type": "classification",
            "product": primary_product,
            "products": product_ids,
            "decision": router_result.decision.value,
            "confidence": router_result.confidence,
        }

        # 되묻기 필요
        if not product_ids and router_result.decision == RouterDecision.CLARIFICATION_NEEDED:
            yield {
                "type": "clarification_needed",
                "candidates": [
                    {
                        "product": c.product,
                        "confidence": c.confidence,
                        "reason": c.reason,
                        "matched_keywords": c.matched_keywords,
                    }
                    for c in router_result.candidates
                ],
                "message": "どの製品に関する質問ですか？",
            }
            return

        # 매칭 없음
        if not product_ids:
            yield {
                "type": "error",
                "message": "該当する製品を特定できませんでした。製品を選択してください。",
            }
            return

        # 2. 검색 진행
        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "structured_search",
            "progress": 0.3,
        }

        # 3. 질문 유형 분류
        query_type = self.query_type_classifier.classify(request.message)

        # 4. 통합 검색
        search_context = await self._multi_product_search(
            query=request.message,
            product_ids=product_ids,
            query_type=query_type,
        )

        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "search_complete",
            "progress": 0.6,
        }

        # 저관련 경고 (best score < 0.3)
        if search_context.structured_results:
            best_score = search_context.structured_results[0].relevance_score
            if best_score < 0.3:
                yield {
                    "type": "low_relevance_warning",
                    "message": "検索結果の関連性が低い可能性があります。質問を具体的にしてお試しください。",
                    "best_score": best_score,
                    "searched_products": product_ids,
                }

        # 5. 응답 생성
        if query_type != QueryType.FREEFORM and search_context.structured_results:
            template_response = self.template_builder.build(
                query=request.message,
                query_type=query_type,
                results=search_context.structured_results,
                language=request.language or "ja",
            )
            if template_response:
                yield {
                    "type": "template_response",
                    "content": template_response,
                    "query_type": query_type.value,
                }
                yield self._build_sources_event(search_context.structured_results)
                yield {
                    "type": "done",
                    "processing_time_ms": int((time.time() - start) * 1000),
                    "product": primary_product,
                    "products": product_ids,
                    "query_type": query_type.value,
                }
                return

        # 비정형: LLM 스트리밍 생성
        yield {
            "type": "search_progress",
            "product": primary_product,
            "products": product_ids,
            "step": "generating",
            "progress": 0.7,
        }

        full_response = ""
        async for token in self._stream_llm(
            request.message, primary_product, search_context, request.language or "ja",
            history=request.history,
        ):
            full_response += token
            yield {"type": "llm_token", "token": token}

        # LLM 응답 후 테이블 보충 (LLM이 재현하지 못한 표 데이터 추가)
        if search_context.structured_results:
            table_supplement = self._build_table_supplement(search_context.structured_results)
            if table_supplement:
                yield {"type": "llm_token", "token": table_supplement}
                full_response += table_supplement

        # 사후 검증
        if full_response and search_context.structured_results:
            verification = self.response_verifier.verify(
                full_response,
                search_context.structured_results,
            )
            if verification:
                yield {
                    "type": "verification",
                    "sentences": [
                        {
                            "text": v.text,
                            "level": v.level.value,
                            "similarity": v.similarity,
                            "source_chunk": v.source_chunk,
                            "source_doc": v.source_doc,
                        }
                        for v in verification
                    ],
                }

        yield self._build_sources_event(search_context.structured_results)
        yield {
            "type": "done",
            "processing_time_ms": int((time.time() - start) * 1000),
            "product": primary_product,
            "products": product_ids,
            "query_type": query_type.value,
        }

    async def _generate_with_llm(
        self,
        query: str,
        product_id: str,
        search_context,
        language: str,
        history=None,
    ) -> Optional[str]:
        """LLM으로 비정형 응답 생성"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()

            if not llm_service:
                logger.warning("LLM skipped (generate): get_learning_llm_service() returned None")
            elif not llm_service.is_available:
                logger.warning(
                    f"LLM skipped (generate): is_available=False "
                    f"(enabled={llm_service.enabled}, initialized={llm_service._is_initialized})"
                )

            if not llm_service or not llm_service.is_available:
                if search_context.structured_results:
                    return self._fallback_from_structured(search_context.structured_results)
                return None

            adapter_product = self._map_product_for_llm(product_id)
            context = self._build_llm_context(search_context.structured_results, history=history)
            logger.info(
                f"LLM generate: product={product_id}, adapter_product={adapter_product}, "
                f"context_len={len(context)}"
            )

            result = await llm_service.generate(
                question=query,
                context=context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
            )

            if result and result.get("response"):
                return result["response"]

        except Exception as e:
            logger.warning(f"LLM generation failed: {type(e).__name__}: {e}")

        if search_context.structured_results:
            return self._fallback_from_structured(search_context.structured_results)
        return None

    async def _stream_llm(
        self,
        query: str,
        product_id: str,
        search_context,
        language: str,
        history=None,
    ) -> AsyncGenerator[str, None]:
        """LLM 스트리밍 생성"""
        try:
            from .learning_llm_service import get_learning_llm_service
            llm_service = get_learning_llm_service()

            if not llm_service:
                logger.warning("LLM skipped (stream): get_learning_llm_service() returned None")
            elif not llm_service.is_available:
                logger.warning(
                    f"LLM skipped (stream): is_available=False "
                    f"(enabled={llm_service.enabled}, initialized={llm_service._is_initialized})"
                )

            if not llm_service or not llm_service.is_available:
                fallback = self._fallback_from_structured(
                    search_context.structured_results
                ) if search_context.structured_results else "情報が見つかりませんでした。"
                yield fallback
                return

            adapter_product = self._map_product_for_llm(product_id)
            context = self._build_llm_context(search_context.structured_results, history=history)
            logger.info(
                f"LLM streaming: product={product_id}, adapter_product={adapter_product}, "
                f"context_len={len(context)}"
            )

            async for token in llm_service.generate_stream(
                question=query,
                context=context,
                max_tokens=2048,
                temperature=0.3,
                product=adapter_product,
            ):
                yield token

        except Exception as e:
            logger.warning(f"LLM streaming failed: {type(e).__name__}: {e}")
            fallback = self._fallback_from_structured(
                search_context.structured_results
            ) if search_context.structured_results else f"生成エラー: {str(e)}"
            yield fallback

    # LLM 컨텍스트 총 문자 수 제한 (모델 context window 고려, ~1500 tokens)
    _MAX_LLM_CONTEXT_CHARS = 4000
    _MAX_HISTORY_CHARS = 800

    def _build_llm_context(self, results, history=None) -> str:
        """검색 결과를 LLM 컨텍스트 문자열로 변환 (대화 이력 + 테이블 포함, 예산 관리)"""
        # 대화 이력 포맷팅
        history_section = self._format_history_for_context(history)
        history_len = len(history_section)
        search_budget = self._MAX_LLM_CONTEXT_CHARS - history_len

        if not results:
            return history_section

        from .structured_knowledge_store import enrich_content_with_tables

        top_score = results[0].relevance_score if results else 0
        threshold = top_score * 0.5
        filtered = [r for r in results[:5] if r.relevance_score >= threshold]
        if not filtered:
            filtered = results[:1]

        parts = []
        total_chars = 0
        per_result_limit = min(2000, search_budget // max(len(filtered), 1))

        for i, r in enumerate(filtered, 1):
            if total_chars >= search_budget:
                break
            content = enrich_content_with_tables(r)
            if len(content) > per_result_limit:
                content = content[:per_result_limit] + "..."
            source = f" (出典: {r.source_file})" if r.source_file else ""
            part = f"[参考資料 {i}: {r.title}{source}]\n{content}"
            parts.append(part)
            total_chars += len(part)

        search_section = "\n\n---\n\n".join(parts)

        if history_section and search_section:
            return history_section + "\n\n" + search_section
        return search_section or history_section

    def _format_history_for_context(self, history) -> str:
        """대화 이력을 LLM 컨텍스트용 텍스트로 포맷 (최근 2~3턴, 예산 내)"""
        if not history:
            return ""

        # 최근 3턴(user+assistant 쌍) = 최대 6메시지를 역순으로 수집
        recent_messages = []
        for msg in reversed(history):
            if len(recent_messages) >= 6:
                break
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
            if role and content:
                recent_messages.append((role, content))

        if not recent_messages:
            return ""

        # 원래 순서로 복원
        recent_messages.reverse()

        lines = ["[会話履歴]"]
        total = len(lines[0])
        for role, content in recent_messages:
            label = "ユーザー" if role == "user" else "アシスタント"
            # 개별 메시지 길이 제한
            truncated = content[:300] if len(content) > 300 else content
            line = f"{label}: {truncated}"
            if total + len(line) + 1 > self._MAX_HISTORY_CHARS:
                break
            lines.append(line)
            total += len(line) + 1

        if len(lines) <= 1:
            return ""
        return "\n".join(lines)

    def _fallback_from_structured(self, results) -> str:
        """구조화 결과로 폴백 응답 생성 (가독성 개선)"""
        if not results:
            return ""
        from .structured_knowledge_store import enrich_content_with_tables

        top_score = results[0].relevance_score if results else 0
        threshold = top_score * 0.5
        filtered = [r for r in results[:3] if r.relevance_score >= threshold]
        if not filtered:
            filtered = results[:1]
        parts = []
        for r in filtered:
            content = enrich_content_with_tables(r)
            if len(content) > 2000:
                cut = content[:2000]
                last_break = max(cut.rfind('。'), cut.rfind('\n'), cut.rfind('. '))
                if last_break > 800:
                    cut = cut[:last_break + 1]
                content = cut + "\n..."
            parts.append(f"### {r.title}\n\n{content}")

        output = "\n\n---\n\n".join(parts)

        # 중복 행 제거 (여러 검색 결과 간 페이지 겹침으로 인한 중복 방지)
        seen_lines: set = set()
        deduped: list = []
        for line in output.split('\n'):
            stripped = line.strip()
            if len(stripped) > 30:
                if stripped in seen_lines:
                    continue
                seen_lines.add(stripped)
            deduped.append(line)
        return '\n'.join(deduped)

    def _build_table_supplement(self, results) -> str:
        """LLM 응답 후 검색 결과의 테이블과 이미지를 보충 자료로 추가"""
        from .structured_knowledge_store import (
            _resolve_pdf_path_and_page,
            StructuredKnowledgeStore,
        )

        tables_md: list = []
        images_md: list = []
        seen_tables: set = set()
        seen_images: set = set()

        for r in results[:3]:
            pdf_path, page_num = _resolve_pdf_path_and_page(r)
            if not pdf_path or page_num < 0:
                continue
            try:
                import pymupdf
                doc = pymupdf.open(pdf_path)
                product_id = r.product or "unknown"
                # 해당 페이지 + 다음 1페이지만 스캔 (인접 무관 테이블 방지)
                for p in range(page_num, min(page_num + 2, len(doc))):
                    try:
                        tables = doc[p].find_tables()
                        for table in tables:
                            data = table.extract()
                            md = StructuredKnowledgeStore._table_to_markdown(data)
                            if md and md not in seen_tables:
                                seen_tables.add(md)
                                tables_md.append(md)
                    except Exception:
                        pass
                    try:
                        imgs = StructuredKnowledgeStore._extract_page_images(
                            doc, p, product_id,
                        )
                        for img_md in imgs:
                            if img_md not in seen_images:
                                seen_images.add(img_md)
                                images_md.append(img_md)
                    except Exception:
                        pass
                doc.close()
            except Exception:
                continue

        parts: list = []
        if tables_md:
            parts.append("**参考テーブル:**\n\n" + "\n\n".join(tables_md[:5]))
        if images_md:
            parts.append("**参考図:**\n\n" + "\n\n".join(images_md[:8]))

        if not parts:
            return ""

        return "\n\n---\n\n" + "\n\n".join(parts)

    def _map_product_for_llm(self, product_id: str) -> str:
        """동적 product_id를 VLLMAdapter가 인식할 수 있는 제품명으로 변환"""
        if product_id in _DYNAMIC_TO_ADAPTER_MAP:
            return _DYNAMIC_TO_ADAPTER_MAP[product_id]
        # Fallback: '_' 기준 첫 부분 (family) 사용
        family = product_id.split("_")[0] if "_" in product_id else product_id
        return family

    def _build_sources(self, results) -> ProductSources:
        """검색 결과에서 출처 정보 생성"""
        vector_sources = []
        for i, r in enumerate(results[:5]):
            vector_sources.append(VectorSource(
                chunk_id=f"structured_{i}",
                doc_id=r.source_file or f"doc_{i}",
                doc_name=r.source_file or "",
                content=r.content[:200] if r.content else "",
                score=r.relevance_score,
                product=r.product or r.domain,
            ))
        return ProductSources(vector_search=vector_sources)

    def _build_sources_event(self, results) -> Dict[str, Any]:
        """출처 정보 SSE 이벤트 생성"""
        sources = []
        for r in results[:5]:
            sources.append({
                "doc_name": r.source_file or "",
                "content": r.content[:200] if r.content else "",
                "score": r.relevance_score,
                "domain": r.domain,
                "product": r.product,
            })
        return {
            "type": "sources",
            "results": sources,
            "total": len(results),
        }

    def _calculate_confidence(
        self,
        verification: Optional[List[VerifiedSentence]],
    ) -> ConfidenceLevel:
        """검증 결과 기반 전체 신뢰도 계산"""
        if not verification:
            return ConfidenceLevel.LOW

        verified_count = sum(
            1 for v in verification if v.level.value == "verified"
        )
        total = len(verification)

        if total == 0:
            return ConfidenceLevel.LOW

        ratio = verified_count / total
        if ratio >= 0.7:
            return ConfidenceLevel.HIGH
        elif ratio >= 0.4:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW


# =============================================================================
# Singleton
# =============================================================================

_service_instance: Optional[AgenticRAGService] = None


def get_agentic_rag_service() -> AgenticRAGService:
    """Get singleton AgenticRAGService"""
    global _service_instance
    if _service_instance is None:
        _service_instance = AgenticRAGService()
    return _service_instance


async def initialize_agentic_rag_service() -> AgenticRAGService:
    """Initialize AgenticRAGService"""
    global _service_instance
    _service_instance = AgenticRAGService()
    logger.info("AgenticRAGService initialized")
    return _service_instance
