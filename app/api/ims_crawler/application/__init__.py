"""
Application Layer - Use Cases and Application Services

Orchestrates business logic by coordinating domain entities and infrastructure adapters.
Contains no business rules (those live in domain) and no infrastructure details (those live in adapters).
"""

from .use_cases.search_issues import SearchIssuesUseCase
from .use_cases.crawl_jobs import CrawlJobsUseCase
from .use_cases.manage_credentials import ManageCredentialsUseCase
from .use_cases.generate_report import GenerateReportUseCase
from .use_cases.get_dashboard_statistics import GetDashboardStatisticsUseCase

__all__ = [
    "SearchIssuesUseCase",
    "CrawlJobsUseCase",
    "ManageCredentialsUseCase",
    "GenerateReportUseCase",
    "GetDashboardStatisticsUseCase",
]
