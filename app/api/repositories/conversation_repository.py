"""
Conversation Repository Interface

Abstract repository for conversation and message persistence with support for:
- Conversation CRUD with soft-delete
- Message operations with branching
- Fork and regeneration tracking
- Summary management
- Context window extraction
"""
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID

from .base import BaseRepository, Entity, EntityId


# ============================================
# Entity Definitions
# ============================================

@dataclass
class ConversationEntity(Entity):
    """Conversation entity"""
    user_id: str = ""
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    title: Optional[str] = None
    message_count: int = 0
    total_tokens: int = 0
    is_archived: bool = False
    is_starred: bool = False
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    strategy: str = "auto"
    language: str = "auto"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageEntity(Entity):
    """Message entity with branching support"""
    conversation_id: EntityId = ""
    parent_message_id: Optional[EntityId] = None
    role: str = "user"  # user, assistant, system
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: Optional[str] = None
    sources: List[Dict[str, Any]] = field(default_factory=list)
    rag_context: Dict[str, Any] = field(default_factory=dict)
    feedback_score: Optional[int] = None
    feedback_text: Optional[str] = None
    is_regenerated: bool = False
    regeneration_count: int = 0
    original_message_id: Optional[EntityId] = None
    branch_root_id: Optional[EntityId] = None
    branch_depth: int = 0
    is_active_branch: bool = True
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None


@dataclass
class SummaryEntity(Entity):
    """Conversation summary entity"""
    conversation_id: EntityId = ""
    summary_text: str = ""
    summary_type: str = "rolling"  # rolling, checkpoint, final
    covers_from_message_id: Optional[EntityId] = None
    covers_to_message_id: Optional[EntityId] = None
    message_count_covered: int = 0
    tokens_before_summary: int = 0
    tokens_after_summary: int = 0
    compression_ratio: Optional[float] = None
    confidence_score: Optional[float] = None
    key_topics: List[str] = field(default_factory=list)
    key_entities: List[str] = field(default_factory=list)


# ============================================
# Repository Interface
# ============================================

class ConversationRepository(BaseRepository[ConversationEntity]):
    """
    Repository interface for conversation operations.

    Provides methods for:
    - Conversation CRUD with soft-delete support
    - Message operations with branching for regenerate/fork
    - Summary management for context window optimization
    - User-scoped queries with RLS support
    """

    # ==================== Conversation Operations ====================

    @abstractmethod
    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False,
        include_deleted: bool = False
    ) -> List[ConversationEntity]:
        """
        Get conversations for a specific user.

        Args:
            user_id: User identifier
            skip: Number of conversations to skip
            limit: Maximum number to return
            include_archived: Whether to include archived conversations
            include_deleted: Whether to include soft-deleted conversations

        Returns:
            List of conversations ordered by updated_at DESC
        """
        pass

    @abstractmethod
    async def get_by_project(
        self,
        project_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[ConversationEntity]:
        """Get conversations for a specific project"""
        pass

    @abstractmethod
    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Tuple[ConversationEntity, float]]:
        """
        Full-text search across conversation messages.

        Args:
            user_id: User identifier
            query: Search query
            limit: Maximum results

        Returns:
            List of (conversation, relevance_score) tuples
        """
        pass

    @abstractmethod
    async def soft_delete(
        self,
        conversation_id: EntityId,
        deleted_by: str
    ) -> bool:
        """
        Soft delete a conversation.

        Args:
            conversation_id: Conversation identifier
            deleted_by: User performing deletion

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def restore(
        self,
        conversation_id: EntityId
    ) -> bool:
        """
        Restore a soft-deleted conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            True if restored, False if not found
        """
        pass

    @abstractmethod
    async def archive(
        self,
        conversation_id: EntityId,
        archived: bool = True
    ) -> bool:
        """Toggle archive status"""
        pass

    @abstractmethod
    async def star(
        self,
        conversation_id: EntityId,
        starred: bool = True
    ) -> bool:
        """Toggle starred status"""
        pass

    # ==================== Message Operations ====================

    @abstractmethod
    async def add_message(
        self,
        conversation_id: EntityId,
        role: str,
        content: str,
        parent_message_id: Optional[EntityId] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        model: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        rag_context: Optional[Dict[str, Any]] = None
    ) -> MessageEntity:
        """
        Add a message to a conversation.

        Args:
            conversation_id: Target conversation
            role: Message role (user, assistant, system)
            content: Message content
            parent_message_id: Parent message for branching
            input_tokens: Input token count
            output_tokens: Output token count
            total_tokens: Total token count
            model: LLM model used
            sources: RAG sources
            rag_context: RAG retrieval context

        Returns:
            Created message entity
        """
        pass

    @abstractmethod
    async def get_messages(
        self,
        conversation_id: EntityId,
        include_inactive_branches: bool = False,
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[MessageEntity]:
        """
        Get messages in a conversation.

        Args:
            conversation_id: Conversation identifier
            include_inactive_branches: Include regenerated alternatives
            include_deleted: Include soft-deleted messages
            skip: Number to skip
            limit: Maximum to return

        Returns:
            List of messages in chronological order
        """
        pass

    @abstractmethod
    async def get_active_branch_messages(
        self,
        conversation_id: EntityId,
        limit: int = 100
    ) -> List[MessageEntity]:
        """Get only active branch messages (current conversation thread)"""
        pass

    @abstractmethod
    async def get_message(
        self,
        message_id: EntityId
    ) -> Optional[MessageEntity]:
        """Get a specific message by ID"""
        pass

    @abstractmethod
    async def update_message_feedback(
        self,
        message_id: EntityId,
        score: int,
        text: Optional[str] = None
    ) -> bool:
        """Update feedback for a message"""
        pass

    @abstractmethod
    async def regenerate_message(
        self,
        original_message_id: EntityId,
        new_content: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        model: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[MessageEntity, MessageEntity]:
        """
        Create a regenerated version of a message.

        Marks original as inactive branch, creates new message
        with same parent.

        Args:
            original_message_id: Message to regenerate
            new_content: New message content
            input_tokens: Input token count
            output_tokens: Output token count
            total_tokens: Total token count
            model: LLM model used
            sources: RAG sources

        Returns:
            Tuple of (new_message, updated_original)
        """
        pass

    @abstractmethod
    async def soft_delete_message(
        self,
        message_id: EntityId
    ) -> bool:
        """Soft delete a message"""
        pass

    # ==================== Fork Operations ====================

    @abstractmethod
    async def fork_conversation(
        self,
        conversation_id: EntityId,
        from_message_id: EntityId,
        new_user_id: str,
        new_title: Optional[str] = None,
        include_system_messages: bool = True
    ) -> Tuple[ConversationEntity, int]:
        """
        Fork a conversation from a specific message point.

        Creates a new conversation with messages up to (and including)
        the fork point.

        Args:
            conversation_id: Source conversation
            from_message_id: Fork point (inclusive)
            new_user_id: Owner of forked conversation
            new_title: Title for new conversation
            include_system_messages: Whether to copy system messages

        Returns:
            Tuple of (new_conversation, messages_copied)
        """
        pass

    @abstractmethod
    async def get_fork_tree(
        self,
        message_id: EntityId
    ) -> List[MessageEntity]:
        """Get all message branches from a specific point"""
        pass

    # ==================== Summary Operations ====================

    @abstractmethod
    async def add_summary(
        self,
        conversation_id: EntityId,
        summary_text: str,
        summary_type: str = "rolling",
        covers_from_id: Optional[EntityId] = None,
        covers_to_id: Optional[EntityId] = None,
        message_count: int = 0,
        tokens_before: int = 0,
        tokens_after: int = 0,
        key_topics: Optional[List[str]] = None,
        key_entities: Optional[List[str]] = None
    ) -> SummaryEntity:
        """Add a conversation summary"""
        pass

    @abstractmethod
    async def get_latest_summary(
        self,
        conversation_id: EntityId
    ) -> Optional[SummaryEntity]:
        """Get the most recent summary for a conversation"""
        pass

    @abstractmethod
    async def get_summaries(
        self,
        conversation_id: EntityId,
        summary_type: Optional[str] = None
    ) -> List[SummaryEntity]:
        """Get all summaries for a conversation"""
        pass

    # ==================== Context Window Operations ====================

    @abstractmethod
    async def get_context_window(
        self,
        conversation_id: EntityId,
        max_tokens: int = 4000,
        include_summary: bool = True
    ) -> Dict[str, Any]:
        """
        Get messages fitting in context window.

        Retrieves messages from most recent backwards until
        token budget is exhausted.

        Args:
            conversation_id: Conversation identifier
            max_tokens: Maximum token budget
            include_summary: Whether to include latest summary

        Returns:
            Dict with:
            - messages: List of message entities
            - summary: Summary text if available
            - total_tokens: Token count of included messages
            - messages_included: Number of messages included
            - messages_summarized: Messages covered by summary
        """
        pass

    @abstractmethod
    async def get_token_count(
        self,
        conversation_id: EntityId,
        active_branch_only: bool = True
    ) -> int:
        """Get total token count for a conversation"""
        pass

    # ==================== Statistics ====================

    @abstractmethod
    async def get_user_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get conversation statistics for a user.

        Returns:
            Dict with:
            - total_conversations
            - active_conversations
            - archived_conversations
            - total_messages
            - total_tokens
        """
        pass
