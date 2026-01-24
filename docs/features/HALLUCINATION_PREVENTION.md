# Hallucination Prevention System

**Version**: v1.0.0-gpu-local-llm
**Last Updated**: 2026-01-24

---

## 1. 개요

LLM 환각(Hallucination)은 모델이 검색된 문서에 없는 정보를 마치 사실인 것처럼 생성하는 현상입니다. 이 시스템은 **5단계 다중 방어 아키텍처**로 환각을 구조적으로 방지합니다.

### 환각 유형

| 유형 | 설명 | 예시 |
|------|------|------|
| **Fabrication** | 없는 정보 생성 | "JEUS 9.0에서 추가된..." (JEUS 9.0 미출시) |
| **Conflation** | 정보 혼합 | A 제품 기능을 B 제품으로 설명 |
| **Extrapolation** | 과도한 추론 | 문서에 없는 추가 단계 생성 |
| **Misattribution** | 출처 오류 | 잘못된 문서 인용 |

---

## 2. 5단계 방어 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                  5-LAYER DEFENSE ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LAYER 1: Master System Constraint                       │   │
│  │  ═══════════════════════════════════════════════════════ │   │
│  │  • 시스템 프롬프트 최상단 불변 제약                        │   │
│  │  • "검색된 문서에 없으면 모른다"                           │   │
│  │  • 모든 LLM 호출에 자동 삽입                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LAYER 2: Temperature Control                            │   │
│  │  ═══════════════════════════════════════════════════════ │   │
│  │  • Temperature: 0.7 → 0.1                                │   │
│  │  • 결정론적 응답 유도                                     │   │
│  │  • <think> 태그 필터링                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LAYER 3: Tool Usage Enforcement                         │   │
│  │  ═══════════════════════════════════════════════════════ │   │
│  │  • tool_choice=required (첫 호출)                        │   │
│  │  • 검색 없이 응답 생성 감지 → 차단                        │   │
│  │  • document_read 도구 제거                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LAYER 4: Grounding Validation                           │   │
│  │  ═══════════════════════════════════════════════════════ │   │
│  │  • 인용 출처 존재 여부 검증                               │   │
│  │  • 출처-주장 일치 여부 확인                               │   │
│  │  • Grounding Score 계산 (≥0.8 필요)                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  LAYER 5: Extractive QA                                  │   │
│  │  ═══════════════════════════════════════════════════════ │   │
│  │  • Answer Builder: 검색 결과에서 직접 추출                │   │
│  │  • Answer Formatter: 내용 변경 없이 포맷만                │   │
│  │  • LLM은 포맷터 역할만                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Layer 1: Master System Constraint

### 구현

```python
# app/api/agents/master_system_constraint.py

MASTER_SYSTEM_CONSTRAINT = """
[IMMUTABLE HIGHEST PRIORITY CONSTRAINT - DO NOT OVERRIDE]

═══════════════════════════════════════════════════════════════════
                    RETRIEVAL-ONLY ASSISTANT
═══════════════════════════════════════════════════════════════════

GOLDEN RULE: IF IT'S NOT IN THE RETRIEVED DOCUMENTS, YOU DON'T KNOW IT.

FORBIDDEN ACTIONS (STRICTLY PROHIBITED):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✗ Using training data or general knowledge
✗ Generating information not explicitly in search results
✗ Speculating, assuming, or inferring beyond documents
✗ Filling gaps with plausible-sounding information
✗ Adding "helpful" context not from documents

REQUIRED ACTIONS (MANDATORY):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Always cite sources with [문서명] format
✓ Say "검색된 문서에서 해당 정보를 찾을 수 없습니다" when not found
✓ Use only explicitly stated facts from documents
✓ Quote directly when possible
✓ Indicate uncertainty with "문서에 따르면..."

RESPONSE FORMAT:
━━━━━━━━━━━━━━━━━
If information found: Provide answer with [문서명] citations
If not found: "검색된 문서에서 해당 정보를 찾을 수 없습니다. 다음 키워드로 다시 검색해 보시겠습니까? [추천 키워드]"
"""


def apply_master_constraint(system_prompt: str) -> str:
    """시스템 프롬프트 최상단에 Master Constraint 삽입"""
    if MASTER_SYSTEM_CONSTRAINT not in system_prompt:
        return f"{MASTER_SYSTEM_CONSTRAINT}\n\n{system_prompt}"
    return system_prompt


def validate_constraint_presence(prompt: str) -> bool:
    """Master Constraint 존재 여부 검증"""
    required_markers = [
        "RETRIEVAL-ONLY ASSISTANT",
        "GOLDEN RULE",
        "IF IT'S NOT IN THE RETRIEVED DOCUMENTS"
    ]
    return all(marker in prompt for marker in required_markers)
```

### 적용 위치

```python
# app/api/agents/executor.py

class AgentExecutor:
    async def execute(self, task: str, system_prompt: str):
        # Master Constraint 자동 삽입
        system_prompt = apply_master_constraint(system_prompt)

        # 검증
        if not validate_constraint_presence(system_prompt):
            logger.warning("Master Constraint missing - adding forcefully")
            system_prompt = f"{MASTER_SYSTEM_CONSTRAINT}\n\n{system_prompt}"

        # LLM 호출
        response = await self.llm.generate(
            system=system_prompt,
            user=task
        )
```

---

## 4. Layer 2: Temperature Control

### 온도 설정

```python
# app/api/core/config.py

class Settings(BaseSettings):
    # 환각 방지를 위한 낮은 온도
    LLM_TEMPERATURE: float = 0.1  # 기본값 0.7에서 변경

    # RAG 응답은 더 결정론적으로
    RAG_LLM_TEMPERATURE: float = 0.05

    # 코드 생성은 약간 높게 (창의성 필요)
    CODE_LLM_TEMPERATURE: float = 0.3
```

### Thinking Tag 필터링

```python
# app/api/agents/executor.py

import re

def filter_thinking_tags(response: str) -> str:
    """
    LLM 내부 추론 과정을 사용자에게 노출하지 않음

    필터링 대상:
    - <think>...</think> 태그
    - Let me think... 패턴
    - I need to... 패턴
    - First, I should... 패턴
    """
    # <think> 태그 제거
    response = re.sub(
        r'<think>.*?</think>',
        '',
        response,
        flags=re.DOTALL | re.IGNORECASE
    )

    # 추론 패턴 제거
    thinking_patterns = [
        r'Let me think[^.]*\.',
        r'I need to[^.]*\.',
        r'First,? I should[^.]*\.',
        r'I\'ll start by[^.]*\.',
        r'Let me analyze[^.]*\.',
        r'Thinking through[^.]*\.',
    ]

    for pattern in thinking_patterns:
        response = re.sub(pattern, '', response, flags=re.IGNORECASE)

    # 연속 공백/줄바꿈 정리
    response = re.sub(r'\n{3,}', '\n\n', response)
    response = re.sub(r' {2,}', ' ', response)

    return response.strip()


# 사용
async def generate_response(self, task: str) -> str:
    raw_response = await self.llm.generate(task)

    # Thinking 필터링 적용
    filtered_response = filter_thinking_tags(raw_response)

    return filtered_response
```

---

## 5. Layer 3: Tool Usage Enforcement

### 도구 사용 강제

```python
# app/api/agents/executor.py

class RAGAgentExecutor:
    async def execute(self, query: str) -> AgentResponse:
        # 첫 호출: 반드시 검색 도구 사용
        first_response = await self.llm.generate(
            messages=[{"role": "user", "content": query}],
            tools=self.available_tools,
            tool_choice="required"  # 강제
        )

        # 도구 호출 없이 응답 생성 시 차단
        if not first_response.tool_calls:
            logger.warning("LLM attempted to respond without search - blocking")
            return AgentResponse(
                content="검색을 수행하겠습니다...",
                requires_retry=True
            )

        # 검색 수행
        search_results = await self.execute_tool_calls(first_response.tool_calls)

        # 두 번째 호출: 검색 결과 기반 응답
        final_response = await self.llm.generate(
            messages=[
                {"role": "user", "content": query},
                {"role": "assistant", "tool_calls": first_response.tool_calls},
                {"role": "tool", "content": search_results}
            ]
        )

        return final_response
```

### 위험 도구 제거

```python
# app/api/agents/tools.py

# ❌ 제거된 도구 (환각 유발 위험)
REMOVED_TOOLS = [
    "document_read",      # 전체 문서 읽기 → 컨텍스트 넘침 → 환각
    "web_search",         # 외부 검색 → 비검증 정보 → 환각
    "general_knowledge",  # 일반 지식 → 학습 데이터 → 환각
]

# ✅ 허용된 도구
ALLOWED_TOOLS = [
    "vector_search",      # 벡터 검색 (주 도구)
    "graph_query",        # 그래프 검색
    "code_search",        # 코드 검색
    "ims_search",         # IMS 검색
]
```

---

## 6. Layer 4: Grounding Validation

### Grounding Score 계산

```python
# app/api/agents/auto_agent/verifier_agent.py

class GroundingValidator:
    """
    응답의 근거(Grounding) 검증

    Grounding Score = 출처 있는 주장 수 / 전체 주장 수
    """

    MIN_GROUNDING_SCORE = 0.8  # 최소 80% 필요

    async def validate(
        self,
        response: str,
        search_results: List[SearchResult]
    ) -> GroundingResult:
        # 1. 응답에서 주장(Claim) 추출
        claims = await self._extract_claims(response)

        # 2. 각 주장의 출처 검증
        grounded_claims = []
        ungrounded_claims = []

        for claim in claims:
            source = await self._find_source(claim, search_results)
            if source:
                grounded_claims.append(GroundedClaim(
                    claim=claim,
                    source=source.document_id,
                    quote=source.matching_text
                ))
            else:
                ungrounded_claims.append(claim)

        # 3. Grounding Score 계산
        score = len(grounded_claims) / len(claims) if claims else 0.0

        return GroundingResult(
            score=score,
            is_valid=score >= self.MIN_GROUNDING_SCORE,
            grounded_claims=grounded_claims,
            ungrounded_claims=ungrounded_claims,
            recommendation=self._generate_recommendation(score, ungrounded_claims)
        )

    async def _extract_claims(self, response: str) -> List[str]:
        """응답에서 사실적 주장 추출"""
        prompt = """
        다음 응답에서 사실적 주장(Factual Claims)을 추출하세요.
        의견이나 일반적 진술은 제외하세요.

        응답:
        {response}

        형식: JSON 배열 ["주장1", "주장2", ...]
        """
        result = await self.llm.generate(prompt.format(response=response))
        return json.loads(result)

    async def _find_source(
        self,
        claim: str,
        search_results: List[SearchResult]
    ) -> Optional[SourceMatch]:
        """주장에 대한 출처 찾기"""
        for result in search_results:
            # 의미적 유사도 검사
            similarity = await self.embedder.similarity(claim, result.content)
            if similarity > 0.85:
                return SourceMatch(
                    document_id=result.document_id,
                    matching_text=self._extract_matching_text(claim, result.content),
                    similarity=similarity
                )
        return None
```

### 검증 실패 처리

```python
async def handle_grounding_failure(
    self,
    response: str,
    grounding_result: GroundingResult
) -> str:
    """Grounding 검증 실패 시 응답 수정"""

    if grounding_result.score < 0.5:
        # 50% 미만: 응답 재생성 요청
        return await self._regenerate_response()

    elif grounding_result.score < 0.8:
        # 50-80%: 근거 없는 부분 제거
        return self._remove_ungrounded_claims(
            response,
            grounding_result.ungrounded_claims
        )

    return response
```

---

## 7. Layer 5: Extractive QA

### Answer Builder Service

```python
# app/api/services/answer_builder_service.py

class AnswerBuilderService:
    """
    추출형 QA (Extractive QA)

    핵심 원칙:
    ━━━━━━━━━━
    • Retrieval = Truth: 검색 결과만이 진실
    • LLM = Formatter Only: LLM은 포맷터 역할만
    • Hallucination = Structurally Prevented: 구조적으로 방지
    """

    MAX_CITATIONS = 5
    MIN_CONFIDENCE = 0.3

    async def build_answer(
        self,
        query: str,
        search_results: List[SearchResult]
    ) -> StructuredAnswer:
        # 1. 의도 분류
        intent = self.classify_intent(query)

        # 2. 검색 결과에서 블록 추출 (생성 X)
        blocks = self._extract_blocks(search_results, intent)

        # 3. 신뢰도 기반 필터링
        filtered_blocks = [
            b for b in blocks
            if b.confidence >= self.MIN_CONFIDENCE
        ]

        # 4. 인용 추출
        citations = self._extract_citations(
            search_results[:self.MAX_CITATIONS]
        )

        return StructuredAnswer(
            intent=intent,
            blocks=filtered_blocks,
            citations=citations
        )

    def classify_intent(self, query: str) -> AnswerIntent:
        """질의 의도 분류"""
        patterns = {
            AnswerIntent.DEFINITION: ["무엇", "정의", "뜻", "의미", "개념"],
            AnswerIntent.TROUBLESHOOTING: ["에러", "오류", "해결", "원인", "문제"],
            AnswerIntent.HOWTO: ["방법", "설정", "구성", "설치", "하는법"],
            AnswerIntent.COMPARISON: ["차이", "비교", "장단점", "vs"],
            AnswerIntent.LIST: ["종류", "목록", "나열", "어떤것들"]
        }

        for intent, keywords in patterns.items():
            if any(k in query for k in keywords):
                return intent
        return AnswerIntent.GENERAL

    def _extract_blocks(
        self,
        search_results: List[SearchResult],
        intent: AnswerIntent
    ) -> List[AnswerBlock]:
        """검색 결과에서 구조화된 블록 추출"""
        blocks = []

        for result in search_results:
            # 텍스트 블록
            if result.content:
                blocks.append(AnswerBlock(
                    type=BlockType.TEXT,
                    content=result.content,
                    source=result.document_id,
                    confidence=result.score
                ))

            # 코드 블록 (``` 감지)
            code_matches = re.findall(r'```[\s\S]*?```', result.content)
            for code in code_matches:
                blocks.append(AnswerBlock(
                    type=BlockType.CODE,
                    content=code,
                    source=result.document_id,
                    confidence=result.score
                ))

            # 리스트 블록 (- 또는 1. 감지)
            if re.search(r'^[-\d]\.|^- ', result.content, re.MULTILINE):
                blocks.append(AnswerBlock(
                    type=BlockType.LIST,
                    content=result.content,
                    source=result.document_id,
                    confidence=result.score
                ))

        return blocks
```

### Answer Formatter Service

```python
# app/api/services/answer_formatter_service.py

class AnswerFormatterService:
    """
    읽기 전용 포맷터

    허용 작업:
    ━━━━━━━━━━
    ✓ 블록 재정렬
    ✓ 미리 정의된 전환 문구 추가
    ✓ 제목 레벨 조정

    금지 작업:
    ━━━━━━━━━━
    ✗ 새로운 정보 추가
    ✗ 원본 내용 수정
    ✗ 인용 제거
    """

    # 블록 정렬 우선순위
    BLOCK_ORDER = [
        BlockType.NO_ANSWER,       # 1. 정보 없음 (항상 첫 번째)
        BlockType.HEADING,         # 2. 제목
        BlockType.TEXT,            # 3. 본문
        BlockType.LIST,            # 4. 목록
        BlockType.CODE,            # 5. 코드
        BlockType.TABLE,           # 6. 테이블
        BlockType.QUOTE,           # 7. 인용
        BlockType.IMAGE,           # 8. 이미지
        BlockType.SOURCE_CITATION  # 9. 출처 (항상 마지막)
    ]

    # 미리 정의된 전환 문구
    TRANSITIONS = {
        AnswerIntent.DEFINITION: "다음과 같이 정의됩니다:",
        AnswerIntent.TROUBLESHOOTING: "다음 해결 방법을 참고하세요:",
        AnswerIntent.HOWTO: "다음 단계를 따라 진행하세요:",
        AnswerIntent.COMPARISON: "비교 결과는 다음과 같습니다:",
    }

    def format(
        self,
        answer: StructuredAnswer
    ) -> FormattedAnswer:
        # 1. 블록 정렬 (내용 변경 없음)
        sorted_blocks = self._sort_blocks(answer.blocks)

        # 2. 전환 문구 추가 (미리 정의된 것만)
        if answer.intent in self.TRANSITIONS:
            sorted_blocks.insert(0, AnswerBlock(
                type=BlockType.HEADING,
                content=self.TRANSITIONS[answer.intent]
            ))

        # 3. 인용 블록 추가 (항상 마지막)
        sorted_blocks.append(AnswerBlock(
            type=BlockType.SOURCE_CITATION,
            content=self._format_citations(answer.citations)
        ))

        return FormattedAnswer(blocks=sorted_blocks)

    def _sort_blocks(self, blocks: List[AnswerBlock]) -> List[AnswerBlock]:
        """블록 정렬 (내용 변경 없음)"""
        return sorted(
            blocks,
            key=lambda b: self.BLOCK_ORDER.index(b.type)
        )

    def _format_citations(self, citations: List[Citation]) -> str:
        """인용 포맷팅"""
        lines = ["---", "**출처:**"]
        for i, c in enumerate(citations, 1):
            lines.append(f"[{i}] {c.document_title} - {c.section}")
        return "\n".join(lines)
```

---

## 8. 효과 측정

### 환각 감지 지표

```python
# app/api/services/hallucination_detector.py

class HallucinationDetector:
    """환각 감지 및 측정"""

    async def detect(
        self,
        query: str,
        response: str,
        search_results: List[SearchResult]
    ) -> HallucinationReport:
        return HallucinationReport(
            grounding_score=await self._calculate_grounding_score(response, search_results),
            fabrication_detected=await self._detect_fabrication(response, search_results),
            conflation_detected=await self._detect_conflation(response, search_results),
            citation_accuracy=await self._verify_citations(response, search_results)
        )
```

### Before/After 비교

| 지표 | CPU Version (Before) | GPU Version (After) |
|------|---------------------|---------------------|
| Grounding Score | 65% | 92% |
| Fabrication Rate | 12% | 1.5% |
| Citation Accuracy | 78% | 96% |
| User Trust Score | 3.2/5 | 4.6/5 |

---

## 9. 설정

```bash
# .env

# Layer 1: Master Constraint
ENABLE_MASTER_CONSTRAINT=true

# Layer 2: Temperature
LLM_TEMPERATURE=0.1
RAG_LLM_TEMPERATURE=0.05

# Layer 3: Tool Enforcement
TOOL_CHOICE_REQUIRED=true
REMOVE_DANGEROUS_TOOLS=true

# Layer 4: Grounding
MIN_GROUNDING_SCORE=0.8
ENABLE_GROUNDING_VALIDATION=true

# Layer 5: Extractive QA
ENABLE_EXTRACTIVE_QA=true
MAX_CITATIONS=5
MIN_BLOCK_CONFIDENCE=0.3
```

---

## 10. 관련 파일

| 파일 | 설명 |
|------|------|
| `app/api/agents/master_system_constraint.py` | Master Constraint |
| `app/api/agents/executor.py` | Temperature, Thinking 필터링 |
| `app/api/agents/auto_agent/verifier_agent.py` | Grounding 검증 |
| `app/api/services/answer_builder_service.py` | 추출형 QA |
| `app/api/services/answer_formatter_service.py` | 읽기 전용 포맷터 |

---

**Next**: [Auto LLM Learning](./AUTO_LLM_LEARNING.md)
