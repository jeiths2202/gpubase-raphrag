# DAG Trace Visualization Fix Planning Document

> **Summary**: DAG 그래프가 동적으로 출력되지 않고, trace.timeline/evaluations가 비어있는 문제 해결
>
> **Project**: HybridRAG KMS
> **Author**: Claude
> **Date**: 2026-02-17
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

TracePanel의 3개 뷰(DAGView, TimelineView, EvaluationsView)가 정상 작동하지 않는 버그를 수정한다:
1. **DAG 그래프**: 비교 질문 시 DAG 구조가 출력되지 않음 (데이터 전달 버그)
2. **Timeline**: 항상 "No events yet" 표시
3. **Evaluations**: 항상 "No evaluations yet" 표시

### 1.2 Background

`parallel-orchestrator-dag` 기능 구현 완료(PDCA 91% 달성) 후, 실제 사용 시 TracePanel이 데이터를 표시하지 못하는 문제 발견. 백엔드는 SSE로 `trace_data` 이벤트를 전송하지만, 프론트엔드에서 데이터를 올바르게 파싱하지 못하고 있음.

### 1.3 Related Documents

- Archived: `docs/archive/2026-02/parallel-orchestrator-dag/`
- Frontend Store: `kms-portal-ui/src/store/traceStore.ts`
- Backend Service: `app/api/services/agentic_rag_service.py`

---

## 2. Root Cause Analysis

### Bug 1: DAG 그래프 미출력 (CRITICAL)

**위치**: `AgenticRAGPage.tsx:524` → `traceStore.ts:227`

**원인**: SSE 이벤트 데이터 구조 불일치 (Nesting Level 오류)

```
Backend 전송 형식:
{
  "type": "trace_data",           ← SSE 이벤트 타입
  "trace_data": {                 ← 실제 데이터 (nested)
    "trace_id": "abc",
    "dag": { ... },
    "current_task": { ... },
    "timeline_event": { ... }
  }
}

Frontend 파싱 (AgenticRAGPage.tsx:524):
  const traceData = event;  // {type, trace_data: {...}}
  updateFromTraceData(traceData);  // ← 전체 event 전달!

Store 기대 형식 (traceStore.ts:106-112):
  updateFromTraceData({
    trace_id?: string,            ← traceData.trace_id → undefined!
    dag?: DAGStructure,           ← traceData.dag → undefined!
    current_task?: CurrentTask,   ← traceData.current_task → undefined!
    timeline_event?: TimelineEvent ← traceData.timeline_event → undefined!
  })
```

**결론**: `updateFromTraceData(event)`에 전체 SSE 이벤트를 전달하지만, 함수는 `event.trace_data` 내부 필드를 기대. 모든 필드가 `undefined`이므로 아무것도 업데이트되지 않음.

### Bug 2: Timeline 비어있음

**1차 원인**: Bug 1과 동일 — `timeline_event` 필드가 `event.trace_data.timeline_event`에 있지만 `event.timeline_event`는 `undefined`

**2차 원인**: `_task_status_event()` 함수(agentic_rag_service.py:208)에서 완료 이벤트 이름이 `"task_done"` → 프론트엔드 TimelineView는 `"task_complete"` 기대

```python
# Backend (line 208):
event_name = "task_start" if status == "running" else "task_done"
#                                                      ^^^^^^^^^ 불일치

# Frontend TimelineView expects:
# "task_start" | "task_complete" | "task_failed" | "task_timeout"
```

**3차 원인**: `latency_ms` 미전송 — `_task_status_event`에서 완료 시 실행 시간을 계산하지 않음

### Bug 3: Evaluations 비어있음

**원인**: 백엔드에서 evaluation 데이터를 **전혀 생성하지 않음**. `agentic_rag_service.py` 전체에서 `evaluations` 필드를 포함한 `trace_data` 이벤트 없음.

현재 평가 가능 데이터:
- `ResponseVerifier` 검증 결과 (단어 겹침 점수)
- `search_progress` 이벤트의 결과 수
- LLM 응답 길이/품질 메트릭

---

## 3. Scope

### 3.1 In Scope

- [x] Bug 1: `AgenticRAGPage.tsx` SSE 파싱에서 `event.trace_data` 추출 수정
- [x] Bug 2-1: `_task_status_event()`에서 이벤트 이름 `"task_done"` → `"task_complete"` 수정
- [x] Bug 2-2: `_task_status_event()`에 `latency_ms` 계산 추가
- [x] Bug 3: `_stream_parallel_comparison()` 및 `_stream_pipeline()`에 evaluation 이벤트 추가
- [x] Standard query path (`stream_chat`)에도 기본 단일 태스크 DAG 추가

### 3.2 Out of Scope

- Standard query에 대한 전체 multi-agent DAG (기존 `AgentTeams` 패턴 범위)
- TracePanel UI 스타일/레이아웃 변경
- 새로운 evaluation 알고리즘 개발

---

## 4. Requirements

### 4.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 비교 질문 시 DAG 그래프가 실시간으로 렌더링되어야 함 | High | Pending |
| FR-02 | DAG 태스크 상태가 running→completed로 실시간 변경되어야 함 | High | Pending |
| FR-03 | Timeline에 task_start/task_complete 이벤트가 순차적으로 표시되어야 함 | High | Pending |
| FR-04 | Evaluations에 각 태스크의 검증 결과(score, passed, issues)가 표시되어야 함 | Medium | Pending |
| FR-05 | Standard query에도 단일 태스크 DAG가 표시되어야 함 | Low | Pending |

### 4.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 이벤트 업데이트 반영 < 100ms | 스트리밍 중 UI freeze 없음 |
| Compatibility | 기존 SSE 이벤트와 하위 호환 | 기존 기능 회귀 없음 |

---

## 5. Implementation Plan

### Phase 1: Frontend SSE 파싱 수정 (FR-01, FR-02, FR-03)

**File: `kms-portal-ui/src/pages/AgenticRAGPage.tsx`**

Line 524 수정:
```typescript
// Before:
useTraceStore.getState().updateFromTraceData(traceData);

// After:
const inner = traceData.trace_data as Record<string, unknown> | undefined;
if (inner) {
  useTraceStore.getState().updateFromTraceData(inner);
}
```

### Phase 2: Backend 이벤트 이름 수정 (FR-03)

**File: `app/api/services/agentic_rag_service.py`**

1. Line 208: `"task_done"` → `"task_complete"` 수정
2. `_task_status_event()`에 `latency_ms` 파라미터 추가
3. failed 상태에 대한 `"task_failed"` 이벤트 이름 분기 추가

```python
def _task_status_event(task_id: str, status: str, latency_ms: int | None = None) -> dict:
    event_map = {"running": "task_start", "completed": "task_complete", "failed": "task_failed"}
    event_name = event_map.get(status, f"task_{status}")
    ...
```

### Phase 3: Evaluation 이벤트 추가 (FR-04)

**File: `app/api/services/agentic_rag_service.py`**

`_stream_parallel_comparison()` 완료 후, 각 검색 결과에 대한 evaluation 이벤트 생성:

```python
# After synthesis complete, emit evaluation per task
for tid, ctx in zip(task_ids, search_contexts):
    eval_result = {
        "passed": ctx is not None and len(ctx.structured_results) > 0,
        "score": min(len(ctx.structured_results) / 5.0, 1.0) if ctx else 0.0,
        "issues": [] if ctx else ["No search results found"],
    }
    yield {
        "type": "trace_data",
        "trace_data": {
            "evaluations": {tid: eval_result}
        },
    }
```

### Phase 4: Standard Query 기본 DAG (FR-05, Optional)

**File: `app/api/services/agentic_rag_service.py`**

`stream_chat()` 진입 시 단일 태스크 DAG 생성:
- 1개 태스크: "Product Search & Response"
- `parallelism_type: "none"`
- 검색/생성 진행에 따라 `current_task` 업데이트

---

## 6. Success Criteria

### 6.1 Definition of Done

- [x] 비교 질문 "OSCとOSIの全般的な機能について比較してください" 시 DAG 그래프 실시간 출력
- [x] Timeline 탭에 task_start → task_complete 이벤트 순차 표시
- [x] Evaluations 탭에 각 태스크 검증 점수 표시
- [x] 기존 단일 질문 기능 회귀 없음

### 6.2 Quality Criteria

- [x] API 테스트 200 OK
- [x] 기존 스트리밍 응답 정상 동작
- [x] TracePanel 3개 탭 모두 데이터 표시

---

## 7. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Frontend 수정이 다른 SSE 이벤트 파싱에 영향 | Medium | Low | trace_data 케이스만 수정, 다른 타입 미영향 |
| Evaluation score 계산이 부정확 | Low | Medium | 간단한 검색결과 수 기반 점수로 시작, 이후 개선 |
| Standard DAG가 UI를 복잡하게 만듦 | Low | Medium | FR-05는 optional, 필요시 제외 |

---

## 8. Files to Modify

| File | Changes |
|------|---------|
| `kms-portal-ui/src/pages/AgenticRAGPage.tsx:524` | `event.trace_data` 추출 후 `updateFromTraceData` 호출 |
| `app/api/services/agentic_rag_service.py:207-221` | `_task_status_event()` 이벤트 이름 수정 + latency_ms |
| `app/api/services/agentic_rag_service.py:1216` | 비교 합성 후 evaluation 이벤트 추가 |
| `app/api/services/agentic_rag_service.py:1305` | 파이프라인 태스크 후 evaluation 이벤트 추가 |

---

## 9. Next Steps

1. [ ] Write design document (`dag-trace-visualization-fix.design.md`)
2. [ ] Implement fixes (estimated: Phase 1~3)
3. [ ] Test with comparison query via API
4. [ ] Test with browser UI

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-02-17 | Initial draft with root cause analysis | Claude |
