"""
Hybrid Retriever Service for Semantic Search

다중 검색 전략 조합 서비스
- Vector Search (Embedding 기반)
- Keyword Search (BM25)
- Entity Lookup (직접 조회)
- Result Fusion (RRF)
"""

import os
import asyncio
import logging
import time
from typing import List, Dict, Optional, Any

from app.api.models.query_analysis import (
    QueryAnalysis,
    RetrievalResult,
    HybridSearchResult,
)
from app.api.services.query_understanding_service import (
    QueryUnderstandingService,
    get_query_understanding_service,
)
from app.api.services.entity_lookup_service import (
    EntityLookupService,
    get_entity_lookup_service,
)
from app.api.services.result_fusion_service import (
    ResultFusionService,
    get_result_fusion_service,
)

logger = logging.getLogger(__name__)


class HybridRetrieverService:
    """다중 검색 전략 조합 서비스"""

    def __init__(
        self,
        query_understanding: QueryUnderstandingService = None,
        entity_lookup: EntityLookupService = None,
        result_fusion: ResultFusionService = None,
        vector_search_func=None,
        keyword_search_func=None,
        weights: Dict[str, float] = None,
    ):
        """
        Args:
            query_understanding: 쿼리 분석 서비스
            entity_lookup: Entity 조회 서비스
            result_fusion: 결과 통합 서비스
            vector_search_func: Vector 검색 함수 (외부 주입)
            keyword_search_func: Keyword 검색 함수 (외부 주입)
            weights: 검색 소스별 가중치
        """
        self.query_understanding = query_understanding or get_query_understanding_service()
        self.entity_lookup = entity_lookup or get_entity_lookup_service()
        self.result_fusion = result_fusion or get_result_fusion_service()

        self.vector_search_func = vector_search_func
        self.keyword_search_func = keyword_search_func

        self.weights = weights or {
            "entity": float(os.getenv("RETRIEVAL_WEIGHT_ENTITY", "1.2")),
            "vector": float(os.getenv("RETRIEVAL_WEIGHT_VECTOR", "1.0")),
            "keyword": float(os.getenv("RETRIEVAL_WEIGHT_KEYWORD", "0.8")),
        }

        # Feature flag
        self.enabled = os.getenv("USE_SEMANTIC_SEARCH", "true").lower() == "true"

    async def search(
        self,
        query: str,
        top_k: int = 10,
        include_analysis: bool = True,
        **kwargs
    ) -> HybridSearchResult:
        """
        하이브리드 검색 실행

        Args:
            query: 사용자 쿼리
            top_k: 반환할 최대 결과 수
            include_analysis: 쿼리 분석 결과 포함 여부

        Returns:
            HybridSearchResult with ranked results
        """
        start_time = time.time()

        # 1. Query Understanding
        analysis = await self.query_understanding.analyze(query)
        logger.info(f"Query analysis: intent={analysis.intent}, "
                   f"entities={[e.value for e in analysis.entities]}, "
                   f"rewritten='{analysis.rewritten_query[:50]}...'")

        # 2. Parallel Retrieval
        retrieval_start = time.time()

        # 병렬 실행할 태스크들
        tasks = []

        # Entity Lookup (항상 실행)
        tasks.append(self._entity_search(analysis))

        # Vector Search (함수가 있으면 실행)
        if self.vector_search_func:
            tasks.append(self._vector_search(query, analysis, top_k * 2))
        else:
            tasks.append(self._empty_results())

        # Keyword Search (함수가 있으면 실행)
        if self.keyword_search_func:
            tasks.append(self._keyword_search(analysis.rewritten_query, top_k * 2))
        else:
            tasks.append(self._empty_results())

        # 병렬 실행
        entity_results, vector_results, keyword_results = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        # 예외 처리
        if isinstance(entity_results, Exception):
            logger.warning(f"Entity search failed: {entity_results}")
            entity_results = []
        if isinstance(vector_results, Exception):
            logger.warning(f"Vector search failed: {vector_results}")
            vector_results = []
        if isinstance(keyword_results, Exception):
            logger.warning(f"Keyword search failed: {keyword_results}")
            keyword_results = []

        retrieval_time = (time.time() - retrieval_start) * 1000
        logger.debug(f"Retrieval time: {retrieval_time:.1f}ms "
                    f"(entity={len(entity_results)}, vector={len(vector_results)}, "
                    f"keyword={len(keyword_results)})")

        # 3. Result Fusion (RRF)
        results_by_source = {
            "entity": entity_results,
            "vector": vector_results,
            "keyword": keyword_results,
        }

        fused_results = self.result_fusion.fuse(
            results_by_source=results_by_source,
            weights=self.weights,
            top_k=top_k
        )

        # 4. 중복 제거
        fused_results = self.result_fusion.deduplicate(fused_results)

        # 5. 키워드 기반 재랭킹 (선택적)
        if analysis.keywords:
            fused_results = self.result_fusion.rerank_by_query_match(
                fused_results,
                analysis.keywords,
                boost_factor=0.05
            )

        # 6. 최종 Top-K
        final_results = fused_results[:top_k]

        total_time = (time.time() - start_time) * 1000
        logger.info(f"Hybrid search completed: {len(final_results)} results in {total_time:.1f}ms")

        return HybridSearchResult(
            query_analysis=analysis if include_analysis else None,
            results=final_results,
            total_candidates=len(entity_results) + len(vector_results) + len(keyword_results),
            search_time_ms=total_time,
            vector_count=len(vector_results),
            keyword_count=len(keyword_results),
            entity_count=len(entity_results),
        )

    async def _entity_search(self, analysis: QueryAnalysis) -> List[RetrievalResult]:
        """Entity 기반 검색"""
        if not analysis.entities:
            return []

        await self.entity_lookup.initialize()
        return await self.entity_lookup.lookup(analysis.entities, max_results=10)

    async def _vector_search(
        self,
        query: str,
        analysis: QueryAnalysis,
        top_k: int
    ) -> List[RetrievalResult]:
        """Vector 유사도 검색"""
        if not self.vector_search_func:
            return []

        try:
            # 외부 vector_search 함수 호출
            results = await self.vector_search_func(query, top_k=top_k)

            # RetrievalResult로 변환
            return [
                RetrievalResult(
                    doc_id=r.get("id", r.get("doc_id", str(i))),
                    content=r.get("content", r.get("text", "")),
                    source="vector",
                    score=r.get("score", r.get("similarity", 0.0)),
                    metadata=r.get("metadata", {}),
                    document_title=r.get("title", r.get("document_title")),
                    page_number=r.get("page_number"),
                    pdf_path=r.get("pdf_path"),
                )
                for i, r in enumerate(results)
            ]
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

    async def _keyword_search(self, query: str, top_k: int) -> List[RetrievalResult]:
        """BM25 키워드 검색"""
        if not self.keyword_search_func:
            return []

        try:
            # 외부 keyword_search 함수 호출
            results = await self.keyword_search_func(query, top_k=top_k)

            # RetrievalResult로 변환
            return [
                RetrievalResult(
                    doc_id=r.get("id", r.get("doc_id", str(i))),
                    content=r.get("content", r.get("text", "")),
                    source="keyword",
                    score=r.get("score", r.get("bm25_score", 0.0)),
                    metadata=r.get("metadata", {}),
                    document_title=r.get("title", r.get("document_title")),
                    page_number=r.get("page_number"),
                    pdf_path=r.get("pdf_path"),
                )
                for i, r in enumerate(results)
            ]
        except Exception as e:
            logger.error(f"Keyword search error: {e}")
            return []

    async def _empty_results(self) -> List[RetrievalResult]:
        """빈 결과 반환 (병렬 실행용)"""
        return []

    def set_vector_search(self, func):
        """Vector 검색 함수 설정"""
        self.vector_search_func = func

    def set_keyword_search(self, func):
        """Keyword 검색 함수 설정"""
        self.keyword_search_func = func


# 싱글톤 인스턴스
_service_instance: Optional[HybridRetrieverService] = None


def get_hybrid_retriever_service() -> HybridRetrieverService:
    """HybridRetrieverService 싱글톤 반환"""
    global _service_instance
    if _service_instance is None:
        _service_instance = HybridRetrieverService()
    return _service_instance


async def create_hybrid_retriever(
    neo4j_driver=None,
    vector_search_func=None,
    keyword_search_func=None,
) -> HybridRetrieverService:
    """
    HybridRetrieverService 팩토리 함수

    Args:
        neo4j_driver: Neo4j 드라이버 (Entity 조회용)
        vector_search_func: Vector 검색 함수
        keyword_search_func: Keyword 검색 함수
    """
    entity_lookup = get_entity_lookup_service(neo4j_driver)
    await entity_lookup.initialize()

    service = HybridRetrieverService(
        entity_lookup=entity_lookup,
        vector_search_func=vector_search_func,
        keyword_search_func=keyword_search_func,
    )

    return service
