"""
Conversation-RAG Integration Service

Bridges the conversation service with the RAG service to provide:
- Conversation-aware queries with context reconstruction
- Automatic message persistence
- Token tracking and summarization triggers
"""
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

from .rag_service import RAGService
from .conversation_service import ConversationService, get_conversation_service
from ..models.conversation import ReconstructedContext, ContextWindowConfig

logger = logging.getLogger(__name__)


class ConversationRAGIntegration:
    """
    Integration layer between Conversation and RAG services.

    Handles:
    - Building conversation context for RAG queries
    - Storing messages with RAG sources
    - Managing conversation flow
    """

    def __init__(
        self,
        rag_service: Optional[RAGService] = None,
        conversation_service: Optional[ConversationService] = None
    ):
        """
        Initialize integration.

        Args:
            rag_service: RAG service instance
            conversation_service: Conversation service instance
        """
        self._rag = rag_service or RAGService.get_instance()
        self._conversation = conversation_service or get_conversation_service()

    async def query_with_conversation(
        self,
        question: str,
        conversation_id: str,
        user_id: str,
        *,
        strategy: str = "auto",
        language: str = "auto",
        top_k: int = 5,
        session_id: Optional[str] = None,
        use_session_docs: bool = True,
        use_external_resources: bool = True
    ) -> Dict[str, Any]:
        """
        Execute RAG query with conversation context.

        This method:
        1. Adds the user question as a message
        2. Reconstructs conversation context
        3. Executes RAG query with context
        4. Stores the assistant response
        5. Returns the complete response

        Args:
            question: User's question
            conversation_id: Conversation ID
            user_id: User ID for authorization
            strategy: RAG strategy (auto, vector, graph, hybrid, code)
            language: Response language (auto, ko, ja, en)
            top_k: Number of results to retrieve
            session_id: Optional session ID for session documents
            use_session_docs: Whether to use session documents
            use_external_resources: Whether to use external resources

        Returns:
            Dict with answer, sources, message IDs, and metadata
        """
        # Step 1: Verify conversation access and get current state
        conversation = await self._conversation.get_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            include_messages=False
        )

        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found or access denied")

        # Step 2: Add user message
        user_message = await self._conversation.add_user_message(
            conversation_id=conversation_id,
            user_id=user_id,
            content=question
        )

        # Step 3: Get the last few messages for context
        context_data = await self._conversation._repository.get_context_window(
            conversation_id=conversation_id,
            max_tokens=4000,
            include_summary=True
        )

        # Build conversation history for RAG
        conversation_history = self._build_conversation_history(
            messages=context_data["messages"],
            summary=context_data.get("summary")
        )

        # Step 4: Execute RAG query with conversation context
        rag_result = await self._rag.query(
            question=question,
            strategy=strategy,
            language=language,
            top_k=top_k,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            session_id=session_id or conversation.session_id,
            use_session_docs=use_session_docs,
            user_id=user_id,
            use_external_resources=use_external_resources
        )

        # Step 5: Store assistant response
        assistant_message = await self._conversation.add_assistant_message(
            conversation_id=conversation_id,
            content=rag_result.get("answer", ""),
            parent_message_id=user_message.id,
            model=None,  # Would come from RAG config
            sources=rag_result.get("sources", []),
            input_tokens=0,  # Would need token counting from RAG
            output_tokens=0
        )

        # Step 6: Build complete response
        return {
            "answer": rag_result.get("answer", ""),
            "sources": rag_result.get("sources", []),
            "strategy": rag_result.get("strategy", strategy),
            "language": rag_result.get("language", language),
            "confidence": rag_result.get("confidence", 0.0),
            "conversation_id": conversation_id,
            "user_message_id": user_message.id,
            "assistant_message_id": assistant_message.id,
            "context_info": {
                "messages_in_context": len(context_data["messages"]),
                "summary_used": context_data.get("summary") is not None,
                "total_context_tokens": context_data.get("total_tokens", 0)
            },
            "query_analysis": rag_result.get("query_analysis", {})
        }

    async def regenerate_with_rag(
        self,
        message_id: str,
        user_id: str,
        *,
        strategy: Optional[str] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Regenerate an assistant response using RAG.

        Args:
            message_id: Original assistant message ID to regenerate
            user_id: User ID for authorization
            strategy: Optional different strategy
            language: Optional different language

        Returns:
            Dict with new response and metadata
        """
        # Get original message
        original = await self._conversation._repository.get_message(message_id)
        if not original:
            raise ValueError(f"Message {message_id} not found")

        # Verify it's an assistant message
        if original.role != "assistant":
            raise ValueError("Can only regenerate assistant messages")

        # Get conversation and verify access
        conversation = await self._conversation.get_conversation(
            conversation_id=original.conversation_id,
            user_id=user_id,
            include_messages=False
        )

        if not conversation:
            raise ValueError("Conversation not found or access denied")

        # Get the user message that prompted this response
        # (should be the parent message)
        parent_message = None
        if original.parent_message_id:
            parent_message = await self._conversation._repository.get_message(
                original.parent_message_id
            )

        if not parent_message or parent_message.role != "user":
            raise ValueError("Could not find original user question for regeneration")

        # Use conversation's strategy/language if not overridden
        regen_strategy = strategy or conversation.strategy or "auto"
        regen_language = language or conversation.language or "auto"

        # Get context (excluding the message being regenerated)
        context_data = await self._conversation._repository.get_context_window(
            conversation_id=original.conversation_id,
            max_tokens=4000,
            include_summary=True
        )

        # Filter out the original response from context
        filtered_messages = [
            m for m in context_data["messages"]
            if m.id != original.id
        ]

        conversation_history = self._build_conversation_history(
            messages=filtered_messages,
            summary=context_data.get("summary")
        )

        # Execute RAG query
        rag_result = await self._rag.query(
            question=parent_message.content,
            strategy=regen_strategy,
            language=regen_language,
            conversation_id=original.conversation_id,
            conversation_history=conversation_history,
            session_id=conversation.session_id,
            user_id=user_id
        )

        # Regenerate message
        regen_response = await self._conversation.regenerate_response(
            message_id=message_id,
            user_id=user_id,
            new_content=rag_result.get("answer", ""),
            sources=rag_result.get("sources", [])
        )

        return {
            "new_message": regen_response.new_message,
            "original_message_id": message_id,
            "regeneration_count": regen_response.regeneration_count,
            "strategy": rag_result.get("strategy", regen_strategy),
            "language": rag_result.get("language", regen_language),
            "sources": rag_result.get("sources", [])
        }

    async def continue_conversation(
        self,
        conversation_id: str,
        user_id: str,
        question: str,
        parent_message_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Continue an existing conversation with a new question.

        This is a convenience method that handles branching if
        parent_message_id is provided.

        Args:
            conversation_id: Conversation ID
            user_id: User ID
            question: New question
            parent_message_id: Optional parent for branching
            **kwargs: Additional args passed to query_with_conversation

        Returns:
            Query result with message IDs
        """
        return await self.query_with_conversation(
            question=question,
            conversation_id=conversation_id,
            user_id=user_id,
            **kwargs
        )

    def _build_conversation_history(
        self,
        messages: List[Any],
        summary: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Build conversation history for RAG context.

        Args:
            messages: List of MessageEntity
            summary: Optional conversation summary

        Returns:
            List of {role, content} dicts
        """
        history = []

        # Add summary as system context if available
        if summary:
            history.append({
                "role": "system",
                "content": f"Previous conversation summary: {summary}"
            })

        # Add messages
        for msg in messages:
            history.append({
                "role": msg.role,
                "content": msg.content
            })

        return history


# Singleton instance
_integration: Optional[ConversationRAGIntegration] = None


def get_conversation_rag_integration() -> ConversationRAGIntegration:
    """Get the global integration instance."""
    global _integration
    if _integration is None:
        _integration = ConversationRAGIntegration()
    return _integration
