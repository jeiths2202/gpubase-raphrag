"""
Issue Entity - Core business entity representing an IMS issue

This is a rich domain model with business logic encapsulated within the entity.
No external dependencies - pure Python with dataclass.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4


class IssueStatus(str, Enum):
    """Issue status enumeration"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    PENDING = "pending"
    REJECTED = "rejected"


class IssuePriority(str, Enum):
    """Issue priority enumeration"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    TRIVIAL = "trivial"


@dataclass
class Issue:
    """
    Issue entity representing a single IMS issue.

    This entity encapsulates all business rules and invariants related to issues.
    All modifications to issue state should go through entity methods to maintain
    domain integrity.
    """

    # Identity
    id: UUID = field(default_factory=uuid4)
    ims_id: str = ""  # Original IMS system ID (e.g., "IMS-12345")

    # Core Attributes
    title: str = ""
    description: str = ""
    status: IssueStatus = IssueStatus.OPEN
    priority: IssuePriority = IssuePriority.MEDIUM
    status_raw: str = ""      # Raw status value from IMS (e.g., 'Closed_P', 'Rejected')
    priority_raw: str = ""    # Raw priority value from IMS (e.g., 'Normal', 'High', 'Very high')

    # IMS-specific fields (from TmaxSoft IMS)
    category: str = ""      # Category (e.g., Technical Support)
    product: str = ""       # Product (e.g., OpenFrame Base)
    version: str = ""       # Version (e.g., 7.3)
    module: str = ""        # Module (e.g., General)
    customer: str = ""      # Customer name
    issued_date: Optional[datetime] = None  # Issue registration date
    issue_details: str = ""  # Issue Details (상세 내용)
    action_no: str = ""      # Action No (액션 번호)
    action_log_text: str = ""  # Action Log 텍스트 내용 (모든 액션 로그 합침)

    # Metadata
    reporter: str = ""
    assignee: Optional[str] = None
    project_key: str = ""
    issue_type: str = "Task"

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    # Content
    labels: List[str] = field(default_factory=list)
    comments_count: int = 0
    attachments_count: int = 0
    attachments: List[Dict[str, Any]] = field(default_factory=list)  # List of attachment metadata

    # Crawling Metadata
    crawled_at: datetime = field(default_factory=datetime.utcnow)
    source_url: str = ""
    user_id: UUID = field(default_factory=uuid4)  # User who crawled this

    # Additional Fields (from IMS system)
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    # Related Issues (from IMS Related Issue tab and Patch List)
    related_issue_ids: List[str] = field(default_factory=list)  # IMS IDs of related issues

    def __post_init__(self):
        """Validate entity invariants after initialization"""
        if not self.ims_id:
            raise ValueError("Issue must have an IMS ID")
        if not self.title:
            raise ValueError("Issue must have a title")

    def update_status(self, new_status: IssueStatus) -> None:
        """
        Update issue status with business rules.

        Business Rule: When status changes to RESOLVED/CLOSED, set resolved_at timestamp.
        """
        self.status = new_status
        self.updated_at = datetime.utcnow()

        if new_status in (IssueStatus.RESOLVED, IssueStatus.CLOSED):
            if not self.resolved_at:
                self.resolved_at = datetime.utcnow()

    def assign_to(self, assignee: str) -> None:
        """Assign issue to a user"""
        self.assignee = assignee
        self.updated_at = datetime.utcnow()

    def add_label(self, label: str) -> None:
        """Add a label to the issue (idempotent)"""
        if label not in self.labels:
            self.labels.append(label)
            self.updated_at = datetime.utcnow()

    def remove_label(self, label: str) -> None:
        """Remove a label from the issue"""
        if label in self.labels:
            self.labels.remove(label)
            self.updated_at = datetime.utcnow()

    def is_resolved(self) -> bool:
        """Check if issue is in a resolved state"""
        return self.status in (IssueStatus.RESOLVED, IssueStatus.CLOSED)

    def is_critical(self) -> bool:
        """Check if issue has critical priority"""
        return self.priority == IssuePriority.CRITICAL

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for persistence"""
        return {
            "id": str(self.id),
            "ims_id": self.ims_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "status_raw": self.status_raw,
            "priority_raw": self.priority_raw,
            # IMS-specific fields
            "category": self.category,
            "product": self.product,
            "version": self.version,
            "module": self.module,
            "customer": self.customer,
            "issued_date": self.issued_date.isoformat() if self.issued_date else None,
            "issue_details": self.issue_details,
            "action_no": self.action_no,
            "action_log_text": self.action_log_text,
            # Metadata
            "reporter": self.reporter,
            "assignee": self.assignee,
            "project_key": self.project_key,
            "issue_type": self.issue_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "labels": self.labels,
            "comments_count": self.comments_count,
            "attachments_count": self.attachments_count,
            "crawled_at": self.crawled_at.isoformat(),
            "source_url": self.source_url,
            "user_id": str(self.user_id),
            "custom_fields": self.custom_fields,
            "related_issue_ids": self.related_issue_ids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Issue":
        """Create entity from dictionary (from persistence)"""
        return cls(
            id=UUID(data["id"]) if isinstance(data.get("id"), str) else data.get("id", uuid4()),
            ims_id=data["ims_id"],
            title=data["title"],
            description=data.get("description", ""),
            status=IssueStatus(data.get("status", "open")),
            priority=IssuePriority(data.get("priority", "medium")),
            status_raw=data.get("status_raw", ""),
            priority_raw=data.get("priority_raw", ""),
            # IMS-specific fields
            category=data.get("category", ""),
            product=data.get("product", ""),
            version=data.get("version", ""),
            module=data.get("module", ""),
            customer=data.get("customer", ""),
            issued_date=datetime.fromisoformat(data["issued_date"]) if data.get("issued_date") else None,
            issue_details=data.get("issue_details", ""),
            action_no=data.get("action_no", ""),
            action_log_text=data.get("action_log_text", ""),
            # Metadata
            reporter=data.get("reporter", ""),
            assignee=data.get("assignee"),
            project_key=data.get("project_key", ""),
            issue_type=data.get("issue_type", "Task"),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow()),
            updated_at=datetime.fromisoformat(data["updated_at"]) if isinstance(data.get("updated_at"), str) else data.get("updated_at", datetime.utcnow()),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            labels=data.get("labels", []),
            comments_count=data.get("comments_count", 0),
            attachments_count=data.get("attachments_count", 0),
            crawled_at=datetime.fromisoformat(data["crawled_at"]) if isinstance(data.get("crawled_at"), str) else data.get("crawled_at", datetime.utcnow()),
            source_url=data.get("source_url", ""),
            user_id=UUID(data["user_id"]) if isinstance(data.get("user_id"), str) else data.get("user_id", uuid4()),
            custom_fields=data.get("custom_fields", {}),
            related_issue_ids=data.get("related_issue_ids", []),
        )
