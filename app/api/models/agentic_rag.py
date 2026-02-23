"""
Agentic RAG Models

제품별 Agent 기반 RAG 시스템용 Pydantic 모델
다단계 질문 라우터, 정형/비정형 응답, 사후 검증을 지원합니다.

NOTE: ProductId enum 대신 str을 사용하여 동적 제품을 지원합니다.
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from .openframe_rag import ConfidenceLevel, ChatMessage, ProductSources


# =============================================================================
# Enums
# =============================================================================

class QueryType(str, Enum):
    """질문 유형"""
    COMMAND = "command"
    ERROR_CODE = "error_code"
    PARAMETER = "parameter"
    CONFIG = "config"
    FREEFORM = "freeform"


class VerificationLevel(str, Enum):
    """신뢰도 검증 등급"""
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


class RouterDecision(str, Enum):
    """라우터 판정 결과"""
    CONFIRMED = "confirmed"
    CLARIFICATION_NEEDED = "clarification_needed"
    NO_MATCH = "no_match"


class AgentMode(str, Enum):
    """Agent 실행 모드"""
    RAG = "rag"
    CODE = "code"
    PLANNER = "planner"
    AUTO = "auto"
    SPECIAL = "special"


# =============================================================================
# Router Models
# =============================================================================

class ClarificationCandidate(BaseModel):
    """되묻기 후보 제품"""
    product: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(description="매칭 이유")
    matched_keywords: List[str] = Field(default_factory=list)


class RouterResult(BaseModel):
    """라우터 분류 결과"""
    decision: RouterDecision
    product: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    candidates: List[ClarificationCandidate] = Field(default_factory=list)
    all_scores: Dict[str, float] = Field(default_factory=dict)


# =============================================================================
# Verification Models
# =============================================================================

class VerifiedSentence(BaseModel):
    """검증된 문장"""
    text: str
    level: VerificationLevel
    similarity: float = Field(ge=0.0, le=1.0)
    source_chunk: Optional[str] = None
    source_doc: Optional[str] = None


# =============================================================================
# Request Models
# =============================================================================

class AgenticRAGRequest(BaseModel):
    """Agentic RAG 채팅 요청"""
    message: str = Field(..., min_length=1, max_length=8000)
    product: str = Field(default="auto")
    products: Optional[List[str]] = Field(
        default=None,
        description="복수 제품 선택. 비어있지 않으면 해당 제품들을 우선 검색. product 필드보다 우선"
    )
    history: Optional[List[ChatMessage]] = None
    file_content: Optional[str] = None
    language: Optional[str] = Field(default="ja")
    selected_product: Optional[str] = Field(
        default=None,
        description="되묻기에서 사용자가 선택한 제품"
    )
    agent_mode: AgentMode = Field(
        default=AgentMode.RAG,
        description="Agent 실행 모드: rag(기본), code(코드 생성), planner(플랜 생성), auto(자동 감지)"
    )
    # Long-term Memory 컨텍스트 (서버에서 주입)
    user_id: Optional[str] = Field(default=None, exclude=True)
    session_id: Optional[str] = Field(default=None, exclude=True)

    @property
    def effective_products(self) -> List[str]:
        """우선순위: selected_product > products > product"""
        if self.selected_product:
            return [self.selected_product]
        if self.products:
            return self.products
        if self.product != "auto":
            return [self.product]
        return []  # auto mode

    @property
    def is_auto_mode(self) -> bool:
        return len(self.effective_products) == 0

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "tjesmgr BOOTの使い方を教えてください",
            "product": "auto",
            "language": "ja"
        }
    })


# =============================================================================
# Response Models
# =============================================================================

class AgenticRAGResponse(BaseModel):
    """Agentic RAG 채팅 응답"""
    success: bool
    response: str
    product: str
    query_type: QueryType
    router_result: RouterResult
    verification: Optional[List[VerifiedSentence]] = None
    sources: ProductSources = Field(default_factory=ProductSources)
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    processing_time_ms: Optional[int] = None


class AgenticRAGHealth(BaseModel):
    """서비스 상태"""
    available: bool
    message: str
    agents: Dict[str, bool] = Field(default_factory=dict)
    knowledge_store_status: Dict[str, int] = Field(default_factory=dict)
    supported_products: List[str] = Field(default_factory=list)
