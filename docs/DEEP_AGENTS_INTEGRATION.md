# Deep Agents 통합 아키텍처

## 1. 개요

이 문서는 LangChain의 Deep Agents 프레임워크를 HybridRAG KMS의 기존 WebUI Agent 시스템에 통합하는 아키텍처를 설계합니다.

### 1.1 목표

1. **점진적 마이그레이션**: 기존 시스템을 유지하면서 Deep Agents 기능 도입
2. **미들웨어 활용**: Deep Agents의 강력한 미들웨어 패턴 도입
3. **Context 관리 개선**: 자동 요약 및 파일 오프로드 기능 활용
4. **SubAgent 패턴**: 복잡한 작업의 효율적인 분리 처리

### 1.2 현재 아키텍처 비교

| 구분 | WebUI Agent | Deep Agents |
|------|-------------|-------------|
| 패턴 | Registry/Orchestrator | Middleware Stack |
| LLM 통합 | 직접 어댑터 | LangChain 기반 |
| Tool 관리 | ToolRegistry | 미들웨어 내장 |
| Context | AgentContext 직접 관리 | 자동 요약 (170K 토큰) |
| 병렬 처리 | DAG + ParallelExecutor | SubAgent 격리 |

---

## 2. 통합 아키텍처

### 2.1 하이브리드 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AgentOrchestrator                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Task Router                                │   │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │   │
│  │   │ Simple Task │    │Complex Task │    │ Deep Task   │      │   │
│  │   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘      │   │
│  └──────────┼──────────────────┼──────────────────┼─────────────┘   │
│             │                  │                  │                  │
│             ▼                  ▼                  ▼                  │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  WebUI Agent     │  │ Enterprise   │  │    Deep Agent        │   │
│  │  (기존 시스템)    │  │ Multi-Agent  │  │    Executor          │   │
│  │                  │  │ (DAG 기반)   │  │                      │   │
│  │  - RAGAgent      │  │              │  │  ┌─────────────────┐ │   │
│  │  - CodeAgent     │  │              │  │  │ Middleware Stack│ │   │
│  │  - VisionAgent   │  │              │  │  │ - TodoList      │ │   │
│  │  - IMSAgent      │  │              │  │  │ - Filesystem    │ │   │
│  │                  │  │              │  │  │ - SubAgent      │ │   │
│  └────────┬─────────┘  └──────┬───────┘  │  │ - RAG (Custom)  │ │   │
│           │                   │          │  └─────────────────┘ │   │
│           │                   │          └──────────┬───────────┘   │
│           │                   │                     │               │
│           ▼                   ▼                     ▼               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                      LLM Adapter Layer                        │   │
│  │   ┌────────────┐  ┌────────────┐  ┌────────────────────┐     │   │
│  │   │ Ollama     │  │ NVIDIA NIM │  │ LangChain ChatModel │     │   │
│  │   └────────────┘  └────────────┘  └────────────────────┘     │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 라우팅 전략

```python
class TaskComplexityRouter:
    """작업 복잡도에 따른 실행 경로 라우팅"""

    SIMPLE_PATTERNS = [
        r"^(what|how|why|where|when)\s",  # 단순 질문
        r"^(explain|describe|show)\s",
    ]

    COMPLEX_PATTERNS = [
        r"(analyze|compare|evaluate).*(and|with)",  # 비교 분석
        r"(step.by.step|detailed|comprehensive)",
    ]

    DEEP_PATTERNS = [
        r"(create|build|implement|develop).*(project|system|app)",  # 프로젝트 생성
        r"(refactor|migrate|redesign)",
        r"(multi.step|complex.workflow)",
    ]

    def route(self, task: str) -> ExecutionMode:
        task_lower = task.lower()

        # Check patterns
        if any(re.search(p, task_lower) for p in self.DEEP_PATTERNS):
            return ExecutionMode.DEEP_AGENT
        elif any(re.search(p, task_lower) for p in self.COMPLEX_PATTERNS):
            return ExecutionMode.ENTERPRISE_MULTI
        else:
            return ExecutionMode.WEBUI_SIMPLE
```

---

## 3. 구현 계획

### 3.1 Phase 1: Deep Agent Adapter 생성

Deep Agents를 기존 시스템에 연결하는 어댑터 레이어 구현

**파일**: `app/api/agents/adapters/deep_agent_adapter.py`

```python
"""
Deep Agents Adapter
기존 WebUI Agent 시스템과 Deep Agents를 연결하는 어댑터
"""
from typing import Optional, List, Dict, Any, AsyncGenerator
import logging

from deepagents import create_deep_agent
from deepagents.middleware import AgentMiddleware
from langchain_openai import ChatOpenAI

from ..types import AgentContext, AgentResult, AgentType
from ..base import BaseAgent

logger = logging.getLogger(__name__)


class DeepAgentAdapter(BaseAgent):
    """
    Deep Agents를 WebUI Agent 인터페이스로 래핑하는 어댑터

    기존 AgentOrchestrator에서 다른 Agent처럼 사용 가능
    """

    def __init__(
        self,
        name: str = "DeepAgent",
        agent_type: AgentType = AgentType.PLANNER,
        description: str = "Deep Agents 기반 복잡한 작업 처리 에이전트",
        llm: Optional[ChatOpenAI] = None,
        middleware: Optional[List[AgentMiddleware]] = None,
        system_prompt: Optional[str] = None
    ):
        super().__init__(
            name=name,
            agent_type=agent_type,
            description=description,
            system_prompt=system_prompt
        )

        self._llm = llm
        self._middleware = middleware or []
        self._deep_agent = None

    def _get_llm(self) -> ChatOpenAI:
        """LLM 인스턴스 반환 (Lazy initialization)"""
        if self._llm is None:
            # NVIDIA NIM 기본 설정
            self._llm = ChatOpenAI(
                model="nvidia/llama-3.1-nemotron-nano-8b-v1",
                base_url="http://localhost:12800/v1",
                api_key="not-needed",
                temperature=0.7,
                max_tokens=4096,
            )
        return self._llm

    def _get_deep_agent(self):
        """Deep Agent 인스턴스 반환 (Lazy initialization)"""
        if self._deep_agent is None:
            self._deep_agent = create_deep_agent(
                model=self._get_llm(),
                middleware=self._middleware,
                system_prompt=self.system_prompt,
            )
        return self._deep_agent

    async def execute(
        self,
        task: str,
        context: AgentContext
    ) -> AgentResult:
        """Deep Agent로 작업 실행"""
        import time
        from langchain_core.messages import HumanMessage

        start_time = time.time()

        try:
            agent = self._get_deep_agent()

            # Context를 메시지에 포함
            message_content = task
            if context.file_context:
                message_content = f"[첨부 파일]\n{context.file_context}\n\n{task}"

            result = await agent.ainvoke({
                "messages": [HumanMessage(content=message_content)]
            })

            # 결과 추출
            answer = result.get("messages", [])[-1].content if result.get("messages") else str(result)

            execution_time = time.time() - start_time

            return AgentResult(
                answer=answer,
                agent_type=self.agent_type,
                steps=1,
                execution_time=execution_time,
                success=True,
                metadata={"engine": "deep_agents"}
            )

        except Exception as e:
            logger.error(f"[DeepAgentAdapter] Execution failed: {e}")
            return AgentResult(
                answer=f"작업 처리 중 오류가 발생했습니다: {str(e)}",
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
    ) -> AsyncGenerator:
        """Deep Agent 스트리밍 실행"""
        from ..types import AgentStreamChunk

        yield AgentStreamChunk(chunk_type="thinking", content="Deep Agent 처리 중...")

        result = await self.execute(task, context)

        # 답변 스트리밍
        chunk_size = 50
        for i in range(0, len(result.answer), chunk_size):
            yield AgentStreamChunk(
                chunk_type="text",
                content=result.answer[i:i + chunk_size]
            )

        yield AgentStreamChunk(
            chunk_type="done",
            metadata={"execution_time": result.execution_time}
        )
```

### 3.2 Phase 2: Custom Middleware 구현

기존 Tool을 Deep Agents 미들웨어로 변환

**파일**: `app/api/agents/middleware/rag_middleware.py`

```python
"""
RAG Middleware for Deep Agents
기존 RAG 기능을 Deep Agents 미들웨어로 제공
"""
from typing import List, Optional
from deepagents.middleware import AgentMiddleware
from langchain_core.tools import tool


class RAGMiddleware(AgentMiddleware):
    """
    RAG (Retrieval-Augmented Generation) 미들웨어

    지식베이스 검색 도구를 Deep Agent에 주입합니다.
    """

    def __init__(
        self,
        neo4j_uri: str = "bolt://localhost:7687",
        neo4j_user: str = "neo4j",
        neo4j_password: str = "",
        embedding_url: str = "http://localhost:12801/v1"
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.embedding_url = embedding_url
        self._vector_store = None
        self._graph_store = None

    def _get_vector_store(self):
        """Vector Store 초기화"""
        if self._vector_store is None:
            # 기존 Neo4j Vector Store 연결
            from langchain_community.vectorstores import Neo4jVector
            from langchain_community.embeddings import OpenAIEmbeddings

            embeddings = OpenAIEmbeddings(
                model="nvidia/nv-embedqa-mistral-7b-v2",
                base_url=self.embedding_url,
                api_key="not-needed",
            )

            self._vector_store = Neo4jVector.from_existing_index(
                embedding=embeddings,
                url=self.neo4j_uri,
                username=self.neo4j_user,
                password=self.neo4j_password,
                index_name="document_embeddings",
            )
        return self._vector_store

    def get_tools(self) -> List:
        """미들웨어가 제공하는 도구 목록"""

        @tool
        def vector_search(query: str, top_k: int = 5) -> str:
            """지식베이스에서 관련 문서를 벡터 검색합니다.

            Args:
                query: 검색할 질문 또는 키워드
                top_k: 반환할 결과 수 (기본값: 5)

            Returns:
                관련 문서 내용
            """
            try:
                store = self._get_vector_store()
                results = store.similarity_search(query, k=top_k)

                if not results:
                    return "관련 문서를 찾을 수 없습니다."

                output = []
                for i, doc in enumerate(results, 1):
                    source = doc.metadata.get("source", "unknown")
                    output.append(f"[{i}] {source}\n{doc.page_content[:500]}...")

                return "\n\n".join(output)

            except Exception as e:
                return f"검색 중 오류 발생: {str(e)}"

        @tool
        def hybrid_search(query: str, strategy: str = "auto") -> str:
            """벡터 검색과 그래프 검색을 결합한 하이브리드 검색입니다.

            Args:
                query: 검색할 질문
                strategy: 검색 전략 (auto, vector, graph, hybrid)

            Returns:
                검색 결과
            """
            # 기존 hybrid search 로직 활용
            return vector_search(query, top_k=5)

        return [vector_search, hybrid_search]

    def get_system_prompt_addition(self) -> str:
        """시스템 프롬프트에 추가할 RAG 지침"""
        return """
## RAG 도구 사용 지침

당신은 HybridRAG KMS의 지식베이스에 접근할 수 있습니다.

사용 가능한 도구:
1. `vector_search`: 의미적 유사성 기반 문서 검색
2. `hybrid_search`: 벡터 + 그래프 결합 검색

중요 지침:
- 사용자 질문에 답하기 전에 **반드시** vector_search로 관련 문서를 검색하세요.
- 검색 결과가 없으면 "지식베이스에서 관련 정보를 찾을 수 없습니다"라고 답하세요.
- 검색 결과를 인용할 때 출처를 명시하세요.
- 일반 지식이 아닌 검색된 정보만 사용하세요.
"""
```

### 3.3 Phase 3: Orchestrator 확장

AgentOrchestrator에 Deep Agent 지원 추가

**파일 수정**: `app/api/agents/orchestrator.py`

```python
# orchestrator.py에 추가할 코드

from enum import Enum

class ExecutionMode(Enum):
    """실행 모드"""
    WEBUI_SIMPLE = "webui_simple"      # 기존 단일 Agent
    ENTERPRISE_MULTI = "enterprise"     # DAG 기반 병렬 실행
    DEEP_AGENT = "deep_agent"           # Deep Agents 활용


class AgentOrchestrator:
    # ... 기존 코드 ...

    def __init__(self, ...):
        # 기존 초기화
        self.agent_registry = agent_registry or get_agent_registry()
        self.executor = executor or get_executor()

        # Deep Agent 지원 추가
        self._deep_agent_adapter = None
        self._task_router = TaskComplexityRouter()

    @property
    def deep_agent(self):
        """Deep Agent 인스턴스 (Lazy initialization)"""
        if self._deep_agent_adapter is None:
            from .adapters.deep_agent_adapter import DeepAgentAdapter
            from .middleware.rag_middleware import RAGMiddleware
            from deepagents.middleware import TodoListMiddleware, FilesystemMiddleware

            self._deep_agent_adapter = DeepAgentAdapter(
                middleware=[
                    RAGMiddleware(),
                    TodoListMiddleware(),
                    FilesystemMiddleware(allowed_paths=["/app/data"]),
                ]
            )
        return self._deep_agent_adapter

    async def execute_smart(
        self,
        request: AgentRequest,
        user_id: Optional[str] = None
    ) -> AgentResponse:
        """
        스마트 실행: 작업 복잡도에 따라 최적의 실행 경로 선택
        """
        # 실행 모드 결정
        mode = self._task_router.route(request.task)

        logger.info(f"[Orchestrator] Smart routing: {mode.value}")

        if mode == ExecutionMode.DEEP_AGENT:
            return await self._execute_with_deep_agent(request, user_id)
        elif mode == ExecutionMode.ENTERPRISE_MULTI:
            enterprise_request = EnterpriseAgentRequest(**request.dict())
            return await self.execute_enterprise(enterprise_request, user_id)
        else:
            return await self.execute(request, user_id)

    async def _execute_with_deep_agent(
        self,
        request: AgentRequest,
        user_id: Optional[str]
    ) -> AgentResponse:
        """Deep Agent로 작업 실행"""
        context = AgentContext(
            session_id=request.session_id or "",
            user_id=user_id,
            language=request.language,
            max_steps=request.max_steps,
            file_context=request.file_context,
        )

        result = await self.deep_agent.execute(request.task, context)

        return AgentResponse(
            answer=result.answer,
            agent_type=result.agent_type,
            session_id=context.session_id,
            steps=result.steps,
            execution_time=result.execution_time,
            success=result.success,
            error=result.error
        )
```

### 3.4 Phase 4: API 엔드포인트 추가

**파일**: `app/api/routers/agents.py`

```python
# agents.py에 추가할 엔드포인트

@router.post("/deep/execute", response_model=AgentResponse)
async def execute_deep_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_user),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """
    Deep Agent로 복잡한 작업 실행

    Deep Agents의 미들웨어 스택을 활용하여 복잡한 작업을 처리합니다.
    - 자동 작업 분해 (TodoList)
    - 파일 시스템 접근
    - SubAgent 위임
    """
    return await orchestrator._execute_with_deep_agent(
        request,
        user_id=str(current_user.id)
    )


@router.post("/smart/execute", response_model=AgentResponse)
async def execute_smart(
    request: AgentRequest,
    current_user: User = Depends(get_current_user),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """
    스마트 실행: 작업 복잡도에 따라 최적의 실행 경로 자동 선택

    - 단순 질문 → WebUI Agent
    - 복잡한 분석 → Enterprise Multi-Agent
    - 프로젝트 생성 → Deep Agent
    """
    return await orchestrator.execute_smart(
        request,
        user_id=str(current_user.id)
    )


@router.post("/deep/stream")
async def stream_deep_agent(
    request: AgentRequest,
    current_user: User = Depends(get_current_user),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Deep Agent 스트리밍 실행"""
    async def generate():
        context = AgentContext(
            session_id=request.session_id or "",
            user_id=str(current_user.id),
            language=request.language,
            max_steps=request.max_steps,
            file_context=request.file_context,
        )

        async for chunk in orchestrator.deep_agent.stream(request.task, context):
            yield f"data: {json.dumps(chunk.dict())}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 4. 마이그레이션 가이드

### 4.1 기존 Tool → Deep Agents Middleware 변환

```python
# 변환 전 (기존 Tool)
class VectorSearchTool(BaseTool):
    name = "vector_search"
    description = "Search documents"

    async def execute(self, context, query, top_k=5):
        # 검색 로직
        pass

# 변환 후 (Deep Agents Middleware)
class VectorSearchMiddleware(AgentMiddleware):
    def get_tools(self):
        @tool
        def vector_search(query: str, top_k: int = 5) -> str:
            """Search documents"""
            # 동일한 검색 로직
            pass
        return [vector_search]
```

### 4.2 기존 Agent → DeepAgentAdapter 변환

```python
# 변환 전 (기존 Agent)
class RAGAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="RAGAgent",
            agent_type=AgentType.RAG,
            tools=["vector_search", "document_read"]
        )

# 변환 후 (Deep Agent)
rag_deep_agent = DeepAgentAdapter(
    name="RAGDeepAgent",
    agent_type=AgentType.RAG,
    middleware=[
        RAGMiddleware(),
        DocumentReadMiddleware(),
    ],
    system_prompt="You are a RAG specialist..."
)
```

---

## 5. 장점 및 고려사항

### 5.1 Deep Agents 도입의 장점

1. **자동 Context 관리**
   - 170K 토큰 초과 시 자동 요약
   - 대용량 결과 파일 오프로드

2. **미들웨어 재사용성**
   - 도구를 미들웨어로 패키징하여 재사용
   - 다양한 Agent에서 동일 미들웨어 활용

3. **SubAgent 패턴**
   - 복잡한 작업을 전문화된 SubAgent로 분리
   - Context 격리로 효율적인 처리

4. **LangChain 생태계**
   - 풍부한 통합 옵션
   - 커뮤니티 지원

### 5.2 고려사항

1. **의존성 추가**
   - `deepagents`, `langchain-openai` 패키지 필요
   - LangChain 버전 호환성 관리

2. **성능 오버헤드**
   - 미들웨어 스택 처리로 약간의 오버헤드
   - 단순 작업에는 기존 시스템이 더 효율적

3. **학습 곡선**
   - 팀원들의 Deep Agents 학습 필요
   - 미들웨어 패턴 이해 필요

---

## 6. 다음 단계

1. **Phase 1 구현** (1주차)
   - DeepAgentAdapter 구현
   - 기본 테스트 작성

2. **Phase 2 구현** (2주차)
   - RAGMiddleware 구현
   - 기존 Tool 마이그레이션

3. **Phase 3 구현** (3주차)
   - Orchestrator 확장
   - 라우팅 로직 구현

4. **Phase 4 구현** (4주차)
   - API 엔드포인트 추가
   - 프론트엔드 연동

5. **테스트 및 최적화** (5주차)
   - 성능 테스트
   - 문서화 완료

---

## 참고 자료

- [Deep Agents GitHub](https://github.com/langchain-ai/deepagents)
- [LangChain Documentation](https://python.langchain.com/)
- [NVIDIA NIM Documentation](https://docs.nvidia.com/nim/)
