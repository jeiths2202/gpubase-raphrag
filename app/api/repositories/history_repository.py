"""
History Repository Interface
Repository for conversation and query history operations.
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from .base import BaseRepository, Entity, EntityId


class MessageRole(str, Enum):
    """Message role in conversation"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class MessageEntity:
    """Conversation message entity"""
    message_id: str
    conversation_id: str
    role: MessageRole
    content: str

    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tokens: int = 0
    model: Optional[str] = None

    # Sources (for assistant messages)
    sources: List[Dict[str, Any]] = field(default_factory=list)

    # Feedback
    feedback_score: Optional[int] = None  # 1-5 rating
    feedback_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "tokens": self.tokens,
            "model": self.model,
            "sources": self.sources,
            "feedback_score": self.feedback_score,
            "feedback_text": self.feedback_text
        }


@dataclass
class HistoryEntity(Entity):
    """Conversation history entity"""
    user_id: str = ""
    title: Optional[str] = None

    # Context
    project_id: Optional[str] = None
    session_id: Optional[str] = None

    # Stats
    message_count: int = 0
    total_tokens: int = 0

    # Status
    is_archived: bool = False
    is_starred: bool = False

    # Metadata
    strategy: Optional[str] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Messages (loaded separately)
    messages: List[MessageEntity] = field(default_factory=list)


class HistoryRepository(BaseRepository[HistoryEntity]):
    """
    Repository interface for conversation history operations.
    """

    # ==================== Conversation Operations ====================

    @abstractmethod
    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False
    ) -> List[HistoryEntity]:
        """Get conversations for a user"""
        pass

    @abstractmethod
    async def get_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[HistoryEntity]:
        """Get conversations in a project"""
        pass

    @abstractmethod
    async def get_by_session(
        self,
        session_id: str
    ) -> List[HistoryEntity]:
        """Get conversations for a session"""
        pass

    @abstractmethod
    async def get_starred(
        self,
        user_id: str
    ) -> List[HistoryEntity]:
        """Get starred conversations"""
        pass

    @abstractmethod
    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[HistoryEntity]:
        """Search conversations by title and content"""
        pass

    @abstractmethod
    async def archive(self, conversation_id: EntityId) -> bool:
        """Archive a conversation"""
        pass

    @abstractmethod
    async def restore(self, conversation_id: EntityId) -> bool:
        """Restore an archived conversation"""
        pass

    @abstractmethod
    async def toggle_star(self, conversation_id: EntityId) -> bool:
        """Toggle starred status"""
        pass

    @abstractmethod
    async def update_title(
        self,
        conversation_id: EntityId,
        title: str
    ) -> bool:
        """Update conversation title"""
        pass

    # ==================== Message Operations ====================

    @abstractmethod
    async def add_message(
        self,
        conversation_id: EntityId,
        message: MessageEntity
    ) -> MessageEntity:
        """Add a message to conversation"""
        pass

    @abstractmethod
    async def get_messages(
        self,
        conversation_id: EntityId,
        skip: int = 0,
        limit: int = 100
    ) -> List[MessageEntity]:
        """Get messages in a conversation"""
        pass

    @abstractmethod
    async def get_recent_messages(
        self,
        conversation_id: EntityId,
        count: int = 10
    ) -> List[MessageEntity]:
        """Get most recent messages"""
        pass

    @abstractmethod
    async def get_message(
        self,
        message_id: str
    ) -> Optional[MessageEntity]:
        """Get specific message"""
        pass

    @abstractmethod
    async def update_message(
        self,
        message_id: str,
        data: Dict[str, Any]
    ) -> Optional[MessageEntity]:
        """Update a message"""
        pass

    @abstractmethod
    async def delete_message(self, message_id: str) -> bool:
        """Delete a message"""
        pass

    # ==================== Feedback ====================

    @abstractmethod
    async def add_feedback(
        self,
        message_id: str,
        score: int,
        text: Optional[str] = None
    ) -> bool:
        """Add feedback to a message"""
        pass

    @abstractmethod
    async def get_feedback_stats(
        self,
        user_id: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get feedback statistics"""
        pass

    # ==================== Context Window ====================

    @abstractmethod
    async def get_context_window(
        self,
        conversation_id: EntityId,
        max_tokens: int = 4000
    ) -> List[MessageEntity]:
        """Get messages fitting in context window"""
        pass

    @abstractmethod
    async def summarize_conversation(
        self,
        conversation_id: EntityId
    ) -> Optional[str]:
        """Get or generate conversation summary"""
        pass

    # ==================== Cleanup ====================

    @abstractmethod
    async def delete_old_conversations(
        self,
        older_than_days: int,
        user_id: Optional[str] = None
    ) -> int:
        """Delete old conversations"""
        pass

    @abstractmethod
    async def get_storage_usage(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get storage usage for user"""
        pass

    # ==================== Statistics ====================

    @abstractmethod
    async def get_stats(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get conversation statistics"""
        pass
