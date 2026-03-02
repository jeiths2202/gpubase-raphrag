"""Report models — ReportType (9 types), ReportFormat, Report base model."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ReportType(str, Enum):
    """9 report types produced by the analysis pipeline."""

    TECHNICAL_FINDINGS = "technical_findings"     # FR-04-A
    EXECUTIVE_SUMMARY = "executive_summary"       # FR-04-B
    REVIEW_REPORT = "review_report"               # FR-04-C
    QA_VALIDATION = "qa_validation"               # FR-04-D
    E2E_TEST = "e2e_test"                         # FR-04-E
    MIGRATION_COST = "migration_cost"             # FR-04-F
    VENDOR_COMPARISON = "vendor_comparison"        # FR-04-G
    RISK_HEATMAP = "risk_heatmap"                 # FR-04-H
    CONFIDENCE_INDEX = "confidence_index"          # FR-04-I


class ReportFormat(str, Enum):
    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    MARKDOWN = "markdown"


class Report(BaseModel):
    """Generated report base model."""

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    report_type: ReportType
    title: str
    format: ReportFormat = ReportFormat.JSON
    content: dict = Field(default_factory=dict, description="Report body (JSON)")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    asset_id: str
    tenant_id: str


class RiskScoreSet(BaseModel):
    """Risk score set for heatmap report."""

    overall_risk: float = Field(..., ge=0.0, le=1.0)
    complexity_score: float = Field(..., ge=0.0, le=1.0)
    effort_score: float = Field(..., ge=0.0, le=1.0)
    compatibility_score: float = Field(..., ge=0.0, le=1.0)
    category_risks: dict[str, float] = Field(default_factory=dict)


class MigrationCostEstimate(BaseModel):
    """Migration cost estimation model."""

    total_person_days: float
    breakdown: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
