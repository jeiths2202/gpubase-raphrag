"""
Pattern A: Parallel Retrieval + Context Merge

Web Doc 검색과 PDF RAG 검색을 asyncio.gather()로 동시 실행.
score 비교 후 승자 컨텍스트로 LLM 응답 생성.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """하나의 검색 채널 결과"""
    source: str                          # "web_doc" or "pdf_rag"
    score: float                         # normalized 0.0 - 1.0
    context: Optional[str] = None        # LLM에 전달할 텍스트 컨텍스트
    search_results: Optional[list] = None  # PDF RAG의 SearchResult 리스트
    web_doc_result: Optional[object] = None  # WebDocSearchResult
    web_content: Optional[str] = None
    latency_ms: int = 0


class ParallelRetrievalService:
    """
    Web Doc 검색과 PDF RAG 검색을 병렬 실행.
    score 비교로 최적 채널 선택.
    """

    def __init__(self, rag_service):
        """
        Args:
            rag_service: AgenticRAGService 인스턴스
        """
        self._rag = rag_service

    async def retrieve_parallel(
        self,
        query: str,
        product_ids: List[str],
        language: str = "ja",
        query_type=None,
    ) -> Tuple[RetrievalResult, Optional[RetrievalResult]]:
        """
        Web Doc과 PDF RAG를 병렬 실행.

        Returns:
            (winner, loser) 튜플. loser는 하나만 성공 시 None.
        """
        web_task = self._web_doc_retrieve(query, language, product_ids)
        pdf_task = self._pdf_rag_retrieve(query, product_ids, query_type)

        results = await asyncio.gather(
            web_task, pdf_task, return_exceptions=True
        )

        web_result = results[0] if not isinstance(results[0], Exception) else None
        pdf_result = results[1] if not isinstance(results[1], Exception) else None

        if isinstance(results[0], Exception):
            logger.warning(f"Web doc retrieve failed: {results[0]}")
        if isinstance(results[1], Exception):
            logger.warning(f"PDF RAG retrieve failed: {results[1]}")

        if web_result and pdf_result:
            if web_result.score >= pdf_result.score:
                return web_result, pdf_result
            return pdf_result, web_result
        elif web_result:
            return web_result, None
        elif pdf_result:
            return pdf_result, None
        else:
            return RetrievalResult(source="pdf_rag", score=0.0), None

    async def _web_doc_retrieve(
        self, query: str, language: str, product_ids: List[str]
    ) -> RetrievalResult:
        """Web Doc 채널"""
        start = time.time()
        try:
            from ..web_doc_search_service import WEB_DOC_THRESHOLD

            web_doc_result = self._rag._search_web_doc(query, language, product_ids)
            if not web_doc_result or web_doc_result.normalized_score < WEB_DOC_THRESHOLD:
                return RetrievalResult(
                    source="web_doc", score=0.0,
                    latency_ms=int((time.time() - start) * 1000)
                )

            web_content = await self._rag._fetch_web_doc_content(web_doc_result.url)
            if not web_content:
                return RetrievalResult(
                    source="web_doc",
                    score=web_doc_result.normalized_score * 0.5,
                    latency_ms=int((time.time() - start) * 1000)
                )

            context = (
                f"[Web Documentation: {web_doc_result.title}]\n"
                f"URL: {web_doc_result.url}\n\n{web_content}"
            )
            return RetrievalResult(
                source="web_doc",
                score=web_doc_result.normalized_score,
                context=context,
                web_doc_result=web_doc_result,
                web_content=web_content,
                latency_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            logger.warning(f"Web doc retrieve error: {e}")
            return RetrievalResult(
                source="web_doc", score=0.0,
                latency_ms=int((time.time() - start) * 1000)
            )

    async def _pdf_rag_retrieve(
        self, query: str, product_ids: List[str], query_type=None,
    ) -> RetrievalResult:
        """PDF RAG 채널"""
        start = time.time()
        try:
            search_context = await self._rag._multi_product_search(
                query=query, product_ids=product_ids, query_type=query_type
            )
            best_score = 0.0
            if search_context and search_context.structured_results:
                best_score = search_context.structured_results[0].relevance_score

            context = None
            if search_context and search_context.structured_results:
                context = self._rag._build_llm_context(
                    search_context.structured_results
                )

            return RetrievalResult(
                source="pdf_rag",
                score=best_score,
                context=context,
                search_results=(
                    search_context.structured_results
                    if search_context else None
                ),
                latency_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            logger.warning(f"PDF RAG retrieve error: {e}")
            return RetrievalResult(
                source="pdf_rag", score=0.0,
                latency_ms=int((time.time() - start) * 1000)
            )
