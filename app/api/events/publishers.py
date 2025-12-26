"""
Event Publishers
Helper functions for publishing domain events from services.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from .domain_events import (
    DocumentCreatedEvent,
    DocumentUpdatedEvent,
    DocumentDeletedEvent,
    DocumentProcessedEvent,
    DocumentIndexedEvent,
    UserCreatedEvent,
    UserLoginEvent,
    UserPasswordChangedEvent,
    UserMFAEnabledEvent,
    ProjectCreatedEvent,
    ProjectMemberAddedEvent,
    QueryExecutedEvent,
    QueryFeedbackEvent,
    ExternalResourceConnectedEvent,
    ExternalResourceSyncedEvent,
    EventPriority
)
from .event_bus import get_event_bus


class DocumentEventPublisher:
    """Publisher for document-related events"""

    @staticmethod
    async def document_created(
        document_id: str,
        document_name: str,
        user_id: str,
        project_id: Optional[str] = None,
        file_size: int = 0,
        mime_type: str = "",
        correlation_id: Optional[str] = None
    ) -> None:
        """Publish document created event"""
        event = DocumentCreatedEvent(
            document_id=document_id,
            document_name=document_name,
            project_id=project_id,
            file_size=file_size,
            mime_type=mime_type,
            user_id=user_id,
            correlation_id=correlation_id or str(uuid.uuid4())
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def document_updated(
        document_id: str,
        document_name: str,
        user_id: str,
        changed_fields: List[str],
        project_id: Optional[str] = None
    ) -> None:
        """Publish document updated event"""
        event = DocumentUpdatedEvent(
            document_id=document_id,
            document_name=document_name,
            project_id=project_id,
            changed_fields=changed_fields,
            user_id=user_id
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def document_deleted(
        document_id: str,
        document_name: str,
        user_id: str,
        project_id: Optional[str] = None,
        soft_delete: bool = True
    ) -> None:
        """Publish document deleted event"""
        event = DocumentDeletedEvent(
            document_id=document_id,
            document_name=document_name,
            project_id=project_id,
            soft_delete=soft_delete,
            user_id=user_id
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def document_processed(
        document_id: str,
        document_name: str,
        user_id: str,
        chunk_count: int = 0,
        total_tokens: int = 0,
        processing_time_ms: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> None:
        """Publish document processed event"""
        event = DocumentProcessedEvent(
            document_id=document_id,
            document_name=document_name,
            chunk_count=chunk_count,
            total_tokens=total_tokens,
            processing_time_ms=processing_time_ms,
            success=success,
            error_message=error_message,
            user_id=user_id,
            correlation_id=correlation_id,
            priority=EventPriority.HIGH if not success else EventPriority.NORMAL
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def document_indexed(
        document_id: str,
        document_name: str,
        user_id: str,
        vector_count: int,
        collection: str
    ) -> None:
        """Publish document indexed event"""
        event = DocumentIndexedEvent(
            document_id=document_id,
            document_name=document_name,
            vector_count=vector_count,
            collection=collection,
            user_id=user_id
        )
        await get_event_bus().publish(event)


class UserEventPublisher:
    """Publisher for user-related events"""

    @staticmethod
    async def user_created(
        user_id: str,
        email: str,
        username: str,
        role: str = "user"
    ) -> None:
        """Publish user created event"""
        event = UserCreatedEvent(
            target_user_id=user_id,
            email=email,
            username=username,
            role=role,
            user_id=user_id  # Self-created
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def user_login(
        user_id: str,
        email: str,
        success: bool = True,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        failure_reason: Optional[str] = None
    ) -> None:
        """Publish user login event"""
        event = UserLoginEvent(
            target_user_id=user_id,
            email=email,
            success=success,
            ip_address=ip_address,
            user_agent=user_agent,
            failure_reason=failure_reason,
            user_id=user_id,
            priority=EventPriority.HIGH if not success else EventPriority.NORMAL
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def password_changed(
        user_id: str,
        email: str,
        forced: bool = False
    ) -> None:
        """Publish password changed event"""
        event = UserPasswordChangedEvent(
            target_user_id=user_id,
            email=email,
            forced=forced,
            user_id=user_id,
            priority=EventPriority.HIGH
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def mfa_enabled(
        user_id: str,
        email: str,
        mfa_type: str = "totp"
    ) -> None:
        """Publish MFA enabled event"""
        event = UserMFAEnabledEvent(
            target_user_id=user_id,
            email=email,
            mfa_type=mfa_type,
            user_id=user_id,
            priority=EventPriority.HIGH
        )
        await get_event_bus().publish(event)


class ProjectEventPublisher:
    """Publisher for project-related events"""

    @staticmethod
    async def project_created(
        project_id: str,
        project_name: str,
        owner_id: str,
        is_public: bool = False
    ) -> None:
        """Publish project created event"""
        event = ProjectCreatedEvent(
            project_id=project_id,
            project_name=project_name,
            owner_id=owner_id,
            is_public=is_public,
            user_id=owner_id
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def member_added(
        project_id: str,
        project_name: str,
        owner_id: str,
        member_id: str,
        role: str,
        invited_by: Optional[str] = None
    ) -> None:
        """Publish project member added event"""
        event = ProjectMemberAddedEvent(
            project_id=project_id,
            project_name=project_name,
            owner_id=owner_id,
            member_id=member_id,
            role=role,
            invited_by=invited_by,
            user_id=invited_by or owner_id
        )
        await get_event_bus().publish(event)


class QueryEventPublisher:
    """Publisher for query-related events"""

    @staticmethod
    async def query_executed(
        query_id: str,
        query_text: str,
        user_id: str,
        strategy: str,
        language: str,
        sources_count: int = 0,
        processing_time_ms: int = 0,
        tokens_used: int = 0,
        success: bool = True,
        error_message: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """Publish query executed event"""
        event = QueryExecutedEvent(
            query_id=query_id,
            query_text=query_text,
            session_id=session_id,
            strategy=strategy,
            language=language,
            sources_count=sources_count,
            processing_time_ms=processing_time_ms,
            tokens_used=tokens_used,
            success=success,
            error_message=error_message,
            user_id=user_id,
            priority=EventPriority.HIGH if not success else EventPriority.NORMAL
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def query_feedback(
        query_id: str,
        message_id: str,
        user_id: str,
        score: int,
        feedback_text: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> None:
        """Publish query feedback event"""
        event = QueryFeedbackEvent(
            query_id=query_id,
            message_id=message_id,
            session_id=session_id,
            score=score,
            feedback_text=feedback_text,
            user_id=user_id,
            query_text=""  # Not needed for feedback
        )
        await get_event_bus().publish(event)


class ExternalResourceEventPublisher:
    """Publisher for external resource events"""

    @staticmethod
    async def resource_connected(
        resource_id: str,
        resource_type: str,
        source_name: str,
        user_id: str,
        oauth_provider: Optional[str] = None
    ) -> None:
        """Publish external resource connected event"""
        event = ExternalResourceConnectedEvent(
            resource_id=resource_id,
            resource_type=resource_type,
            source_name=source_name,
            oauth_provider=oauth_provider,
            user_id=user_id
        )
        await get_event_bus().publish(event)

    @staticmethod
    async def resource_synced(
        resource_id: str,
        resource_type: str,
        source_name: str,
        user_id: str,
        documents_synced: int = 0,
        documents_added: int = 0,
        documents_updated: int = 0,
        documents_deleted: int = 0
    ) -> None:
        """Publish external resource synced event"""
        event = ExternalResourceSyncedEvent(
            resource_id=resource_id,
            resource_type=resource_type,
            source_name=source_name,
            documents_synced=documents_synced,
            documents_added=documents_added,
            documents_updated=documents_updated,
            documents_deleted=documents_deleted,
            user_id=user_id
        )
        await get_event_bus().publish(event)
