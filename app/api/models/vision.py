"""
Vision Data Models

Data models for Vision LLM routing, document analysis, and response handling.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union


class ProcessingMode(str, Enum):
    """Document processing modes"""
    TEXT_ONLY = "text_only"           # Traditional text extraction
    VLM_ENHANCED = "vlm_enhanced"     # VLM-assisted extraction
    MULTIMODAL = "multimodal"         # Full image understanding
    OCR = "ocr"                       # Scanned documents


class ImageType(str, Enum):
    """Types of images extracted from documents"""
    PAGE = "page"           # Full page render
    EMBEDDED = "embedded"   # Embedded image in document
    CHART = "chart"         # Chart/graph
    TABLE = "table"         # Table as image
    DIAGRAM = "diagram"     # Diagram/flowchart
    SCREENSHOT = "screenshot"  # Screenshot/UI
    PHOTO = "photo"         # Photograph


@dataclass
class BoundingBox:
    """Bounding box for image regions"""
    x: float  # Left position (0.0 - 1.0 normalized)
    y: float  # Top position (0.0 - 1.0 normalized)
    width: float
    height: float

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class ProcessedImage:
    """Processed image ready for Vision LLM"""
    image_bytes: bytes
    mime_type: str
    original_size: tuple  # (width, height)
    processed_size: tuple  # (width, height) after preprocessing
    format: str  # "PNG", "JPEG"

    # Source information
    page_number: Optional[int] = None
    region: Optional[BoundingBox] = None
    image_type: ImageType = ImageType.PAGE

    # Processing metadata
    file_size_bytes: int = 0
    compression_ratio: float = 1.0

    def __post_init__(self):
        self.file_size_bytes = len(self.image_bytes)


@dataclass
class DocumentVisualProfile:
    """Visual characteristics profile for a document"""

    # Layer 1: Basic Classification
    document_id: str
    mime_type: str
    extension: str
    is_pure_image: bool = False  # .png, .jpg, etc.

    # Layer 2: Content Metrics
    total_pages: int = 0
    image_count: int = 0
    image_area_ratio: float = 0.0  # 0.0 ~ 1.0
    text_density: float = 0.0  # chars per page
    extractable_text_ratio: float = 1.0  # ratio of extractable text
    table_count: int = 0
    table_area_ratio: float = 0.0

    # Layer 3: Visual Complexity
    has_charts: bool = False
    has_diagrams: bool = False
    has_screenshots: bool = False
    has_handwriting: bool = False
    requires_ocr: bool = False

    # Computed
    visual_complexity_score: float = 0.0

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def requires_vision_llm(self) -> bool:
        """Determine if Vision LLM is required"""
        return (
            self.is_pure_image or
            self.visual_complexity_score >= 0.4 or
            self.image_area_ratio >= 0.3 or
            self.has_charts or
            self.has_diagrams or
            self.requires_ocr
        )

    @property
    def recommended_processing_mode(self) -> ProcessingMode:
        """Recommend processing mode based on profile"""
        if self.is_pure_image or self.requires_ocr:
            return ProcessingMode.MULTIMODAL
        elif self.visual_complexity_score >= 0.4:
            return ProcessingMode.MULTIMODAL
        elif self.visual_complexity_score >= 0.2:
            return ProcessingMode.VLM_ENHANCED
        else:
            return ProcessingMode.TEXT_ONLY

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "document_id": self.document_id,
            "mime_type": self.mime_type,
            "extension": self.extension,
            "is_pure_image": self.is_pure_image,
            "total_pages": self.total_pages,
            "image_count": self.image_count,
            "image_area_ratio": self.image_area_ratio,
            "text_density": self.text_density,
            "extractable_text_ratio": self.extractable_text_ratio,
            "table_count": self.table_count,
            "table_area_ratio": self.table_area_ratio,
            "has_charts": self.has_charts,
            "has_diagrams": self.has_diagrams,
            "has_screenshots": self.has_screenshots,
            "has_handwriting": self.has_handwriting,
            "requires_ocr": self.requires_ocr,
            "visual_complexity_score": self.visual_complexity_score,
            "requires_vision_llm": self.requires_vision_llm,
            "recommended_processing_mode": self.recommended_processing_mode.value,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


@dataclass
class VisualQuerySignals:
    """Visual signals detected in a query"""
    is_visual_query: bool
    visual_aspects: List[str]  # ["chart", "diagram", "image", ...]
    confidence: float
    suggested_model: Literal["vision", "text", "code"]
    detected_patterns: List[str] = field(default_factory=list)


@dataclass
class RoutingDecision:
    """Routing decision for LLM selection"""
    selected_llm: Literal["vision", "text", "code"]
    reasoning: str
    confidence: float
    query_type: str = "vector"  # vector, graph, hybrid, code
    visual_context: Optional[List[ProcessedImage]] = None

    # Cost estimation
    estimated_cost: float = 0.0
    estimated_tokens: int = 0


# Structured data extraction models

@dataclass
class AxisInfo:
    """Chart axis information"""
    label: Optional[str] = None
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    tick_values: List[Union[str, float]] = field(default_factory=list)


@dataclass
class DataPoint:
    """Single data point in a chart"""
    x: Union[str, float]
    y: float
    series: Optional[str] = None
    label: Optional[str] = None


@dataclass
class ChartData:
    """Extracted chart data"""
    chart_type: str  # "bar", "line", "pie", "scatter", "area"
    title: Optional[str] = None
    x_axis: Optional[AxisInfo] = None
    y_axis: Optional[AxisInfo] = None
    data_points: List[DataPoint] = field(default_factory=list)
    legend: List[str] = field(default_factory=list)
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chart_type": self.chart_type,
            "title": self.title,
            "x_axis": self.x_axis.__dict__ if self.x_axis else None,
            "y_axis": self.y_axis.__dict__ if self.y_axis else None,
            "data_points": [
                {"x": dp.x, "y": dp.y, "series": dp.series, "label": dp.label}
                for dp in self.data_points
            ],
            "legend": self.legend,
            "source": self.source,
        }


@dataclass
class TableCell:
    """Table cell data"""
    value: str
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False


@dataclass
class TableData:
    """Extracted table data"""
    headers: List[str]
    rows: List[List[str]]
    cells: List[TableCell] = field(default_factory=list)
    title: Optional[str] = None

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return len(self.headers) if self.headers else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "headers": self.headers,
            "rows": self.rows,
            "title": self.title,
            "row_count": self.row_count,
            "col_count": self.col_count,
        }


@dataclass
class DiagramNode:
    """Node in a diagram"""
    id: str
    label: str
    node_type: Optional[str] = None  # "process", "decision", "start", "end"
    position: Optional[BoundingBox] = None


@dataclass
class DiagramEdge:
    """Edge connecting diagram nodes"""
    source_id: str
    target_id: str
    label: Optional[str] = None
    edge_type: str = "arrow"  # "arrow", "line", "dashed"


@dataclass
class DiagramStructure:
    """Extracted diagram structure"""
    diagram_type: str  # "flowchart", "sequence", "class", "er", "architecture"
    nodes: List[DiagramNode] = field(default_factory=list)
    edges: List[DiagramEdge] = field(default_factory=list)
    title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "diagram_type": self.diagram_type,
            "nodes": [
                {"id": n.id, "label": n.label, "type": n.node_type}
                for n in self.nodes
            ],
            "edges": [
                {"source": e.source_id, "target": e.target_id, "label": e.label}
                for e in self.edges
            ],
            "title": self.title,
        }


@dataclass
class ImageAnalysisResult:
    """Result of analyzing a single image"""
    image_id: str
    page_number: Optional[int]
    description: str
    extracted_text: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    processing_time_ms: float = 0.0


@dataclass
class VisualAnalysis:
    """Complete visual analysis result"""
    analyzed_images: List[ImageAnalysisResult]
    extracted_data: Dict[str, Any]  # Charts, tables, diagrams
    visual_summary: str
    total_processing_time_ms: float = 0.0


@dataclass
class DocumentVisionResult:
    """Complete Vision processing result for a document"""
    document_id: str
    visual_profile: DocumentVisualProfile
    extracted_images: List[ProcessedImage]
    analysis_results: List[ImageAnalysisResult]

    # Aggregated data
    all_extracted_text: str = ""
    charts: List[ChartData] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    diagrams: List[DiagramStructure] = field(default_factory=list)

    # Metadata
    processing_time_ms: float = 0.0
    vision_model_used: Optional[str] = None
    total_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "visual_profile": self.visual_profile.to_dict(),
            "image_count": len(self.extracted_images),
            "analysis_count": len(self.analysis_results),
            "charts": [c.to_dict() for c in self.charts],
            "tables": [t.to_dict() for t in self.tables],
            "diagrams": [d.to_dict() for d in self.diagrams],
            "processing_time_ms": self.processing_time_ms,
            "vision_model_used": self.vision_model_used,
            "total_cost": self.total_cost,
        }


# Response models

@dataclass
class SourceInfo:
    """Source information for a retrieved document"""
    document_id: str
    filename: str
    page_number: Optional[int] = None
    chunk_text: str = ""
    relevance_score: float = 0.0
    has_visual_content: bool = False


@dataclass
class RoutingInfo:
    """Routing decision information"""
    selected_llm: str  # "vision", "text", "code"
    reasoning: str
    query_type: str  # "vector", "graph", "hybrid", "code"
    visual_signals_detected: bool


@dataclass
class ResponseMetadata:
    """Response metadata"""
    total_tokens: int
    latency_ms: float
    model_used: str
    vision_model_used: Optional[str] = None
    cache_hit: bool = False
    cost: float = 0.0


@dataclass
class UnifiedQueryResponse:
    """Unified response format for all LLM types"""
    # Core response
    answer: str
    confidence: float

    # Routing info
    routing: RoutingInfo

    # Sources
    sources: List[SourceInfo]

    # Vision-specific (optional)
    visual_analysis: Optional[VisualAnalysis] = None

    # Metadata
    metadata: ResponseMetadata = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "answer": self.answer,
            "confidence": self.confidence,
            "routing": {
                "selected_llm": self.routing.selected_llm,
                "reasoning": self.routing.reasoning,
                "query_type": self.routing.query_type,
                "visual_signals_detected": self.routing.visual_signals_detected,
            },
            "sources": [
                {
                    "document_id": s.document_id,
                    "filename": s.filename,
                    "page_number": s.page_number,
                    "chunk_text": s.chunk_text[:200],
                    "relevance_score": s.relevance_score,
                    "has_visual_content": s.has_visual_content,
                }
                for s in self.sources
            ],
        }

        if self.visual_analysis:
            result["visual_analysis"] = {
                "image_count": len(self.visual_analysis.analyzed_images),
                "visual_summary": self.visual_analysis.visual_summary,
                "extracted_data": self.visual_analysis.extracted_data,
            }

        if self.metadata:
            result["metadata"] = {
                "total_tokens": self.metadata.total_tokens,
                "latency_ms": self.metadata.latency_ms,
                "model_used": self.metadata.model_used,
                "vision_model_used": self.metadata.vision_model_used,
                "cache_hit": self.metadata.cache_hit,
            }

        return result
