# LLM 할루시네이션 방지 기술 세미나

## 1. 개요

### 1.1 문서 목적
본 문서는 HybridRAG KMS 프로젝트에서 LLM **할루시네이션(Hallucination)**을 방지하기 위해 구현한 기술들의 발전 과정을 정리한 기술 세미나 자료입니다. 문제 발생 → 해결책 적용 → 검증의 히스토리를 추적하고, 최종적으로 채택한 다층 방어 체계를 설명합니다.

### 1.2 대상 독자
- AI/ML 엔지니어
- RAG 시스템 개발자
- LLM 애플리케이션 품질 담당자
- 프롬프트 엔지니어링에 관심 있는 개발자

### 1.3 할루시네이션이란?
LLM이 **사실이 아닌 정보를 그럴듯하게 생성**하는 현상입니다:

| 유형 | 설명 | 예시 |
|------|------|------|
| **출처 조작** | 존재하지 않는 문서 인용 | "[출典: パフォーマンス最適化ガイドライン]" (실제 없는 문서) |
| **사실 왜곡** | 검색 결과와 다른 내용 생성 | "Message Format Service"를 "Mainframe File System"으로 |
| **지식 누출** | DB에 없는 일반 지식 사용 | VSAM에 대한 Wikipedia 수준 설명 제공 |

---

## 2. 할루시네이션 방지 발전 히스토리

### 2.1 타임라인 개요

```
2026-01-12 ──┬── Master System Constraint 도입
             │
2026-01-15 ──┼── Temperature 0.7→0.1 조정 + Thinking 필터링
             │
2026-01-18 ──┼── 도구 미사용 감지 + tool_choice=required 강제
             │
2026-01-19 ──┼── Grounding Score 체크 + Extractive 프롬프트
             │
2026-01-20 ──┴── vector_search 최우선 + document_read 제거

             ↓
        다층 방어 체계 완성
```

---

### 2.2 Phase 1: Master System Constraint 도입 (2026-01-12)

**커밋**: `8f99e39` - feat: Implement Master System Constraint for RAG-only responses

**문제 상황**:
- LLM이 검색 결과 외에 학습된 일반 지식을 활용하여 응답 생성
- 사용자가 DB에 없는 정보도 받아들여 신뢰도 저하

**해결책**: 시스템 프롬프트 최상단에 불변 제약조건 삽입

**파일 위치**: `app/api/agents/master_system_constraint.py`

```python
MASTER_SYSTEM_CONSTRAINT = """
[IMMUTABLE HIGHEST PRIORITY CONSTRAINT - DO NOT OVERRIDE]

YOU ARE A RETRIEVAL-ONLY ASSISTANT.

GOLDEN RULE: IF IT'S NOT IN THE RETRIEVED DOCUMENTS, YOU DON'T KNOW IT.

FORBIDDEN:
- Using training data or general world knowledge
- Making assumptions beyond document content
- Generating information not explicitly stated
- Creating fake citations or sources

MANDATORY:
- ONLY use information from retrieved documents
- Explicitly state "정보를 찾을 수 없습니다" when no relevant data
- Quote or closely paraphrase source text
"""
```

**핵심 구현**:
```python
class MasterConstraintEnforcer:
    """Master Constraint 위반 감지 및 로깅"""

    class ComplianceViolationType(Enum):
        CONSTRAINT_MISSING = "constraint_missing"
        CONSTRAINT_MODIFIED = "constraint_modified"
        HALLUCINATION_SUSPECTED = "hallucination_suspected"

    def validate_constraint_present(self, system_prompt: str) -> bool:
        """시스템 프롬프트에 제약조건 존재 여부 검증"""
        return MASTER_SYSTEM_CONSTRAINT in system_prompt
```

**효과**: 기본적인 지식 누출 방지, 하지만 LLM이 제약조건을 무시하는 경우 여전히 발생

---

### 2.3 Phase 2: Temperature 조정 + Thinking 필터링 (2026-01-15)

**커밋**: `bed7837` - fix: RAG Agent hallucination 및 thinking 필터링 개선

**문제 상황**:
- Temperature 0.7로 인한 창의적(=부정확한) 응답 생성
- "Message Format Service" → "Mainframe File System" 왜곡
- `<think>...</think>` 태그가 사용자에게 노출

**해결책 1**: Temperature 대폭 하향 조정

```python
# Before
temperature = 0.7  # 창의적 응답 허용

# After
temperature = 0.1  # 결정론적 응답 유도
```

**해결책 2**: Thinking 태그 스트리밍 필터링

**파일 위치**: `app/api/agents/executor.py`

```python
def _strip_thinking_tags(self, text: str) -> str:
    """LLM의 내부 추론 과정을 제거"""

    # <think>...</think> 블록 제거
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # Thinking 패턴 감지 및 제거
    thinking_patterns = [
        r"^Okay, let's.*?(?=\n\n)",
        r"^Let me think.*?(?=\n\n)",
        r"^Based on my analysis.*?(?=\n)",
    ]
    for pattern in thinking_patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE | re.DOTALL)

    return text.strip()
```

**효과**: 응답 정확도 향상, 하지만 LLM이 도구를 호출하지 않고 바로 응답하는 문제 잔존

---

### 2.4 Phase 3: 도구 미사용 감지 + tool_choice=required (2026-01-18)

**커밋 1**: `2192604` - fix: prevent RAG agent hallucination when no search tools are called
**커밋 2**: `a598318` - feat: add tool_choice=required for RAG agent first call

**문제 상황**:
- Qwen2.5-7B 모델이 검색 도구를 호출하지 않고 바로 응답 생성
- 가짜 출처: "VSAM Overview - IBM Documentation" (DB에 없음)

**해결책 1**: 도구 미사용 시 강제 차단

```python
# app/api/agents/executor.py

async def execute(self, task, context):
    result = await self._run_agent_step(task, context)

    # 할루시네이션 감지: RAG 에이전트가 도구 없이 응답한 경우
    if (self.agent_type == AgentType.RAG and
        step == 1 and
        not result.tool_calls):

        logger.warning("RAG agent responded without search tools - blocking hallucination")
        return AgentResult(
            content="요청하신 정보를 찾을 수 없습니다.",
            sources=[],
            confidence=0.0
        )
```

**해결책 2**: API 레벨에서 도구 호출 강제

```python
# app/api/agents/adapters/ollama_adapter.py

async def generate(self, messages, tools=None, tool_choice=None):
    payload = {
        "model": self.model,
        "messages": messages,
        "temperature": 0.1,
    }

    if tools:
        payload["tools"] = tools

        # RAG 에이전트 첫 호출 시 도구 사용 강제
        if tool_choice == "required":
            payload["tool_choice"] = "required"
```

**적용 위치**:
```python
# executor.py - RAG 에이전트 첫 번째 스텝
if agent_type == AgentType.RAG and step == 1:
    result = await adapter.generate(
        messages=messages,
        tools=self.tools,
        tool_choice="required"  # 도구 호출 필수
    )
```

**효과**: LLM이 반드시 검색 도구를 호출하도록 강제, 하지만 검색 결과가 없을 때 여전히 할루시네이션 가능

---

### 2.5 Phase 4: Grounding Score 체크 + Extractive 프롬프트 (2026-01-19)

**커밋 1**: `04a4cd8` - fix(auto-agent): prevent hallucination when no KB sources found
**커밋 2**: `1cab191` - fix(rag): reduce hallucination with extractive prompt and better limits

**문제 상황**:
- 검색 결과가 없어도 LLM이 그럴듯한 가짜 응답 생성
- 일본어 쿼리 "パフォーマンス最適化方法"에 대해 가짜 출처 생성

**해결책 1**: Grounding Score 기반 차단

**파일 위치**: `app/api/agents/auto_agent/answer_composer.py`

```python
async def compose_answer(self, task_results, verification):
    all_sources = self._collect_validated_sources(task_results)

    # 핵심 할루시네이션 방지 로직
    if verification.grounding_score < 0.1 and len(all_sources) == 0:
        logger.warning(
            f"Grounding score {verification.grounding_score:.2%} "
            "with no sources - returning 'not found' to prevent hallucination"
        )
        return self._create_not_found_response(
            query=task_results[0].task.query,
            language=self._detect_language(task_results[0].task.query)
        )
```

**다국어 "찾을 수 없음" 응답**:
```python
def _create_not_found_response(self, query: str, language: str):
    messages = {
        "ko": "요청하신 정보를 데이터베이스에서 찾을 수 없습니다.",
        "ja": "ご依頼の情報はデータベースで見つかりませんでした。",
        "en": "The requested information could not be found in the database."
    }
    return AnswerResult(
        content=messages.get(language, messages["en"]),
        sources=[],
        confidence=0.0
    )
```

**해결책 2**: Extractive-only 프롬프트

**파일 위치**: `app/api/agents/prompts/rag_agent.txt`

```
## EXTRACTION MODE (CRITICAL)

You are a COPY-PASTE machine. Your ONLY job is to:
1. Call vector_search to find documents
2. EXTRACT exact quotes from search results
3. Present the extracted content with citations

FORBIDDEN:
- Paraphrasing beyond minor grammar fixes
- Summarizing in your own words
- Adding context or explanations not in documents
- Using phrases like "Based on my knowledge..."
- Creating citations for non-existent documents

If search returns no results:
→ Reply ONLY: "검색 결과가 없습니다."
→ DO NOT generate alternative content
```

**효과**: 검색 결과 없을 때 정직한 응답, 하지만 LLM이 여전히 document_read로 우회 가능

---

### 2.6 Phase 5: vector_search 최우선 + document_read 제거 (2026-01-20)

**커밋**: `cba01e8` - fix(agent): enforce vector_search first, remove document_read from RAG agent

**문제 상황**:
- LLM이 vector_search 대신 document_read를 먼저 호출
- "Document service not available" 에러 발생 시 할루시네이션으로 폴백

**해결책 1**: RAG 에이전트에서 document_read 도구 제거

```python
# app/api/agents/agents/rag_agent.py

class RAGAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="RAGAgent",
            agent_type=AgentType.RAG,
            tools=["vector_search", "graph_query"],  # document_read 제거!
            system_prompt=load_prompt("rag_agent.txt")
        )
```

**해결책 2**: 프롬프트에 순서 강제 명시

```
## MANDATORY FIRST ACTION

When user asks ANY question:
1. ALWAYS call vector_search() FIRST
2. NEVER skip vector_search
3. NEVER use document_read as first tool

Tool Priority:
1. vector_search (PRIMARY - for all queries)
2. graph_query (SECONDARY - for entity relationships)

The document_read tool is NOT available to you.
```

**효과**: 우회 경로 차단으로 안정적인 검색 우선 동작 확보

---

## 3. 최종 채택 다층 방어 체계

### 3.1 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                     사용자 쿼리                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Master System Constraint                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ "IF IT'S NOT IN THE RETRIEVED DOCUMENTS,            │   │
│  │  YOU DON'T KNOW IT"                                 │   │
│  │                                                      │   │
│  │ - 시스템 프롬프트 최상단 삽입                          │   │
│  │ - 일반 지식 사용 금지                                 │   │
│  │ - 위반 시 로깅                                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Tool Usage Enforcement                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ tool_choice = "required"                            │   │
│  │                                                      │   │
│  │ - RAG 에이전트 첫 호출 시 도구 사용 강제              │   │
│  │ - vector_search만 허용 (document_read 제거)          │   │
│  │ - 도구 미사용 시 응답 차단                           │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Response Verification                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Verifier Agent + Confidence Scorer         │   │
│  │                                                      │   │
│  │ Grounding Score (30% weight)                        │   │
│  │ ├─ 출처 존재 여부 확인                               │   │
│  │ ├─ 인용문과 출처 매칭                                │   │
│  │ └─ 다중 출처 시 보너스 점수                          │   │
│  │                                                      │   │
│  │ Consistency Score (20% weight)                      │   │
│  │ └─ 응답 간 모순 검출                                 │   │
│  │                                                      │   │
│  │ Completeness Score (25% weight)                     │   │
│  │ └─ 질문 대비 답변 완성도                             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: Final Guard                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ if grounding_score < 0.1 AND sources == []:         │   │
│  │     return "정보를 찾을 수 없습니다"                  │   │
│  │                                                      │   │
│  │ - LLM 생성 출처 제거 (검증된 출처만 사용)             │   │
│  │ - Thinking 태그 필터링                               │   │
│  │ - 다국어 "Not Found" 응답                            │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                검증된 응답 + 출처 목록                         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 각 레이어별 역할

| Layer | 파일 | 방어 대상 | 방어 방법 |
|-------|------|----------|----------|
| **1. Master Constraint** | `master_system_constraint.py` | 일반 지식 누출 | 프롬프트 제약 |
| **2. Tool Enforcement** | `executor.py`, `rag_agent.py` | 검색 우회 | API 강제 + 도구 제한 |
| **3. Verification** | `verifier_agent.py`, `confidence_scorer.py` | 미검증 주장 | 다단계 검증 |
| **4. Final Guard** | `answer_composer.py` | 출처 없는 응답 | 점수 기반 차단 |

---

## 4. 핵심 구현 코드

### 4.1 Confidence Scorer - Grounding 점수 계산

**파일 위치**: `app/api/agents/auto_agent/confidence_scorer.py`

```python
class ConfidenceScorer:
    """응답 품질 점수 계산"""

    WEIGHT_EXECUTION = 0.25    # 실행 성공률
    WEIGHT_GROUNDING = 0.30    # 출처 기반 점수 (최고 가중치!)
    WEIGHT_CONSISTENCY = 0.20  # 일관성
    WEIGHT_COMPLETENESS = 0.25 # 완성도

    def _calculate_grounding_score(self, task_results: List[TaskResult]) -> float:
        """출처 기반 Grounding 점수 계산"""

        rag_results = [r for r in task_results
                       if r.agent_type in [AgentType.RAG, AgentType.IMS]]

        if not rag_results:
            return 1.0  # RAG 태스크 없으면 해당 없음

        total_score = 0.0
        for result in rag_results:
            sources = result.sources or []

            if not sources:
                # 출처 없음 = 0점
                total_score += 0.0
            else:
                # 기본 점수 0.9 + 다중 출처 보너스 (최대 0.1)
                source_bonus = min(len(sources) * 0.02, 0.1)
                total_score += 0.9 + source_bonus

        return total_score / len(rag_results)
```

### 4.2 Answer Composer - 최종 방어선

**파일 위치**: `app/api/agents/auto_agent/answer_composer.py`

```python
class AnswerComposer:
    """최종 응답 생성 및 할루시네이션 방지"""

    async def compose_answer(
        self,
        task_results: List[TaskResult],
        verification: VerificationResult
    ) -> AnswerResult:

        # 검증된 출처만 수집 (LLM 생성 출처 제외!)
        all_sources = self._collect_validated_sources(task_results)

        # ★ 핵심 할루시네이션 방지 ★
        if verification.grounding_score < 0.1 and len(all_sources) == 0:
            logger.warning(
                f"Grounding score {verification.grounding_score:.2%} "
                "with no sources - returning 'not found'"
            )
            return self._create_not_found_response(
                query=task_results[0].task.query,
                language=self._detect_language(task_results[0].task.query)
            )

        # 검증 통과 시 LLM으로 응답 구성
        composed = await self._compose_with_llm(task_results, all_sources)

        # 응답 정제 (thinking 태그 등 제거)
        cleaned = self._clean_response(composed)

        return AnswerResult(
            content=cleaned,
            sources=all_sources[:10],  # 최대 10개 출처
            confidence=verification.overall_confidence
        )

    def _collect_validated_sources(self, results: List[TaskResult]) -> List[Source]:
        """도구 실행 결과에서만 출처 수집 (LLM 생성 출처 무시)"""
        sources = []
        seen = set()

        for result in results:
            # 오직 tool_results에서만 출처 추출
            if result.tool_results:
                for tool_result in result.tool_results:
                    for source in tool_result.sources:
                        key = (source.doc_id, source.reference)
                        if key not in seen:
                            seen.add(key)
                            sources.append(source)

        return sources
```

### 4.3 Verifier Agent - 검증 프로세스

**파일 위치**: `app/api/agents/auto_agent/verifier_agent.py`

```python
class VerifierAgent:
    """에이전트 결과 검증"""

    async def verify(self, task_results: List[TaskResult]) -> VerificationResult:
        # 1. 빠른 규칙 기반 검증
        quick_issues = self._quick_validation(task_results)

        # 2. LLM 기반 심층 검증
        llm_issues = await self._llm_verification(task_results)

        # 3. 점수 계산
        scores = self._calculate_scores(task_results, quick_issues + llm_issues)

        return VerificationResult(
            grounding_score=scores.grounding,
            consistency_score=scores.consistency,
            completeness_score=scores.completeness,
            issues=quick_issues + llm_issues
        )

    def _quick_validation(self, results: List[TaskResult]) -> List[Issue]:
        """규칙 기반 빠른 검증"""
        issues = []

        for result in results:
            # RAG/IMS 에이전트의 출처 없는 응답 감지
            if result.agent_type in [AgentType.RAG, AgentType.IMS]:
                if not result.sources:
                    issues.append(Issue(
                        issue_type=IssueType.UNGROUNDED_CLAIM,
                        severity=Severity.CRITICAL,
                        evidence=f"No sources for: {result.content[:100]}...",
                        suggested_fix="Re-run with broader search query"
                    ))

        return issues
```

---

## 5. 환경 설정

### 5.1 LLM Temperature 설정

```python
# app/api/agents/adapters/ollama_adapter.py
DEFAULT_TEMPERATURE = 0.1  # 할루시네이션 방지를 위한 낮은 값
```

### 5.2 검색 결과 제한

```python
# app/api/agents/tools/vector_search.py
CONTENT_LIMIT = 2000       # 충분한 컨텍스트 제공
RESULT_COUNT = 10          # 상위 10개 결과

# app/api/agents/executor.py
TOOL_RESULT_TRUNCATE = 6000  # 도구 결과 최대 길이
```

### 5.3 신뢰도 임계값

```python
# app/api/agents/auto_agent/answer_composer.py
GROUNDING_THRESHOLD = 0.1  # 10% 미만이면 "찾을 수 없음" 반환
```

---

## 6. 효과 검증

### 6.1 개선 전후 비교

| 시나리오 | 개선 전 | 개선 후 |
|----------|---------|---------|
| DB에 없는 질문 | 가짜 출처와 함께 응답 | "정보를 찾을 수 없습니다" |
| 일본어 쿼리 | 가짜 일본어 출처 생성 | 정직한 다국어 응답 |
| 검색 도구 우회 | document_read로 우회 | vector_search 강제 |
| 창의적 왜곡 | "Mainframe File System" | "Message Format Service" (정확) |

### 6.2 품질 메트릭

```
┌────────────────────────────────────────┐
│          RAG 평가 지표 (RAGAS)          │
├────────────────────────────────────────┤
│ Faithfulness (충실도)      30% weight  │◀─ 할루시네이션 방지 핵심
│ Context Relevance          25% weight  │
│ Answer Relevancy           25% weight  │
│ Context Precision          10% weight  │
│ Context Recall             10% weight  │
└────────────────────────────────────────┘
```

---

## 7. 관련 파일 참조

| 용도 | 파일 경로 |
|------|-----------|
| Master Constraint | `app/api/agents/master_system_constraint.py` |
| Verifier Agent | `app/api/agents/auto_agent/verifier_agent.py` |
| Confidence Scorer | `app/api/agents/auto_agent/confidence_scorer.py` |
| Answer Composer | `app/api/agents/auto_agent/answer_composer.py` |
| RAG Agent 정의 | `app/api/agents/agents/rag_agent.py` |
| RAG Agent 프롬프트 | `app/api/agents/prompts/rag_agent.txt` |
| Executor | `app/api/agents/executor.py` |
| RAG 평가 서비스 | `app/api/services/rag_evaluation_service.py` |
| 타입 정의 | `app/api/agents/auto_agent/types.py` |

---

## 8. 결론

### 8.1 핵심 교훈

1. **단일 방어선은 불충분**: 프롬프트만으로는 LLM의 할루시네이션을 완전히 방지할 수 없음
2. **다층 방어 필수**: Prompt → API → Verification → Guard의 4단계 방어
3. **정직한 실패가 가짜 성공보다 낫다**: "찾을 수 없음"이 할루시네이션보다 신뢰 구축에 유리
4. **검증 가능한 출처만 신뢰**: LLM이 생성한 출처는 반드시 무시

### 8.2 최종 채택 방법 요약

```
┌─────────────────────────────────────────────────────────────┐
│             HybridRAG KMS 할루시네이션 방지 체계              │
├─────────────────────────────────────────────────────────────┤
│ 1. Master Constraint    │ 일반 지식 사용 금지 선언           │
│ 2. tool_choice=required │ 검색 도구 호출 API 강제            │
│ 3. document_read 제거   │ 우회 경로 차단                     │
│ 4. Temperature 0.1      │ 결정론적 응답 유도                 │
│ 5. Grounding Score      │ 출처 기반 품질 점수 (30% 가중치)    │
│ 6. Final Guard          │ 10% 미만 + 출처 없음 = 차단         │
│ 7. Thinking 필터링      │ 내부 추론 과정 제거                 │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 향후 개선 방향

- [ ] 실시간 할루시네이션 감지 대시보드
- [ ] 사용자 피드백 기반 자동 튜닝
- [ ] 더 정교한 출처-주장 매칭 알고리즘
- [ ] 할루시네이션 패턴 학습 및 사전 차단

---

## 9. Q&A

기술적인 질문이나 구현 세부사항에 대한 문의는 개발팀으로 연락해 주세요.

---

**문서 작성일**: 2026년 1월 21일
**작성자**: AI Development Team
**버전**: 1.0
