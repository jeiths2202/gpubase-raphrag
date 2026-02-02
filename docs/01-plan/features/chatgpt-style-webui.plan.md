# Plan: ChatGPT-Style Chat WebUI

**Feature**: chatgpt-style-webui
**Created**: 2026-02-03
**Status**: Planning
**PDCA Phase**: Plan

---

## 1. Overview

### 1.1 Objective

KMS Chat WebUI의 출력 형식과 사용자 경험을 **ChatGPT와 구분할 수 없는 수준**으로 구현합니다.

### 1.2 Success Criteria

| 기준 | 목표 |
|------|------|
| Markdown 렌더링 | 100% ChatGPT 스타일 |
| 스트리밍 UX | 토큰 단위 점진적 표시 |
| RAG 통합 | 소스 분리, 접기/펼치기 지원 |
| 가독성 | 문단 간격, 헤더, 코드 블록 일관성 |

---

## 2. Requirements Analysis

### 2.1 Mandatory Output Format Rules

```text
✅ 섹션 헤더 (##, ###) 사용
✅ 불릿 포인트로 설명
✅ 문단 사이 빈 줄 삽입
✅ 문단 최대 3-4줄 제한
✅ 핵심 용어 **굵게** 강조
✅ 명령어/파라미터는 `inline code`
✅ 예제는 fenced code block (```)
✅ 응답 끝에 요약/핵심 포인트
```

### 2.2 Frontend Requirements

| 구분 | 요구사항 |
|------|----------|
| Markdown 렌더러 | `react-markdown` + `remark-gfm` + `rehype-highlight` |
| 콘텐츠 폭 | 760-800px |
| 줄 높이 | 1.6-1.8 |
| 코드 블록 | 다크 배경, 둥근 모서리 |
| 인라인 코드 | 연한 배경색 |

### 2.3 Streaming Requirements

| 항목 | 요구사항 |
|------|----------|
| 프로토콜 | SSE (Server-Sent Events) |
| 단위 | 토큰 레벨 |
| 렌더링 | 점진적 Markdown 재렌더링 |
| 코드 블록 | 중간 렌더링 시 깨지지 않도록 처리 |

### 2.4 RAG Integration Requirements

| 항목 | 요구사항 |
|------|----------|
| 내부 로그 | 숨김 (검색, 검증 단계) |
| 최종 답변 | ChatGPT 스타일로 렌더링 |
| 소스 표시 | 시각적 분리, 접기/펼치기 |

---

## 3. Current State Analysis

### 3.1 Existing Components

| 컴포넌트 | 파일 | 현재 상태 |
|----------|------|----------|
| AgentChat | `components/AgentChat/AgentChat.tsx` | 기본 채팅 UI |
| MessageBubble | `components/AgentChat/MessageBubble.tsx` | 메시지 렌더링 |
| MessageContent | `components/AgentChat/MessageContent.tsx` | 콘텐츠 표시 |
| useStreamingChat | `components/AgentChat/hooks/useStreamingChat.ts` | SSE 스트리밍 |
| OpenFrameRAGPage | `pages/OpenFrameRAGPage.tsx` | RAG 전용 페이지 |

### 3.2 Gap Analysis (Initial)

| 항목 | 현재 | 목표 | Gap |
|------|------|------|-----|
| Markdown 렌더링 | 부분 지원 | 완전 지원 | 라이브러리 확인 필요 |
| 스트리밍 | SSE 지원 | 토큰 단위 | 현재 한 번에 덤프 |
| 문단 간격 | 기본 | ChatGPT 스타일 | CSS 조정 필요 |
| 코드 블록 | 기본 | 다크 테마 | 스타일링 필요 |
| RAG 소스 | 인라인 표시 | 접기/펼치기 | 컴포넌트 추가 필요 |

---

## 4. Implementation Scope

### 4.1 In Scope

1. **System Prompt 주입**
   - ChatGPT 스타일 포맷 강제 프롬프트
   - 백엔드 LLM 설정에 추가

2. **Markdown 렌더링 개선**
   - `react-markdown` 설정 최적화
   - `remark-gfm`, `rehype-highlight` 통합
   - 커스텀 컴포넌트 (헤더, 코드 블록)

3. **CSS 스타일 업데이트**
   - ChatGPT 스타일 간격/여백
   - 코드 블록 테마
   - 반응형 대응

4. **스트리밍 UX 개선**
   - 토큰 단위 렌더링
   - 코드 블록 중간 렌더링 안전 처리
   - 타이핑 효과

5. **RAG 소스 UI**
   - 소스 섹션 분리
   - 접기/펼치기 (Accordion)
   - 시각적 구분

### 4.2 Out of Scope

- 백엔드 RAG 로직 변경
- 새로운 LLM 모델 추가
- 모바일 앱 지원

---

## 5. Technical Approach

### 5.1 Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (React)                   │
├─────────────────────────────────────────────────────┤
│  ChatContainer                                       │
│  ├── MessageList                                     │
│  │   └── ChatMessage (ChatGPT-style)                │
│  │       ├── MarkdownRenderer                        │
│  │       │   ├── react-markdown                      │
│  │       │   ├── remark-gfm                          │
│  │       │   └── rehype-highlight                    │
│  │       └── SourcesAccordion                        │
│  │           └── Collapsible Sources                 │
│  └── ChatInput                                       │
├─────────────────────────────────────────────────────┤
│  Streaming Hook (useStreamingChat)                   │
│  ├── SSE Connection                                  │
│  ├── Token Buffer                                    │
│  └── Progressive Render                              │
└─────────────────────────────────────────────────────┘
           │
           ▼ SSE (text/event-stream)
┌─────────────────────────────────────────────────────┐
│                   Backend (FastAPI)                  │
├─────────────────────────────────────────────────────┤
│  LLM Configuration                                   │
│  └── System Prompt (ChatGPT-style format)           │
├─────────────────────────────────────────────────────┤
│  RAG Pipeline                                        │
│  ├── Search (hidden)                                 │
│  ├── Verify (hidden)                                 │
│  └── Generate (streamed)                             │
└─────────────────────────────────────────────────────┘
```

### 5.2 Key Components

| 컴포넌트 | 역할 |
|----------|------|
| `ChatMessage` | ChatGPT 스타일 메시지 컨테이너 |
| `MarkdownRenderer` | Markdown 렌더링 래퍼 |
| `SourcesAccordion` | RAG 소스 접기/펼치기 |
| `CodeBlock` | 구문 강조 코드 블록 |
| `useStreamingChat` | SSE 토큰 스트리밍 |

---

## 6. Implementation Priority

### Phase 1: Core Rendering (P0)
1. Markdown 렌더러 설정 (`react-markdown` + plugins)
2. ChatGPT 스타일 CSS 적용
3. 기본 메시지 컴포넌트 업데이트

### Phase 2: Streaming UX (P0)
1. 토큰 단위 스트리밍 구현
2. 코드 블록 안전 렌더링
3. 타이핑 효과 (커서 애니메이션)

### Phase 3: RAG Integration (P1)
1. 소스 섹션 분리
2. Accordion 컴포넌트
3. 시각적 구분 스타일

### Phase 4: Backend Format (P1)
1. System Prompt 주입
2. 포맷 검증 로직 (optional)

---

## 7. Risks & Mitigations

| 리스크 | 영향 | 완화 방안 |
|--------|------|----------|
| 코드 블록 중간 깨짐 | UX 저하 | 버퍼링 + 완성 감지 |
| 성능 저하 (재렌더링) | 느린 응답 | React.memo + 최적화 |
| 기존 UI 호환성 | 레그레션 | 점진적 적용 + 테스트 |

---

## 8. Acceptance Criteria

```text
[ ] ChatGPT와 시각적으로 구분 불가
[ ] 응답이 읽기 쉽고, 차분하고, 점진적
[ ] RAG 답변이 자연스럽고 대화형
[ ] 스트리밍 출력이 "타이핑" 느낌
[ ] 코드 블록 구문 강조 정상
[ ] 소스 섹션 접기/펼치기 동작
[ ] 다크/라이트 테마 모두 지원
```

---

## 9. Timeline (Estimated)

| Phase | Description | Priority |
|-------|-------------|----------|
| Phase 1 | Core Rendering | P0 |
| Phase 2 | Streaming UX | P0 |
| Phase 3 | RAG Integration | P1 |
| Phase 4 | Backend Format | P1 |

---

## 10. Next Steps

1. `/pdca design chatgpt-style-webui` 실행하여 상세 설계 문서 작성
2. 현재 `MessageContent.tsx` 분석
3. CSS 변수 및 테마 시스템 확인

---

**PDCA Status**: Plan ✅ → Design ⏳ → Do ⏳ → Check ⏳ → Act ⏳
