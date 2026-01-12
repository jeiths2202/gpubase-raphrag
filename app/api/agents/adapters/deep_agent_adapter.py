"""
Deep Agent Adapter
Deep Agents를 기존 WebUI Agent 인터페이스로 래핑하는 어댑터

이 어댑터를 통해 Deep Agents를 AgentOrchestrator에서
다른 Agent와 동일하게 사용할 수 있습니다.
"""
import os
import time
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator

logger = logging.getLogger(__name__)

# Deep Agents 의존성 체크
try:
    from deepagents import create_deep_agent
    from deepagents.middleware import (
        FilesystemMiddleware,
        SubAgentMiddleware,
        SubAgent,
    )
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    DEEPAGENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Deep Agents not available: {e}")
    DEEPAGENTS_AVAILABLE = False

try:
    from langchain_openai import ChatOpenAI
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

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
    Deep Agents를 WebUI Agent 인터페이스로 래핑하는 어댑터

    기존 AgentOrchestrator에서 다른 Agent와 동일하게 사용 가능합니다.
    Deep Agents의 미들웨어 스택, SubAgent, 자동 컨텍스트 관리 기능을 활용합니다.

    사용 예시:
    ```python
    from app.api.agents.adapters.deep_agent_adapter import DeepAgentAdapter
    from app.api.agents.middleware import RAGMiddleware, CodeMiddleware

    # Deep Agent 생성
    deep_agent = DeepAgentAdapter(
        name="ProjectAgent",
        agent_type=AgentType.PLANNER,
        middleware=[
            RAGMiddleware(),
            CodeMiddleware(),
        ]
    )

    # 기존 Agent처럼 사용
    result = await deep_agent.execute("프로젝트 계획 수립", context)
    ```
    """

    def __init__(
        self,
        name: str = "DeepAgent",
        agent_type: AgentType = AgentType.PLANNER,
        description: str = "Deep Agents 기반 복잡한 작업 처리 에이전트",
        llm: Optional[Any] = None,
        tools: Optional[List] = None,
        subagents: Optional[List] = None,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        nim_base_url: Optional[str] = None,
        nim_model: Optional[str] = None,
        enable_filesystem: bool = False,
    ):
        """
        Deep Agent Adapter 초기화

        Args:
            name: 에이전트 이름
            agent_type: 에이전트 타입 (기본: PLANNER)
            description: 에이전트 설명
            llm: LangChain ChatModel 인스턴스 (None이면 NIM 사용)
            tools: 추가 도구 목록 (langchain tools)
            subagents: SubAgent 목록
            system_prompt: 시스템 프롬프트
            model_id: 모델 ID
            temperature: 생성 온도
            max_tokens: 최대 토큰 수
            nim_base_url: NVIDIA NIM 서버 URL
            nim_model: NIM 모델 이름
            enable_filesystem: Filesystem 미들웨어 활성화
        """
        super().__init__(
            name=name,
            agent_type=agent_type,
            description=description,
            system_prompt=system_prompt,
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens
        )

        # LLM 설정
        self._llm = llm
        self.nim_base_url = nim_base_url or os.getenv("NIM_BASE_URL", "http://localhost:12800/v1")
        self.nim_model = nim_model or os.getenv("NIM_MODEL", "nvidia/llama-3.1-nemotron-nano-8b-v1")

        # 도구 및 SubAgent 설정
        self._custom_tools = tools or []
        self._subagents = subagents
        self.enable_filesystem = enable_filesystem

        # Deep Agent 인스턴스 (Lazy initialization)
        self._deep_agent = None

        # 상태 확인
        if not DEEPAGENTS_AVAILABLE:
            logger.warning(f"[{self.name}] Deep Agents not available. Install with: pip install deepagents")
        if not LANGCHAIN_AVAILABLE:
            logger.warning(f"[{self.name}] langchain-openai not available. Install with: pip install langchain-openai")

    def _get_llm(self):
        """LLM 인스턴스 반환 (Lazy initialization)

        Ollama qwen2.5:3b 모델 사용 (로컬 실행)
        langchain-ollama 사용 시 native tool calling 지원
        """
        if self._llm is not None:
            return self._llm

        ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

        # langchain-ollama 사용 (tool calling 지원이 더 좋음)
        if LANGCHAIN_OLLAMA_AVAILABLE:
            self._llm = ChatOllama(
                model=ollama_model,
                base_url=ollama_base,
                temperature=self.temperature,
                num_predict=self.max_tokens,
            )
            logger.info(f"[{self.name}] LLM initialized (ChatOllama): {ollama_model} @ {ollama_base}")
            print(f"[{self.name}] Using ChatOllama for native tool calling support", flush=True)
            return self._llm

        # Fallback: langchain-openai 사용
        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError("langchain-openai or langchain-ollama is required. Run: pip install langchain-ollama")

        ollama_base_url = f"{ollama_base.rstrip('/')}/v1"
        self._llm = ChatOpenAI(
            model=ollama_model,
            base_url=ollama_base_url,
            api_key="ollama",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        logger.info(f"[{self.name}] LLM initialized (ChatOpenAI): {ollama_model} @ {ollama_base_url}")
        print(f"[{self.name}] Using ChatOpenAI (tool calling may not work properly)", flush=True)
        return self._llm

    def _build_subagents(self) -> Optional[List]:
        """SubAgent 목록 구성"""
        if self._subagents is not None:
            return self._subagents

        if not DEEPAGENTS_AVAILABLE:
            return None

        # 기본 SubAgents 구성
        return [
            SubAgent(
                name="researcher",
                description="Research specialist for gathering and analyzing information",
                prompt="You are a research expert. Gather and analyze information thoroughly."
            ),
            SubAgent(
                name="coder",
                description="Software developer for writing and analyzing code",
                prompt="You are a software developer. Write clean and efficient code."
            ),
            SubAgent(
                name="reviewer",
                description="Code review specialist for quality assurance",
                prompt="You are a senior code reviewer. Review code for quality, security, and performance."
            ),
        ]

    def _get_deep_agent(self):
        """Deep Agent 인스턴스 반환 (Lazy initialization)

        LangGraph의 create_react_agent를 직접 사용하여
        deepagents의 SubAgentMiddleware 문제를 회피합니다.
        """
        if self._deep_agent is not None:
            return self._deep_agent

        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError("langchain-openai is not installed. Run: pip install langchain-openai")

        try:
            from langgraph.prebuilt import create_react_agent
        except ImportError:
            raise RuntimeError("langgraph is not installed. Run: pip install langgraph")

        llm = self._get_llm()

        # LangGraph의 create_react_agent 사용 (deepagents 대신)
        # 이렇게 하면 SubAgentMiddleware 문제를 회피할 수 있음
        tools = self._custom_tools if self._custom_tools else []

        logger.debug(f"[{self.name}] Creating agent with {len(tools)} tools")
        logger.debug(f"[{self.name}] System prompt length: {len(self.system_prompt)} chars")

        self._deep_agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=self.system_prompt,
        )
        logger.info(f"[{self.name}] LangGraph React Agent created")

        return self._deep_agent

    def _build_language_instruction(self, language: str) -> str:
        """언어 설정에 따른 응답 언어 지시사항 생성

        Args:
            language: 언어 코드 (en, ko, ja, auto)

        Returns:
            언어 지시사항 문자열
        """
        if not language or language == "auto":
            return ""

        language_names = {"en": "English", "ko": "Korean", "ja": "Japanese"}
        lang_name = language_names.get(language, language)

        return f"""[LANGUAGE REQUIREMENT]
- You MUST respond in {lang_name} by default
- This is the user's configured language preference
- ONLY switch to a different language if the user EXPLICITLY requests it in their message (e.g., "Answer in English", "日本語で答えて", "영어로 대답해줘")
- If the user's message is in a different language but they don't explicitly request a response in that language, still respond in {lang_name}

"""

    def _build_context_message(self, task: str, context: AgentContext) -> str:
        """컨텍스트 정보를 포함한 메시지 생성"""
        parts = []

        # 언어 지시사항 (최우선)
        language_instruction = self._build_language_instruction(context.language)
        if language_instruction:
            parts.append(language_instruction)

        # 첨부 파일 컨텍스트
        if context.file_context:
            parts.append(f"[첨부 파일 컨텍스트]\n{context.file_context}\n")

        # URL 컨텍스트
        if context.url_context:
            source = context.url_source or "제공된 URL"
            parts.append(f"[URL 컨텍스트: {source}]\n{context.url_context}\n")

        # 대화 히스토리
        if context.conversation_history:
            parts.append("[이전 대화]\n")
            for hist in context.conversation_history[-3:]:  # 최근 3개만
                if "question" in hist:
                    parts.append(f"사용자: {hist['question']}\n")
                if "answer" in hist:
                    parts.append(f"어시스턴트: {hist['answer'][:500]}...\n")

        # 사용자 작업
        parts.append(f"[현재 작업]\n{task}")

        return "\n".join(parts)

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        Deep Agent로 작업 실행

        Args:
            task: 사용자 작업/질문
            context: 실행 컨텍스트

        Returns:
            AgentResult with answer and metadata
        """
        start_time = time.time()

        # Deep Agents 사용 불가 시 폴백
        if not DEEPAGENTS_AVAILABLE:
            return AgentResult(
                answer="Deep Agents가 설치되지 않았습니다. `pip install deepagents langchain-openai`를 실행하세요.",
                agent_type=self.agent_type,
                steps=0,
                execution_time=time.time() - start_time,
                success=False,
                error="DeepAgents not installed"
            )

        try:
            agent = self._get_deep_agent()

            # 컨텍스트 포함 메시지 생성
            message_content = self._build_context_message(task, context)

            logger.info(f"[{self.name}] Executing task: {task[:100]}...")
            print(f"[{self.name}] Tools available: {len(self._custom_tools)}", flush=True)
            for t in self._custom_tools:
                print(f"[{self.name}]   - {t.name}: {t.description[:50]}...", flush=True)

            # Deep Agent 실행
            result = await agent.ainvoke({
                "messages": [HumanMessage(content=message_content)]
            })

            # 결과 디버깅 (인코딩 오류 방지)
            try:
                print(f"[{self.name}] Result type: {type(result)}", flush=True)
                if isinstance(result, dict):
                    print(f"[{self.name}] Result keys: {result.keys()}", flush=True)
                    if "messages" in result:
                        print(f"[{self.name}] Messages count: {len(result['messages'])}", flush=True)
                        for i, msg in enumerate(result["messages"]):
                            msg_type = type(msg).__name__
                            # ASCII 안전 출력
                            content_preview = str(msg.content)[:100] if hasattr(msg, 'content') else str(msg)[:100]
                            safe_preview = content_preview.encode('ascii', 'replace').decode('ascii')
                            print(f"[{self.name}] Message[{i}] ({msg_type}): {safe_preview}...", flush=True)
                            # Tool call 확인
                            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                                print(f"[{self.name}]   Tool calls: {msg.tool_calls}", flush=True)
            except Exception as e:
                print(f"[{self.name}] Debug output error: {e}", flush=True)

            # 결과 추출
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_msg = messages[-1]
                    answer = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
                else:
                    answer = str(result)
            else:
                answer = str(result)

            execution_time = time.time() - start_time

            logger.info(f"[{self.name}] Task completed in {execution_time:.2f}s")

            return AgentResult(
                answer=answer,
                agent_type=self.agent_type,
                steps=1,
                execution_time=execution_time,
                success=True,
                metadata={
                    "engine": "deep_agents",
                    "model": self.nim_model,
                    "middleware_count": 0
                }
            )

        except Exception as e:
            import traceback
            execution_time = time.time() - start_time
            logger.error(f"[{self.name}] Execution failed: {e}")
            logger.error(f"[{self.name}] Traceback:\n{traceback.format_exc()}")

            return AgentResult(
                answer=f"작업 처리 중 오류가 발생했습니다: {str(e)}",
                agent_type=self.agent_type,
                steps=0,
                execution_time=execution_time,
                success=False,
                error=str(e)
            )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        Deep Agent 스트리밍 실행

        현재 Deep Agents는 네이티브 스트리밍을 완전히 지원하지 않아
        전체 실행 후 청크로 분할하여 스트리밍합니다.

        Args:
            task: 사용자 작업/질문
            context: 실행 컨텍스트

        Yields:
            AgentStreamChunk with incremental results
        """
        import asyncio

        # 시작 청크
        yield AgentStreamChunk(
            chunk_type="thinking",
            content=f"Deep Agent ({self.name}) 처리 중..."
        )

        try:
            # 전체 실행
            result = await self.execute(task, context)

            if not result.success:
                yield AgentStreamChunk(
                    chunk_type="error",
                    content=result.error or "알 수 없는 오류"
                )
                return

            # 답변 스트리밍
            answer = result.answer
            chunk_size = 50

            for i in range(0, len(answer), chunk_size):
                chunk = answer[i:i + chunk_size]
                yield AgentStreamChunk(
                    chunk_type="text",
                    content=chunk
                )
                await asyncio.sleep(0.02)  # 스트리밍 효과

            # 완료 청크
            yield AgentStreamChunk(
                chunk_type="done",
                metadata={
                    "execution_time": result.execution_time,
                    "engine": "deep_agents",
                    "steps": result.steps
                }
            )

        except Exception as e:
            logger.error(f"[{self.name}] Stream failed: {e}")
            yield AgentStreamChunk(
                chunk_type="error",
                content=str(e)
            )

    def reset(self):
        """Deep Agent 인스턴스 리셋"""
        self._deep_agent = None
        self._llm = None
        logger.info(f"[{self.name}] Agent reset")


# Factory 함수들
def create_rag_deep_agent(
    neo4j_password: Optional[str] = None,
    **kwargs
) -> DeepAgentAdapter:
    """
    RAG 전문 Deep Agent 생성

    Args:
        neo4j_password: Neo4j 비밀번호
        **kwargs: DeepAgentAdapter 추가 인자

    Returns:
        RAG 도구가 설정된 DeepAgentAdapter
    """
    from ..middleware import get_rag_tools, RAG_SYSTEM_PROMPT

    rag_tools = get_rag_tools(neo4j_password=neo4j_password)

    return DeepAgentAdapter(
        name="RAGDeepAgent",
        agent_type=AgentType.RAG,
        description="Deep Agents 기반 RAG 에이전트",
        tools=rag_tools,
        subagents=None,  # RAG agent doesn't need subagents
        system_prompt=RAG_SYSTEM_PROMPT + """

You are a knowledge base search specialist for HybridRAG KMS.

Key responsibilities:
1. Search the knowledge base to answer user questions
2. Provide accurate answers based on search results
3. Always cite sources for reliability

IMPORTANT: Do not answer from general knowledge.
Always use vector_search tool first.""",
        **kwargs
    )


def create_code_deep_agent(**kwargs) -> DeepAgentAdapter:
    """
    코드 전문 Deep Agent 생성

    Args:
        **kwargs: DeepAgentAdapter 추가 인자

    Returns:
        코드 도구가 설정된 DeepAgentAdapter
    """
    from ..middleware import get_code_tools, CODE_SYSTEM_PROMPT

    code_tools = get_code_tools(
        allowed_languages=["python", "javascript", "typescript"],
        enable_execution=True
    )

    return DeepAgentAdapter(
        name="CodeDeepAgent",
        agent_type=AgentType.CODE,
        description="Deep Agents 기반 코드 생성/분석 에이전트",
        tools=code_tools,
        subagents=None,  # Will use default subagents
        nim_base_url=os.getenv("CODE_NIM_URL", "http://localhost:12802/v1"),
        nim_model=os.getenv("CODE_NIM_MODEL", "nvidia/mistral-nemo-minitron-8b-base"),
        system_prompt=CODE_SYSTEM_PROMPT + """

You are a professional software developer.

Key responsibilities:
1. Write code that meets user requirements
2. Analyze and review code
3. Fix bugs and optimize performance

When writing code:
- Write clean, readable code
- Add appropriate comments
- Include error handling
- Test before delivering""",
        **kwargs
    )


def create_project_deep_agent(**kwargs) -> DeepAgentAdapter:
    """
    프로젝트 관리 Deep Agent 생성

    SubAgent를 활용한 복잡한 프로젝트 작업 처리
    RAG, Code, IMS 도구를 모두 포함하여 통합 검색 및 개발 지원

    Args:
        **kwargs: DeepAgentAdapter 추가 인자

    Returns:
        풀스택 도구가 설정된 DeepAgentAdapter
    """
    from ..middleware import get_rag_tools, get_code_tools, get_ims_tools

    # RAG + Code + IMS 도구 통합
    rag_tools = get_rag_tools()
    code_tools = get_code_tools()
    ims_tools = get_ims_tools()

    print(f"[create_project_deep_agent] RAG tools: {len(rag_tools)}, Code tools: {len(code_tools)}, IMS tools: {len(ims_tools)}", flush=True)
    for tool in ims_tools:
        print(f"[create_project_deep_agent] IMS tool: {tool.name}", flush=True)

    all_tools = rag_tools + code_tools + ims_tools

    return DeepAgentAdapter(
        name="ProjectDeepAgent",
        agent_type=AgentType.PLANNER,
        description="Deep Agents 기반 프로젝트 관리 에이전트 (RAG + Code + IMS 통합)",
        tools=all_tools,
        subagents=None,  # Will use default subagents
        system_prompt="""You are a project manager and tech lead with access to multiple systems.

## Available Tools:

### Knowledge Base (RAG)
- **vector_search**: Search documents in the knowledge base
- **document_read**: Read full document content

### Code Tools
- **code_execute**: Execute code snippets

### IMS (Issue Management System)
- **ims_search**: Search for issues in IMS (bug reports, feature requests)
- **ims_get_detail**: Get detailed information for a specific issue

## Key Responsibilities:
1. Understand user requests and break them down into steps
2. Use appropriate tools to gather information
3. For IMS-related questions, ALWAYS use ims_search first
4. Provide clear, well-organized responses with sources

## Important Rules:
- When user asks about IMS issues, API usage, or bug reports: Use ims_search
- When user asks about knowledge base or documents: Use vector_search
- Always provide URLs so users can access sources directly""",
        **kwargs
    )
