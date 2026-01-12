"""
Deep Agent Adapter (Minimal Version)
Deep Agents를 기존 Agent 시스템에서 사용할 수 있도록 래핑하는 어댑터

PR #719 패치 버전 사용 (system_prompt KeyError 수정됨)
"""
import os
import time
import asyncio
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator

logger = logging.getLogger(__name__)

# Deep Agents 의존성 체크
try:
    from deepagents import create_deep_agent
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    DEEPAGENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Deep Agents not available: {e}")
    DEEPAGENTS_AVAILABLE = False

try:
    from langchain_ollama import ChatOllama
    LANGCHAIN_OLLAMA_AVAILABLE = True
except ImportError:
    LANGCHAIN_OLLAMA_AVAILABLE = False

from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk,
    MessageRole
)
from ..base import BaseAgent


class DeepAgentAdapter(BaseAgent):
    """
    Deep Agents를 기존 Agent 인터페이스로 래핑하는 최소 어댑터

    SubAgent 없이 기본 Deep Agent만 사용하여 안정성 확보
    """

    def __init__(
        self,
        name: str = "DeepAgent",
        agent_type: AgentType = AgentType.PLANNER,
        description: str = "Deep Agents 기반 에이전트",
        llm: Optional[Any] = None,
        tools: Optional[List] = None,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        super().__init__(
            name=name,
            agent_type=agent_type,
            description=description,
            system_prompt=system_prompt,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens
        )

        self._llm = llm
        self._custom_tools = tools or []
        self._deep_agent = None

        if not DEEPAGENTS_AVAILABLE:
            logger.warning(f"[{self.name}] Deep Agents not available")

    def _get_llm(self):
        """LLM 인스턴스 반환"""
        if self._llm is not None:
            return self._llm

        if not LANGCHAIN_OLLAMA_AVAILABLE:
            raise RuntimeError("langchain-ollama not installed")

        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

        return ChatOllama(
            base_url=ollama_base,
            model=ollama_model,
            temperature=self.temperature,
        )

    def _create_deep_agent(self):
        """Deep Agent 인스턴스 생성 (Lazy initialization)"""
        if self._deep_agent is not None:
            return self._deep_agent

        if not DEEPAGENTS_AVAILABLE:
            raise RuntimeError("Deep Agents not available")

        llm = self._get_llm()

        # 최소 설정으로 Deep Agent 생성 (SubAgent 없음)
        self._deep_agent = create_deep_agent(
            model=llm,
            tools=self._custom_tools if self._custom_tools else None,
            system_prompt=self.system_prompt,
        )

        return self._deep_agent

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """태스크 실행"""
        start_time = time.time()

        if not DEEPAGENTS_AVAILABLE:
            return AgentResult(
                answer="Deep Agents not available",
                agent_type=self.agent_type,
                steps=0,
                execution_time=time.time() - start_time,
                success=False,
                error="Deep Agents not installed"
            )

        try:
            agent = self._create_deep_agent()

            # 대화 히스토리 변환
            messages = []
            for hist in context.conversation_history[-5:]:
                if "question" in hist:
                    messages.append(HumanMessage(content=hist["question"]))
                if "answer" in hist:
                    messages.append(AIMessage(content=hist["answer"]))
            messages.append(HumanMessage(content=task))

            # Deep Agent 실행 (recursion_limit으로 무한 루프 방지)
            result = await asyncio.wait_for(
                agent.ainvoke(
                    {"messages": messages},
                    config={"recursion_limit": 25}  # 최대 25번 반복
                ),
                timeout=300.0  # 5분 타임아웃
            )

            # 결과 추출
            answer = ""
            if "messages" in result:
                for msg in reversed(result["messages"]):
                    if hasattr(msg, "content") and msg.content:
                        answer = msg.content
                        break

            return AgentResult(
                answer=answer or "No response",
                agent_type=self.agent_type,
                steps=len(result.get("messages", [])),
                execution_time=time.time() - start_time,
                success=True
            )

        except Exception as e:
            logger.error(f"[{self.name}] Execution error: {e}", exc_info=True)
            return AgentResult(
                answer=f"Error: {str(e)}",
                agent_type=self.agent_type,
                steps=0,
                execution_time=time.time() - start_time,
                success=False,
                error=str(e)
            )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """스트리밍 실행"""
        yield AgentStreamChunk(chunk_type="thinking", content="Processing...")

        try:
            result = await self.execute(task, context)

            # 결과를 청크로 스트리밍
            chunk_size = 50
            for i in range(0, len(result.answer), chunk_size):
                chunk = result.answer[i:i + chunk_size]
                yield AgentStreamChunk(chunk_type="text", content=chunk)

            yield AgentStreamChunk(
                chunk_type="done",
                metadata={"execution_time": result.execution_time}
            )

        except Exception as e:
            yield AgentStreamChunk(
                chunk_type="error",
                content=str(e)
            )


def create_deep_agent_adapter(
    name: str = "DeepAgent",
    agent_type: AgentType = AgentType.PLANNER,
    tools: Optional[List] = None,
    system_prompt: Optional[str] = None,
) -> DeepAgentAdapter:
    """Deep Agent 어댑터 팩토리 함수"""
    return DeepAgentAdapter(
        name=name,
        agent_type=agent_type,
        tools=tools,
        system_prompt=system_prompt,
    )


def create_rag_deep_agent(
    name: str = "RAGDeepAgent",
    system_prompt: Optional[str] = None,
    include_vector_search: bool = True,
    include_graph_query: bool = True,
    additional_tools: Optional[List] = None,
) -> DeepAgentAdapter:
    """RAG 도구가 포함된 Deep Agent 생성

    Args:
        name: 에이전트 이름
        system_prompt: 시스템 프롬프트
        include_vector_search: 벡터 검색 도구 포함 여부
        include_graph_query: 그래프 쿼리 도구 포함 여부
        additional_tools: 추가 도구 목록

    Returns:
        RAG 도구가 연동된 DeepAgentAdapter
    """
    from ..middleware import get_rag_tools

    tools = []

    # RAG 도구 추가
    rag_tools = get_rag_tools()
    for tool in rag_tools:
        if include_vector_search and tool.name == "vector_search":
            tools.append(tool)
        elif include_graph_query and tool.name == "graph_query":
            tools.append(tool)

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    # 기본 시스템 프롬프트
    default_prompt = """You are a RAG (Retrieval-Augmented Generation) assistant.
You have access to a knowledge base through vector_search and graph_query tools.

When answering questions:
1. Use vector_search to find relevant documents
2. Use graph_query to explore entity relationships
3. Synthesize information from multiple sources
4. Always cite your sources

Answer in the user's language."""

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.RAG,
        description="RAG Deep Agent with knowledge base access",
        tools=tools if tools else None,
        system_prompt=system_prompt or default_prompt,
    )


def create_ims_deep_agent(
    name: str = "IMSDeepAgent",
    system_prompt: Optional[str] = None,
    additional_tools: Optional[List] = None,
) -> DeepAgentAdapter:
    """IMS 도구가 포함된 Deep Agent 생성

    Args:
        name: 에이전트 이름
        system_prompt: 시스템 프롬프트
        additional_tools: 추가 도구 목록

    Returns:
        IMS 도구가 연동된 DeepAgentAdapter
    """
    from ..middleware import get_ims_tools, IMS_SYSTEM_PROMPT

    tools = get_ims_tools()

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.IMS,
        description="IMS Deep Agent with issue tracking access",
        tools=tools if tools else None,
        system_prompt=system_prompt or IMS_SYSTEM_PROMPT,
    )


def create_vision_deep_agent(
    name: str = "VisionDeepAgent",
    system_prompt: Optional[str] = None,
    additional_tools: Optional[List] = None,
) -> DeepAgentAdapter:
    """Vision 도구가 포함된 Deep Agent 생성

    Args:
        name: 에이전트 이름
        system_prompt: 시스템 프롬프트
        additional_tools: 추가 도구 목록

    Returns:
        Vision 도구가 연동된 DeepAgentAdapter
    """
    from ..middleware import get_vision_tools, VISION_SYSTEM_PROMPT

    tools = get_vision_tools()

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.VISION,
        description="Vision Deep Agent with image analysis capabilities",
        tools=tools if tools else None,
        system_prompt=system_prompt or VISION_SYSTEM_PROMPT,
    )


def create_code_deep_agent(
    name: str = "CodeDeepAgent",
    system_prompt: Optional[str] = None,
    additional_tools: Optional[List] = None,
) -> DeepAgentAdapter:
    """Code 도구가 포함된 Deep Agent 생성

    Args:
        name: 에이전트 이름
        system_prompt: 시스템 프롬프트
        additional_tools: 추가 도구 목록

    Returns:
        Code 도구가 연동된 DeepAgentAdapter
    """
    from ..middleware import get_code_tools, CODE_SYSTEM_PROMPT

    tools = get_code_tools()

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.CODE,
        description="Code Deep Agent with code generation and execution capabilities",
        tools=tools if tools else None,
        system_prompt=system_prompt or CODE_SYSTEM_PROMPT,
    )


def create_planner_deep_agent(
    name: str = "PlannerDeepAgent",
    system_prompt: Optional[str] = None,
    additional_tools: Optional[List] = None,
) -> DeepAgentAdapter:
    """Planner 도구가 포함된 Deep Agent 생성

    Args:
        name: 에이전트 이름
        system_prompt: 시스템 프롬프트
        additional_tools: 추가 도구 목록

    Returns:
        Planner 도구가 연동된 DeepAgentAdapter
    """
    from ..middleware import get_planner_tools, PLANNER_SYSTEM_PROMPT

    tools = get_planner_tools()

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.PLANNER,
        description="Planner Deep Agent with task decomposition capabilities",
        tools=tools if tools else None,
        system_prompt=system_prompt or PLANNER_SYSTEM_PROMPT,
    )
