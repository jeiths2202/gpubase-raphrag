"""
Domain models for IMS dashboard statistics
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID


@dataclass
class TrendData:
    """Time-series trend data"""
    date: datetime
    count: int


@dataclass
class ActivityMetrics:
    """User activity metrics"""
    total_crawls: int
    total_issues_crawled: int
    total_attachments: int
    last_crawl_date: Optional[datetime] = None
    avg_issues_per_crawl: float = 0.0


@dataclass
class IssueMetrics:
    """Issue-related metrics"""
    total_issues: int
    open_issues: int
    closed_issues: int
    critical_issues: int
    high_priority_issues: int
    resolution_rate: float
    avg_resolution_time_days: Optional[float] = None


@dataclass
class ProjectMetrics:
    """Project-level metrics"""
    project_key: str
    total_issues: int
    open_issues: int
    closed_issues: int
    critical_issues: int
    last_updated: datetime


@dataclass
class TopReporter:
    """Top issue reporter statistics"""
    reporter: str
    issue_count: int
    critical_count: int
    open_count: int


@dataclass
class DashboardStatistics:
    """Complete dashboard statistics"""
    user_id: UUID
    generated_at: datetime
    activity_metrics: ActivityMetrics
    issue_metrics: IssueMetrics
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    top_projects: List[ProjectMetrics]
    top_reporters: List[TopReporter]
    issue_trend_7days: List[TrendData]
    issue_trend_30days: List[TrendData]
    status_trend: Dict[str, List[TrendData]]
