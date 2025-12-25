"""
Notification models for the Knowledge Management System
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class NotificationType(str, Enum):
    """Types of notifications"""
    # Knowledge workflow
    KNOWLEDGE_SUBMITTED = "knowledge_submitted"     # New knowledge submitted for review
    REVIEW_REQUESTED = "review_requested"           # Review assigned to reviewer
    REVIEW_COMPLETED = "review_completed"           # Review completed (approved/rejected)
    KNOWLEDGE_PUBLISHED = "knowledge_published"     # Knowledge published
    CHANGES_REQUESTED = "changes_requested"         # Reviewer requested changes

    # Recommendations
    RECOMMENDATION_RECEIVED = "recommendation_received"  # Someone recommended your knowledge
    RECOMMENDATION_MILESTONE = "recommendation_milestone"  # Reached recommendation milestone

    # System
    SYSTEM_ANNOUNCEMENT = "system_announcement"     # System-wide announcement
    ROLE_CHANGED = "role_changed"                   # User role changed


class NotificationPriority(str, Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, Enum):
    """Notification delivery channels"""
    IN_APP = "in_app"
    EMAIL = "email"
    BOTH = "both"


# Notification i18n templates
NOTIFICATION_TEMPLATES = {
    NotificationType.KNOWLEDGE_SUBMITTED: {
        "ko": {
            "title": "새 지식 등록",
            "message": "{author_name}님이 '{knowledge_title}' 지식을 등록했습니다."
        },
        "ja": {
            "title": "新しい知識の登録",
            "message": "{author_name}さんが「{knowledge_title}」を登録しました。"
        },
        "en": {
            "title": "New Knowledge Submitted",
            "message": "{author_name} submitted '{knowledge_title}'."
        }
    },
    NotificationType.REVIEW_REQUESTED: {
        "ko": {
            "title": "검수 요청",
            "message": "'{knowledge_title}' 지식에 대한 검수가 요청되었습니다."
        },
        "ja": {
            "title": "レビュー依頼",
            "message": "「{knowledge_title}」のレビューが依頼されました。"
        },
        "en": {
            "title": "Review Requested",
            "message": "Review requested for '{knowledge_title}'."
        }
    },
    NotificationType.REVIEW_COMPLETED: {
        "ko": {
            "title": "검수 완료",
            "message": "'{knowledge_title}' 지식이 {action} 되었습니다."
        },
        "ja": {
            "title": "レビュー完了",
            "message": "「{knowledge_title}」が{action}されました。"
        },
        "en": {
            "title": "Review Completed",
            "message": "'{knowledge_title}' has been {action}."
        }
    },
    NotificationType.KNOWLEDGE_PUBLISHED: {
        "ko": {
            "title": "지식 게시됨",
            "message": "'{knowledge_title}' 지식이 게시되었습니다."
        },
        "ja": {
            "title": "知識公開",
            "message": "「{knowledge_title}」が公開されました。"
        },
        "en": {
            "title": "Knowledge Published",
            "message": "'{knowledge_title}' has been published."
        }
    },
    NotificationType.CHANGES_REQUESTED: {
        "ko": {
            "title": "수정 요청",
            "message": "'{knowledge_title}' 지식에 수정이 요청되었습니다."
        },
        "ja": {
            "title": "修正依頼",
            "message": "「{knowledge_title}」の修正が依頼されました。"
        },
        "en": {
            "title": "Changes Requested",
            "message": "Changes requested for '{knowledge_title}'."
        }
    },
    NotificationType.RECOMMENDATION_RECEIVED: {
        "ko": {
            "title": "추천 받음",
            "message": "'{knowledge_title}' 지식이 추천을 받았습니다."
        },
        "ja": {
            "title": "推薦を受けました",
            "message": "「{knowledge_title}」が推薦されました。"
        },
        "en": {
            "title": "Recommendation Received",
            "message": "'{knowledge_title}' received a recommendation."
        }
    }
}


class Notification(BaseModel):
    """Notification model"""
    id: str

    # Target user
    user_id: str

    # Notification content
    type: NotificationType
    title: str
    message: str

    # Metadata for navigation
    reference_type: Optional[str] = None  # "knowledge", "user", etc.
    reference_id: Optional[str] = None

    # Additional data
    data: Dict[str, Any] = {}

    # Status
    is_read: bool = False
    read_at: Optional[datetime] = None

    # Priority
    priority: NotificationPriority = NotificationPriority.NORMAL

    # Channel
    channel: NotificationChannel = NotificationChannel.IN_APP
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class NotificationPreferences(BaseModel):
    """User notification preferences"""
    user_id: str

    # Email preferences
    email_enabled: bool = True
    email_knowledge_submitted: bool = True
    email_review_requested: bool = True
    email_review_completed: bool = True
    email_recommendations: bool = False

    # In-app preferences
    in_app_enabled: bool = True

    # Language preference
    preferred_language: str = "ko"


# Request/Response models

class NotificationListRequest(BaseModel):
    """List notifications request"""
    is_read: Optional[bool] = None
    type: Optional[NotificationType] = None
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=100)


class NotificationListResponse(BaseModel):
    """Notification list response"""
    notifications: List[Notification]
    total: int
    unread_count: int
    page: int
    limit: int


class MarkReadRequest(BaseModel):
    """Mark notifications as read"""
    notification_ids: List[str]


class NotificationCountResponse(BaseModel):
    """Unread notification count"""
    unread_count: int
    by_type: Dict[str, int] = {}


class CreateNotificationRequest(BaseModel):
    """Create notification (internal use)"""
    user_id: str
    type: NotificationType
    title: str
    message: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    data: Dict[str, Any] = {}
    priority: NotificationPriority = NotificationPriority.NORMAL
    channel: NotificationChannel = NotificationChannel.IN_APP


class BroadcastNotificationRequest(BaseModel):
    """Broadcast notification to multiple users"""
    user_ids: List[str]  # Empty list means all users
    role_filter: Optional[str] = None  # Filter by role (senior, leader, etc.)
    type: NotificationType
    title: str
    message: str
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    data: Dict[str, Any] = {}
    priority: NotificationPriority = NotificationPriority.NORMAL
    channel: NotificationChannel = NotificationChannel.BOTH
