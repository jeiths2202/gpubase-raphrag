"""
Notification Service for the Knowledge Management System
Handles in-app notifications and email notifications (mock)
"""
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from ..models.notification import (
    Notification, NotificationType, NotificationPriority,
    NotificationChannel, NotificationPreferences,
    NOTIFICATION_TEMPLATES
)
from ..models.auth import UserRole, can_review


class NotificationService:
    """Service for managing notifications"""

    # In-memory storage (replace with PostgreSQL in production)
    _notifications: Dict[str, Notification] = {}
    _preferences: Dict[str, NotificationPreferences] = {}

    # User lookup should be done via AuthService, not hardcoded mock users
    # SECURITY: No hardcoded mock users - use proper user database/service
    _users: Dict[str, dict] = {}

    async def create_notification(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        data: Dict[str, Any] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channel: NotificationChannel = NotificationChannel.IN_APP
    ) -> Notification:
        """Create a new notification"""
        notification_id = f"notif_{uuid.uuid4().hex[:12]}"

        notification = Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=title,
            message=message,
            reference_type=reference_type,
            reference_id=reference_id,
            data=data or {},
            priority=priority,
            channel=channel
        )

        self._notifications[notification_id] = notification

        # Send email if channel includes email
        if channel in [NotificationChannel.EMAIL, NotificationChannel.BOTH]:
            await self._send_email_notification(notification)

        return notification

    async def _send_email_notification(self, notification: Notification) -> bool:
        """Send email notification (mock implementation)"""
        user = self._users.get(notification.user_id)
        if not user or "email" not in user:
            return False

        print(f"[EMAIL MOCK] Sending to {user['email']}")
        print(f"[EMAIL MOCK] Subject: {notification.title}")
        print(f"[EMAIL MOCK] Body: {notification.message}")

        notification.email_sent = True
        notification.email_sent_at = datetime.now(timezone.utc)
        self._notifications[notification.id] = notification

        return True

    async def create_from_template(
        self,
        user_id: str,
        notification_type: NotificationType,
        language: str = "ko",
        template_vars: Dict[str, str] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channel: NotificationChannel = NotificationChannel.IN_APP
    ) -> Notification:
        """Create notification from template with i18n support"""
        template = NOTIFICATION_TEMPLATES.get(notification_type, {})
        lang_template = template.get(language, template.get("en", {}))

        title = lang_template.get("title", str(notification_type))
        message = lang_template.get("message", "")

        # Replace template variables
        if template_vars:
            for key, value in template_vars.items():
                title = title.replace(f"{{{key}}}", value)
                message = message.replace(f"{{{key}}}", value)

        return await self.create_notification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            reference_type=reference_type,
            reference_id=reference_id,
            data=template_vars,
            priority=priority,
            channel=channel
        )

    async def broadcast_notification(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        user_ids: List[str] = None,
        role_filter: Optional[str] = None,
        reference_type: Optional[str] = None,
        reference_id: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        channel: NotificationChannel = NotificationChannel.IN_APP
    ) -> List[Notification]:
        """Broadcast notification to multiple users"""
        notifications = []

        # Determine target users
        if user_ids:
            target_users = [self._users[uid] for uid in user_ids if uid in self._users]
        else:
            target_users = list(self._users.values())

        # Apply role filter
        if role_filter:
            target_users = [
                u for u in target_users
                if u.get("role") == role_filter or can_review(u.get("role", "user"))
            ]

        for user in target_users:
            notification = await self.create_notification(
                user_id=user["id"],
                notification_type=notification_type,
                title=title,
                message=message,
                reference_type=reference_type,
                reference_id=reference_id,
                priority=priority,
                channel=channel
            )
            notifications.append(notification)

        return notifications

    async def notify_reviewers(
        self,
        knowledge_id: str,
        knowledge_title: str,
        author_name: str,
        assigned_reviewer_id: Optional[str] = None,
        language: str = "ko"
    ) -> List[Notification]:
        """Notify reviewers about new knowledge submission"""
        notifications = []

        # If specific reviewer assigned, notify only them
        if assigned_reviewer_id:
            notification = await self.create_from_template(
                user_id=assigned_reviewer_id,
                notification_type=NotificationType.REVIEW_REQUESTED,
                language=language,
                template_vars={
                    "knowledge_title": knowledge_title,
                    "author_name": author_name
                },
                reference_type="knowledge",
                reference_id=knowledge_id,
                priority=NotificationPriority.HIGH
            )
            notifications.append(notification)
        else:
            # Notify all reviewers (senior, leader, admin)
            reviewers = [
                u for u in self._users.values()
                if u.get("role") in ["senior", "leader", "admin"]
            ]
            for reviewer in reviewers:
                notification = await self.create_from_template(
                    user_id=reviewer["id"],
                    notification_type=NotificationType.KNOWLEDGE_SUBMITTED,
                    language=language,
                    template_vars={
                        "knowledge_title": knowledge_title,
                        "author_name": author_name
                    },
                    reference_type="knowledge",
                    reference_id=knowledge_id
                )
                notifications.append(notification)

        return notifications

    async def notify_author_review_result(
        self,
        author_id: str,
        knowledge_id: str,
        knowledge_title: str,
        action: str,  # "approved", "rejected", "changes_requested"
        reviewer_name: str,
        comment: str,
        language: str = "ko"
    ) -> Notification:
        """Notify author about review result"""
        action_texts = {
            "approved": {"ko": "승인", "ja": "承認", "en": "approved"},
            "rejected": {"ko": "반려", "ja": "却下", "en": "rejected"},
            "changes_requested": {"ko": "수정 요청", "ja": "修正依頼", "en": "changes requested"}
        }

        notification_type = (
            NotificationType.REVIEW_COMPLETED
            if action in ["approved", "rejected"]
            else NotificationType.CHANGES_REQUESTED
        )

        return await self.create_from_template(
            user_id=author_id,
            notification_type=notification_type,
            language=language,
            template_vars={
                "knowledge_title": knowledge_title,
                "action": action_texts.get(action, {}).get(language, action),
                "reviewer_name": reviewer_name
            },
            reference_type="knowledge",
            reference_id=knowledge_id,
            priority=NotificationPriority.HIGH
        )

    async def get_notifications(
        self,
        user_id: str,
        is_read: Optional[bool] = None,
        notification_type: Optional[NotificationType] = None,
        page: int = 1,
        limit: int = 20
    ) -> tuple[List[Notification], int, int]:
        """Get notifications for a user"""
        notifications = [
            n for n in self._notifications.values()
            if n.user_id == user_id
        ]

        # Apply filters
        if is_read is not None:
            notifications = [n for n in notifications if n.is_read == is_read]

        if notification_type:
            notifications = [n for n in notifications if n.type == notification_type]

        # Sort by created_at descending
        notifications.sort(key=lambda x: x.created_at, reverse=True)

        # Count unread
        unread_count = len([n for n in self._notifications.values() if n.user_id == user_id and not n.is_read])

        total = len(notifications)
        start = (page - 1) * limit
        end = start + limit

        return notifications[start:end], total, unread_count

    async def get_unread_count(self, user_id: str) -> Dict[str, int]:
        """Get unread notification count by type"""
        notifications = [
            n for n in self._notifications.values()
            if n.user_id == user_id and not n.is_read
        ]

        count_by_type: Dict[str, int] = {}
        for n in notifications:
            count_by_type[n.type.value] = count_by_type.get(n.type.value, 0) + 1

        return {
            "total": len(notifications),
            "by_type": count_by_type
        }

    async def mark_as_read(
        self,
        notification_ids: List[str],
        user_id: str
    ) -> int:
        """Mark notifications as read"""
        count = 0
        for nid in notification_ids:
            notification = self._notifications.get(nid)
            if notification and notification.user_id == user_id:
                notification.is_read = True
                notification.read_at = datetime.now(timezone.utc)
                self._notifications[nid] = notification
                count += 1
        return count

    async def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user"""
        count = 0
        for notification in self._notifications.values():
            if notification.user_id == user_id and not notification.is_read:
                notification.is_read = True
                notification.read_at = datetime.now(timezone.utc)
                count += 1
        return count

    async def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Delete a notification"""
        notification = self._notifications.get(notification_id)
        if not notification or notification.user_id != user_id:
            return False

        del self._notifications[notification_id]
        return True

    async def get_preferences(self, user_id: str) -> NotificationPreferences:
        """Get user notification preferences"""
        if user_id not in self._preferences:
            self._preferences[user_id] = NotificationPreferences(user_id=user_id)
        return self._preferences[user_id]

    async def update_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ) -> NotificationPreferences:
        """Update user notification preferences"""
        current = await self.get_preferences(user_id)

        for key, value in preferences.items():
            if hasattr(current, key):
                setattr(current, key, value)

        self._preferences[user_id] = current
        return current


# Singleton instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
