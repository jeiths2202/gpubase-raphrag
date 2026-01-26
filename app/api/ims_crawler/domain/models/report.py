"""
Domain models for IMS report generation
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
from uuid import UUID


@dataclass
class ReportMetadata:
    """Metadata for generated report"""
    generated_at: datetime
    user_id: UUID
    title: str
    description: Optional[str] = None
    total_issues: int = 0
    date_range_start: Optional[datetime] = None
    date_range_end: Optional[datetime] = None
    filters_applied: Dict[str, str] = field(default_factory=dict)


@dataclass
class IssueSummary:
    """Summarized issue data for reports"""
    ims_id: str
    title: str
    status: str
    priority: str
    reporter: str
    assignee: Optional[str]
    created_at: datetime
    updated_at: datetime
    labels: List[str]
    similarity_score: Optional[float] = None


@dataclass
class ReportStatistics:
    """Statistical summary for report"""
    total_issues: int
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    by_project: Dict[str, int]
    avg_resolution_time_days: Optional[float] = None
    open_issues: int = 0
    closed_issues: int = 0
    critical_issues: int = 0
    high_priority_issues: int = 0


@dataclass
class MarkdownReport:
    """Complete markdown report"""
    metadata: ReportMetadata
    statistics: ReportStatistics
    issues: List[IssueSummary]
    markdown_content: str

    def to_filename(self) -> str:
        """Generate filename for report"""
        timestamp = self.metadata.generated_at.strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() else "_" for c in self.metadata.title)
        return f"ims_report_{safe_title}_{timestamp}.md"
