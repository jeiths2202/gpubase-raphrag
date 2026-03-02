"""
Document-related Pydantic models
Supports multimodal document processing with VLM
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Document processing status"""
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    EXTRACTING = "extracting"  # VLM extraction in progress
    EMBEDDING = "embedding"  # Generating embeddings
    INTERRUPTED = "interrupted"  # Server restart interrupted processing


class EmbeddingStatus(str, Enum):
    """Embedding generation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, Enum):
    """Supported document types"""
    PDF = "pdf"
    TEXT = "text"
    WORD = "word"
    EXCEL = "excel"
    POWERPOINT = "powerpoint"
    IMAGE = "image"
    MARKDOWN = "markdown"
    HTML = "html"
    CSV = "csv"
    JSON = "json"


class ProcessingMode(str, Enum):
    """Document processing mode"""
    TEXT_ONLY = "text_only"  # Traditional text extraction (pypdf)
    IMAGE_ONLY = "image_only"  # OCR extraction for scanned/image-based documents
    VLM_ENHANCED = "vlm_enhanced"  # VLM-assisted: text + OCR + layout + table extraction


# MIME type mappings
SUPPORTED_MIME_TYPES: Dict[str, DocumentType] = {
    # PDF
    "application/pdf": DocumentType.PDF,
    # Text
    "text/plain": DocumentType.TEXT,
    "text/markdown": DocumentType.MARKDOWN,
    "text/html": DocumentType.HTML,
    "text/csv": DocumentType.CSV,
    # Microsoft Office
    "application/msword": DocumentType.WORD,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.WORD,
    "application/vnd.ms-excel": DocumentType.EXCEL,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.EXCEL,
    "application/vnd.ms-powerpoint": DocumentType.POWERPOINT,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": DocumentType.POWERPOINT,
    # Images
    "image/png": DocumentType.IMAGE,
    "image/jpeg": DocumentType.IMAGE,
    "image/jpg": DocumentType.IMAGE,
    "image/gif": DocumentType.IMAGE,
    "image/bmp": DocumentType.IMAGE,
    "image/tiff": DocumentType.IMAGE,
    "image/webp": DocumentType.IMAGE,
    # JSON
    "application/json": DocumentType.JSON,
}

# File extension mappings
EXTENSION_TO_MIME: Dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".csv": "text/csv",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
    ".json": "application/json",
}


class VLMExtractionResult(BaseModel):
    """VLM extraction result for images/documents"""
    text_content: str = ""
    layout_analysis: Dict[str, Any] = Field(default_factory=dict)
    detected_objects: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    figures: List[Dict[str, Any]] = Field(default_factory=list)
    equations: List[str] = Field(default_factory=list)
    handwriting: List[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    processing_time_ms: int = 0


class ImageInfo(BaseModel):
    """Extracted image information"""
    id: str
    page_number: Optional[int] = None
    position: Dict[str, float] = Field(default_factory=dict)  # x, y, width, height
    description: str = ""
    alt_text: str = ""
    embedding: Optional[List[float]] = None
    vlm_analysis: Optional[Dict[str, Any]] = None
    # Actual image binary data for embedding processing
    data: Optional[bytes] = None
    width: int = 0
    height: int = 0
    mime_type: str = ""
    # Figure reference for matching images to text references (e.g., "図1.1", "Figure 1-1")
    figure_reference: Optional[str] = None
    figure_caption: Optional[str] = None

    class Config:
        # Allow arbitrary types for bytes field
        arbitrary_types_allowed = True


class TableInfo(BaseModel):
    """Extracted table information"""
    id: str
    page_number: Optional[int] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    caption: str = ""
    markdown: str = ""


class DocumentBase(BaseModel):
    """Base document model"""
    filename: str
    original_name: str
    file_size: int = Field(ge=0, description="File size in bytes")
    mime_type: str = "application/pdf"
    document_type: DocumentType = DocumentType.PDF
    processing_mode: ProcessingMode = ProcessingMode.TEXT_ONLY


class DocumentCreate(BaseModel):
    """Document upload request"""
    name: Optional[str] = Field(default=None, description="Display name")
    language: str = Field(default="auto", description="Document language")
    tags: List[str] = Field(default_factory=list, description="Tags")
    processing_mode: ProcessingMode = Field(default=ProcessingMode.TEXT_ONLY, description="Processing mode")
    enable_vlm: bool = Field(default=False, description="Enable VLM-based extraction")
    extract_tables: bool = Field(default=True, description="Extract tables from document")
    extract_images: bool = Field(default=True, description="Extract and analyze images")


class DocumentStats(BaseModel):
    """Document statistics"""
    pages: int = 0
    chunks_count: int = 0
    entities_count: int = 0
    avg_chunk_size: float = 0.0
    embedding_dimension: int = 1024
    images_count: int = 0
    tables_count: int = 0
    figures_count: int = 0
    vlm_processed: bool = False
    total_characters: Optional[int] = None
    title: Optional[str] = None
    author: Optional[str] = None


class ProcessingInfo(BaseModel):
    """Document processing information"""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time_seconds: Optional[float] = None


class DocumentListItem(BaseModel):
    """Document list item"""
    id: str
    filename: str
    original_name: str
    file_size: int
    mime_type: str
    document_type: DocumentType = DocumentType.PDF
    status: DocumentStatus
    chunks_count: int = 0
    entities_count: int = 0
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    language: str = "auto"
    processing_mode: ProcessingMode = ProcessingMode.TEXT_ONLY
    vlm_processed: bool = False
    created_at: datetime
    updated_at: datetime


class MultimodalContent(BaseModel):
    """Multimodal content extracted from document"""
    images: List[ImageInfo] = Field(default_factory=list)
    tables: List[TableInfo] = Field(default_factory=list)
    vlm_extractions: List[VLMExtractionResult] = Field(default_factory=list)


class DocumentDetail(DocumentListItem):
    """Document detail model"""
    tags: List[str] = Field(default_factory=list)
    stats: Optional[DocumentStats] = None
    processing_info: Optional[ProcessingInfo] = None
    multimodal_content: Optional[MultimodalContent] = None


class DocumentUploadResponse(BaseModel):
    """Document upload response"""
    document_id: str
    filename: str
    status: DocumentStatus = DocumentStatus.PROCESSING
    message: str
    task_id: str


class DocumentDeleteResponse(BaseModel):
    """Document deletion response"""
    document_id: str
    message: str
    deleted_chunks: int = 0
    deleted_entities: int = 0
    deleted_text_chunks: int = Field(default=0, description="PostgreSQL text_chunks 삭제 수")
    deleted_images: int = Field(default=0, description="PostgreSQL image_embeddings 삭제 수")
    deleted_neo4j_nodes: int = Field(default=0, description="Neo4j 노드 삭제 수")
    deleted_rag_profiles: int = Field(default=0, description="PostgreSQL document_rag_profiles 삭제 수")


class ChunkInfo(BaseModel):
    """Chunk information"""
    id: str
    index: int
    content: str
    content_length: int
    has_embedding: bool = False
    entities: List[str] = Field(default_factory=list)
    page_number: Optional[int] = None
    chunk_type: str = "text"  # text, table, image_caption, vlm_extraction
    source_image_id: Optional[str] = None
    source_table_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UploadStep(BaseModel):
    """Upload processing step"""
    name: str
    status: str
    progress: Optional[int] = None


class UploadProgress(BaseModel):
    """Upload progress information"""
    current_step: str
    steps: list[UploadStep]
    overall_progress: int = Field(ge=0, le=100)


class UploadStatusResponse(BaseModel):
    """Upload status response"""
    task_id: str
    document_id: str
    status: DocumentStatus
    progress: UploadProgress
    started_at: datetime
    estimated_completion: Optional[datetime] = None


# =============================================================================
# Embedding Quality Verification Models
# =============================================================================

class QualityLevel(str, Enum):
    """Embedding quality level"""
    EXCELLENT = "excellent"  # >= 0.8
    GOOD = "good"           # >= 0.6
    FAIR = "fair"           # >= 0.4
    POOR = "poor"           # < 0.4


class SimilarityTestResult(BaseModel):
    """Result of a single similarity test"""
    query: str
    expected_chunk_index: int
    retrieved_chunk_index: int
    similarity_score: float
    is_hit: bool


class EmbeddingQualityMetrics(BaseModel):
    """Embedding quality metrics"""
    overall_score: float = Field(ge=0.0, le=1.0, description="Overall quality score (0-1)")
    quality_level: QualityLevel = Field(description="Quality level classification")
    retrieval_accuracy: float = Field(ge=0.0, le=1.0, description="Retrieval accuracy rate")
    avg_similarity: float = Field(ge=0.0, le=1.0, description="Average similarity score")
    similarity_std: float = Field(ge=0.0, description="Similarity standard deviation")
    coverage_score: float = Field(ge=0.0, le=1.0, description="Embedding coverage score")


class EmbeddingQualityResponse(BaseModel):
    """Embedding quality verification response"""
    document_id: str
    verified_at: datetime
    metrics: EmbeddingQualityMetrics
    embedding_dimension: int
    chunks_tested: int
    chunks_total: int
    test_results: List[SimilarityTestResult] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class EmbeddingQualitySummary(BaseModel):
    """Summary of embedding quality for document list"""
    overall_score: float = Field(ge=0.0, le=1.0)
    quality_level: QualityLevel
    verified_at: Optional[datetime] = None
    has_issues: bool = False


# =============================================================================
# Re-Embedding Models
# =============================================================================

class ReEmbedRequest(BaseModel):
    """Request to re-embed a document with custom parameters"""
    chunk_size: int = Field(
        default=512,
        ge=100,
        le=4000,
        description="Size of each text chunk in characters"
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="Overlap between consecutive chunks"
    )
    processing_mode: ProcessingMode = Field(
        default=ProcessingMode.TEXT_ONLY,
        description="Processing mode for document"
    )
    enable_vlm: bool = Field(
        default=False,
        description="Enable Vision Language Model processing"
    )
    extract_tables: bool = Field(
        default=True,
        description="Extract tables from document"
    )
    extract_images: bool = Field(
        default=True,
        description="Extract images from document"
    )
    force: bool = Field(
        default=False,
        description="Force re-embedding even if already processing"
    )


class ReEmbedResponse(BaseModel):
    """Response for re-embedding request"""
    document_id: str
    task_id: str
    status: str = Field(description="Current status: processing, queued")
    message: str
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Applied re-embedding parameters"
    )


# =============================================================================
# Document Comparison Models
# =============================================================================

class DocumentCompareRequest(BaseModel):
    """Request to compare multiple documents on a topic
    문서 비교 요청
    """
    document_ids: List[str] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="List of document IDs to compare (2-5 documents)"
    )
    topic: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Topic/question to compare documents on"
    )
    language: str = Field(
        default="auto",
        description="Response language (auto, ko, en, ja)"
    )


class DocumentSection(BaseModel):
    """Relevant section from a document
    문서에서 추출된 관련 섹션
    """
    section_path: Optional[str] = Field(
        default=None,
        description="Section path (e.g., '1.2.3 Installation')"
    )
    section_title: Optional[str] = Field(
        default=None,
        description="Section title"
    )
    content: str = Field(
        ...,
        description="Section content text"
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Page number if available"
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Relevance score"
    )
    chunk_id: Optional[str] = Field(
        default=None,
        description="Source chunk ID"
    )


class DocumentCompareResult(BaseModel):
    """Comparison result for a single document
    단일 문서의 비교 결과
    """
    doc_id: str = Field(
        ...,
        description="Document ID"
    )
    doc_name: str = Field(
        ...,
        description="Document name"
    )
    relevant_sections: List[DocumentSection] = Field(
        default_factory=list,
        description="Relevant sections found in this document"
    )
    has_content: bool = Field(
        default=False,
        description="Whether the document has relevant content"
    )


class ComparisonDifference(BaseModel):
    """A specific difference between documents
    문서 간 차이점
    """
    aspect: str = Field(
        ...,
        description="Aspect or dimension of comparison"
    )
    documents: Dict[str, str] = Field(
        default_factory=dict,
        description="Document ID to content mapping for this difference"
    )


class ComparisonSummary(BaseModel):
    """Summary of document comparison
    문서 비교 요약
    """
    topic: str = Field(
        ...,
        description="Comparison topic"
    )
    documents: List[DocumentCompareResult] = Field(
        default_factory=list,
        description="Results for each document"
    )
    summary: str = Field(
        default="",
        description="LLM-generated comparison summary"
    )
    commonalities: List[str] = Field(
        default_factory=list,
        description="Common points across documents"
    )
    differences: List[ComparisonDifference] = Field(
        default_factory=list,
        description="Differences between documents"
    )
    language: str = Field(
        default="ko",
        description="Response language"
    )
