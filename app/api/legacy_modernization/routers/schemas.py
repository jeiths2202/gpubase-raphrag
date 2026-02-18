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
