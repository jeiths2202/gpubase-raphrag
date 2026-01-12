# WebUI Agent 구조 가이드

## 개요

이 문서는 HybridRAG KMS 프로젝트의 **WebUI Agent 구조**를 설명합니다.
WebUI에서는 자체 구현된 AI Agent 프레임워크를 사용하며, OpenCode(CLI 도구)와는 별개입니다.

---

## 목차

1. [WebUI vs OpenCode](#1-webui-vs-opencode)
2. [아키텍처 개요](#2-아키텍처-개요)
3. [핵심 컴포넌트](#3-핵심-컴포넌트)
4. [디렉토리 구조](#4-디렉토리-구조)
5. [에이전트 구현 패턴](#5-에이전트-구현-패턴)
6. [도구(Tool) 시스템](#6-도구tool-시스템)
7. [오케스트레이터](#7-오케스트레이터)
8. [API 엔드포인트](#8-api-엔드포인트)
9. [샘플 코드 실행](#9-샘플-코드-실행)

---

## 1. WebUI vs OpenCode

### 비교표

| 항목 | WebUI Agent | OpenCode |
|------|-------------|----------|
| **용도** | 사용자 서비스 (웹) | 개발자 도구 (CLI) |
| **구현** | 자체 구현 (FastAPI) | 외부 오픈소스 |
| **위치** | `app/api/agents/` | `.opencode/` |
| **LLM** | NVIDIA NIM (Nemotron, Mistral) | Ollama, OpenAI |
| **실행** | HTTP API | 터미널 명령 |

### WebUI Agent 시스템

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Frontend                               │
│                  (http://localhost:3000)                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP/SSE
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                              │
│               /api/v1/agents/execute                             │
│               /api/v1/agents/stream                              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   AgentOrchestrator                              │
│                                                                  │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │   RAG   │  │   IMS   │  │  Code   │  │ Vision  │   ...      │
│  │  Agent  │  │  Agent  │  │  Agent  │  │  Agent  │            │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘            │
│       └────────────┼────────────┼────────────┘                  │
│                    ▼            ▼                               │
│              AgentExecutor (ReAct Loop)                         │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   NVIDIA NIM Containers                          │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Nemotron Nano   │  │ NeMo Embeddings │  │ Mistral Code    │ │
│  │ (Port 12800)    │  │ (Port 12801)    │  │ (Port 12802)    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 아키텍처 개요

### 핵심 설계 패턴

| 패턴 | 적용 위치 | 목적 |
|------|-----------|------|
| **Template Method** | `BaseAgent` | 공통 로직 캡슐화, 확장 포인트 제공 |
| **Singleton** | `ToolRegistry`, `AgentRegistry` | 전역 상태 관리 |
| **Strategy** | 각 Agent 클래스 | 역할별 다른 행동 방식 |
| **Facade** | `AgentOrchestrator` | 복잡한 상호작용 단순화 |
| **ReAct** | `AgentExecutor` | Reasoning + Acting 루프 |

### 실행 흐름

```
사용자 요청
    │
    ▼
┌─────────────────────┐
│  AgentOrchestrator  │ ← 태스크 분류 (키워드/LLM)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   AgentRegistry     │ ← 적절한 에이전트 선택
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   AgentExecutor     │ ← ReAct 루프 실행
│                     │
│  ┌───────────────┐  │
│  │ 1. LLM 호출   │  │
│  └───────┬───────┘  │
│          │          │
│  ┌───────▼───────┐  │
│  │ 2. 도구 호출? │──┼──→ ToolRegistry → Tool 실행
│  └───────┬───────┘  │
│          │          │
│  ┌───────▼───────┐  │
│  │ 3. 최종 응답  │  │
│  └───────────────┘  │
└─────────────────────┘
```

---

## 3. 핵심 컴포넌트

### 3.1 타입 정의 (`types.py`)

```python
class AgentType(str, Enum):
    """에이전트 타입"""
    RAG = "rag"
    IMS = "ims"
    VISION = "vision"
    CODE = "code"
    PLANNER = "planner"
    ENHANCEMENT_ANALYST = "enhancement_analyst"
    ENHANCEMENT_ARCHITECT = "enhancement_architect"
    ENHANCEMENT_CODER = "enhancement_coder"
    ENHANCEMENT_QA = "enhancement_qa"


@dataclass
class AgentContext:
    """실행 컨텍스트"""
    session_id: str
    user_id: str
    language: str = "ko"
    conversation_history: List[Dict] = field(default_factory=list)
    file_context: Optional[str] = None  # 첨부 파일 내용
    url_context: Optional[str] = None   # URL 콘텐츠


@dataclass
class AgentResult:
    """실행 결과"""
    answer: str
    agent_type: AgentType
    steps: int
    tool_calls: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    sources: List[Dict] = field(default_factory=list)
    execution_time: float = 0.0
    success: bool = True
    error: Optional[str] = None
```

### 3.2 기본 에이전트 (`base.py`)

```python
class BaseAgent(ABC):
    """모든 에이전트의 기반 클래스"""

    def __init__(
        self,
        name: str,
        agent_type: AgentType,
        description: str,
        tools: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None
    ):
        self.name = name
        self.agent_type = agent_type
        self.description = description
        self.tools = tools or []
        self._system_prompt = system_prompt
        self.model_id = model_id

    @property
    def system_prompt(self) -> str:
        """시스템 프롬프트"""
        if self._system_prompt:
            return self._system_prompt
        return self._get_default_prompt()

    @abstractmethod
    def _get_default_prompt(self) -> str:
        """기본 프롬프트 (하위 클래스 구현)"""
        pass

    @abstractmethod
    async def execute(self, task: str, context: AgentContext) -> AgentResult:
        """태스크 실행"""
        pass

    @abstractmethod
    async def stream(self, task: str, context: AgentContext) -> AsyncGenerator:
        """스트리밍 실행"""
        pass
```

### 3.3 에이전트 실행기 (`executor.py`)

```python
class AgentExecutor:
    """ReAct 루프 실행기"""

    def __init__(
        self,
        llm_adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        max_iterations: int = 10
    ):
        self.llm_adapter = llm_adapter
        self.tool_registry = tool_registry
        self.max_iterations = max_iterations

    async def run(
        self,
        agent: BaseAgent,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """
        ReAct 루프 실행

        1. 시스템 프롬프트 + 태스크로 LLM 호출
        2. 도구 호출 요청 시 도구 실행
        3. 도구 결과를 LLM에 전달
        4. 최종 응답까지 반복
        """
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": task}
        ]

        tool_definitions = self.tool_registry.get_definitions(agent.tools)

        for step in range(self.max_iterations):
            response = await self.llm_adapter.generate(
                messages=messages,
                tools=tool_definitions
            )

            if response.get("tool_calls"):
                # 도구 실행
                for tool_call in response["tool_calls"]:
                    result = await self._execute_tool(tool_call, context)
                    messages.append({"role": "tool", "content": result})
            else:
                # 최종 응답
                return AgentResult(
                    answer=response["content"],
                    agent_type=agent.agent_type,
                    steps=step + 1
                )
```

---

## 4. 디렉토리 구조

```
app/api/agents/
├── __init__.py              # 모듈 익스포트
├── base.py                  # BaseAgent 추상 클래스
├── types.py                 # 타입 정의 (AgentType, AgentResult 등)
├── registry.py              # ToolRegistry, AgentRegistry
├── orchestrator.py          # AgentOrchestrator
├── executor.py              # AgentExecutor (ReAct 루프)
├── evaluator.py             # 결과 평가
├── parallel_executor.py     # 병렬 실행
│
├── agents/                  # 구체적인 에이전트 구현
│   ├── rag_agent.py
│   ├── ims_agent.py
│   ├── code_agent.py
│   ├── vision_agent.py
│   ├── planner_agent.py
│   ├── enhancement_analyst_agent.py
│   ├── enhancement_architect_agent.py
│   ├── enhancement_coder_agent.py
│   └── enhancement_qa_agent.py
│
├── tools/                   # 도구 구현
│   ├── base.py              # BaseTool 추상 클래스
│   ├── vector_search.py
│   ├── graph_query.py
│   ├── ims_search.py
│   ├── document_read.py
│   ├── web_fetch.py
│   └── safe_bash.py
│
└── prompts/                 # 시스템 프롬프트 파일
    ├── rag_agent.txt
    ├── code_agent.txt
    └── ...
```

---

## 5. 에이전트 구현 패턴

### 새 에이전트 추가 방법

```python
# app/api/agents/agents/my_agent.py

from ..base import BaseAgent
from ..types import AgentType, AgentContext, AgentResult
from ..executor import AgentExecutor, get_executor

class MyAgent(BaseAgent):
    """커스텀 에이전트"""

    def __init__(self, executor: Optional[AgentExecutor] = None):
        super().__init__(
            name="My Agent",
            agent_type=AgentType.MY_TYPE,  # types.py에 추가 필요
            description="커스텀 에이전트 설명",
            tools=["tool1", "tool2"],      # 사용할 도구
            model_id="nemotron-nano-9b"    # 사용할 LLM
        )
        self._executor = executor

    @property
    def executor(self) -> AgentExecutor:
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    def _get_default_prompt(self) -> str:
        return """당신은 [역할]입니다.

역할:
- ...

도구 사용:
- tool1: 설명
- tool2: 설명

응답 형식:
- ..."""

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        return await self.executor.run(self, task, context)

    async def stream(
        self,
        task: str,
        context: AgentContext
    ):
        async for chunk in self.executor.stream(self, task, context):
            yield chunk
```

### 레지스트리에 등록

```python
# app/api/agents/registry.py

def _register_default_agents(self):
    from .agents import MyAgent

    self._agent_classes = {
        # ... 기존 에이전트 ...
        AgentType.MY_TYPE: MyAgent,
    }
```

---

## 6. 도구(Tool) 시스템

### 도구 구현 패턴

```python
# app/api/agents/tools/my_tool.py

from .base import BaseTool

class MyTool(BaseTool):
    """커스텀 도구"""

    def __init__(self):
        super().__init__(
            name="my_tool",
            description="도구 설명"
        )

    async def execute(
        self,
        arguments: Dict[str, Any],
        context: AgentContext
    ) -> Dict[str, Any]:
        """도구 실행 로직"""
        param = arguments.get("param")

        # 실행 로직
        result = do_something(param)

        return {
            "success": True,
            "output": result
        }

    def _get_parameters(self) -> Dict[str, Any]:
        """LLM Function Calling용 파라미터 스키마"""
        return {
            "type": "object",
            "properties": {
                "param": {
                    "type": "string",
                    "description": "파라미터 설명"
                }
            },
            "required": ["param"]
        }
```

### 등록된 도구 목록

| 도구 | 파일 | 용도 |
|------|------|------|
| `vector_search` | `vector_search.py` | 벡터 유사도 검색 |
| `graph_query` | `graph_query.py` | Neo4j 그래프 쿼리 |
| `ims_search` | `ims_search.py` | IMS 이슈 검색 |
| `document_read` | `document_read.py` | 문서 읽기 |
| `web_fetch` | `web_fetch.py` | 웹 콘텐츠 가져오기 |
| `bash` | `safe_bash.py` | 안전한 셸 명령 실행 |

---

## 7. 오케스트레이터

### AgentOrchestrator 주요 기능

```python
class AgentOrchestrator:
    """에이전트 조율자"""

    async def execute(
        self,
        request: AgentRequest,
        user_id: str
    ) -> AgentResponse:
        """단일 에이전트 실행"""
        # 1. 태스크 분류
        agent_type = await self.classify_task(request.task)

        # 2. 에이전트 가져오기
        agent = self.agent_registry.get(agent_type)

        # 3. 실행
        result = await self.executor.run(agent, request.task, context)

        return AgentResponse(...)

    async def classify_task(self, task: str) -> AgentType:
        """태스크 분류 (키워드 기반)"""
        # 코드 관련 키워드
        if any(kw in task for kw in ["코드", "code", "함수"]):
            return AgentType.CODE

        # IMS 관련 키워드
        if any(kw in task for kw in ["이슈", "issue", "버그"]):
            return AgentType.IMS

        # 기본값
        return AgentType.RAG

    async def execute_enterprise(
        self,
        request: EnterpriseAgentRequest,
        user_id: str
    ) -> EnterpriseAgentResponse:
        """멀티 에이전트 오케스트레이션"""
        # DAG 기반 태스크 분해
        # 병렬 에이전트 실행
        # 결과 평가 및 재시도
        # 결과 합성
        pass
```

### 에이전트별 도구 매핑

```python
# registry.py

AGENT_TOOLS = {
    AgentType.RAG: ["vector_search", "graph_query", "document_read"],
    AgentType.IMS: ["ims_search", "web_fetch", "vector_search"],
    AgentType.CODE: ["document_read", "bash", "vector_search"],
    AgentType.VISION: ["document_read", "vector_search"],
    AgentType.PLANNER: ["vector_search", "graph_query", "ims_search"],
}
```

---

## 8. API 엔드포인트

### 라우터 (`routers/agents.py`)

| 엔드포인트 | 메서드 | 설명 |
|------------|--------|------|
| `/api/v1/agents/execute` | POST | 단일 에이전트 실행 |
| `/api/v1/agents/stream` | POST | SSE 스트리밍 실행 |
| `/api/v1/agents/enterprise/execute` | POST | 멀티 에이전트 실행 |
| `/api/v1/agents/enterprise/stream` | POST | 멀티 에이전트 스트리밍 |
| `/api/v1/agents/types` | GET | 등록된 에이전트 목록 |
| `/api/v1/agents/tools` | GET | 등록된 도구 목록 |
| `/api/v1/agents/classify` | POST | 태스크 분류 |

### 요청/응답 예시

```bash
# 단일 에이전트 실행
curl -X POST http://localhost:9000/api/v1/agents/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "HelloWorld를 출력하는 C 코드를 작성해주세요",
    "agent_type": "code",
    "language": "ko"
  }'

# 응답
{
  "answer": "```c\n#include <stdio.h>\nint main() {...}\n```",
  "agent_type": "code",
  "session_id": "abc123",
  "steps": 2,
  "sources": [],
  "execution_time": 3.5,
  "success": true
}
```

---

## 9. 샘플 코드 실행

### 파일 목록

| 파일 | 설명 |
|------|------|
| `webui_agent_sample.py` | WebUI 구조 기반 샘플 (이 문서) |
| `ai_agent_sample.py` | 독립 실행형 샘플 (이전 버전) |

### 실행 방법

```bash
# Mock 모드 (LLM 서버 불필요)
python samples/webui_agent_sample.py

# 실제 LLM 모드 (NVIDIA NIM 필요)
python samples/webui_agent_sample.py --llm
```

### 예상 출력

```
╔══════════════════════════════════════════════════════════════╗
║         WebUI Agent 구조 기반 샘플 - HelloWorld              ║
╚══════════════════════════════════════════════════════════════╝

============================================================
멀티 에이전트 워크플로우 시작
============================================================
태스크: "HelloWorld" 메시지를 출력하는 C 프로그램을 작성해주세요.
============================================================

[Step 1] Orchestra Agent - 요구사항 분석
----------------------------------------
## 요구사항 분석
...

[Step 2] Developer Agent - 코드 작성
----------------------------------------
## 코드 작성 완료
```c
#include <stdio.h>
int main(void) {
    printf("HelloWorld\n");
    return 0;
}
```
...

[Step 3] Reviewer Agent - 코드 리뷰
----------------------------------------
## 코드 리뷰 결과
### 1. 정확성 (5/5)
...

============================================================
워크플로우 완료
============================================================
```

---

## 부록

### A. 관련 파일

| 파일 | 설명 |
|------|------|
| `app/api/agents/` | 에이전트 프레임워크 전체 |
| `app/api/routers/agents.py` | API 라우터 |
| `app/api/adapters/` | LLM 어댑터 |
| `.opencode/` | OpenCode CLI 설정 (별개) |

### B. LLM 포트

| 포트 | 서비스 | 용도 |
|------|--------|------|
| 12800 | Nemotron Nano 9B | RAG, 일반 쿼리 |
| 12801 | NeMo Embeddings | 벡터 임베딩 |
| 12802 | Mistral NeMo 12B | 코드 생성 |

### C. 참고 문서

- `CLAUDE.md`: 프로젝트 가이드
- `app/api/agents/README.md`: 에이전트 상세 문서

---

*이 문서는 HybridRAG KMS 프로젝트의 WebUI Agent 구조를 설명합니다.*
