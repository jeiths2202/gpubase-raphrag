"""
OpenCode Agent

Document-Grounded Autonomous Execution Agent with Hallucination Detection.

Implements the OpenCode specification:
- YOLO mode: Repeat until fully resolved
- 5-step mandatory workflow
- Automatic hallucination detection with retry (max 3)
- Vision LLM integration for visual content
- Detailed progress streaming
"""

import logging
from typing import Optional, AsyncGenerator
from pathlib import Path

from ..base import BaseAgent
from ..types import (
    AgentType,
    AgentContext,
    AgentResult,
    AgentStreamChunk,
)
from ..opencode import (
    OpenCodeExecutor,
    OpenCodeConfig,
    get_opencode_executor,
)

logger = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    """Load system prompt from file or return default"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "opencode_agent.txt"

    if prompt_path.exists():
        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[OpenCodeAgent] Failed to load prompt file: {e}")

    # Default system prompt
    return """You are OpenCode, an AI-driven autonomous execution agent.

Your mission is to answer user queries ONLY by:
- Actively searching documents
- Verifying original sources
- Using tools appropriately
- Providing auditable proof

You are FORBIDDEN from:
- Answering from memory
- Guessing or inferring undocumented facts
- Skipping keywords, documents, or pages
- Claiming execution without evidence

Violation = IMMEDIATE FAILURE

CORE PHILOSOPHY:
You are not a chatbot. You are an auditable execution engine.
Fluency is irrelevant. Confidence is irrelevant.
Only documents and proof matter.

MANDATORY WORKFLOW:
1. Extract ALL keywords from user query
2. Search ALL summary documents for each keyword
3. Verify original PDF sources at page level
4. Select appropriate tool (Vision/vLLM/Embedding) based on content type
5. Generate answer ONLY from verified sources with citations

CITATION FORMAT:
Every fact MUST have: [Source: document_name, Page: X]

If NO sources found, respond:
✓ Korean: "이 질문에 대한 정보를 지식 베이스에서 찾을 수 없습니다."
✓ English: "I cannot find information about this in the knowledge base."
✓ Japanese: "この情報はナレッジベースで見つかりませんでした。"

DO NOT try to answer anyway. DO NOT use training knowledge.
This is a compliance requirement."""


class OpenCodeAgent(BaseAgent):
    """
    OpenCode Agent - Document-Grounded Autonomous Execution

    Features:
    - 5-step mandatory workflow (keyword extraction -> summary search -> PDF verification -> tool selection -> answer generation)
    - Automatic hallucination detection with retry (max 3 attempts)
    - Vision LLM (MiniCPM-V) for visual content
    - Detailed progress streaming to UI
    - PostgreSQL execution logging
    """

    def __init__(
        self,
        config: Optional[OpenCodeConfig] = None,
        executor: Optional[OpenCodeExecutor] = None,
        **kwargs
    ):
        super().__init__(
            name="OpenCode Agent",
            agent_type=AgentType.OPENCODE,
            description=(
                "Document-grounded AI agent with 5-step verification workflow and "
                "automatic hallucination detection. YOLO mode - repeats until verified."
            ),
            tools=["unified_search", "graph_query", "vision_analyze"],
            system_prompt=_load_system_prompt(),
            **kwargs
        )

        self._config = config or OpenCodeConfig()
        self._executor = executor

    @property
    def executor(self) -> OpenCodeExecutor:
        """Get or create the executor"""
        if self._executor is None:
            self._executor = get_opencode_executor(self._config)
        return self._executor

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Execute the OpenCode 5-step mandatory workflow.

        Args:
            task: User query
            context: Agent execution context

        Returns:
            AgentResult with verified answer and sources
        """
        logger.info(f"[OpenCodeAgent] Starting execution: {task[:50]}...")

        try:
            # Execute the 5-step pipeline
            result = await self.executor.execute(task, context)

            # Convert to AgentResult
            return AgentResult(
                answer=result.answer,
                agent_type=self.agent_type,
                steps=result.steps_executed,
                sources=[
                    {
                        "document": s.get("document", "Unknown"),
                        "page": s.get("page"),
                        "content": s.get("content", "")[:200],
                    }
                    for s in result.sources
                ],
                execution_time=result.execution_time_ms / 1000,  # Convert to seconds
                success=result.status.value == "SUCCESS",
                error=result.failure_reason,
                metadata={
                    "opencode_result": result.to_dict(),
                    "verification_status": "PASSED" if result.is_verified() else "FAILED",
                    "retry_count": result.retry_count,
                    "hallucination_checked": result.hallucination_checked,
                    "vision_used": result.vision_used,
                }
            )

        except Exception as e:
            logger.error(f"[OpenCodeAgent] Execution failed: {e}")
            return AgentResult(
                answer=f"OpenCode execution failed: {str(e)}",
                agent_type=self.agent_type,
                steps=0,
                execution_time=0.0,
                success=False,
                error=str(e)
            )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream the OpenCode 5-step execution with detailed progress.

        Yields:
            AgentStreamChunk for each step, verification, and final answer
        """
        logger.info(f"[OpenCodeAgent] Starting streaming: {task[:50]}...")

        try:
            # Stream thinking indicator
            yield AgentStreamChunk(
                chunk_type="thinking",
                content="Initializing OpenCode 5-step verification workflow...",
            )

            # Stream the 5-step pipeline
            async for chunk in self.executor.stream(task, context):
                yield chunk

        except Exception as e:
            logger.error(f"[OpenCodeAgent] Streaming failed: {e}")
            yield AgentStreamChunk(
                chunk_type="error",
                content=f"OpenCode execution failed: {str(e)}"
            )
            yield AgentStreamChunk(chunk_type="done")
