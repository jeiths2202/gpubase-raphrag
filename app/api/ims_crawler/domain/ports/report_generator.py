"""
Port for report generation service
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime

from app.api.ims_crawler.domain.models.report import MarkdownReport, ReportMetadata, IssueSummary


class ReportGeneratorPort(ABC):
    """Interface for report generation"""

    @abstractmethod
    def generate_markdown(
        self,
        metadata: ReportMetadata,
        issues: List[IssueSummary]
    ) -> MarkdownReport:
        """
        Generate markdown report from issues

        Args:
            metadata: Report metadata
            issues: List of issues to include

        Returns:
            Complete markdown report
        """
        pass

    @abstractmethod
    def generate_statistics_section(
        self,
        issues: List[IssueSummary]
    ) -> str:
        """Generate statistics markdown section"""
        pass

    @abstractmethod
    def generate_issues_table(
        self,
        issues: List[IssueSummary]
    ) -> str:
        """Generate issues table markdown"""
        pass

    @abstractmethod
    def generate_summary_charts(
        self,
        issues: List[IssueSummary]
    ) -> str:
        """Generate text-based charts for summary"""
        pass
