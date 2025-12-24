"""
Query-related Pydantic models
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class StrategyType(str, Enum):
    """Query strategy types"""
    AUTO = "auto"
    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"
    CODE = "code"


class LanguageType(str, Enum):
    """Supported languages"""
    AUTO = "auto"
    KO = "ko"
    JA = "ja"
    EN = "en"


class QueryOptions(BaseModel):
    """Query options"""
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    include_sources: bool = Field(default=True, description="Include source documents")
    conversation_id: Optional[str] = Field(default=None, description="Conversation session ID")


class QueryRequest(BaseModel):
    """Query request model"""
    question: str = Field(..., min_length=1, max_length=2000, description="Question text")
    strategy: StrategyType = Field(default=StrategyType.AUTO, description="Search strategy")
    language: LanguageType = Field(default=LanguageType.AUTO, description="Response language")
    options: Optional[QueryOptions] = Field(default_factory=QueryOptions)

    class Config:
        json_schema_extra = {
            "example": {
                "question": "OpenFrame 설치 방법을 알려주세요",
                "strategy": "auto",
                "language": "auto",
                "options": {
                    "top_k": 5,
                    "include_sources": True
                }
            }
        }


class SourceInfo(BaseModel):
    """Source document information"""
    doc_id: str
    doc_name: str
    chunk_id: str
    chunk_index: int
    content: str
    score: float = Field(ge=0.0, le=1.0)
    source_type: str
    entities: list[str] = Field(default_factory=list)


class QueryAnalysis(BaseModel):
    """Query analysis result"""
    detected_language: str
    query_type: str
    is_comprehensive: bool = False
    is_deep_analysis: bool = False
    has_error_code: bool = False


class QueryResponse(BaseModel):
    """Query response model"""
    answer: str
    strategy: StrategyType
    language: LanguageType
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[SourceInfo] = Field(default_factory=list)
    query_analysis: Optional[QueryAnalysis] = None


class ClassificationResult(BaseModel):
    """Query classification result"""
    strategy: StrategyType
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]


class ClassificationFeatures(BaseModel):
    """Features detected in query"""
    language: str
    has_error_code: bool = False
    is_comprehensive: bool = False
    is_code_query: bool = False


class ClassifyResponse(BaseModel):
    """Classification response model"""
    question: str
    classification: ClassificationResult
    features: ClassificationFeatures
