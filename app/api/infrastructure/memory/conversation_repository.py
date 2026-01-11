"""
In-Memory Conversation Repository Implementation

Thread-safe implementation for development and testing.
Provides all conversation, message, and summary operations
using in-memory storage with asyncio locks.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from uuid import uuid4
import asyncio
import re

from .base import MemoryBaseRepository
from ...repositories.base import EntityId
from ...repositories.conversation_repository import (
    ConversationRepository,
    ConversationEntity,
    MessageEntity,
    SummaryEntity
)


class MemoryConversationRepository(ConversationRepository):
    """
    In-memory implementation of ConversationRepository.

    Suitable for development and testing. Not recommended for production.
    """

    def __init__(self):
        # Conversation storage
        self._conversations: Dict[str, ConversationEntity] = {}
        # Message storage (separate for efficient lookups)
        self._messages: Dict[str, MessageEntity] = {}
        # Messages indexed by conversation
        self._conversation_messages: Dict[str, List[str]] = {}
        # Summary storage
        self._summaries: Dict[str, SummaryEntity] = {}
        # Summaries indexed by conversation
        self._conversation_summaries: Dict[str, List[str]] = {}
        # Thread safety
        self._lock = asyncio.Lock()
        self._id_counter = 0

    def _generate_id(self) -> str:
        """Generate a unique ID"""
        return str(uuid4())

    def _normalize_id(self, entity_id: EntityId) -> str:
        """Normalize entity ID to string"""
        return str(entity_id)

    # ==================== Base CRUD Operations ====================

    async def create(self, entity: ConversationEntity) -> ConversationEntity:
        """Create a new conversation"""
        async with self._lock:
            if not entity.id:
                entity.id = self._generate_id()

            entity_id = self._normalize_id(entity.id)
            entity.created_at = datetime.now(timezone.utc)
            entity.updated_at = datetime.now(timezone.utc)
            self._conversations[entity_id] = entity
            self._conversation_messages[entity_id] = []
            self._conversation_summaries[entity_id] = []
            return entity

    async def get_by_id(self, entity_id: EntityId) -> Optional[ConversationEntity]:
        """Get conversation by ID"""
        conv = self._conversations.get(self._normalize_id(entity_id))
        if conv and not conv.is_deleted:
            return conv
        return None

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[ConversationEntity]:
        """Get all conversations"""
        conversations = [c for c in self._conversations.values() if not c.is_deleted]

        if filters:
            for key, value in filters.items():
                conversations = [c for c in conversations if getattr(c, key, None) == value]

        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations[skip:skip + limit]

    async def update(self, entity_id: EntityId, data: Dict[str, Any]) -> Optional[ConversationEntity]:
        """Update a conversation"""
        async with self._lock:
            entity_id = self._normalize_id(entity_id)
            conv = self._conversations.get(entity_id)

            if not conv:
                return None

            for key, value in data.items():
                if hasattr(conv, key):
                    setattr(conv, key, value)

            conv.updated_at = datetime.now(timezone.utc)
            return conv

    async def delete(self, entity_id: EntityId) -> bool:
        """Hard delete a conversation and all related data"""
        async with self._lock:
            entity_id = self._normalize_id(entity_id)
            if entity_id in self._conversations:
                # Delete all messages
                for msg_id in self._conversation_messages.get(entity_id, []):
                    del self._messages[msg_id]
                del self._conversation_messages[entity_id]

                # Delete all summaries
                for sum_id in self._conversation_summaries.get(entity_id, []):
                    del self._summaries[sum_id]
                del self._conversation_summaries[entity_id]

                # Delete conversation
                del self._conversations[entity_id]
                return True
            return False

    async def exists(self, entity_id: EntityId) -> bool:
        """Check if conversation exists"""
        conv = self._conversations.get(self._normalize_id(entity_id))
        return conv is not None and not conv.is_deleted

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """Count conversations"""
        conversations = [c for c in self._conversations.values() if not c.is_deleted]

        if filters:
            for key, value in filters.items():
                conversations = [c for c in conversations if getattr(c, key, None) == value]

        return len(conversations)

    # ==================== Conversation Operations ====================

    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False,
        include_deleted: bool = False,
        agent_type: Optional[str] = None
    ) -> List[ConversationEntity]:
        """Get conversations for a user, optionally filtered by agent_type"""
        conversations = []

        for conv in self._conversations.values():
            if conv.user_id != user_id:
                continue
            if not include_deleted and conv.is_deleted:
                continue
            if not include_archived and conv.is_archived:
                continue
            if agent_type and conv.agent_type != agent_type:
                continue
            conversations.append(conv)

        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations[skip:skip + limit]

    async def get_by_project(
        self,
        project_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[ConversationEntity]:
        """Get conversations for a project"""
        conversations = [
            c for c in self._conversations.values()
            if c.project_id == project_id
            and c.user_id == user_id
            and not c.is_deleted
        ]
        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations[skip:skip + limit]

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Tuple[ConversationEntity, float]]:
        """Full-text search across messages"""
        results = []
        query_lower = query.lower()
        query_words = query_lower.split()

        for conv in self._conversations.values():
            if conv.user_id != user_id or conv.is_deleted:
                continue

            # Search in messages
            conv_id = self._normalize_id(conv.id)
            messages = [
                self._messages[mid]
                for mid in self._conversation_messages.get(conv_id, [])
            ]

            max_score = 0.0
            for msg in messages:
                if msg.is_deleted:
                    continue

                content_lower = msg.content.lower()
                # Simple scoring: count matching words
                matches = sum(1 for word in query_words if word in content_lower)
                if matches > 0:
                    score = matches / len(query_words)
                    max_score = max(max_score, score)

            # Also search in title
            if conv.title:
                title_lower = conv.title.lower()
                title_matches = sum(1 for word in query_words if word in title_lower)
                if title_matches > 0:
                    title_score = (title_matches / len(query_words)) * 1.2  # Boost title matches
                    max_score = max(max_score, min(title_score, 1.0))

            if max_score > 0:
                results.append((conv, max_score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def soft_delete(
        self,
        conversation_id: EntityId,
        deleted_by: str
    ) -> bool:
        """Soft delete a conversation"""
        async with self._lock:
            conv = self._conversations.get(self._normalize_id(conversation_id))
            if not conv:
                return False

            conv.is_deleted = True
            conv.deleted_at = datetime.now(timezone.utc)
            conv.deleted_by = deleted_by
            conv.updated_at = datetime.now(timezone.utc)
            return True

    async def restore(
        self,
        conversation_id: EntityId
    ) -> bool:
        """Restore a soft-deleted conversation"""
        async with self._lock:
            conv = self._conversations.get(self._normalize_id(conversation_id))
            if not conv or not conv.is_deleted:
                return False

            conv.is_deleted = False
            conv.deleted_at = None
            conv.deleted_by = None
            conv.updated_at = datetime.now(timezone.utc)
            return True

    async def archive(
        self,
        conversation_id: EntityId,
        archived: bool = True
    ) -> bool:
        """Toggle archive status"""
        async with self._lock:
            conv = self._conversations.get(self._normalize_id(conversation_id))
            if not conv:
                return False

            conv.is_archived = archived
            conv.updated_at = datetime.now(timezone.utc)
            return True

    async def star(
        self,
        conversation_id: EntityId,
        starred: bool = True
    ) -> bool:
        """Toggle starred status"""
        async with self._lock:
            conv = self._conversations.get(self._normalize_id(conversation_id))
            if not conv:
                return False

            conv.is_starred = starred
            conv.updated_at = datetime.now(timezone.utc)
            return True

    # ==================== Message Operations ====================

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
        """Add a message to a conversation"""
        async with self._lock:
            conv_id = self._normalize_id(conversation_id)
            conv = self._conversations.get(conv_id)

            if not conv:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Determine branch info from parent
            branch_root_id = None
            branch_depth = 0

            if parent_message_id:
                parent_id = self._normalize_id(parent_message_id)
                parent = self._messages.get(parent_id)
                if parent:
                    branch_root_id = parent.branch_root_id
                    branch_depth = parent.branch_depth + 1

            message = MessageEntity(
                id=self._generate_id(),
                conversation_id=conv_id,
                parent_message_id=self._normalize_id(parent_message_id) if parent_message_id else None,
                role=role,
                content=content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                model=model,
                sources=sources or [],
                rag_context=rag_context or {},
                branch_root_id=branch_root_id,
                branch_depth=branch_depth,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            msg_id = self._normalize_id(message.id)
            self._messages[msg_id] = message
            self._conversation_messages[conv_id].append(msg_id)

            # Update conversation stats
            conv.message_count += 1
            conv.total_tokens += total_tokens
            conv.updated_at = datetime.now(timezone.utc)

            return message

    async def get_messages(
        self,
        conversation_id: EntityId,
        include_inactive_branches: bool = False,
        include_deleted: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[MessageEntity]:
        """Get messages in a conversation"""
        conv_id = self._normalize_id(conversation_id)
        message_ids = self._conversation_messages.get(conv_id, [])

        messages = []
        for msg_id in message_ids:
            msg = self._messages.get(msg_id)
            if not msg:
                continue
            if not include_deleted and msg.is_deleted:
                continue
            if not include_inactive_branches and not msg.is_active_branch:
                continue
            messages.append(msg)

        messages.sort(key=lambda x: x.created_at)
        return messages[skip:skip + limit]

    async def get_active_branch_messages(
        self,
        conversation_id: EntityId,
        limit: int = 100
    ) -> List[MessageEntity]:
        """Get only active branch messages"""
        return await self.get_messages(
            conversation_id,
            include_inactive_branches=False,
            include_deleted=False,
            limit=limit
        )

    async def get_message(
        self,
        message_id: EntityId
    ) -> Optional[MessageEntity]:
        """Get a specific message"""
        return self._messages.get(self._normalize_id(message_id))

    async def update_message_feedback(
        self,
        message_id: EntityId,
        score: int,
        text: Optional[str] = None
    ) -> bool:
        """Update feedback for a message"""
        async with self._lock:
            msg = self._messages.get(self._normalize_id(message_id))
            if not msg:
                return False

            msg.feedback_score = score
            msg.feedback_text = text
            msg.updated_at = datetime.now(timezone.utc)
            return True

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
        """Create a regenerated version of a message"""
        async with self._lock:
            orig_id = self._normalize_id(original_message_id)
            original = self._messages.get(orig_id)

            if not original:
                raise ValueError(f"Message {original_message_id} not found")

            if original.role != "assistant":
                raise ValueError("Can only regenerate assistant messages")

            # Mark original as inactive
            original.is_active_branch = False
            original.updated_at = datetime.now(timezone.utc)

            # Get existing regeneration count
            regen_count = 1
            if original.original_message_id:
                # This was already a regeneration
                orig_orig = self._messages.get(self._normalize_id(original.original_message_id))
                if orig_orig:
                    regen_count = original.regeneration_count + 1

            # Create new message
            new_message = MessageEntity(
                id=self._generate_id(),
                conversation_id=original.conversation_id,
                parent_message_id=original.parent_message_id,
                role=original.role,
                content=new_content,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                model=model,
                sources=sources or [],
                is_regenerated=True,
                regeneration_count=regen_count,
                original_message_id=orig_id,
                branch_root_id=original.branch_root_id or orig_id,
                branch_depth=original.branch_depth,
                is_active_branch=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            new_id = self._normalize_id(new_message.id)
            self._messages[new_id] = new_message
            conv_id = self._normalize_id(original.conversation_id)
            self._conversation_messages[conv_id].append(new_id)

            # Update conversation stats (add new tokens, don't remove old)
            conv = self._conversations.get(conv_id)
            if conv:
                conv.message_count += 1
                conv.total_tokens += total_tokens
                conv.updated_at = datetime.now(timezone.utc)

            return new_message, original

    async def soft_delete_message(
        self,
        message_id: EntityId
    ) -> bool:
        """Soft delete a message"""
        async with self._lock:
            msg = self._messages.get(self._normalize_id(message_id))
            if not msg:
                return False

            msg.is_deleted = True
            msg.deleted_at = datetime.now(timezone.utc)
            msg.updated_at = datetime.now(timezone.utc)

            # Update conversation stats
            conv = self._conversations.get(self._normalize_id(msg.conversation_id))
            if conv:
                conv.message_count = max(0, conv.message_count - 1)
                conv.total_tokens = max(0, conv.total_tokens - msg.total_tokens)
                conv.updated_at = datetime.now(timezone.utc)

            return True

    # ==================== Fork Operations ====================

    async def fork_conversation(
        self,
        conversation_id: EntityId,
        from_message_id: EntityId,
        new_user_id: str,
        new_title: Optional[str] = None,
        include_system_messages: bool = True
    ) -> Tuple[ConversationEntity, int]:
        """Fork a conversation from a specific point"""
        async with self._lock:
            orig_conv_id = self._normalize_id(conversation_id)
            orig_conv = self._conversations.get(orig_conv_id)

            if not orig_conv:
                raise ValueError(f"Conversation {conversation_id} not found")

            from_msg_id = self._normalize_id(from_message_id)
            from_msg = self._messages.get(from_msg_id)

            if not from_msg:
                raise ValueError(f"Message {from_message_id} not found")

            # Get messages up to fork point
            all_messages = []
            for msg_id in self._conversation_messages.get(orig_conv_id, []):
                msg = self._messages.get(msg_id)
                if msg and not msg.is_deleted and msg.is_active_branch:
                    all_messages.append(msg)

            all_messages.sort(key=lambda x: x.created_at)

            # Find messages to copy (up to and including fork point)
            messages_to_copy = []
            for msg in all_messages:
                if not include_system_messages and msg.role == "system":
                    continue
                messages_to_copy.append(msg)
                if self._normalize_id(msg.id) == from_msg_id:
                    break

            # Create new conversation
            new_conv = ConversationEntity(
                id=self._generate_id(),
                user_id=new_user_id,
                project_id=orig_conv.project_id,
                session_id=orig_conv.session_id,
                title=new_title or f"Fork of {orig_conv.title or 'Conversation'}",
                strategy=orig_conv.strategy,
                language=orig_conv.language,
                metadata={
                    **orig_conv.metadata,
                    "forked_from": orig_conv_id,
                    "forked_at_message": from_msg_id
                },
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            new_conv_id = self._normalize_id(new_conv.id)
            self._conversations[new_conv_id] = new_conv
            self._conversation_messages[new_conv_id] = []
            self._conversation_summaries[new_conv_id] = []

            # Copy messages
            total_tokens = 0
            for msg in messages_to_copy:
                new_msg = MessageEntity(
                    id=self._generate_id(),
                    conversation_id=new_conv_id,
                    parent_message_id=None,  # Reset parent links
                    role=msg.role,
                    content=msg.content,
                    input_tokens=msg.input_tokens,
                    output_tokens=msg.output_tokens,
                    total_tokens=msg.total_tokens,
                    model=msg.model,
                    sources=msg.sources.copy() if msg.sources else [],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )

                new_msg_id = self._normalize_id(new_msg.id)
                self._messages[new_msg_id] = new_msg
                self._conversation_messages[new_conv_id].append(new_msg_id)
                total_tokens += msg.total_tokens

            new_conv.message_count = len(messages_to_copy)
            new_conv.total_tokens = total_tokens

            return new_conv, len(messages_to_copy)

    async def get_fork_tree(
        self,
        message_id: EntityId
    ) -> List[MessageEntity]:
        """Get all message branches from a specific point"""
        msg_id = self._normalize_id(message_id)
        branches = []

        for msg in self._messages.values():
            if msg.branch_root_id == msg_id or self._normalize_id(msg.id) == msg_id:
                branches.append(msg)

        branches.sort(key=lambda x: (x.branch_depth, x.created_at))
        return branches

    # ==================== Summary Operations ====================

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
        async with self._lock:
            conv_id = self._normalize_id(conversation_id)

            if conv_id not in self._conversations:
                raise ValueError(f"Conversation {conversation_id} not found")

            compression_ratio = None
            if tokens_before > 0:
                compression_ratio = tokens_after / tokens_before

            summary = SummaryEntity(
                id=self._generate_id(),
                conversation_id=conv_id,
                summary_text=summary_text,
                summary_type=summary_type,
                covers_from_message_id=self._normalize_id(covers_from_id) if covers_from_id else None,
                covers_to_message_id=self._normalize_id(covers_to_id) if covers_to_id else None,
                message_count_covered=message_count,
                tokens_before_summary=tokens_before,
                tokens_after_summary=tokens_after,
                compression_ratio=compression_ratio,
                key_topics=key_topics or [],
                key_entities=key_entities or [],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            sum_id = self._normalize_id(summary.id)
            self._summaries[sum_id] = summary

            if conv_id not in self._conversation_summaries:
                self._conversation_summaries[conv_id] = []
            self._conversation_summaries[conv_id].append(sum_id)

            return summary

    async def get_latest_summary(
        self,
        conversation_id: EntityId
    ) -> Optional[SummaryEntity]:
        """Get the most recent summary"""
        conv_id = self._normalize_id(conversation_id)
        summary_ids = self._conversation_summaries.get(conv_id, [])

        if not summary_ids:
            return None

        summaries = [self._summaries.get(sid) for sid in summary_ids]
        summaries = [s for s in summaries if s is not None]

        if not summaries:
            return None

        summaries.sort(key=lambda x: x.created_at, reverse=True)
        return summaries[0]

    async def get_summaries(
        self,
        conversation_id: EntityId,
        summary_type: Optional[str] = None
    ) -> List[SummaryEntity]:
        """Get all summaries for a conversation"""
        conv_id = self._normalize_id(conversation_id)
        summary_ids = self._conversation_summaries.get(conv_id, [])

        summaries = [self._summaries.get(sid) for sid in summary_ids]
        summaries = [s for s in summaries if s is not None]

        if summary_type:
            summaries = [s for s in summaries if s.summary_type == summary_type]

        summaries.sort(key=lambda x: x.created_at, reverse=True)
        return summaries

    # ==================== Context Window Operations ====================

    async def get_context_window(
        self,
        conversation_id: EntityId,
        max_tokens: int = 4000,
        include_summary: bool = True
    ) -> Dict[str, Any]:
        """Get messages fitting in context window"""
        conv_id = self._normalize_id(conversation_id)

        result = {
            "messages": [],
            "summary": None,
            "total_tokens": 0,
            "messages_included": 0,
            "messages_summarized": 0
        }

        # Get latest summary if requested
        if include_summary:
            summary = await self.get_latest_summary(conversation_id)
            if summary:
                result["summary"] = summary.summary_text
                result["messages_summarized"] = summary.message_count_covered

        # Get active messages in reverse order (most recent first)
        messages = await self.get_active_branch_messages(conversation_id)
        messages.reverse()  # Most recent first

        # Build context from most recent messages
        token_budget = max_tokens
        selected = []

        for msg in messages:
            if token_budget >= msg.total_tokens:
                selected.insert(0, msg)  # Insert at beginning for chronological order
                token_budget -= msg.total_tokens
                result["total_tokens"] += msg.total_tokens
            else:
                break

        result["messages"] = selected
        result["messages_included"] = len(selected)

        return result

    async def get_token_count(
        self,
        conversation_id: EntityId,
        active_branch_only: bool = True
    ) -> int:
        """Get total token count for a conversation"""
        conv_id = self._normalize_id(conversation_id)
        message_ids = self._conversation_messages.get(conv_id, [])

        total = 0
        for msg_id in message_ids:
            msg = self._messages.get(msg_id)
            if msg and not msg.is_deleted:
                if active_branch_only and not msg.is_active_branch:
                    continue
                total += msg.total_tokens

        return total

    # ==================== Statistics ====================

    async def get_user_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get conversation statistics for a user"""
        total = 0
        active = 0
        archived = 0
        total_messages = 0
        total_tokens = 0

        for conv in self._conversations.values():
            if conv.user_id != user_id or conv.is_deleted:
                continue

            total += 1
            if conv.is_archived:
                archived += 1
            else:
                active += 1

            total_messages += conv.message_count
            total_tokens += conv.total_tokens

        return {
            "total_conversations": total,
            "active_conversations": active,
            "archived_conversations": archived,
            "total_messages": total_messages,
            "total_tokens": total_tokens
        }

    # ==================== Testing Helpers ====================

    async def clear(self) -> None:
        """Clear all data (for testing)"""
        async with self._lock:
            self._conversations.clear()
            self._messages.clear()
            self._conversation_messages.clear()
            self._summaries.clear()
            self._conversation_summaries.clear()
            self._id_counter = 0
