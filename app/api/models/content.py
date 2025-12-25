"""
Content generation models for AI-based content creation
AI 기반 콘텐츠 생성 모델
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Generated content types"""
    SUMMARY = "summary"
    FAQ = "faq"
    STUDY_GUIDE = "study_guide"
    BRIEFING = "briefing"
    TIMELINE = "timeline"
    TOC = "toc"
    KEY_TOPICS = "key_topics"


class ContentStatus(str, Enum):
    """Content generation status"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# Request models
class GenerateContentRequest(BaseModel):
    """Request to generate content from documents"""
    document_ids: list[str] = Field(..., min_length=1, description="Document IDs to analyze")
    content_type: ContentType = Field(..., description="Type of content to generate")
    language: str = Field(default="auto", description="Output language (auto, ko, en, ja)")
    options: Optional[dict] = Field(default=None, description="Type-specific options")


class GenerateSummaryOptions(BaseModel):
    """Options for summary generation"""
    length: str = Field(default="medium", description="Summary length: short, medium, long")
    focus_topics: Optional[list[str]] = Field(default=None, description="Topics to focus on")
    include_key_points: bool = Field(default=True, description="Include bullet points")


class GenerateFAQOptions(BaseModel):
    """Options for FAQ generation"""
    max_questions: int = Field(default=10, ge=3, le=30, description="Maximum number of Q&As")
    difficulty_level: str = Field(default="mixed", description="easy, medium, hard, mixed")


class GenerateStudyGuideOptions(BaseModel):
    """Options for study guide generation"""
    include_quiz: bool = Field(default=True, description="Include practice questions")
    include_definitions: bool = Field(default=True, description="Include key term definitions")
    include_summary: bool = Field(default=True, description="Include chapter summaries")


class GenerateBriefingOptions(BaseModel):
    """Options for briefing document generation"""
    audience: str = Field(default="general", description="Target audience: executive, technical, general")
    include_recommendations: bool = Field(default=True, description="Include action recommendations")
    max_pages: int = Field(default=2, ge=1, le=10, description="Maximum briefing pages")


class GenerateTimelineOptions(BaseModel):
    """Options for timeline generation"""
    granularity: str = Field(default="auto", description="Time granularity: day, month, year, auto")
    include_descriptions: bool = Field(default=True, description="Include event descriptions")


class GenerateTOCOptions(BaseModel):
    """Options for table of contents generation"""
    max_depth: int = Field(default=3, ge=1, le=5, description="Maximum heading depth")
    include_page_refs: bool = Field(default=True, description="Include page references")


# Response models
class SummaryContent(BaseModel):
    """Generated summary content"""
    title: str
    overview: str
    key_points: list[str] = Field(default_factory=list)
    detailed_summary: str
    word_count: int


class FAQItem(BaseModel):
    """Single FAQ item"""
    question: str
    answer: str
    difficulty: str = "medium"
    related_section: Optional[str] = None
    source_refs: list[str] = Field(default_factory=list)


class FAQContent(BaseModel):
    """Generated FAQ content"""
    title: str
    description: str
    questions: list[FAQItem]
    categories: list[str] = Field(default_factory=list)


class StudyGuideSection(BaseModel):
    """Study guide section"""
    title: str
    summary: str
    key_concepts: list[str]
    definitions: dict[str, str] = Field(default_factory=dict)


class QuizQuestion(BaseModel):
    """Quiz question for study guide"""
    question: str
    options: list[str] = Field(default_factory=list)
    correct_answer: str
    explanation: str


class StudyGuideContent(BaseModel):
    """Generated study guide content"""
    title: str
    learning_objectives: list[str]
    sections: list[StudyGuideSection]
    quiz_questions: list[QuizQuestion] = Field(default_factory=list)
    review_summary: str


class BriefingSection(BaseModel):
    """Briefing document section"""
    heading: str
    content: str
    bullet_points: list[str] = Field(default_factory=list)


class BriefingContent(BaseModel):
    """Generated briefing document"""
    title: str
    executive_summary: str
    sections: list[BriefingSection]
    recommendations: list[str] = Field(default_factory=list)
    conclusion: str


class TimelineEvent(BaseModel):
    """Timeline event"""
    date: str
    title: str
    description: str
    category: Optional[str] = None
    importance: str = "medium"  # low, medium, high


class TimelineContent(BaseModel):
    """Generated timeline"""
    title: str
    description: str
    date_range: dict[str, str]  # start, end
    events: list[TimelineEvent]
    summary: str


class TOCItem(BaseModel):
    """Table of contents item"""
    level: int
    title: str
    page: Optional[int] = None
    children: list["TOCItem"] = Field(default_factory=list)


class TOCContent(BaseModel):
    """Generated table of contents"""
    title: str
    items: list[TOCItem]
    total_sections: int
    document_title: str


class KeyTopic(BaseModel):
    """Key topic extracted from documents"""
    topic: str
    relevance_score: float
    description: str
    related_topics: list[str] = Field(default_factory=list)
    document_refs: list[str] = Field(default_factory=list)


class KeyTopicsContent(BaseModel):
    """Generated key topics"""
    title: str
    topics: list[KeyTopic]
    topic_relationships: list[dict] = Field(default_factory=list)


# Generic content wrapper
class GeneratedContent(BaseModel):
    """Generated content wrapper"""
    id: str
    content_type: ContentType
    status: ContentStatus
    document_ids: list[str]
    language: str
    content: Optional[dict] = None  # Type-specific content
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    generation_time_seconds: Optional[float] = None


class ContentListItem(BaseModel):
    """Content list item for listing generated contents"""
    id: str
    content_type: ContentType
    status: ContentStatus
    title: str
    document_count: int
    created_at: datetime


class GenerateContentResponse(BaseModel):
    """Response for content generation request"""
    content_id: str
    content_type: ContentType
    status: ContentStatus
    message: str


class ContentDetailResponse(BaseModel):
    """Detailed content response"""
    id: str
    content_type: ContentType
    status: ContentStatus
    document_ids: list[str]
    language: str
    content: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
