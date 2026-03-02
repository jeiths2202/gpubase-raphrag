# Plan: Qwen3 Think Mode Toggle

## Feature Name
`qwen3-think-toggle`

## Overview
Agent RAG 화면 오른쪽 상단 툴바에 **Think 체크 버튼**을 추가하여, 사용자가 Qwen3의 Thinking Mode(내부 추론)를 ON/OFF 할 수 있도록 구현합니다.

## Background
- Qwen3-32B는 `<think>...</think>` 태그로 chain-of-thought 추론을 생성하는 기능을 가짐
- 현재 `enable_thinking: False`로 하드코딩되어 있어 항상 비활성
- Think ON: 내부 추론 후 답변 → 품질 향상, 응답 시간 증가 (~100s)
- Think OFF: 바로 답변 → 빠른 응답 (~20s)
- 사용자가 상황에 따라 선택할 수 있어야 함

## Requirements

### FR-01: Think 토글 UI
- Agent RAG 페이지 상단 툴바에 체크박스 추가
- 위치: Special 체크박스와 Product Dropdown 사이
- 라벨: "Think" (Brain 아이콘)
- 기본값: OFF (체크 해제)

### FR-02: Think ON 동작
- 체크 시 `enable_thinking: true`가 API 요청에 포함
- vLLM에서 `<think>` 블록을 생성함
- `<think>` 블록은 **별도 UI 영역(접힌 상태)**으로 표시
- 응답 본문은 `</think>` 이후만 표시

### FR-03: Think OFF 동작 (기본)
- 현재와 동일한 동작 유지
- `enable_thinking: false` 전송 → `<think>` 토큰 생성 안됨
- 기존 safety filter는 이중 안전장치로 유지

### FR-04: Think 블록 UI 표시
- Think ON일 때 SSE 스트림에서 `<think>` 블록 감지
- 접을 수 있는 "Thinking..." 패널로 표시 (기본: 접힌 상태)
- 사용자가 클릭하면 내부 추론 과정을 볼 수 있음

## Architecture

### Data Flow
```
[Frontend]                  [Backend]                    [vLLM]
Think 체크 ──→ enable_thinking ──→ generate_stream() ──→ chat_template_kwargs
    │              (API 요청)        (서비스 체인)        {"enable_thinking": true/false}
    │                                    │
    │         ← SSE: <think>... ←────────┘
    │         ← SSE: </think>
    │         ← SSE: 응답 토큰들
    ↓
Think Panel (접힌 상태)
응답 본문 표시
```

### Parameter Chain
```
AgenticRAGPage.tsx (state: enableThinking)
  → AgenticRAGRequest (field: enable_thinking)
    → agentic_rag.py router (passthrough)
      → openframe_rag_service.py chat_stream()
        → learning_llm_service.generate_stream(enable_thinking=)
          → vllm_adapter.py generate_stream(enable_thinking=)
            → payload["chat_template_kwargs"]["enable_thinking"]
```

## Scope

### 수정 파일 목록

| Layer | File | Changes |
|-------|------|---------|
| **Frontend** | `kms-portal-ui/src/pages/AgenticRAGPage.tsx` | Think 체크박스 UI + state + 요청 payload |
| **Frontend** | `kms-portal-ui/src/api/agentic-rag.api.ts` | `enable_thinking` 필드 추가 |
| **Frontend** | `kms-portal-ui/src/i18n/locales/en/common.json` | i18n: "Think" |
| **Frontend** | `kms-portal-ui/src/i18n/locales/ko/common.json` | i18n: "Think" |
| **Frontend** | `kms-portal-ui/src/i18n/locales/ja/common.json` | i18n: "Think" |
| **Backend** | `app/api/models/agentic_rag.py` | `enable_thinking: bool` 필드 추가 |
| **Backend** | `app/api/services/openframe_rag_service.py` | 파라미터 전달 + think 블록 SSE 이벤트 분리 |
| **Backend** | `app/api/services/learning_llm_service.py` | `enable_thinking` 파라미터 추가 |
| **Backend** | `app/api/adapters/learning_llm/vllm_adapter.py` | 하드코딩 → 파라미터화 |

### 수정하지 않는 것
- `app/api/routers/agentic_rag.py` — Request 모델 변경으로 자동 반영
- `app/api/models/openframe_rag.py` — OpenFrame RAG 전용 (별도 경로)
- vLLM 서버 설정 — 이미 chat_template_kwargs 지원

## Implementation Details

### 1. Frontend: AgenticRAGPage.tsx

**State 추가** (line ~139):
```typescript
const [enableThinking, setEnableThinking] = useState(false);
```

**Toolbar UI** (Special과 Product Dropdown 사이):
```tsx
<label className="toolbar-toggle think-toggle" title="Qwen3 Think Mode">
  <input
    type="checkbox"
    checked={enableThinking}
    onChange={(e) => setEnableThinking(e.target.checked)}
  />
  <Brain size={14} />
  <span>Think</span>
</label>
```

**Request payload** (line ~340-353):
```typescript
const request: AgenticRAGRequest = {
  // ... existing fields ...
  enable_thinking: enableThinking,
};
```

**SSE think 블록 처리** (line ~500 부근):
```typescript
// Think 블록 감지 및 분리
if (enableThinking) {
  // type: "think_token" → thinkContent에 축적
  // type: "token" → 본문에 축적
}
```

### 2. Backend: openframe_rag_service.py

**think 블록 SSE 이벤트 분리** (line 405-432 수정):
```python
if request.enable_thinking:
    # think 블록을 별도 이벤트로 전송
    # type: "think_token" → 프론트엔드에서 Think 패널에 표시
    # type: "token" → 본문 표시
else:
    # 기존 동작 유지 (enable_thinking=False → <think> 생성 안됨)
```

### 3. Backend: vllm_adapter.py

**하드코딩 제거** (line 409-410):
```python
# Before:
"chat_template_kwargs": {"enable_thinking": False},

# After:
"chat_template_kwargs": {"enable_thinking": enable_thinking},
```

## UI Mockup

```
┌─────────────────────────────────────────────────────────────────┐
│ ⟳  +  🔗  [RAG│Code│Plan]  ☐ Special  ☐ Think  [Auto▼]  🗑   │
│─────────────────────────────────────────────────────────────────│
│                                                                 │
│  User: tjesmgrコマンドの使い方を教えてください                      │
│                                                                 │
│  ▶ Thinking... (click to expand)                                │
│  ┌─────────────────────────────────────────────┐               │
│  │ (접힌 상태 - 클릭 시 think 내용 표시)          │               │
│  └─────────────────────────────────────────────┘               │
│                                                                 │
│  tjesmgr コマンドは OpenFrame の TJES に関連し...                 │
│                                                                 │
│  질문을 입력してください...                            [▷]        │
└─────────────────────────────────────────────────────────────────┘
```

## Performance Impact

| Mode | 응답 시간 | 토큰 사용량 | 품질 |
|------|----------|-----------|------|
| Think OFF (기본) | ~20-23s | ~500 tokens | 양호 |
| Think ON | ~60-100s | ~1500-3000 tokens | 향상 (추론 포함) |

## Verification

1. Think OFF: 기존 동작과 100% 동일 확인
2. Think ON: `<think>` 블록이 Think 패널에 표시되는지 확인
3. Think ON: 응답 본문에 `<think>` 태그 누출 없음 확인
4. API: `enable_thinking` 필드가 SSE에 정상 전달되는지 확인
5. i18n: 3개 언어 라벨 표시 확인

## Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| Think ON 시 응답 시간 증가 | UI에 "Think 모드는 응답이 느릴 수 있습니다" 툴팁 표시 |
| `<think>` 태그 파싱 실패 | 기존 safety filter (2차 방어) 유지 |
| 기본값 변경 우려 | `enable_thinking: false`가 기본 → 100% 하위 호환 |
