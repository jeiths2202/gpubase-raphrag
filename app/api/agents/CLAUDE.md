# Agents CLAUDE.md

AI Agent 시스템 및 Deep Agents 구현 가이드입니다.

## Directory Structure

```
app/api/agents/
├── orchestrator.py           # Agent routing & execution
├── parallel_executor.py      # Multi-agent parallel tasks
├── executor.py               # Individual agent execution
├── evaluator.py              # Result evaluation & synthesis
├── intent.py                 # Intent classification
├── dag.py                    # Task DAG builder
├── base.py                   # BaseAgent abstract class
├── types.py                  # AgentContext, AgentResult, AgentRequest
├── permissions.py            # Agent permissions
├── registry.py               # Agent registry
├── agents/                   # Specialized agents (9 agents)
│   ├── rag_agent.py
│   ├── ims_agent.py
│   ├── code_agent.py
│   ├── vision_agent.py
│   ├── planner_agent.py
│   ├── enhancement_analyst_agent.py
│   ├── enhancement_architect_agent.py
│   ├── enhancement_coder_agent.py
│   └── enhancement_qa_agent.py
├── middleware/               # Agent tools providers
│   ├── rag_tools.py          # vector_search, graph_query
│   ├── ims_middleware.py     # ims_search
│   ├── code_middleware.py    # code_generation, code_execution
│   ├── vision_middleware.py  # image_analysis
│   └── planner_middleware.py # task_decomposition
├── tools/                    # Tool implementations
│   ├── vector_search.py
│   ├── ims_search.py
│   ├── document_read.py
│   ├── bash.py
│   └── base.py
└── adapters/                 # Deep Agent integration
    ├── deep_agent_adapter.py # DeepAgentAdapter class
    ├── integration.py        # Registration & lifecycle
    ├── ollama_adapter.py     # Ollama LLM adapter
    └── __init__.py
```

## Agent System Overview

| Agent | 역할 | 파일 |
|-------|------|------|
| RAG Agent | 지식 기반 질의응답 | `agents/rag_agent.py` |
| IMS Agent | 이슈 관리 시스템 검색 | `agents/ims_agent.py` |
| Code Agent | 코드 분석/생성 | `agents/code_agent.py` |
| Vision Agent | 이미지/차트 분석 | `agents/vision_agent.py` |
| Planner Agent | 작업 계획 및 분해 | `agents/planner_agent.py` |
| Enhancement Analyst | 기능 개선 분석 | `agents/enhancement_analyst_agent.py` |
| Enhancement Architect | 아키텍처 설계 | `agents/enhancement_architect_agent.py` |
| Enhancement Coder | 코드 구현 | `agents/enhancement_coder_agent.py` |
| Enhancement QA | 품질 검증 | `agents/enhancement_qa_agent.py` |

## Execution Flow

### Single Agent
```
AgentRequest
    ↓
Orchestrator.execute()
    ↓
IntentClassifier → AgentType 결정
    ↓
Registry.get(agent_type) → Agent instance
    ↓
Agent.execute(task, context)
    ↓
AgentResult
```

### Multi-Agent (Enterprise)
```
EnterpriseAgentRequest
    ↓
Orchestrator.execute_enterprise()
    ↓
DAGBuilder.build_dag() → Task decomposition
    ↓
ParallelExecutor.execute_dag()
    ↓
For each task: Agent.execute() with timeout
    ↓
Evaluator.synthesize() → Combined result
    ↓
EnterpriseAgentResult
```

---

## Deep Agents Implementation

### Overview
Deep Agents는 LangGraph 기반의 AI 에이전트 프레임워크로, 기존 에이전트 시스템과 통합되어 tool calling 기능을 제공합니다.

### Architecture
```
adapters/
├── deep_agent_adapter.py    # DeepAgentAdapter (BaseAgent 구현)
├── integration.py           # 등록/활성화 관리
├── ollama_adapter.py        # Ollama LLM 통합
└── __init__.py              # Public API exports
```

### DeepAgentAdapter (`deep_agent_adapter.py`)

`BaseAgent` 인터페이스를 구현하여 기존 시스템과 호환됩니다.

**Factory 함수들:**
- `create_rag_deep_agent()` - vector_search, graph_query 도구
- `create_ims_deep_agent()` - IMS 이슈 검색 도구
- `create_vision_deep_agent()` - 이미지 분석 도구
- `create_code_deep_agent()` - 코드 생성/실행 도구
- `create_planner_deep_agent()` - 작업 분해/계획 도구

### Integration API (`integration.py`)

```python
from app.api.agents.adapters import (
    register_deep_agent,      # 특정 에이전트 등록
    enable_deep_agents,       # 복수 에이전트 활성화
    get_deep_agent,           # 에이전트 인스턴스 획득
    is_deep_agent_enabled,    # 활성화 여부 확인
    auto_register_deep_agents # 환경변수 기반 자동 등록
)
```

### Deep Agent Execution Flow

```
Request (use_deep_agent=true)
    ↓
Orchestrator.execute()
    ↓
get_deep_agent(agent_type) → DeepAgentAdapter
    ↓
DeepAgentAdapter.execute()
    ↓
_create_deep_agent() [Lazy initialization]
    ↓
agent.ainvoke(messages, config={recursion_limit: 25})
    ↓
Result extraction & return
```

### Environment Variables

```bash
# Deep Agent 설정
ENABLE_DEEP_AGENT=true              # 전역 활성화 플래그
DEEP_AGENT_TYPES=rag,planner        # 활성화할 에이전트 타입 (쉼표 구분)

# LLM 설정 (Deep Agent용)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

### Safety Mechanisms

| 메커니즘 | 값 | 설명 |
|----------|-----|------|
| Recursion Limit | 25 | 무한 루프 방지 |
| Timeout | 300s | 작업당 최대 실행 시간 |
| Fallback | Auto | Deep Agent 실패 시 일반 에이전트로 전환 |

### Tool Integration (Middleware)

| Middleware | 도구 | 파일 |
|------------|------|------|
| RAG | vector_search, graph_query | `middleware/rag_tools.py` |
| IMS | ims_search (status, priority, product 필터) | `middleware/ims_middleware.py` |
| Vision | image_analysis | `middleware/vision_middleware.py` |
| Code | code_generation, code_execution | `middleware/code_middleware.py` |
| Planner | task_decomposition | `middleware/planner_middleware.py` |

### API Usage

```python
# Request with Deep Agent
POST /api/v1/agent/stream
{
    "task": "검색 쿼리",
    "agent_type": "rag",
    "use_deep_agent": true,    # Deep Agent 사용 여부
    "stream": true
}

# Enterprise Multi-Agent
POST /api/v1/enterprise/stream
{
    "task": "복잡한 작업",
    "use_deep_agent": true,    # 모든 하위 에이전트에 적용
    "parallel": true
}
```

### Current Status

- **RAG Agent**: Deep Agent 사용 (권장)
- **IMS/Vision/Code/Planner**: 일반 에이전트 사용 (성능 이유)
  - Ollama의 tool calling이 복잡한 에이전트에서 느림
  - RAG는 단순한 도구 구조로 Deep Agent에 적합

---

## Long-term Memory

### Overview
Deep Agents는 `CompositeBackend`를 통해 세션 간 영구 메모리를 지원합니다.
작업 파일은 임시로 유지되고, 중요한 데이터는 세션 간에 유지됩니다.

### Architecture
```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

agent = create_deep_agent(
    backend=CompositeBackend(
        default=StateBackend(),  # 임시 저장 (작업 파일)
        routes={"/memories/": StoreBackend(store=InMemoryStore())},  # 영구 저장
    ),
)
```

### Persistent Memory Paths

| 경로 | 용도 |
|------|------|
| `/memories/` | 일반 장기 메모리 |
| `/preferences/` | 사용자 선호도 (세션 간 유지) |
| `/knowledge/` | 대화에서 축적된 지식 |
| `/instructions/` | 피드백 기반 자기 개선 지침 |
| `/research/` | 연구 진행 상황 |

### Use Cases

1. **사용자 선호도 유지**: 언어, 응답 스타일, 자주 사용하는 제품 등
2. **지식 기반 구축**: 여러 대화에서 학습한 내용 축적
3. **자기 개선**: 사용자 피드백을 기반으로 응답 품질 향상
4. **연구 진행**: 긴 연구 작업의 중간 결과 저장

### Memory Store Service

`app/api/services/memory_store_service.py`에서 메모리 저장소 서비스를 제공합니다.

```python
from app.api.services.memory_store_service import (
    get_memory_store_service,
    initialize_memory_store,
)

# 서비스 초기화 (Neo4j 드라이버와 함께)
memory_service = await initialize_memory_store(neo4j_driver)

# 메모리 저장
await memory_service.store_memory("preferences", "language", {"lang": "ko"}, user_id="user123")

# 메모리 조회
pref = await memory_service.retrieve_memory("preferences", "language", user_id="user123")
```

### Environment Variables

```bash
# Long-term Memory 설정
MEMORY_STORE_DIR=data/agent_memory  # 파일 기반 폴백 저장소 경로
```

---

## Adding New Agent

1. `agents/` 에 에이전트 클래스 생성 (BaseAgent 상속)
2. `middleware/` 에 도구 제공자 추가 (필요시)
3. `registry.py` 에 에이전트 등록
4. `types.py` 의 AgentType enum에 추가

```python
# agents/my_agent.py
from app.api.agents.base import BaseAgent
from app.api.agents.types import AgentType, AgentContext, AgentResult

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="MyAgent", agent_type=AgentType.MY_TYPE)

    async def execute(self, task: str, context: AgentContext) -> AgentResult:
        # Implementation
        return AgentResult(success=True, content="Result")
```

## Adding New Deep Agent

1. `adapters/deep_agent_adapter.py` 에 factory 함수 추가
2. `middleware/` 에 도구 정의
3. `adapters/integration.py` 에 등록 로직 추가

```python
# adapters/deep_agent_adapter.py
def create_my_deep_agent(
    name: str = "MyDeepAgent",
    system_prompt: Optional[str] = None,
) -> DeepAgentAdapter:
    tools = get_my_tools()  # from middleware
    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.MY_TYPE,
        tools=tools,
        system_prompt=system_prompt or DEFAULT_MY_PROMPT
    )
```

## Debugging

```bash
# Agent 로그 확인
grep -E "\[.*Agent\]|\[Orchestrator\]" logs/backend_*.log | tail -50

# Deep Agent 로그 확인
grep -E "\[Deep.*Agent\]|\[DeepAgentAdapter\]" logs/backend_*.log | tail -50

# 테스트 스크립트
python scripts/test_deep_agents.py

# Agent API 직접 테스트
curl -X POST http://localhost:9000/api/v1/agent/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "agent_type": "rag", "use_deep_agent": true}'
```

## Key Files Reference

| 작업 | 파일 |
|------|------|
| 새 에이전트 추가 | `agents/*.py`, `registry.py`, `types.py` |
| 새 Deep Agent 추가 | `adapters/deep_agent_adapter.py` |
| 도구 추가 | `middleware/*.py`, `tools/*.py` |
| 등록 로직 변경 | `adapters/integration.py` |
| Fallback 로직 | `orchestrator.py:204-213` |
| 병렬 실행 | `parallel_executor.py` |
| Intent 분류 | `intent.py` |
