# LangGraph DeepAgents Long-term Memory 기술 세미나

## 1. 개요

### 1.1 문서 목적
본 문서는 HybridRAG KMS 프로젝트에서 구현한 LangGraph DeepAgents의 **Long-term Memory(LTM)** 기능에 대한 기술 세미나 자료입니다. LTM 도입 배경, 아키텍처, 구현 세부사항, 그리고 실제 코드 샘플을 통해 이 기술의 이해를 돕고자 합니다.

### 1.2 대상 독자
- AI/ML 엔지니어
- 백엔드 개발자
- 시스템 아키텍트
- LangChain/LangGraph에 관심 있는 개발자

---

## 2. 기술 도입 배경

### 2.1 기존 AI Agent의 한계

기존 AI Agent 시스템은 다음과 같은 **상태 비저장(Stateless)** 문제를 가지고 있었습니다:

| 문제점 | 설명 |
|--------|------|
| **세션 격리** | 각 대화 세션이 독립적으로 동작하여 이전 대화 내용을 기억하지 못함 |
| **사용자 선호도 미반영** | 매번 언어, 응답 스타일 등을 다시 설정해야 함 |
| **지식 휘발** | 대화에서 학습한 내용이 세션 종료 시 사라짐 |
| **연구 중단** | 긴 연구 작업의 중간 진행 상황을 유지할 수 없음 |

### 2.2 Long-term Memory의 필요성

```
┌─────────────────────────────────────────────────────────────┐
│  기존 Agent (Stateless)                                     │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                  │
│  │Session 1│    │Session 2│    │Session 3│  ← 각 세션 격리   │
│  │  독립적  │    │  독립적  │    │  독립적  │                  │
│  └─────────┘    └─────────┘    └─────────┘                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Long-term Memory Agent (Stateful)                          │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐                  │
│  │Session 1│────│Session 2│────│Session 3│  ← 연속성 유지   │
│  └────┬────┘    └────┬────┘    └────┬────┘                  │
│       │              │              │                        │
│       └──────────────┴──────────────┘                        │
│                      ↓                                       │
│              ┌──────────────┐                                │
│              │  LTM Store   │  ← 영구 저장소                  │
│              │  (Neo4j/File)│                                │
│              └──────────────┘                                │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 기대 효과

1. **개인화된 사용자 경험**: 선호도 기억으로 맞춤형 응답 제공
2. **지식 누적**: 대화를 통해 학습한 내용을 지속적으로 축적
3. **자기 개선**: 사용자 피드백을 기반으로 Agent 품질 향상
4. **연구 연속성**: 장기 프로젝트의 진행 상황 유지

---

## 3. 시스템 아키텍처

### 3.1 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    DeepAgentAdapter                          │
│  - Lazy initialization with LLM support                      │
│  - Persistent memory configuration                           │
│  - User isolation support                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              CompositeBackend (from DeepAgents)              │
│  ┌──────────────────┐    ┌──────────────────┐               │
│  │  StateBackend    │    │  StoreBackend    │               │
│  │  (임시 데이터)    │    │  (영구 데이터)    │               │
│  │  - 작업 파일      │    │  - /memories/    │               │
│  │  - 중간 결과      │    │  - /preferences/ │               │
│  └──────────────────┘    │  - /knowledge/   │               │
│                          │  - /instructions/│               │
│                          │  - /research/    │               │
│                          └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│           LangGraphStoreAdapter (Storage Layer)              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    Neo4jMemoryStore                     │ │
│  │  - 그래프 데이터베이스 기반 영구 저장                    │ │
│  │  - ACID 트랜잭션 지원                                   │ │
│  │  - 기존 RAG 인프라와 통합                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ↓ (Fallback)                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                   File-based Storage                    │ │
│  │  - JSON 파일 기반 백업 저장소                           │ │
│  │  - Neo4j 불가시 자동 전환                               │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 영구 메모리 경로 (Persistent Memory Paths)

| 경로 | 용도 | 예시 |
|------|------|------|
| `/memories/` | 일반 장기 메모리 | 중요한 대화 내용, 결정 사항 |
| `/preferences/` | 사용자 선호도 | 언어, 응답 스타일, 출력 형식 |
| `/knowledge/` | 축적된 지식 | 도메인 지식, 학습 내용 |
| `/instructions/` | 자기 개선 지침 | 피드백 기반 행동 수정 |
| `/research/` | 연구 진행 상황 | 프로젝트 중간 결과, 분석 데이터 |

---

## 4. 핵심 구현

### 4.1 Neo4j 메모리 저장소

**파일 위치**: `app/api/services/memory_store_service.py`

```python
class Neo4jMemoryStore:
    """
    Neo4j 기반 영구 메모리 저장소
    LangGraph와 통합되어 세션 간 메모리 유지
    """

    def __init__(
        self,
        driver: Optional[Any] = None,
        database: str = "neo4j"
    ):
        self._driver = driver
        self._database = database
        self._initialized = False

    async def initialize(self):
        """인덱스 생성으로 빠른 검색 지원"""
        if self._driver is None:
            logger.warning("Neo4j driver not provided, using file-based fallback")
            return

        async with self._driver.session(database=self._database) as session:
            await session.run("""
                CREATE INDEX memory_namespace_key IF NOT EXISTS
                FOR (m:AgentMemory)
                ON (m.namespace, m.key)
            """)
        self._initialized = True

    async def put(
        self,
        namespace: str,
        key: str,
        value: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> None:
        """메모리 항목 저장"""
        async with self._driver.session(database=self._database) as session:
            await session.run(
                """
                MERGE (m:AgentMemory {namespace: $namespace, key: $key})
                SET m.value = $value,
                    m.user_id = $user_id,
                    m.updated_at = datetime()
                """,
                namespace=namespace,
                key=key,
                value=json.dumps(value),
                user_id=user_id
            )

    async def get(
        self,
        namespace: str,
        key: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """메모리 항목 조회"""
        async with self._driver.session(database=self._database) as session:
            result = await session.run(
                """
                MATCH (m:AgentMemory {namespace: $namespace, key: $key})
                WHERE m.user_id = $user_id OR m.user_id IS NULL
                RETURN m.value as value
                """,
                namespace=namespace,
                key=key,
                user_id=user_id
            )
            record = await result.single()
            if record:
                return json.loads(record["value"])
        return None
```

**Neo4j 데이터 모델**:

```cypher
-- AgentMemory 노드 구조
(:AgentMemory {
    namespace: "/memories/preferences",  -- 네임스페이스
    key: "language",                      -- 고유 키
    value: '{"lang": "ko", "region": "KR"}',  -- JSON 값
    user_id: "user123",                   -- 사용자 격리
    updated_at: datetime()                -- 최종 수정 시간
})

-- 인덱스 (빠른 검색용)
CREATE INDEX memory_namespace_key IF NOT EXISTS
FOR (m:AgentMemory)
ON (m.namespace, m.key)
```

### 4.2 DeepAgentAdapter with LTM

**파일 위치**: `app/api/agents/adapters/deep_agent_adapter.py`

```python
class DeepAgentAdapter(BaseAgent):
    """
    Deep Agents를 기존 Agent 인터페이스로 래핑하는 어댑터
    CompositeBackend를 통한 Long-term Memory 지원
    """

    # 영구 저장 경로 정의
    PERSISTENT_MEMORY_PATHS = [
        "/memories/",       # 일반 장기 메모리
        "/preferences/",    # 사용자 선호도
        "/knowledge/",      # 축적된 지식
        "/instructions/",   # 자기 개선 지침
        "/research/",       # 연구 진행 상황
    ]

    def __init__(
        self,
        name: str = "DeepAgent",
        agent_type: AgentType = AgentType.PLANNER,
        llm: Optional[Any] = None,
        tools: Optional[List] = None,
        system_prompt: Optional[str] = None,
        enable_long_term_memory: bool = True,   # LTM 활성화 플래그
        memory_store: Optional[Any] = None,     # 커스텀 저장소
        user_id: Optional[str] = None,          # 사용자 격리
    ):
        super().__init__(name=name, agent_type=agent_type, ...)

        self._enable_ltm = enable_long_term_memory
        self._memory_store = memory_store
        self._user_id = user_id

    def _get_composite_backend_factory(self):
        """CompositeBackend 팩토리 생성"""
        if not DEEPAGENTS_BACKENDS_AVAILABLE or not self._enable_ltm:
            return None

        store = self._get_langraph_store()
        persistent_paths = self.PERSISTENT_MEMORY_PATHS

        def backend_factory(runtime):
            routes = {}
            for path in persistent_paths:
                # 영구 경로는 StoreBackend로 라우팅
                routes[path] = StoreBackend(runtime)

            return CompositeBackend(
                default=StateBackend(runtime),  # 기본: 임시 저장
                routes=routes                    # 영구 경로 라우팅
            )

        return backend_factory

    def _create_deep_agent(self):
        """Deep Agent 인스턴스 생성 (Lazy initialization)"""
        llm = self._llm or self._create_default_llm()
        store = self._get_langraph_store()
        backend_factory = self._get_composite_backend_factory()

        agent_kwargs = {
            "model": llm,
            "tools": self._custom_tools,
            "system_prompt": self.system_prompt,
        }

        # 영구 저장소 연결
        if store is not None:
            agent_kwargs["store"] = store

        # CompositeBackend 팩토리 연결
        if backend_factory is not None:
            agent_kwargs["backend"] = backend_factory

        return create_deep_agent(**agent_kwargs)
```

### 4.3 LangGraph Store Adapter

```python
class LangGraphStoreAdapter:
    """
    Neo4jMemoryStore를 LangGraph 인터페이스로 래핑
    비동기 저장소를 동기 LangGraph API와 연결
    """

    def __init__(self, neo4j_store: Neo4jMemoryStore):
        self._neo4j_store = neo4j_store
        self._cache: Dict[str, Any] = {}  # 동기 접근용 캐시

    def put(self, namespace: str, key: str, value: Dict[str, Any]) -> None:
        """LangGraph 호환 put 메서드 (동기)"""
        # 캐시에 즉시 저장 (동기)
        cache_key = f"{namespace}:{key}"
        self._cache[cache_key] = value

        # 백그라운드에서 Neo4j에 저장 (비동기)
        asyncio.create_task(
            self._neo4j_store.put(namespace, key, value)
        )

    def get(self, namespace: str, key: str) -> Optional[Dict[str, Any]]:
        """LangGraph 호환 get 메서드 (동기)"""
        cache_key = f"{namespace}:{key}"

        # 캐시에서 먼저 조회
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 캐시 미스 시 Neo4j에서 로드 (동기 래퍼)
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self._neo4j_store.get(namespace, key)
        )

        if result:
            self._cache[cache_key] = result
        return result

    def search(self, namespace: str, query: str = "") -> List[Dict[str, Any]]:
        """네임스페이스 내 검색"""
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            self._neo4j_store.list_keys(namespace)
        )
```

### 4.4 Factory 함수 예시: RAG Deep Agent

```python
def create_rag_deep_agent(
    name: str = "RAGDeepAgent",
    system_prompt: Optional[str] = None,
    include_vector_search: bool = True,
    include_graph_query: bool = True,
    include_image_search: bool = True,
    additional_tools: Optional[List] = None,
    enable_long_term_memory: bool = True,  # LTM 기본 활성화
    memory_store: Optional[Any] = None,
    user_id: Optional[str] = None,
) -> DeepAgentAdapter:
    """
    RAG 기능을 갖춘 Deep Agent 생성

    Long-term Memory를 통해:
    - 사용자 선호도 기억
    - 검색 패턴 학습
    - 도메인 지식 축적
    """

    # 도구 수집
    tools = []
    if include_vector_search:
        tools.append(vector_search_tool)
    if include_graph_query:
        tools.append(graph_query_tool)
    if include_image_search:
        tools.append(image_search_tool)
    if additional_tools:
        tools.extend(additional_tools)

    # 시스템 프롬프트 (LTM 사용 지침 포함)
    default_prompt = """You are a RAG assistant with long-term memory.

## Long-term Memory Paths
Store and retrieve information across conversations:
- /memories/: General long-term memory
- /preferences/: User preferences that persist
- /knowledge/: Accumulated knowledge from conversations
- /instructions/: Self-improving instructions
- /research/: Research progress across sessions

## Workflow
1. Use vector_search to find relevant documents
2. Use graph_query to explore entity relationships
3. Synthesize information from multiple sources
4. Store important insights in /knowledge/
5. Remember user preferences in /preferences/
"""

    return DeepAgentAdapter(
        name=name,
        agent_type=AgentType.RAG,
        tools=tools,
        system_prompt=system_prompt or default_prompt,
        enable_long_term_memory=enable_long_term_memory,
        memory_store=memory_store,
        user_id=user_id,
    )
```

---

## 5. 사용 예시

### 5.1 메모리 서비스 초기화

```python
from app.api.services.memory_store_service import (
    initialize_memory_store,
    get_memory_store_service
)

# 애플리케이션 시작 시 초기화
async def startup():
    # Neo4j 드라이버와 함께 메모리 서비스 초기화
    memory_service = await initialize_memory_store(neo4j_driver)
    print("Memory store initialized")
```

### 5.2 사용자 선호도 저장/조회

```python
# 사용자 선호도 저장
await memory_service.store_user_preference(
    user_id="user123",
    preference_key="language",
    preference_value="ko"
)

await memory_service.store_user_preference(
    user_id="user123",
    preference_key="response_style",
    preference_value="detailed"
)

# 다음 세션에서 선호도 조회
language = await memory_service.get_user_preference(
    user_id="user123",
    preference_key="language",
    default="en"
)
# 결과: "ko"
```

### 5.3 지식 축적

```python
# 대화에서 학습한 내용 저장
await memory_service.accumulate_knowledge(
    user_id="user123",
    topic="database_design",
    knowledge_item={
        "concept": "정규화(Normalization)",
        "explanation": "데이터 중복을 최소화하고 무결성을 보장하는 과정",
        "source": "conversation_session_42",
        "timestamp": "2024-01-14T10:30:00Z"
    }
)

# 나중에 축적된 지식 조회
knowledge = await memory_service.retrieve_memory(
    namespace="/knowledge/",
    key="database_design",
    user_id="user123"
)
# 결과: {"items": [...], "updated_at": "2024-01-14T..."}
```

### 5.4 Deep Agent와 LTM 통합 사용

```python
from app.api.agents.adapters import create_rag_deep_agent

# LTM이 활성화된 RAG Agent 생성
agent = create_rag_deep_agent(
    user_id="user123",
    enable_long_term_memory=True
)

# 첫 번째 세션
result1 = await agent.execute(
    task="Python의 데코레이터에 대해 설명해주세요.",
    context=AgentContext(user_id="user123")
)
# Agent가 /knowledge/python에 학습 내용 저장

# 두 번째 세션 (다음 날)
result2 = await agent.execute(
    task="어제 배운 Python 개념을 복습하고 싶어요.",
    context=AgentContext(user_id="user123")
)
# Agent가 /knowledge/python에서 이전 학습 내용 조회하여 응답
```

---

## 6. 안전 메커니즘

### 6.1 보호 기능

| 메커니즘 | 값 | 목적 |
|----------|-----|------|
| **Recursion Limit** | 25 | 무한 도구 호출 루프 방지 |
| **Timeout** | 300초 | 장시간 실행 방지 |
| **User Isolation** | user_id 기반 | 사용자 간 데이터 격리 |
| **Graceful Degradation** | Neo4j → File | 저장소 장애 시 자동 전환 |
| **Memory Path Control** | 명시적 경로 | 영구/임시 데이터 명확한 구분 |

### 6.2 파일 기반 Fallback

Neo4j 불가 시 파일 시스템으로 자동 전환:

```
data/agent_memory/
├── user_user123_preferences_language.json
├── user_user123_preferences_response_style.json
├── user_user123_knowledge_python.json
├── user_user123_knowledge_database_design.json
└── user_user123_research_project_alpha.json
```

파일 형식:
```json
{
  "namespace": "/memories/preferences",
  "key": "language",
  "value": {"lang": "ko", "region": "KR"},
  "user_id": "user123",
  "updated_at": "2024-01-14T10:30:45.123456"
}
```

---

## 7. 환경 설정

### 7.1 환경 변수

```bash
# Deep Agent 설정
ENABLE_DEEP_AGENT=true              # 전역 활성화 플래그
DEEP_AGENT_TYPES=rag,planner        # 활성화할 에이전트 타입

# LLM 설정
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b

# Long-term Memory 설정
MEMORY_STORE_DIR=data/agent_memory  # 파일 기반 폴백 저장소 경로

# Neo4j 설정 (기존 RAG 인프라)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphrag2024
```

---

## 8. 테스트

### 8.1 테스트 스크립트 실행

```bash
# Long-term Memory 기능 테스트
python scripts/test_long_term_memory.py
```

### 8.2 테스트 항목

1. **MemoryStoreService 파일 저장**: 서비스 생성, 저장/조회, 삭제
2. **DeepAgentAdapter 임포트**: 기능 플래그 확인, 임포트 검증
3. **CompositeBackend 생성**: LangGraph 저장소, 백엔드 팩토리
4. **다중 세션 영속성**: 세션 간 데이터 일관성 검증

---

## 9. 관련 파일 참조

| 용도 | 파일 경로 |
|------|-----------|
| 메모리 서비스 | `app/api/services/memory_store_service.py` |
| Deep Agent 어댑터 | `app/api/agents/adapters/deep_agent_adapter.py` |
| 통합 및 등록 | `app/api/agents/adapters/integration.py` |
| 테스트 스위트 | `scripts/test_long_term_memory.py` |
| Agent 문서 | `app/api/agents/CLAUDE.md` |

---

## 10. 결론

### 10.1 구현 요약

LangGraph DeepAgents의 Long-term Memory 기능은 다음을 통해 AI Agent의 상태 유지 문제를 해결합니다:

1. **CompositeBackend 패턴**: 임시 데이터와 영구 데이터의 명확한 분리
2. **Neo4j 통합**: 기존 RAG 인프라를 활용한 안정적인 저장소
3. **사용자 격리**: user_id 기반의 안전한 멀티테넌시 지원
4. **Graceful Degradation**: 장애 상황에서의 파일 기반 폴백

### 10.2 향후 개선 방향

- [ ] 메모리 관리 API 엔드포인트 추가
- [ ] 프론트엔드 UI에서 선호도/지식 조회 기능
- [ ] 메모리 자동 정리 (TTL 기반)
- [ ] 벡터 임베딩을 통한 의미 기반 메모리 검색

---

## 11. Q&A

기술적인 질문이나 구현 세부사항에 대한 문의는 개발팀으로 연락해 주세요.

---

**문서 작성일**: 2024년 1월 14일
**작성자**: AI Development Team
**버전**: 1.0
