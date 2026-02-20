"""Modernization Chat Service - Routes chat to HOST/OpenFrame/ALL handlers.

Integrates with ConversationService for PostgreSQL persistence.
Source code explanation requests are always routed to HOST handler.
Singleton pattern following project conventions.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..agents.chat_adapter import _is_source_explanation_request, _mentions_source_code
from ..routers.chat_schemas import ModernizationChatRequest, SystemType

logger = logging.getLogger(__name__)

# Agent type used for filtering modernization conversations
AGENT_TYPE = "modernization"


class ModernizationChatService:
    """Chat routing service for Legacy Modernization AI Assistant.

    Persists chat history to PostgreSQL via ConversationService.
    """

    _instance: Optional["ModernizationChatService"] = None

    def __init__(self):
        self._conversation_service = None

    def _get_conversation_service(self):
        """Lazy-load ConversationService to avoid circular imports."""
        if self._conversation_service is None:
            try:
                from ...services.conversation_service import get_conversation_service
                self._conversation_service = get_conversation_service()
                logger.info("ModernizationChatService: ConversationService loaded")
            except Exception as e:
                logger.warning(f"ConversationService not available: {e}")
        return self._conversation_service

    async def stream_chat(
        self, request: ModernizationChatRequest, user_id: str = "anonymous"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Route and stream chat based on system_type, with DB persistence."""

        # 1. Get or create conversation
        conv_id = request.conversation_id
        conv_service = self._get_conversation_service()

        if conv_service and not conv_id:
            try:
                conv = await conv_service.create_conversation(
                    user_id=user_id,
                    agent_type=AGENT_TYPE,
                    language=request.language,
                    metadata={
                        "system_type": request.system_type.value,
                    },
                )
                conv_id = conv.id
                logger.info(f"Created modernization conversation: {conv_id}")
            except Exception as e:
                logger.error(f"Failed to create conversation: {e}")

        # 2. Save user message
        if conv_service and conv_id:
            try:
                await conv_service.add_user_message(
                    conversation_id=conv_id,
                    user_id=user_id,
                    content=request.message,
                )
            except Exception as e:
                logger.error(f"Failed to save user message: {e}")

        # 3. Emit conversation_id so frontend can track it
        if conv_id:
            yield {"type": "conversation_id", "conversation_id": conv_id}

        # 4. Stream response and accumulate for persistence
        full_response = ""
        all_sources: List[Dict[str, Any]] = []

        # Source-related requests always route to HOST handler
        # (explicit intent patterns OR broad keyword match when source code is present)
        has_source = bool(
            request.analysis_context
            and (request.analysis_context.source_code_full or request.analysis_context.source_code_snippet)
        )
        mentions_source = (
            _is_source_explanation_request(request.message)
            or _mentions_source_code(request.message)
        )
        # Bug 4 fix: explicit source explanation requests always route to HOST
        # (even without source code present, HOST handler will provide general response)
        is_explicit_source_request = _is_source_explanation_request(request.message)
        use_host = (
            request.system_type == SystemType.HOST
            or (mentions_source and has_source)
            or is_explicit_source_request
        )

        if use_host:
            async for event in self._stream_host(request):
                if event.get("type") == "llm_token":
                    full_response += event.get("token", "")
                elif event.get("type") == "sources":
                    all_sources.extend(event.get("sources", []))
                yield event
        elif request.system_type == SystemType.OPENFRAME:
            async for event in self._stream_openframe(request, user_id):
                if event.get("type") == "llm_token":
                    full_response += event.get("token", "")
                elif event.get("type") == "sources":
                    all_sources.extend(event.get("results", event.get("sources", [])))
                yield event
        else:  # ALL
            async for event in self._stream_combined(request, user_id):
                if event.get("type") == "llm_token":
                    full_response += event.get("token", "")
                elif event.get("type") == "sources":
                    all_sources.extend(event.get("results", event.get("sources", [])))
                yield event

        # 5. Save assistant response after streaming completes
        if conv_service and conv_id and full_response.strip():
            try:
                await conv_service.add_assistant_message(
                    conversation_id=conv_id,
                    content=full_response,
                    sources=all_sources if all_sources else None,
                )
            except Exception as e:
                logger.error(f"Failed to save assistant message: {e}")

    async def _stream_host(
        self, request: ModernizationChatRequest
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream HOST system analysis via LegacyChatAdapter → vLLM."""
        from ..agents.chat_adapter import get_legacy_chat_adapter

        adapter = get_legacy_chat_adapter()
        analysis_ctx = request.analysis_context.model_dump() if request.analysis_context else None

        async for event in adapter.stream_chat(
            message=request.message,
            language=request.language,
            analysis_context=analysis_ctx,
        ):
            yield event

    async def _stream_openframe(
        self, request: ModernizationChatRequest, user_id: str = "anonymous"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream OpenFrame RAG via AgenticRAGService."""
        from ...models.agentic_rag import AgenticRAGRequest
        from ...services.agent_teams.team_orchestrator import get_team_orchestrator

        yield {"type": "system_info", "system_type": "openframe"}

        # Use selected product from UI dropdown, fallback to auto-detection
        product = "auto"
        if request.analysis_context and request.analysis_context.target_product:
            product = request.analysis_context.target_product
            logger.info(f"OpenFrame RAG using selected product: {product}")

        rag_request = AgenticRAGRequest(
            message=request.message,
            language=request.language,
            product=product,
            user_id=user_id,
        )

        orchestrator = get_team_orchestrator()
        async for event in orchestrator.stream_chat_enhanced(rag_request):
            event["source_system"] = "openframe"
            yield event

    async def _stream_combined(
        self, request: ModernizationChatRequest, user_id: str = "anonymous"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream both HOST and OpenFrame in parallel, merge results."""
        host_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        of_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        async def collect_host():
            try:
                async for event in self._stream_host(request):
                    await host_queue.put(event)
            except Exception as e:
                logger.error(f"HOST stream error in ALL mode: {e}")
                await host_queue.put({"type": "error", "message": str(e), "source_system": "host"})
            finally:
                await host_queue.put(None)  # sentinel

        async def collect_openframe():
            try:
                async for event in self._stream_openframe(request, user_id):
                    await of_queue.put(event)
            except Exception as e:
                logger.error(f"OpenFrame stream error in ALL mode: {e}")
                await of_queue.put({"type": "error", "message": str(e), "source_system": "openframe"})
            finally:
                await of_queue.put(None)  # sentinel

        # Start both streams
        host_task = asyncio.create_task(collect_host())
        of_task = asyncio.create_task(collect_openframe())

        # Yield HOST section first
        yield {"type": "section_start", "source_system": "host", "label": "HOST Analysis"}
        while True:
            event = await host_queue.get()
            if event is None:
                break
            yield event
        yield {"type": "section_end", "source_system": "host"}

        # Then OpenFrame section
        yield {"type": "section_start", "source_system": "openframe", "label": "OpenFrame RAG"}
        while True:
            event = await of_queue.get()
            if event is None:
                break
            yield event
        yield {"type": "section_end", "source_system": "openframe"}

        yield {"type": "done"}

        # Ensure tasks complete
        await asyncio.gather(host_task, of_task, return_exceptions=True)


def get_chat_service() -> ModernizationChatService:
    """Get or create ModernizationChatService singleton."""
    if ModernizationChatService._instance is None:
        ModernizationChatService._instance = ModernizationChatService()
    return ModernizationChatService._instance
