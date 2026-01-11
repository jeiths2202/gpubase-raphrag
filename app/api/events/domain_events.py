"""
Domain Events
Events that represent significant occurrences in the domain.
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid


class EventPriority(int, Enum):
    """Event processing priority"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class DomainEvent:
    """
    Base class for all domain events.

    Domain events represent something that happened in the domain that
    domain experts care about. They are used for decoupling services
    and enabling event-driven architecture.
    """

    # Event metadata
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    # Context
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    user_id: Optional[str] = None

    # Priority
    priority: EventPriority = EventPriority.NORMAL

    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_type:
            self.event_type = self.__class__.__name__

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "user_id": self.user_id,
            "priority": self.priority.value,
            "metadata": self.metadata,
            "data": self._get_data()
        }

    def _get_data(self) -> Dict[str, Any]:
        """Get event-specific data. Override in subclasses."""
        return {}


# ==================== Document Events ====================

@dataclass
class DocumentEvent(DomainEvent):
    """Base class for document-related events"""
    document_id: str = ""
    document_name: str = ""
    project_id: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "project_id": self.project_id
        }


@dataclass
class DocumentCreatedEvent(DocumentEvent):
    """Raised when a document is created"""
    file_size: int = 0
    mime_type: str = ""

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "file_size": self.file_size,
            "mime_type": self.mime_type
        })
        return data


@dataclass
class DocumentUpdatedEvent(DocumentEvent):
    """Raised when a document is updated"""
    changed_fields: List[str] = field(default_factory=list)

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data["changed_fields"] = self.changed_fields
        return data


@dataclass
class DocumentDeletedEvent(DocumentEvent):
    """Raised when a document is deleted"""
    soft_delete: bool = True

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data["soft_delete"] = self.soft_delete
        return data


@dataclass
class DocumentProcessedEvent(DocumentEvent):
    """Raised when document processing is complete"""
    chunk_count: int = 0
    total_tokens: int = 0
    processing_time_ms: int = 0
    success: bool = True
    error_message: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "chunk_count": self.chunk_count,
            "total_tokens": self.total_tokens,
            "processing_time_ms": self.processing_time_ms,
            "success": self.success,
            "error_message": self.error_message
        })
        return data


@dataclass
class DocumentIndexedEvent(DocumentEvent):
    """Raised when a document is indexed in vector store"""
    vector_count: int = 0
    collection: str = ""

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "vector_count": self.vector_count,
            "collection": self.collection
        })
        return data


# ==================== User Events ====================

@dataclass
class UserEvent(DomainEvent):
    """Base class for user-related events"""
    target_user_id: str = ""
    email: str = ""

    def _get_data(self) -> Dict[str, Any]:
        return {
            "target_user_id": self.target_user_id,
            "email": self.email
        }


@dataclass
class UserCreatedEvent(UserEvent):
    """Raised when a user is created"""
    username: str = ""
    role: str = "user"

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "username": self.username,
            "role": self.role
        })
        return data


@dataclass
class UserLoginEvent(UserEvent):
    """Raised when a user logs in"""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool = True
    failure_reason: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
            "failure_reason": self.failure_reason
        })
        return data


@dataclass
class UserPasswordChangedEvent(UserEvent):
    """Raised when a user changes their password"""
    forced: bool = False

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data["forced"] = self.forced
        return data


@dataclass
class UserMFAEnabledEvent(UserEvent):
    """Raised when a user enables MFA"""
    mfa_type: str = "totp"

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data["mfa_type"] = self.mfa_type
        return data


# ==================== Project Events ====================

@dataclass
class ProjectEvent(DomainEvent):
    """Base class for project-related events"""
    project_id: str = ""
    project_name: str = ""
    owner_id: str = ""

    def _get_data(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "owner_id": self.owner_id
        }


@dataclass
class ProjectCreatedEvent(ProjectEvent):
    """Raised when a project is created"""
    is_public: bool = False

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data["is_public"] = self.is_public
        return data


@dataclass
class ProjectMemberAddedEvent(ProjectEvent):
    """Raised when a member is added to a project"""
    member_id: str = ""
    role: str = ""
    invited_by: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "member_id": self.member_id,
            "role": self.role,
            "invited_by": self.invited_by
        })
        return data


# ==================== Query Events ====================

@dataclass
class QueryEvent(DomainEvent):
    """Base class for query-related events"""
    query_id: str = ""
    query_text: str = ""
    session_id: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text[:100],  # Truncate for logging
            "session_id": self.session_id
        }


@dataclass
class QueryExecutedEvent(QueryEvent):
    """Raised when a query is executed"""
    strategy: str = ""
    language: str = ""
    sources_count: int = 0
    processing_time_ms: int = 0
    tokens_used: int = 0
    success: bool = True
    error_message: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "strategy": self.strategy,
            "language": self.language,
            "sources_count": self.sources_count,
            "processing_time_ms": self.processing_time_ms,
            "tokens_used": self.tokens_used,
            "success": self.success,
            "error_message": self.error_message
        })
        return data


@dataclass
class QueryFeedbackEvent(QueryEvent):
    """Raised when feedback is given for a query"""
    message_id: str = ""
    score: int = 0
    feedback_text: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "message_id": self.message_id,
            "score": self.score,
            "feedback_text": self.feedback_text
        })
        return data


# ==================== External Resource Events ====================

@dataclass
class ExternalResourceEvent(DomainEvent):
    """Base class for external resource events"""
    resource_id: str = ""
    resource_type: str = ""
    source_name: str = ""

    def _get_data(self) -> Dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "source_name": self.source_name
        }


@dataclass
class ExternalResourceConnectedEvent(ExternalResourceEvent):
    """Raised when an external resource is connected"""
    oauth_provider: Optional[str] = None

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data["oauth_provider"] = self.oauth_provider
        return data


@dataclass
class ExternalResourceSyncedEvent(ExternalResourceEvent):
    """Raised when an external resource is synced"""
    documents_synced: int = 0
    documents_added: int = 0
    documents_updated: int = 0
    documents_deleted: int = 0

    def _get_data(self) -> Dict[str, Any]:
        data = super()._get_data()
        data.update({
            "documents_synced": self.documents_synced,
            "documents_added": self.documents_added,
            "documents_updated": self.documents_updated,
            "documents_deleted": self.documents_deleted
        })
        return data
