"""
Adaptive Chunk Models for PDF Structure-Preserving Embedding
PDF 구조 보존 임베딩을 위한 적응형 청크 모델

Supports semantic boundary-based chunking with hierarchical relationships.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    """Chunk content type classification"""
    TEXT_CHUNK = "TEXT_CHUNK"
    TABLE_CHUNK = "TABLE_CHUNK"
    IMAGE_CHUNK = "IMAGE_CHUNK"
    OCR_CHUNK = "OCR_CHUNK"


class DocumentType(str, Enum):
    """Document type classification for structure analysis"""
    MANUAL = "manual"           # Technical manual with numbered sections
    REPORT = "report"           # Business/technical report
    PAPER = "paper"             # Academic paper
    CONTRACT = "contract"       # Legal contract
    PRESENTATION = "presentation"  # Slide deck content
    FORM = "form"               # Structured form
    OTHER = "other"             # Unclassified


class ProcessingStatus(str, Enum):
    """Processing status for adaptive embedding"""
    PENDING = "pending"
    ANALYZING = "analyzing"      # Structure analysis in progress
    CHUNKING = "chunking"        # Adaptive chunking in progress
    EMBEDDING = "embedding"      # Embedding generation in progress
    VALIDATING = "validating"    # Coverage validation in progress
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"          # Partially completed with some failures


class QualityLevel(str, Enum):
    """Embedding quality level classification"""
    EXCELLENT = "excellent"      # >= 0.9
    GOOD = "good"                # >= 0.7
    FAIR = "fair"                # >= 0.5
    POOR = "poor"                # < 0.5


# =============================================================================
# Dataclass Models (Internal Use)
# =============================================================================

@dataclass
class ChunkRelations:
    """Relationships between chunks"""
    previous: Optional[str] = None
    next: Optional[str] = None
    references: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "previous": self.previous,
            "next": self.next,
            "references": self.references,
            "parent": self.parent,
            "children": self.children
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkRelations":
        if not data:
            return cls()
        return cls(
            previous=data.get("previous"),
            next=data.get("next"),
            references=data.get("references", []),
            parent=data.get("parent"),
            children=data.get("children", [])
        )


@dataclass
class AdaptiveChunk:
    """
    Adaptive chunk with semantic boundaries and relationships.
    적응형 청크: 의미적 경계와 관계 정보 포함
    """
    pdf_id: str
    chunk_id: str
    chunk_type: ChunkType
    content: str
    page_start: int
    page_end: int
    content_hash: str
    section_path: Optional[str] = None
    section_title: Optional[str] = None
    parent_section_id: Optional[str] = None
    relations: ChunkRelations = field(default_factory=ChunkRelations)
    embedding: Optional[List[float]] = None
    embedding_model_version: str = "nv-embedqa-mistral-7b-v2"
    chunk_version: int = 1
    acl: Dict[str, List[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # DB에서 로드 시 임베딩 존재 여부를 별도로 저장 (큰 임베딩 벡터를 로드하지 않기 위함)
    _db_has_embedding: Optional[bool] = field(default=None, repr=False)

    @property
    def has_embedding(self) -> bool:
        # DB에서 로드된 값이 있으면 우선 사용 (임베딩 벡터를 로드하지 않아도 상태 확인 가능)
        if self._db_has_embedding is not None:
            return self._db_has_embedding
        return self.embedding is not None and len(self.embedding) > 0

    @property
    def content_length(self) -> int:
        return len(self.content)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pdf_id": self.pdf_id,
            "chunk_id": self.chunk_id,
            "chunk_type": self.chunk_type.value,
            "content": self.content,
            "content_length": self.content_length,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section_path": self.section_path,
            "section_title": self.section_title,
            "parent_section_id": self.parent_section_id,
            "relations": self.relations.to_dict(),
            "has_embedding": self.has_embedding,
            "embedding_model_version": self.embedding_model_version,
            "chunk_version": self.chunk_version,
            "content_hash": self.content_hash,
            "acl": self.acl,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


@dataclass
class SectionInfo:
    """Section hierarchy information"""
    id: str
    title: str
    level: int
    page_start: int
    page_end: int
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "parent_id": self.parent_id,
            "children": self.children
        }


@dataclass
class LayoutInfo:
    """Document layout information"""
    columns: int = 1
    has_header: bool = False
    has_footer: bool = False
    has_toc: bool = False
    page_dimensions: Dict[str, float] = field(default_factory=lambda: {"width": 595, "height": 842})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": self.columns,
            "has_header": self.has_header,
            "has_footer": self.has_footer,
            "has_toc": self.has_toc,
            "page_dimensions": self.page_dimensions
        }


@dataclass
class PDFStructureAnalysis:
    """Complete structure analysis result for a PDF"""
    pdf_id: str
    document_type: DocumentType
    hierarchy: List[SectionInfo]
    layout_info: LayoutInfo
    page_hashes: Dict[str, str]  # page_num -> sha256_hash
    total_pages: int
    total_images: int = 0
    total_tables: int = 0
    language: str = "auto"
    analyzed_at: Optional[datetime] = None
    document_name: Optional[str] = None  # Original filename for source reference

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pdf_id": self.pdf_id,
            "document_type": self.document_type.value,
            "hierarchy": [s.to_dict() for s in self.hierarchy],
            "layout_info": self.layout_info.to_dict(),
            "page_hashes": self.page_hashes,
            "total_pages": self.total_pages,
            "total_images": self.total_images,
            "total_tables": self.total_tables,
            "language": self.language,
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
            "document_name": self.document_name
        }


@dataclass
class ChunkPlan:
    """Plan for creating a chunk from document content"""
    chunk_type: ChunkType
    content: str
    page_start: int
    page_end: int
    section_path: Optional[str] = None
    section_title: Optional[str] = None
    parent_section_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CoverageReport:
    """Embedding coverage report"""
    total_chunks: int
    embedded_chunks: int
    failed_chunks: List[str]
    skipped_chunks: List[str]
    by_type: Dict[str, Dict[str, int]]  # type -> {total, embedded}

    @property
    def overall_coverage(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return self.embedded_chunks / self.total_chunks

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chunks": self.total_chunks,
            "embedded_chunks": self.embedded_chunks,
            "failed_chunks": self.failed_chunks,
            "skipped_chunks": self.skipped_chunks,
            "by_type": self.by_type,
            "overall_coverage": self.overall_coverage
        }


@dataclass
class QualityMetrics:
    """Quality evaluation metrics"""
    top_k_recall: float
    section_precision: float
    avg_similarity: float
    embedding_dimension: int
    quality_level: QualityLevel
    hallucination_detected: bool = False
    hallucination_details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "top_k_recall": self.top_k_recall,
            "section_precision": self.section_precision,
            "avg_similarity": self.avg_similarity,
            "embedding_dimension": self.embedding_dimension,
            "quality_level": self.quality_level.value,
            "hallucination_detected": self.hallucination_detected,
            "hallucination_details": self.hallucination_details
        }


@dataclass
class ChunkEmbeddingCoverage:
    """Complete embedding coverage and quality for a document"""
    pdf_id: str
    text_coverage: float
    table_coverage: float
    image_coverage: float
    ocr_coverage: float
    overall_coverage: float
    coverage_report: CoverageReport
    quality_metrics: QualityMetrics
    last_verified_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pdf_id": self.pdf_id,
            "text_coverage": self.text_coverage,
            "table_coverage": self.table_coverage,
            "image_coverage": self.image_coverage,
            "ocr_coverage": self.ocr_coverage,
            "overall_coverage": self.overall_coverage,
            "coverage_report": self.coverage_report.to_dict(),
            "quality_metrics": self.quality_metrics.to_dict(),
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None
        }


# =============================================================================
# Pydantic Models (API Request/Response)
# =============================================================================

class AdaptiveProcessRequest(BaseModel):
    """Request to process a PDF with adaptive embedding"""
    language: str = Field(default="auto", description="Document language (auto, en, ja, ko)")
    processing_mode: str = Field(default="text_only", description="Processing mode: text_only, vlm_enhanced, image_only")
    enable_ocr: bool = Field(default=False, description="Enable OCR for scanned pages")
    max_chunk_size: int = Field(default=1500, ge=200, le=4000, description="Maximum chunk size in characters")
    min_chunk_size: int = Field(default=100, ge=50, le=500, description="Minimum chunk size in characters")
    overlap_size: int = Field(default=100, ge=0, le=300, description="Overlap between chunks")
    preserve_tables: bool = Field(default=True, description="Keep tables as single chunks")
    preserve_sections: bool = Field(default=True, description="Respect section boundaries")
    force_reprocess: bool = Field(default=False, description="Force re-processing even if already processed")


class AdaptiveProcessResponse(BaseModel):
    """Response for adaptive processing request"""
    pdf_id: str
    task_id: str
    status: ProcessingStatus
    message: str
    estimated_chunks: int = Field(default=0, description="Estimated number of chunks")


class ChunkListItem(BaseModel):
    """Chunk list item for API responses"""
    chunk_id: str
    chunk_type: ChunkType
    content_preview: str = Field(description="First 200 characters of content")
    content_length: int
    page_start: int
    page_end: int
    section_path: Optional[str] = None
    section_title: Optional[str] = None
    has_embedding: bool


class ChunkDetailResponse(BaseModel):
    """Detailed chunk response"""
    chunk_id: str
    pdf_id: str
    chunk_type: ChunkType
    content: str
    content_length: int
    page_start: int
    page_end: int
    section_path: Optional[str] = None
    section_title: Optional[str] = None
    relations: Dict[str, Any]
    has_embedding: bool
    embedding_model_version: str
    chunk_version: int
    metadata: Dict[str, Any]
    created_at: Optional[datetime] = None


class CoverageResponse(BaseModel):
    """Coverage report API response"""
    pdf_id: str
    text_coverage: float
    table_coverage: float
    image_coverage: float
    ocr_coverage: float
    overall_coverage: float
    total_chunks: int
    embedded_chunks: int
    quality_level: QualityLevel
    last_verified_at: Optional[datetime] = None


class QualityResponse(BaseModel):
    """Quality evaluation API response"""
    pdf_id: str
    top_k_recall: float
    section_precision: float
    avg_similarity: float
    quality_level: QualityLevel
    hallucination_detected: bool
    issues: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class ReprocessRequest(BaseModel):
    """Request to incrementally re-embed changed pages"""
    changed_pages: Optional[List[int]] = Field(default=None, description="Specific pages to reprocess (None = detect changes)")
    force_all: bool = Field(default=False, description="Force re-embedding of all chunks")


class ReprocessResponse(BaseModel):
    """Response for reprocess request"""
    pdf_id: str
    task_id: str
    status: ProcessingStatus
    chunks_to_update: int
    chunks_skipped: int
    message: str


class StructureAnalysisResponse(BaseModel):
    """Structure analysis API response"""
    pdf_id: str
    document_name: Optional[str] = None  # 원본 파일명
    document_type: DocumentType
    total_pages: int
    total_sections: int
    total_images: int
    total_tables: int
    language: str
    hierarchy: List[Dict[str, Any]]
    layout_info: Dict[str, Any]
    analyzed_at: Optional[datetime] = None


class SearchAdaptiveChunksRequest(BaseModel):
    """Request to search adaptive chunks"""
    query: str = Field(min_length=1, description="Search query text")
    pdf_id: Optional[str] = Field(default=None, description="Filter by PDF ID")
    chunk_types: Optional[List[ChunkType]] = Field(default=None, description="Filter by chunk types")
    section_path_prefix: Optional[str] = Field(default=None, description="Filter by section path prefix")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum results")
    min_similarity: float = Field(default=0.3, ge=0.0, le=1.0, description="Minimum similarity threshold")


class SearchResultItem(BaseModel):
    """Search result item"""
    chunk_id: str
    pdf_id: str
    chunk_type: ChunkType
    content: str
    section_path: Optional[str] = None
    section_title: Optional[str] = None
    page_start: int
    page_end: int
    similarity: float
    related_chunks: List[str] = Field(default_factory=list)


class SearchAdaptiveChunksResponse(BaseModel):
    """Response for adaptive chunk search"""
    query: str
    total_results: int
    results: List[SearchResultItem]
