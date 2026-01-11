"""
Knowledge Article models for the Knowledge Management System
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class KnowledgeStatus(str, Enum):
    """Knowledge article workflow status"""
    DRAFT = "draft"           # Being written
    PENDING = "pending"       # Submitted for review
    IN_REVIEW = "in_review"   # Under review
    APPROVED = "approved"     # Review passed
    REJECTED = "rejected"     # Review failed
    PUBLISHED = "published"   # Publicly available


class KnowledgeCategory(str, Enum):
    """Pre-defined knowledge categories"""
    TECHNICAL = "technical"           # Technical documentation
    PROCESS = "process"               # Business processes
    GUIDELINE = "guideline"           # Guidelines and standards
    TROUBLESHOOTING = "troubleshooting"  # Problem solving
    BEST_PRACTICE = "best_practice"   # Best practices
    TUTORIAL = "tutorial"             # How-to guides
    FAQ = "faq"                       # Frequently asked questions
    ANNOUNCEMENT = "announcement"     # Announcements
    RESEARCH = "research"             # Research and analysis
    OTHER = "other"                   # Other


class SupportedLanguage(str, Enum):
    """Supported languages for i18n"""
    KOREAN = "ko"
    JAPANESE = "ja"
    ENGLISH = "en"


# Category display names for i18n
CATEGORY_NAMES = {
    KnowledgeCategory.TECHNICAL: {
        "ko": "기술 문서",
        "ja": "技術文書",
        "en": "Technical Documentation"
    },
    KnowledgeCategory.PROCESS: {
        "ko": "업무 프로세스",
        "ja": "業務プロセス",
        "en": "Business Process"
    },
    KnowledgeCategory.GUIDELINE: {
        "ko": "가이드라인",
        "ja": "ガイドライン",
        "en": "Guideline"
    },
    KnowledgeCategory.TROUBLESHOOTING: {
        "ko": "문제 해결",
        "ja": "トラブルシューティング",
        "en": "Troubleshooting"
    },
    KnowledgeCategory.BEST_PRACTICE: {
        "ko": "모범 사례",
        "ja": "ベストプラクティス",
        "en": "Best Practice"
    },
    KnowledgeCategory.TUTORIAL: {
        "ko": "튜토리얼",
        "ja": "チュートリアル",
        "en": "Tutorial"
    },
    KnowledgeCategory.FAQ: {
        "ko": "자주 묻는 질문",
        "ja": "よくある質問",
        "en": "FAQ"
    },
    KnowledgeCategory.ANNOUNCEMENT: {
        "ko": "공지사항",
        "ja": "お知らせ",
        "en": "Announcement"
    },
    KnowledgeCategory.RESEARCH: {
        "ko": "연구 및 분석",
        "ja": "研究・分析",
        "en": "Research & Analysis"
    },
    KnowledgeCategory.OTHER: {
        "ko": "기타",
        "ja": "その他",
        "en": "Other"
    }
}


class KnowledgeTranslation(BaseModel):
    """Translated content for a knowledge article"""
    language: SupportedLanguage
    title: str
    content: str  # HTML/Markdown content
    summary: Optional[str] = None
    translated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_auto_translated: bool = False


class ReviewComment(BaseModel):
    """Review comment from reviewer"""
    id: str
    reviewer_id: str
    reviewer_name: str
    comment: str
    action: str  # "approve", "reject", "request_changes"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeArticle(BaseModel):
    """Knowledge article main model"""
    id: str

    # Original content (primary language)
    title: str
    content: str  # HTML/Markdown content
    summary: Optional[str] = None
    primary_language: SupportedLanguage = SupportedLanguage.KOREAN

    # Metadata
    category: KnowledgeCategory
    tags: List[str] = []

    # Author info
    author_id: str
    author_name: str
    author_department: Optional[str] = None

    # Workflow status
    status: KnowledgeStatus = KnowledgeStatus.DRAFT

    # Review info
    reviewer_id: Optional[str] = None
    reviewer_name: Optional[str] = None
    review_comments: List[ReviewComment] = []
    reviewed_at: Optional[datetime] = None

    # Translations (ko, ja, en)
    translations: Dict[str, KnowledgeTranslation] = {}

    # Metrics
    view_count: int = 0
    recommendation_count: int = 0

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: Optional[datetime] = None
    published_at: Optional[datetime] = None

    # Attachments
    attachments: List[str] = []  # File IDs

    # Related articles
    related_article_ids: List[str] = []

    class Config:
        json_schema_extra = {
            "example": {
                "id": "ka_abc123",
                "title": "GPU 기반 RAG 시스템 구축 가이드",
                "content": "<h1>개요</h1><p>이 문서는...</p>",
                "summary": "GPU를 활용한 RAG 시스템 구축 방법을 설명합니다.",
                "category": "technical",
                "tags": ["gpu", "rag", "ai"],
                "author_id": "user_123",
                "author_name": "홍길동",
                "status": "published"
            }
        }


class Recommendation(BaseModel):
    """User recommendation for a knowledge article"""
    id: str
    knowledge_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Request/Response models

class CreateKnowledgeRequest(BaseModel):
    """Create knowledge article request"""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    summary: Optional[str] = Field(None, max_length=500)
    category: KnowledgeCategory
    tags: List[str] = []
    primary_language: SupportedLanguage = SupportedLanguage.KOREAN
    attachments: List[str] = []

    class Config:
        json_schema_extra = {
            "example": {
                "title": "새로운 지식 문서",
                "content": "<h1>내용</h1><p>본문...</p>",
                "summary": "문서 요약",
                "category": "technical",
                "tags": ["태그1", "태그2"]
            }
        }


class UpdateKnowledgeRequest(BaseModel):
    """Update knowledge article request"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = None
    summary: Optional[str] = Field(None, max_length=500)
    category: Optional[KnowledgeCategory] = None
    tags: Optional[List[str]] = None
    attachments: Optional[List[str]] = None


class SubmitReviewRequest(BaseModel):
    """Submit knowledge for review"""
    pass  # No additional fields needed


class ReviewActionRequest(BaseModel):
    """Reviewer action on knowledge article"""
    action: str = Field(..., pattern="^(approve|reject|request_changes)$")
    comment: str = Field(..., min_length=1, max_length=1000)


class KnowledgeSearchRequest(BaseModel):
    """Search knowledge articles"""
    query: Optional[str] = None
    category: Optional[KnowledgeCategory] = None
    status: Optional[KnowledgeStatus] = None
    author_id: Optional[str] = None
    tags: Optional[List[str]] = None
    language: SupportedLanguage = SupportedLanguage.KOREAN
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


class KnowledgeListResponse(BaseModel):
    """Knowledge list response"""
    articles: List[KnowledgeArticle]
    total: int
    page: int
    limit: int


class KnowledgeDetailResponse(BaseModel):
    """Knowledge detail response with full translation"""
    article: KnowledgeArticle
    current_translation: Optional[KnowledgeTranslation] = None


class TopContributorResponse(BaseModel):
    """Top knowledge contributors"""
    user_id: str
    username: str
    department: Optional[str]
    total_recommendations: int
    article_count: int
    rank: int


class TopContributorsListResponse(BaseModel):
    """Top contributors list"""
    contributors: List[TopContributorResponse]
    period: str  # "all_time", "monthly", "weekly"


class RecommendationResponse(BaseModel):
    """Recommendation action response"""
    knowledge_id: str
    recommendation_count: int
    user_recommended: bool
