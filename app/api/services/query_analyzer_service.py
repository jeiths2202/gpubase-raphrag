"""
QueryAnalyzerService: 쿼리 분석 및 메타데이터 추출

Responsibilities:
1. 쿼리 의도 감지 (Intent Detection)
2. 정확 매칭 패턴 감지 (Exact Match Detection)
3. 키워드 추출 (Keyword Extraction)
4. 언어 감지 (Language Detection)

Created as part of PDCA: rag-accuracy-improvement
"""

import re
import logging
from typing import Optional, Set, List, Tuple

from ..models.rag_accuracy import (
    QueryIntent,
    ExactMatchType,
    QueryAnalysis,
)

logger = logging.getLogger(__name__)


class QueryAnalyzerService:
    """쿼리 분석 서비스"""

    # Intent detection patterns (다국어 지원)
    INTENT_PATTERNS = {
        QueryIntent.DEFINITION: [
            r'とは[?？]?$', r'란[?？]?$', r'이란[?？]?$',
            r'what\s+is', r'무엇', r'정의',
            r'について', r'에\s*대해',
        ],
        QueryIntent.ERROR: [
            r'에러|error|오류|エラー|障害',
            r'ABEND\s*S\d+', r'-\d{4,5}',
            r'失敗|fail|実行できない|안됨|안\s*돼',
        ],
        QueryIntent.COMMAND: [
            r'명령|command|コマンド',
            r'mgr$',  # tjesmgr, oscmgr etc.
            r'실행|execute|実行',
            r'옵션|option|オプション',
        ],
        QueryIntent.STRUCTURE: [
            r'構造|구조|structure|architecture|아키텍처',
            r'構成|구성|configuration|composition',
            r'概要|개요|overview',
            r'仕組み|원리|mechanism',
        ],
        QueryIntent.HOWTO: [
            r'方法|방법|how\s+to|使い方|사용법',
            r'設定|설정|configure|setup',
            r'手順|순서|procedure|step',
            r'やり方|하는\s*법',
        ],
        QueryIntent.COMPARISON: [
            r'比較|비교|compare|difference|違い|차이',
            r'vs|versus',
        ],
        QueryIntent.LIST: [
            r'一覧|목록|list|種類|종류|type',
            r'すべて|all|모두',
        ],
    }

    # Exact match patterns (정확 매칭이 필요한 패턴)
    EXACT_MATCH_PATTERNS = {
        ExactMatchType.CONFIG_FILE: r'(\w+\.conf)',  # Config files: osc.conf, tjes.conf
        ExactMatchType.ERROR_CODE: r'(ABEND\s*S[0-9A-Za-z]+|-\d{4,5})',  # ABEND S0C7, -5212
        ExactMatchType.COMMAND_NAME: r'\b(\w+mgr)\b',  # Commands: tjesmgr, oscmgr
    }

    # Known command names for better detection
    KNOWN_COMMANDS = {
        'tjesmgr', 'tacfmgr', 'hidbmgr', 'ndbmgr', 'oscmgr',
        'osimgr', 'volmgr', 'catmgr', 'ofmgr', 'jclmgr',
        'idcams', 'iebgener', 'iebcopy', 'dfsort',
        'dsmigin', 'dsmigout', 'tmboot', 'tmdown',
    }

    def analyze(self, query: str) -> QueryAnalysis:
        """
        쿼리 분석 수행

        Args:
            query: 사용자 쿼리

        Returns:
            QueryAnalysis: 분석 결과
        """
        logger.debug(f"[QueryAnalyzer] Analyzing query: {query}")

        # 1. Intent detection
        intents = self._detect_intents(query)
        primary_intent = self._determine_primary_intent(intents)

        # 2. Exact match detection
        exact_type, exact_value = self._detect_exact_match(query)

        # 3. Keyword extraction
        keywords = self._extract_keywords(query)

        # 4. Language detection
        language = self._detect_language(query)

        result = QueryAnalysis(
            original_query=query,
            intents=intents,
            primary_intent=primary_intent,
            exact_match_type=exact_type,
            exact_match_value=exact_value,
            keywords=keywords,
            language=language,
        )

        logger.info(
            f"[QueryAnalyzer] Result: intent={primary_intent.value}, "
            f"exact_match={exact_type.value}:{exact_value}, lang={language}"
        )

        return result

    def _detect_intents(self, query: str) -> Set[QueryIntent]:
        """의도 감지"""
        intents: Set[QueryIntent] = set()
        query_lower = query.lower()

        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    intents.add(intent)
                    break

        if not intents:
            intents.add(QueryIntent.GENERAL)

        return intents

    def _determine_primary_intent(self, intents: Set[QueryIntent]) -> QueryIntent:
        """주요 의도 결정 (우선순위 기반)"""
        priority = [
            QueryIntent.ERROR,       # 에러는 가장 높은 우선순위
            QueryIntent.COMMAND,     # 명령어 관련
            QueryIntent.STRUCTURE,   # 구조 관련
            QueryIntent.HOWTO,       # 사용법
            QueryIntent.DEFINITION,  # 정의
            QueryIntent.COMPARISON,  # 비교
            QueryIntent.LIST,        # 목록
            QueryIntent.GENERAL,     # 기타
        ]

        for intent in priority:
            if intent in intents:
                return intent

        return QueryIntent.GENERAL

    def _detect_exact_match(self, query: str) -> Tuple[ExactMatchType, Optional[str]]:
        """정확 매칭 패턴 감지"""
        query_lower = query.lower()

        # Priority 1: Check for config files first (most specific)
        config_match = re.search(self.EXACT_MATCH_PATTERNS[ExactMatchType.CONFIG_FILE], query, re.IGNORECASE)
        if config_match:
            return ExactMatchType.CONFIG_FILE, config_match.group(1)

        # Priority 2: Check for error codes
        error_match = re.search(self.EXACT_MATCH_PATTERNS[ExactMatchType.ERROR_CODE], query, re.IGNORECASE)
        if error_match:
            return ExactMatchType.ERROR_CODE, error_match.group(1)

        # Priority 3: Check for known commands
        for cmd in self.KNOWN_COMMANDS:
            if cmd in query_lower:
                return ExactMatchType.COMMAND_NAME, cmd

        # Priority 4: Check for command patterns
        cmd_match = re.search(self.EXACT_MATCH_PATTERNS[ExactMatchType.COMMAND_NAME], query, re.IGNORECASE)
        if cmd_match:
            return ExactMatchType.COMMAND_NAME, cmd_match.group(1)

        return ExactMatchType.NONE, None

    def _extract_keywords(self, query: str) -> List[str]:
        """키워드 추출"""
        keywords: List[str] = []

        # Extract technical terms (uppercase, mixed case with numbers)
        tech_terms = re.findall(r'\b[A-Z][A-Za-z0-9_]*\b', query)
        keywords.extend(tech_terms)

        # Extract config file names
        config_files = re.findall(r'\b\w+\.conf\b', query, re.IGNORECASE)
        keywords.extend(config_files)

        # Extract error codes
        error_codes = re.findall(r'ABEND\s*S\d+|-\d{4,5}', query, re.IGNORECASE)
        keywords.extend(error_codes)

        # Extract known commands
        query_lower = query.lower()
        for cmd in self.KNOWN_COMMANDS:
            if cmd in query_lower and cmd not in keywords:
                keywords.append(cmd)

        # Extract CJK technical terms (2+ characters)
        cjk_terms = re.findall(r'[\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]{2,}', query)
        keywords.extend(cjk_terms)

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                unique_keywords.append(kw)

        return unique_keywords

    def _detect_language(self, query: str) -> str:
        """언어 감지"""
        # Check for Japanese (Hiragana/Katakana)
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', query):
            return "ja"
        # Check for Korean (Hangul)
        if re.search(r'[\uAC00-\uD7AF]', query):
            return "ko"
        # Check for Chinese characters (assume Japanese for this system)
        if re.search(r'[\u4E00-\u9FFF]', query):
            return "ja"
        # Default to English
        return "en"


# =============================================================================
# Singleton Pattern
# =============================================================================

_query_analyzer_service: Optional[QueryAnalyzerService] = None


def get_query_analyzer_service() -> QueryAnalyzerService:
    """QueryAnalyzerService 싱글톤 반환"""
    global _query_analyzer_service
    if _query_analyzer_service is None:
        _query_analyzer_service = QueryAnalyzerService()
    return _query_analyzer_service
