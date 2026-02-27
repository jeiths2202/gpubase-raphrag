"""Reports API Router — GET /reports/{analysis_id}, GET /reports/{id}/{type}.

Endpoints:
  GET  /api/v1/legacy/reports/{analysis_id}              — List all reports
  GET  /api/v1/legacy/reports/{analysis_id}/{report_type} — Get specific report
"""

import logging

from fastapi import APIRouter, HTTPException

from ..models.reports import ReportType
from ..services.analysis_service import get_analysis_service
from .schemas import ReportListResponse, ReportResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legacy/reports", tags=["Legacy Reports"])


@router.get(
    "/{analysis_id}",
    response_model=ReportListResponse,
    summary="List available reports",
    description="Returns a summary of all generated reports for an analysis.",
)
async def list_reports(analysis_id: str) -> ReportListResponse:
    """List all available reports for a completed analysis."""
    service = get_analysis_service()
    results = await service.get_results(analysis_id)

    if "error" in results:
        raise HTTPException(status_code=404, detail="Analysis not found")

    reports_data = results.get("reports", {})
    report_summaries = []
    for rt_str, rpt in reports_data.items():
        report_summaries.append({
            "report_type": rt_str,
            "title": rpt.get("title", ""),
            "generated_at": rpt.get("generated_at", ""),
            "report_id": rpt.get("report_id", ""),
        })

    return ReportListResponse(
        analysis_id=analysis_id,
        reports=report_summaries,
    )


@router.get(
    "/{analysis_id}/{report_type}",
    response_model=ReportResponse,
    summary="Get specific report",
    description="Returns full report content by type.",
)
async def get_report(
    analysis_id: str,
    report_type: str,
) -> ReportResponse:
    """Get a specific report by type.

    Valid report_type values:
      technical_findings, executive_summary, review_report,
      qa_validation, e2e_test, migration_cost, vendor_comparison,
      risk_heatmap, confidence_index
    """
    # Validate report type
    try:
        rt = ReportType(report_type)
    except ValueError:
        valid_types = [t.value for t in ReportType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report_type '{report_type}'. Valid: {valid_types}",
        )

    service = get_analysis_service()
    report = await service.get_report(analysis_id, rt)

    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report '{report_type}' not found for analysis {analysis_id}",
        )

    return ReportResponse(
        report_id=report.report_id,
        report_type=report.report_type.value,
        title=report.title,
        format=report.format.value,
        content=report.content,
        generated_at=report.generated_at.isoformat(),
        asset_id=report.asset_id,
        tenant_id=report.tenant_id,
    )
