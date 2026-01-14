"""
Deep Agent Adapter (With Long-term Memory)
Deep Agents를 기존 Agent 시스템에서 사용할 수 있도록 래핑하는 어댑터

Features:
- CompositeBackend를 통한 Long-term Memory 지원
- /memories/ 경로의 데이터는 세션 간 영구 저장
- 사용자 선호도, 지식 기반, 연구 진행 상황 유지

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

# Deep Agents backends for long-term memory
try:
    from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
    DEEPAGENTS_BACKENDS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_BACKENDS_AVAILABLE = False
    logger.info("Deep Agents backends not available, long-term memory disabled")

# LangGraph store for persistent memory
try:
    from langgraph.store.memory import InMemoryStore
    LANGGRAPH_STORE_AVAILABLE = True
except ImportError:
    LANGGRAPH_STORE_AVAILABLE = False

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
    Deep Agents를 기존 Agent 인터페이스로 래핑하는 어댑터

    Features:
    - SubAgent 없이 기본 Deep Agent만 사용하여 안정성 확보
    - CompositeBackend를 통한 Long-term Memory 지원
    - /memories/ 경로의 데이터는 세션 간 영구 저장
    """

    # Long-term memory paths (persist across sessions)
    PERSISTENT_MEMORY_PATHS = [
        "/memories/",           # General long-term memory
        "/preferences/",        # User preferences
        "/knowledge/",          # Accumulated knowledge
        "/instructions/",       # Self-improving instructions
        "/research/",           # Research progress
    ]

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
        enable_long_term_memory: bool = True,
        memory_store: Optional[Any] = None,
        user_id: Optional[str] = None,
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
        self._enable_long_term_memory = enable_long_term_memory
        self._memory_store = memory_store
        self._user_id = user_id
        self._composite_backend = None

        if not DEEPAGENTS_AVAILABLE:
            logger.warning(f"[{self.name}] Deep Agents not available")

        if enable_long_term_memory and not DEEPAGENTS_BACKENDS_AVAILABLE:
            logger.info(f"[{self.name}] Long-term memory backends not available, using ephemeral storage")

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

    def _get_langraph_store(self):
        """
        LangGraph Store 반환 (Long-term Memory 지원)

        create_deep_agent에 store 파라미터로 전달됩니다.
        """
        if not self._enable_long_term_memory:
            return None

        try:
            # Get persistent store (from memory_store_service or InMemoryStore)
            if self._memory_store is not None:
                return self._memory_store
            elif LANGGRAPH_STORE_AVAILABLE:
                return InMemoryStore()
            else:
                logger.warning("No persistent store available")
                return None
        except Exception as e:
            logger.warning(f"[{self.name}] Failed to get LangGraph store: {e}")
            return None

    def _get_composite_backend_factory(self):
        """
        CompositeBackend 팩토리 함수 반환 (Long-term Memory 지원)

        deepagents의 backend 파라미터는 ToolRuntime을 받는 callable을 기대합니다.
        /memories/, /preferences/, /knowledge/, /instructions/, /research/ 경로는
        StoreBackend를 통해 영구 저장됨. 나머지 경로는 StateBackend로 임시 저장.

        Returns:
            Callable that takes ToolRuntime and returns CompositeBackend, or None
        """
        if not DEEPAGENTS_BACKENDS_AVAILABLE or not self._enable_long_term_memory:
            return None

        # Create a factory function that will be called with ToolRuntime
        def backend_factory(runtime):
            try:
                # Build routes for persistent paths
                routes = {}
                for path in self.PERSISTENT_MEMORY_PATHS:
                    routes[path] = StoreBackend(runtime)

                composite = CompositeBackend(
                    default=StateBackend(runtime),  # Ephemeral for working files
                    routes=routes                    # Persistent for memory paths
                )

                logger.info(f"[{self.name}] Long-term memory CompositeBackend created")
                return composite

            except Exception as e:
                logger.warning(f"[{self.name}] Failed to create CompositeBackend: {e}")
                # Fallback to StateBackend
                return StateBackend(runtime)

        return backend_factory

    def _create_deep_agent(self):
        """Deep Agent 인스턴스 생성 (Lazy initialization with Long-term Memory)"""
        if self._deep_agent is not None:
            return self._deep_agent

        if not DEEPAGENTS_AVAILABLE:
            raise RuntimeError("Deep Agents not available")

        llm = self._get_llm()

        # Create Deep Agent with optional long-term memory
        agent_kwargs = {
            "model": llm,
            "tools": self._custom_tools if self._custom_tools else None,
            "system_prompt": self.system_prompt,
        }

        # Add LangGraph store for persistence
        store = self._get_langraph_store()
        if store is not None:
            agent_kwargs["store"] = store
            logger.info(f"[{self.name}] LangGraph store configured for persistence")

        # Add CompositeBackend factory for file system routing
        backend_factory = self._get_composite_backend_factory()
        if backend_factory is not None:
            agent_kwargs["backend"] = backend_factory
            logger.info(f"[{self.name}] Creating Deep Agent with Long-term Memory backend")
        else:
            logger.info(f"[{self.name}] Creating Deep Agent without Long-term Memory (ephemeral only)")

        self._deep_agent = create_deep_agent(**agent_kwargs)

        return self._deep_agent

    def set_user_id(self, user_id: str):
        """
        Set user ID for user-specific memory.

        Should be called before creating the deep agent to enable
        user-specific memory isolation.
        """
        self._user_id = user_id
        # Reset agent to recreate with new user context
        if self._deep_agent is not None:
            self._deep_agent = None
            self._composite_backend = None

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

        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Request timed out after 300s")
            return AgentResult(
                answer="요청 시간이 초과되었습니다. LLM 서버가 응답하지 않습니다. 잠시 후 다시 시도해주세요.",
                agent_type=self.agent_type,
                steps=0,
                execution_time=time.time() - start_time,
                success=False,
                error="Timeout: LLM server not responding"
            )
        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Request was cancelled")
            return AgentResult(
                answer="요청이 취소되었습니다.",
                agent_type=self.agent_type,
                steps=0,
                execution_time=time.time() - start_time,
                success=False,
                error="Request cancelled"
            )
        except ConnectionError as e:
            logger.error(f"[{self.name}] Connection error: {e}")
            return AgentResult(
                answer="LLM 서버에 연결할 수 없습니다. Ollama 서비스가 실행 중인지 확인해주세요.",
                agent_type=self.agent_type,
                steps=0,
                execution_time=time.time() - start_time,
                success=False,
                error=f"Connection error: {str(e)}"
            )
        except Exception as e:
            error_msg = str(e)
            # 연결 관련 오류인지 확인
            if "connection" in error_msg.lower() or "connect" in error_msg.lower():
                user_message = "LLM 서버에 연결할 수 없습니다. Ollama 서비스가 실행 중인지 확인해주세요."
            elif "timeout" in error_msg.lower():
                user_message = "요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요."
            else:
                user_message = f"처리 중 오류가 발생했습니다: {error_msg}"

            logger.error(f"[{self.name}] Execution error: {e}", exc_info=True)
            return AgentResult(
                answer=user_message,
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

        except asyncio.CancelledError:
            yield AgentStreamChunk(
                chunk_type="error",
                content="요청이 취소되었습니다."
            )
        except Exception as e:
            error_msg = str(e)
            if "connection" in error_msg.lower() or "connect" in error_msg.lower():
                user_message = "LLM 서버에 연결할 수 없습니다."
            elif "timeout" in error_msg.lower():
                user_message = "요청 시간이 초과되었습니다."
            else:
                user_message = f"오류 발생: {error_msg}"
            yield AgentStreamChunk(
                chunk_type="error",
                content=user_message
            )


def create_deep_agent_adapter(
    name: str = "DeepAgent",
    agent_type: AgentType = AgentType.PLANNER,
    tools: Optional[List] = None,
    system_prompt: Optional[str] = None,
    enable_long_term_memory: bool = True,
    memory_store: Optional[Any] = None,
    user_id: Optional[str] = None,
) -> DeepAgentAdapter:
    """
    Deep Agent 어댑터 팩토리 함수

    Args:
        name: 에이전트 이름
        agent_type: 에이전트 타입
        tools: 사용할 도구 목록
        system_prompt: 시스템 프롬프트
        enable_long_term_memory: Long-term Memory 활성화 여부
        memory_store: 영구 저장소 (None이면 InMemoryStore 사용)
        user_id: 사용자 ID (사용자별 메모리 분리)

    Returns:
        DeepAgentAdapter 인스턴스
    """
    return DeepAgentAdapter(
        name=name,
        agent_type=agent_type,
        tools=tools,
        system_prompt=system_prompt,
        enable_long_term_memory=enable_long_term_memory,
        memory_store=memory_store,
        user_id=user_id,
    )


def create_rag_deep_agent(
    name: str = "RAGDeepAgent",
    system_prompt: Optional[str] = None,
    include_vector_search: bool = True,
    include_graph_query: bool = True,
    include_image_search: bool = True,
    additional_tools: Optional[List] = None,
    multimodal_service=None,
    enable_long_term_memory: bool = True,
    memory_store: Optional[Any] = None,
    user_id: Optional[str] = None,
) -> DeepAgentAdapter:
    """RAG 도구가 포함된 Deep Agent 생성

    Args:
        name: 에이전트 이름
        system_prompt: 시스템 프롬프트
        include_vector_search: 벡터 검색 도구 포함 여부
        include_graph_query: 그래프 쿼리 도구 포함 여부
        include_image_search: 이미지 검색 도구 포함 여부
        additional_tools: 추가 도구 목록
        multimodal_service: MultimodalRAGService 인스턴스
        enable_long_term_memory: Long-term Memory 활성화 여부
        memory_store: 영구 저장소 (None이면 InMemoryStore 사용)
        user_id: 사용자 ID (사용자별 메모리 분리)

    Returns:
        RAG 도구가 연동된 DeepAgentAdapter
    """
    from ..middleware import get_rag_tools

    tools = []

    # Get multimodal service for image search
    if multimodal_service is None and include_image_search:
        try:
            from ...core.deps import get_multimodal_rag_service
            import asyncio
            # Try to get the service synchronously
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't await in sync context, will lazy load later
                pass
            else:
                multimodal_service = loop.run_until_complete(get_multimodal_rag_service())
        except Exception:
            pass  # Will use lazy loading in the tool

    # RAG 도구 추가
    rag_tools = get_rag_tools(multimodal_service=multimodal_service)
    for tool in rag_tools:
        if include_vector_search and tool.name == "vector_search":
            tools.append(tool)
        elif include_graph_query and tool.name == "graph_query":
            tools.append(tool)
        elif include_image_search and tool.name == "image_search":
            tools.append(tool)

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    # 기본 시스템 프롬프트 (Long-term Memory 기능 설명 추가)
    default_prompt = """You are a RAG (Retrieval-Augmented Generation) assistant with long-term memory capabilities.
You have access to a knowledge base through vector_search, graph_query, and image_search tools.

## Long-term Memory
You can store and retrieve information across conversations using file paths:
- /memories/: General long-term memory
- /preferences/: User preferences that persist
- /knowledge/: Accumulated knowledge from conversations
- /instructions/: Self-improving instructions based on feedback
- /research/: Research progress across sessions

When answering questions:
1. Use vector_search to find relevant documents
2. Use graph_query to explore entity relationships
3. Use image_search to find relevant images, diagrams, or charts
4. Synthesize information from multiple sources
5. Always cite your sources
6. Store important insights in /knowledge/ for future reference
7. Remember user preferences in /preferences/

If the user asks about diagrams, flowcharts, or images, use the image_search tool.
Answer in the user's language."""

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.RAG,
        description="RAG Deep Agent with knowledge base, image search, and long-term memory",
        tools=tools if tools else None,
        system_prompt=system_prompt or default_prompt,
        enable_long_term_memory=enable_long_term_memory,
        memory_store=memory_store,
        user_id=user_id,
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
