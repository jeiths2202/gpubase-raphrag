"""
In-Memory History Repository Implementation
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from .base import MemoryBaseRepository
from ...repositories.history_repository import (
    HistoryRepository,
    HistoryEntity,
    MessageEntity,
    MessageRole
)
from ...repositories.base import EntityId


class MemoryHistoryRepository(MemoryBaseRepository[HistoryEntity], HistoryRepository):
    """In-memory history repository implementation"""

    def __init__(self):
        super().__init__()
        self._messages: Dict[str, List[MessageEntity]] = {}  # conversation_id -> messages
        self._message_index: Dict[str, MessageEntity] = {}  # message_id -> message

    # ==================== Conversation Operations ====================

    async def get_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False
    ) -> List[HistoryEntity]:
        conversations = [c for c in self._storage.values() if c.user_id == user_id]
        if not include_archived:
            conversations = [c for c in conversations if not c.is_archived]
        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations[skip:skip + limit]

    async def get_by_project(
        self,
        project_id: str,
        skip: int = 0,
        limit: int = 50
    ) -> List[HistoryEntity]:
        conversations = [c for c in self._storage.values() if c.project_id == project_id]
        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations[skip:skip + limit]

    async def get_by_session(
        self,
        session_id: str
    ) -> List[HistoryEntity]:
        return [c for c in self._storage.values() if c.session_id == session_id]

    async def get_starred(
        self,
        user_id: str
    ) -> List[HistoryEntity]:
        conversations = [c for c in self._storage.values()
                         if c.user_id == user_id and c.is_starred]
        conversations.sort(key=lambda x: x.updated_at, reverse=True)
        return conversations

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[HistoryEntity]:
        query_lower = query.lower()
        results = []

        for conv in self._storage.values():
            if conv.user_id != user_id:
                continue

            # Search in title
            if conv.title and query_lower in conv.title.lower():
                results.append(conv)
                continue

            # Search in messages
            messages = self._messages.get(str(conv.id), [])
            for msg in messages:
                if query_lower in msg.content.lower():
                    results.append(conv)
                    break

        results.sort(key=lambda x: x.updated_at, reverse=True)
        return results[:limit]

    async def archive(self, conversation_id: EntityId) -> bool:
        conv = await self.get_by_id(conversation_id)
        if not conv:
            return False
        conv.is_archived = True
        conv.updated_at = datetime.utcnow()
        return True

    async def restore(self, conversation_id: EntityId) -> bool:
        conv = await self.get_by_id(conversation_id)
        if not conv:
            return False
        conv.is_archived = False
        conv.updated_at = datetime.utcnow()
        return True

    async def toggle_star(self, conversation_id: EntityId) -> bool:
        conv = await self.get_by_id(conversation_id)
        if not conv:
            return False
        conv.is_starred = not conv.is_starred
        conv.updated_at = datetime.utcnow()
        return True

    async def update_title(
        self,
        conversation_id: EntityId,
        title: str
    ) -> bool:
        conv = await self.get_by_id(conversation_id)
        if not conv:
            return False
        conv.title = title
        conv.updated_at = datetime.utcnow()
        return True

    # ==================== Message Operations ====================

    async def add_message(
        self,
        conversation_id: EntityId,
        message: MessageEntity
    ) -> MessageEntity:
        conv_id = self._normalize_id(conversation_id)

        if conv_id not in self._messages:
            self._messages[conv_id] = []

        message.conversation_id = conv_id
        self._messages[conv_id].append(message)
        self._message_index[message.message_id] = message

        # Update conversation stats
        conv = await self.get_by_id(conversation_id)
        if conv:
            conv.message_count = len(self._messages[conv_id])
            conv.total_tokens += message.tokens
            conv.updated_at = datetime.utcnow()

        return message

    async def get_messages(
        self,
        conversation_id: EntityId,
        skip: int = 0,
        limit: int = 100
    ) -> List[MessageEntity]:
        conv_id = self._normalize_id(conversation_id)
        messages = self._messages.get(conv_id, [])
        messages.sort(key=lambda x: x.timestamp)
        return messages[skip:skip + limit]

    async def get_recent_messages(
        self,
        conversation_id: EntityId,
        count: int = 10
    ) -> List[MessageEntity]:
        conv_id = self._normalize_id(conversation_id)
        messages = self._messages.get(conv_id, [])
        messages.sort(key=lambda x: x.timestamp, reverse=True)
        return list(reversed(messages[:count]))

    async def get_message(
        self,
        message_id: str
    ) -> Optional[MessageEntity]:
        return self._message_index.get(message_id)

    async def update_message(
        self,
        message_id: str,
        data: Dict[str, Any]
    ) -> Optional[MessageEntity]:
        message = self._message_index.get(message_id)
        if not message:
            return None

        for key, value in data.items():
            if hasattr(message, key):
                setattr(message, key, value)

        return message

    async def delete_message(self, message_id: str) -> bool:
        message = self._message_index.get(message_id)
        if not message:
            return False

        conv_id = message.conversation_id
        if conv_id in self._messages:
            self._messages[conv_id] = [
                m for m in self._messages[conv_id]
                if m.message_id != message_id
            ]

        del self._message_index[message_id]
        return True

    # ==================== Feedback ====================

    async def add_feedback(
        self,
        message_id: str,
        score: int,
        text: Optional[str] = None
    ) -> bool:
        message = self._message_index.get(message_id)
        if not message:
            return False

        message.feedback_score = score
        message.feedback_text = text
        return True

    async def get_feedback_stats(
        self,
        user_id: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        all_messages = list(self._message_index.values())

        if user_id:
            user_convs = {str(c.id) for c in self._storage.values() if c.user_id == user_id}
            all_messages = [m for m in all_messages if m.conversation_id in user_convs]

        if since:
            all_messages = [m for m in all_messages if m.timestamp >= since]

        with_feedback = [m for m in all_messages if m.feedback_score is not None]

        if not with_feedback:
            return {"total_feedback": 0, "average_score": 0, "score_distribution": {}}

        scores = [m.feedback_score for m in with_feedback]
        distribution = {}
        for score in scores:
            distribution[score] = distribution.get(score, 0) + 1

        return {
            "total_feedback": len(with_feedback),
            "average_score": sum(scores) / len(scores),
            "score_distribution": distribution
        }

    # ==================== Context Window ====================

    async def get_context_window(
        self,
        conversation_id: EntityId,
        max_tokens: int = 4000
    ) -> List[MessageEntity]:
        messages = await self.get_messages(conversation_id)
        messages.reverse()  # Start from most recent

        context = []
        total_tokens = 0

        for msg in messages:
            if total_tokens + msg.tokens > max_tokens:
                break
            context.insert(0, msg)
            total_tokens += msg.tokens

        return context

    async def summarize_conversation(
        self,
        conversation_id: EntityId
    ) -> Optional[str]:
        conv = await self.get_by_id(conversation_id)
        if not conv:
            return None

        messages = await self.get_messages(conversation_id)
        if not messages:
            return None

        # Simple summary: first and last user message
        user_messages = [m for m in messages if m.role == MessageRole.USER]
        if not user_messages:
            return None

        first_msg = user_messages[0].content[:100]
        last_msg = user_messages[-1].content[:100] if len(user_messages) > 1 else ""

        summary = f"Started with: {first_msg}..."
        if last_msg:
            summary += f" Most recent: {last_msg}..."

        return summary

    # ==================== Cleanup ====================

    async def delete_old_conversations(
        self,
        older_than_days: int,
        user_id: Optional[str] = None
    ) -> int:
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        to_delete = []

        for conv_id, conv in self._storage.items():
            if user_id and conv.user_id != user_id:
                continue
            if conv.updated_at < cutoff:
                to_delete.append(conv_id)

        for conv_id in to_delete:
            await self.delete(conv_id)

        return len(to_delete)

    async def get_storage_usage(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        conversations = [c for c in self._storage.values() if c.user_id == user_id]

        total_messages = 0
        total_tokens = 0

        for conv in conversations:
            total_messages += conv.message_count
            total_tokens += conv.total_tokens

        return {
            "conversation_count": len(conversations),
            "message_count": total_messages,
            "total_tokens": total_tokens
        }

    # ==================== Statistics ====================

    async def get_stats(
        self,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        conversations = list(self._storage.values())

        if user_id:
            conversations = [c for c in conversations if c.user_id == user_id]
        if project_id:
            conversations = [c for c in conversations if c.project_id == project_id]
        if since:
            conversations = [c for c in conversations if c.created_at >= since]

        total_messages = sum(c.message_count for c in conversations)
        total_tokens = sum(c.total_tokens for c in conversations)

        return {
            "total_conversations": len(conversations),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "archived_count": len([c for c in conversations if c.is_archived]),
            "starred_count": len([c for c in conversations if c.is_starred])
        }

    async def delete(self, entity_id: EntityId) -> bool:
        """Override to also delete messages"""
        conv_id = self._normalize_id(entity_id)

        # Delete messages
        messages = self._messages.pop(conv_id, [])
        for msg in messages:
            self._message_index.pop(msg.message_id, None)

        return await super().delete(entity_id)
