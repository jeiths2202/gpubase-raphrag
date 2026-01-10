"""
Agent Orchestrator
Manages agent selection and execution flow.
"""
from typing import Dict, List, Optional, AsyncGenerator
import logging
import re

from .types import (
    AgentType, AgentContext, AgentResult, AgentRequest, AgentResponse,
    AgentStreamChunk
)
from .base import BaseAgent
from .registry import AgentRegistry, get_agent_registry
from .executor import AgentExecutor, get_executor
from .intent import IntentClassifier, get_intent_classifier, IntentResult

logger = logging.getLogger(__name__)


# Keywords for agent type classification
AGENT_KEYWORDS = {
    AgentType.RAG: [
        "what", "how", "why", "explain", "describe", "tell me",
        "knowledge", "information", "document", "article",
        "뭐", "무엇", "어떻게", "왜", "설명", "알려",
        "何", "どう", "なぜ", "説明",
    ],
    AgentType.IMS: [
        "issue", "bug", "error", "problem", "ticket",
        "ims", "jira", "defect", "fix", "resolved",
        "이슈", "버그", "오류", "문제", "티켓",
        "バグ", "エラー", "問題", "チケット",
    ],
    AgentType.VISION: [
        "image", "picture", "photo", "chart", "graph",
        "diagram", "figure", "screenshot", "visual",
        "이미지", "사진", "차트", "그래프", "다이어그램",
        "画像", "写真", "チャート", "グラフ",
    ],
    AgentType.CODE: [
        "code", "program", "function", "class", "implement",
        "debug", "compile", "script", "algorithm",
        "코드", "프로그램", "함수", "클래스", "구현",
        "コード", "プログラム", "関数", "クラス",
    ],
    AgentType.PLANNER: [
        "plan", "strategy", "approach", "steps", "roadmap",
        "breakdown", "decompose", "organize", "schedule",
        "계획", "전략", "접근", "단계", "로드맵",
        "計画", "戦略", "アプローチ", "ステップ",
    ],
}


class AgentOrchestrator:
    """
    Orchestrates agent selection and execution.
    Singleton pattern with lazy initialization.
    """

    _instance: Optional['AgentOrchestrator'] = None

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        executor: Optional[AgentExecutor] = None,
        intent_classifier: Optional[IntentClassifier] = None
    ):
        self.agent_registry = agent_registry or get_agent_registry()
        self.executor = executor or get_executor()
        self.intent_classifier = intent_classifier or get_intent_classifier()

    @classmethod
    def get_instance(cls) -> 'AgentOrchestrator':
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def execute(
        self,
        request: AgentRequest,
        user_id: Optional[str] = None
    ) -> AgentResponse:
        """
        Execute an agent request.

        Args:
            request: The agent request
            user_id: Optional user ID for context

        Returns:
            AgentResponse with answer and metadata
        """
        # Create context
        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps
        )

        # Select agent
        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Classify intent and attach to context
        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result
        logger.info(f"[Orchestrator] Intent: {intent_result.intent.value} "
                   f"(confidence={intent_result.confidence:.2f}, method={intent_result.method})")

        # Get agent
        agent = self.agent_registry.get(agent_type)

        # Execute
        result = await agent.execute(request.task, context)

        # Build response
        return AgentResponse(
            answer=result.answer,
            agent_type=result.agent_type,
            session_id=context.session_id,
            steps=result.steps,
            sources=result.sources if request.include_sources else [],
            execution_time=result.execution_time,
            success=result.success,
            error=result.error
        )

    async def stream(
        self,
        request: AgentRequest,
        user_id: Optional[str] = None
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Stream agent execution.

        Args:
            request: The agent request
            user_id: Optional user ID for context

        Yields:
            AgentStreamChunk with incremental results
        """
        logger.info(f"[Orchestrator] stream called: task={request.task[:50]}...")

        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps
        )

        if request.agent_type:
            agent_type = request.agent_type
        else:
            agent_type = await self.classify_task(request.task)

        # Classify intent and attach to context
        intent_result = await self.intent_classifier.classify(
            request.task,
            agent_type=agent_type.value
        )
        context.intent = intent_result
        print(f"[Orchestrator] Intent: {intent_result.intent.value} "
              f"(confidence={intent_result.confidence:.2f}, method={intent_result.method}, "
              f"params={intent_result.extracted_params})", flush=True)

        print(f"[Orchestrator] agent_type={agent_type.value}", flush=True)

        agent = self.agent_registry.get(agent_type)
        print(f"[Orchestrator] agent={agent.name}", flush=True)

        try:
            async for chunk in agent.stream(request.task, context):
                logger.debug(f"[Orchestrator] chunk={chunk.chunk_type}")
                yield chunk
        except Exception as e:
            logger.error(f"[Orchestrator] ERROR: {e}")
            raise

    async def classify_task(self, task: str) -> AgentType:
        """
        Classify a task to determine the appropriate agent type.

        Uses keyword matching and optionally LLM classification.
        """
        task_lower = task.lower()

        # Score each agent type based on keyword matches
        scores: Dict[AgentType, int] = {at: 0 for at in AgentType}

        for agent_type, keywords in AGENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in task_lower:
                    scores[agent_type] += 1
                    logger.debug(f"[Classify] matched '{keyword}' -> {agent_type.value}")

        logger.debug(f"[Classify] scores={scores}")

        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # If no strong match, default to RAG
        if best_score == 0:
            logger.info("[Classify] no match, defaulting to RAG")
            return AgentType.RAG

        # If multiple high scores, prefer RAG as it's most general
        high_scores = [at for at, score in scores.items() if score == best_score]
        if len(high_scores) > 1 and AgentType.RAG in high_scores:
            logger.info(f"[Classify] multiple high scores {high_scores}, preferring RAG")
            return AgentType.RAG

        logger.info(f"[Classify] result={best_type.value}")
        return best_type

    async def classify_with_llm(self, task: str) -> AgentType:
        """
        Use LLM to classify the task (more accurate but slower).
        """
        try:
            if self.executor.llm_adapter is None:
                return await self.classify_task(task)

            prompt = f"""Classify this task into one of these categories:
- rag: General knowledge queries, questions about documents or information
- ims: Issue tracking, bug reports, technical problems
- vision: Image or visual content analysis
- code: Code generation, review, or debugging
- planner: Complex task planning or decomposition

Task: {task}

Respond with only the category name (rag, ims, vision, code, or planner):"""

            response = await self.executor.llm_adapter.generate([
                {"role": "user", "content": prompt}
            ])

            classification = response.get("content", "").strip().lower()

            type_map = {
                "rag": AgentType.RAG,
                "ims": AgentType.IMS,
                "vision": AgentType.VISION,
                "code": AgentType.CODE,
                "planner": AgentType.PLANNER,
            }

            return type_map.get(classification, AgentType.RAG)

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return await self.classify_task(task)

    def get_available_agents(self) -> List[Dict]:
        """Get information about available agents"""
        agents = []
        for agent_type in self.agent_registry.get_all_types():
            agent = self.agent_registry.get(agent_type)
            agents.append({
                "type": agent_type.value,
                "name": agent.name,
                "description": agent.description,
                "tools": agent.tools
            })
        return agents


# Convenience function
def get_orchestrator() -> AgentOrchestrator:
    """Get the global orchestrator instance"""
    return AgentOrchestrator.get_instance()
