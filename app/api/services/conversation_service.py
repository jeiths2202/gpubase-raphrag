"""
Conversation Service

Provides business logic for conversation management including:
- Token counting and context window management
- Rolling summarization for long conversations
- Regenerate and fork operations
- Context reconstruction for RAG
- Audit logging integration
"""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4

from ..repositories.conversation_repository import (
    ConversationRepository,
    ConversationEntity,
    MessageEntity,
    SummaryEntity,
)
from ..models.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationDetail,
    ConversationListItem,
    MessageCreate,
    MessageResponse,
    RegenerateRequest,
    ConversationForkRequest,
    ConversationForkResponse,
    RegenerateResponse,
    SummaryResponse,
    ReconstructedContext,
    ContextWindowConfig,
    MessageRole,
)

logger = logging.getLogger(__name__)


# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    _ENCODING = tiktoken.get_encoding("cl100k_base")
    _HAS_TIKTOKEN = True
except ImportError:
    _ENCODING = None
    _HAS_TIKTOKEN = False
    logger.warning("tiktoken not available, using approximate token counting")


class ConversationService:
    """
    Service for managing conversations with context window optimization.

    Features:
    - Token-aware context window management
    - Rolling summarization when token threshold exceeded
    - Regenerate and fork support with branch tracking
    - Audit logging for compliance
    """

    # Summarization thresholds
    SUMMARIZE_THRESHOLD_TOKENS = 6000
    SUMMARY_TARGET_TOKENS = 500
    KEEP_RECENT_TURNS = 6  # Keep last N user-assistant turn pairs

    # Context window defaults
    DEFAULT_MAX_TOKENS = 8000
    RESERVED_FOR_RESPONSE = 2000
    SYSTEM_PROMPT_TOKENS = 500
    RAG_CONTEXT_TOKENS = 2000

    def __init__(
        self,
        repository: ConversationRepository,
        llm_service: Optional[Any] = None,
        audit_service: Optional[Any] = None
    ):
        """
        Initialize conversation service.

        Args:
            repository: Conversation repository implementation
            llm_service: Optional LLM service for summarization
            audit_service: Optional audit service for logging
        """
        self._repository = repository
        self._llm_service = llm_service
        self._audit_service = audit_service

    # ==================== Token Counting ====================

    @staticmethod
    def count_tokens(text: str) -> int:
        """
        Count tokens in text using tiktoken or approximation.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        if _HAS_TIKTOKEN and _ENCODING:
            return len(_ENCODING.encode(text))
        else:
            # Approximation: ~4 characters per token for English
            # Adjust for CJK characters (1-2 chars per token)
            cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff'
                          or '\u3040' <= c <= '\u30ff'
                          or '\uac00' <= c <= '\ud7af')
            other_count = len(text) - cjk_count
            return (cjk_count // 2) + (other_count // 4)

    def _count_message_tokens(self, message: MessageEntity) -> int:
        """Count tokens for a message (content + overhead)."""
        content_tokens = self.count_tokens(message.content)
        # Add overhead for role, formatting (~4 tokens)
        return content_tokens + 4

    # ==================== Conversation CRUD ====================

    async def create_conversation(
        self,
        user_id: str,
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        strategy: str = "auto",
        language: str = "auto",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationEntity:
        """
        Create a new conversation.

        Args:
            user_id: Owner user ID
            title: Optional conversation title
            project_id: Optional project association
            session_id: Optional session association
            strategy: RAG strategy (auto, vector, graph, hybrid, code)
            language: Response language (auto, ko, ja, en)
            metadata: Additional metadata

        Returns:
            Created conversation entity
        """
        entity = ConversationEntity(
            id=str(uuid4()),
            user_id=user_id,
            title=title,
            project_id=project_id,
            session_id=session_id,
            strategy=strategy,
            language=language,
            metadata=metadata or {}
        )

        conversation = await self._repository.create(entity)

        if self._audit_service:
            await self._log_audit(
                "conversation.created",
                user_id=user_id,
                conversation_id=conversation.id,
                details={"title": title, "strategy": strategy}
            )

        return conversation

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str,
        include_messages: bool = True
    ) -> Optional[ConversationDetail]:
        """
        Get conversation with optional messages.

        Args:
            conversation_id: Conversation ID
            user_id: Requesting user ID (for authorization)
            include_messages: Whether to include messages

        Returns:
            Conversation detail or None if not found
        """
        conversation = await self._repository.get_by_id(conversation_id)
        if not conversation:
            return None

        # Authorization check
        if conversation.user_id != user_id:
            logger.warning(f"User {user_id} attempted to access conversation {conversation_id}")
            return None

        messages = []
        active_summary = None

        if include_messages:
            message_entities = await self._repository.get_active_branch_messages(
                conversation_id
            )
            messages = [self._entity_to_message_response(m) for m in message_entities]

            summary = await self._repository.get_latest_summary(conversation_id)
            if summary:
                active_summary = summary.summary_text

        return ConversationDetail(
            id=UUID(conversation.id),
            title=conversation.title,
            user_id=conversation.user_id,
            project_id=conversation.project_id,
            session_id=conversation.session_id,
            message_count=conversation.message_count,
            total_tokens=conversation.total_tokens,
            is_archived=conversation.is_archived,
            is_starred=conversation.is_starred,
            strategy=conversation.strategy,
            language=conversation.language,
            metadata=conversation.metadata,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=messages,
            active_summary=active_summary
        )

    async def list_conversations(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        include_archived: bool = False
    ) -> List[ConversationListItem]:
        """
        List conversations for a user.

        Args:
            user_id: User ID
            skip: Number to skip
            limit: Maximum to return
            include_archived: Include archived conversations

        Returns:
            List of conversation list items
        """
        conversations = await self._repository.get_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
            include_archived=include_archived
        )

        return [self._entity_to_list_item(c) for c in conversations]

    async def update_conversation(
        self,
        conversation_id: str,
        user_id: str,
        update: ConversationUpdate
    ) -> Optional[ConversationEntity]:
        """
        Update a conversation.

        Args:
            conversation_id: Conversation ID
            user_id: Requesting user ID
            update: Update data

        Returns:
            Updated conversation or None
        """
        conversation = await self._repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            return None

        # Apply updates
        if update.title is not None:
            conversation.title = update.title
        if update.is_archived is not None:
            conversation.is_archived = update.is_archived
        if update.is_starred is not None:
            conversation.is_starred = update.is_starred
        if update.strategy is not None:
            conversation.strategy = update.strategy
        if update.language is not None:
            conversation.language = update.language
        if update.metadata is not None:
            conversation.metadata = update.metadata

        # Build update dict for repository
        update_data = update.model_dump(exclude_none=True)
        updated = await self._repository.update(conversation_id, update_data)

        if self._audit_service:
            await self._log_audit(
                "conversation.updated",
                user_id=user_id,
                conversation_id=conversation_id,
                details=update.model_dump(exclude_none=True)
            )

        return updated

    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: str,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete a conversation (soft by default).

        Args:
            conversation_id: Conversation ID
            user_id: Requesting user ID
            hard_delete: Whether to permanently delete

        Returns:
            True if deleted
        """
        conversation = await self._repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            return False

        if hard_delete:
            result = await self._repository.delete(conversation_id)
        else:
            result = await self._repository.soft_delete(conversation_id, user_id)

        if result and self._audit_service:
            await self._log_audit(
                "conversation.deleted",
                user_id=user_id,
                conversation_id=conversation_id,
                details={"hard_delete": hard_delete}
            )

        return result

    # ==================== Message Operations ====================

    async def add_user_message(
        self,
        conversation_id: str,
        user_id: str,
        content: str,
        parent_message_id: Optional[str] = None
    ) -> MessageEntity:
        """
        Add a user message to a conversation.

        Args:
            conversation_id: Conversation ID
            user_id: User ID for authorization
            content: Message content
            parent_message_id: Optional parent for branching

        Returns:
            Created message entity
        """
        # Verify ownership
        conversation = await self._repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise ValueError("Conversation not found or access denied")

        tokens = self.count_tokens(content)

        message = await self._repository.add_message(
            conversation_id=conversation_id,
            role="user",
            content=content,
            parent_message_id=parent_message_id,
            total_tokens=tokens
        )

        # Check if summarization needed
        await self._check_and_summarize(conversation_id)

        return message

    async def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        parent_message_id: Optional[str] = None,
        model: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> MessageEntity:
        """
        Add an assistant message to a conversation.

        Args:
            conversation_id: Conversation ID
            content: Message content
            parent_message_id: Parent message (usually the user message)
            model: LLM model used
            sources: RAG sources
            input_tokens: Input token count
            output_tokens: Output token count

        Returns:
            Created message entity
        """
        total_tokens = input_tokens + output_tokens
        if total_tokens == 0:
            total_tokens = self.count_tokens(content)

        message = await self._repository.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            parent_message_id=parent_message_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model=model,
            sources=sources
        )

        # Check if summarization needed
        await self._check_and_summarize(conversation_id)

        return message

    async def add_feedback(
        self,
        message_id: str,
        user_id: str,
        score: int,
        text: Optional[str] = None
    ) -> bool:
        """
        Add feedback to a message.

        Args:
            message_id: Message ID
            user_id: User ID for audit
            score: Feedback score (1-5)
            text: Optional feedback text

        Returns:
            True if updated
        """
        result = await self._repository.update_message_feedback(
            message_id=message_id,
            score=score,
            text=text
        )

        if result and self._audit_service:
            await self._log_audit(
                "message.feedback",
                user_id=user_id,
                details={"message_id": message_id, "score": score}
            )

        return result

    # ==================== Summarization ====================

    async def _check_and_summarize(self, conversation_id: str) -> None:
        """Check if summarization is needed and perform if necessary."""
        total_tokens = await self._repository.get_token_count(conversation_id)

        if total_tokens > self.SUMMARIZE_THRESHOLD_TOKENS:
            await self._perform_rolling_summary(conversation_id)

    async def _perform_rolling_summary(self, conversation_id: str) -> Optional[SummaryEntity]:
        """
        Perform rolling summarization of older messages.

        Keeps the last N turns and summarizes earlier messages.
        """
        messages = await self._repository.get_active_branch_messages(conversation_id)
        if len(messages) < self.KEEP_RECENT_TURNS * 2 + 2:
            # Not enough messages to summarize
            return None

        # Split messages: keep recent, summarize older
        keep_count = self.KEEP_RECENT_TURNS * 2  # pairs of user/assistant
        messages_to_summarize = messages[:-keep_count]

        if not messages_to_summarize:
            return None

        # Get existing summary to build upon
        existing_summary = await self._repository.get_latest_summary(conversation_id)
        existing_text = existing_summary.summary_text if existing_summary else ""

        # Calculate tokens before summary
        tokens_before = sum(self._count_message_tokens(m) for m in messages_to_summarize)
        if existing_summary:
            tokens_before += self.count_tokens(existing_text)

        # Generate summary
        summary_text = await self._generate_summary(
            messages_to_summarize,
            existing_summary=existing_text
        )

        tokens_after = self.count_tokens(summary_text)

        # Store summary
        summary = await self._repository.add_summary(
            conversation_id=conversation_id,
            summary_text=summary_text,
            summary_type="rolling",
            covers_from_id=messages_to_summarize[0].id if messages_to_summarize else None,
            covers_to_id=messages_to_summarize[-1].id if messages_to_summarize else None,
            message_count=len(messages_to_summarize),
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            key_topics=self._extract_topics(messages_to_summarize)
        )

        logger.info(
            f"Created rolling summary for conversation {conversation_id}: "
            f"{tokens_before} -> {tokens_after} tokens "
            f"(compression: {tokens_after/tokens_before:.2%})"
        )

        return summary

    async def _generate_summary(
        self,
        messages: List[MessageEntity],
        existing_summary: str = ""
    ) -> str:
        """
        Generate a summary of messages using LLM.

        Falls back to extractive summary if LLM not available.
        """
        if self._llm_service:
            # Build conversation text for summarization
            conversation_text = self._format_messages_for_summary(messages)

            prompt = f"""Summarize the following conversation, preserving key information, decisions, and context that would be needed to continue the discussion.

{f"Previous summary: {existing_summary}" if existing_summary else ""}

Conversation:
{conversation_text}

Summary (be concise but preserve important details):"""

            try:
                response = await self._llm_service.generate(
                    prompt=prompt,
                    max_tokens=self.SUMMARY_TARGET_TOKENS
                )
                return response.get("text", "").strip()
            except Exception as e:
                logger.error(f"LLM summarization failed: {e}")

        # Fallback: extractive summary
        return self._extractive_summary(messages, existing_summary)

    def _extractive_summary(
        self,
        messages: List[MessageEntity],
        existing_summary: str = ""
    ) -> str:
        """Create an extractive summary from messages."""
        parts = []

        if existing_summary:
            parts.append(f"Previous context: {existing_summary[:500]}")

        # Extract key points from messages
        for msg in messages:
            if msg.role == "user":
                # First 100 chars of user questions
                content = msg.content[:100]
                parts.append(f"Q: {content}...")
            elif msg.role == "assistant":
                # First 200 chars of assistant responses
                content = msg.content[:200]
                parts.append(f"A: {content}...")

        # Truncate to target tokens
        summary = "\n".join(parts)
        while self.count_tokens(summary) > self.SUMMARY_TARGET_TOKENS and parts:
            parts.pop()
            summary = "\n".join(parts)

        return summary

    def _format_messages_for_summary(self, messages: List[MessageEntity]) -> str:
        """Format messages for summarization prompt."""
        lines = []
        for msg in messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            lines.append(f"{role_label}: {msg.content}")
        return "\n\n".join(lines)

    def _extract_topics(self, messages: List[MessageEntity]) -> List[str]:
        """Extract key topics from messages (simple keyword extraction)."""
        # Simple implementation - could be enhanced with NLP
        topics = set()
        for msg in messages:
            # Extract capitalized words as potential topics
            words = msg.content.split()
            for word in words:
                if len(word) > 3 and word[0].isupper() and word.isalpha():
                    topics.add(word)
        return list(topics)[:10]

    # ==================== Context Reconstruction ====================

    async def build_context_for_rag(
        self,
        conversation_id: str,
        current_input: str,
        rag_context: Optional[str] = None,
        system_prompt: Optional[str] = None,
        config: Optional[ContextWindowConfig] = None
    ) -> ReconstructedContext:
        """
        Build reconstructed context for RAG query.

        Args:
            conversation_id: Conversation ID
            current_input: Current user input
            rag_context: Retrieved RAG context
            system_prompt: System prompt to use
            config: Context window configuration

        Returns:
            ReconstructedContext with all components
        """
        config = config or ContextWindowConfig()

        # Calculate available token budget
        available_tokens = (
            config.max_tokens
            - config.reserved_for_response
            - config.system_prompt_tokens
            - config.rag_context_tokens
        )

        # Get context window from repository
        context_data = await self._repository.get_context_window(
            conversation_id=conversation_id,
            max_tokens=available_tokens,
            include_summary=True
        )

        # Format recent messages and respect recent_turns_count limit
        recent_messages = []
        messages_to_include = context_data["messages"]

        # Limit by recent_turns_count if specified (each turn = 2 messages)
        max_messages = config.recent_turns_count * 2
        if len(messages_to_include) > max_messages:
            messages_to_include = messages_to_include[-max_messages:]

        for msg in messages_to_include:
            recent_messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Build default system prompt if not provided
        if not system_prompt:
            system_prompt = self._build_system_prompt()

        # Calculate actual token usage
        total_tokens = (
            self.count_tokens(system_prompt)
            + context_data["total_tokens"]
            + self.count_tokens(current_input)
            + (self.count_tokens(rag_context) if rag_context else 0)
        )

        return ReconstructedContext(
            system_prompt=system_prompt,
            summary=context_data["summary"],
            recent_messages=recent_messages,
            rag_context=rag_context,
            current_input=current_input,
            total_tokens=total_tokens,
            summary_used=context_data["summary"] is not None,
            messages_included=len(recent_messages),
            messages_summarized=context_data["messages_summarized"]
        )

    def _build_system_prompt(self) -> str:
        """Build default system prompt."""
        return """You are a helpful AI assistant with access to a knowledge base.
Use the provided context to answer questions accurately.
If you don't know the answer based on the context, say so.
Always cite sources when available."""

    # ==================== Regenerate Operations ====================

    async def regenerate_response(
        self,
        message_id: str,
        user_id: str,
        new_content: str,
        model: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> RegenerateResponse:
        """
        Regenerate an assistant response.

        Args:
            message_id: Original message ID to regenerate
            user_id: User ID for authorization
            new_content: New response content
            model: LLM model used
            sources: RAG sources
            input_tokens: Input token count
            output_tokens: Output token count

        Returns:
            RegenerateResponse with new and original message info
        """
        # Verify the message exists and user has access
        original = await self._repository.get_message(message_id)
        if not original:
            raise ValueError(f"Message {message_id} not found")

        # Verify conversation ownership
        conversation = await self._repository.get_by_id(original.conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise ValueError("Access denied")

        if original.role != "assistant":
            raise ValueError("Can only regenerate assistant messages")

        total_tokens = input_tokens + output_tokens
        if total_tokens == 0:
            total_tokens = self.count_tokens(new_content)

        # Perform regeneration
        new_message, updated_original = await self._repository.regenerate_message(
            original_message_id=message_id,
            new_content=new_content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            model=model,
            sources=sources
        )

        if self._audit_service:
            await self._log_audit(
                "message.regenerated",
                user_id=user_id,
                conversation_id=original.conversation_id,
                details={
                    "original_message_id": message_id,
                    "new_message_id": new_message.id,
                    "regeneration_count": new_message.regeneration_count
                }
            )

        return RegenerateResponse(
            original_message_id=UUID(message_id),
            new_message=self._entity_to_message_response(new_message),
            regeneration_count=new_message.regeneration_count
        )

    # ==================== Fork Operations ====================

    async def fork_conversation(
        self,
        conversation_id: str,
        from_message_id: str,
        user_id: str,
        new_title: Optional[str] = None
    ) -> ConversationForkResponse:
        """
        Fork a conversation from a specific message.

        Args:
            conversation_id: Source conversation ID
            from_message_id: Fork point message ID
            user_id: User ID (owner of new conversation)
            new_title: Title for forked conversation

        Returns:
            ConversationForkResponse with new conversation details
        """
        # Verify source conversation exists and user has access
        source = await self._repository.get_by_id(conversation_id)
        if not source or source.user_id != user_id:
            raise ValueError("Conversation not found or access denied")

        # Perform fork
        new_conversation, messages_copied = await self._repository.fork_conversation(
            conversation_id=conversation_id,
            from_message_id=from_message_id,
            new_user_id=user_id,
            new_title=new_title
        )

        if self._audit_service:
            await self._log_audit(
                "conversation.forked",
                user_id=user_id,
                conversation_id=new_conversation.id,
                details={
                    "source_conversation_id": conversation_id,
                    "fork_point": from_message_id,
                    "messages_copied": messages_copied
                }
            )

        # Get full conversation detail
        detail = await self.get_conversation(
            new_conversation.id,
            user_id,
            include_messages=True
        )

        # Handle both string and UUID inputs
        orig_id = conversation_id if isinstance(conversation_id, UUID) else UUID(conversation_id)
        fork_msg_id = from_message_id if isinstance(from_message_id, UUID) else UUID(from_message_id)

        return ConversationForkResponse(
            original_conversation_id=orig_id,
            new_conversation=detail,
            forked_from_message_id=fork_msg_id,
            messages_copied=messages_copied
        )

    # ==================== Search ====================

    async def search_conversations(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Tuple[ConversationListItem, float]]:
        """
        Search conversations by content.

        Args:
            user_id: User ID
            query: Search query
            limit: Maximum results

        Returns:
            List of (conversation, relevance_score) tuples
        """
        results = await self._repository.search(
            user_id=user_id,
            query=query,
            limit=limit
        )

        return [
            (self._entity_to_list_item(conv), score)
            for conv, score in results
        ]

    # ==================== Statistics ====================

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get conversation statistics for a user."""
        return await self._repository.get_user_stats(user_id)

    # ==================== Helper Methods ====================

    def _entity_to_message_response(self, entity: MessageEntity) -> MessageResponse:
        """Convert MessageEntity to MessageResponse."""
        return MessageResponse(
            id=UUID(entity.id),
            conversation_id=UUID(entity.conversation_id),
            parent_message_id=UUID(entity.parent_message_id) if entity.parent_message_id else None,
            role=MessageRole(entity.role),
            content=entity.content,
            input_tokens=entity.input_tokens,
            output_tokens=entity.output_tokens,
            total_tokens=entity.total_tokens,
            model=entity.model,
            sources=entity.sources,
            feedback_score=entity.feedback_score,
            feedback_text=entity.feedback_text,
            is_regenerated=entity.is_regenerated,
            regeneration_count=entity.regeneration_count,
            is_active_branch=entity.is_active_branch,
            branch_depth=entity.branch_depth,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )

    def _entity_to_list_item(self, entity: ConversationEntity) -> ConversationListItem:
        """Convert ConversationEntity to ConversationListItem."""
        return ConversationListItem(
            id=UUID(entity.id),
            title=entity.title,
            message_count=entity.message_count,
            total_tokens=entity.total_tokens,
            is_archived=entity.is_archived,
            is_starred=entity.is_starred,
            strategy=entity.strategy,
            language=entity.language,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )

    async def _log_audit(
        self,
        event_type: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log audit event if audit service available."""
        if self._audit_service:
            try:
                await self._audit_service.log(
                    event_type=event_type,
                    user_id=user_id,
                    resource_id=conversation_id,
                    details=details or {}
                )
            except Exception as e:
                logger.warning(f"Failed to log audit event: {e}")


# Singleton instance
_conversation_service: Optional[ConversationService] = None


def get_conversation_service() -> ConversationService:
    """Get the global conversation service instance."""
    global _conversation_service
    if _conversation_service is None:
        # Import here to avoid circular imports
        from ..infrastructure.memory.conversation_repository import MemoryConversationRepository
        _conversation_service = ConversationService(
            repository=MemoryConversationRepository()
        )
    return _conversation_service


def set_conversation_service(service: ConversationService) -> None:
    """Set the global conversation service instance."""
    global _conversation_service
    _conversation_service = service
