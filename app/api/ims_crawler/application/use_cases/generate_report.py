"""
Use case for generating IMS reports
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from app.api.ims_crawler.infrastructure.ports.issue_repository_port import IssueRepositoryPort
from app.api.ims_crawler.domain.ports.report_generator import ReportGeneratorPort
from app.api.ims_crawler.domain.models.report import (
    MarkdownReport,
    ReportMetadata,
    IssueSummary
)
from app.api.ims_crawler.domain.entities.issue import Issue


class GenerateReportUseCase:
    """Use case for generating markdown reports"""

    def __init__(
        self,
        issue_repository: IssueRepositoryPort,
        report_generator: ReportGeneratorPort
    ):
        self.issue_repository = issue_repository
        self.report_generator = report_generator

    async def generate_report(
        self,
        user_id: UUID,
        title: str = "IMS Issues Report",
        description: Optional[str] = None,
        date_range_start: Optional[datetime] = None,
        date_range_end: Optional[datetime] = None,
        status_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        max_issues: int = 1000
    ) -> MarkdownReport:
        """
        Generate markdown report for user's issues

        Args:
            user_id: User ID
            title: Report title
            description: Report description
            date_range_start: Filter issues from this date
            date_range_end: Filter issues until this date
            status_filter: Filter by status
            priority_filter: Filter by priority
            max_issues: Maximum issues to include

        Returns:
            Generated markdown report
        """

        # Fetch issues
        issues = await self.issue_repository.find_by_user_id(user_id, limit=max_issues)

        # Apply filters
        filtered_issues = self._apply_filters(
            issues,
            date_range_start,
            date_range_end,
            status_filter,
            priority_filter
        )

        # Convert to summaries
        issue_summaries = [self._issue_to_summary(issue) for issue in filtered_issues]

        # Create metadata
        filters_applied = {}
        if status_filter:
            filters_applied['status'] = status_filter
        if priority_filter:
            filters_applied['priority'] = priority_filter

        metadata = ReportMetadata(
            generated_at=datetime.utcnow(),
            user_id=user_id,
            title=title,
            description=description,
            total_issues=len(issue_summaries),
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            filters_applied=filters_applied
        )

        # Generate report
        report = self.report_generator.generate_markdown(metadata, issue_summaries)

        return report

    async def generate_search_results_report(
        self,
        user_id: UUID,
        search_query: str,
        issues: List[Issue]
    ) -> MarkdownReport:
        """
        Generate report from search results

        Args:
            user_id: User ID
            search_query: Original search query
            issues: Search result issues

        Returns:
            Generated markdown report
        """

        issue_summaries = [self._issue_to_summary(issue) for issue in issues]

        metadata = ReportMetadata(
            generated_at=datetime.utcnow(),
            user_id=user_id,
            title=f"Search Results: {search_query}",
            description=f"Issues matching query: '{search_query}'",
            total_issues=len(issue_summaries),
            filters_applied={'search_query': search_query}
        )

        report = self.report_generator.generate_markdown(metadata, issue_summaries)

        return report

    def _apply_filters(
        self,
        issues: List[Issue],
        date_range_start: Optional[datetime],
        date_range_end: Optional[datetime],
        status_filter: Optional[str],
        priority_filter: Optional[str]
    ) -> List[Issue]:
        """Apply filters to issues list"""

        filtered = issues

        if date_range_start:
            filtered = [
                issue for issue in filtered
                if issue.created_at >= date_range_start
            ]

        if date_range_end:
            filtered = [
                issue for issue in filtered
                if issue.created_at <= date_range_end
            ]

        if status_filter:
            filtered = [
                issue for issue in filtered
                if issue.status.upper() == status_filter.upper()
            ]

        if priority_filter:
            filtered = [
                issue for issue in filtered
                if issue.priority.upper() == priority_filter.upper()
            ]

        return filtered

    def _issue_to_summary(self, issue: Issue) -> IssueSummary:
        """Convert Issue to IssueSummary"""
        return IssueSummary(
            ims_id=issue.ims_id,
            title=issue.title,
            status=issue.status,
            priority=issue.priority,
            reporter=issue.reporter,
            assignee=issue.assignee,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            labels=issue.labels,
            similarity_score=getattr(issue, 'similarity_score', None)
        )
