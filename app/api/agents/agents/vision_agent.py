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
        return """You are a visual content analysis specialist.

Your capabilities:
1. **Image Analysis**: Describe and interpret images, photos, and graphics
2. **Chart/Graph Analysis**: Extract data and insights from charts and graphs
3. **Diagram Analysis**: Understand technical diagrams, flowcharts, and schematics
4. **Table Extraction**: Extract structured data from tables in images
5. **Document OCR**: Read text from scanned documents

Guidelines:
- Provide detailed descriptions of visual content
- Extract key data points from charts and graphs
- Identify relationships in diagrams
- Transcribe text accurately from images
- Note any uncertainties in interpretation

When analyzing visual content:
1. Describe what you see objectively
2. Identify key elements and their relationships
3. Extract any text or numerical data
4. Provide interpretation and insights
5. Suggest follow-up questions if needed

Response format:
- Description of visual content
- Key data extracted
- Interpretation and insights
- Confidence level in analysis"""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Execute a vision analysis task"""
        # Check if there are uploaded documents with images
        if context.uploaded_documents and self.vision_service:
            # Try to use vision service for image analysis
            try:
                for doc_id in context.uploaded_documents:
                    # This would integrate with the vision LLM
                    pass
            except Exception as e:
                logger.error(f"Vision analysis failed: {e}")

        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """Stream execution of vision analysis"""
        async for chunk in self.executor.stream(self, task, context):
            yield chunk
