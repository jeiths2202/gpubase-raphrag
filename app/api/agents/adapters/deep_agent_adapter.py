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
import re
import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator

logger = logging.getLogger(__name__)


def _load_agent_prompt(agent_type: str) -> Optional[str]:
    """
    에이전트 프롬프트 파일 로드

    Args:
        agent_type: 에이전트 타입 (rag, ims, code, vision, planner)

    Returns:
        프롬프트 텍스트 또는 None
    """
    # adapters/ 디렉토리에서 상위로 이동하여 prompts/ 디렉토리 접근
    prompt_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompt_dir / f"{agent_type}_agent.txt"

    if prompt_file.exists():
        try:
            content = prompt_file.read_text(encoding="utf-8")
            logger.info(f"[DeepAgent] Loaded prompt from {prompt_file.name} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.warning(f"[DeepAgent] Failed to load {prompt_file}: {e}")
    else:
        logger.warning(f"[DeepAgent] Prompt file not found: {prompt_file}")

    return None


def strip_thinking_tags(text: str) -> str:
    """
    LLM 응답에서 thinking 관련 콘텐츠 제거
    - <think>...</think> 태그
    - 내부 추론 과정 전체
    """
    if not text:
        return text

    # <think>...</think> 태그와 그 내용 제거 (멀티라인 지원)
    cleaned = re.sub(r'<think>.*?</think>\s*', '', text, flags=re.DOTALL)

    # 내부 추론 패턴 (응답 전체가 이런 패턴이면 무시)
    internal_reasoning_patterns = [
        r'This will help me',
        # 확장된 동사 목록: provide, answer, explain, give, respond, analyze 추가
        r'I (?:need to|should|will|\'ll) (?:search|check|look|find|use|try|provide|answer|explain|give|respond|analyze)',
        r'(?:Let me|I\'m going to) (?:search|check|look|find|use|try|provide|answer|explain|give|respond|analyze)',
        r'using the available tools',
        r'(?:First|Next),? I (?:need to|should|will)',
        r'The (?:user|question) (?:is asking|wants|asked)',
        r'I don\'t have (?:enough|any) information',
        r'(?:Maybe|Perhaps) (?:I should|using)',
        # 새로 추가된 패턴들
        r'Looking at the (?:tool|search) (?:response|results?|output)',
        r'(?:Based on|According to) the (?:search|tool) results?',
        r'to ".*?" in (?:Japanese|Korean|English|Chinese)',  # 언어 변환 추론
        r'I can see (?:that|from)',
        r'(?:There are|I found) (?:two|three|several|\d+) (?:main |relevant )?(?:chunks?|results?|documents?)',
        r'I (?:can|will|should) (?:combine|synthesize|summarize)',
    ]

    # 응답이 내부 추론인지 확인
    is_internal_reasoning = any(
        re.search(pattern, cleaned, re.IGNORECASE)
        for pattern in internal_reasoning_patterns
    )

    if is_internal_reasoning:
        # 전체 응답이 추론이면 기본 메시지 반환
        return ""  # 빈 문자열 반환하면 호출자가 기본 메시지 사용

    # 응답이 내부 추론으로 시작하는지 확인
    thinking_start_patterns = [
        r'^Okay,?\s+(?:so\s+)?(?:the user|I)',
        r'^(?:First|Let me|I need to|I should|I\'ll|I will)\s+',
        r'^(?:Hmm|Well|Alright|The user)',
        r'^(?:Since|Looking at|Based on)\s+(?:the|this|my)',
        # 새로 추가된 시작 패턴
        r'^to\s+".*?"\s+in\s+(?:Japanese|Korean|English)',  # 'to "query" in Japanese' 형태
        r'^(?:Now|So),?\s+(?:I|let me|the)',
        r'^The\s+(?:first|second|main|relevant)\s+',
        r'^(?:Looking|Analyzing|Examining)\s+',
    ]

    is_thinking_response = any(
        re.match(pattern, cleaned, re.IGNORECASE)
        for pattern in thinking_start_patterns
    )

    if is_thinking_response:
        # 마지막 문단에서 실제 답변 찾기
        paragraphs = cleaned.split('\n\n')
        for para in reversed(paragraphs):
            para = para.strip()
            if para and not any(
                re.match(p, para, re.IGNORECASE)
                for p in thinking_start_patterns
            ) and not any(
                re.search(p, para, re.IGNORECASE)
                for p in internal_reasoning_patterns
            ):
                return para

    return cleaned.strip()

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

# LangGraph checkpointer for conversation state (prefer SqliteSaver for persistence)
try:
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    LANGGRAPH_SQLITE_CHECKPOINTER_AVAILABLE = True
except ImportError:
    SqliteSaver = None
    LANGGRAPH_SQLITE_CHECKPOINTER_AVAILABLE = False
    logger.info("LangGraph SqliteSaver not available, trying MemorySaver fallback")

try:
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_CHECKPOINTER_AVAILABLE = True
except ImportError:
    MemorySaver = None
    LANGGRAPH_CHECKPOINTER_AVAILABLE = LANGGRAPH_SQLITE_CHECKPOINTER_AVAILABLE
    if not LANGGRAPH_CHECKPOINTER_AVAILABLE:
        logger.info("LangGraph checkpointer not available, conversation state disabled")

try:
    from langchain_ollama import ChatOllama
    LANGCHAIN_OLLAMA_AVAILABLE = True
except ImportError:
    LANGCHAIN_OLLAMA_AVAILABLE = False

# NIM (OpenAI-compatible) support
try:
    from langchain_openai import ChatOpenAI
    LANGCHAIN_OPENAI_AVAILABLE = True
except ImportError:
    LANGCHAIN_OPENAI_AVAILABLE = False

from ..types import (
    AgentType, AgentContext, AgentResult, AgentStreamChunk,
    MessageRole
)
from ..base import BaseAgent
from ...core.config import get_api_settings

_settings = get_api_settings()


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
        temperature: float = _settings.LLM_TEMPERATURE,
        max_tokens: int = _settings.LLM_MAX_TOKENS,
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
        self._current_language = None  # 언어 변경 시 에이전트 재생성을 위한 추적
        self._base_system_prompt = system_prompt  # 원본 system_prompt 보존
        self._checkpointer = None  # 대화 상태 체크포인터 (cross-thread persistence)

        if not DEEPAGENTS_AVAILABLE:
            logger.warning(f"[{self.name}] Deep Agents not available")

        if enable_long_term_memory and not DEEPAGENTS_BACKENDS_AVAILABLE:
            logger.info(f"[{self.name}] Long-term memory backends not available, using ephemeral storage")

    def _get_llm(self):
        """LLM instance - NIM first, Ollama fallback

        Supports RAG_LLM_USE_LARGE_CONTEXT environment variable:
        - When true: Uses Mistral NeMo 12B (128K context) for better RAG performance
        - When false/unset: Uses Nemotron Nano 9B (8K context)
        """
        if self._llm is not None:
            return self._llm

        # Check if large context mode is enabled for RAG
        use_large_context = os.getenv("RAG_LLM_USE_LARGE_CONTEXT", "false").lower() == "true"

        if use_large_context:
            # Use Mistral NeMo 12B (128K context) for better RAG performance
            llm_api_url = os.getenv("CODE_LLM_API_URL")
            llm_model = os.getenv("CODE_LLM_MODEL", "mistralai/Mistral-Nemo-Instruct-2407")
            context_info = "Large Context (128K)"
        else:
            # Default: Qwen2.5-72B v10 unified v2 (4K context)
            llm_api_url = os.getenv("LLM_API_URL")
            llm_model = os.getenv("LLM_MODEL", "/opt/models/merged_cpt_72b")
            context_info = "Standard (4K)"

        if llm_api_url and LANGCHAIN_OPENAI_AVAILABLE:
            base_url = llm_api_url.replace("/chat/completions", "")
            if not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            logger.info(f"[{self.name}] Using NIM {context_info}: {llm_model}")
            return ChatOpenAI(
                api_key="not-needed",
                base_url=base_url,
                model=llm_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        if LANGCHAIN_OLLAMA_AVAILABLE:
            ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
            logger.info(f"[{self.name}] Using Ollama: {ollama_model}")
            return ChatOllama(
                base_url=ollama_base,
                model=ollama_model,
                temperature=self.temperature,
            )

        raise RuntimeError("No LLM backend available")

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

    def _create_checkpointer(self):
        """
        대화 상태 체크포인터 생성.
        SqliteSaver 우선 (영속), MemorySaver fallback (비영속).
        """
        if LANGGRAPH_SQLITE_CHECKPOINTER_AVAILABLE:
            try:
                db_dir = Path(os.getenv("CHECKPOINT_DB_DIR", "data/checkpoints"))
                db_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(db_dir / "deep_agent.db")
                conn = sqlite3.connect(db_path, check_same_thread=False)
                saver = SqliteSaver(conn)
                saver.setup()
                logger.info(f"[{self.name}] Using SqliteSaver (persistent) at {db_path}")
                return saver
            except Exception as e:
                logger.warning(f"[{self.name}] SqliteSaver failed ({e}), falling back to MemorySaver")

        if LANGGRAPH_CHECKPOINTER_AVAILABLE and MemorySaver is not None:
            logger.info(f"[{self.name}] Using MemorySaver (non-persistent)")
            return MemorySaver()

        logger.warning(f"[{self.name}] No checkpointer available")
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

    def _create_deep_agent(self, language: Optional[str] = None):
        """
        Deep Agent 인스턴스 생성 (Lazy initialization with Long-term Memory)

        Args:
            language: 사용자 설정 언어 (ko, en, ja). 언어가 변경되면 에이전트 재생성.
        """
        # 언어가 변경되면 에이전트 재생성
        if language and language != self._current_language:
            if self._deep_agent is not None:
                logger.info(f"[{self.name}] Language changed ({self._current_language} -> {language}), recreating agent")
                self._deep_agent = None
            self._current_language = language

        if self._deep_agent is not None:
            return self._deep_agent

        if not DEEPAGENTS_AVAILABLE:
            raise RuntimeError("Deep Agents not available")

        llm = self._get_llm()

        # 언어 지시가 포함된 system_prompt 빌드
        final_system_prompt = self.system_prompt or ""

        if language and language != "auto":
            # 중앙화된 언어 정책 서비스 사용
            from app.api.services.language_policy import get_language_policy_service
            lang_service = get_language_policy_service()
            language_instruction = lang_service.get_language_instruction(language)

            # 언어 지시를 system_prompt 최상단에 PREPEND
            final_system_prompt = f"{language_instruction}\n\n{final_system_prompt}"
            logger.info(f"[{self.name}] Language instruction PREPENDED to system_prompt: {language}")

        # Create Deep Agent with optional long-term memory
        agent_kwargs = {
            "model": llm,
            "tools": self._custom_tools if self._custom_tools else None,
            "system_prompt": final_system_prompt,
        }

        # Add LangGraph store for persistence
        store = self._get_langraph_store()
        if store is not None:
            agent_kwargs["store"] = store
            logger.info(f"[{self.name}] LangGraph store configured for persistence")

        # Add checkpointer for conversation state persistence
        if (LANGGRAPH_SQLITE_CHECKPOINTER_AVAILABLE or LANGGRAPH_CHECKPOINTER_AVAILABLE) and self._enable_long_term_memory:
            if self._checkpointer is None:
                self._checkpointer = self._create_checkpointer()
            if self._checkpointer is not None:
                agent_kwargs["checkpointer"] = self._checkpointer
                logger.info(f"[{self.name}] Checkpointer configured for conversation state")

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
            # 🔴 언어 설정을 전달하여 에이전트 생성 (언어 변경 시 자동 재생성)
            user_language = context.language if context.language and context.language != "auto" else None
            agent = self._create_deep_agent(language=user_language)

            # 대화 히스토리 변환
            messages = []
            for hist in context.conversation_history[-5:]:
                if "question" in hist:
                    messages.append(HumanMessage(content=hist["question"]))
                if "answer" in hist:
                    messages.append(AIMessage(content=hist["answer"]))

            # 언어 지시는 이제 _create_deep_agent()에서 system_prompt에 직접 포함됨
            # (SystemMessage 방식보다 효과적)

            # 🚨 CRITICAL: Handle file_context (Session Context vs Database Separation)
            # User-attached files/URLs must be answered from DIRECTLY without using search tools
            # This is session-only context, NOT stored in database
            if context.file_context:
                enhanced_task = f"""[ATTACHED FILE CONTEXT - PRIMARY REFERENCE]
The user has attached file(s) to this session. Answer from this context FIRST.
Do NOT use vector_search, graph_query, or other database tools if the answer is in the attached context.

{context.file_context}

[END ATTACHED FILE CONTEXT]

IMPORTANT:
- Answer from the attached file context above if possible
- Mention "첨부된 문서에 따르면" or "According to the attached document" when answering from attached files
- Only use search tools if the information is NOT found in the attached context

User Query: {task}"""
                messages.append(HumanMessage(content=enhanced_task))
                logger.info(f"[{self.name}] Processing with attached file context ({len(context.file_context)} chars)")
            else:
                messages.append(HumanMessage(content=task))

            # Deep Agent 실행 (recursion_limit으로 무한 루프 방지)
            # thread_id로 사용자/세션별 대화 상태 분리
            thread_id = self._user_id or "default"
            if context.metadata and context.metadata.get("session_id"):
                thread_id = f"{thread_id}_{context.metadata['session_id']}"
            result = await asyncio.wait_for(
                agent.ainvoke(
                    {"messages": messages},
                    config={
                        "configurable": {"thread_id": thread_id},
                        "recursion_limit": 25,
                    }
                ),
                timeout=300.0  # 5분 타임아웃
            )

            # 결과 추출 및 thinking 태그 제거
            answer = ""
            if "messages" in result:
                for msg in reversed(result["messages"]):
                    if hasattr(msg, "content") and msg.content:
                        answer = strip_thinking_tags(msg.content)
                        break

            # 빈 응답이면 기본 메시지 사용
            if not answer:
                answer = "죄송합니다. 해당 질문에 대한 관련 정보를 지식 베이스에서 찾을 수 없습니다. 다른 키워드로 검색하거나 질문을 더 구체적으로 해주세요."

            return AgentResult(
                answer=answer,
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

    async def _fetch_images_for_sources(
        self,
        sources: List[Dict[str, Any]],
        max_images: int = 5,
        max_image_size_kb: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Fetch figure images related to source documents.

        Args:
            sources: List of source dictionaries with doc_id and page_number
            max_images: Maximum number of images to return
            max_image_size_kb: Maximum size per image in KB

        Returns:
            List of image data dicts with base64 encoded data
        """
        if not sources:
            return []

        try:
            import asyncpg
            from ...services.figure_image_service import get_figure_image_service
            from ...infrastructure.postgres.image_embedding_repository import PostgresImageEmbeddingRepository
            from ...core.config import api_settings

            # Create connection DSN
            dsn = f"postgresql://{api_settings.POSTGRES_USER}:{api_settings.POSTGRES_PASSWORD}@{api_settings.POSTGRES_HOST}:{api_settings.POSTGRES_PORT}/{api_settings.POSTGRES_DB}"

            # Create repository with pool
            repo = await PostgresImageEmbeddingRepository.create_with_pool(
                dsn,
                min_size=1,
                max_size=3
            )

            try:
                # Create fresh figure image service (don't use singleton to ensure new code is used)
                from ...services.figure_image_service import FigureImageService, reset_figure_image_service
                reset_figure_image_service()  # Reset singleton to pick up any code changes
                figure_service = FigureImageService(repo)

                # Fetch images for sources
                images = await figure_service.get_images_for_sources(
                    sources=sources,
                    include_data=True
                )

                # Filter by size and limit count
                filtered_images = []
                for img in images:
                    if len(filtered_images) >= max_images:
                        break
                    if img.get("data"):
                        # Check base64 data size (rough estimate: base64 is ~33% larger)
                        data_size_kb = len(img["data"]) / 1024 / 1.33
                        if data_size_kb <= max_image_size_kb:
                            filtered_images.append(img)
                        else:
                            logger.warning(f"Image {img.get('id')} exceeds size limit ({data_size_kb:.0f}KB > {max_image_size_kb}KB)")

                logger.info(f"[{self.name}] Retrieved {len(filtered_images)} images for {len(sources)} sources")
                return filtered_images

            finally:
                # Close the repository pool
                await repo.close()

        except Exception as e:
            logger.error(f"[{self.name}] Failed to fetch images: {e}")
            return []

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """스트리밍 실행 with sources extraction"""
        yield AgentStreamChunk(chunk_type="thinking", content="Processing...")

        try:
            # Execute and get result
            result = await self.execute(task, context)

            # Extract sources from context metadata (set by tools during execution)
            sources = context.metadata.get("sources", []) if context.metadata else []

            # 결과를 청크로 스트리밍
            chunk_size = 50
            for i in range(0, len(result.answer), chunk_size):
                chunk = result.answer[i:i + chunk_size]
                yield AgentStreamChunk(chunk_type="text", content=chunk)

            # Yield sources before done (if available)
            if sources:
                logger.info(f"[{self.name}] Yielding {len(sources)} sources from Deep Agent")
                yield AgentStreamChunk(
                    chunk_type="sources",
                    sources=sources[:10]  # Limit to 10 sources
                )

                # Fetch and yield related images
                try:
                    images = await self._fetch_images_for_sources(sources[:10])
                    if images:
                        logger.info(f"[{self.name}] Yielding {len(images)} images from Deep Agent")
                        yield AgentStreamChunk(
                            chunk_type="images",
                            images=images
                        )
                except Exception as img_err:
                    logger.warning(f"[{self.name}] Failed to fetch images: {img_err}")

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
    include_adaptive_search: bool = False,  # Disabled: PostgreSQL embedding asymmetry issue
    additional_tools: Optional[List] = None,
    multimodal_service=None,
    adaptive_service=None,
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
        include_adaptive_search: 적응형 PDF 검색 도구 포함 여부
        additional_tools: 추가 도구 목록
        multimodal_service: MultimodalRAGService 인스턴스
        adaptive_service: PDFAdaptiveEmbeddingService 인스턴스
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

    # Get adaptive service for structure-preserving PDF search
    if adaptive_service is None and include_adaptive_search:
        try:
            from ...core.deps import get_adaptive_embedding_service
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pass  # Will lazy load in the tool
            else:
                adaptive_service = loop.run_until_complete(get_adaptive_embedding_service())
        except Exception:
            pass  # Will use lazy loading in the tool

    # RAG 도구 추가
    rag_tools = get_rag_tools(
        multimodal_service=multimodal_service,
        adaptive_service=adaptive_service
    )
    for tool in rag_tools:
        if include_vector_search and tool.name == "vector_search":
            tools.append(tool)
        elif include_graph_query and tool.name == "graph_query":
            tools.append(tool)
        elif include_image_search and tool.name == "image_search":
            tools.append(tool)
        elif include_adaptive_search and tool.name == "adaptive_search":
            tools.append(tool)

    # 추가 도구
    if additional_tools:
        tools.extend(additional_tools)

    # =========================================================================
    # 통합된 시스템 프롬프트: rag_agent.txt 로드 + Deep Agent 전용 보충
    # =========================================================================

    # 1. rag_agent.txt에서 기본 프롬프트 로드 (일반 RAG Agent와 동일)
    base_prompt = _load_agent_prompt("rag")

    # 2. Deep Agent 전용 보충 (도구 상세 설명 + Long-term Memory)
    deep_agent_supplement = """

## Deep Agent Specific: Available Tools

### vector_search (PRIORITY 1 - ALWAYS USE FIRST)
**MANDATORY: Use this tool FIRST** for all knowledge base queries.
- Primary search tool using Neo4j vector index
- Accurate semantic similarity with properly embedded passages
- **CRITICAL: Use the EXACT user query text - DO NOT modify, translate, or summarize**
- Best for all document searches

### graph_query (OPTIONAL)
Query entity relationships in the knowledge graph.
- Use for exploring connections between concepts

### image_search (OPTIONAL)
Search for images, diagrams, and charts in documents.
- Use when questions involve visual content

## Deep Agent Specific: Long-term Memory
You can store and retrieve information across conversations using file paths:
- /memories/: General long-term memory
- /preferences/: User preferences that persist
- /knowledge/: Accumulated knowledge from conversations
- /instructions/: Self-improving instructions based on feedback
- /research/: Research progress across sessions
"""

    # 3. 최종 프롬프트 조합
    if base_prompt:
        default_prompt = base_prompt + deep_agent_supplement
        logger.info("[DeepAgent] Using integrated prompt: rag_agent.txt + Deep Agent supplement")
    else:
        # Fallback: 기본 프롬프트 (rag_agent.txt 로드 실패 시)
        default_prompt = """You are an intelligent knowledge assistant powered by a Hybrid RAG system.

IMPORTANT: Do NOT show your internal reasoning or thinking process to the user.
Do NOT start responses with phrases like "Okay, the user is asking...", "First, I need to...", "Let me think...", etc.
Provide direct, helpful answers without exposing your thought process.

Search the knowledge base using tools before answering.
If no relevant information is found, clearly state that.
Respond in the user's configured language preference.
""" + deep_agent_supplement
        logger.warning("[DeepAgent] Using fallback prompt (rag_agent.txt not found)")

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
