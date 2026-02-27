"""API request/response schemas for Legacy Modernization endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..models.enums import PipelineStatus


class AnalysisOptions(BaseModel):
    """Analysis options for controlling the pipeline."""

    include_competitor_analysis: bool = Field(
        True, description="Include multi-vendor compatibility comparison",
    )
    include_risk_assessment: bool = Field(
        True, description="Include LLM-based risk scoring",
    )
    include_e2e_test: bool = Field(
        False, description="Include E2E test agent (optional)",
    )
    max_reanalysis_iterations: int = Field(
        5, ge=1, le=10, description="Max reanalysis loop iterations",
    )


class AnalysisRequest(BaseModel):
    """Request body for analysis endpoint (JSON mode, file content inline)."""

    file_name: str = Field(
        ..., min_length=1, description="Source file name (e.g., 'PAYROLL.cbl')",
        examples=["PAYROLL.cbl"],
    )
    source_code: str = Field(
        ..., min_length=1, description="Legacy source code content",
    )
    target_product: Optional[str] = Field(
        None,
        description="Target OpenFrame product (e.g., 'osc', 'batch', 'aim_xsp')",
        examples=["osc"],
    )
    target_version: Optional[str] = Field(
        None,
        description="Target product version (e.g., '7.1', '8.0')",
        examples=["7.1"],
    )
    vendors: List[str] = Field(
        default=["openframe"],
        description="Target vendors for compatibility analysis",
        examples=[["openframe", "ibm_zos", "micro_focus"]],
    )
    options: AnalysisOptions = Field(
        default_factory=AnalysisOptions,
        description="Analysis pipeline options",
    )


class AnalysisResponse(BaseModel):
    """Response after starting an analysis."""

    analysis_id: str = Field(..., description="Unique analysis session ID")
    status: str = Field(..., description="Initial pipeline status")
    message: str = Field(..., description="Human-readable status message")
    estimated_duration_minutes: Optional[int] = Field(
        None, description="Rough time estimate in minutes",
    )


class AnalysisStatusResponse(BaseModel):
    """Current analysis progress."""

    analysis_id: str
    status: str = Field(..., description="Current pipeline status")
    progress_percent: float = Field(
        ..., ge=0.0, le=100.0, description="Progress percentage",
    )
    current_agent: Optional[str] = Field(
        None, description="Name of the currently active agent",
    )
    elapsed_seconds: float = Field(
        ..., description="Elapsed time since analysis started",
    )


class AnalysisResultsResponse(BaseModel):
    """Complete analysis results."""

    analysis_id: str
    workspace: Dict[str, Any] = Field(
        ..., description="Full SharedWorkspaceState snapshot",
    )
    reports: Dict[str, Any] = Field(
        ..., description="Generated reports keyed by report_type",
    )
    audit_trail: List[Dict[str, Any]] = Field(
        default_factory=list, description="Audit trail entries",
    )


class ReportResponse(BaseModel):
    """Single report response."""

    report_id: str
    report_type: str
    title: str
    format: str
    content: Dict[str, Any]
    generated_at: str
    asset_id: str
    tenant_id: str


class ReportListResponse(BaseModel):
    """List of available reports for an analysis."""

    analysis_id: str
    reports: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Available report summaries (type, title, generated_at)",
    )


class ProductVersionItem(BaseModel):
    """Single product+version entry."""

    product: str = Field(..., description="Product ID (e.g., 'osc')")
    version: str = Field(..., description="Version string (e.g., '7.1')")
    display_name: str = Field(..., description="Localized display name")
    asset_types: List[str] = Field(default_factory=list)


class ProductFamilyItem(BaseModel):
    """Product family with grouped versions."""

    family: str = Field(..., description="Family name (e.g., 'OSC')")
    display_name: str
    versions: List[ProductVersionItem]


class ProductListResponse(BaseModel):
    """Response for GET /products endpoint."""

    families: List[ProductFamilyItem] = Field(default_factory=list)
    total_products: int = Field(0, description="Total number of product+version combinations")


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Error description")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")


# ---------------------------------------------------------------------------
# Batch Analysis Models
# ---------------------------------------------------------------------------


class FileItem(BaseModel):
    """Individual file for batch analysis."""

    file_name: str = Field(..., min_length=1, description="Source file name")
    source_code: str = Field(..., min_length=1, description="Source code content")


class BatchAnalysisRequest(BaseModel):
    """Multi-file batch analysis request."""

    files: List[FileItem] = Field(
        ..., min_length=1, max_length=10,
        description="Files to analyze (1-10)",
    )
    target_product: Optional[str] = Field(None, description="Target OpenFrame product")
    target_version: Optional[str] = Field(None, description="Target product version")
    vendors: List[str] = Field(default=["openframe"])
    options: AnalysisOptions = Field(default_factory=AnalysisOptions)


class FileAnalysisResult(BaseModel):
    """Per-file analysis result within a batch."""

    file_name: str
    analysis_id: str
    status: str  # "completed" | "failed" | "in_progress"
    asset_type: str = ""
    total_features: int = 0
    supported_count: int = 0
    incompatible_count: int = 0
    support_rate: float = 0.0
    risk_summary: Dict[str, int] = Field(default_factory=dict)
    incompatibility_report: Optional[Dict[str, Any]] = None


class BatchSummary(BaseModel):
    """Aggregate summary across all files in a batch."""

    batch_id: str
    total_files: int
    completed_files: int
    failed_files: int
    total_features: int = 0
    total_supported: int = 0
    total_incompatible: int = 0
    overall_support_rate: float = 0.0
    risk_breakdown: Dict[str, int] = Field(default_factory=dict)
    top_incompatible_items: List[Dict[str, Any]] = Field(default_factory=list)


class BatchAnalysisResponse(BaseModel):
    """Response after starting a batch analysis."""

    batch_id: str
    total_files: int
    analysis_ids: List[str]
    status: str
    message: str


class BatchStatusResponse(BaseModel):
    """Batch analysis progress."""

    batch_id: str
    total_files: int
    completed: int
    failed: int
    in_progress: int
    overall_progress: float = 0.0
    file_statuses: List[Dict[str, Any]] = Field(default_factory=list)


class BatchResultsResponse(BaseModel):
    """Complete batch results with summary + per-file details."""

    batch_id: str
    summary: BatchSummary
    file_results: List[FileAnalysisResult]


# ---------------------------------------------------------------------------
# Persisted Analysis Models (Data Table & Detail Popup)
# ---------------------------------------------------------------------------


class AnalysisListItem(BaseModel):
    """Data Table row item (no JSONB, for fast list queries)."""

    id: str
    batch_id: Optional[str] = None
    file_name: str
    asset_type: str
    loc_count: int = 0
    target_product: Optional[str] = None
    target_version: Optional[str] = None
    status: str = "completed"
    total_features: int = 0
    supported_count: int = 0
    incompatible_count: int = 0
    support_rate: float = 0.0
    risk_high: int = 0
    risk_medium: int = 0
    risk_low: int = 0
    analysis_duration_seconds: Optional[float] = None
    pipeline_status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AnalysisListResponse(BaseModel):
    """Paginated Data Table response."""

    items: List[AnalysisListItem]
    total: int
    page: int
    limit: int
    total_pages: int


class AnalysisDetailResponse(BaseModel):
    """Full detail for popup page (includes JSONB fields)."""

    id: str
    user_id: Optional[str] = None
    batch_id: Optional[str] = None
    file_name: str
    asset_type: str
    source_code: Optional[str] = None
    loc_count: int = 0
    target_product: Optional[str] = None
    target_version: Optional[str] = None
    vendors: List[str] = Field(default_factory=list)
    status: str = "completed"
    total_features: int = 0
    supported_count: int = 0
    incompatible_count: int = 0
    support_rate: float = 0.0
    risk_high: int = 0
    risk_medium: int = 0
    risk_low: int = 0
    incompatibility_report: Optional[Dict[str, Any]] = None
    reports: Dict[str, Any] = Field(default_factory=dict)
    workspace_snapshot: Optional[Dict[str, Any]] = None
    analysis_duration_seconds: Optional[float] = None
    pipeline_status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
