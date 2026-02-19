# Plan: Source Code Explanation Feature

## Feature Overview

**Feature**: `source-code-explanation`
**Created**: 2026-02-19
**Status**: Plan Phase

### Summary

"모더나이제이션AI" Chat 입력창에서 사용자가 "이 소스에 대해서 설명해줘" 또는 "이 소스에 대해서 상세한 설명해줘"와 같이 화면에 표시된 소스코드(JCL, COBOL, COPYBOOK, ASM 등)에 대해 라인별 기능 설명을 요청하면, 소스 전문을 읽어 LLM으로 분석한 뒤 ChatUI에 구조화된 설명을 출력하는 기능.

---

## Problem Statement

### 현재 상태
1. **소스 코드 전송 제한**: `AnalysisContext.source_code_snippet`은 `max_length=2000`으로 제한 (약 30~50줄)
2. **프론트엔드 슬라이싱**: `LegacyModernizationPage.tsx`에서 `sourceCode.slice(0, 2000)` 전달
3. **백엔드 추가 슬라이싱**: `chat_adapter.py:78`에서 `ctx["source_code_snippet"][:1000]`으로 1000자만 사용
4. **의도 감지 없음**: "이 소스에 대해서 설명해줘" 같은 소스 설명 요청을 일반 질문과 동일하게 처리
5. **max_new_tokens=1024**: 긴 소스코드 설명에는 토큰 수 부족

### 필요한 기능
- 사용자가 소스 설명을 요청하면 전체 소스코드를 LLM에 전달
- 라인별/섹션별 구조화된 설명 생성
- ChatUI에서 소스 설명을 가독성 있게 표시

---

## Technical Analysis

### 현재 데이터 흐름

```
[LegacyModernizationPage.tsx]
  sourceCode.slice(0, 2000) → analysisContext.sourceCodeSnippet
    ↓
[useModernizationChat.ts:173-181]
  body.analysis_context.source_code_snippet = sourceCodeSnippet
    ↓
[POST /legacy/chat/stream]
    ↓
[chat_schemas.py] AnalysisContext.source_code_snippet (max_length=2000)
    ↓
[chat_service.py:84] → _stream_host(request)
    ↓
[chat_adapter.py:66-80] _build_analysis_context()
  ctx["source_code_snippet"][:1000] → system prompt에 삽입
    ↓
[VLLMAdapter.generate_stream(max_new_tokens=1024)]
```

### 수정 대상 파일

| 파일 | 변경 유형 | 변경 내용 |
|------|-----------|-----------|
| `kms-portal-ui/src/pages/LegacyModernizationPage.tsx` | 수정 | 소스 전문 전달 (슬라이싱 제거) |
| `kms-portal-ui/src/components/ModernizationAI/useModernizationChat.ts` | 수정 | `source_code_full` 필드 추가 전송 |
| `kms-portal-ui/src/components/ModernizationAI/types.ts` | 수정 | `AnalysisContextInfo` 타입에 `sourceCodeFull` 추가 |
| `app/api/legacy_modernization/routers/chat_schemas.py` | 수정 | `AnalysisContext`에 `source_code_full` 필드 추가 |
| `app/api/legacy_modernization/agents/chat_adapter.py` | 수정 | 소스 설명 의도 감지 + 전용 프롬프트 + 토큰 증가 |
| `kms-portal-ui/src/i18n/locales/{en,ko,ja}/legacy.json` | 수정 | 소스 설명 관련 i18n 키 추가 |

---

## Implementation Plan

### Phase 1: 백엔드 - 스키마 확장

**File**: `app/api/legacy_modernization/routers/chat_schemas.py`

- `AnalysisContext`에 `source_code_full: Optional[str]` 필드 추가 (max_length=100000)
- 기존 `source_code_snippet` (2000자)은 하위 호환을 위해 유지

### Phase 2: 백엔드 - 의도 감지 + 전용 프롬프트

**File**: `app/api/legacy_modernization/agents/chat_adapter.py`

1. **소스 설명 의도 감지 함수** `_is_source_explanation_request(message: str) -> bool`:
   - 한국어: "이 소스", "소스 설명", "소스코드 설명", "코드 설명", "라인별 설명"
   - 일본어: "このソース", "ソース説明", "ソースコード説明", "コード説明", "行ごと"
   - 영어: "explain this source", "explain this code", "line by line", "describe this code"

2. **전용 시스템 프롬프트** `_SOURCE_EXPLANATION_PROMPT`:
   - 소스 타입별 분석 지시 (JCL: JOB/EXEC/DD, COBOL: DIVISION/SECTION/PARAGRAPH, ASM: CSECT/MACRO/INSTRUCTION)
   - 라인별/섹션별 구조화된 설명 출력 포맷 지정
   - Markdown 포맷 (헤더, 코드블록, 테이블) 사용 지시

3. **stream_chat 수정**:
   - `_is_source_explanation_request()` → True이면:
     - `source_code_full` 사용 (없으면 `source_code_snippet` fallback)
     - `_SOURCE_EXPLANATION_PROMPT` 사용
     - `max_new_tokens` 증가 (1024 → 4096)
     - `temperature` 낮춤 (0.3 → 0.1, 정확성 우선)

### Phase 3: 프론트엔드 - 소스 전문 전달

**File**: `kms-portal-ui/src/pages/LegacyModernizationPage.tsx`

- `analysisContext`에 `sourceCodeFull: sourceCode` 추가 (전체 소스, 슬라이싱 없음)
- 기존 `sourceCodeSnippet: sourceCode.slice(0, 2000)` 유지 (일반 질문용)

**File**: `kms-portal-ui/src/components/ModernizationAI/useModernizationChat.ts`

- `body.analysis_context`에 `source_code_full: analysisContext.sourceCodeFull` 추가
- 소스 설명 요청 시에만 전송하는 최적화 (선택적)

**File**: `kms-portal-ui/src/components/ModernizationAI/types.ts`

- `AnalysisContextInfo` 인터페이스에 `sourceCodeFull?: string` 추가

### Phase 4: i18n 업데이트

3개 언어 파일에 소스 설명 관련 텍스트 추가:
- `ai.sourceExplanationHint`: 소스 설명 기능 안내 텍스트

---

## Design Constraints

1. **소스 코드 크기 제한**: `source_code_full`은 최대 100KB (약 2000~3000줄) - Qwen 32K context window 대비 충분
2. **하위 호환성**: 기존 `source_code_snippet` 유지, `source_code_full`은 Optional
3. **LLM 부하**: 소스 설명은 HOST 모드에서만 동작 (OpenFrame RAG는 기존 플로우 유지)
4. **토큰 비용**: 소스 설명 요청에만 max_new_tokens=4096 적용, 일반 채팅은 기존 1024 유지

---

## Success Criteria

- [ ] "이 소스에 대해서 설명해줘" 입력 시 전체 소스코드 라인별 설명 출력
- [ ] JCL, COBOL, ASM, MAP 4개 타입 모두 구조화된 설명 지원
- [ ] 한국어, 일본어, 영어 3개 언어 의도 감지 동작
- [ ] 일반 채팅 질문에는 기존 동작 영향 없음
- [ ] 소스코드가 없는 상태에서 "이 소스 설명해줘" 요청 시 안내 메시지 출력

---

## Risk Assessment

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 긴 소스코드로 LLM context 초과 | 응답 품질 저하 | 100KB 제한 + context window 50% 이내 유지 |
| 대용량 소스 전송 네트워크 부하 | 응답 지연 | 소스 설명 요청 시에만 전문 전송 |
| 의도 감지 오탐 | 일반 질문에 소스 설명 시도 | 키워드 매칭 + 소스코드 존재 여부 AND 조건 |
| Streaming 중 긴 대기 시간 | UX 저하 | "소스코드를 분석중입니다..." 진행 상태 SSE 이벤트 |

---

## Implementation Order

```
1. chat_schemas.py (스키마 확장) ← 의존성 없음
2. chat_adapter.py (의도 감지 + 프롬프트) ← 1에 의존
3. types.ts (타입 확장) ← 의존성 없음
4. LegacyModernizationPage.tsx (전문 전달) ← 3에 의존
5. useModernizationChat.ts (API 전송) ← 3에 의존
6. legacy.json × 3 (i18n) ← 의존성 없음
```

병렬 가능: (1 + 3 + 6) → (2 + 4 + 5)
