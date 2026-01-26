"""
User Feedback Models for RAG Response Quality

Provides models for:
- Response feedback (👍/👎 + detailed categories)
- Human-in-the-Loop learning signals
- Response consistency tracking
- Citation/source feedback
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ============================================
# Enums
# ============================================

class FeedbackType(str, Enum):
    """Quick feedback type"""
    THUMBS_UP = "thumbs_up"      # 👍
    THUMBS_DOWN = "thumbs_down"  # 👎


class FeedbackCategory(str, Enum):
    """Detailed feedback categories for negative feedback"""
    INCORRECT_INFO = "incorrect_info"       # 잘못된 정보
    INCOMPLETE = "incomplete"               # 불완전한 답변
    IRRELEVANT = "irrelevant"               # 관련 없는 답변
    OUTDATED = "outdated"                   # 오래된 정보
    HALLUCINATION = "hallucination"         # 환각 (없는 내용 생성)
    POOR_CITATION = "poor_citation"         # 출처 부정확
    TOO_VERBOSE = "too_verbose"             # 너무 장황함
    TOO_BRIEF = "too_brief"                 # 너무 간단함
    WRONG_LANGUAGE = "wrong_language"       # 잘못된 언어
    FORMATTING = "formatting"               # 형식 문제
    OTHER = "other"                         # 기타


class PositiveFeedbackCategory(str, Enum):
    """Categories for positive feedback"""
    ACCURATE = "accurate"                   # 정확한 정보
    HELPFUL = "helpful"                     # 도움이 됨
    WELL_CITED = "well_cited"               # 출처가 명확함
    COMPREHENSIVE = "comprehensive"         # 포괄적인 답변
    CONCISE = "concise"                     # 간결함
    WELL_FORMATTED = "well_formatted"       # 형식이 좋음


class FeedbackStatus(str, Enum):
    """Processing status for feedback"""
    PENDING = "pending"           # 처리 대기
    REVIEWED = "reviewed"         # 검토 완료
    APPLIED = "applied"           # 학습에 적용됨
    DISMISSED = "dismissed"       # 무시됨


class CitationFeedbackType(str, Enum):
    """Feedback type for individual citations"""
    HELPFUL = "helpful"           # 도움이 되는 출처
    UNHELPFUL = "unhelpful"       # 도움이 안 되는 출처
    INCORRECT = "incorrect"       # 잘못된 출처
    OUTDATED = "outdated"         # 오래된 출처


# ============================================
# Feedback Request Models
# ============================================

class QuickFeedbackRequest(BaseModel):
    """Request for quick thumbs up/down feedback"""
    message_id: str = Field(..., description="대상 메시지 ID (UUID 또는 클라이언트 생성 ID)")
    feedback_type: FeedbackType = Field(..., description="👍 또는 👎")
    query: Optional[str] = Field(None, description="사용자 질문 (학습용 스냅샷)")
    answer: Optional[str] = Field(None, description="어시스턴트 답변 (학습용 스냅샷)")
    conversation_id: Optional[str] = Field(None, description="대화 ID")

    model_config = {"json_schema_extra": {
        "example": {
            "message_id": "msg-1706123456789-assistant",
            "feedback_type": "thumbs_up",
            "query": "BMS란 무엇인가요?",
            "answer": "BMS는 Battery Management System의 약자로...",
            "conversation_id": "conv-123"
        }
    }}


class DetailedFeedbackRequest(BaseModel):
    """Request for detailed feedback with categories"""
    message_id: str = Field(..., description="대상 메시지 ID (UUID 또는 클라이언트 생성 ID)")
    feedback_type: FeedbackType = Field(..., description="👍 또는 👎")
    categories: List[str] = Field(
        default_factory=list,
        description="피드백 카테고리 목록"
    )
    comment: Optional[str] = Field(
        None,
        max_length=2000,
        description="추가 코멘트"
    )
    expected_answer: Optional[str] = Field(
        None,
        max_length=5000,
        description="기대했던 답변 (HITL 학습용)"
    )

    @field_validator('categories')
    @classmethod
    def validate_categories(cls, v: List[str]) -> List[str]:
        """Validate category values"""
        valid_negative = {c.value for c in FeedbackCategory}
        valid_positive = {c.value for c in PositiveFeedbackCategory}
        valid_all = valid_negative | valid_positive

        for cat in v:
            if cat not in valid_all:
                raise ValueError(f"Invalid category: {cat}")
        return v


class CitationFeedbackRequest(BaseModel):
    """Feedback for individual citation/source"""
    message_id: UUID = Field(..., description="메시지 ID")
    source_index: int = Field(..., ge=0, description="소스 인덱스")
    feedback_type: CitationFeedbackType = Field(..., description="출처 피드백 타입")
    comment: Optional[str] = Field(None, max_length=500)


class BulkCitationFeedback(BaseModel):
    """Bulk feedback for multiple citations"""
    message_id: UUID
    feedbacks: List[Dict[str, Any]] = Field(
        ...,
        description="[{source_index, feedback_type, comment?}]"
    )


# ============================================
# Response Models
# ============================================

class FeedbackResponse(BaseModel):
    """Response after submitting feedback"""
    feedback_id: UUID
    message_id: str
    feedback_type: FeedbackType
    categories: List[str] = Field(default_factory=list)
    status: FeedbackStatus = FeedbackStatus.PENDING
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackSummary(BaseModel):
    """Summary of feedback for a message"""
    message_id: str
    thumbs_up_count: int = 0
    thumbs_down_count: int = 0
    total_count: int = 0
    positive_ratio: float = 0.0
    top_categories: List[Dict[str, Any]] = Field(default_factory=list)  # [{category: str, count: int}]
    avg_score: Optional[float] = None


class FeedbackDetail(BaseModel):
    """Full feedback detail"""
    feedback_id: UUID
    message_id: str
    conversation_id: Optional[str] = None
    user_id: str
    feedback_type: FeedbackType
    categories: List[str] = Field(default_factory=list)
    comment: Optional[str] = None
    expected_answer: Optional[str] = None
    status: FeedbackStatus
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    # Context for HITL
    query: Optional[str] = None
    answer: Optional[str] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = {"from_attributes": True}


# ============================================
# HITL (Human-in-the-Loop) Models
# ============================================

class HITLSignal(BaseModel):
    """Learning signal from human feedback"""
    query: str
    original_answer: str
    expected_answer: Optional[str] = None
    feedback_type: FeedbackType
    categories: List[str] = Field(default_factory=list)
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    source_feedbacks: List[Dict[str, Any]] = Field(default_factory=list)

    # Computed signals
    relevance_adjustment: float = 0.0  # -1.0 to 1.0
    source_quality_scores: Dict[str, float] = Field(default_factory=dict)


class ReRankingUpdate(BaseModel):
    """Re-ranking adjustment based on feedback"""
    document_id: str
    chunk_id: Optional[str] = None
    query_pattern: str  # Generalized query pattern
    adjustment_score: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    feedback_count: int = 1


class HITLStats(BaseModel):
    """Statistics for HITL learning"""
    total_signals: int = 0
    positive_signals: int = 0
    negative_signals: int = 0
    applied_updates: int = 0
    pending_updates: int = 0
    avg_adjustment: float = 0.0
    top_improved_docs: List[Dict[str, Any]] = Field(default_factory=list)
    top_issues: List[Dict[str, int]] = Field(default_factory=list)


# ============================================
# Response Consistency Models
# ============================================

class QueryAnswerPair(BaseModel):
    """Cached query-answer pair for consistency"""
    query_hash: str
    query: str
    answer: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    feedback_score: float = 0.0
    usage_count: int = 1
    last_used_at: datetime
    created_at: datetime

    # Consistency metadata
    answer_variations: int = 1
    consistency_score: float = 1.0


class ConsistencyCheckRequest(BaseModel):
    """Request to check response consistency"""
    query: str
    threshold: float = Field(default=0.85, ge=0.0, le=1.0)


class ConsistencyCheckResponse(BaseModel):
    """Response from consistency check"""
    has_similar_query: bool
    similar_query: Optional[str] = None
    cached_answer: Optional[str] = None
    similarity_score: float = 0.0
    recommendation: str = "generate_new"  # use_cached, generate_new, review_needed


class ConsistencyStats(BaseModel):
    """Statistics for response consistency"""
    total_cached_pairs: int = 0
    cache_hit_rate: float = 0.0
    avg_consistency_score: float = 0.0
    inconsistent_queries: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================
# Citation Enhancement Models
# ============================================

class EnhancedCitation(BaseModel):
    """Enhanced citation with feedback integration"""
    source_index: int
    doc_id: Optional[str] = None
    doc_name: str
    chunk_id: Optional[str] = None
    content_preview: str = Field(..., max_length=500)
    full_content: Optional[str] = None
    score: float = Field(..., ge=0.0, le=1.0)

    # Source metadata
    source_type: str = "vector"
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    source_url: Optional[str] = None

    # Feedback-based adjustments
    feedback_score: float = 0.0  # Average user rating
    helpful_count: int = 0
    unhelpful_count: int = 0

    # Display helpers
    citation_text: str = ""  # e.g., "[1] document.pdf, p.5"
    highlight_ranges: List[Dict[str, int]] = Field(default_factory=list)


class CitationDisplayConfig(BaseModel):
    """Configuration for citation display"""
    show_page_numbers: bool = True
    show_section_titles: bool = True
    show_relevance_scores: bool = False
    show_feedback_scores: bool = True
    max_preview_length: int = 200
    highlight_matched_terms: bool = True
    group_by_document: bool = False


# ============================================
# Aggregated Stats Models
# ============================================

class UserFeedbackStats(BaseModel):
    """Aggregated feedback statistics"""
    period_start: datetime
    period_end: datetime

    # Overall stats
    total_feedbacks: int = 0
    thumbs_up: int = 0
    thumbs_down: int = 0
    satisfaction_rate: float = 0.0

    # Category breakdown
    category_distribution: Dict[str, int] = Field(default_factory=dict)

    # Trend
    daily_trend: List[Dict[str, Any]] = Field(default_factory=list)

    # Top issues
    top_negative_categories: List[Dict[str, int]] = Field(default_factory=list)
    top_positive_categories: List[Dict[str, int]] = Field(default_factory=list)

    # HITL metrics
    hitl_signals_generated: int = 0
    hitl_updates_applied: int = 0


class FeedbackAnalyticsRequest(BaseModel):
    """Request for feedback analytics"""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    user_id: Optional[str] = None
    conversation_id: Optional[UUID] = None
    include_hitl_stats: bool = True
    include_consistency_stats: bool = True
