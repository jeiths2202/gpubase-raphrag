# RAG Context Pollution Fix - Plan Document

> **Feature**: rag-context-pollution-fix
> **Created**: 2026-02-03
> **Updated**: 2026-02-20
> **Author**: Claude Opus 4.5 → Claude Opus 4.6
> **Status**: 📝 Plan Phase (Updated)

---

## 1. Problem Statement

### 1.1 발견된 문제

**문제 A: 청크 레벨 오염 (2026-02-03 발견)**:
- **질문**: "osctdlrmについて説明してください"
- **응답**: osctdlrm 설명 + **oscsiggen 설명까지 포함**
- **문제**: 사용자가 묻지 않은 명령어까지 응답에 포함됨

**문제 B: 히스토리 컨텍스트 오염 (2026-02-20 발견)**:
- **질문 1**: "tacfについて説明してください。" → 정상 응답
- **질문 2**: "tjesinitについて説明してください。" → **tacf 내용이 출력됨**
- **문제**: 이전 대화(tacf)의 내용이 다음 질문(tjesinit) 응답에 오염됨

### 1.2 Hallucination 유형

| 유형 | 설명 | 문제 A | 문제 B |
|------|------|--------|--------|
| **Chunk Pollution** | RAG에서 관련 없는 청크가 함께 검색됨 | ✅ | ❌ |
| **History Pollution** | 이전 대화 내용이 현재 응답에 오염 | ❌ | ✅ |
| Type Misclassification | 타입 분류 오류로 잘못된 정보 제공 | ❌ | ❌ |
| Fabrication | LLM이 존재하지 않는 정보 생성 | ❌ | ❌ |

### 1.3 근본 원인

**문제 A (Chunk Pollution):**
1. **청크 단위 문제**: PDF 파싱 시 여러 명령어가 하나의 청크에 포함
2. **Vector Search Top-K**: 유사한 명령어들이 함께 검색됨
3. **LLM 프롬프트 문제**: "검색된 모든 정보를 활용하라"는 지시
4. **Reranking 부재**: 검색 결과 중 관련성 낮은 것 필터링 없음

**문제 B (History Pollution) - 3단계 원인 체인:**

| 단계 | 위치 | 문제 |
|------|------|------|
| **Stage 1** | `AgenticRAGPage.tsx:346` | Frontend가 최근 10개 메시지를 `history`로 무조건 전송 (이전 tacf 대화 포함) |
| **Stage 2** | `agentic_rag_service.py:1777` | `_build_llm_context()`가 history를 검색 결과 **앞에** 배치 |
| **Stage 3** | `vllm_adapter.py:538` | `_extract_core_content()`가 20줄로 절단 → history(tacf)는 보존, 검색 결과(tjesinit)는 잘림 |

```
[Frontend] messages[-10:] → history (tacf Q&A 포함)
     ↓
[agentic_rag_service] _build_llm_context():
  context = history_text + "\n" + search_results
  # history가 앞에 → 최소 600~800자 차지
     ↓
[vllm_adapter] _extract_core_content(context):
  lines = context.split('\n')
  return '\n'.join(lines[:20])  # ← 20줄 절단!
  # history(tacf)가 20줄 안에 들어감
  # search_results(tjesinit)는 잘려나감
     ↓
[LLM] tacf 정보만 보고 응답 생성 → tjesinit 질문에 tacf 답변
```

---

## 2. Investigation Plan

### 2.1 문제 A: Chunk Pollution 조사 (완료)

| 조사 항목 | 방법 | 도구 | 상태 |
|-----------|------|------|------|
| osctdlrm 청크 확인 | Neo4j 직접 쿼리 | Cypher | ✅ |
| oscsiggen 청크 확인 | Vector Search 결과 분석 | API | ✅ |
| 청크 내용 검토 | RAG 응답 소스 확인 | WebUI | ✅ |

### 2.2 문제 B: History Pollution 조사 (2026-02-20 완료)

| 조사 항목 | 결과 |
|-----------|------|
| Frontend history 전송 확인 | `AgenticRAGPage.tsx:346` - 최근 10개 메시지 무조건 전송 |
| Backend history 배치 확인 | `agentic_rag_service.py:1777` - history가 search results **앞에** 배치 |
| VLLMAdapter 절단 확인 | `vllm_adapter.py:538` - `_extract_core_content()` 20줄 절단 |
| API 단독 테스트 (history 없음) | ✅ 정상 응답 (tjesinit 내용만 반환) |
| API 테스트 (tacf history 포함) | ✅ 정상 (짧은 history → 절단 안 됨) |
| 결론 | **긴 대화 + 상세 응답** 시 history가 20줄 한계 채우면 발생 |

**핵심 코드 경로:**
```
AgenticRAGPage.tsx:346 → history 전송
  → agentic_rag_service.py:1727 → _build_llm_context()
    → history_text (800자 제한) + search_results
      → learning_llm_service.py:223 → generate_stream(context=built_context)
        → vllm_adapter.py:538 → _extract_core_content(context) → 20줄 절단
```

---

## 3. Proposed Solutions

### 문제 A: Chunk Pollution 해결안 (기존)

#### 3.1 Solution A: 청크 필터링 (Post-Retrieval)

검색 후 관련성 낮은 청크를 필터링하는 방식

```python
def filter_irrelevant_chunks(query: str, chunks: List[Chunk]) -> List[Chunk]:
    """질문과 관련 없는 청크 필터링"""
    query_keywords = extract_keywords(query)  # ['osctdlrm']
    filtered = []
    for chunk in chunks:
        if any(kw in chunk.content.lower() for kw in query_keywords):
            filtered.append(chunk)
    return filtered
```

**장점**: 구현 간단, 기존 코드 변경 최소화
**단점**: 키워드 매칭에 의존, 동의어 처리 어려움

#### 3.2 Solution B: LLM 프롬프트 강화

RAG Agent 프롬프트에 "질문에 대한 정보만 응답" 지시 추가

**장점**: 코드 변경 없이 동작 개선 가능
**단점**: LLM이 지시를 무시할 수 있음

#### 3.3 Solution C: Re-ranking 도입

Cross-Encoder 기반 Re-ranking으로 관련성 점수 재계산

**장점**: 가장 정확한 필터링
**단점**: 추가 모델 필요, 지연시간 증가

#### 3.4 Solution D: Entity-Based Filtering

질문에서 추출한 Entity 기반 필터링

**장점**: Entity 매칭으로 정확도 높음
**단점**: Entity 추출 정확도에 의존

---

### 문제 B: History Pollution 해결안 (2026-02-20 추가)

#### 3.5 Solution E: `_extract_core_content()` 절단 방식 개선 (CRITICAL)

**현재**: 20줄 무차별 절단 → history가 앞에 있어 보존됨
**수정**: search results를 우선 보존하는 구조적 절단

```python
# vllm_adapter.py - _extract_core_content()
def _extract_core_content(self, context: str) -> Optional[str]:
    """검색 결과 우선 보존하는 컨텍스트 절단"""
    if not context or not context.strip():
        return None

    # 히스토리와 검색 결과 영역 분리
    # _build_llm_context()가 "---" 구분자로 분리하도록 수정
    parts = context.split("---\n", 1)
    if len(parts) == 2:
        history_part, search_part = parts
        # 검색 결과 우선 (최대 15줄), 나머지에 history (최대 5줄)
        search_lines = [l for l in search_part.strip().split('\n') if l.strip()][:15]
        history_lines = [l for l in history_part.strip().split('\n') if l.strip()][:5]
        return '\n'.join(history_lines + ['---'] + search_lines)

    # 구분자 없으면 기존 동작 (backward compatible)
    lines = [l for l in context.split('\n') if l.strip()]
    return '\n'.join(lines[:20])
```

**장점**: 근본 원인 해결, 검색 결과가 항상 LLM에 전달됨
**단점**: `_build_llm_context()`와 `_extract_core_content()` 양쪽 수정 필요

#### 3.6 Solution F: `_build_llm_context()` 배치 순서 변경

**현재**: history → search_results (history가 앞에)
**수정**: search_results → history (검색 결과가 앞에)

```python
# agentic_rag_service.py - _build_llm_context()
def _build_llm_context(self, search_results, history, ...):
    # Before: context = history_text + "\n" + search_text
    # After:  context = search_text + "\n---\n" + history_text
    context = search_text  # 검색 결과 우선
    if history_text:
        context += f"\n---\n대화 이력:\n{history_text}"
    return context
```

**장점**: 간단한 수정, `_extract_core_content()` 20줄 절단 시 검색 결과 보존
**단점**: history가 잘리지만 검색 정확도 향상

#### 3.7 Solution G: Agentic RAG에서 `system_prompt` 경로 사용

Modernization AI Chat과 동일한 패턴으로, Agentic RAG도 `system_prompt` 파라미터를 사용하여 `_extract_core_content()` 절단을 우회

```python
# agentic_rag_service.py - _stream_llm()
async def _stream_llm(self, query, context, product, ...):
    # system_prompt로 전달하면 _extract_core_content() 우회
    async for token in llm_service.generate_stream(
        question=query,
        system_prompt=f"以下の検索結果に基づいて回答してください:\n{context}",
        product=adapter_product,
    ):
        yield token
```

**장점**: 절단 없이 전체 컨텍스트 전달, 이미 구현된 인프라 활용
**단점**: system prompt가 길어질 수 있음, vLLM token 제한 주의

---

## 4. Recommended Approach

### 4.1 단계별 구현 계획

| Phase | Solution | 대상 문제 | 난이도 | 효과 | 상태 |
|-------|----------|----------|--------|------|------|
| **Phase 1** | F. 컨텍스트 배치 순서 변경 | History Pollution | 낮음 | 높음 | ⏳ |
| **Phase 2** | E. `_extract_core_content()` 개선 | History Pollution | 중간 | 높음 | ⏳ |
| **Phase 3** | B. LLM 프롬프트 강화 | Chunk Pollution | 낮음 | 중간 | ⏳ |
| Phase 4 | A. 키워드 기반 필터링 (선택) | Chunk Pollution | 중간 | 높음 | ⏳ |

### 4.2 Phase 1: History 배치 순서 변경 (즉시 적용)

**수정 파일**: `app/api/services/agentic_rag_service.py`
**수정 위치**: `_build_llm_context()` (line 1727-1778)

현재: `history_text + search_results` → 변경: `search_results + "---" + history_text`

검색 결과가 항상 앞에 위치하여, `_extract_core_content()` 20줄 절단 시에도 검색 결과가 보존됨.

### 4.3 Phase 2: `_extract_core_content()` 구조적 절단

**수정 파일**: `app/api/adapters/learning_llm/vllm_adapter.py`
**수정 위치**: `_extract_core_content()` (line 525-538)

`---` 구분자를 인식하여 검색 결과(15줄)와 히스토리(5줄)를 별도 할당.

### 4.4 Phase 3: 프롬프트 강화 (선택)

**수정 파일**: `app/api/agents/prompts/rag_agent.txt`

```markdown
## CRITICAL: 응답 범위 제한 (Context Pollution 방지)

1. **질문 분석**: 사용자가 물어본 구체적인 항목 식별
   - 예: "osctdlrmについて" → osctdlrm만 설명

2. **무관한 정보 제외**: 검색 결과에 다른 명령어/개념이 포함되어 있어도:
   - 질문에서 언급되지 않은 항목은 응답에서 제외
   - "또한", "관련하여" 등으로 다른 명령어 추가 설명 금지
```

---

## 5. Success Criteria

| 기준 | 목표 | 측정 방법 |
|------|------|----------|
| **tjesinit → tacf 오염 해소** | tacf 내용 미포함 | 대화 연속 테스트 |
| osctdlrm 단독 질문 | oscsiggen 미포함 | E2E 테스트 |
| 명령어 단독 질문 전체 | 다른 명령어 미포함 | 45개 케이스 재테스트 |
| RAG 응답 정확도 | Hallucination -50% | E2E 결과 비교 |
| 응답 지연시간 | +500ms 이내 | 성능 테스트 |
| **검색 결과 보존율** | 절단 후 검색 결과 80% 이상 보존 | 로그 분석 |

---

## 6. Risk Assessment

| 위험 | 영향 | 대응 |
|------|------|------|
| 과도한 필터링 | 필요한 정보도 제외 | min_match 조정, 폴백 로직 |
| 프롬프트 무시 | LLM이 지시 따르지 않음 | 코드 필터링 추가 |
| 성능 저하 | 응답 지연 | Re-ranking 선택적 적용 |
| **history 절단으로 맥락 손실** | 후속 질문 이해도 저하 | history 5줄 최소 보장 |
| **배치 순서 변경 부작용** | 기존 동작에 영향 | backward compatible 구분자 사용 |

---

## 7. 수정 대상 파일 목록

| 파일 | 수정 내용 | Phase |
|------|----------|-------|
| `app/api/services/agentic_rag_service.py` | `_build_llm_context()` 배치 순서: search → history | Phase 1 |
| `app/api/adapters/learning_llm/vllm_adapter.py` | `_extract_core_content()` 구분자 인식 절단 | Phase 2 |
| `app/api/agents/prompts/rag_agent.txt` | 응답 범위 제한 프롬프트 추가 | Phase 3 |

---

## 8. Timeline

| Phase | 작업 | 예상 시간 |
|-------|------|----------|
| Phase 1 | `_build_llm_context()` 배치 순서 변경 | 30분 |
| Phase 2 | `_extract_core_content()` 구조적 절단 | 1시간 |
| Phase 3 | 프롬프트 수정 (선택) | 30분 |
| 검증 | tjesinit/tacf 연속 대화 테스트 | 30분 |
| Total | | 2.5시간 |

---

## 9. Next Steps

1. **즉시**: `_build_llm_context()` 검색 결과 → 히스토리 순서로 변경
2. **검증**: tjesinit after tacf 연속 대화 테스트
3. **Phase 2**: 효과 부족시 `_extract_core_content()` 구조적 절단 구현

---

**다음 단계**: `/pdca design rag-context-pollution-fix`
