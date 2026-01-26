"""
API router for IMS report generation
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.core.deps import get_current_user
from app.api.ims_crawler.infrastructure.dependencies import get_report_generator_use_case


router = APIRouter(prefix="/ims-reports", tags=["IMS Reports"])


class GenerateReportRequest(BaseModel):
    """Request model for report generation"""
    title: str = Field(default="IMS Issues Report", description="Report title")
    description: Optional[str] = Field(None, description="Report description")
    date_range_start: Optional[datetime] = Field(None, description="Filter issues from this date")
    date_range_end: Optional[datetime] = Field(None, description="Filter issues until this date")
    status_filter: Optional[str] = Field(None, description="Filter by status")
    priority_filter: Optional[str] = Field(None, description="Filter by priority")
    max_issues: int = Field(1000, ge=1, le=10000, description="Maximum issues to include")


class ReportResponse(BaseModel):
    """Response model for generated report"""
    filename: str
    total_issues: int
    generated_at: datetime
    download_url: str


@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    request: GenerateReportRequest,
    current_user: dict = Depends(get_current_user),
    use_case = Depends(get_report_generator_use_case)
):
    """
    Generate markdown report for user's IMS issues

    - **title**: Report title
    - **description**: Optional description
    - **date_range_start**: Filter issues from this date
    - **date_range_end**: Filter issues until this date
    - **status_filter**: Filter by status (e.g., "OPEN", "CLOSED")
    - **priority_filter**: Filter by priority (e.g., "CRITICAL", "HIGH")
    - **max_issues**: Maximum number of issues to include (1-10000)
    """

    user_id = UUID(current_user["id"])

    try:
        report = await use_case.generate_report(
            user_id=user_id,
            title=request.title,
            description=request.description,
            date_range_start=request.date_range_start,
            date_range_end=request.date_range_end,
            status_filter=request.status_filter,
            priority_filter=request.priority_filter,
            max_issues=request.max_issues
        )

        filename = report.to_filename()

        return ReportResponse(
            filename=filename,
            total_issues=report.metadata.total_issues,
            generated_at=report.metadata.generated_at,
            download_url=f"/api/v1/ims-reports/download?filename={filename}"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.post("/generate-download")
async def generate_and_download_report(
    request: GenerateReportRequest,
    current_user: dict = Depends(get_current_user),
    use_case = Depends(get_report_generator_use_case)
):
    """
    Generate markdown report and download immediately

    Returns the markdown file directly as a download
    """

    user_id = UUID(current_user["id"])

    try:
        report = await use_case.generate_report(
            user_id=user_id,
            title=request.title,
            description=request.description,
            date_range_start=request.date_range_start,
            date_range_end=request.date_range_end,
            status_filter=request.status_filter,
            priority_filter=request.priority_filter,
            max_issues=request.max_issues
        )

        filename = report.to_filename()

        return Response(
            content=report.markdown_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "text/markdown; charset=utf-8"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/quick-summary")
async def get_quick_summary(
    current_user: dict = Depends(get_current_user),
    use_case = Depends(get_report_generator_use_case)
):
    """
    Get quick statistics summary without generating full report

    Returns basic statistics about user's issues
    """

    user_id = UUID(current_user["id"])

    try:
        report = await use_case.generate_report(
            user_id=user_id,
            title="Quick Summary",
            max_issues=10000
        )

        return {
            "total_issues": report.statistics.total_issues,
            "open_issues": report.statistics.open_issues,
            "closed_issues": report.statistics.closed_issues,
            "critical_issues": report.statistics.critical_issues,
            "high_priority_issues": report.statistics.high_priority_issues,
            "by_status": report.statistics.by_status,
            "by_priority": report.statistics.by_priority,
            "by_project": report.statistics.by_project
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")
