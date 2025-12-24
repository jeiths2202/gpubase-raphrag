"""
History and Conversation Pydantic models
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from .query import SourceInfo, QueryAnalysis, StrategyType, LanguageType


class HistoryListItem(BaseModel):
    """Query history list item"""
    id: str
    conversation_id: Optional[str] = None
    question: str
    answer_preview: str = Field(..., description="Truncated answer preview")
    strategy: StrategyType
    language: LanguageType
    sources_count: int = 0
    processing_time_ms: int
    created_at: datetime


class HistoryDetail(BaseModel):
    """Query history detail"""
    id: str
    conversation_id: Optional[str] = None
    question: str
    answer: str
    strategy: StrategyType
    language: LanguageType
    sources: list[SourceInfo] = Field(default_factory=list)
    query_analysis: Optional[QueryAnalysis] = None
    processing_time_ms: int
    created_at: datetime


class ConversationListItem(BaseModel):
    """Conversation list item"""
    id: str
    title: str
    queries_count: int = 0
    last_query_at: Optional[datetime] = None
    created_at: datetime


class ConversationCreate(BaseModel):
    """Create conversation request"""
    title: str = Field(..., min_length=1, max_length=200)


class ConversationDetail(ConversationListItem):
    """Conversation detail with history"""
    history: list[HistoryListItem] = Field(default_factory=list)
