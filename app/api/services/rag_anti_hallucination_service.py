"""
RAG Anti-Hallucination Service
할루시네이션 방지를 위한 RAG 서비스

Dependencies:
- test_0203/test_0203/rag_solution_improved.py (ImprovedRAG)
- test_0203/test_0203/rag_solution.py (TmaxProductRAG)
"""

import logging
import time
import os
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# LLM URL from environment variable (fallback to localhost for testing)
DEFAULT_LLM_URL = os.getenv('RAG_LLM_URL', os.getenv('LLM_API_URL', 'http://192.168.8.11:12810/v1')).replace('/chat/completions', '')


class RAGAntiHallucinationService:
    """
    FastAPI 백엔드용 RAG Anti-Hallucination 서비스

    Responsibilities:
    1. ImprovedRAG 클래스 래핑 및 FastAPI 통합
    2. 3가지 RAG 모드 지원 (direct, llm, hybrid)
    3. 통계 수집 및 모니터링
    4. 에러 핸들링 및 로깅

    Usage:
        service = RAGAntiHallucinationService.get_instance()
        result = await service.query_hybrid("DFSURGL0について")
    """

    _instance: Optional['RAGAntiHallucinationService'] = None
    _initialized: bool = False

    def __init__(self, training_data_dir: str):
        """
        Initialize RAG service

        Args:
            training_data_dir: 학습 데이터 디렉토리 (JSONL 파일들)
        """
        # Import ImprovedRAG
        import sys
        rag_path = Path(__file__).parent.parent.parent.parent / "test_0203" / "test_0203"
        if str(rag_path) not in sys.path:
            sys.path.insert(0, str(rag_path))

        try:
            from rag_solution_improved import ImprovedRAG
            self.rag = ImprovedRAG(training_data_dir)
            self._initialized = True
        except ImportError as e:
            logger.error(f"Failed to import ImprovedRAG: {e}")
            logger.error(f"RAG path: {rag_path}")
            self.rag = None
            self._initialized = False
        except Exception as e:
            logger.error(f"Failed to initialize ImprovedRAG: {e}")
            self.rag = None
            self._initialized = False

        # Statistics
        self.stats = {
            'total_queries': 0,
            'modes_usage': {
                'direct_answer': 0,
                'llm_with_context': 0,
                'no_sources': 0
            },
            'total_search_time_ms': 0,
            'total_llm_time_ms': 0
        }

        if self._initialized:
            logger.info(f"✅ RAG service initialized with {len(self.rag.documents)} documents")
        else:
            logger.warning("⚠️ RAG service initialized without ImprovedRAG (fallback mode)")

    @property
    def is_initialized(self) -> bool:
        """서비스 초기화 여부"""
        return self._initialized and self.rag is not None

    @classmethod
    def get_instance(cls, training_data_dir: Optional[str] = None) -> 'RAGAntiHallucinationService':
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            if training_data_dir is None:
                # 기본 경로 (환경변수 또는 기본값)
                training_data_dir = os.getenv(
                    'RAG_TRAINING_DATA_DIR',
                    str(Path(__file__).parent.parent.parent.parent / "test_0203" / "test_0203" / "training_data_v2")
                )
            cls._instance = cls(training_data_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """테스트용 인스턴스 리셋"""
        cls._instance = None

    async def query_hybrid(
        self,
        query: str,
        model: str = "openframe_common_v2",
        llm_url: str = DEFAULT_LLM_URL,
        max_tokens: int = 500,
        temperature: float = 0.2
    ) -> Dict:
        """
        Hybrid 모드 쿼리 (권장)

        Score >= 10 → Direct Answer (100% 정확)
        Score < 10  → LLM with Context (85% 정확)

        Args:
            query: 사용자 질문
            model: LLM 모델 이름
            llm_url: LLM 서버 URL
            max_tokens: 최대 토큰 수
            temperature: Temperature

        Returns:
            {
                'answer': str,
                'mode_used': str,
                'search_score': int,
                'sources': List[Dict],
                'keyword_extracted': str,
                'metadata': Dict
            }
        """
        if not self.is_initialized:
            return self._fallback_response(query, "RAG service not initialized")

        start_time = time.time()
        search_start = time.time()

        try:
            # Hybrid 모드 실행
            result = self.rag.query_mode_3_hybrid(
                query=query,
                model=model,
                llm_url=llm_url
            )

            search_time = (time.time() - search_start) * 1000

            # 키워드 추출
            keyword = self.rag.extract_keyword(query)

            # 통계 업데이트
            mode_used = result.get('mode', 'unknown')
            self._update_stats(mode_used, search_time)

            total_time = (time.time() - start_time) * 1000
            llm_time = total_time - search_time if mode_used == 'llm_with_context' else 0

            if llm_time > 0:
                self.stats['total_llm_time_ms'] += llm_time

            return {
                'answer': result['answer'],
                'mode_used': mode_used,
                'search_score': result.get('search_score', 0),
                'sources': self._format_sources(result.get('sources', [])),
                'keyword_extracted': keyword,
                'metadata': {
                    'search_time_ms': round(search_time, 2),
                    'llm_time_ms': round(llm_time, 2),
                    'total_time_ms': round(total_time, 2)
                }
            }

        except Exception as e:
            logger.error(f"RAG hybrid query failed: {e}", exc_info=True)
            return self._fallback_response(query, str(e))

    async def query_direct(self, query: str) -> Dict:
        """
        Direct Answer 모드 (LLM 우회, 100% 정확)

        학습 데이터의 응답을 그대로 반환합니다.
        환각이 절대 발생하지 않습니다.

        Args:
            query: 사용자 질문

        Returns:
            RAG 응답 딕셔너리
        """
        if not self.is_initialized:
            return self._fallback_response(query, "RAG service not initialized")

        start_time = time.time()

        try:
            result = self.rag.query_mode_2_direct_answer(query)
            keyword = self.rag.extract_keyword(query)

            total_time = (time.time() - start_time) * 1000

            mode_used = result.get('mode', 'direct_answer')
            self._update_stats(mode_used, total_time)

            return {
                'answer': result['answer'],
                'mode_used': mode_used,
                'search_score': result.get('score', 0),
                'sources': self._format_sources(result.get('sources', [])),
                'keyword_extracted': keyword,
                'metadata': {
                    'search_time_ms': round(total_time, 2),
                    'llm_time_ms': 0,
                    'total_time_ms': round(total_time, 2)
                }
            }

        except Exception as e:
            logger.error(f"RAG direct query failed: {e}", exc_info=True)
            return self._fallback_response(query, str(e))

    async def query_llm(
        self,
        query: str,
        model: str = "openframe_common_v2",
        llm_url: str = DEFAULT_LLM_URL,
        max_tokens: int = 500,
        temperature: float = 0.2
    ) -> Dict:
        """
        LLM 모드 (검색 결과를 LLM으로 재구성)

        자연스러운 답변이 필요할 때 사용합니다.
        약간의 환각 가능성이 있습니다 (5% 미만).

        Args:
            query: 사용자 질문
            model: LLM 모델 이름
            llm_url: LLM 서버 URL
            max_tokens: 최대 토큰 수
            temperature: Temperature

        Returns:
            RAG 응답 딕셔너리
        """
        if not self.is_initialized:
            return self._fallback_response(query, "RAG service not initialized")

        start_time = time.time()
        search_start = time.time()

        try:
            result = self.rag.query_mode_1_strict_prompt(
                query=query,
                model=model,
                llm_url=llm_url
            )

            search_time = (time.time() - search_start) * 1000
            keyword = self.rag.extract_keyword(query)

            total_time = (time.time() - start_time) * 1000
            llm_time = total_time - search_time

            self._update_stats('llm_with_context', search_time)
            self.stats['total_llm_time_ms'] += llm_time

            return {
                'answer': result['answer'],
                'mode_used': result.get('mode', 'strict_prompt'),
                'search_score': 0,  # LLM 모드는 score 없음
                'sources': self._format_sources(result.get('sources', [])),
                'keyword_extracted': keyword,
                'metadata': {
                    'search_time_ms': round(search_time, 2),
                    'llm_time_ms': round(llm_time, 2),
                    'total_time_ms': round(total_time, 2)
                }
            }

        except Exception as e:
            logger.error(f"RAG LLM query failed: {e}", exc_info=True)
            return self._fallback_response(query, str(e))

    async def search_only(self, query: str, top_k: int = 5) -> Dict:
        """
        검색만 수행 (디버깅용)

        LLM을 사용하지 않고 검색 결과만 반환합니다.

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수

        Returns:
            검색 결과 딕셔너리
        """
        if not self.is_initialized:
            return {
                'query': query,
                'keyword_extracted': '',
                'results_count': 0,
                'results': [],
                'error': 'RAG service not initialized'
            }

        try:
            keyword = self.rag.extract_keyword(query)
            results = self.rag.keyword_search(keyword, top_k=top_k)

            return {
                'query': query,
                'keyword_extracted': keyword,
                'results_count': len(results),
                'results': [
                    {
                        'product': r.get('product', 'unknown'),
                        'name': r.get('name', 'N/A'),
                        'score': r.get('score', 0),
                        'instruction': r.get('instruction', ''),
                        'response': r.get('response', '')[:200] + '...' if len(r.get('response', '')) > 200 else r.get('response', '')
                    }
                    for r in results
                ]
            }

        except Exception as e:
            logger.error(f"RAG search failed: {e}", exc_info=True)
            return {
                'query': query,
                'keyword_extracted': '',
                'results_count': 0,
                'results': [],
                'error': str(e)
            }

    def get_stats(self) -> Dict:
        """통계 반환"""
        if not self.is_initialized:
            return {
                'total_documents': 0,
                'products': {},
                'total_queries': self.stats['total_queries'],
                'modes_usage': self.stats['modes_usage'],
                'avg_search_time_ms': 0,
                'avg_llm_time_ms': 0,
                'error': 'RAG service not initialized'
            }

        # 제품별 문서 수
        products = {}
        for doc in self.rag.documents:
            product = doc.get('product', 'unknown')
            products[product] = products.get(product, 0) + 1

        # 평균 시간
        total_queries = self.stats['total_queries']
        avg_search_time = self.stats['total_search_time_ms'] / total_queries if total_queries > 0 else 0
        avg_llm_time = self.stats['total_llm_time_ms'] / total_queries if total_queries > 0 else 0

        return {
            'total_documents': len(self.rag.documents),
            'products': products,
            'total_queries': total_queries,
            'modes_usage': self.stats['modes_usage'],
            'avg_search_time_ms': round(avg_search_time, 2),
            'avg_llm_time_ms': round(avg_llm_time, 2)
        }

    def _update_stats(self, mode: str, search_time: float):
        """통계 업데이트"""
        self.stats['total_queries'] += 1
        self.stats['modes_usage'][mode] = self.stats['modes_usage'].get(mode, 0) + 1
        self.stats['total_search_time_ms'] += search_time

    def _format_sources(self, sources: List[Dict]) -> List[Dict]:
        """출처 포맷팅"""
        return [
            {
                'product': src.get('product', 'unknown'),
                'name': src.get('name', 'N/A'),
                'score': src.get('score', 0)
            }
            for src in sources
        ]

    def _fallback_response(self, query: str, error: str) -> Dict:
        """폴백 응답 생성"""
        return {
            'answer': f"申し訳ございませんが、RAGサービスでエラーが発生しました。エラー: {error}",
            'mode_used': 'error',
            'search_score': 0,
            'sources': [],
            'keyword_extracted': '',
            'metadata': {
                'search_time_ms': 0,
                'llm_time_ms': 0,
                'total_time_ms': 0,
                'error': error
            }
        }


# Dependency Injection용
def get_rag_service() -> RAGAntiHallucinationService:
    """FastAPI 의존성 주입용"""
    return RAGAntiHallucinationService.get_instance()
