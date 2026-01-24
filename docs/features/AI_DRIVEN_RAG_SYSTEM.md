# AI Driven RAG System

**Version**: v1.0.0-gpu-local-llm
**Last Updated**: 2026-01-24

---

## 1. 개요

AI Driven RAG System은 기존의 단순 검색-생성 파이프라인을 **지능형 Meta-Agent 기반 오케스트레이션**으로 업그레이드한 시스템입니다.

### 기존 RAG vs AI Driven RAG

| 구분 | 기존 RAG (CPU) | AI Driven RAG (GPU) |
|------|---------------|---------------------|
| 처리 방식 | 단일 파이프라인 | Multi-Agent 오케스트레이션 |
| 질의 이해 | 키워드 기반 | 의도 분석 + 명확화 |
| 검색 | 벡터 유사도 | 벡터 + Intent Verification |
| 실행 | 순차 실행 | 병렬 실행 + 재시도 |
| 검증 | 없음 | Verifier Agent 검증 |

---

## 2. 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI DRIVEN RAG ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User Query                                                     │
│      │                                                          │
│      ▼                                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Query Clarification Layer                   │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │  Ambiguous  │  │    User     │  │   ML Entity     │  │   │
│  │  │    Term     │→ │ Preference  │→ │ Recommendation  │  │   │
│  │  │  Detection  │  │   Check     │  │   (Phase 2)     │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘  │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Auto Agent Orchestrator                     │   │
│  │                                                          │   │
│  │  ┌─────────────┐                                         │   │
│  │  │   Memory    │  ← Load conversation context            │   │
│  │  │   Manager   │                                         │   │
│  │  └──────┬──────┘                                         │   │
│  │         │                                                │   │
│  │         ▼                                                │   │
│  │  ┌─────────────┐                                         │   │
│  │  │   Planner   │  ← MANDATORY: Task decomposition       │   │
│  │  │    Agent    │  ← Create ExecutionPlan                │   │
│  │  └──────┬──────┘                                         │   │
│  │         │                                                │   │
│  │         ▼                                                │   │
│  │  ┌─────────────────────────────────────────────────┐    │   │
│  │  │          Parallel Executor                       │    │   │
│  │  │                                                  │    │   │
│  │  │  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐    │    │   │
│  │  │  │  RAG  │  │  IMS  │  │ Code  │  │Vision │    │    │   │
│  │  │  │ Agent │  │ Agent │  │ Agent │  │ Agent │    │    │   │
│  │  │  └───┬───┘  └───┬───┘  └───┬───┘  └───┬───┘    │    │   │
│  │  │      │          │          │          │         │    │   │
│  │  │      └──────────┴──────────┴──────────┘         │    │   │
│  │  │                     │                           │    │   │
│  │  └─────────────────────┼───────────────────────────┘    │   │
│  │                        │                                 │   │
│  │                        ▼                                 │   │
│  │  ┌─────────────┐                                         │   │
│  │  │  Verifier   │  ← MANDATORY: Result validation        │   │
│  │  │    Agent    │  ← Grounding check                     │   │
│  │  └──────┬──────┘                                         │   │
│  │         │                                                │   │
│  │         ▼                                                │   │
│  │  ┌─────────────┐                                         │   │
│  │  │   Answer    │  ← Strip reasoning                     │   │
│  │  │  Composer   │  ← Format response                     │   │
│  │  └─────────────┘                                         │   │
│  │                                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│                    Final Response                               │
│                    + Next Actions                               │
│                    + Execution Trace                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 핵심 컴포넌트

### 3.1 Query Clarification Layer

사용자 질의에 애매한 용어가 포함되어 있는지 사전 감지합니다.

```python
# app/api/services/query_clarification_service.py

class QueryClarificationService:
    """
    질의 명확화 서비스

    기능:
    1. 애매한 용어 감지 (ambiguous_terms 테이블)
    2. 사용자 선호도 확인 (user_term_preferences 테이블)
    3. ML 기반 엔티티 추천 (entity_embedding_service)
    """

    async def check_clarification_needed(
        self,
        query: str,
        user_id: str
    ) -> ClarificationCheckResponse:
        # 1. 애매한 용어 감지
        detected_terms = await self._detect_ambiguous_terms(query)

        if not detected_terms:
            return ClarificationCheckResponse(needs_clarification=False)

        # 2. 사용자 선호도로 자동 해결 시도
        resolved_terms = []
        unresolved_terms = []

        for term in detected_terms:
            preference = await self._get_user_preference(user_id, term)
            if preference and preference.remember:
                resolved_terms.append(term.with_selection(preference.selected))
            else:
                unresolved_terms.append(term)

        # 3. 해결되지 않은 용어가 있으면 명확화 필요
        if unresolved_terms:
            return ClarificationCheckResponse(
                needs_clarification=True,
                detected_terms=unresolved_terms,
                auto_resolved_terms=resolved_terms
            )

        # 4. 모두 자동 해결됨
        return ClarificationCheckResponse(
            needs_clarification=False,
            auto_resolved_terms=resolved_terms,
            resolved_query=self._apply_resolutions(query, resolved_terms)
        )
```

#### 애매한 용어 예시

| 용어 | 가능한 의미 |
|------|-------------|
| MFS | JEUS MFS, Tmax MFS, WebtoB MFS |
| WebAdmin | JEUS WebAdmin, Tmax WebAdmin |
| 세션 | HTTP Session, WAS Session, DB Session |
| 클러스터 | JEUS Cluster, Tmax Cluster, K8s Cluster |

### 3.2 Planner Agent

작업을 분해하고 실행 계획을 수립합니다.

```python
# app/api/agents/auto_agent/planner_agent.py

class PlannerAgent:
    """
    실행 계획 수립 Agent

    책임:
    - 작업 분해 (Task Decomposition)
    - 의존성 분석 (Dependency Analysis)
    - 병렬/순차 실행 결정
    """

    async def create_plan(
        self,
        task: str,
        context: ConversationContext
    ) -> ExecutionPlan:
        # LLM을 사용하여 작업 분해
        decomposition = await self.llm.analyze(
            prompt=self.PLANNING_PROMPT,
            task=task,
            context=context.summary
        )

        # ExecutionPlan 생성
        return ExecutionPlan(
            task_id=generate_id(),
            original_task=task,
            sub_tasks=[
                SubTask(
                    id=f"subtask_{i}",
                    description=t.description,
                    agent_type=t.agent_type,
                    dependencies=t.dependencies,
                    priority=t.priority
                )
                for i, t in enumerate(decomposition.tasks)
            ],
            execution_order=self._determine_order(decomposition),
            estimated_time=decomposition.estimated_time
        )

    PLANNING_PROMPT = """
    주어진 작업을 분석하여 실행 계획을 수립하세요.

    작업: {task}
    컨텍스트: {context}

    분석 기준:
    1. 어떤 정보가 필요한가? (RAG 검색 필요?)
    2. 코드 분석이 필요한가? (Code Agent 필요?)
    3. IMS 데이터가 필요한가? (IMS Agent 필요?)
    4. 이미지 분석이 필요한가? (Vision Agent 필요?)

    출력 형식:
    {
      "tasks": [
        {"description": "...", "agent_type": "rag|code|ims|vision", "dependencies": [], "priority": 1}
      ],
      "execution_strategy": "parallel|sequential|mixed",
      "estimated_time": "seconds"
    }
    """
```

### 3.3 Parallel Executor

Sub-agent들을 병렬로 실행합니다.

```python
# app/api/agents/auto_agent/orchestrator.py

class ParallelExecutor:
    """
    병렬 실행기

    기능:
    - 의존성 없는 작업 병렬 실행
    - 실패 시 재시도 (최대 2회)
    - 타임아웃 관리
    """

    async def execute(
        self,
        plan: ExecutionPlan,
        config: ExecutionConfig
    ) -> List[SubTaskResult]:
        results = []
        pending = list(plan.sub_tasks)
        completed = set()

        while pending:
            # 의존성이 해결된 작업 찾기
            ready = [
                t for t in pending
                if all(d in completed for d in t.dependencies)
            ]

            if not ready:
                raise CircularDependencyError()

            # 병렬 실행
            tasks = [
                self._execute_with_retry(t, config.max_retries)
                for t in ready
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 결과 처리
            for task, result in zip(ready, batch_results):
                if isinstance(result, Exception):
                    results.append(SubTaskResult(
                        task_id=task.id,
                        status="failed",
                        error=str(result)
                    ))
                else:
                    results.append(result)
                    completed.add(task.id)
                pending.remove(task)

        return results

    async def _execute_with_retry(
        self,
        task: SubTask,
        max_retries: int
    ) -> SubTaskResult:
        for attempt in range(max_retries + 1):
            try:
                agent = self._get_agent(task.agent_type)
                result = await asyncio.wait_for(
                    agent.execute(task.description),
                    timeout=self.timeout
                )
                return SubTaskResult(
                    task_id=task.id,
                    status="completed",
                    result=result,
                    attempts=attempt + 1
                )
            except Exception as e:
                if attempt == max_retries:
                    raise
                await asyncio.sleep(1)  # 재시도 전 대기
```

### 3.4 Verifier Agent

실행 결과를 검증합니다.

```python
# app/api/agents/auto_agent/verifier_agent.py

class VerifierAgent:
    """
    결과 검증 Agent

    검증 항목:
    1. 원본 작업 충족 여부
    2. 출처 근거 존재 여부 (Grounding)
    3. 일관성 검사
    """

    async def verify(
        self,
        original_task: str,
        results: List[SubTaskResult]
    ) -> VerificationResult:
        # 성공한 결과만 수집
        successful_results = [r for r in results if r.status == "completed"]

        if not successful_results:
            return VerificationResult(
                verified=False,
                reason="모든 하위 작업이 실패했습니다",
                suggestions=["질문을 더 구체적으로 해주세요"]
            )

        # LLM으로 검증
        verification = await self.llm.analyze(
            prompt=self.VERIFICATION_PROMPT,
            task=original_task,
            results=[r.result for r in successful_results]
        )

        return VerificationResult(
            verified=verification.is_valid,
            confidence=verification.confidence,
            grounding_score=self._calculate_grounding_score(results),
            reason=verification.reason,
            suggestions=verification.suggestions if not verification.is_valid else None
        )

    def _calculate_grounding_score(
        self,
        results: List[SubTaskResult]
    ) -> float:
        """출처 근거 점수 계산"""
        total_claims = 0
        grounded_claims = 0

        for result in results:
            if hasattr(result.result, 'citations'):
                total_claims += len(result.result.claims)
                grounded_claims += sum(
                    1 for c in result.result.claims if c.has_citation
                )

        return grounded_claims / total_claims if total_claims > 0 else 0.0
```

### 3.5 Intent Verification (Stage 2)

검색 결과가 사용자 의도와 일치하는지 LLM으로 2차 검증합니다.

```python
# app/api/services/rag_service.py

class RAGService:
    """
    Stage 2 Intent Verification 적용
    """

    async def search_with_intent_verification(
        self,
        query: str,
        top_k: int = 10
    ) -> List[SearchResult]:
        # Stage 1: Vector similarity search
        candidates = await self.vector_store.search(query, top_k=top_k * 2)

        # Stage 2: Intent verification
        intent = await self._classify_intent(query)
        verified_results = []

        for candidate in candidates:
            is_relevant = await self._verify_intent_match(
                query=query,
                intent=intent,
                document=candidate
            )
            if is_relevant:
                verified_results.append(candidate)
                if len(verified_results) >= top_k:
                    break

        return verified_results

    async def _classify_intent(self, query: str) -> QueryIntent:
        """질의 의도 분류"""
        intent_patterns = {
            QueryIntent.DEFINITION: ["무엇", "정의", "뜻", "의미", "개념"],
            QueryIntent.TROUBLESHOOTING: ["에러", "오류", "해결", "원인", "문제"],
            QueryIntent.HOWTO: ["방법", "설정", "구성", "설치", "하는법"],
            QueryIntent.COMPARISON: ["차이", "비교", "장단점", "versus", "vs"]
        }

        for intent, patterns in intent_patterns.items():
            if any(p in query for p in patterns):
                return intent

        return QueryIntent.GENERAL

    async def _verify_intent_match(
        self,
        query: str,
        intent: QueryIntent,
        document: SearchResult
    ) -> bool:
        """LLM으로 의도 일치 여부 검증"""
        prompt = f"""
        질의: {query}
        의도: {intent.value}
        문서 내용: {document.content[:500]}

        이 문서가 질의 의도에 적합한가요?

        의도별 기준:
        - definition: 용어 정의, 개념 설명이 있어야 함
        - troubleshooting: 에러 해결책, 원인 분석이 있어야 함
        - howto: 단계별 가이드, 설정 방법이 있어야 함
        - comparison: 비교 분석, 장단점이 있어야 함

        답변: YES 또는 NO (한 단어로만)
        """

        response = await self.llm.generate(prompt, temperature=0.1)
        return "YES" in response.upper()
```

---

## 4. 실행 흐름 예시

### 예시 질의: "JEUS와 Tomcat의 클러스터링 차이점"

```
1. Query Clarification
   └─ "클러스터" 용어 감지 → 사용자 선호도 확인 → JEUS Cluster로 해결

2. Planner Agent
   └─ ExecutionPlan 생성:
      - SubTask 1: "JEUS 클러스터링 기능" (RAG Agent)
      - SubTask 2: "Tomcat 클러스터링 기능" (RAG Agent)
      - SubTask 3: "비교 분석" (RAG Agent, depends: [1, 2])

3. Parallel Executor
   └─ SubTask 1, 2 병렬 실행
   └─ SubTask 3 순차 실행 (1, 2 완료 후)

4. Intent Verification
   └─ 검색 결과가 "comparison" 의도에 적합한지 검증
   └─ 부적합한 결과 필터링

5. Verifier Agent
   └─ 원본 질문 충족 여부 확인
   └─ 출처 근거 검증 (Grounding Score: 0.95)

6. Answer Composer
   └─ 비교표 형식으로 응답 구성
   └─ 출처 인용 추가
```

---

## 5. 설정

### 환경 변수

```bash
# Auto Agent 설정
ENABLE_AUTO_AGENT=true
AUTO_AGENT_MAX_RETRIES=2
AUTO_AGENT_TIMEOUT_SECONDS=120
AUTO_AGENT_MAX_PARALLEL=4

# Query Clarification 설정
ENABLE_QUERY_CLARIFICATION=true
CLARIFICATION_MIN_CONFIDENCE=0.6

# Intent Verification 설정
ENABLE_INTENT_VERIFICATION=true
INTENT_VERIFICATION_THRESHOLD=0.7
```

---

## 6. API 사용법

### Auto Agent 호출

```bash
POST /api/v1/agent/stream
Content-Type: application/json

{
  "query": "JEUS와 Tomcat의 클러스터링 차이점",
  "conversation_id": "conv_123",
  "use_auto_agent": true,
  "options": {
    "max_retries": 2,
    "timeout": 120,
    "include_trace": true
  }
}
```

### 응답 예시

```json
{
  "answer": "## JEUS vs Tomcat 클러스터링 비교\n\n| 항목 | JEUS | Tomcat |\n|------|------|--------|\n| 세션 복제 | In-memory + DB | DeltaManager |\n| 로드밸런싱 | 내장 | 외부 필요 |\n\n[출처: JEUS 8 Reference Guide, Tomcat 9 Clustering HowTo]",
  "metadata": {
    "execution_time_ms": 2340,
    "sub_tasks_count": 3,
    "grounding_score": 0.95,
    "intent": "comparison"
  },
  "trace": {
    "dag": [...],
    "timeline": [...]
  }
}
```

---

## 7. 관련 파일

| 파일 | 설명 |
|------|------|
| `app/api/agents/auto_agent/orchestrator.py` | 메인 오케스트레이터 |
| `app/api/agents/auto_agent/planner_agent.py` | 실행 계획 수립 |
| `app/api/agents/auto_agent/verifier_agent.py` | 결과 검증 |
| `app/api/agents/auto_agent/memory_manager.py` | 컨텍스트 관리 |
| `app/api/services/query_clarification_service.py` | 질의 명확화 |
| `app/api/services/rag_service.py` | Intent Verification |

---

**Next**: [Hallucination Prevention](./HALLUCINATION_PREVENTION.md)
