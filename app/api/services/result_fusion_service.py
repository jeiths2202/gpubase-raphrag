"""
Result Fusion Service for Semantic Search

Reciprocal Rank Fusion (RRF) 기반 결과 통합 서비스
- 다중 검색 결과 통합
- 중복 제거
- 최종 랭킹 계산
"""

import logging
from typing import List, Dict, Optional
from collections import defaultdict

from app.api.models.query_analysis import RetrievalResult

logger = logging.getLogger(__name__)


class ResultFusionService:
    """Reciprocal Rank Fusion 기반 결과 통합 서비스"""

    def __init__(
        self,
        k: int = 60,
        default_weights: Dict[str, float] = None
    ):
        """
        Args:
            k: RRF 상수 (기본 60, 학술 논문에서 권장)
            default_weights: 소스별 기본 가중치
        """
        self.k = k
        self.default_weights = default_weights or {
            "entity": 1.2,    # Entity 직접 매칭 - 최고 우선순위
            "vector": 1.0,    # Vector 유사도 검색
            "keyword": 0.8,   # BM25 키워드 검색
        }

    def fuse(
        self,
        results_by_source: Dict[str, List[RetrievalResult]],
        weights: Dict[str, float] = None,
        top_k: int = None
    ) -> List[RetrievalResult]:
        """
        RRF 알고리즘으로 여러 검색 결과 통합

        RRF Score = Σ (weight_i / (k + rank_i))

        Args:
            results_by_source: 소스별 검색 결과 {"vector": [...], "keyword": [...], "entity": [...]}
            weights: 소스별 가중치 (None이면 default_weights 사용)
            top_k: 반환할 최대 결과 수

        Returns:
            RRF 점수로 정렬된 통합 결과
        """
        weights = weights or self.default_weights

        # 1. 문서별 RRF 점수 계산
        doc_scores: Dict[str, float] = defaultdict(float)
        doc_data: Dict[str, RetrievalResult] = {}
        doc_original_scores: Dict[str, Dict[str, float]] = defaultdict(dict)

        for source, results in results_by_source.items():
            weight = weights.get(source, 1.0)

            for rank, result in enumerate(results, start=1):
                doc_id = result.doc_id

                # RRF 점수 계산: weight / (k + rank)
                rrf_contribution = weight / (self.k + rank)
                doc_scores[doc_id] += rrf_contribution

                # 원본 점수 저장
                doc_original_scores[doc_id][source] = result.score

                # 첫 번째 등장 결과 저장 (메타데이터용)
                if doc_id not in doc_data:
                    doc_data[doc_id] = result

        # 2. RRF 점수로 정렬
        sorted_doc_ids = sorted(
            doc_scores.keys(),
            key=lambda x: doc_scores[x],
            reverse=True
        )

        # 3. 최종 결과 생성
        fused_results = []
        for doc_id in sorted_doc_ids:
            result = doc_data[doc_id]
            # RRF 점수로 업데이트
            result.score = doc_scores[doc_id]
            result.original_scores = dict(doc_original_scores[doc_id])

            # 소스 정보 업데이트 (여러 소스에서 등장했으면 표시)
            sources_appeared = [s for s, rs in results_by_source.items()
                              if any(r.doc_id == doc_id for r in rs)]
            if len(sources_appeared) > 1:
                result.metadata["fusion_sources"] = sources_appeared

            fused_results.append(result)

        # 4. Top-K 반환
        if top_k:
            fused_results = fused_results[:top_k]

        logger.debug(f"Fused {sum(len(rs) for rs in results_by_source.values())} "
                    f"results into {len(fused_results)} unique documents")

        return fused_results

    def fuse_lists(
        self,
        result_lists: List[List[RetrievalResult]],
        weights: List[float] = None,
        top_k: int = None
    ) -> List[RetrievalResult]:
        """
        리스트 형태의 결과 통합 (소스명 없이)

        Args:
            result_lists: 검색 결과 리스트들
            weights: 리스트별 가중치
            top_k: 반환할 최대 결과 수
        """
        if weights is None:
            weights = [1.0] * len(result_lists)

        # 소스명을 인덱스로 생성
        results_by_source = {}
        weight_map = {}

        for i, (results, weight) in enumerate(zip(result_lists, weights)):
            source_name = f"source_{i}"
            results_by_source[source_name] = results
            weight_map[source_name] = weight

        return self.fuse(results_by_source, weight_map, top_k)

    def deduplicate(
        self,
        results: List[RetrievalResult],
        similarity_threshold: float = 0.9
    ) -> List[RetrievalResult]:
        """
        중복 문서 제거 (내용 기반)

        Args:
            results: 검색 결과 리스트
            similarity_threshold: 유사도 임계값 (이 이상이면 중복으로 간주)

        Returns:
            중복 제거된 결과
        """
        if not results:
            return results

        unique_results = []
        seen_content_hashes = set()

        for result in results:
            # 내용의 앞부분 해시
            content_hash = self._content_hash(result.content)

            if content_hash not in seen_content_hashes:
                seen_content_hashes.add(content_hash)
                unique_results.append(result)

        logger.debug(f"Deduplicated {len(results)} → {len(unique_results)} results")
        return unique_results

    def _content_hash(self, content: str, prefix_length: int = 200) -> int:
        """내용 해시 생성 (앞부분만)"""
        # 공백 정규화 후 해시
        normalized = " ".join(content[:prefix_length].split())
        return hash(normalized)

    def rerank_by_query_match(
        self,
        results: List[RetrievalResult],
        query_keywords: List[str],
        boost_factor: float = 0.1
    ) -> List[RetrievalResult]:
        """
        쿼리 키워드 매칭으로 재랭킹

        Args:
            results: 검색 결과
            query_keywords: 쿼리에서 추출된 키워드
            boost_factor: 키워드 매칭당 점수 부스트

        Returns:
            재랭킹된 결과
        """
        if not query_keywords:
            return results

        query_keywords_lower = [kw.lower() for kw in query_keywords]

        for result in results:
            content_lower = result.content.lower()
            title_lower = (result.document_title or "").lower()

            # 키워드 매칭 수 계산
            matches = sum(
                1 for kw in query_keywords_lower
                if kw in content_lower or kw in title_lower
            )

            # 점수 부스트
            if matches > 0:
                result.score += matches * boost_factor
                result.metadata["keyword_matches"] = matches

        # 재정렬
        results.sort(key=lambda r: r.score, reverse=True)
        return results


# 싱글톤 인스턴스
_service_instance: Optional[ResultFusionService] = None


def get_result_fusion_service(k: int = 60) -> ResultFusionService:
    """ResultFusionService 싱글톤 반환"""
    global _service_instance
    if _service_instance is None:
        _service_instance = ResultFusionService(k=k)
    return _service_instance
