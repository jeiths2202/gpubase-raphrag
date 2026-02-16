"""
OpenFrame RAG Models

QLoRA Learning LLM 기반 Multi-Product RAG 시스템용 Pydantic 모델
8개 제품(openframe_mvs, msp_openframe, vos3_openframe, tibero7, ofasm, ofcobol, xsp_openframe, tmax)에 대한
동적 라우팅 및 DeepSeek 통합 검색을 지원합니다.
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict
from .web_doc import WebDocSource


# =============================================================================
# Enums
# =============================================================================

class ProductId(str, Enum):
    """Supported product identifiers"""
    OPENFRAME_MVS = "openframe_mvs"
    OPENFRAME_BASE = "openframe_base"  # OpenFrame Base 시스템
    MSP_OPENFRAME = "msp_openframe"
    VOS3_OPENFRAME = "vos3_openframe"
    TIBERO7 = "tibero7"
    OFASM = "ofasm"
    OFCOBOL = "ofcobol"
    OFPLI = "ofpli"
    XSP_OPENFRAME = "xsp_openframe"
    TMAX = "tmax"
    JEUS = "jeus"
    WEBTOB = "webtob"
    OFGW = "ofgw"
    OFMANAGER = "ofmanager"
    OFMINER = "ofminer"
    OFSTUDIO = "ofstudio"
    PROSORT = "prosort"
    PROSYNC = "prosync"
    PROTRIEVE = "protrieve"
    AUTO = "auto"       # 자동 분류
    OTHER = "other"     # 기타 (모든 제품 검색)


class SourceType(str, Enum):
    """Source types for RAG responses"""
    LEARNING_LLM = "learning_llm"
    VECTOR_SEARCH = "vector_search"
    GRAPH_SEARCH = "graph_search"


class ConfidenceLevel(str, Enum):
    """Confidence level for classification"""
    HIGH = "high"       # >= 0.8
    MEDIUM = "medium"   # 0.5-0.8
    LOW = "low"         # < 0.5


# =============================================================================
# Classification Models
# =============================================================================

class ProductKeywords(BaseModel):
    """Product-specific keywords for classification"""
    product: ProductId
    keywords: List[str] = Field(default_factory=list)
    patterns: List[str] = Field(default_factory=list, description="Regex patterns")
    weight: float = Field(default=1.0, ge=0.0, le=2.0)


class ClassificationResult(BaseModel):
    """Product classification result"""
    product: ProductId
    confidence: float = Field(ge=0.0, le=1.0)
    needs_selection: bool = Field(
        default=False,
        description="True if confidence < 0.7 and user selection is needed"
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Alternative product suggestions"
    )
    matched_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords that matched"
    )
    all_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Scores for all products"
    )


class ClassifyRequest(BaseModel):
    """Classification request"""
    query: str = Field(..., min_length=1, max_length=4000)
    language: Optional[str] = Field(default="ja", description="UI language (en, ko, ja)")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "query": "tjesmgrのBOOTコマンドについて教えてください",
            "language": "ja"
        }
    })


class ClassifyResponse(BaseModel):
    """Classification response"""
    success: bool
    classification: ClassificationResult
    message: str = ""


# =============================================================================
# Source Models
# =============================================================================

class LearningLLMSource(BaseModel):
    """Learning LLM response source"""
    model: str = Field(default="Qwen/Qwen2.5-7B-Instruct+QLoRA")
    adapter: Optional[str] = Field(default=None, description="Active QLoRA adapter")
    product: Optional[str] = Field(default=None, description="Target product ID")
    confidence: float = Field(ge=0.0, le=1.0)
    generation_time_ms: Optional[int] = None


class VectorSource(BaseModel):
    """Vector search result source"""
    chunk_id: str
    doc_id: str
    doc_name: str
    content: str
    score: float = Field(ge=0.0)
    page_number: Optional[int] = None
    product: Optional[str] = None


class GraphSource(BaseModel):
    """Graph search result source"""
    entity_id: str
    entity_name: str
    entity_type: str
    related_chunks: List[str] = Field(default_factory=list)
    score: float = Field(ge=0.0)
    product: Optional[str] = None


class ProductSources(BaseModel):
    """Combined sources for a response"""
    learning_llm: Optional[LearningLLMSource] = None
    vector_search: List[VectorSource] = Field(default_factory=list)
    graph_search: List[GraphSource] = Field(default_factory=list)
    web_doc: Optional[WebDocSource] = Field(default=None, description="Web document source (docs.tmaxsoft.com)")


# =============================================================================
# Chat Request/Response Models
# =============================================================================

class ChatMessage(BaseModel):
    """A single chat message"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class OpenFrameRAGRequest(BaseModel):
    """OpenFrame RAG chat request"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="User message/question"
    )
    product: ProductId = Field(
        default=ProductId.AUTO,
        description="Target product (auto for automatic classification)"
    )
    history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="Conversation history"
    )
    file_content: Optional[str] = Field(
        default=None,
        description="Attached file content for context"
    )
    language: Optional[str] = Field(
        default="ja",
        description="UI language (en, ko, ja)"
    )
    use_learning_llm: bool = Field(
        default=True,
        description="Whether to use Learning LLM"
    )
    use_vector_search: bool = Field(
        default=True,
        description="Whether to use vector search"
    )
    use_graph_search: bool = Field(
        default=True,
        description="Whether to use graph search"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "tjesmgrのBOOTコマンドの使い方を教えてください",
            "product": "auto",
            "language": "ja"
        }
    })


class OpenFrameRAGResponse(BaseModel):
    """OpenFrame RAG chat response"""
    success: bool
    response: str = Field(..., description="Generated response")
    product: ProductId = Field(..., description="Product used for this response")
    classification: Optional[ClassificationResult] = Field(
        default=None,
        description="Classification result (if auto-classified)"
    )
    sources: ProductSources = Field(
        default_factory=ProductSources,
        description="Source information"
    )
    confidence: ConfidenceLevel = Field(
        default=ConfidenceLevel.LOW,
        description="Overall response confidence"
    )
    model: str = Field(default="Qwen/Qwen2.5-7B-Instruct+QLoRA")
    processing_time_ms: Optional[int] = None


# =============================================================================
# DeepSeek Models
# =============================================================================

class DeepSeekRequest(BaseModel):
    """DeepSeek comprehensive search request"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="User message/question"
    )
    history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="Conversation history"
    )
    file_content: Optional[str] = Field(
        default=None,
        description="Attached file content"
    )
    language: Optional[str] = Field(
        default="ja",
        description="UI language"
    )
    max_products: int = Field(
        default=8,
        ge=1,
        le=8,
        description="Maximum number of products to search"
    )
    include_all_databases: bool = Field(
        default=True,
        description="Include all database sources"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "OpenFrameでJCLを実行する方法を教えてください",
            "language": "ja",
            "max_products": 8,
            "include_all_databases": True
        }
    })


class ProductSearchResult(BaseModel):
    """Search result for a single product"""
    product: ProductId
    response: str = Field(default="")
    sources: ProductSources = Field(default_factory=ProductSources)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    search_time_ms: Optional[int] = None
    error: Optional[str] = None


class DeepSeekProgress(BaseModel):
    """DeepSeek progress update (for SSE streaming)"""
    type: str = Field(default="progress", description="Event type: progress, product_result, final")
    current_product: Optional[str] = None
    completed: int = 0
    total: int = 8
    percentage: float = 0.0
    product_result: Optional[ProductSearchResult] = None


class DeepSeekResponse(BaseModel):
    """DeepSeek comprehensive search response"""
    success: bool
    query: str
    summary: str = Field(
        ...,
        description="Synthesized response from all products"
    )
    product_results: List[ProductSearchResult] = Field(
        default_factory=list,
        description="Results from each product"
    )
    total_sources: int = Field(default=0)
    processing_time_ms: Optional[int] = None
    products_searched: int = Field(default=0)


# =============================================================================
# Health & Status Models
# =============================================================================

class AdapterStatus(BaseModel):
    """QLoRA adapter status"""
    name: str
    product: ProductId
    loaded: bool
    last_used: Optional[str] = None


class OpenFrameRAGHealth(BaseModel):
    """OpenFrame RAG service health"""
    available: bool
    message: str
    learning_llm_status: Dict[str, Any] = Field(default_factory=dict)
    vector_search_available: bool = False
    graph_search_available: bool = False
    adapters: List[AdapterStatus] = Field(default_factory=list)
    supported_products: List[str] = Field(default_factory=list)
