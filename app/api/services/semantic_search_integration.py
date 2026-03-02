"""
Semantic Search Integration Module

기존 unified_search와 semantic_search를 통합하는 어댑터 모듈
Feature Flag로 점진적 전환 지원

Usage:
    from app.api.services.semantic_search_integration import (
        get_search_service,
        search,
    )

    # 자동으로 USE_SEMANTIC_SEARCH 플래그에 따라 검색 방식 결정
    results = await search(query="ofasmifコマンドについて説明してください", top_k=10)
"""

import os
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable
from functools import wraps

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
from app.api.services.hybrid_retriever_service import (
    HybridRetrieverService,
    get_hybrid_retriever_service,
)

logger = logging.getLogger(__name__)

# =============================================================
# Feature Flags
# =============================================================

USE_SEMANTIC_SEARCH = os.getenv("USE_SEMANTIC_SEARCH", "true").lower() == "true"
SEMANTIC_SEARCH_FALLBACK = os.getenv("SEMANTIC_SEARCH_FALLBACK", "true").lower() == "true"
SEMANTIC_QUERY_UNDERSTANDING_ONLY = os.getenv("SEMANTIC_QUERY_UNDERSTANDING_ONLY", "false").lower() == "true"


# =============================================================
# Search Service Facade
# =============================================================

class SemanticSearchService:
    """
    Semantic Search 통합 서비스

    기존 검색 함수들을 주입받아 HybridRetriever와 통합
    """

    def __init__(
        self,
        neo4j_driver=None,
        vector_search_func: Callable = None,
        keyword_search_func: Callable = None,
    ):
        self._neo4j = neo4j_driver
        self._vector_search_func = vector_search_func
        self._keyword_search_func = keyword_search_func

        # Lazy initialization
        self._query_understanding: Optional[QueryUnderstandingService] = None
        self._entity_lookup: Optional[EntityLookupService] = None
        self._result_fusion: Optional[ResultFusionService] = None
        self._hybrid_retriever: Optional[HybridRetrieverService] = None

        self._initialized = False

    async def initialize(self):
        """서비스 초기화"""
        if self._initialized:
            return

        try:
            # 서비스 인스턴스 생성
            self._query_understanding = get_query_understanding_service()
            self._entity_lookup = get_entity_lookup_service(self._neo4j)
            self._result_fusion = get_result_fusion_service()

            # Entity 인덱스 초기화
            await self._entity_lookup.initialize()

            # HybridRetriever 생성
            self._hybrid_retriever = HybridRetrieverService(
                query_understanding=self._query_understanding,
                entity_lookup=self._entity_lookup,
                result_fusion=self._result_fusion,
                vector_search_func=self._vector_search_func,
                keyword_search_func=self._keyword_search_func,
            )

            self._initialized = True
            logger.info("SemanticSearchService initialized successfully")

        except Exception as e:
            logger.error(f"SemanticSearchService initialization failed: {e}")
            raise

    def set_vector_search(self, func: Callable):
        """Vector 검색 함수 설정"""
        self._vector_search_func = func
        if self._hybrid_retriever:
            self._hybrid_retriever.set_vector_search(func)

    def set_keyword_search(self, func: Callable):
        """Keyword 검색 함수 설정"""
        self._keyword_search_func = func
        if self._hybrid_retriever:
            self._hybrid_retriever.set_keyword_search(func)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        **kwargs
    ) -> HybridSearchResult:
        """
        하이브리드 검색 실행

        Args:
            query: 사용자 쿼리
            top_k: 반환할 결과 수

        Returns:
            HybridSearchResult
        """
        if not self._initialized:
            await self.initialize()

        return await self._hybrid_retriever.search(
            query=query,
            top_k=top_k,
            **kwargs
        )

    def analyze_query_sync(self, query: str) -> QueryAnalysis:
        """
        동기 쿼리 분석 (BM25 전처리용)

        기존 BM25 검색에서 Query Understanding만 활용할 때 사용
        """
        if self._query_understanding is None:
            self._query_understanding = get_query_understanding_service()

        return self._query_understanding.analyze_sync(query)

    async def analyze_query(self, query: str) -> QueryAnalysis:
        """비동기 쿼리 분석"""
        if self._query_understanding is None:
            self._query_understanding = get_query_understanding_service()

        return await self._query_understanding.analyze(query)


# =============================================================
# Singleton & Factory
# =============================================================

_service_instance: Optional[SemanticSearchService] = None


def get_search_service() -> SemanticSearchService:
    """SemanticSearchService 싱글톤 반환"""
    global _service_instance
    if _service_instance is None:
        _service_instance = SemanticSearchService()
    return _service_instance


async def initialize_search_service(
    neo4j_driver=None,
    vector_search_func: Callable = None,
    keyword_search_func: Callable = None,
) -> SemanticSearchService:
    """
    검색 서비스 초기화 (앱 시작 시 호출)

    Args:
        neo4j_driver: Neo4j 드라이버
        vector_search_func: Vector 검색 함수
        keyword_search_func: Keyword 검색 함수
    """
    global _service_instance

    _service_instance = SemanticSearchService(
        neo4j_driver=neo4j_driver,
        vector_search_func=vector_search_func,
        keyword_search_func=keyword_search_func,
    )

    await _service_instance.initialize()
    return _service_instance


# =============================================================
# Convenience Functions
# =============================================================

async def search(
    query: str,
    top_k: int = 10,
    fallback_func: Callable = None,
    **kwargs
) -> Dict[str, Any]:
    """
    통합 검색 함수 (Feature Flag 자동 적용)

    Args:
        query: 검색 쿼리
        top_k: 결과 수
        fallback_func: Semantic Search 비활성화 시 사용할 함수

    Returns:
        검색 결과 딕셔너리
    """
    # Feature Flag 확인
    if not USE_SEMANTIC_SEARCH:
        if fallback_func:
            return await fallback_func(query, top_k=top_k, **kwargs)
        return {"results": [], "error": "Semantic search disabled and no fallback provided"}

    try:
        service = get_search_service()
        result = await service.search(query, top_k=top_k, **kwargs)

        return {
            "results": [
                {
                    "doc_id": r.doc_id,
                    "content": r.content,
                    "score": r.score,
                    "source": r.source,
                    "document_title": r.document_title,
                    "page_number": r.page_number,
                    "metadata": r.metadata,
                }
                for r in result.results
            ],
            "query_analysis": {
                "intent": result.query_analysis.intent.value if result.query_analysis else None,
                "entities": [
                    {"type": e.type, "value": e.value}
                    for e in (result.query_analysis.entities if result.query_analysis else [])
                ],
                "rewritten_query": result.query_analysis.rewritten_query if result.query_analysis else query,
            },
            "metadata": {
                "total_candidates": result.total_candidates,
                "search_time_ms": result.search_time_ms,
            }
        }

    except Exception as e:
        logger.error(f"Semantic search error: {e}")

        # Fallback
        if SEMANTIC_SEARCH_FALLBACK and fallback_func:
            logger.info("Falling back to legacy search")
            return await fallback_func(query, top_k=top_k, **kwargs)

        return {"results": [], "error": str(e)}


def preprocess_query_for_search(query: str) -> Dict[str, Any]:
    """
    검색 전 쿼리 전처리 (동기)

    기존 BM25 검색에서 Query Understanding만 활용할 때 사용

    Returns:
        {
            "rewritten_query": "검색 최적화된 쿼리",
            "entities": [{"type": "command", "value": "ofasmif"}],
            "intent": "explanation",
            "keywords": ["ofasmif", "OFASM", ...]
        }
    """
    if not USE_SEMANTIC_SEARCH and not SEMANTIC_QUERY_UNDERSTANDING_ONLY:
        return {"rewritten_query": query, "entities": [], "intent": "search", "keywords": []}

    try:
        service = get_search_service()
        analysis = service.analyze_query_sync(query)

        return {
            "rewritten_query": analysis.rewritten_query,
            "entities": [
                {"type": e.type, "value": e.value}
                for e in analysis.entities
            ],
            "intent": analysis.intent.value,
            "keywords": analysis.keywords,
            "language": analysis.language,
        }

    except Exception as e:
        logger.warning(f"Query preprocessing error: {e}")
        return {"rewritten_query": query, "entities": [], "intent": "search", "keywords": []}


# =============================================================
# Decorator for Easy Integration
# =============================================================

def with_semantic_search(fallback_to_original: bool = True):
    """
    기존 검색 함수에 Semantic Search를 적용하는 데코레이터

    Usage:
        @with_semantic_search()
        async def my_search(query: str, top_k: int = 10):
            # Original search logic
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(query: str, top_k: int = 10, *args, **kwargs):
            if USE_SEMANTIC_SEARCH:
                try:
                    result = await search(query, top_k=top_k)
                    if result.get("results"):
                        return result
                except Exception as e:
                    logger.warning(f"Semantic search failed, falling back: {e}")

            # Fallback to original
            if fallback_to_original:
                return await func(query, top_k=top_k, *args, **kwargs)

            return {"results": [], "error": "Search failed"}

        return wrapper
    return decorator


# =============================================================
# Integration Helpers
# =============================================================

def create_vector_search_adapter(neo4j_vector_search_func: Callable) -> Callable:
    """
    기존 Neo4j vector search 함수를 어댑터로 래핑

    Args:
        neo4j_vector_search_func: 기존 vector search 함수

    Returns:
        HybridRetriever 호환 함수
    """
    async def adapter(query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        results = await neo4j_vector_search_func(query, top_k=top_k)

        # 결과 포맷 통일
        return [
            {
                "id": r.get("id", r.get("chunk_id", "")),
                "content": r.get("content", r.get("text", "")),
                "score": r.get("score", r.get("similarity", 0.0)),
                "title": r.get("title", r.get("document_title", "")),
                "page_number": r.get("page_number"),
                "pdf_path": r.get("pdf_path"),
                "metadata": r.get("metadata", {}),
            }
            for r in results
        ]

    return adapter


def create_keyword_search_adapter(bm25_search_func: Callable) -> Callable:
    """
    기존 BM25 search 함수를 어댑터로 래핑

    Args:
        bm25_search_func: 기존 BM25 search 함수

    Returns:
        HybridRetriever 호환 함수
    """
    async def adapter(query: str, top_k: int = 20) -> List[Dict[str, Any]]:
        # BM25 서비스 호출
        results = await bm25_search_func(query, top_k=top_k)

        # 결과 포맷 통일
        return [
            {
                "id": r.get("id", r.get("doc_id", "")),
                "content": r.get("content", r.get("body", "")),
                "score": r.get("score", r.get("bm25_score", 0.0)),
                "title": r.get("title", r.get("name", "")),
                "page_number": r.get("page_number"),
                "pdf_path": r.get("pdf_file"),
                "metadata": r.get("metadata", {}),
            }
            for r in results
        ]

    return adapter
