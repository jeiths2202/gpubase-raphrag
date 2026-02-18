"""Modernization Chat Service - Routes chat to HOST/OpenFrame/ALL handlers.

Singleton pattern following project conventions.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from ..routers.chat_schemas import ModernizationChatRequest, SystemType

logger = logging.getLogger(__name__)


class ModernizationChatService:
    """Chat routing service for Legacy Modernization AI Assistant."""

    _instance: Optional["ModernizationChatService"] = None

    async def stream_chat(
        self, request: ModernizationChatRequest, user_id: str = "anonymous"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Route and stream chat based on system_type."""
        if request.system_type == SystemType.HOST:
            async for event in self._stream_host(request):
                yield event
        elif request.system_type == SystemType.OPENFRAME:
            async for event in self._stream_openframe(request, user_id):
                yield event
        else:  # ALL
            async for event in self._stream_combined(request, user_id):
                yield event

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

        rag_request = AgenticRAGRequest(
            message=request.message,
            language=request.language,
            product="auto",
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
