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
    TEXT_ONLY = "text_only"  # Traditional text extraction
    VLM_ENHANCED = "vlm_enhanced"  # VLM-assisted extraction
    MULTIMODAL = "multimodal"  # Full multimodal with image understanding
    OCR = "ocr"  # OCR for scanned documents


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
    embedding_dimension: int = 4096
    images_count: int = 0
    tables_count: int = 0
    figures_count: int = 0
    vlm_processed: bool = False


class ProcessingInfo(BaseModel):
    """Document processing information"""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time_seconds: Optional[int] = None


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
