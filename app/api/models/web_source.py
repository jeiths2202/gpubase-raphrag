"""
Web Source Models for URL-based RAG
Supports fetching and processing web content for RAG indexing
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl


class WebSourceStatus(str, Enum):
    """Web source processing status"""
    PENDING = "pending"
    FETCHING = "fetching"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    ERROR = "error"
    STALE = "stale"  # Content may have changed


class ContentType(str, Enum):
    """Extracted content type"""
    ARTICLE = "article"
    BLOG = "blog"
    DOCUMENTATION = "documentation"
    NEWS = "news"
    WIKI = "wiki"
    GENERIC = "generic"


class ExtractorType(str, Enum):
    """Content extraction method"""
    TRAFILATURA = "trafilatura"
    BEAUTIFULSOUP = "beautifulsoup"
    READABILITY = "readability"
    RAW = "raw"


class WebSourceMetadata(BaseModel):
    """Metadata extracted from web page"""
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    published_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    language: Optional[str] = None
    site_name: Optional[str] = None
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    content_type: ContentType = ContentType.GENERIC


class WebSourceCreate(BaseModel):
    """Web source creation request"""
    url: str = Field(..., description="URL to fetch and process")
    name: Optional[str] = Field(None, description="Display name for the source")
    tags: List[str] = Field(default_factory=list, description="Tags for organization")
    extractor: ExtractorType = Field(
        default=ExtractorType.TRAFILATURA,
        description="Content extraction method"
    )
    include_images: bool = Field(
        default=False,
        description="Extract and process images from the page"
    )
    include_links: bool = Field(
        default=False,
        description="Extract and store links from the page"
    )
    follow_links: bool = Field(
        default=False,
        description="Recursively fetch linked pages (limited depth)"
    )
    max_depth: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Maximum depth for link following"
    )
    language: str = Field(
        default="auto",
        description="Expected content language (auto, ko, ja, en)"
    )


class WebSourceBulkCreate(BaseModel):
    """Bulk web source creation request"""
    urls: List[str] = Field(..., min_length=1, max_length=20, description="List of URLs")
    tags: List[str] = Field(default_factory=list, description="Tags for all sources")
    extractor: ExtractorType = Field(default=ExtractorType.TRAFILATURA)


class ExtractionResult(BaseModel):
    """Content extraction result"""
    text_content: str = ""
    html_content: str = ""
    word_count: int = 0
    char_count: int = 0
    extraction_time_ms: int = 0
    extractor_used: ExtractorType = ExtractorType.TRAFILATURA
    success: bool = True
    error_message: Optional[str] = None


class LinkInfo(BaseModel):
    """Extracted link information"""
    url: str
    text: str = ""
    is_internal: bool = False
    is_processed: bool = False


class ImageFromWeb(BaseModel):
    """Image extracted from web page"""
    url: str
    alt_text: str = ""
    caption: str = ""
    width: Optional[int] = None
    height: Optional[int] = None


class WebSourceStats(BaseModel):
    """Web source statistics"""
    word_count: int = 0
    char_count: int = 0
    chunk_count: int = 0
    link_count: int = 0
    image_count: int = 0
    embedding_dimension: int = 4096
    last_fetched: Optional[datetime] = None
    last_checked: Optional[datetime] = None
    fetch_time_ms: int = 0
    extraction_time_ms: int = 0


class WebSource(BaseModel):
    """Web source document model"""
    id: str
    url: str
    display_name: str
    domain: str
    status: WebSourceStatus = WebSourceStatus.PENDING
    metadata: WebSourceMetadata = Field(default_factory=WebSourceMetadata)
    stats: WebSourceStats = Field(default_factory=WebSourceStats)
    tags: List[str] = Field(default_factory=list)

    # Extraction settings
    extractor: ExtractorType = ExtractorType.TRAFILATURA
    include_images: bool = False
    include_links: bool = False

    # Extracted content
    extracted_text: Optional[str] = None
    extracted_links: List[LinkInfo] = Field(default_factory=list)
    extracted_images: List[ImageFromWeb] = Field(default_factory=list)

    # Processing info
    http_status_code: Optional[int] = None
    content_hash: Optional[str] = None  # For change detection
    error_message: Optional[str] = None
    retry_count: int = 0

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    fetched_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    # Owner
    created_by: Optional[str] = None


class WebSourceListItem(BaseModel):
    """Web source list item (compact)"""
    id: str
    url: str
    display_name: str
    domain: str
    status: WebSourceStatus
    chunk_count: int = 0
    word_count: int = 0
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    fetched_at: Optional[datetime] = None
    error_message: Optional[str] = None


class WebSourceDetail(WebSource):
    """Detailed web source with full content"""
    chunks: List[Dict[str, Any]] = Field(default_factory=list)


class WebSourceResponse(BaseModel):
    """Web source API response"""
    status: str = "success"
    data: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None


class WebSourceListResponse(BaseModel):
    """Web source list response"""
    status: str = "success"
    data: Dict[str, Any] = Field(default_factory=dict)


class RefreshRequest(BaseModel):
    """Request to refresh web source content"""
    force: bool = Field(
        default=False,
        description="Force refresh even if content hasn't changed"
    )


class RefreshResponse(BaseModel):
    """Refresh operation response"""
    web_source_id: str
    status: str
    content_changed: bool = False
    message: str
