# PDCA Design: RAG Accuracy Improvement

> **Feature**: rag-accuracy-improvement
> **Plan Document**: `docs/01-plan/features/rag-accuracy-improvement.plan.md`
> **Created**: 2026-01-31
> **Version**: v1.0
> **Status**: Design Phase

---

## 1. Design Overview

### 1.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RAG Accuracy Pipeline v2                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  User Query                                                                  │
│      │                                                                       │
│      ▼                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐         │
│  │                    QueryAnalyzerService                         │         │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │         │
│  │  │ Intent      │  │ Keyword     │  │ ExactMatchPattern       │ │         │
│  │  │ Detector    │  │ Extractor   │  │ Detector                │ │         │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘ │         │
│  └────────────────────────────────────────────────────────────────┘         │
│      │                                                                       │
│      ▼                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐         │
│  │                    UnifiedSearchTool (existing)                 │         │
│  │  Vector Search + Keyword Search + CLIP Image Search            │         │
│  └────────────────────────────────────────────────────────────────┘         │
│      │                                                                       │
│      ▼                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐         │
│  │                    RelevanceGraderService [NEW]                 │         │
│  │  ┌─────────────────────────────────────────────────────────┐   │         │
│  │  │ Grade each result: RELEVANT / IRRELEVANT / PARTIAL      │   │         │
│  │  │ Check: Exact Match → Intent Match → Semantic Match      │   │         │
│  │  └─────────────────────────────────────────────────────────┘   │         │
│  └────────────────────────────────────────────────────────────────┘         │
│      │                                                                       │
│      ├── All IRRELEVANT ──▶ QueryRewriterService [NEW] ──▶ Retry (max 2)    │
│      │                                                                       │
│      ▼ (RELEVANT results)                                                    │
│  ┌────────────────────────────────────────────────────────────────┐         │
│  │                    AnswerBuilderService (existing)              │         │
│  │  Generate structured answer from graded results                │         │
│  └────────────────────────────────────────────────────────────────┘         │
│      │                                                                       │
│      ▼                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐         │
│  │                    FaithfulnessCheckerService [NEW]             │         │
│  │  ┌─────────────────────────────────────────────────────────┐   │         │
│  │  │ Verify: FULLY_SUPPORTED / PARTIAL / NOT_SUPPORTED       │   │         │
│  │  └─────────────────────────────────────────────────────────┘   │         │
│  └────────────────────────────────────────────────────────────────┘         │
│      │                                                                       │
│      ├── NOT_SUPPORTED ──▶ PartialMatchHandler [NEW] ──▶ Partial Response   │
│      │                                                                       │
│      ▼ (SUPPORTED)                                                           │
│  ┌────────────────────────────────────────────────────────────────┐         │
│  │                    Final Response with Citations                │         │
│  └────────────────────────────────────────────────────────────────┘         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Summary

| Component | Type | File | Description |
|-----------|------|------|-------------|
| QueryAnalyzerService | NEW | `services/query_analyzer_service.py` | 쿼리 분석 및 메타데이터 추출 |
| RelevanceGraderService | NEW | `services/relevance_grader_service.py` | 검색 결과 관련성 평가 |
| FaithfulnessCheckerService | NEW | `services/faithfulness_checker_service.py` | 응답 근거 검증 |
| QueryRewriterService | NEW | `services/query_rewriter_service.py` | 쿼리 재작성 |
| PartialMatchHandler | NEW | `services/partial_match_handler.py` | 부분 일치 응답 처리 |
| UnifiedSearchTool | MODIFY | `agents/tools/unified_search.py` | Grader 통합 |
| AnswerBuilderService | MODIFY | `services/answer_builder_service.py` | Checker 통합 |
| rag_agent.txt | MODIFY | `agents/prompts/rag_agent.txt` | Strict matching 규칙 추가 |

---

## 2. Data Models

### 2.1 Query Analysis Models

```python
# app/api/models/rag_accuracy.py

from enum import Enum
from typing import List, Optional, Set
from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    """쿼리 의도 분류"""
    DEFINITION = "definition"      # ~とは, ~란, what is
    ERROR = "error"                # 에러, エラー, error
    COMMAND = "command"            # 명령어, コマンド, command
    STRUCTURE = "structure"        # 구조, 構造, architecture
    HOWTO = "howto"               # 방법, 使い方, how to
    COMPARISON = "comparison"      # 비교, 比較, compare
    LIST = "list"                  # 종류, 一覧, list
    GENERAL = "general"            # 기타


class ExactMatchType(str, Enum):
    """정확 매칭이 필요한 패턴 유형"""
    CONFIG_FILE = "config_file"    # *.conf
    ERROR_CODE = "error_code"      # -5212, ABEND S0C7
    COMMAND_NAME = "command_name"  # tjesmgr, oscmgr
    NONE = "none"


class QueryAnalysis(BaseModel):
    """쿼리 분석 결과"""
    original_query: str = Field(..., description="원본 쿼리")
    intents: Set[QueryIntent] = Field(default_factory=set, description="감지된 의도들")
    primary_intent: QueryIntent = Field(default=QueryIntent.GENERAL, description="주요 의도")
    exact_match_type: ExactMatchType = Field(default=ExactMatchType.NONE)
    exact_match_value: Optional[str] = Field(None, description="정확 매칭 대상 값")
    keywords: List[str] = Field(default_factory=list, description="추출된 키워드")
    language: str = Field(default="auto", description="감지된 언어")

    class Config:
        json_schema_extra = {
            "example": {
                "original_query": "osc.confの設定方法",
                "intents": ["howto"],
                "primary_intent": "howto",
                "exact_match_type": "config_file",
                "exact_match_value": "osc.conf",
                "keywords": ["osc.conf", "設定"],
                "language": "ja"
            }
        }
```

### 2.2 Relevance Grading Models

```python
# app/api/models/rag_accuracy.py (continued)

class RelevanceGrade(str, Enum):
    """관련성 등급"""
    RELEVANT = "relevant"           # 질문에 직접 답변 가능
    PARTIAL = "partial"             # 관련 있지만 완전한 답변 아님
    IRRELEVANT = "irrelevant"       # 관련 없음


class GradedResult(BaseModel):
    """등급이 부여된 검색 결과"""
    content: str = Field(..., description="검색 결과 내용")
    doc_name: str = Field(..., description="문서명")
    chunk_id: Optional[str] = Field(None, description="청크 ID")
    original_score: float = Field(..., description="원본 검색 점수")
    grade: RelevanceGrade = Field(..., description="관련성 등급")
    grade_reason: str = Field(..., description="등급 부여 이유")
    exact_match_found: bool = Field(default=False, description="정확 매칭 여부")
    intent_match: bool = Field(default=False, description="의도 매칭 여부")

    class Config:
        json_schema_extra = {
            "example": {
                "content": "osc.conf 파일은 OSC 서버 설정...",
                "doc_name": "OpenFrame_OSC_Guide.pdf",
                "original_score": 0.85,
                "grade": "relevant",
                "grade_reason": "Contains exact config file name and setup info",
                "exact_match_found": True,
                "intent_match": True
            }
        }


class GradingResult(BaseModel):
    """전체 그레이딩 결과"""
    query_analysis: QueryAnalysis
    graded_results: List[GradedResult]
    relevant_count: int = Field(default=0)
    partial_count: int = Field(default=0)
    irrelevant_count: int = Field(default=0)
    needs_rewrite: bool = Field(default=False, description="쿼리 재작성 필요 여부")
```

### 2.3 Faithfulness Check Models

```python
# app/api/models/rag_accuracy.py (continued)

class SupportLevel(str, Enum):
    """근거 지원 수준"""
    FULLY_SUPPORTED = "fully_supported"      # 모든 주장이 컨텍스트에 있음
    PARTIALLY_SUPPORTED = "partially_supported"  # 일부만 지원
    NOT_SUPPORTED = "not_supported"          # 근거 없음


class ClaimVerification(BaseModel):
    """개별 주장 검증 결과"""
    claim: str = Field(..., description="검증 대상 주장")
    supported: bool = Field(..., description="지원 여부")
    evidence: Optional[str] = Field(None, description="근거 텍스트")


class FaithfulnessResult(BaseModel):
    """충실도 검증 결과"""
    answer: str = Field(..., description="검증 대상 응답")
    support_level: SupportLevel = Field(..., description="전체 지원 수준")
    verified_claims: List[ClaimVerification] = Field(default_factory=list)
    unsupported_claims: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
```

### 2.4 Configuration Models

```python
# app/api/models/rag_accuracy.py (continued)

class RAGAccuracyConfig(BaseModel):
    """RAG 정확도 설정"""
    # Relevance Grader
    enable_relevance_grading: bool = Field(default=True)
    relevance_model: str = Field(default="rule_based", description="rule_based or llm")
    min_relevant_results: int = Field(default=1, description="최소 관련 결과 수")

    # Faithfulness Checker
    enable_faithfulness_check: bool = Field(default=True)
    faithfulness_model: str = Field(default="rule_based")
    min_support_level: SupportLevel = Field(default=SupportLevel.PARTIALLY_SUPPORTED)

    # Query Rewriter
    enable_query_rewrite: bool = Field(default=True)
    max_rewrite_attempts: int = Field(default=2)

    # Partial Match Handler
    enable_partial_response: bool = Field(default=True)

    class Config:
        env_prefix = "RAG_ACCURACY_"
        json_schema_extra = {
            "env_var_mapping": {
                "enable_relevance_grading": "RAG_ACCURACY_ENABLE_GRADING",
                "enable_faithfulness_check": "RAG_ACCURACY_ENABLE_FAITHFULNESS",
                "max_rewrite_attempts": "RAG_ACCURACY_MAX_REWRITE"
            }
        }
```

---

## 3. Service Specifications

### 3.1 QueryAnalyzerService

```python
# app/api/services/query_analyzer_service.py

"""
QueryAnalyzerService: 쿼리 분석 및 메타데이터 추출

Responsibilities:
1. 쿼리 의도 감지 (Intent Detection)
2. 정확 매칭 패턴 감지 (Exact Match Detection)
3. 키워드 추출 (Keyword Extraction)
4. 언어 감지 (Language Detection)
"""

import re
import logging
from typing import Optional, Set, List
from functools import lru_cache

from ..models.rag_accuracy import (
    QueryIntent,
    ExactMatchType,
    QueryAnalysis,
)

logger = logging.getLogger(__name__)


class QueryAnalyzerService:
    """쿼리 분석 서비스"""

    # Intent detection patterns
    INTENT_PATTERNS = {
        QueryIntent.DEFINITION: [
            r'とは[?？]?$', r'란[?？]?$', r'이란[?？]?$',
            r'what\s+is', r'무엇', r'정의',
        ],
        QueryIntent.ERROR: [
            r'에러|error|오류|エラー|障害',
            r'ABEND\s*S\d+', r'-\d{4,5}',
        ],
        QueryIntent.COMMAND: [
            r'명령|command|コマンド',
            r'mgr$',  # tjesmgr, oscmgr etc.
        ],
        QueryIntent.STRUCTURE: [
            r'構造|구조|structure|architecture|아키텍처',
            r'構成|구성|configuration',
        ],
        QueryIntent.HOWTO: [
            r'方法|방법|how\s+to|使い方|사용법',
            r'設定|설정|configure|setup',
        ],
    }

    # Exact match patterns
    EXACT_MATCH_PATTERNS = {
        ExactMatchType.CONFIG_FILE: r'(\w+\.conf)\b',
        ExactMatchType.ERROR_CODE: r'(ABEND\s*S\d+|-\d{4,5})',
        ExactMatchType.COMMAND_NAME: r'\b(\w+mgr)\b',
    }

    def analyze(self, query: str) -> QueryAnalysis:
        """
        쿼리 분석 수행

        Args:
            query: 사용자 쿼리

        Returns:
            QueryAnalysis: 분석 결과
        """
        # 1. Intent detection
        intents = self._detect_intents(query)
        primary_intent = self._determine_primary_intent(intents)

        # 2. Exact match detection
        exact_type, exact_value = self._detect_exact_match(query)

        # 3. Keyword extraction
        keywords = self._extract_keywords(query)

        # 4. Language detection
        language = self._detect_language(query)

        return QueryAnalysis(
            original_query=query,
            intents=intents,
            primary_intent=primary_intent,
            exact_match_type=exact_type,
            exact_match_value=exact_value,
            keywords=keywords,
            language=language,
        )

    def _detect_intents(self, query: str) -> Set[QueryIntent]:
        """의도 감지"""
        intents = set()
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
            QueryIntent.ERROR,
            QueryIntent.COMMAND,
            QueryIntent.STRUCTURE,
            QueryIntent.HOWTO,
            QueryIntent.DEFINITION,
            QueryIntent.GENERAL,
        ]

        for intent in priority:
            if intent in intents:
                return intent

        return QueryIntent.GENERAL

    def _detect_exact_match(self, query: str) -> tuple[ExactMatchType, Optional[str]]:
        """정확 매칭 패턴 감지"""
        for match_type, pattern in self.EXACT_MATCH_PATTERNS.items():
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match_type, match.group(1)

        return ExactMatchType.NONE, None

    def _extract_keywords(self, query: str) -> List[str]:
        """키워드 추출"""
        # Remove common stopwords and extract meaningful terms
        # Implementation depends on language
        keywords = []

        # Extract technical terms (uppercase, mixed case with numbers)
        tech_terms = re.findall(r'\b[A-Z][A-Za-z0-9_]*\b', query)
        keywords.extend(tech_terms)

        # Extract config file names
        config_files = re.findall(r'\b\w+\.conf\b', query)
        keywords.extend(config_files)

        return list(set(keywords))

    def _detect_language(self, query: str) -> str:
        """언어 감지"""
        if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', query):  # Hiragana/Katakana
            return "ja"
        if re.search(r'[\uAC00-\uD7AF]', query):  # Korean
            return "ko"
        if re.search(r'[\u4E00-\u9FFF]', query):  # Chinese characters
            return "ja"  # Assume Japanese for this system
        return "en"


# Singleton
_query_analyzer_service: Optional[QueryAnalyzerService] = None

def get_query_analyzer_service() -> QueryAnalyzerService:
    """QueryAnalyzerService 싱글톤 반환"""
    global _query_analyzer_service
    if _query_analyzer_service is None:
        _query_analyzer_service = QueryAnalyzerService()
    return _query_analyzer_service
```

### 3.2 RelevanceGraderService

```python
# app/api/services/relevance_grader_service.py

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
"""

import re
import logging
from typing import List, Dict, Any, Optional

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

    # Intent-to-content mapping
    INTENT_CONTENT_PATTERNS = {
        QueryIntent.STRUCTURE: [
            r'構造|구조|structure|architecture|アーキテクチャ',
            r'構成|구성|composition|component',
            r'概要|개요|overview',
        ],
        QueryIntent.COMMAND: [
            r'コマンド|명령|command',
            r'オプション|옵션|option|parameter',
            r'構文|구문|syntax',
        ],
        QueryIntent.ERROR: [
            r'エラー|에러|error|exception',
            r'原因|원인|cause|reason',
            r'対処|대처|solution|fix',
        ],
        QueryIntent.HOWTO: [
            r'方法|방법|how|procedure',
            r'手順|순서|step',
            r'設定|설정|configure|setup',
        ],
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
        graded_results = []

        for result in search_results:
            graded = self._grade_single_result(query_analysis, result)
            graded_results.append(graded)

        # Count grades
        relevant_count = sum(1 for r in graded_results if r.grade == RelevanceGrade.RELEVANT)
        partial_count = sum(1 for r in graded_results if r.grade == RelevanceGrade.PARTIAL)
        irrelevant_count = sum(1 for r in graded_results if r.grade == RelevanceGrade.IRRELEVANT)

        # Determine if rewrite is needed
        needs_rewrite = relevant_count == 0 and partial_count == 0

        return GradingResult(
            query_analysis=query_analysis,
            graded_results=graded_results,
            relevant_count=relevant_count,
            partial_count=partial_count,
            irrelevant_count=irrelevant_count,
            needs_rewrite=needs_rewrite,
        )

    def _grade_single_result(
        self,
        query_analysis: QueryAnalysis,
        result: Dict[str, Any],
    ) -> GradedResult:
        """단일 결과 그레이딩"""
        content = result.get("content", "") or result.get("text", "")
        doc_name = result.get("doc_name", "") or result.get("document_name", "Unknown")
        original_score = result.get("score", 0.0) or result.get("similarity", 0.0)

        # Step 1: Exact match check
        exact_match_found = self._check_exact_match(query_analysis, content)

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
            content=content[:500],  # Truncate for logging
            doc_name=doc_name,
            chunk_id=result.get("chunk_id"),
            original_score=float(original_score),
            grade=grade,
            grade_reason=reason,
            exact_match_found=exact_match_found,
            intent_match=intent_match,
        )

    def _check_exact_match(self, query_analysis: QueryAnalysis, content: str) -> bool:
        """정확 매칭 확인"""
        if query_analysis.exact_match_type == ExactMatchType.NONE:
            return True  # No exact match required

        exact_value = query_analysis.exact_match_value
        if not exact_value:
            return True

        # Case-insensitive search for exact value
        return exact_value.lower() in content.lower()

    def _check_intent_match(self, query_analysis: QueryAnalysis, content: str) -> bool:
        """의도 매칭 확인"""
        primary_intent = query_analysis.primary_intent

        if primary_intent == QueryIntent.GENERAL:
            return True  # General intent matches anything

        patterns = self.INTENT_CONTENT_PATTERNS.get(primary_intent, [])
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
    ) -> tuple[RelevanceGrade, str]:
        """등급 결정"""

        # Config file strict matching
        if query_analysis.exact_match_type == ExactMatchType.CONFIG_FILE:
            if not exact_match_found:
                return RelevanceGrade.IRRELEVANT, f"Config file '{query_analysis.exact_match_value}' not found in content"

        # Grade determination
        if exact_match_found and intent_match:
            return RelevanceGrade.RELEVANT, "Exact match and intent match"

        if exact_match_found and not intent_match:
            return RelevanceGrade.PARTIAL, "Exact match but intent mismatch"

        if not exact_match_found and intent_match:
            return RelevanceGrade.PARTIAL, "Intent match but no exact match"

        return RelevanceGrade.IRRELEVANT, "No exact match and no intent match"


# Singleton
_relevance_grader_service: Optional[RelevanceGraderService] = None

def get_relevance_grader_service() -> RelevanceGraderService:
    """RelevanceGraderService 싱글톤 반환"""
    global _relevance_grader_service
    if _relevance_grader_service is None:
        _relevance_grader_service = RelevanceGraderService()
    return _relevance_grader_service
```

### 3.3 FaithfulnessCheckerService

```python
# app/api/services/faithfulness_checker_service.py

"""
FaithfulnessCheckerService: 응답 근거 검증

Implements ISSUP-style verification:
- FULLY_SUPPORTED: 모든 주장이 컨텍스트에 근거
- PARTIALLY_SUPPORTED: 일부만 근거 있음
- NOT_SUPPORTED: 근거 없음
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..models.rag_accuracy import (
    SupportLevel,
    ClaimVerification,
    FaithfulnessResult,
)

logger = logging.getLogger(__name__)


class FaithfulnessCheckerService:
    """응답 충실도 검증 서비스"""

    # Common claim indicators to extract
    CLAIM_PATTERNS = [
        r'です[。．]',           # Japanese sentence ending
        r'ます[。．]',
        r'입니다[.。]',         # Korean sentence ending
        r'합니다[.。]',
        r'\.\s',               # English sentence ending
    ]

    def check_faithfulness(
        self,
        answer: str,
        context: str,
        graded_results: List[Dict[str, Any]],
    ) -> FaithfulnessResult:
        """
        응답 충실도 검증

        Args:
            answer: 생성된 응답
            context: 검색된 컨텍스트 (연결된 문자열)
            graded_results: 그레이딩된 검색 결과

        Returns:
            FaithfulnessResult: 충실도 검증 결과
        """
        # Extract claims from answer
        claims = self._extract_claims(answer)

        # Verify each claim against context
        verified_claims = []
        unsupported_claims = []

        for claim in claims:
            verification = self._verify_claim(claim, context)
            if verification.supported:
                verified_claims.append(verification)
            else:
                unsupported_claims.append(claim)

        # Calculate support level
        support_level = self._calculate_support_level(
            total_claims=len(claims),
            supported_count=len(verified_claims),
        )

        # Calculate confidence
        confidence = len(verified_claims) / len(claims) if claims else 0.0

        return FaithfulnessResult(
            answer=answer,
            support_level=support_level,
            verified_claims=verified_claims,
            unsupported_claims=unsupported_claims,
            confidence=confidence,
        )

    def _extract_claims(self, answer: str) -> List[str]:
        """응답에서 주장 추출"""
        # Split by sentence boundaries
        sentences = re.split(r'[。．.!?！？]\s*', answer)

        # Filter out empty or too short sentences
        claims = [s.strip() for s in sentences if len(s.strip()) > 10]

        return claims

    def _verify_claim(self, claim: str, context: str) -> ClaimVerification:
        """개별 주장 검증"""
        # Extract key terms from claim
        key_terms = self._extract_key_terms(claim)

        # Check if key terms appear in context
        context_lower = context.lower()
        matched_terms = [t for t in key_terms if t.lower() in context_lower]

        # Calculate match ratio
        match_ratio = len(matched_terms) / len(key_terms) if key_terms else 0.0

        # Determine if supported (threshold: 50% key terms)
        supported = match_ratio >= 0.5

        # Find evidence snippet
        evidence = None
        if supported and matched_terms:
            evidence = self._find_evidence_snippet(matched_terms[0], context)

        return ClaimVerification(
            claim=claim,
            supported=supported,
            evidence=evidence,
        )

    def _extract_key_terms(self, text: str) -> List[str]:
        """핵심 용어 추출"""
        # Technical terms (uppercase, mixed case)
        tech_terms = re.findall(r'\b[A-Z][A-Za-z0-9_.-]+\b', text)

        # Numbers and codes
        codes = re.findall(r'\b\d+\b', text)

        # CJK terms (longer than 2 characters)
        cjk_terms = re.findall(r'[\u3040-\u9FFF]{2,}', text)

        return tech_terms + codes + cjk_terms

    def _find_evidence_snippet(self, term: str, context: str, window: int = 100) -> Optional[str]:
        """근거 스니펫 찾기"""
        idx = context.lower().find(term.lower())
        if idx == -1:
            return None

        start = max(0, idx - window)
        end = min(len(context), idx + len(term) + window)

        return context[start:end]

    def _calculate_support_level(self, total_claims: int, supported_count: int) -> SupportLevel:
        """지원 수준 계산"""
        if total_claims == 0:
            return SupportLevel.NOT_SUPPORTED

        ratio = supported_count / total_claims

        if ratio >= 0.8:
            return SupportLevel.FULLY_SUPPORTED
        elif ratio >= 0.3:
            return SupportLevel.PARTIALLY_SUPPORTED
        else:
            return SupportLevel.NOT_SUPPORTED


# Singleton
_faithfulness_checker_service: Optional[FaithfulnessCheckerService] = None

def get_faithfulness_checker_service() -> FaithfulnessCheckerService:
    """FaithfulnessCheckerService 싱글톤 반환"""
    global _faithfulness_checker_service
    if _faithfulness_checker_service is None:
        _faithfulness_checker_service = FaithfulnessCheckerService()
    return _faithfulness_checker_service
```

### 3.4 QueryRewriterService

```python
# app/api/services/query_rewriter_service.py

"""
QueryRewriterService: 쿼리 재작성

검색 결과가 없거나 관련 없을 때 쿼리를 개선합니다.
"""

import logging
from typing import Optional, List

from ..models.rag_accuracy import QueryAnalysis, QueryIntent

logger = logging.getLogger(__name__)


class QueryRewriterService:
    """쿼리 재작성 서비스"""

    # Intent-specific expansion templates
    EXPANSION_TEMPLATES = {
        QueryIntent.STRUCTURE: [
            "{query} 概要",
            "{query} アーキテクチャ",
            "{query} overview",
        ],
        QueryIntent.COMMAND: [
            "{query} コマンド",
            "{query} 使い方",
            "{query} オプション",
        ],
        QueryIntent.ERROR: [
            "{query} 原因",
            "{query} 対処",
            "{query} 解決",
        ],
        QueryIntent.HOWTO: [
            "{query} 方法",
            "{query} 手順",
            "{query} 設定",
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

        # Get expansion templates for intent
        templates = self.EXPANSION_TEMPLATES.get(intent, [])

        if not templates:
            # Fallback: simplify query
            return self._simplify_query(original, query_analysis.keywords)

        # Select template based on attempt
        template_idx = min(attempt - 1, len(templates) - 1)
        template = templates[template_idx]

        # Apply template
        rewritten = template.format(query=self._get_core_term(query_analysis))

        logger.info(f"[QueryRewriter] Rewritten: '{original}' → '{rewritten}'")

        return rewritten

    def _get_core_term(self, query_analysis: QueryAnalysis) -> str:
        """쿼리의 핵심 용어 추출"""
        # Prefer exact match value
        if query_analysis.exact_match_value:
            return query_analysis.exact_match_value

        # Use first keyword
        if query_analysis.keywords:
            return query_analysis.keywords[0]

        # Fallback to original query
        return query_analysis.original_query

    def _simplify_query(self, query: str, keywords: List[str]) -> str:
        """쿼리 단순화"""
        if keywords:
            return " ".join(keywords[:2])
        return query


# Singleton
_query_rewriter_service: Optional[QueryRewriterService] = None

def get_query_rewriter_service() -> QueryRewriterService:
    global _query_rewriter_service
    if _query_rewriter_service is None:
        _query_rewriter_service = QueryRewriterService()
    return _query_rewriter_service
```

### 3.5 PartialMatchHandler

```python
# app/api/services/partial_match_handler.py

"""
PartialMatchHandler: 부분 일치 응답 처리

검색 결과가 질문에 완전히 답하지 못할 때 사용자에게 명확한 안내를 제공합니다.
"""

import logging
from typing import List, Optional

from ..models.rag_accuracy import (
    QueryAnalysis,
    GradedResult,
    RelevanceGrade,
    SupportLevel,
)

logger = logging.getLogger(__name__)


class PartialMatchHandler:
    """부분 일치 응답 처리기"""

    # Response templates by language
    TEMPLATES = {
        "ja": {
            "partial_intro": "「{query}」に関連する情報が見つかりましたが、完全な回答ではありません：",
            "found_instead": "以下の関連情報が見つかりました：",
            "no_exact_match": "「{exact_term}」の正確な情報は見つかりませんでした。",
            "suggestion": "より具体的なキーワードで検索してみてください。",
            "related_topics": "関連トピック：",
        },
        "ko": {
            "partial_intro": "'{query}'와 관련된 정보를 찾았지만, 완전한 답변이 아닙니다:",
            "found_instead": "다음 관련 정보를 찾았습니다:",
            "no_exact_match": "'{exact_term}'에 대한 정확한 정보를 찾지 못했습니다.",
            "suggestion": "더 구체적인 키워드로 검색해 보세요.",
            "related_topics": "관련 토픽:",
        },
        "en": {
            "partial_intro": "Found related information for '{query}', but not a complete answer:",
            "found_instead": "Found the following related information:",
            "no_exact_match": "No exact information found for '{exact_term}'.",
            "suggestion": "Try searching with more specific keywords.",
            "related_topics": "Related topics:",
        },
    }

    def build_partial_response(
        self,
        query_analysis: QueryAnalysis,
        graded_results: List[GradedResult],
        support_level: SupportLevel,
    ) -> str:
        """
        부분 일치 응답 생성

        Args:
            query_analysis: 쿼리 분석 결과
            graded_results: 그레이딩된 검색 결과
            support_level: 충실도 검증 결과

        Returns:
            부분 일치 응답 문자열
        """
        lang = query_analysis.language
        templates = self.TEMPLATES.get(lang, self.TEMPLATES["en"])

        parts = []

        # 1. Introduction
        if support_level == SupportLevel.PARTIALLY_SUPPORTED:
            parts.append(templates["partial_intro"].format(query=query_analysis.original_query))
        else:
            parts.append(templates["found_instead"])

        # 2. Exact match warning
        if query_analysis.exact_match_value:
            exact_found = any(r.exact_match_found for r in graded_results)
            if not exact_found:
                parts.append("")
                parts.append(templates["no_exact_match"].format(exact_term=query_analysis.exact_match_value))

        # 3. Related topics from partial matches
        partial_results = [r for r in graded_results if r.grade in (RelevanceGrade.RELEVANT, RelevanceGrade.PARTIAL)]
        if partial_results:
            parts.append("")
            parts.append(templates["related_topics"])
            for r in partial_results[:3]:
                parts.append(f"- {r.doc_name}: {r.content[:100]}...")

        # 4. Suggestion
        parts.append("")
        parts.append(templates["suggestion"])

        return "\n".join(parts)


# Singleton
_partial_match_handler: Optional[PartialMatchHandler] = None

def get_partial_match_handler() -> PartialMatchHandler:
    global _partial_match_handler
    if _partial_match_handler is None:
        _partial_match_handler = PartialMatchHandler()
    return _partial_match_handler
```

---

## 4. Integration Points

### 4.1 UnifiedSearchTool Integration

```python
# app/api/agents/tools/unified_search.py 수정 사항

# === 추가할 import ===
from ...services.query_analyzer_service import get_query_analyzer_service
from ...services.relevance_grader_service import get_relevance_grader_service
from ...services.query_rewriter_service import get_query_rewriter_service

# === execute() 메서드 내 추가 로직 ===

async def execute(self, parameters: Dict[str, Any], context: AgentContext) -> ToolResult:
    """Execute unified search with relevance grading"""
    query = parameters.get("query", "")

    # NEW: Query analysis
    query_analyzer = get_query_analyzer_service()
    query_analysis = query_analyzer.analyze(query)

    # Existing search logic...
    search_results = await self._perform_search(query, parameters)

    # NEW: Relevance grading
    if os.getenv("RAG_ACCURACY_ENABLE_GRADING", "true").lower() == "true":
        relevance_grader = get_relevance_grader_service()
        grading_result = relevance_grader.grade_results(query_analysis, search_results)

        # Filter to relevant/partial results only
        filtered_results = [
            r for r, gr in zip(search_results, grading_result.graded_results)
            if gr.grade in (RelevanceGrade.RELEVANT, RelevanceGrade.PARTIAL)
        ]

        # NEW: Query rewrite if no relevant results
        if grading_result.needs_rewrite and context.get("rewrite_attempt", 0) < 2:
            rewriter = get_query_rewriter_service()
            rewritten_query = rewriter.rewrite(query_analysis, context.get("rewrite_attempt", 0) + 1)

            # Recursive search with rewritten query
            new_context = context.copy()
            new_context["rewrite_attempt"] = context.get("rewrite_attempt", 0) + 1

            return await self.execute({"query": rewritten_query, **parameters}, new_context)

        # Add grading metadata to results
        for i, result in enumerate(filtered_results):
            if i < len(grading_result.graded_results):
                result["relevance_grade"] = grading_result.graded_results[i].grade.value
                result["grade_reason"] = grading_result.graded_results[i].grade_reason

        search_results = filtered_results

    return ToolResult(success=True, data=search_results)
```

### 4.2 AnswerBuilderService Integration

```python
# app/api/services/answer_builder_service.py 수정 사항

# === 추가할 import ===
from .faithfulness_checker_service import get_faithfulness_checker_service
from .partial_match_handler import get_partial_match_handler
from ..models.rag_accuracy import SupportLevel

# === build_answer() 메서드 수정 ===

async def build_answer(
    self,
    query: str,
    search_results: List[Dict[str, Any]],
    intent: Optional[str] = None,
    language: str = "auto",
    multi_product_results: Optional[List[Dict[str, Any]]] = None
) -> StructuredAnswer:
    """Build structured answer with faithfulness checking"""

    # Existing answer building logic...
    answer = await self._build_answer_internal(query, search_results, intent, language, multi_product_results)

    # NEW: Faithfulness check
    if os.getenv("RAG_ACCURACY_ENABLE_FAITHFULNESS", "true").lower() == "true":
        faithfulness_checker = get_faithfulness_checker_service()

        # Combine context from search results
        context = "\n".join([r.get("content", "") for r in search_results])

        # Check faithfulness
        faithfulness_result = faithfulness_checker.check_faithfulness(
            answer=answer.blocks[0].content if answer.blocks else "",
            context=context,
            graded_results=search_results,
        )

        # Handle unsupported answers
        if faithfulness_result.support_level == SupportLevel.NOT_SUPPORTED:
            partial_handler = get_partial_match_handler()

            # Get query analysis from context or create new
            query_analysis = context.get("query_analysis")
            if not query_analysis:
                from .query_analyzer_service import get_query_analyzer_service
                query_analysis = get_query_analyzer_service().analyze(query)

            partial_response = partial_handler.build_partial_response(
                query_analysis=query_analysis,
                graded_results=[],  # Would need GradedResult objects
                support_level=faithfulness_result.support_level,
            )

            return StructuredAnswer(
                blocks=[AnswerBlock(type=BlockType.PARTIAL_MATCH, content=partial_response)],
                confidence=faithfulness_result.confidence,
                language=language,
                metadata={"support_level": faithfulness_result.support_level.value}
            )

        # Add faithfulness metadata
        answer.metadata["support_level"] = faithfulness_result.support_level.value
        answer.metadata["faithfulness_confidence"] = faithfulness_result.confidence

    return answer
```

---

## 5. Prompt Updates

### 5.1 RAG Agent Prompt Additions

```markdown
# app/api/agents/prompts/rag_agent.txt 에 추가할 내용

## 🔒 STRICT MATCHING RULES

### Config File Matching
When user asks about a SPECIFIC config file (e.g., osc.conf, tacf.conf):
1. Search results MUST contain the EXACT filename
2. If only DIFFERENT config files are found → Say "情報が見つかりませんでした"
3. NEVER substitute one config file for another

| User Asks | Found | Action |
|-----------|-------|--------|
| osc.conf | osc.conf info | ✅ Answer |
| osc.conf | tjes.conf info | ❌ "osc.confの情報は見つかりませんでした" |
| osc.conf | both files | ✅ Answer ONLY about osc.conf |

### Intent-Content Matching
When user asks about STRUCTURE (構造, 구조, architecture):
- Results about COMMANDS/USAGE are NOT relevant
- Say: "構造に関する情報は見つかりませんでした。コマンドの情報はあります。"

When user asks about USAGE (使い方, 사용법):
- Results about STRUCTURE/OVERVIEW are NOT relevant
- Focus on command options, parameters, examples

### Partial Match Response
When search finds RELATED but not EXACT information:
1. Do NOT say "情報が見つかりませんでした" (completely)
2. Instead, say: "完全な回答ではありませんが、関連情報を見つけました："
3. List what WAS found
4. Suggest alternative search terms
```

---

## 6. Configuration & Environment Variables

### 6.1 New Environment Variables

```bash
# .env.example 에 추가

# === RAG Accuracy Improvement ===
# Relevance Grading
RAG_ACCURACY_ENABLE_GRADING=true
RAG_ACCURACY_GRADING_MODEL=rule_based  # rule_based or llm
RAG_ACCURACY_MIN_RELEVANT=1

# Faithfulness Checking
RAG_ACCURACY_ENABLE_FAITHFULNESS=true
RAG_ACCURACY_FAITHFULNESS_MODEL=rule_based

# Query Rewriting
RAG_ACCURACY_ENABLE_REWRITE=true
RAG_ACCURACY_MAX_REWRITE=2

# Partial Match
RAG_ACCURACY_ENABLE_PARTIAL=true
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

```python
# tests/unit/test_relevance_grader.py

import pytest
from app.api.services.relevance_grader_service import RelevanceGraderService
from app.api.models.rag_accuracy import QueryAnalysis, ExactMatchType, QueryIntent, RelevanceGrade

class TestRelevanceGrader:

    def test_config_file_exact_match_required(self):
        """Config 파일은 정확 매칭 필수"""
        grader = RelevanceGraderService()

        query_analysis = QueryAnalysis(
            original_query="osc.confの設定方法",
            intents={QueryIntent.HOWTO},
            primary_intent=QueryIntent.HOWTO,
            exact_match_type=ExactMatchType.CONFIG_FILE,
            exact_match_value="osc.conf",
            keywords=["osc.conf"],
            language="ja",
        )

        # tjes.conf 정보만 있는 결과
        results = [{"content": "tjes.confの設定方法について説明します...", "doc_name": "TJES_Guide.pdf"}]

        grading = grader.grade_results(query_analysis, results)

        assert grading.graded_results[0].grade == RelevanceGrade.IRRELEVANT
        assert not grading.graded_results[0].exact_match_found

    def test_intent_mismatch_partial(self):
        """의도 불일치는 PARTIAL"""
        grader = RelevanceGraderService()

        query_analysis = QueryAnalysis(
            original_query="OSIシステムの構造",
            intents={QueryIntent.STRUCTURE},
            primary_intent=QueryIntent.STRUCTURE,
            exact_match_type=ExactMatchType.NONE,
            keywords=["OSI"],
            language="ja",
        )

        # 명령어 정보만 있는 결과
        results = [{"content": "OSIシステムを起動するにはTMBOOTコマンドを使用します...", "doc_name": "OSI_Command.pdf"}]

        grading = grader.grade_results(query_analysis, results)

        # 명령어 정보이므로 구조 질문에는 PARTIAL
        assert grading.graded_results[0].grade in (RelevanceGrade.PARTIAL, RelevanceGrade.IRRELEVANT)
```

### 7.2 E2E Test Updates

```javascript
// e2e/e2e_sentence_test.js 에 추가할 테스트 케이스

const STRICT_MATCH_TESTS = [
    {
        keyword: 'osc.conf',
        query: 'osc.confの設定方法を教えてください。',
        expected: ['osc.conf'],
        notExpected: ['tjes.conf'],  // Must NOT mention other config files
        strictMatch: true,
    },
    {
        keyword: 'OSI構造',
        query: 'OSIシステムの構造について説明してください。',
        expected: ['構造', '構成', 'アーキテクチャ'],
        notExpected: [],  // If only commands found, should say "構造の情報なし"
        intentMatch: 'structure',
    },
];
```

---

## 8. Implementation Order

### Phase 1: Core Services (Week 1)
1. [ ] `app/api/models/rag_accuracy.py` - 데이터 모델 생성
2. [ ] `app/api/services/query_analyzer_service.py` - 쿼리 분석기
3. [ ] `app/api/services/relevance_grader_service.py` - 관련성 평가기
4. [ ] Unit tests for Phase 1

### Phase 2: Verification Services (Week 2)
5. [ ] `app/api/services/faithfulness_checker_service.py` - 충실도 검증기
6. [ ] `app/api/services/query_rewriter_service.py` - 쿼리 재작성기
7. [ ] `app/api/services/partial_match_handler.py` - 부분 일치 처리기
8. [ ] Unit tests for Phase 2

### Phase 3: Integration (Week 3)
9. [ ] `app/api/agents/tools/unified_search.py` 수정 - Grader 통합
10. [ ] `app/api/services/answer_builder_service.py` 수정 - Checker 통합
11. [ ] Integration tests

### Phase 4: Prompts & Config (Week 4)
12. [ ] `app/api/agents/prompts/rag_agent.txt` 수정
13. [ ] `.env.example` 환경변수 추가
14. [ ] E2E tests 확장
15. [ ] Documentation update

---

## 9. Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Hallucination Rate | 3% | <0.5% | E2E Test: notExpected keywords |
| Config File Accuracy | ~90% | 100% | E2E Test: strict match cases |
| Intent Match Rate | ~85% | >95% | E2E Test: intent-specific queries |
| Faithfulness Score | N/A | >0.90 | FaithfulnessChecker output |
| E2E Pass Rate | 97% | >99% | e2e_sentence_test.js |

---

**Next Step**: `/pdca do rag-accuracy-improvement`

---

> **Design Version**: v1.0
> **Created by**: Claude Code + bkit PDCA
> **Last Updated**: 2026-01-31
