"""
Team Orchestrator - Agent Teams 메인 통합 레이어

AgenticRAGService를 래핑하여 Feature Flag에 따라
5개 패턴을 조건부 활성화. Flag가 모두 OFF이면 100% 원래 동작.
"""
import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, Any, List, Optional

from ...models.agentic_rag import (
    AgenticRAGRequest,
    AgentMode,
    QueryType,
    RouterDecision,
)
from ...core.config import get_api_settings

from .parallel_retrieval import ParallelRetrievalService
from .domain_specialist import DomainSpecialistTeam
from .multi_product_collab import MultiProductCollaborationService
from .competitive_hypothesis import CompetitiveHypothesisService
from .self_improvement import SelfImprovementService, get_self_improvement_service

logger = logging.getLogger(__name__)


class TeamOrchestrator:
    """
    Enhanced RAG 오케스트레이터.
    Feature flag에 따라 Agent Teams 패턴을 적용하고,
    비활성 시 원래 AgenticRAGService.stream_chat()으로 100% 위임.
    """

    def __init__(self, rag_service=None):
        self._rag = rag_service
        self._settings = get_api_settings()

        # Lazy-initialized pattern services
        self._parallel_retrieval: Optional[ParallelRetrievalService] = None
        self._domain_specialist: Optional[DomainSpecialistTeam] = None
        self._multi_product: Optional[MultiProductCollaborationService] = None
        self._competitive: Optional[CompetitiveHypothesisService] = None
        self._self_improvement: Optional[SelfImprovementService] = None

    def _get_rag(self):
        """AgenticRAGService lazy init"""
        if self._rag is None:
            from ..agentic_rag_service import get_agentic_rag_service
            self._rag = get_agentic_rag_service()
        return self._rag

    def _any_pattern_enabled(self) -> bool:
        """하나라도 활성화된 패턴이 있는지 확인"""
        s = self._settings
        return any([
            s.AGENT_TEAMS_PARALLEL_RETRIEVAL,
            s.AGENT_TEAMS_DOMAIN_SPECIALIST,
            s.AGENT_TEAMS_MULTI_PRODUCT,
            s.AGENT_TEAMS_COMPETITIVE_HYPOTHESIS,
            s.AGENT_TEAMS_SELF_IMPROVEMENT,
        ])

    # =========================================================================
    # Pattern service getters (lazy init)
    # =========================================================================

    def _get_parallel_retrieval(self) -> ParallelRetrievalService:
        if self._parallel_retrieval is None:
            self._parallel_retrieval = ParallelRetrievalService(self._get_rag())
        return self._parallel_retrieval

    def _get_domain_specialist(self) -> DomainSpecialistTeam:
        if self._domain_specialist is None:
            self._domain_specialist = DomainSpecialistTeam(
                max_parallel=self._settings.AGENT_TEAMS_MAX_PARALLEL_LLM,
                winner_threshold=self._settings.AGENT_TEAMS_WINNER_THRESHOLD,
            )
        return self._domain_specialist

    def _get_multi_product(self) -> MultiProductCollaborationService:
        if self._multi_product is None:
            self._multi_product = MultiProductCollaborationService()
        return self._multi_product

    def _get_competitive(self) -> CompetitiveHypothesisService:
        if self._competitive is None:
            self._competitive = CompetitiveHypothesisService()
        return self._competitive

    def _get_self_improvement(self) -> SelfImprovementService:
        if self._self_improvement is None:
            self._self_improvement = get_self_improvement_service()
        return self._self_improvement

    # =========================================================================
    # Main entry point
    # =========================================================================

    async def stream_chat_enhanced(
        self,
        request: AgenticRAGRequest,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Enhanced stream_chat with Agent Teams 패턴.
        모든 패턴 OFF 시 원래 stream_chat()으로 100% 위임.
        """
        # 패턴이 하나도 활성화되지 않으면 원래 동작으로 바로 위임
        if not self._any_pattern_enabled():
            async for event in self._get_rag().stream_chat(request):
                yield event
            return

        start = time.time()
        rag = self._get_rag()

        # 1. 제품 라우팅 (기존 로직 재사용)
        product_ids, router_result = rag._resolve_search_products(request)
        primary_product = product_ids[0] if product_ids else "auto"

        # Long-term Memory 저장
        if product_ids and rag.product_memory and rag.product_memory.available:
            user_id = getattr(request, "user_id", None) or "anonymous"
            session_id = getattr(request, "session_id", None) or "default"
            rag.product_memory.save_product_context(
                user_id=user_id,
                session_id=session_id,
                product_id=primary_product,
                query=request.message,
                confidence=router_result.confidence,
            )

        # 분류 결과 SSE 전송
        yield {
            "type": "classification",
            "product": primary_product,
            "products": product_ids,
            "decision": router_result.decision.value,
            "confidence": router_result.confidence,
        }

        # 되묻기/매칭 실패 → 원래 로직 위임
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

        if not product_ids:
            yield {
                "type": "error",
                "message": "該当する製品を特定できませんでした。製品を選択してください。",
            }
            return

        # 2. Agent Mode 체크 (CODE/PLANNER → 원래 로직 위임)
        effective_mode = rag._classify_agent_mode(
            request.message, request.agent_mode,
        )
        if effective_mode != AgentMode.RAG:
            # CODE/PLANNER 모드는 Agent Teams 적용하지 않음
            async for event in rag.stream_chat(request):
                if event.get("type") != "classification":
                    yield event
            return

        # =================================================================
        # Pattern D: Multi-Product Collaboration
        # =================================================================
        if (
            self._settings.AGENT_TEAMS_MULTI_PRODUCT
            and len(product_ids) >= 2
            and self._get_multi_product().is_multi_product_query(
                request.message, product_ids
            )
        ):
            yield {"type": "team_pattern", "pattern": "multi_product_collab"}
            logger.info(
                f"[AgentTeams] Pattern D: multi-product collab for "
                f"{product_ids}"
            )

            collab_result = await self._get_multi_product().execute_collaboration(
                query=request.message,
                product_ids=product_ids,
                language=request.language or "ja",
                rag_service=rag,
            )

            if collab_result.get("synthesized_answer"):
                yield {
                    "type": "llm_token",
                    "token": collab_result["synthesized_answer"],
                }
                yield {
                    "type": "team_result",
                    "pattern": "multi_product_collab",
                    "products_used": collab_result.get("products_used", []),
                }

                # Pattern E: 피드백 기록
                if self._settings.AGENT_TEAMS_SELF_IMPROVEMENT:
                    self._get_self_improvement().record_interaction(
                        query=request.message,
                        product=primary_product,
                        answer=collab_result["synthesized_answer"],
                        pattern_used="multi_product_collab",
                    )

                yield {
                    "type": "done",
                    "processing_time_ms": int((time.time() - start) * 1000),
                    "product": primary_product,
                    "products": product_ids,
                }
                return

        # =================================================================
        # Pattern A: Parallel Retrieval
        # =================================================================
        if self._settings.AGENT_TEAMS_PARALLEL_RETRIEVAL:
            yield {
                "type": "search_progress",
                "product": primary_product,
                "products": product_ids,
                "step": "parallel_retrieval",
                "progress": 0.3,
            }

            query_type = rag.query_type_classifier.classify(request.message)
            logger.info(
                f"[AgentTeams] Pattern A: parallel retrieval, "
                f"query_type={query_type}"
            )

            winner, loser = await self._get_parallel_retrieval().retrieve_parallel(
                query=request.message,
                product_ids=product_ids,
                language=request.language or "ja",
                query_type=query_type,
            )

            yield {
                "type": "retrieval_comparison",
                "winner": winner.source,
                "winner_score": round(winner.score, 3),
                "loser": loser.source if loser else None,
                "loser_score": round(loser.score, 3) if loser else None,
                "winner_latency_ms": winner.latency_ms,
                "loser_latency_ms": loser.latency_ms if loser else None,
            }

            if winner.context:
                # =============================================================
                # Pattern C: Domain Specialist (FREEFORM + pdf_rag winner)
                # =============================================================
                if (
                    self._settings.AGENT_TEAMS_DOMAIN_SPECIALIST
                    and query_type == QueryType.FREEFORM
                    and winner.source == "pdf_rag"
                ):
                    specialists = self._get_domain_specialist()
                    specialist_products = specialists.get_specialist_products(
                        primary_product, product_ids
                    )

                    if len(specialist_products) > 1:
                        logger.info(
                            f"[AgentTeams] Pattern C: domain specialist, "
                            f"products={specialist_products}"
                        )
                        yield {
                            "type": "team_pattern",
                            "pattern": "domain_specialist",
                        }

                        answers = await specialists.generate_specialist_answers(
                            query=request.message,
                            context=winner.context,
                            specialist_products=specialist_products,
                        )

                        if answers:
                            best = specialists.select_winner(answers)
                            yield {
                                "type": "specialist_result",
                                "candidates": [
                                    {
                                        "adapter": a.adapter_name,
                                        "confidence": round(a.confidence, 3),
                                        "latency_ms": a.latency_ms,
                                    }
                                    for a in answers
                                ],
                                "winner": best.adapter_name if best else None,
                            }

                            if best and best.answer:
                                yield {
                                    "type": "llm_token",
                                    "token": best.answer,
                                }

                                # sources
                                if winner.search_results:
                                    yield rag._build_sources_event(
                                        winner.search_results
                                    )

                                # Pattern E
                                if self._settings.AGENT_TEAMS_SELF_IMPROVEMENT:
                                    self._get_self_improvement().record_interaction(
                                        query=request.message,
                                        product=primary_product,
                                        answer=best.answer,
                                        specialist_answers=[
                                            {
                                                "adapter": a.adapter_name,
                                                "confidence": a.confidence,
                                            }
                                            for a in answers
                                        ],
                                        retrieval_source="domain_specialist",
                                        pattern_used="domain_specialist",
                                    )

                                yield {
                                    "type": "done",
                                    "processing_time_ms": int(
                                        (time.time() - start) * 1000
                                    ),
                                    "product": primary_product,
                                    "products": product_ids,
                                }
                                return

                # =============================================================
                # Pattern B: Competitive Hypothesis (optional)
                # =============================================================
                if (
                    self._settings.AGENT_TEAMS_COMPETITIVE_HYPOTHESIS
                    and query_type == QueryType.FREEFORM
                    and winner.search_results
                    and len(winner.search_results) >= 3
                ):
                    logger.info("[AgentTeams] Pattern B: competitive hypothesis")
                    yield {
                        "type": "team_pattern",
                        "pattern": "competitive_hypothesis",
                    }

                    adapter_product = rag._map_product_for_llm(primary_product)
                    hyp_result = await self._get_competitive().generate_and_evaluate(
                        query=request.message,
                        context=winner.context,
                        product=adapter_product,
                    )

                    if hyp_result.get("winner"):
                        hyp_winner = hyp_result["winner"]
                        yield {
                            "type": "hypothesis_result",
                            "winner_label": hyp_winner.config.label,
                            "winner_score": round(hyp_winner.score, 3),
                            "candidates_count": len(
                                hyp_result.get("all_hypotheses", [])
                            ),
                        }
                        yield {"type": "llm_token", "token": hyp_winner.answer}

                        if winner.search_results:
                            yield rag._build_sources_event(winner.search_results)

                        if self._settings.AGENT_TEAMS_SELF_IMPROVEMENT:
                            self._get_self_improvement().record_interaction(
                                query=request.message,
                                product=primary_product,
                                answer=hyp_winner.answer,
                                retrieval_source=winner.source,
                                pattern_used="competitive_hypothesis",
                            )

                        yield {
                            "type": "done",
                            "processing_time_ms": int(
                                (time.time() - start) * 1000
                            ),
                            "product": primary_product,
                            "products": product_ids,
                        }
                        return

                # 표준 LLM 스트리밍 (Pattern A 승자 컨텍스트 사용)
                full_response = ""
                async for token in rag._stream_llm_from_context(
                    request.message,
                    primary_product,
                    winner.context,
                    request.language or "ja",
                    history=request.history,
                ):
                    full_response += token
                    yield {"type": "llm_token", "token": token}

                # Sources
                if winner.source == "web_doc" and winner.web_doc_result:
                    yield {
                        "type": "sources",
                        "results": [{
                            "doc_name": winner.web_doc_result.title,
                            "source_page": winner.web_doc_result.url,
                            "score": winner.web_doc_result.normalized_score,
                            "domain": "web_doc",
                            "url": winner.web_doc_result.url,
                        }],
                    }
                elif winner.search_results:
                    yield rag._build_sources_event(winner.search_results)

                # Pattern E
                if self._settings.AGENT_TEAMS_SELF_IMPROVEMENT and full_response:
                    self._get_self_improvement().record_interaction(
                        query=request.message,
                        product=primary_product,
                        answer=full_response,
                        retrieval_source=winner.source,
                        pattern_used="parallel_retrieval",
                    )

                yield {
                    "type": "done",
                    "processing_time_ms": int((time.time() - start) * 1000),
                    "product": primary_product,
                    "products": product_ids,
                }
                return

        # =================================================================
        # Fallback: 원래 stream_chat (패턴 미적용 또는 검색 실패)
        # =================================================================
        logger.info("[AgentTeams] Falling back to original stream_chat")
        async for event in rag.stream_chat(request):
            if event.get("type") != "classification":
                yield event


# =========================================================================
# Singleton
# =========================================================================

_orchestrator_instance: Optional[TeamOrchestrator] = None


def get_team_orchestrator() -> TeamOrchestrator:
    """TeamOrchestrator 싱글톤"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = TeamOrchestrator()
    return _orchestrator_instance
