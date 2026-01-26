"""
Statistics Pydantic models
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DatabaseStats(BaseModel):
    """Database statistics"""
    documents_count: int = 0
    chunks_count: int = 0
    entities_count: int = 0
    relationships_count: int = 0


class EmbeddingStats(BaseModel):
    """Embedding statistics"""
    total_chunks: int = 0
    with_embedding: int = 0
    without_embedding: int = 0
    coverage_percent: float = Field(ge=0.0, le=100.0, default=0.0)
    dimension: int = 4096


class StrategyDistribution(BaseModel):
    """Query strategy distribution"""
    vector: int = 0
    graph: int = 0
    hybrid: int = 0
    code: int = 0


class QueryStats(BaseModel):
    """Query statistics"""
    total_queries: int = 0
    today_queries: int = 0
    avg_response_time_ms: float = 0.0
    strategy_distribution: StrategyDistribution = Field(default_factory=StrategyDistribution)


class StorageStats(BaseModel):
    """Storage statistics"""
    neo4j_size_mb: float = 0.0
    documents_size_mb: float = 0.0


class SystemStats(BaseModel):
    """Complete system statistics"""
    database: DatabaseStats = Field(default_factory=DatabaseStats)
    embeddings: EmbeddingStats = Field(default_factory=EmbeddingStats)
    queries: QueryStats = Field(default_factory=QueryStats)
    storage: StorageStats = Field(default_factory=StorageStats)


class TimelineEntry(BaseModel):
    """Query timeline entry"""
    date: str
    queries_count: int = 0
    avg_response_time_ms: float = 0.0
    by_strategy: StrategyDistribution = Field(default_factory=StrategyDistribution)


class TopQuery(BaseModel):
    """Top queried question"""
    question: str
    count: int


class QueryStatsDetail(BaseModel):
    """Detailed query statistics"""
    period: str
    total_queries: int = 0
    avg_response_time_ms: float = 0.0
    timeline: list[TimelineEntry] = Field(default_factory=list)
    top_queries: list[TopQuery] = Field(default_factory=list)


class DocumentStatusDistribution(BaseModel):
    """Document status distribution"""
    ready: int = 0
    processing: int = 0
    error: int = 0


class LanguageDistribution(BaseModel):
    """Document language distribution"""
    ko: int = 0
    ja: int = 0
    en: int = 0


class DocumentStatsDetail(BaseModel):
    """Detailed document statistics"""
    total_documents: int = 0
    by_status: DocumentStatusDistribution = Field(default_factory=DocumentStatusDistribution)
    by_language: LanguageDistribution = Field(default_factory=LanguageDistribution)
    total_pages: int = 0
    total_chunks: int = 0
    avg_chunks_per_document: float = 0.0
