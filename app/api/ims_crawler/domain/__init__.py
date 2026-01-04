"""
Domain Layer - Business Entities and Domain Logic

Contains pure business logic with no external dependencies.
All entities represent core business concepts in the IMS domain.
"""

from .entities.issue import Issue, IssueStatus, IssuePriority
from .entities.attachment import Attachment, AttachmentType
from .entities.crawl_job import CrawlJob, CrawlJobStatus
from .entities.user_credentials import UserCredentials
from .value_objects.search_intent import SearchIntent, SearchIntentType
from .value_objects.view_mode import ViewMode

__all__ = [
    "Issue",
    "IssueStatus",
    "IssuePriority",
    "Attachment",
    "AttachmentType",
    "CrawlJob",
    "CrawlJobStatus",
    "UserCredentials",
    "SearchIntent",
    "SearchIntentType",
    "ViewMode",
]
