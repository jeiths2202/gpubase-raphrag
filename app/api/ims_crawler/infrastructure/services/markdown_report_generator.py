"""
Markdown report generator implementation
"""
from typing import List, Dict
from datetime import datetime
from collections import Counter

from app.api.ims_crawler.domain.ports.report_generator import ReportGeneratorPort
from app.api.ims_crawler.domain.models.report import (
    MarkdownReport,
    ReportMetadata,
    IssueSummary,
    ReportStatistics
)


class MarkdownReportGenerator(ReportGeneratorPort):
    """Generate markdown reports from IMS issues"""

    def generate_markdown(
        self,
        metadata: ReportMetadata,
        issues: List[IssueSummary]
    ) -> MarkdownReport:
        """Generate complete markdown report"""

        statistics = self._calculate_statistics(issues)

        sections = [
            self._generate_header(metadata),
            self._generate_metadata_section(metadata),
            self.generate_statistics_section(issues),
            self.generate_summary_charts(issues),
            self._generate_detailed_issues_section(issues),
            self._generate_footer()
        ]

        markdown_content = "\n\n".join(sections)

        return MarkdownReport(
            metadata=metadata,
            statistics=statistics,
            issues=issues,
            markdown_content=markdown_content
        )

    def _generate_header(self, metadata: ReportMetadata) -> str:
        """Generate report header"""
        return f"""# {metadata.title}

> **Generated**: {metadata.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")}
> **Report ID**: `{metadata.user_id}`

{metadata.description or "IMS Issues Analysis Report"}"""

    def _generate_metadata_section(self, metadata: ReportMetadata) -> str:
        """Generate metadata section"""
        lines = ["## Report Metadata", ""]

        lines.append(f"- **Total Issues**: {metadata.total_issues}")

        if metadata.date_range_start and metadata.date_range_end:
            lines.append(f"- **Date Range**: {metadata.date_range_start.strftime('%Y-%m-%d')} to {metadata.date_range_end.strftime('%Y-%m-%d')}")

        if metadata.filters_applied:
            lines.append("- **Filters Applied**:")
            for key, value in metadata.filters_applied.items():
                lines.append(f"  - {key}: `{value}`")

        return "\n".join(lines)

    def generate_statistics_section(self, issues: List[IssueSummary]) -> str:
        """Generate statistics section"""
        stats = self._calculate_statistics(issues)

        lines = [
            "## Summary Statistics",
            "",
            f"- **Total Issues**: {stats.total_issues}",
            f"- **Open Issues**: {stats.open_issues}",
            f"- **Closed Issues**: {stats.closed_issues}",
            f"- **Critical Issues**: {stats.critical_issues}",
            f"- **High Priority Issues**: {stats.high_priority_issues}",
            ""
        ]

        # Status breakdown
        if stats.by_status:
            lines.append("### By Status")
            lines.append("")
            for status, count in sorted(stats.by_status.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / stats.total_issues * 100) if stats.total_issues > 0 else 0
                lines.append(f"- **{status}**: {count} ({percentage:.1f}%)")
            lines.append("")

        # Priority breakdown
        if stats.by_priority:
            lines.append("### By Priority")
            lines.append("")
            priority_order = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
            sorted_priorities = sorted(
                stats.by_priority.items(),
                key=lambda x: priority_order.get(x[0].upper(), 99)
            )
            for priority, count in sorted_priorities:
                percentage = (count / stats.total_issues * 100) if stats.total_issues > 0 else 0
                lines.append(f"- **{priority}**: {count} ({percentage:.1f}%)")
            lines.append("")

        # Project breakdown
        if stats.by_project:
            lines.append("### By Project")
            lines.append("")
            for project, count in sorted(stats.by_project.items(), key=lambda x: x[1], reverse=True)[:10]:
                percentage = (count / stats.total_issues * 100) if stats.total_issues > 0 else 0
                lines.append(f"- **{project}**: {count} ({percentage:.1f}%)")
            lines.append("")

        return "\n".join(lines)

    def generate_summary_charts(self, issues: List[IssueSummary]) -> str:
        """Generate text-based charts"""
        lines = ["## Visual Summary", ""]

        # Status chart
        status_counts = Counter(issue.status for issue in issues)
        if status_counts:
            lines.append("### Status Distribution")
            lines.append("```")
            max_count = max(status_counts.values())
            for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
                bar_length = int((count / max_count) * 40) if max_count > 0 else 0
                bar = "█" * bar_length
                lines.append(f"{status:15} {bar} {count}")
            lines.append("```")
            lines.append("")

        # Priority chart
        priority_counts = Counter(issue.priority for issue in issues)
        if priority_counts:
            lines.append("### Priority Distribution")
            lines.append("```")
            max_count = max(priority_counts.values())
            priority_order = {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 3, "LOW": 4}
            sorted_priorities = sorted(
                priority_counts.items(),
                key=lambda x: priority_order.get(x[0].upper(), 99)
            )
            for priority, count in sorted_priorities:
                bar_length = int((count / max_count) * 40) if max_count > 0 else 0
                bar = "█" * bar_length
                lines.append(f"{priority:15} {bar} {count}")
            lines.append("```")
            lines.append("")

        return "\n".join(lines)

    def generate_issues_table(self, issues: List[IssueSummary]) -> str:
        """Generate issues table"""
        if not issues:
            return "_No issues to display_"

        lines = [
            "| ID | Title | Status | Priority | Reporter | Created | Updated |",
            "|:---|:------|:-------|:---------|:---------|:--------|:--------|"
        ]

        for issue in issues[:100]:  # Limit to 100 for readability
            title = issue.title[:50] + "..." if len(issue.title) > 50 else issue.title
            title = title.replace("|", "\\|")  # Escape pipe characters

            created = issue.created_at.strftime("%Y-%m-%d")
            updated = issue.updated_at.strftime("%Y-%m-%d")

            lines.append(
                f"| {issue.ims_id} | {title} | {issue.status} | "
                f"{issue.priority} | {issue.reporter} | {created} | {updated} |"
            )

        if len(issues) > 100:
            lines.append("")
            lines.append(f"_... and {len(issues) - 100} more issues_")

        return "\n".join(lines)

    def _generate_detailed_issues_section(self, issues: List[IssueSummary]) -> str:
        """Generate detailed issues section"""
        lines = [
            "## Detailed Issues",
            "",
            self.generate_issues_table(issues)
        ]

        return "\n".join(lines)

    def _generate_footer(self) -> str:
        """Generate report footer"""
        return f"""---

_Report generated by IMS Crawler - HybridRAG KMS_
_Generation timestamp: {datetime.utcnow().isoformat()}Z_"""

    def _calculate_statistics(self, issues: List[IssueSummary]) -> ReportStatistics:
        """Calculate statistics from issues"""

        status_counts = Counter(issue.status for issue in issues)
        priority_counts = Counter(issue.priority for issue in issues)

        # Extract project keys from IMS IDs (e.g., "PROJ-123" -> "PROJ")
        project_keys = [issue.ims_id.split('-')[0] if '-' in issue.ims_id else 'UNKNOWN' for issue in issues]
        project_counts = Counter(project_keys)

        open_issues = sum(
            count for status, count in status_counts.items()
            if status.upper() in ['OPEN', 'IN_PROGRESS', 'PENDING']
        )

        closed_issues = sum(
            count for status, count in status_counts.items()
            if status.upper() in ['CLOSED', 'RESOLVED', 'DONE']
        )

        critical_issues = priority_counts.get('CRITICAL', 0) + priority_counts.get('critical', 0)
        high_priority_issues = priority_counts.get('HIGH', 0) + priority_counts.get('high', 0)

        return ReportStatistics(
            total_issues=len(issues),
            by_status=dict(status_counts),
            by_priority=dict(priority_counts),
            by_project=dict(project_counts),
            open_issues=open_issues,
            closed_issues=closed_issues,
            critical_issues=critical_issues,
            high_priority_issues=high_priority_issues
        )
