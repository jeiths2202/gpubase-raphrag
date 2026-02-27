"""
QueryRewriterService: 쿼리 재작성

검색 결과가 없거나 관련 없을 때 쿼리를 개선합니다.

Strategies:
1. Intent-based expansion: 의도에 맞는 키워드 추가
2. Simplification: 복잡한 쿼리를 단순화
3. Synonym expansion: 동의어 추가

Created as part of PDCA: rag-accuracy-improvement
"""

import logging
from typing import Optional, List

from ..models.rag_accuracy import QueryAnalysis, QueryIntent

logger = logging.getLogger(__name__)


class QueryRewriterService:
    """쿼리 재작성 서비스"""

    # Intent-specific expansion templates (by language)
    EXPANSION_TEMPLATES = {
        QueryIntent.STRUCTURE: {
            "ja": ["{core} 概要", "{core} アーキテクチャ", "{core} 構成"],
            "ko": ["{core} 개요", "{core} 구조", "{core} 아키텍처"],
            "en": ["{core} overview", "{core} architecture", "{core} structure"],
        },
        QueryIntent.COMMAND: {
            "ja": ["{core} コマンド", "{core} 使い方", "{core} オプション"],
            "ko": ["{core} 명령어", "{core} 사용법", "{core} 옵션"],
            "en": ["{core} command", "{core} usage", "{core} options"],
        },
        QueryIntent.ERROR: {
            "ja": ["{core} 原因", "{core} 対処", "{core} 解決方法"],
            "ko": ["{core} 원인", "{core} 해결", "{core} 대처"],
            "en": ["{core} cause", "{core} solution", "{core} fix"],
        },
        QueryIntent.HOWTO: {
            "ja": ["{core} 方法", "{core} 手順", "{core} 設定方法"],
            "ko": ["{core} 방법", "{core} 순서", "{core} 설정"],
            "en": ["{core} how to", "{core} steps", "{core} configure"],
        },
        QueryIntent.DEFINITION: {
            "ja": ["{core}とは", "{core} 説明", "{core} 概念"],
            "ko": ["{core}란", "{core} 설명", "{core} 정의"],
            "en": ["what is {core}", "{core} definition", "{core} explained"],
        },
    }

    # Fallback simplification patterns (strip common suffixes)
    SIMPLIFICATION_PATTERNS = {
        "ja": [
            r'について.*$', r'に関して.*$', r'の設定.*$',
            r'を教えて.*$', r'を説明.*$',
        ],
        "ko": [
            r'에\s*대해.*$', r'에\s*관해.*$', r'설정.*$',
            r'알려.*$', r'설명.*$',
        ],
        "en": [
            r'\s+about\s+.*$', r'\s+regarding\s+.*$',
            r'\s+please\s*$', r'\s+explain\s*$',
        ],
    }

    def rewrite(
        self,
        query_analysis: QueryAnalysis,
        attempt: int = 1,
    ) -> str:
        """
        쿼리 재작성

        Args:
            query_analysis: 원본 쿼리 분석 결과
            attempt: 재시도 횟수 (1 또는 2)

        Returns:
            재작성된 쿼리
        """
        original = query_analysis.original_query
        intent = query_analysis.primary_intent
        language = query_analysis.language

        logger.info(
            f"[QueryRewriter] Rewriting (attempt {attempt}): "
            f"'{original[:50]}...' intent={intent.value}, lang={language}"
        )

        # Get core term for expansion
        core_term = self._get_core_term(query_analysis)

        # Strategy 1: Intent-based expansion
        if attempt == 1:
            rewritten = self._expand_by_intent(core_term, intent, language)
            if rewritten:
                logger.info(f"[QueryRewriter] Expanded: '{rewritten}'")
                return rewritten

        # Strategy 2: Simplification (attempt 2)
        if attempt == 2:
            rewritten = self._simplify_query(original, query_analysis.keywords, language)
            if rewritten and rewritten != original:
                logger.info(f"[QueryRewriter] Simplified: '{rewritten}'")
                return rewritten

        # Fallback: use keywords only
        if query_analysis.keywords:
            rewritten = " ".join(query_analysis.keywords[:3])
            logger.info(f"[QueryRewriter] Fallback to keywords: '{rewritten}'")
            return rewritten

        # Last resort: return original
        logger.warning("[QueryRewriter] Could not rewrite, returning original")
        return original

    def _get_core_term(self, query_analysis: QueryAnalysis) -> str:
        """쿼리의 핵심 용어 추출"""
        # Prefer exact match value (config file, command name, error code)
        if query_analysis.exact_match_value:
            return query_analysis.exact_match_value

        # Use first meaningful keyword
        if query_analysis.keywords:
            for kw in query_analysis.keywords:
                # Skip common stopwords
                if len(kw) >= 2:
                    return kw

        # Fallback to first part of original query
        parts = query_analysis.original_query.split()
        if parts:
            return parts[0]

        return query_analysis.original_query

    def _expand_by_intent(
        self,
        core_term: str,
        intent: QueryIntent,
        language: str,
    ) -> Optional[str]:
        """의도에 맞게 쿼리 확장"""
        templates_by_lang = self.EXPANSION_TEMPLATES.get(intent, {})
        templates = templates_by_lang.get(language, templates_by_lang.get("en", []))

        if not templates:
            return None

        # Use first template
        template = templates[0]
        return template.format(core=core_term)

    def _simplify_query(
        self,
        query: str,
        keywords: List[str],
        language: str,
    ) -> str:
        """쿼리 단순화"""
        import re

        simplified = query

        # Apply simplification patterns for language
        patterns = self.SIMPLIFICATION_PATTERNS.get(language, [])
        for pattern in patterns:
            simplified = re.sub(pattern, '', simplified, flags=re.IGNORECASE)

        simplified = simplified.strip()

        # If simplified is too short, use keywords
        if len(simplified) < 3 and keywords:
            simplified = " ".join(keywords[:2])

        return simplified

    def generate_alternative_queries(
        self,
        query_analysis: QueryAnalysis,
        count: int = 3,
    ) -> List[str]:
        """
        대안 쿼리 생성 (여러 개)

        Args:
            query_analysis: 원본 쿼리 분석 결과
            count: 생성할 대안 수

        Returns:
            대안 쿼리 리스트
        """
        alternatives: List[str] = []
        core_term = self._get_core_term(query_analysis)
        intent = query_analysis.primary_intent
        language = query_analysis.language

        # Get all templates for intent
        templates_by_lang = self.EXPANSION_TEMPLATES.get(intent, {})
        templates = templates_by_lang.get(language, templates_by_lang.get("en", []))

        for template in templates[:count]:
            alt = template.format(core=core_term)
            if alt not in alternatives:
                alternatives.append(alt)

        # Add simplified version
        if len(alternatives) < count:
            simplified = self._simplify_query(
                query_analysis.original_query,
                query_analysis.keywords,
                language,
            )
            if simplified not in alternatives:
                alternatives.append(simplified)

        return alternatives[:count]


# =============================================================================
# Singleton Pattern
# =============================================================================

_query_rewriter_service: Optional[QueryRewriterService] = None


def get_query_rewriter_service() -> QueryRewriterService:
    """QueryRewriterService 싱글톤 반환"""
    global _query_rewriter_service
    if _query_rewriter_service is None:
        _query_rewriter_service = QueryRewriterService()
    return _query_rewriter_service
