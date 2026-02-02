"""
Hybrid Score Calculator

모든 스코어 계산 로직의 중앙 집중화.
하드코딩 값 없이 오직 HybridScoreConfig 기반으로 동작.

이 서비스는 다음 파일들의 하드코딩을 대체합니다:
- app/src/hybrid_rag.py
- app/api/services/rag_service.py
- app/api/ims_crawler/infrastructure/services/hybrid_search_service.py
"""

from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
import logging

from ..models.scoring_config import HybridScoreConfig

logger = logging.getLogger(__name__)


class SourceType(str, Enum):
    """검색 결과 소스 타입"""
    ERROR_CODE = "error_code"
    TOPIC_DENSITY = "topic_density"
    VECTOR = "vector"
    GRAPH = "graph"
    BM25 = "bm25"
    GLOSSARY = "glossary"
    VERIFIED = "verified"
    SESSION = "session"
    EXTERNAL = "external"


class QueryType(str, Enum):
    """쿼리 복잡도 타입"""
    SIMPLE = "simple"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"
    DEEP_ANALYSIS = "deep_analysis"


class SearchType(str, Enum):
    """검색 타입 (배수 결정용)"""
    NORMAL = "normal"
    TOPIC = "topic"
    DEEP = "deep"
    COMPREHENSIVE = "comprehensive"


@dataclass
class ScoredResult:
    """스코어가 계산된 검색 결과"""
    chunk_id: str
    content: str
    score: float
    combined_score: float
    source: SourceType
    metadata: Dict[str, Any] = field(default_factory=dict)
    boost_applied: List[str] = field(default_factory=list)


class HybridScoreCalculator:
    """
    Hybrid Score 중앙 계산 엔진.

    모든 스코어링 로직이 이 클래스를 통해 수행됩니다.
    하드코딩된 값은 없으며, 모든 파라미터는 config에서 로드됩니다.

    Usage:
        config = HybridScoreConfig()
        calculator = HybridScoreCalculator(config)

        # Topic density 스코어 계산
        score = calculator.calculate_topic_score(0.5)  # 0.4 + (0.5 * 0.2) = 0.5

        # 키워드 부스트 적용
        boosted = calculator.apply_keyword_boost(0.8, keyword_matches=3)
    """

    def __init__(self, config: HybridScoreConfig):
        """
        Args:
            config: HybridScoreConfig 인스턴스
        """
        self.config = config
        logger.debug(f"HybridScoreCalculator initialized with config: {config.model_dump()}")

    def update_config(self, config: HybridScoreConfig) -> None:
        """
        런타임 설정 업데이트.

        Admin API를 통한 설정 변경 시 호출됩니다.
        """
        self.config = config
        logger.info("HybridScoreCalculator config updated")

    # ═══════════════════════════════════════════════════════════════
    # Score Calculation Methods
    # ═══════════════════════════════════════════════════════════════

    def calculate_topic_score(self, topic_density: float) -> float:
        """
        Topic density 스코어 계산.

        Formula: base + (density * weight)
        Range: [base, base + weight] = [0.4, 0.6] (기본값)

        Args:
            topic_density: 0.0 ~ 1.0 사이의 토픽 밀도 값

        Returns:
            계산된 스코어 (예: 0.4 ~ 0.6)

        기존 하드코딩 (hybrid_rag.py:1075):
            result["combined_score"] = 0.4 + (topic_score * 0.2)
        """
        return (
            self.config.topic_density_base +
            (topic_density * self.config.topic_density_weight)
        )

    def calculate_vector_score(self, raw_score: float) -> float:
        """
        Vector search 스코어 계산.

        Formula: raw_score * vector_weight

        Args:
            raw_score: Vector search에서 반환된 원본 스코어

        Returns:
            가중치가 적용된 스코어

        기존 하드코딩 (hybrid_rag.py:1092):
            result["combined_score"] = result["score"] * self.vector_weight
        """
        return raw_score * self.config.vector_weight

    def calculate_graph_score(self, raw_score: float) -> float:
        """
        Graph search 스코어 계산.

        Formula: raw_score * graph_weight

        Args:
            raw_score: Graph search에서 반환된 원본 스코어

        Returns:
            가중치가 적용된 스코어

        기존 하드코딩 (hybrid_rag.py:1104):
            graph_weight = 1.0 - self.vector_weight
            result["combined_score"] = result.get("score", 0.5) * graph_weight
        """
        return raw_score * self.config.graph_weight

    def calculate_bm25_hybrid_score(
        self,
        bm25_score: float,
        semantic_score: float
    ) -> float:
        """
        BM25 + Semantic hybrid 스코어 계산.

        Formula: (bm25 * bm25_weight) + (semantic * semantic_weight)

        Args:
            bm25_score: BM25 정규화 스코어
            semantic_score: Semantic similarity 스코어

        Returns:
            하이브리드 스코어

        기존 하드코딩 (hybrid_search_service.py:140-143):
            hybrid_scores = (
                self.bm25_weight * bm25_scores_norm +
                self.semantic_weight * semantic_scores
            )
        """
        return (
            (bm25_score * self.config.bm25_weight) +
            (semantic_score * self.config.semantic_weight)
        )

    def normalize_bm25_scores(self, scores: List[float]) -> List[float]:
        """
        BM25 스코어 정규화 (0~1 범위).

        Formula: score / (max_score + epsilon)

        Args:
            scores: BM25 원본 스코어 리스트

        Returns:
            정규화된 스코어 리스트

        기존 하드코딩 (hybrid_search_service.py:133):
            bm25_scores_norm = bm25_scores / (bm25_scores.max() + 1e-8)
        """
        if not scores:
            return []
        max_score = max(scores)
        return [
            s / (max_score + self.config.normalization_epsilon)
            for s in scores
        ]

    def normalize_entity_match_count(self, match_count: int) -> float:
        """
        엔티티 매칭 수 정규화.

        Formula: min(1.0, match_count / divisor)

        Args:
            match_count: 매칭된 엔티티 수

        Returns:
            정규화된 스코어 (0.0 ~ 1.0)

        기존 하드코딩 (hybrid_rag.py:794):
            min(1.0, match_count / 5.0)
        """
        return min(
            1.0,
            match_count / self.config.entity_match_normalization_divisor
        )

    # ═══════════════════════════════════════════════════════════════
    # Boost Application Methods
    # ═══════════════════════════════════════════════════════════════

    def apply_source_boost(
        self,
        score: float,
        source_type: SourceType
    ) -> Tuple[float, Optional[str]]:
        """
        소스 타입별 부스트 적용.

        Args:
            score: 원본 스코어
            source_type: 소스 타입

        Returns:
            (boosted_score, boost_name or None)

        기존 하드코딩들:
        - hybrid_rag.py:1062: combined_score = 1.0 (error code)
        - hybrid_rag.py:527: score *= 1.1 (glossary)
        - hybrid_rag.py:604: score *= 1.5 (verified)
        - rag_service.py:493: score * 2.0 (session)
        - rag_service.py:559: score * 2.5 (external)
        """
        if source_type == SourceType.ERROR_CODE:
            return self.config.error_code_priority, "error_code_priority"

        if source_type == SourceType.GLOSSARY:
            return score * self.config.glossary_boost, "glossary_boost"

        if source_type == SourceType.VERIFIED:
            return score * self.config.verified_result_boost, "verified_boost"

        if source_type == SourceType.SESSION:
            boosted = min(score * self.config.session_document_weight, 1.0)
            return boosted, "session_weight"

        if source_type == SourceType.EXTERNAL:
            boosted = min(score * self.config.external_document_weight, 1.0)
            return boosted, "external_weight"

        return score, None

    def apply_overlap_boost(
        self,
        current_score: float,
        overlap_source: SourceType,
        overlap_raw_score: float = 0.0
    ) -> Tuple[float, str]:
        """
        여러 소스에서 발견된 경우 부스트 적용.

        Args:
            current_score: 현재 combined_score
            overlap_source: 중복 발견된 소스 타입
            overlap_raw_score: 중복 소스의 원본 스코어 (vector/graph용)

        Returns:
            (boosted_score, boost_name)

        기존 하드코딩들:
        - hybrid_rag.py:1082: m["combined_score"] += 0.2 (topic overlap)
        - hybrid_rag.py:1099: m["combined_score"] += result["score"] * 0.1 (vector overlap)
        - hybrid_rag.py:1115: m["combined_score"] += result.get("score", 0.5) * 0.1 (graph overlap)
        """
        if overlap_source == SourceType.TOPIC_DENSITY:
            return (
                current_score + self.config.topic_boost_increment,
                "topic_overlap"
            )

        if overlap_source == SourceType.VECTOR:
            increment = overlap_raw_score * self.config.vector_boost_increment
            return current_score + increment, "vector_overlap"

        if overlap_source == SourceType.GRAPH:
            increment = overlap_raw_score * self.config.graph_boost_increment
            return current_score + increment, "graph_overlap"

        return current_score, "none"

    def apply_keyword_boost(
        self,
        score: float,
        keyword_matches: int
    ) -> float:
        """
        키워드 매칭 부스트 적용.

        Formula: score * (1 + boost_per_keyword * match_count)

        Args:
            score: 현재 스코어
            keyword_matches: 매칭된 키워드 수

        Returns:
            부스트된 스코어

        기존 하드코딩 (hybrid_rag.py:1137):
            result["combined_score"] *= (1 + 0.1 * keyword_matches)
        """
        if keyword_matches <= 0:
            return score

        multiplier = 1 + (self.config.keyword_match_boost * keyword_matches)
        return score * multiplier

    # ═══════════════════════════════════════════════════════════════
    # Result Merging & Filtering
    # ═══════════════════════════════════════════════════════════════

    def merge_multi_source_results(
        self,
        error_results: List[Dict[str, Any]],
        topic_results: List[Dict[str, Any]],
        vector_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]]
    ) -> List[ScoredResult]:
        """
        다중 소스 결과 병합 및 스코어링.

        우선순위:
        1. Error code (highest)
        2. Topic density (boosted if overlaps)
        3. Vector (primary semantic)
        4. Graph (entity-based)

        Args:
            error_results: 에러 코드 검색 결과
            topic_results: Topic density 검색 결과
            vector_results: Vector 검색 결과
            graph_results: Graph 검색 결과

        Returns:
            병합된 ScoredResult 리스트
        """
        merged: List[ScoredResult] = []
        seen_chunks: set = set()

        # 1. Error code 결과 (최고 우선)
        for result in error_results:
            chunk_id = result.get("chunk_id")
            if chunk_id and chunk_id not in seen_chunks:
                merged.append(ScoredResult(
                    chunk_id=chunk_id,
                    content=result.get("content", ""),
                    score=result.get("score", 1.0),
                    combined_score=self.config.error_code_priority,
                    source=SourceType.ERROR_CODE,
                    metadata=result,
                    boost_applied=["error_code_priority"]
                ))
                seen_chunks.add(chunk_id)

        # 2. Topic density 결과
        for result in topic_results:
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue

            topic_density = result.get("topic_density", 0.5)

            if topic_density < self.config.topic_density_min_threshold:
                continue

            if chunk_id not in seen_chunks:
                combined = self.calculate_topic_score(topic_density)
                merged.append(ScoredResult(
                    chunk_id=chunk_id,
                    content=result.get("content", ""),
                    score=topic_density,
                    combined_score=combined,
                    source=SourceType.TOPIC_DENSITY,
                    metadata=result,
                    boost_applied=[]
                ))
                seen_chunks.add(chunk_id)
            else:
                # 기존 결과에 부스트 적용
                for m in merged:
                    if m.chunk_id == chunk_id:
                        new_score, boost_name = self.apply_overlap_boost(
                            m.combined_score,
                            SourceType.TOPIC_DENSITY
                        )
                        m.combined_score = new_score
                        m.boost_applied.append(boost_name)
                        break

        # 3. Vector 결과
        for result in vector_results:
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue

            raw_score = result.get("score", 0.5)

            if chunk_id not in seen_chunks:
                combined = self.calculate_vector_score(raw_score)
                merged.append(ScoredResult(
                    chunk_id=chunk_id,
                    content=result.get("content", ""),
                    score=raw_score,
                    combined_score=combined,
                    source=SourceType.VECTOR,
                    metadata=result,
                    boost_applied=[]
                ))
                seen_chunks.add(chunk_id)
            else:
                for m in merged:
                    if m.chunk_id == chunk_id:
                        new_score, boost_name = self.apply_overlap_boost(
                            m.combined_score,
                            SourceType.VECTOR,
                            raw_score
                        )
                        m.combined_score = new_score
                        m.boost_applied.append(boost_name)
                        break

        # 4. Graph 결과
        for result in graph_results:
            chunk_id = result.get("chunk_id")
            if not chunk_id:
                continue

            raw_score = result.get("score", 0.5)

            if chunk_id not in seen_chunks:
                combined = self.calculate_graph_score(raw_score)
                merged.append(ScoredResult(
                    chunk_id=chunk_id,
                    content=result.get("content", ""),
                    score=raw_score,
                    combined_score=combined,
                    source=SourceType.GRAPH,
                    metadata=result,
                    boost_applied=[]
                ))
                seen_chunks.add(chunk_id)
            else:
                for m in merged:
                    if m.chunk_id == chunk_id:
                        new_score, boost_name = self.apply_overlap_boost(
                            m.combined_score,
                            SourceType.GRAPH,
                            raw_score
                        )
                        m.combined_score = new_score
                        m.boost_applied.append(boost_name)
                        break

        return merged

    def filter_by_relevance(
        self,
        results: List[ScoredResult]
    ) -> List[ScoredResult]:
        """
        최소 관련성 스코어 필터링.

        Args:
            results: ScoredResult 리스트

        Returns:
            필터링된 리스트

        기존 하드코딩 (hybrid_rag.py:1157):
            MIN_RELEVANCE_SCORE = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.3"))
        """
        return [
            r for r in results
            if r.combined_score >= self.config.min_relevance_score
        ]

    def filter_dict_by_relevance(
        self,
        results: List[Dict[str, Any]],
        score_key: str = "combined_score"
    ) -> List[Dict[str, Any]]:
        """
        Dict 형식 결과의 최소 관련성 스코어 필터링.

        Args:
            results: Dict 리스트
            score_key: 스코어 필드 이름

        Returns:
            필터링된 리스트
        """
        return [
            r for r in results
            if r.get(score_key, r.get("score", 0)) >= self.config.min_relevance_score
        ]

    def sort_by_score(
        self,
        results: List[ScoredResult],
        descending: bool = True
    ) -> List[ScoredResult]:
        """스코어 기준 정렬"""
        return sorted(
            results,
            key=lambda x: x.combined_score,
            reverse=descending
        )

    # ═══════════════════════════════════════════════════════════════
    # Utility Methods
    # ═══════════════════════════════════════════════════════════════

    def get_result_limit(self, query_type: QueryType) -> int:
        """
        쿼리 타입별 결과 수 제한.

        Args:
            query_type: 쿼리 복잡도 타입

        Returns:
            결과 수 제한

        기존 하드코딩 (hybrid_rag.py:1170-1177):
            if is_deep_analysis: result_count = 20
            elif is_comprehensive: result_count = 10
            else: result_count = 5
        """
        limits = {
            QueryType.SIMPLE: self.config.simple_query_results,
            QueryType.STANDARD: self.config.standard_query_results,
            QueryType.COMPREHENSIVE: self.config.comprehensive_query_results,
            QueryType.DEEP_ANALYSIS: self.config.comprehensive_query_results,
        }
        return limits.get(query_type, self.config.standard_query_results)

    def get_search_multiplier(self, search_type: SearchType, base_k: int) -> int:
        """
        검색 타입별 결과 배수 계산.

        Args:
            search_type: 검색 타입
            base_k: 기본 k 값

        Returns:
            배수가 적용된 k 값

        기존 하드코딩들:
        - hybrid_rag.py:138: self.top_k * 4 (deep)
        - hybrid_rag.py:140: self.top_k * 2 (comprehensive)
        - hybrid_rag.py:226: k * 3 (topic)
        """
        multipliers = {
            SearchType.NORMAL: 1,
            SearchType.TOPIC: self.config.topic_search_multiplier,
            SearchType.COMPREHENSIVE: self.config.comprehensive_query_multiplier,
            SearchType.DEEP: self.config.deep_analysis_multiplier,
        }
        multiplier = multipliers.get(search_type, 1)
        return base_k * multiplier

    def get_min_entity_k(self, requested_k: int) -> int:
        """
        엔티티당 최소 k값 보장.

        Args:
            requested_k: 요청된 k 값

        Returns:
            최소값이 보장된 k

        기존 하드코딩 (hybrid_rag.py:314):
            max(k, 5)
        """
        return max(requested_k, self.config.min_entity_k)

    def is_above_topic_threshold(self, topic_density: float) -> bool:
        """
        Topic density가 최소 임계값 이상인지 확인.

        Args:
            topic_density: 토픽 밀도 값

        Returns:
            임계값 이상이면 True

        기존 하드코딩 (hybrid_rag.py:1640):
            MIN_TOPIC_DENSITY = 0.15
        """
        return topic_density >= self.config.topic_density_min_threshold

    def get_config_summary(self) -> Dict[str, Any]:
        """설정 요약 반환 (디버깅용)"""
        return {
            "weights": {
                "vector": self.config.vector_weight,
                "graph": self.config.graph_weight,
                "bm25": self.config.bm25_weight,
                "semantic": self.config.semantic_weight,
            },
            "topic_formula": f"{self.config.topic_density_base} + (density * {self.config.topic_density_weight})",
            "boosts": {
                "error_code": self.config.error_code_priority,
                "glossary": self.config.glossary_boost,
                "verified": self.config.verified_result_boost,
                "keyword_per_match": self.config.keyword_match_boost,
            },
            "overlap_increments": {
                "topic": self.config.topic_boost_increment,
                "vector": self.config.vector_boost_increment,
                "graph": self.config.graph_boost_increment,
            },
            "limits": {
                "simple": self.config.simple_query_results,
                "standard": self.config.standard_query_results,
                "comprehensive": self.config.comprehensive_query_results,
            },
            "min_relevance": self.config.min_relevance_score,
        }


# Singleton instance holder
_calculator_instance: Optional[HybridScoreCalculator] = None


def get_hybrid_score_calculator(config: Optional[HybridScoreConfig] = None) -> HybridScoreCalculator:
    """
    HybridScoreCalculator 싱글톤 인스턴스 획득.

    Args:
        config: 설정 (첫 호출 시 필수, 이후 선택)

    Returns:
        HybridScoreCalculator 인스턴스
    """
    global _calculator_instance

    if _calculator_instance is None:
        if config is None:
            config = HybridScoreConfig()
        _calculator_instance = HybridScoreCalculator(config)

    elif config is not None:
        _calculator_instance.update_config(config)

    return _calculator_instance


def reset_calculator() -> None:
    """싱글톤 인스턴스 리셋 (테스트용)"""
    global _calculator_instance
    _calculator_instance = None
