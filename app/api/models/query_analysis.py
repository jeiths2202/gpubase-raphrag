"""
Query Analysis Models for Semantic Search

LLM 기반 쿼리 분석 결과를 담는 Pydantic 모델들
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class QueryIntent(str, Enum):
    """쿼리 의도 분류"""
    EXPLANATION = "explanation"      # ~について説明して, ~가 뭐야
    DEFINITION = "definition"        # ~とは？, ~의 정의
    USAGE = "usage"                  # ~の使い方, 사용법
    ERROR_RESOLUTION = "error"       # エラー解決, 에러 해결
    COMPARISON = "comparison"        # ~と~の違い, 비교
    PROCEDURE = "procedure"          # ~の手順, 절차
    CONFIGURATION = "configuration"  # ~の設定方法, 설정
    SEARCH = "search"               # 일반 검색


class ExtractedEntity(BaseModel):
    """추출된 Entity"""
    type: str = Field(
        ...,
        description="Entity type: command, error_code, product, config, term"
    )
    value: str = Field(
        ...,
        description="Extracted entity value"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.8,
        description="Extraction confidence"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "type": "command",
                "value": "ofasmif",
                "confidence": 0.95
            }
        }


class QueryAnalysis(BaseModel):
    """LLM 쿼리 분석 결과"""
    original_query: str = Field(
        ...,
        description="Original user query"
    )
    intent: QueryIntent = Field(
        default=QueryIntent.SEARCH,
        description="Classified query intent"
    )
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Extracted named entities"
    )
    language: str = Field(
        default="en",
        description="Detected language code (ja, ko, en)"
    )
    rewritten_query: str = Field(
        ...,
        description="Search-optimized query in English"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="Key search keywords"
    )

    # 메타데이터
    analysis_source: str = Field(
        default="llm",
        description="Analysis source: llm, cache, fallback"
    )
    processing_time_ms: Optional[float] = Field(
        default=None,
        description="Processing time in milliseconds"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "original_query": "ofasmifコマンドについて説明してください",
                "intent": "explanation",
                "entities": [
                    {"type": "command", "value": "ofasmif", "confidence": 0.95}
                ],
                "language": "ja",
                "rewritten_query": "ofasmif command syntax usage parameters manual OFASM",
                "keywords": ["ofasmif", "command", "OFASM", "コマンド"],
                "analysis_source": "llm",
                "processing_time_ms": 150.5
            }
        }

    def get_primary_entity(self) -> Optional[ExtractedEntity]:
        """가장 신뢰도 높은 Entity 반환"""
        if not self.entities:
            return None
        return max(self.entities, key=lambda e: e.confidence)

    def has_entity_type(self, entity_type: str) -> bool:
        """특정 타입의 Entity 존재 여부"""
        return any(e.type == entity_type for e in self.entities)

    def get_entities_by_type(self, entity_type: str) -> List[ExtractedEntity]:
        """특정 타입의 모든 Entity 반환"""
        return [e for e in self.entities if e.type == entity_type]


class RetrievalResult(BaseModel):
    """검색 결과 단일 항목"""
    doc_id: str = Field(..., description="Document/Chunk ID")
    content: str = Field(..., description="Document content")
    source: str = Field(
        ...,
        description="Result source: vector, keyword, entity"
    )
    score: float = Field(..., description="Relevance score")
    original_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Original scores from each retriever"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )

    # 문서 정보
    document_title: Optional[str] = None
    page_number: Optional[int] = None
    chunk_index: Optional[int] = None
    pdf_path: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "chunk_12345",
                "content": "ofasmif is a command-line tool for...",
                "source": "entity",
                "score": 0.95,
                "original_scores": {"entity": 1.0, "vector": 0.85},
                "metadata": {"entity_type": "command"},
                "document_title": "OF_ASM_Reference_Guide",
                "page_number": 45
            }
        }


class HybridSearchResult(BaseModel):
    """하이브리드 검색 전체 결과"""
    query_analysis: QueryAnalysis = Field(
        ...,
        description="Query analysis result"
    )
    results: List[RetrievalResult] = Field(
        default_factory=list,
        description="Ranked search results"
    )
    total_candidates: int = Field(
        default=0,
        description="Total candidates before fusion"
    )
    search_time_ms: float = Field(
        default=0.0,
        description="Total search time in milliseconds"
    )

    # 디버깅 정보
    vector_count: int = Field(default=0, description="Vector search results count")
    keyword_count: int = Field(default=0, description="Keyword search results count")
    entity_count: int = Field(default=0, description="Entity lookup results count")

    def top_k(self, k: int = 10) -> List[RetrievalResult]:
        """상위 K개 결과 반환"""
        return self.results[:k]
