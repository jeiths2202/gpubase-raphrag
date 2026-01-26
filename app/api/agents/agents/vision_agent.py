"""
Vision Agent
Specialized agent for image and document analysis.
"""
from typing import List, Optional, AsyncGenerator
import logging

from ..base import BaseAgent
from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk
)
from ..executor import AgentExecutor, get_executor

logger = logging.getLogger(__name__)


class VisionAgent(BaseAgent):
    """
    Agent specialized for visual content analysis.
    Analyzes images, charts, diagrams, and visual documents.
    """

    def __init__(
        self,
        executor: Optional[AgentExecutor] = None,
        vision_service=None,
        **kwargs
    ):
        super().__init__(
            name="Vision Agent",
            agent_type=AgentType.VISION,
            description="Visual content analysis agent for images and documents",
            tools=["document_read", "vector_search"],
            **kwargs
        )
        self._executor = executor
        self._vision_service = vision_service

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    @property
    def vision_service(self):
        """Lazy load vision service"""
        if self._vision_service is None:
            try:
                from ...services.vision_service import get_vision_service
                self._vision_service = get_vision_service()
            except ImportError:
                logger.warning("Vision service not available")
        return self._vision_service

    def _get_default_prompt(self) -> str:
        """Fallback prompt if external file not found."""
        return """You are a visual content analysis specialist.
Analyze images, charts, diagrams, and tables. Extract data and provide insights.
Note uncertainties in interpretation."""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute a vision analysis task"""
        # TODO: Integrate vision_service for direct image analysis when available
        # Currently relies on executor's tool-based approach (document_read, vector_search)
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of vision analysis"""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk
