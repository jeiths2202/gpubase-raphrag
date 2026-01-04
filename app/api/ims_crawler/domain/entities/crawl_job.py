"""
Crawl Job Entity - Represents a crawling operation with progress tracking
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4


class CrawlJobStatus(str, Enum):
    """Crawl job status enumeration"""
    PENDING = "pending"
    AUTHENTICATING = "authenticating"
    PARSING_QUERY = "parsing_query"
    CRAWLING = "crawling"
    PROCESSING_ATTACHMENTS = "processing_attachments"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CrawlJob:
    """
    Crawl Job entity representing a single crawling operation.

    Tracks progress, errors, and statistics for real-time SSE streaming.
    """

    # Identity
    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)

    # Query Information
    raw_query: str = ""  # User's natural language input
    parsed_query: Optional[str] = None  # Converted IMS syntax
    search_intent: Optional[str] = None  # Detected intent type

    # Status
    status: CrawlJobStatus = CrawlJobStatus.PENDING
    current_step: str = "Initializing..."
    progress_percentage: int = 0

    # Results
    issues_found: int = 0
    issues_crawled: int = 0
    attachments_processed: int = 0
    related_issues_crawled: int = 0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Error Handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Configuration
    include_attachments: bool = True
    include_related_issues: bool = True
    max_issues: int = 100

    # Results Storage
    result_issue_ids: List[UUID] = field(default_factory=list)

    def __post_init__(self):
        """Validate entity invariants"""
        if not self.raw_query:
            raise ValueError("Crawl job must have a query")

    def start(self) -> None:
        """Mark job as started"""
        self.status = CrawlJobStatus.AUTHENTICATING
        self.started_at = datetime.utcnow()
        self.current_step = "Authenticating with IMS system..."
        self.progress_percentage = 5

    def update_progress(self, status: CrawlJobStatus, step: str, percentage: int) -> None:
        """Update job progress for SSE streaming"""
        self.status = status
        self.current_step = step
        self.progress_percentage = min(percentage, 100)

    def add_crawled_issue(self, issue_id: UUID) -> None:
        """Add a successfully crawled issue to results"""
        self.result_issue_ids.append(issue_id)
        self.issues_crawled += 1

    def mark_as_completed(self) -> None:
        """Mark job as successfully completed"""
        self.status = CrawlJobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.progress_percentage = 100
        self.current_step = f"Completed: {self.issues_crawled} issues crawled"

    def mark_as_failed(self, error: str) -> None:
        """Mark job as failed with error message"""
        self.status = CrawlJobStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error
        self.current_step = f"Failed: {error}"

    def can_retry(self) -> bool:
        """Check if job can be retried"""
        return self.status == CrawlJobStatus.FAILED and self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry count"""
        self.retry_count += 1

    def is_terminal_state(self) -> bool:
        """Check if job is in a terminal state (completed/failed/cancelled)"""
        return self.status in (
            CrawlJobStatus.COMPLETED,
            CrawlJobStatus.FAILED,
            CrawlJobStatus.CANCELLED
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for persistence and SSE streaming"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "raw_query": self.raw_query,
            "parsed_query": self.parsed_query,
            "search_intent": self.search_intent,
            "status": self.status.value,
            "current_step": self.current_step,
            "progress_percentage": self.progress_percentage,
            "issues_found": self.issues_found,
            "issues_crawled": self.issues_crawled,
            "attachments_processed": self.attachments_processed,
            "related_issues_crawled": self.related_issues_crawled,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "include_attachments": self.include_attachments,
            "include_related_issues": self.include_related_issues,
            "max_issues": self.max_issues,
            "result_issue_ids": [str(iid) for iid in self.result_issue_ids],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CrawlJob":
        """Create entity from dictionary"""
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            user_id=UUID(data["user_id"]) if isinstance(data.get("user_id"), str) else data.get("user_id", uuid4()),
            raw_query=data["raw_query"],
            parsed_query=data.get("parsed_query"),
            search_intent=data.get("search_intent"),
            status=CrawlJobStatus(data.get("status", "pending")),
            current_step=data.get("current_step", "Initializing..."),
            progress_percentage=data.get("progress_percentage", 0),
            issues_found=data.get("issues_found", 0),
            issues_crawled=data.get("issues_crawled", 0),
            attachments_processed=data.get("attachments_processed", 0),
            related_issues_crawled=data.get("related_issues_crawled", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow()),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            include_attachments=data.get("include_attachments", True),
            include_related_issues=data.get("include_related_issues", True),
            max_issues=data.get("max_issues", 100),
            result_issue_ids=[UUID(iid) for iid in data.get("result_issue_ids", [])],
        )
