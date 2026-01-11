"""
Query Log Models for FAQ System

Models for storing AI agent queries and generating dynamic FAQ items.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field


class FAQSourceType(str, Enum):
    """Source type for FAQ items"""
    STATIC = "static"      # Hardcoded in i18n files
    DYNAMIC = "dynamic"    # Auto-generated from popular queries
    CURATED = "curated"    # Admin-edited from dynamic queries


class AgentTypeEnum(str, Enum):
    """Agent types for query classification"""
    RAG = "rag"
    IMS = "ims"
    VISION = "vision"
    CODE = "code"
    PLANNER = "planner"


class IntentTypeEnum(str, Enum):
    """Intent types from query classification"""
    SEARCH = "search"
    LIST_ALL = "list_all"
    DETAIL = "detail"
    ANALYZE = "analyze"
    UNKNOWN = "unknown"


# ============================================
# Request/Response Models for API
# ============================================

class QueryLogCreate(BaseModel):
    """Data for creating a query log entry"""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[UUID] = None
    query_text: str
    agent_type: str
    intent_type: Optional[str] = None
    category: Optional[str] = None
    language: str = "auto"
    execution_time_ms: Optional[int] = None
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    response_summary: Optional[str] = None


class QueryLogResponse(BaseModel):
    """Query log entry response"""
    id: UUID
    user_id: Optional[str]
    query_text: str
    agent_type: str
    intent_type: Optional[str]
    category: Optional[str]
    execution_time_ms: Optional[int]
    success: bool
    created_at: datetime


class QueryAggregate(BaseModel):
    """Aggregated query statistics"""
    id: UUID
    query_normalized: str
    representative_query: str
    representative_answer: Optional[str] = None
    frequency_count: int
    last_asked_at: datetime
    first_asked_at: datetime
    unique_users_count: int
    agent_type: Optional[str] = None
    category: Optional[str] = None
    popularity_score: float
    is_faq_eligible: bool


class FAQItem(BaseModel):
    """FAQ item for display"""
    id: UUID
    source_type: FAQSourceType
    question: str  # Localized based on request language
    answer: str    # Localized based on request language
    category: str
    tags: List[str] = Field(default_factory=list)
    view_count: int = 0
    helpful_count: int = 0
    not_helpful_count: int = 0
    is_pinned: bool = False
    created_at: datetime


class FAQItemCreate(BaseModel):
    """Data for creating a FAQ item"""
    source_type: FAQSourceType = FAQSourceType.CURATED
    query_aggregate_id: Optional[UUID] = None
    question_en: Optional[str] = None
    question_ko: Optional[str] = None
    question_ja: Optional[str] = None
    answer_en: Optional[str] = None
    answer_ko: Optional[str] = None
    answer_ja: Optional[str] = None
    category: str
    tags: List[str] = Field(default_factory=list)
    display_order: int = 0
    is_active: bool = True
    is_pinned: bool = False


class FAQItemUpdate(BaseModel):
    """Data for updating a FAQ item"""
    question_en: Optional[str] = None
    question_ko: Optional[str] = None
    question_ja: Optional[str] = None
    answer_en: Optional[str] = None
    answer_ko: Optional[str] = None
    answer_ja: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    is_pinned: Optional[bool] = None


class FAQFeedbackRequest(BaseModel):
    """Request for FAQ feedback"""
    is_helpful: bool


# ============================================
# Response Models for API Endpoints
# ============================================

class PopularQueriesResponse(BaseModel):
    """Response for popular queries endpoint"""
    status: str = "success"
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "queries": [],
                    "total": 0,
                    "period_days": 30
                }
            }
        }


class FAQListResponse(BaseModel):
    """Response for FAQ list endpoint"""
    status: str = "success"
    data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "items": [],
                    "total": 0,
                    "has_more": False
                }
            }
        }


class FAQCategoryResponse(BaseModel):
    """Response for FAQ categories endpoint"""
    status: str = "success"
    data: Dict[str, Any] = Field(default_factory=dict)


class FAQCategory(BaseModel):
    """FAQ category with count"""
    id: str
    name: str
    name_ko: Optional[str] = None
    name_ja: Optional[str] = None
    count: int = 0


# ============================================
# Statistics Models
# ============================================

class QueryStatistics(BaseModel):
    """Query statistics for admin dashboard"""
    total_queries: int = 0
    queries_today: int = 0
    queries_this_week: int = 0
    unique_users: int = 0
    avg_execution_time_ms: float = 0.0
    success_rate: float = 0.0
    top_categories: List[Dict[str, Any]] = Field(default_factory=list)
    top_agent_types: List[Dict[str, Any]] = Field(default_factory=list)


class FAQStatistics(BaseModel):
    """FAQ statistics for admin dashboard"""
    total_faq_items: int = 0
    dynamic_faq_count: int = 0
    static_faq_count: int = 0
    total_views: int = 0
    total_helpful: int = 0
    total_not_helpful: int = 0
    helpfulness_ratio: float = 0.0
