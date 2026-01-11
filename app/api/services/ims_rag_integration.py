"""
IMS RAG Integration Service

Provides AI chat functionality over crawled IMS issues.
Context is LIMITED to searched/crawled issues only - not general knowledge.
"""
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from uuid import UUID, uuid4
from datetime import datetime, timezone

from ..ports.llm_port import LLMPort, LLMMessage, LLMRole, LLMConfig, LLMStreamChunk
from ..ims_crawler.infrastructure.ports.issue_repository_port import IssueRepositoryPort
from ..ims_crawler.domain.entities import Issue
from ..models.ims_chat import (
    IMSChatRequest,
    IMSChatResponse,
    IMSChatStreamEvent,
    IMSIssueContext,
    IMSChatRole,
    IMSChatConversation,
    IMSChatMessage
)

logger = logging.getLogger(__name__)


class IMSRAGIntegrationService:
    """
    IMS RAG Integration Service.

    Provides AI-powered chat about crawled IMS issues.
    The chat context is STRICTLY LIMITED to the specified issue_ids.
    """

    # System prompt template for IMS chat
    SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant specialized in analyzing TmaxSoft IMS (Issue Management System) issues.

Your knowledge is LIMITED to the following IMS issues that were searched/crawled by the user.
You MUST only answer questions based on the provided issue context.
If a question cannot be answered from the provided issues, say so clearly.

IMPORTANT RULES:
1. Only use information from the provided IMS issues
2. When referencing issues, always cite the IMS ID (e.g., IMS-12345)
3. Provide accurate technical information from the issue details
4. If you're unsure, say so - don't make up information
5. Respond in the same language as the user's question (Korean, Japanese, or English)

Available IMS Issues for context:
{issue_context}

Total issues in context: {issue_count}
"""

    def __init__(
        self,
        llm: LLMPort,
        issue_repository: IssueRepositoryPort
    ):
        """
        Initialize IMS RAG Integration Service.

        Args:
            llm: LLM adapter for generating responses
            issue_repository: Repository for fetching IMS issues
        """
        self.llm = llm
        self.issue_repo = issue_repository

        # In-memory conversation storage (can be replaced with persistent storage)
        self._conversations: Dict[UUID, IMSChatConversation] = {}

    async def chat(
        self,
        request: IMSChatRequest,
        user_id: UUID
    ) -> IMSChatResponse:
        """
        Process a chat request (non-streaming).

        Args:
            request: Chat request with question and issue_ids
            user_id: User ID for authorization

        Returns:
            IMSChatResponse with the answer
        """
        # Fetch issues by IDs
        issues = await self.issue_repo.find_by_ids_with_details(
            issue_ids=list(request.issue_ids),
            user_id=user_id
        )

        if not issues:
            raise ValueError("No valid issues found for the provided IDs")

        # Limit number of issues in context
        context_issues = issues[:request.max_context_issues]

        # Build system prompt with issue context
        system_prompt = self._build_system_prompt(context_issues)

        # Get or create conversation
        conversation = self._get_or_create_conversation(
            conversation_id=request.conversation_id,
            issue_ids=request.issue_ids
        )

        # Build messages for LLM
        messages = self._build_llm_messages(
            system_prompt=system_prompt,
            conversation=conversation,
            user_question=request.question
        )

        # Generate response
        config = LLMConfig(
            temperature=0.3,  # Lower temperature for factual responses
            max_tokens=2048
        )

        response = await self.llm.generate(messages, config)

        # Create message IDs
        message_id = uuid4()
        now = datetime.now(timezone.utc)

        # Store messages in conversation
        user_message = IMSChatMessage(
            id=uuid4(),
            role=IMSChatRole.USER,
            content=request.question,
            created_at=now,
            referenced_issues=[]
        )

        assistant_message = IMSChatMessage(
            id=message_id,
            role=IMSChatRole.ASSISTANT,
            content=response.content,
            created_at=now,
            referenced_issues=self._extract_referenced_issues(response.content, context_issues)
        )

        conversation.messages.append(user_message)
        conversation.messages.append(assistant_message)
        conversation.updated_at = now
        self._conversations[conversation.id] = conversation

        # Build referenced issues for response
        referenced_issues = [
            IMSIssueContext(
                issue_id=issue.id,
                ims_id=issue.ims_id,
                title=issue.title,
                status_raw=issue.status_raw,
                priority_raw=issue.priority_raw,
                product=issue.product,
                version=issue.version,
                module=issue.module,
                customer=issue.customer,
                description=issue.description[:500] if issue.description else None,
                relevance_score=1.0
            )
            for issue in context_issues
        ]

        return IMSChatResponse(
            conversation_id=conversation.id,
            message_id=message_id,
            content=response.content,
            role=IMSChatRole.ASSISTANT,
            referenced_issues=referenced_issues,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            created_at=now
        )

    async def chat_stream(
        self,
        request: IMSChatRequest,
        user_id: UUID
    ) -> AsyncGenerator[IMSChatStreamEvent, None]:
        """
        Process a chat request with streaming response.

        Args:
            request: Chat request with question and issue_ids
            user_id: User ID for authorization

        Yields:
            IMSChatStreamEvent for SSE streaming
        """
        try:
            # Fetch issues by IDs
            issues = await self.issue_repo.find_by_ids_with_details(
                issue_ids=list(request.issue_ids),
                user_id=user_id
            )

            if not issues:
                yield IMSChatStreamEvent(
                    event="error",
                    data={"message": "No valid issues found for the provided IDs"}
                )
                return

            # Limit number of issues in context
            context_issues = issues[:request.max_context_issues]

            # Get or create conversation
            conversation = self._get_or_create_conversation(
                conversation_id=request.conversation_id,
                issue_ids=request.issue_ids
            )

            message_id = uuid4()
            now = datetime.now(timezone.utc)

            # Emit start event
            yield IMSChatStreamEvent(
                event="start",
                data={
                    "conversation_id": str(conversation.id),
                    "message_id": str(message_id),
                    "issues_count": len(context_issues)
                }
            )

            # Build system prompt with issue context
            system_prompt = self._build_system_prompt(context_issues)

            # Build messages for LLM
            messages = self._build_llm_messages(
                system_prompt=system_prompt,
                conversation=conversation,
                user_question=request.question
            )

            # Generate streaming response
            config = LLMConfig(
                temperature=0.3,
                max_tokens=2048
            )

            full_content = ""
            async for chunk in self.llm.generate_stream(messages, config):
                full_content += chunk.content

                yield IMSChatStreamEvent(
                    event="token",
                    data={
                        "content": chunk.content,
                        "is_final": chunk.is_final
                    }
                )

            # Store messages in conversation
            user_message = IMSChatMessage(
                id=uuid4(),
                role=IMSChatRole.USER,
                content=request.question,
                created_at=now,
                referenced_issues=[]
            )

            assistant_message = IMSChatMessage(
                id=message_id,
                role=IMSChatRole.ASSISTANT,
                content=full_content,
                created_at=now,
                referenced_issues=self._extract_referenced_issues(full_content, context_issues)
            )

            conversation.messages.append(user_message)
            conversation.messages.append(assistant_message)
            conversation.updated_at = now
            self._conversations[conversation.id] = conversation

            # Emit sources event
            sources = [
                {
                    "issue_id": str(issue.id),
                    "ims_id": issue.ims_id,
                    "title": issue.title,
                    "status": issue.status_raw or issue.status.value,
                    "priority": issue.priority_raw or issue.priority.value
                }
                for issue in context_issues
            ]

            yield IMSChatStreamEvent(
                event="sources",
                data={"sources": sources}
            )

            # Emit done event
            yield IMSChatStreamEvent(
                event="done",
                data={
                    "conversation_id": str(conversation.id),
                    "message_id": str(message_id),
                    "total_issues": len(context_issues)
                }
            )

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield IMSChatStreamEvent(
                event="error",
                data={"message": str(e)}
            )

    def _build_system_prompt(self, issues: List[Issue]) -> str:
        """Build system prompt with issue context."""
        issue_contexts = []

        for issue in issues:
            context = f"""
--- Issue: {issue.ims_id} ---
Title: {issue.title}
Status: {issue.status_raw or issue.status.value}
Priority: {issue.priority_raw or issue.priority.value}
Product: {issue.product or 'N/A'}
Version: {issue.version or 'N/A'}
Module: {issue.module or 'N/A'}
Customer: {issue.customer or 'N/A'}
Reporter: {issue.reporter or 'N/A'}
Created: {issue.created_at.strftime('%Y-%m-%d') if issue.created_at else 'N/A'}

Description:
{issue.description or 'No description'}

Issue Details:
{issue.issue_details or 'No additional details'}

Action Notes:
{issue.action_no or 'No action notes'}
---
"""
            issue_contexts.append(context)

        return self.SYSTEM_PROMPT_TEMPLATE.format(
            issue_context="\n".join(issue_contexts),
            issue_count=len(issues)
        )

    def _build_llm_messages(
        self,
        system_prompt: str,
        conversation: IMSChatConversation,
        user_question: str
    ) -> List[LLMMessage]:
        """Build message list for LLM."""
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=system_prompt)
        ]

        # Add conversation history (last 10 messages for context window management)
        history_messages = conversation.messages[-10:]
        for msg in history_messages:
            if msg.role == IMSChatRole.USER:
                messages.append(LLMMessage(role=LLMRole.USER, content=msg.content))
            elif msg.role == IMSChatRole.ASSISTANT:
                messages.append(LLMMessage(role=LLMRole.ASSISTANT, content=msg.content))

        # Add current question
        messages.append(LLMMessage(role=LLMRole.USER, content=user_question))

        return messages

    def _get_or_create_conversation(
        self,
        conversation_id: Optional[UUID],
        issue_ids: List[UUID]
    ) -> IMSChatConversation:
        """Get existing conversation or create new one."""
        if conversation_id and conversation_id in self._conversations:
            return self._conversations[conversation_id]

        # Create new conversation
        now = datetime.now(timezone.utc)
        new_conversation = IMSChatConversation(
            id=uuid4(),
            title=None,
            issue_ids=list(issue_ids),
            messages=[],
            created_at=now,
            updated_at=now
        )
        self._conversations[new_conversation.id] = new_conversation
        return new_conversation

    def _extract_referenced_issues(
        self,
        content: str,
        context_issues: List[Issue]
    ) -> List[str]:
        """Extract IMS IDs referenced in the response content."""
        referenced = []
        for issue in context_issues:
            if issue.ims_id in content:
                referenced.append(issue.ims_id)
        return referenced

    def get_conversation(self, conversation_id: UUID) -> Optional[IMSChatConversation]:
        """Get a conversation by ID."""
        return self._conversations.get(conversation_id)

    def list_conversations(self, limit: int = 20) -> List[IMSChatConversation]:
        """List recent conversations."""
        conversations = list(self._conversations.values())
        conversations.sort(key=lambda c: c.updated_at, reverse=True)
        return conversations[:limit]


# Singleton instance
_ims_rag_service: Optional[IMSRAGIntegrationService] = None


async def get_ims_rag_service() -> IMSRAGIntegrationService:
    """
    Get the IMS RAG Integration Service singleton.

    Uses Ollama for local testing if USE_OLLAMA=true environment variable is set.
    Otherwise uses the container's default LLM.
    """
    global _ims_rag_service

    if _ims_rag_service is None:
        import os
        from ..ims_crawler.infrastructure.dependencies import get_issue_repository

        issue_repo = await get_issue_repository()

        # Check if we should use Ollama for local testing
        use_ollama = os.getenv("USE_OLLAMA", "false").lower() in ("true", "1", "yes")
        ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:1b")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

        if use_ollama:
            from ..adapters.ollama import OllamaLLMAdapter
            llm = OllamaLLMAdapter(model=ollama_model, base_url=ollama_url)
            logger.info(f"[OK] IMSRAGIntegrationService initialized with Ollama ({ollama_model})")
        else:
            from ..core.container import get_container
            container = get_container()
            llm = container.llm
            logger.info("[OK] IMSRAGIntegrationService initialized with default LLM")

        _ims_rag_service = IMSRAGIntegrationService(
            llm=llm,
            issue_repository=issue_repo
        )

    return _ims_rag_service


def reset_ims_rag_service() -> None:
    """Reset the singleton instance (useful for testing with different LLM)."""
    global _ims_rag_service
    _ims_rag_service = None
    logger.info("[OK] IMSRAGIntegrationService singleton reset")
