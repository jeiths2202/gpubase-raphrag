"""
RAG Configuration & Governance Models
Pydantic models for RAG profiles, experiments, and metrics
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID


# =============================================================================
# Enums
# =============================================================================

class ChunkStrategy(str, Enum):
    """Document chunking strategies"""
    SEMANTIC = "semantic"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    HEADER = "header"
    FIXED = "fixed"


class RetrievalStrategy(str, Enum):
    """RAG retrieval strategies"""
    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"


class OCREngine(str, Enum):
    """OCR engine options for image processing"""
    TESSERACT = "tesseract"
    PADDLE = "paddle"
    VISION_LLM = "vision-llm"


class ExperimentStatus(str, Enum):
    """A/B experiment lifecycle status"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class EmbeddingStatus(str, Enum):
    """Document embedding status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# =============================================================================
# RAG Profile Models
# =============================================================================

class ChunkingConfig(BaseModel):
    """Chunking configuration section"""
    strategy: ChunkStrategy = ChunkStrategy.SEMANTIC
    chunk_size: int = Field(default=512, ge=100, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=500)
    min_chunk_size: int = Field(default=100, ge=50, le=1000)
    max_chunk_size: int = Field(default=1000, ge=200, le=4000)
    language: str = Field(default="auto", pattern=r"^(auto|ko|en|ja|zh)$")


class EmbeddingConfig(BaseModel):
    """Embedding configuration section"""
    model: str = Field(default="nv-embedqa-mistral-7b-v2")
    dimension: int = Field(default=1024, ge=128, le=8192)
    normalize: bool = True
    batch_size: int = Field(default=64, ge=1, le=256)


class ImageIngestionConfig(BaseModel):
    """Image/document ingestion configuration"""
    enabled: bool = True
    ocr_engine: OCREngine = OCREngine.VISION_LLM
    dpi: int = Field(default=300, ge=72, le=600)
    layout_analysis: bool = True
    caption_generation: bool = True
    chunk_strategy: str = Field(default="layout_block")


class RetrievalConfig(BaseModel):
    """Retrieval configuration section"""
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    hybrid_alpha: float = Field(default=0.5, ge=0.0, le=1.0, description="Vector weight in hybrid search")


class GenerationConfig(BaseModel):
    """LLM generation configuration"""
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=100, le=16384)


class RAGProfileBase(BaseModel):
    """Base RAG profile fields"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    space_id: Optional[str] = None
    project_id: Optional[str] = None


class RAGProfileCreate(RAGProfileBase):
    """Request model for creating a new RAG profile"""
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    image_ingestion: ImageIngestionConfig = Field(default_factory=ImageIngestionConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RAGProfileUpdate(BaseModel):
    """Request model for updating a RAG profile (creates new version)"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    chunking: Optional[ChunkingConfig] = None
    embedding: Optional[EmbeddingConfig] = None
    image_ingestion: Optional[ImageIngestionConfig] = None
    retrieval: Optional[RetrievalConfig] = None
    generation: Optional[GenerationConfig] = None
    is_active: Optional[bool] = None
    traffic_percentage: Optional[int] = Field(None, ge=0, le=100)
    metadata: Optional[Dict[str, Any]] = None


class RAGProfile(RAGProfileBase):
    """Full RAG profile response model"""
    id: UUID
    embedding_version: int
    is_active: bool
    traffic_percentage: int
    experiment_id: Optional[UUID] = None

    # Nested configurations
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    image_ingestion: ImageIngestionConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig

    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RAGProfileSummary(BaseModel):
    """Lightweight profile summary for lists"""
    id: UUID
    name: str
    description: Optional[str]
    space_id: Optional[str]
    embedding_version: int
    is_active: bool
    traffic_percentage: int
    retrieval_strategy: RetrievalStrategy
    chunk_size: int
    created_at: datetime


# =============================================================================
# A/B Experiment Models
# =============================================================================

class ExperimentVariant(BaseModel):
    """Experiment variant with traffic allocation"""
    profile_id: UUID
    profile_name: Optional[str] = None
    traffic_ratio: float = Field(..., ge=0.0, le=1.0)
    variant_name: Optional[str] = None


class ExperimentCreate(BaseModel):
    """Request model for creating an A/B experiment"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    space_id: Optional[str] = None
    baseline_profile_id: UUID
    variants: List[ExperimentVariant] = Field(..., min_length=1, max_length=5)


class ExperimentUpdate(BaseModel):
    """Request model for updating an experiment"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ExperimentStatus] = None
    variants: Optional[List[ExperimentVariant]] = None


class RAGExperiment(BaseModel):
    """Full experiment response model"""
    id: UUID
    name: str
    description: Optional[str]
    space_id: Optional[str]
    baseline_profile_id: UUID
    baseline_profile_name: Optional[str] = None
    variants: List[ExperimentVariant]
    status: ExperimentStatus
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    total_queries: int = 0
    created_by: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExperimentSummary(BaseModel):
    """Lightweight experiment summary for lists"""
    id: UUID
    name: str
    status: ExperimentStatus
    baseline_profile_name: str
    variant_count: int
    total_queries: int
    started_at: Optional[datetime]
    created_at: datetime


# =============================================================================
# Metrics Models
# =============================================================================

class DailyMetrics(BaseModel):
    """Daily aggregated metrics for a profile in an experiment"""
    metric_date: str  # YYYY-MM-DD
    query_count: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_latency_ms: Optional[int] = None
    avg_similarity_score: Optional[float] = None
    retrieval_hit_rate: Optional[float] = None
    total_tokens: int = 0
    estimated_cost: float = 0.0
    thumbs_up: int = 0
    thumbs_down: int = 0
    satisfaction_rate: Optional[float] = None


class ProfileMetricsSummary(BaseModel):
    """Aggregated metrics summary for a profile"""
    profile_id: UUID
    profile_name: str
    total_queries: int
    success_rate: float
    avg_latency_ms: int
    avg_similarity_score: float
    retrieval_hit_rate: float
    total_tokens: int
    estimated_cost: float
    thumbs_up: int
    thumbs_down: int
    satisfaction_rate: float  # (up - down) / (up + down) or 0


class ExperimentMetricsComparison(BaseModel):
    """Metrics comparison between experiment variants"""
    experiment_id: UUID
    experiment_name: str
    period_days: int
    baseline: ProfileMetricsSummary
    variants: List[ProfileMetricsSummary]
    winner_profile_id: Optional[UUID] = None
    winner_confidence: Optional[float] = None  # Statistical significance


# =============================================================================
# Document-Profile Assignment Models
# =============================================================================

class DocumentProfileAssignment(BaseModel):
    """Document-level profile assignment"""
    document_id: str
    profile_id: UUID
    profile_name: Optional[str] = None
    embedding_version: int
    embedding_status: EmbeddingStatus
    embedding_started_at: Optional[datetime] = None
    embedding_completed_at: Optional[datetime] = None
    created_at: datetime


class AssignProfileRequest(BaseModel):
    """Request to assign a profile to documents"""
    document_ids: List[str] = Field(..., min_length=1, max_length=100)
    profile_id: UUID
    trigger_reembedding: bool = Field(default=False, description="Start re-embedding immediately")


# =============================================================================
# Response Models
# =============================================================================

class RAGProfileListResponse(BaseModel):
    """Response for profile list endpoint"""
    profiles: List[RAGProfileSummary]
    total_count: int
    active_count: int


class ExperimentListResponse(BaseModel):
    """Response for experiment list endpoint"""
    experiments: List[ExperimentSummary]
    total_count: int
    active_count: int


class RAGConfigOverview(BaseModel):
    """Dashboard overview of RAG configuration"""
    total_profiles: int
    active_profiles: int
    total_experiments: int
    active_experiments: int
    documents_with_custom_profile: int
    pending_reembedding: int
    recent_profiles: List[RAGProfileSummary]
    recent_experiments: List[ExperimentSummary]
