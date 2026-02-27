"""
RelevanceGraderService: 검색 결과 관련성 평가

Implements ISREL-style grading:
- RELEVANT: 질문에 직접 답변 가능
- PARTIAL: 관련 있지만 완전한 답변 아님
- IRRELEVANT: 관련 없음

Grading Criteria:
1. Exact Match Check: 정확한 용어/파일명 포함 여부
2. Intent Match Check: 질문 의도와 결과 내용 일치
3. Semantic Match Check: 의미적 관련성

Created as part of PDCA: rag-accuracy-improvement
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from ..models.rag_accuracy import (
    QueryAnalysis,
    QueryIntent,
    ExactMatchType,
    RelevanceGrade,
    GradedResult,
    GradingResult,
)

logger = logging.getLogger(__name__)


class RelevanceGraderService:
    """검색 결과 관련성 평가 서비스"""

    # Intent-to-content mapping (의도별 컨텐츠 패턴)
    INTENT_CONTENT_PATTERNS = {
        QueryIntent.STRUCTURE: [
            r'構造|구조|structure|architecture|アーキテクチャ',
            r'構成|구성|composition|component',
            r'概要|개요|overview|概説',
            r'仕組み|원리|mechanism|how\s+it\s+works',
        ],
        QueryIntent.COMMAND: [
            r'コマンド|명령|command',
            r'オプション|옵션|option|parameter',
            r'構文|구문|syntax',
            r'実行|실행|execute|run',
            r'使用法|사용법|usage',
        ],
        QueryIntent.ERROR: [
            r'エラー|에러|error|exception|例外',
            r'原因|원인|cause|reason',
            r'対処|대처|solution|fix|解決',
            r'障害|장애|failure|trouble',
        ],
        QueryIntent.HOWTO: [
            r'方法|방법|how|procedure',
            r'手順|순서|step|steps',
            r'設定|설정|configure|setup|configuration',
            r'やり方|하는\s*법|way\s+to',
        ],
        QueryIntent.DEFINITION: [
            r'とは|란|is\s+a|definition',
            r'概念|개념|concept',
            r'説明|설명|explanation|describe',
        ],
    }

    # Config file strict matching (설정 파일 엄격 매칭)
    STRICT_CONFIG_FILES = {
        'osc.conf', 'tjes.conf', 'tacf.conf', 'ds.conf',
        'oframe.conf', 'osi.conf', 'hidb.conf', 'ndb.conf',
    }

    def grade_results(
        self,
        query_analysis: QueryAnalysis,
        search_results: List[Dict[str, Any]],
    ) -> GradingResult:
        """
        검색 결과 그레이딩

        Args:
            query_analysis: 쿼리 분석 결과
            search_results: 검색 결과 리스트

        Returns:
            GradingResult: 그레이딩 결과
        """
        logger.info(
            f"[RelevanceGrader] Grading {len(search_results)} results for: "
            f"{query_analysis.original_query[:50]}..."
        )

        graded_results: List[GradedResult] = []

        for result in search_results:
            graded = self._grade_single_result(query_analysis, result)
            graded_results.append(graded)

        # Count grades
        relevant_count = sum(
            1 for r in graded_results if r.grade == RelevanceGrade.RELEVANT
        )
        partial_count = sum(
            1 for r in graded_results if r.grade == RelevanceGrade.PARTIAL
        )
        irrelevant_count = sum(
            1 for r in graded_results if r.grade == RelevanceGrade.IRRELEVANT
        )

        # Determine if rewrite is needed (no relevant or partial results)
        needs_rewrite = relevant_count == 0 and partial_count == 0

        grading_result = GradingResult(
            query_analysis=query_analysis,
            graded_results=graded_results,
            relevant_count=relevant_count,
            partial_count=partial_count,
            irrelevant_count=irrelevant_count,
            needs_rewrite=needs_rewrite,
        )

        logger.info(
            f"[RelevanceGrader] Results: relevant={relevant_count}, "
            f"partial={partial_count}, irrelevant={irrelevant_count}, "
            f"needs_rewrite={needs_rewrite}"
        )

        return grading_result

    def _grade_single_result(
        self,
        query_analysis: QueryAnalysis,
        result: Dict[str, Any],
    ) -> GradedResult:
        """단일 결과 그레이딩"""
        # Extract content from various possible keys
        content = (
            result.get("content", "") or
            result.get("text", "") or
            result.get("chunk_text", "") or
            ""
        )

        doc_name = (
            result.get("doc_name", "") or
            result.get("document_name", "") or
            result.get("title", "") or
            "Unknown"
        )

        original_score = float(
            result.get("score", 0.0) or
            result.get("similarity", 0.0) or
            result.get("combined_score", 0.0) or
            0.0
        )

        # Step 1: Exact match check
        exact_match_found = self._check_exact_match(query_analysis, content, doc_name)

        # Step 2: Intent match check
        intent_match = self._check_intent_match(query_analysis, content)

        # Step 3: Determine grade
        grade, reason = self._determine_grade(
            exact_match_found=exact_match_found,
            intent_match=intent_match,
            query_analysis=query_analysis,
            content=content,
        )

        return GradedResult(
            content=content[:500] if content else "",  # Truncate for response size
            doc_name=doc_name,
            chunk_id=result.get("chunk_id"),
            original_score=original_score,
            grade=grade,
            grade_reason=reason,
            exact_match_found=exact_match_found,
            intent_match=intent_match,
        )

    def _check_exact_match(
        self,
        query_analysis: QueryAnalysis,
        content: str,
        doc_name: str,
    ) -> bool:
        """정확 매칭 확인"""
        if query_analysis.exact_match_type == ExactMatchType.NONE:
            return True  # No exact match required

        exact_value = query_analysis.exact_match_value
        if not exact_value:
            return True

        # Combine content and doc_name for search
        search_text = f"{content} {doc_name}".lower()
        exact_value_lower = exact_value.lower()

        # Config file strict matching
        if query_analysis.exact_match_type == ExactMatchType.CONFIG_FILE:
            # Must contain the EXACT config file name
            # Use a pattern that matches the config file followed by boundary or non-alphanumeric
            import re
            # Match config file name with possible extensions or boundaries
            pattern = re.escape(exact_value_lower) + r'(?:\s|$|[^a-z0-9])'
            return bool(re.search(pattern, search_text + " "))

        # Command name matching (more lenient)
        if query_analysis.exact_match_type == ExactMatchType.COMMAND_NAME:
            return exact_value_lower in search_text

        # Error code matching
        if query_analysis.exact_match_type == ExactMatchType.ERROR_CODE:
            # Normalize error codes (remove spaces)
            normalized_value = exact_value.replace(" ", "").lower()
            normalized_text = content.replace(" ", "").lower()
            return normalized_value in normalized_text

        return exact_value_lower in search_text

    def _check_intent_match(
        self,
        query_analysis: QueryAnalysis,
        content: str,
    ) -> bool:
        """의도 매칭 확인"""
        primary_intent = query_analysis.primary_intent

        if primary_intent == QueryIntent.GENERAL:
            return True  # General intent matches anything

        patterns = self.INTENT_CONTENT_PATTERNS.get(primary_intent, [])
        if not patterns:
            return True  # No specific patterns, assume match

        content_lower = content.lower()

        for pattern in patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True

        return False

    def _determine_grade(
        self,
        exact_match_found: bool,
        intent_match: bool,
        query_analysis: QueryAnalysis,
        content: str,
    ) -> Tuple[RelevanceGrade, str]:
        """등급 결정"""

        # Config file STRICT matching - most critical
        if query_analysis.exact_match_type == ExactMatchType.CONFIG_FILE:
            exact_value = query_analysis.exact_match_value
            if exact_value and exact_value.lower() in self.STRICT_CONFIG_FILES:
                if not exact_match_found:
                    # Check if a DIFFERENT config file is mentioned
                    content_lower = content.lower()
                    other_configs = [
                        c for c in self.STRICT_CONFIG_FILES
                        if c != exact_value.lower() and c in content_lower
                    ]
                    if other_configs:
                        return (
                            RelevanceGrade.IRRELEVANT,
                            f"Wrong config file: found {other_configs[0]}, "
                            f"expected {exact_value}"
                        )
                    return (
                        RelevanceGrade.IRRELEVANT,
                        f"Config file '{exact_value}' not found in content"
                    )

        # Standard grading logic
        if exact_match_found and intent_match:
            return RelevanceGrade.RELEVANT, "Exact match and intent match"

        if exact_match_found and not intent_match:
            return RelevanceGrade.PARTIAL, "Exact match but intent mismatch"

        if not exact_match_found and intent_match:
            return RelevanceGrade.PARTIAL, "Intent match but no exact match"

        return RelevanceGrade.IRRELEVANT, "No exact match and no intent match"

    def filter_relevant_results(
        self,
        grading_result: GradingResult,
        search_results: List[Dict[str, Any]],
        include_partial: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        관련성 높은 결과만 필터링

        Args:
            grading_result: 그레이딩 결과
            search_results: 원본 검색 결과
            include_partial: PARTIAL 등급 포함 여부

        Returns:
            필터링된 검색 결과
        """
        allowed_grades = {RelevanceGrade.RELEVANT}
        if include_partial:
            allowed_grades.add(RelevanceGrade.PARTIAL)

        filtered = []
        for result, graded in zip(search_results, grading_result.graded_results):
            if graded.grade in allowed_grades:
                # Add grading metadata to result
                result_with_grade = result.copy()
                result_with_grade["relevance_grade"] = graded.grade.value
                result_with_grade["grade_reason"] = graded.grade_reason
                filtered.append(result_with_grade)

        return filtered


# =============================================================================
# Singleton Pattern
# =============================================================================

_relevance_grader_service: Optional[RelevanceGraderService] = None


def get_relevance_grader_service() -> RelevanceGraderService:
    """RelevanceGraderService 싱글톤 반환"""
    global _relevance_grader_service
    if _relevance_grader_service is None:
        _relevance_grader_service = RelevanceGraderService()
    return _relevance_grader_service
