"""
RAG Accuracy Pipeline: Unified integration layer for RAG accuracy improvement services.

This module integrates:
- QueryAnalyzerService
- RelevanceGraderService
- FaithfulnessCheckerService
- QueryRewriterService
- PartialMatchHandler

Usage:
    from app.api.services.rag_accuracy_pipeline import get_rag_accuracy_pipeline

    pipeline = get_rag_accuracy_pipeline()

    # Analyze and grade search results
    result = await pipeline.process_search_results(
        query="osc.confの設定方法",
        search_results=results,
    )

Created as part of PDCA: rag-accuracy-improvement
"""

import os
import logging
from typing import Dict, Any, List, Optional, Tuple

from ..models.rag_accuracy import (
    QueryAnalysis,
    GradingResult,
    FaithfulnessResult,
    RelevanceGrade,
    SupportLevel,
    RAGAccuracyConfig,
)
from .query_analyzer_service import get_query_analyzer_service, QueryAnalyzerService
from .relevance_grader_service import get_relevance_grader_service, RelevanceGraderService
from .faithfulness_checker_service import get_faithfulness_checker_service, FaithfulnessCheckerService
from .query_rewriter_service import get_query_rewriter_service, QueryRewriterService
from .partial_match_handler import get_partial_match_handler, PartialMatchHandler

logger = logging.getLogger(__name__)


class RAGAccuracyPipeline:
    """
    RAG 정확도 개선 통합 파이프라인

    통합 흐름:
    1. Query Analysis: 쿼리 분석 및 메타데이터 추출
    2. Relevance Grading: 검색 결과 관련성 평가
    3. Query Rewriting: 필요시 쿼리 재작성
    4. Faithfulness Checking: 응답 근거 검증
    5. Partial Match Handling: 부분 일치 응답 처리
    """

    def __init__(
        self,
        query_analyzer: Optional[QueryAnalyzerService] = None,
        relevance_grader: Optional[RelevanceGraderService] = None,
        faithfulness_checker: Optional[FaithfulnessCheckerService] = None,
        query_rewriter: Optional[QueryRewriterService] = None,
        partial_match_handler: Optional[PartialMatchHandler] = None,
        config: Optional[RAGAccuracyConfig] = None,
    ):
        self.query_analyzer = query_analyzer or get_query_analyzer_service()
        self.relevance_grader = relevance_grader or get_relevance_grader_service()
        self.faithfulness_checker = faithfulness_checker or get_faithfulness_checker_service()
        self.query_rewriter = query_rewriter or get_query_rewriter_service()
        self.partial_match_handler = partial_match_handler or get_partial_match_handler()
        self.config = config or self._load_config_from_env()

    def _load_config_from_env(self) -> RAGAccuracyConfig:
        """환경변수에서 설정 로드"""
        return RAGAccuracyConfig(
            enable_relevance_grading=os.getenv(
                "RAG_ACCURACY_ENABLE_GRADING", "true"
            ).lower() == "true",
            enable_faithfulness_check=os.getenv(
                "RAG_ACCURACY_ENABLE_FAITHFULNESS", "true"
            ).lower() == "true",
            enable_query_rewrite=os.getenv(
                "RAG_ACCURACY_ENABLE_REWRITE", "true"
            ).lower() == "true",
            enable_partial_response=os.getenv(
                "RAG_ACCURACY_ENABLE_PARTIAL", "true"
            ).lower() == "true",
            max_rewrite_attempts=int(os.getenv("RAG_ACCURACY_MAX_REWRITE", "2")),
        )

    def analyze_query(self, query: str) -> QueryAnalysis:
        """
        쿼리 분석 수행

        Args:
            query: 사용자 쿼리

        Returns:
            QueryAnalysis: 분석 결과
        """
        return self.query_analyzer.analyze(query)

    def grade_search_results(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        query_analysis: Optional[QueryAnalysis] = None,
    ) -> Tuple[GradingResult, List[Dict[str, Any]]]:
        """
        검색 결과 그레이딩 및 필터링

        Args:
            query: 사용자 쿼리
            search_results: 검색 결과
            query_analysis: 쿼리 분석 결과 (선택, 없으면 자동 분석)

        Returns:
            Tuple[GradingResult, List[Dict]]: 그레이딩 결과와 필터링된 검색 결과
        """
        if not self.config.enable_relevance_grading:
            # Grading disabled, return all results
            dummy_grading = GradingResult(
                query_analysis=query_analysis or self.analyze_query(query),
                graded_results=[],
                relevant_count=len(search_results),
                partial_count=0,
                irrelevant_count=0,
                needs_rewrite=False,
            )
            return dummy_grading, search_results

        # Analyze query if not provided
        if query_analysis is None:
            query_analysis = self.analyze_query(query)

        # Grade results
        grading_result = self.relevance_grader.grade_results(
            query_analysis=query_analysis,
            search_results=search_results,
        )

        # Filter to relevant results
        filtered_results = self.relevance_grader.filter_relevant_results(
            grading_result=grading_result,
            search_results=search_results,
            include_partial=True,  # Include partial matches
        )

        logger.info(
            f"[RAGAccuracyPipeline] Graded {len(search_results)} results: "
            f"{grading_result.relevant_count} relevant, "
            f"{grading_result.partial_count} partial, "
            f"{grading_result.irrelevant_count} irrelevant"
        )

        return grading_result, filtered_results

    def check_faithfulness(
        self,
        answer: str,
        search_results: List[Dict[str, Any]],
    ) -> FaithfulnessResult:
        """
        응답 충실도 검증

        Args:
            answer: 생성된 응답
            search_results: 검색 결과

        Returns:
            FaithfulnessResult: 충실도 검증 결과
        """
        if not self.config.enable_faithfulness_check:
            return FaithfulnessResult(
                answer=answer,
                support_level=SupportLevel.FULLY_SUPPORTED,
                verified_claims=[],
                unsupported_claims=[],
                confidence=1.0,
            )

        # Combine context from search results
        context = "\n".join([
            r.get("content", "") or r.get("text", "")
            for r in search_results
        ])

        return self.faithfulness_checker.check_faithfulness(
            answer=answer,
            context=context,
            graded_results=search_results,
        )

    def rewrite_query(
        self,
        query: str,
        query_analysis: Optional[QueryAnalysis] = None,
        attempt: int = 1,
    ) -> str:
        """
        쿼리 재작성

        Args:
            query: 원본 쿼리
            query_analysis: 쿼리 분석 결과 (선택)
            attempt: 재시도 횟수

        Returns:
            재작성된 쿼리
        """
        if not self.config.enable_query_rewrite:
            return query

        if attempt > self.config.max_rewrite_attempts:
            logger.warning(
                f"[RAGAccuracyPipeline] Max rewrite attempts ({self.config.max_rewrite_attempts}) reached"
            )
            return query

        if query_analysis is None:
            query_analysis = self.analyze_query(query)

        return self.query_rewriter.rewrite(
            query_analysis=query_analysis,
            attempt=attempt,
        )

    def build_partial_response(
        self,
        query: str,
        grading_result: GradingResult,
        faithfulness_result: Optional[FaithfulnessResult] = None,
    ) -> str:
        """
        부분 일치 응답 생성

        Args:
            query: 원본 쿼리
            grading_result: 그레이딩 결과
            faithfulness_result: 충실도 검증 결과 (선택)

        Returns:
            부분 일치 응답 문자열
        """
        if not self.config.enable_partial_response:
            return ""

        support_level = (
            faithfulness_result.support_level
            if faithfulness_result
            else SupportLevel.PARTIALLY_SUPPORTED
        )

        # Generate alternative queries
        alternative_queries = self.query_rewriter.generate_alternative_queries(
            query_analysis=grading_result.query_analysis,
            count=3,
        )

        return self.partial_match_handler.build_partial_response(
            query_analysis=grading_result.query_analysis,
            graded_results=grading_result.graded_results,
            support_level=support_level,
            alternative_queries=alternative_queries,
        )

    async def process_search_results(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        max_rewrite_attempts: int = 2,
        search_function: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        검색 결과 처리 통합 파이프라인

        쿼리 재작성이 필요한 경우 search_function을 호출하여 재검색합니다.

        Args:
            query: 사용자 쿼리
            search_results: 검색 결과
            max_rewrite_attempts: 최대 재시도 횟수
            search_function: 재검색 함수 (async, query -> results)

        Returns:
            Dict with:
                - query_analysis: 쿼리 분석 결과
                - grading_result: 그레이딩 결과
                - filtered_results: 필터링된 검색 결과
                - rewritten_query: 재작성된 쿼리 (있는 경우)
                - needs_partial_response: 부분 응답 필요 여부
        """
        # Step 1: Analyze query
        query_analysis = self.analyze_query(query)

        # Step 2: Grade search results
        grading_result, filtered_results = self.grade_search_results(
            query=query,
            search_results=search_results,
            query_analysis=query_analysis,
        )

        # Step 3: Rewrite and retry if needed
        rewritten_query = None
        attempt = 0

        while grading_result.needs_rewrite and attempt < max_rewrite_attempts:
            attempt += 1
            rewritten_query = self.rewrite_query(
                query=query,
                query_analysis=query_analysis,
                attempt=attempt,
            )

            if rewritten_query == query:
                # No rewrite possible
                break

            logger.info(
                f"[RAGAccuracyPipeline] Rewriting query (attempt {attempt}): "
                f"'{query[:30]}...' → '{rewritten_query[:30]}...'"
            )

            # Re-search if search function provided
            if search_function:
                try:
                    new_results = await search_function(rewritten_query)
                    if new_results:
                        grading_result, filtered_results = self.grade_search_results(
                            query=rewritten_query,
                            search_results=new_results,
                            query_analysis=query_analysis,
                        )
                except Exception as e:
                    logger.warning(f"[RAGAccuracyPipeline] Re-search failed: {e}")
            else:
                # No search function, just return the rewritten query
                break

        # Determine if partial response is needed
        needs_partial_response = (
            grading_result.relevant_count == 0 and
            grading_result.partial_count > 0
        )

        return {
            "query_analysis": query_analysis,
            "grading_result": grading_result,
            "filtered_results": filtered_results,
            "rewritten_query": rewritten_query,
            "needs_partial_response": needs_partial_response,
            "rewrite_attempts": attempt,
        }

    def should_use_partial_response(
        self,
        grading_result: GradingResult,
        faithfulness_result: Optional[FaithfulnessResult] = None,
    ) -> bool:
        """
        부분 응답 사용 여부 결정

        Args:
            grading_result: 그레이딩 결과
            faithfulness_result: 충실도 검증 결과

        Returns:
            부분 응답 사용 여부
        """
        # No relevant results, only partial
        if grading_result.relevant_count == 0 and grading_result.partial_count > 0:
            return True

        # Faithfulness check failed
        if faithfulness_result and faithfulness_result.support_level == SupportLevel.NOT_SUPPORTED:
            return True

        return False


# =============================================================================
# Singleton Pattern
# =============================================================================

_rag_accuracy_pipeline: Optional[RAGAccuracyPipeline] = None


def get_rag_accuracy_pipeline() -> RAGAccuracyPipeline:
    """RAGAccuracyPipeline 싱글톤 반환"""
    global _rag_accuracy_pipeline
    if _rag_accuracy_pipeline is None:
        _rag_accuracy_pipeline = RAGAccuracyPipeline()
    return _rag_accuracy_pipeline
