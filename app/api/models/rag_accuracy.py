"""
RAG Accuracy Improvement Data Models

This module defines data models for:
- Query Analysis (Intent Detection, Exact Match Patterns)
- Relevance Grading (ISREL-style)
- Faithfulness Checking (ISSUP-style)
- Configuration

Created as part of PDCA: rag-accuracy-improvement
"""

from enum import Enum
from typing import List, Optional, Set
from pydantic import BaseModel, Field


# =============================================================================
# Query Analysis Models
# =============================================================================


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


# =============================================================================
# Relevance Grading Models
# =============================================================================


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
    graded_results: List[GradedResult] = Field(default_factory=list)
    relevant_count: int = Field(default=0)
    partial_count: int = Field(default=0)
    irrelevant_count: int = Field(default=0)
    needs_rewrite: bool = Field(default=False, description="쿼리 재작성 필요 여부")


# =============================================================================
# Faithfulness Check Models
# =============================================================================


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


# =============================================================================
# Configuration Models
# =============================================================================


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
