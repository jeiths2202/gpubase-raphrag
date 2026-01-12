#!/usr/bin/env python3
"""
WebUI Agent 구조 기반 샘플 코드
================================

이 샘플은 HybridRAG KMS 프로젝트의 WebUI Agent 구조를 기반으로
AI Agent를 생성하고 사용하는 방법을 보여줍니다.

핵심 구조:
- BaseAgent: 모든 에이전트의 추상 기반 클래스
- AgentExecutor: ReAct (Reasoning + Acting) 루프 실행
- ToolRegistry: 도구 등록 및 관리 (Singleton)
- AgentRegistry: 에이전트 등록 및 관리 (Singleton)
- AgentOrchestrator: 태스크 라우팅 및 실행 조율

실행 방법:
    python samples/webui_agent_sample.py
    python samples/webui_agent_sample.py --test  # Mock LLM 사용

작성자: WebUI Agent Sample
"""

import asyncio
import json
import logging
import time
import sys
import io
from abc import ABC, abstractmethod

# Windows 콘솔 UTF-8 인코딩 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any, AsyncGenerator, Dict, List, Optional, Type, Callable
)

import httpx

# =============================================================================
# 로깅 설정
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# 1. 타입 정의 (app/api/agents/types.py 패턴)
# =============================================================================

class AgentType(str, Enum):
    """
    에이전트 타입 열거형

    WebUI에서는 각 에이전트가 고유한 타입을 가지며,
    Orchestrator가 태스크에 맞는 에이전트를 선택합니다.
    """
    ORCHESTRA = "orchestra"           # 오케스트라: 전체 흐름 조율
    DEVELOPER = "developer"           # 개발자: 코드 작성
    REVIEWER = "reviewer"             # 리뷰어: 코드 검토
    RAG = "rag"                       # RAG: 지식베이스 검색
    CODE = "code"                     # 코드: 코드 생성/분석


class MessageRole(str, Enum):
    """메시지 역할"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChunkType(str, Enum):
    """스트리밍 청크 타입"""
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TEXT = "text"
    DONE = "done"
    ERROR = "error"


@dataclass
class AgentMessage:
    """
    에이전트 메시지

    LLM과의 대화에서 사용되는 메시지 구조입니다.
    WebUI의 AgentMessage와 동일한 패턴을 따릅니다.
    """
    role: MessageRole
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """LLM API 호출용 딕셔너리 변환"""
        msg = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class AgentContext:
    """
    에이전트 실행 컨텍스트

    세션 정보, 대화 히스토리, 사용자 설정 등
    에이전트 실행에 필요한 컨텍스트를 담습니다.
    """
    session_id: str
    user_id: str
    language: str = "ko"
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """
    에이전트 실행 결과

    WebUI의 AgentResult와 동일한 구조입니다.
    """
    answer: str
    agent_type: AgentType
    steps: int
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class AgentStreamChunk:
    """
    스트리밍 청크

    SSE(Server-Sent Events)로 전송되는 스트리밍 응답 단위입니다.
    """
    chunk_type: ChunkType
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ToolDefinition:
    """
    도구 정의

    LLM Function Calling에 사용되는 도구 스키마입니다.
    """
    name: str
    description: str
    parameters: Dict[str, Any]


# =============================================================================
# 2. LLM 어댑터 (app/api/adapters/ 패턴)
# =============================================================================

class LLMAdapter:
    """
    LLM 어댑터

    WebUI에서는 adapters/ 디렉토리에 각 LLM별 어댑터가 있습니다.
    (nemotron_adapter.py, mistral_adapter.py 등)

    이 샘플에서는 간단한 HTTP 클라이언트로 구현합니다.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:12800/v1/chat/completions",
        model: str = "nvidia/llama-3.1-nemotron-nano-8b-v1",
        timeout: float = 120.0
    ):
        """
        LLM 어댑터 초기화

        Args:
            api_url: LLM API 엔드포인트 (NVIDIA NIM 또는 OpenAI 호환)
            model: 사용할 모델 ID
            timeout: API 타임아웃 (초)
        """
        self.api_url = api_url
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 가져오기 (지연 초기화)"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        LLM 응답 생성

        Args:
            messages: 대화 메시지 리스트
            tools: Function Calling용 도구 정의
            temperature: 생성 다양성
            max_tokens: 최대 토큰 수

        Returns:
            LLM 응답 (content, tool_calls 포함)
        """
        client = await self._get_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            response = await client.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()

            # OpenAI 형식 응답 파싱
            choice = result["choices"][0]["message"]
            return {
                "content": choice.get("content", ""),
                "tool_calls": choice.get("tool_calls"),
                "finish_reason": result["choices"][0].get("finish_reason")
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"LLM API 오류: HTTP {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"LLM 호출 실패: {e}")
            raise

    async def close(self):
        """리소스 정리"""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# 3. 도구 시스템 (app/api/agents/tools/ 패턴)
# =============================================================================

class BaseTool(ABC):
    """
    도구 기본 클래스

    WebUI에서는 tools/base.py에 정의되어 있습니다.
    모든 도구는 이 클래스를 상속받아 구현합니다.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: AgentContext
    ) -> Dict[str, Any]:
        """
        도구 실행

        Args:
            arguments: 도구 인자
            context: 실행 컨텍스트

        Returns:
            실행 결과 (success, output 포함)
        """
        pass

    def get_definition(self) -> ToolDefinition:
        """LLM Function Calling용 정의 반환"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self._get_parameters()
        )

    @abstractmethod
    def _get_parameters(self) -> Dict[str, Any]:
        """도구 파라미터 스키마 반환"""
        pass


class CodeCompileTool(BaseTool):
    """
    코드 컴파일 도구

    C 코드를 컴파일하고 결과를 반환합니다.
    """

    def __init__(self):
        super().__init__(
            name="code_compile",
            description="C 코드를 컴파일하고 결과를 확인합니다"
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: AgentContext
    ) -> Dict[str, Any]:
        code = arguments.get("code", "")
        language = arguments.get("language", "c")

        # 실제 구현에서는 subprocess로 컴파일 실행
        # 샘플에서는 Mock 결과 반환
        logger.info(f"[{self.name}] 컴파일 실행: {language}")

        return {
            "success": True,
            "output": f"컴파일 성공: {language} 코드 ({len(code)} chars)",
            "warnings": [],
            "errors": []
        }

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "컴파일할 코드"
                },
                "language": {
                    "type": "string",
                    "description": "프로그래밍 언어",
                    "enum": ["c", "cpp", "java"]
                }
            },
            "required": ["code"]
        }


class CodeAnalyzeTool(BaseTool):
    """
    코드 분석 도구

    코드의 품질, 복잡도, 이슈를 분석합니다.
    """

    def __init__(self):
        super().__init__(
            name="code_analyze",
            description="코드를 분석하여 품질 점수와 이슈를 반환합니다"
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: AgentContext
    ) -> Dict[str, Any]:
        code = arguments.get("code", "")

        # 간단한 분석 로직 (실제로는 정적 분석 도구 사용)
        lines = len(code.split('\n'))
        has_comments = '//' in code or '/*' in code
        has_main = 'main' in code

        return {
            "success": True,
            "output": {
                "lines": lines,
                "has_comments": has_comments,
                "has_main_function": has_main,
                "complexity_score": min(lines / 10, 10),  # 단순 예시
                "quality_score": 8 if has_comments else 6
            }
        }

    def _get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "분석할 코드"
                }
            },
            "required": ["code"]
        }


# =============================================================================
# 4. 도구 레지스트리 (app/api/agents/registry.py 패턴)
# =============================================================================

class ToolRegistry:
    """
    도구 레지스트리 (Singleton)

    WebUI에서는 모든 도구를 중앙에서 관리합니다.
    에이전트는 레지스트리에서 필요한 도구를 가져와 사용합니다.
    """

    _instance: Optional['ToolRegistry'] = None

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    @classmethod
    def get_instance(cls) -> 'ToolRegistry':
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_tools()
        return cls._instance

    def _register_default_tools(self):
        """기본 도구 등록"""
        default_tools = [
            CodeCompileTool(),
            CodeAnalyzeTool(),
        ]

        for tool in default_tools:
            self.register(tool)

        logger.info(f"[ToolRegistry] {len(default_tools)}개 기본 도구 등록됨")

    def register(self, tool: BaseTool) -> None:
        """도구 등록"""
        self._tools[tool.name] = tool
        logger.debug(f"[ToolRegistry] 도구 등록: {tool.name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """이름으로 도구 가져오기"""
        return self._tools.get(name)

    def get_all(self) -> List[BaseTool]:
        """모든 도구 반환"""
        return list(self._tools.values())

    def get_definitions(
        self,
        tool_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        LLM Function Calling용 도구 정의 반환

        Args:
            tool_names: 특정 도구만 선택 (None이면 전체)

        Returns:
            OpenAI 형식의 도구 정의 리스트
        """
        if tool_names is None:
            tools = self._tools.values()
        else:
            tools = [self._tools[n] for n in tool_names if n in self._tools]

        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t._get_parameters()
                }
            }
            for t in tools
        ]


def get_tool_registry() -> ToolRegistry:
    """전역 도구 레지스트리 반환"""
    return ToolRegistry.get_instance()


# =============================================================================
# 5. 기본 에이전트 (app/api/agents/base.py 패턴)
# =============================================================================

class BaseAgent(ABC):
    """
    에이전트 기본 추상 클래스

    WebUI의 BaseAgent와 동일한 패턴입니다.
    모든 에이전트는 이 클래스를 상속받아 구현합니다.

    핵심 메서드:
    - execute(): 동기식 실행
    - stream(): 비동기 스트리밍 실행
    - system_prompt: 에이전트 행동 정의
    """

    def __init__(
        self,
        name: str,
        agent_type: AgentType,
        description: str,
        tools: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ):
        """
        에이전트 초기화

        Args:
            name: 에이전트 이름
            agent_type: 에이전트 타입
            description: 에이전트 설명
            tools: 사용 가능한 도구 이름 리스트
            system_prompt: 시스템 프롬프트 (None이면 기본값 사용)
            model_id: 사용할 LLM 모델 ID
            temperature: 생성 다양성
            max_tokens: 최대 토큰 수
        """
        self.name = name
        self.agent_type = agent_type
        self.description = description
        self.tools = tools or []
        self._system_prompt = system_prompt
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def system_prompt(self) -> str:
        """시스템 프롬프트 반환"""
        if self._system_prompt:
            return self._system_prompt
        return self._get_default_prompt()

    @abstractmethod
    def _get_default_prompt(self) -> str:
        """기본 시스템 프롬프트 반환 (하위 클래스에서 구현)"""
        pass

    @abstractmethod
    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        태스크 실행

        Args:
            task: 사용자 태스크/질문
            context: 실행 컨텍스트

        Returns:
            실행 결과
        """
        pass

    @abstractmethod
    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        스트리밍 실행

        Args:
            task: 사용자 태스크/질문
            context: 실행 컨텍스트

        Yields:
            스트리밍 청크
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', type={self.agent_type.value})"


# =============================================================================
# 6. 에이전트 실행기 (app/api/agents/executor.py 패턴)
# =============================================================================

class AgentExecutor:
    """
    에이전트 실행기

    ReAct (Reasoning + Acting) 루프를 구현합니다.
    WebUI의 AgentExecutor와 동일한 패턴입니다.

    실행 흐름:
    1. 시스템 프롬프트 + 사용자 태스크로 LLM 호출
    2. LLM이 도구 호출을 요청하면 도구 실행
    3. 도구 결과를 LLM에 전달
    4. 최종 응답 생성까지 반복
    """

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        tool_registry: Optional[ToolRegistry] = None,
        max_iterations: int = 10
    ):
        """
        실행기 초기화

        Args:
            llm_adapter: LLM 어댑터
            tool_registry: 도구 레지스트리 (None이면 전역 사용)
            max_iterations: 최대 ReAct 루프 반복 횟수
        """
        self.llm_adapter = llm_adapter
        self.tool_registry = tool_registry or get_tool_registry()
        self.max_iterations = max_iterations

    async def run(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        에이전트 실행

        Args:
            agent: 실행할 에이전트
            task: 사용자 태스크
            context: 실행 컨텍스트

        Returns:
            실행 결과
        """
        start_time = time.time()
        steps = 0
        tool_calls_history = []
        tool_results_history = []

        # 메시지 초기화
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": task}
        ]

        # 도구 정의 가져오기
        tool_definitions = self.tool_registry.get_definitions(agent.tools) if agent.tools else None

        logger.info(f"[Executor] {agent.name} 실행 시작: {task[:50]}...")

        # ReAct 루프
        while steps < self.max_iterations:
            steps += 1
            logger.debug(f"[Executor] Step {steps}")

            try:
                # LLM 호출
                response = await self.llm_adapter.generate(
                    messages=messages,
                    tools=tool_definitions,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens
                )

                content = response.get("content", "")
                tool_calls = response.get("tool_calls")

                # 도구 호출이 있으면 실행
                if tool_calls:
                    # Assistant 메시지 추가 (도구 호출 포함)
                    messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": tool_calls
                    })

                    # 각 도구 실행
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        tool_name = func.get("name")
                        tool_args = json.loads(func.get("arguments", "{}"))
                        tool_id = tc.get("id", f"call_{steps}")

                        logger.info(f"[Executor] 도구 호출: {tool_name}")

                        tool = self.tool_registry.get(tool_name)
                        if tool:
                            result = await tool.execute(tool_args, context)
                        else:
                            result = {"success": False, "error": f"Unknown tool: {tool_name}"}

                        tool_calls_history.append({
                            "name": tool_name,
                            "arguments": tool_args
                        })
                        tool_results_history.append(result)

                        # 도구 결과 메시지 추가
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                else:
                    # 도구 호출 없음 = 최종 응답
                    execution_time = time.time() - start_time

                    logger.info(f"[Executor] {agent.name} 실행 완료 ({steps} steps, {execution_time:.2f}s)")

                    return AgentResult(
                        answer=content,
                        agent_type=agent.agent_type,
                        steps=steps,
                        tool_calls=tool_calls_history,
                        tool_results=tool_results_history,
                        execution_time=execution_time,
                        success=True
                    )

            except Exception as e:
                logger.error(f"[Executor] 실행 오류: {e}")
                return AgentResult(
                    answer="",
                    agent_type=agent.agent_type,
                    steps=steps,
                    execution_time=time.time() - start_time,
                    success=False,
                    error=str(e)
                )

        # 최대 반복 도달
        return AgentResult(
            answer="최대 실행 단계에 도달했습니다.",
            agent_type=agent.agent_type,
            steps=steps,
            tool_calls=tool_calls_history,
            tool_results=tool_results_history,
            execution_time=time.time() - start_time,
            success=False,
            error="Max iterations reached"
        )

    async def stream(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        """
        스트리밍 실행

        실제 WebUI에서는 SSE로 청크를 전송합니다.
        """
        yield AgentStreamChunk(chunk_type=ChunkType.THINKING, content="처리 중...")

        # 실행
        result = await self.run(agent, task, context)

        # 결과 스트리밍
        chunk_size = 50
        for i in range(0, len(result.answer), chunk_size):
            chunk = result.answer[i:i + chunk_size]
            yield AgentStreamChunk(chunk_type=ChunkType.TEXT, content=chunk)
            await asyncio.sleep(0.02)

        yield AgentStreamChunk(
            chunk_type=ChunkType.DONE,
            metadata={"execution_time": result.execution_time, "steps": result.steps}
        )


# =============================================================================
# 7. 구체적인 에이전트 구현 (app/api/agents/agents/ 패턴)
# =============================================================================

class OrchestraAgent(BaseAgent):
    """
    오케스트라 에이전트

    전체 작업 흐름을 조율하고 다른 에이전트에게 작업을 분배합니다.
    WebUI의 AgentOrchestrator와 유사한 역할을 합니다.
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        super().__init__(
            name="Orchestra Agent",
            agent_type=AgentType.ORCHESTRA,
            description="전체 작업 흐름을 조율하고 에이전트를 조정하는 오케스트라",
            tools=[],  # 오케스트라는 직접 도구를 사용하지 않음
            model_id="nemotron-nano-9b"
        )
        self._executor = executor

    def _get_default_prompt(self) -> str:
        return """당신은 소프트웨어 개발 프로젝트의 오케스트라(조율자)입니다.

역할:
- 사용자의 요구사항을 분석하고 작업 계획을 수립합니다.
- Developer 에이전트와 Reviewer 에이전트에게 작업을 할당합니다.
- 전체 프로세스를 조율하고 최종 결과를 보고합니다.

응답 형식:
1. 요구사항 분석
2. 개발자에게 전달할 스펙
3. 리뷰어가 확인할 항목
4. 작업 흐름 계획

한국어로 응답하세요."""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        if self._executor:
            return await self._executor.run(self, task, context)

        # 실행기 없이 직접 응답 생성 (Mock)
        return AgentResult(
            answer=self._mock_response(task),
            agent_type=self.agent_type,
            steps=1,
            execution_time=0.1
        )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        if self._executor:
            async for chunk in self._executor.stream(self, task, context):
                yield chunk
        else:
            yield AgentStreamChunk(chunk_type=ChunkType.TEXT, content=self._mock_response(task))
            yield AgentStreamChunk(chunk_type=ChunkType.DONE)

    def _mock_response(self, task: str) -> str:
        return f"""## 요구사항 분석

**태스크**: {task}

### 1. 요구사항 분석
- "HelloWorld" 메시지를 출력하는 C 프로그램 작성
- ANSI C 표준 준수
- 적절한 주석 포함

### 2. 개발자 스펙
- stdio.h 헤더 사용
- printf() 함수로 출력
- main() 함수 반환값 0

### 3. 리뷰어 확인 항목
- 컴파일 가능 여부
- 출력 결과 정확성
- 코딩 컨벤션 준수

### 4. 작업 흐름
1. Developer Agent → 코드 작성
2. Reviewer Agent → 코드 리뷰
3. Orchestra Agent → 최종 보고서"""


class DeveloperAgent(BaseAgent):
    """
    개발자 에이전트

    코드 작성을 담당합니다.
    WebUI의 CodeAgent와 유사한 역할입니다.
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        super().__init__(
            name="Developer Agent",
            agent_type=AgentType.DEVELOPER,
            description="코드 작성 및 구현을 담당하는 개발자 에이전트",
            tools=["code_compile", "code_analyze"],
            model_id="mistral-nemo-12b"
        )
        self._executor = executor

    def _get_default_prompt(self) -> str:
        return """당신은 숙련된 소프트웨어 개발자입니다.

역할:
- 주어진 요구사항에 맞는 깔끔한 코드를 작성합니다.
- 적절한 주석을 포함합니다.
- 코드 설명과 사용 방법을 제공합니다.

코딩 규칙:
1. 코드는 ```언어명 ... ``` 형식으로 작성
2. 변수명/함수명은 명확하게
3. 에러 처리 고려
4. 한국어로 설명

도구 사용:
- code_compile: 코드 컴파일 확인
- code_analyze: 코드 품질 분석"""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        if self._executor:
            return await self._executor.run(self, task, context)

        return AgentResult(
            answer=self._mock_response(task),
            agent_type=self.agent_type,
            steps=1,
            execution_time=0.1
        )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        if self._executor:
            async for chunk in self._executor.stream(self, task, context):
                yield chunk
        else:
            yield AgentStreamChunk(chunk_type=ChunkType.TEXT, content=self._mock_response(task))
            yield AgentStreamChunk(chunk_type=ChunkType.DONE)

    def _mock_response(self, task: str) -> str:
        return """## 코드 작성 완료

### 설명
"HelloWorld"를 출력하는 간단한 C 프로그램입니다.
표준 입출력 헤더를 포함하고 printf 함수를 사용합니다.

### 코드

```c
/*
 * HelloWorld 프로그램
 *
 * 설명: 표준 출력으로 "HelloWorld" 메시지를 출력합니다.
 * 작성자: Developer Agent
 * 표준: ANSI C
 */

#include <stdio.h>

/*
 * 메인 함수
 * 프로그램의 진입점입니다.
 */
int main(void) {
    /* "HelloWorld" 메시지 출력 */
    printf("HelloWorld\\n");

    /* 정상 종료 */
    return 0;
}
```

### 컴파일 및 실행 방법

```bash
# 컴파일
gcc -o helloworld helloworld.c

# 실행
./helloworld
```

### 예상 출력
```
HelloWorld
```"""


class ReviewerAgent(BaseAgent):
    """
    리뷰어 에이전트

    코드 리뷰를 담당합니다.
    코드 품질, 보안, 성능을 검토합니다.
    """

    def __init__(self, executor: Optional[AgentExecutor] = None):
        super().__init__(
            name="Reviewer Agent",
            agent_type=AgentType.REVIEWER,
            description="코드 리뷰 및 품질 검증을 담당하는 리뷰어 에이전트",
            tools=["code_analyze"],
            model_id="nemotron-nano-9b"
        )
        self._executor = executor

    def _get_default_prompt(self) -> str:
        return """당신은 꼼꼼한 코드 리뷰어입니다.

역할:
- 제출된 코드를 철저히 검토합니다.
- 버그, 보안 취약점, 성능 이슈를 찾습니다.
- 코드 품질 향상을 위한 피드백을 제공합니다.

리뷰 기준:
1. 정확성 (1-5점): 요구사항 충족 여부
2. 가독성 (1-5점): 코드 스타일, 네이밍
3. 효율성 (1-5점): 성능, 리소스 사용
4. 보안성 (1-5점): 취약점 여부
5. 유지보수성 (1-5점): 확장성, 수정 용이성

응답 형식:
- 각 항목별 점수와 피드백
- 총점 및 종합 평가
- 개선 권장사항 (있는 경우)"""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        if self._executor:
            return await self._executor.run(self, task, context)

        return AgentResult(
            answer=self._mock_response(task),
            agent_type=self.agent_type,
            steps=1,
            execution_time=0.1
        )

    async def stream(
        self,
        task: str,
        context: AgentContext
    ) -> AsyncGenerator[AgentStreamChunk, None]:
        if self._executor:
            async for chunk in self._executor.stream(self, task, context):
                yield chunk
        else:
            yield AgentStreamChunk(chunk_type=ChunkType.TEXT, content=self._mock_response(task))
            yield AgentStreamChunk(chunk_type=ChunkType.DONE)

    def _mock_response(self, task: str) -> str:
        return """## 코드 리뷰 결과

### 1. 정확성 (5/5)
- 요구사항을 완벽히 충족합니다.
- "HelloWorld" 메시지가 정확히 출력됩니다.
- main 함수 반환값 0 준수

### 2. 가독성 (5/5)
- 코드가 간결하고 이해하기 쉽습니다.
- 주석이 적절히 포함되어 있습니다.
- 함수명과 구조가 명확합니다.

### 3. 효율성 (5/5)
- 단순한 프로그램으로 효율성 이슈 없음
- 불필요한 연산이나 메모리 사용 없음

### 4. 보안성 (5/5)
- 보안 취약점 없음
- 사용자 입력을 받지 않아 안전

### 5. 유지보수성 (5/5)
- 코드 구조가 표준적임
- 수정 및 확장이 용이함

---

### 총평
- **총점: 25/25 (우수)**
- 깔끔하고 표준적인 HelloWorld 프로그램입니다.
- 개선 권장사항 없음"""


# =============================================================================
# 8. 에이전트 레지스트리 (app/api/agents/registry.py 패턴)
# =============================================================================

class AgentRegistry:
    """
    에이전트 레지스트리 (Singleton)

    WebUI에서는 모든 에이전트를 중앙에서 관리합니다.
    Orchestrator는 레지스트리에서 적절한 에이전트를 선택합니다.
    """

    _instance: Optional['AgentRegistry'] = None

    def __init__(self):
        self._agents: Dict[AgentType, BaseAgent] = {}
        self._agent_classes: Dict[AgentType, Type[BaseAgent]] = {}

    @classmethod
    def get_instance(cls) -> 'AgentRegistry':
        """싱글톤 인스턴스 반환"""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_agents()
        return cls._instance

    def _register_default_agents(self):
        """기본 에이전트 등록"""
        self._agent_classes = {
            AgentType.ORCHESTRA: OrchestraAgent,
            AgentType.DEVELOPER: DeveloperAgent,
            AgentType.REVIEWER: ReviewerAgent,
        }
        logger.info(f"[AgentRegistry] {len(self._agent_classes)}개 에이전트 타입 등록됨")

    def register_class(
        self,
        agent_type: AgentType,
        agent_class: Type[BaseAgent]
    ) -> None:
        """에이전트 클래스 등록"""
        self._agent_classes[agent_type] = agent_class

    def get(self, agent_type: AgentType) -> BaseAgent:
        """에이전트 인스턴스 가져오기 (캐시됨)"""
        if agent_type not in self._agents:
            agent_class = self._agent_classes.get(agent_type)
            if agent_class is None:
                raise ValueError(f"등록되지 않은 에이전트 타입: {agent_type}")
            self._agents[agent_type] = agent_class()

        return self._agents[agent_type]

    def get_all_types(self) -> List[AgentType]:
        """등록된 모든 에이전트 타입 반환"""
        return list(self._agent_classes.keys())


def get_agent_registry() -> AgentRegistry:
    """전역 에이전트 레지스트리 반환"""
    return AgentRegistry.get_instance()


# =============================================================================
# 9. 오케스트레이터 (app/api/agents/orchestrator.py 패턴)
# =============================================================================

class AgentOrchestrator:
    """
    에이전트 오케스트레이터

    WebUI의 AgentOrchestrator와 동일한 패턴입니다.
    태스크를 분석하고 적절한 에이전트에게 라우팅합니다.

    주요 기능:
    - 태스크 분류 (classify_task)
    - 에이전트 실행 (execute)
    - 멀티 에이전트 워크플로우 (execute_workflow)
    """

    def __init__(
        self,
        llm_adapter: Optional[LLMAdapter] = None,
        agent_registry: Optional[AgentRegistry] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """
        오케스트레이터 초기화

        Args:
            llm_adapter: LLM 어댑터
            agent_registry: 에이전트 레지스트리
            tool_registry: 도구 레지스트리
        """
        self.llm_adapter = llm_adapter
        self.agent_registry = agent_registry or get_agent_registry()
        self.tool_registry = tool_registry or get_tool_registry()

        # 실행기 생성
        if llm_adapter:
            self.executor = AgentExecutor(llm_adapter, self.tool_registry)
        else:
            self.executor = None

        logger.info("[Orchestrator] 초기화 완료")

    def classify_task(self, task: str) -> AgentType:
        """
        태스크 분류

        키워드 기반으로 적절한 에이전트 타입을 결정합니다.
        WebUI에서는 LLM 기반 분류도 지원합니다.

        Args:
            task: 사용자 태스크

        Returns:
            적절한 에이전트 타입
        """
        task_lower = task.lower()

        # 코드 관련 키워드
        code_keywords = ["코드", "code", "프로그램", "함수", "구현", "작성", "개발"]
        if any(kw in task_lower for kw in code_keywords):
            return AgentType.DEVELOPER

        # 리뷰 관련 키워드
        review_keywords = ["리뷰", "review", "검토", "분석", "평가"]
        if any(kw in task_lower for kw in review_keywords):
            return AgentType.REVIEWER

        # 기본값: Orchestra
        return AgentType.ORCHESTRA

    async def execute(
        self,
        task: str,
        context: AgentContext,
        agent_type: Optional[AgentType] = None
    ) -> AgentResult:
        """
        단일 에이전트 실행

        Args:
            task: 사용자 태스크
            context: 실행 컨텍스트
            agent_type: 에이전트 타입 (None이면 자동 분류)

        Returns:
            실행 결과
        """
        # 에이전트 타입 결정
        if agent_type is None:
            agent_type = self.classify_task(task)

        logger.info(f"[Orchestrator] 에이전트 선택: {agent_type.value}")

        # 에이전트 가져오기
        agent = self.agent_registry.get(agent_type)

        # 실행기 주입
        if self.executor:
            agent._executor = self.executor

        # 실행
        return await agent.execute(task, context)

    async def execute_workflow(
        self,
        task: str,
        context: AgentContext
    ) -> Dict[str, AgentResult]:
        """
        멀티 에이전트 워크플로우 실행

        Orchestra → Developer → Reviewer 순으로 실행합니다.

        Args:
            task: 사용자 태스크
            context: 실행 컨텍스트

        Returns:
            각 에이전트별 실행 결과
        """
        results = {}

        print("\n" + "=" * 60)
        print("멀티 에이전트 워크플로우 시작")
        print("=" * 60)
        print(f"태스크: {task}")
        print("=" * 60 + "\n")

        # Step 1: Orchestra - 요구사항 분석
        print("[Step 1] Orchestra Agent - 요구사항 분석")
        print("-" * 40)
        orchestra_result = await self.execute(task, context, AgentType.ORCHESTRA)
        results["orchestra"] = orchestra_result
        print(orchestra_result.answer)
        print()

        # Step 2: Developer - 코드 작성
        print("[Step 2] Developer Agent - 코드 작성")
        print("-" * 40)
        dev_task = f"{task}\n\n추가 컨텍스트:\n{orchestra_result.answer}"
        dev_result = await self.execute(dev_task, context, AgentType.DEVELOPER)
        results["developer"] = dev_result
        print(dev_result.answer)
        print()

        # Step 3: Reviewer - 코드 리뷰
        print("[Step 3] Reviewer Agent - 코드 리뷰")
        print("-" * 40)
        review_task = f"다음 코드를 리뷰해주세요:\n\n{dev_result.answer}"
        review_result = await self.execute(review_task, context, AgentType.REVIEWER)
        results["reviewer"] = review_result
        print(review_result.answer)
        print()

        print("=" * 60)
        print("워크플로우 완료")
        print("=" * 60)

        return results


# =============================================================================
# 10. 메인 실행
# =============================================================================

async def main():
    """메인 함수"""
    print("""
+==============================================================+
|         WebUI Agent 구조 기반 샘플 - HelloWorld              |
|                                                              |
|  이 샘플은 HybridRAG KMS의 WebUI Agent 구조를 따릅니다:      |
|                                                              |
|  - BaseAgent: 에이전트 추상 기반 클래스                      |
|  - AgentExecutor: ReAct 루프 실행기                          |
|  - ToolRegistry: 도구 관리 (Singleton)                       |
|  - AgentRegistry: 에이전트 관리 (Singleton)                  |
|  - AgentOrchestrator: 태스크 라우팅 및 조율                  |
+==============================================================+
    """)

    # 컨텍스트 생성
    context = AgentContext(
        session_id="sample-session-001",
        user_id="sample-user",
        language="ko"
    )

    # 사용자 요청
    task = '"HelloWorld" 메시지를 출력하는 C 프로그램을 작성해주세요.'

    # 오케스트레이터 생성 (LLM 어댑터 없이 Mock 모드)
    orchestrator = AgentOrchestrator()

    # 워크플로우 실행
    results = await orchestrator.execute_workflow(task, context)

    # 결과 요약
    print("\n" + "=" * 60)
    print("실행 결과 요약")
    print("=" * 60)

    total_steps = sum(r.steps for r in results.values())
    total_time = sum(r.execution_time for r in results.values())

    print(f"• 총 단계: {total_steps}")
    print(f"• 총 실행 시간: {total_time:.2f}초")
    print(f"• 실행된 에이전트: {', '.join(results.keys())}")


async def main_with_llm():
    """실제 LLM을 사용하는 메인 함수"""
    print("\n[실제 LLM 모드] NVIDIA NIM 서버 연결")
    print("-" * 40)

    # LLM 어댑터 생성
    llm_adapter = LLMAdapter(
        api_url="http://localhost:12800/v1/chat/completions",
        model="nvidia/llama-3.1-nemotron-nano-8b-v1"
    )

    try:
        # 컨텍스트 생성
        context = AgentContext(
            session_id="sample-session-002",
            user_id="sample-user",
            language="ko"
        )

        # 오케스트레이터 생성
        orchestrator = AgentOrchestrator(llm_adapter=llm_adapter)

        # 단일 에이전트 실행
        task = '"HelloWorld" 메시지를 출력하는 C 프로그램을 작성해주세요.'
        result = await orchestrator.execute(task, context, AgentType.DEVELOPER)

        print("\n결과:")
        print(result.answer)

    except Exception as e:
        print(f"\n오류: {e}")
        print("\n[TIP] LLM 서버가 실행 중인지 확인하세요:")
        print("      http://localhost:12800/v1/chat/completions")

    finally:
        await llm_adapter.close()


# =============================================================================
# 실행
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--llm":
        # 실제 LLM 모드
        asyncio.run(main_with_llm())
    else:
        # Mock 모드 (기본)
        asyncio.run(main())
