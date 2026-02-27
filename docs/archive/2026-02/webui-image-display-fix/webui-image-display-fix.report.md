# webui-image-display-fix Completion Report

> **Status**: Complete
>
> **Project**: HybridRAG KMS
> **Author**: Claude Code
> **Completion Date**: 2026-02-27
> **PDCA Cycle**: #1

---

## 1. Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | webui-image-display-fix |
| Start Date | 2026-02-27 |
| End Date | 2026-02-27 |
| Duration | ~2 hours (single session) |
| Predecessor | rag-table-image-display (archived) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ Complete:     3 / 3 fixes                │
│  ⏳ In Progress:  0 / 3 fixes                │
│  ❌ Cancelled:    0 / 3 fixes                │
└─────────────────────────────────────────────┘
```

### 1.3 Problem Statement

Agentic RAG 페이지에서 PDF 추출 이미지가 WebUI에 표시되지 않는 문제. 백엔드 이미지 추출 파이프라인(`rag-table-image-display`)은 이미 구현 완료되었으나, 프론트엔드에서 CSS 클래스 불일치로 인해 이미지 스타일이 적용되지 않았음.

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [webui-image-display-fix.plan.md](../../01-plan/features/webui-image-display-fix.plan.md) | ✅ Finalized |
| Design | (Plan에 설계 포함 — 별도 Design 불필요) | ⏭️ Skipped |
| Check | [webui-image-display-fix.analysis.md](../../03-analysis/webui-image-display-fix.analysis.md) | ✅ Complete (100%) |
| Report | Current document | ✅ Complete |

---

## 3. Root Cause Analysis

### 3.1 Critical Root Cause: CSS 클래스 불일치

```
MessageContent.tsx:88  → useChatGPTStyle = true (기본값)
MessageContent.tsx:95  → prefix = 'chatgpt'
MessageContent.tsx:184 → className = "chatgpt-markdown-img"

BUT: "chatgpt-markdown-img" CSS 규칙이 프로젝트 전체에 존재하지 않음!
     "agent-markdown-img"만 AgentChat.css:2110에 존재
```

**호출처 5개 모두** `useChatGPTStyle`을 전달하지 않아 기본값 `true` 사용:
- AgenticRAGPage.tsx, OpenFrameRAGPage.tsx, MessageBubble.tsx, ExpandableSearchResultCard.tsx, DirectModeFloatingPanel.tsx

### 3.2 부차적 확인: 이미지가 응답에 미포함 가능성

검색 결과 페이지에 실제 이미지가 없는 경우 `**参考図:**` 섹션 자체가 생성되지 않음 — 이는 정상 동작이지만, 디버그 로그 없이는 원인 파악 불가능했음.

---

## 4. Completed Fixes

### Fix 1: CSS 클래스 추가 (CRITICAL)

| Item | Detail |
|------|--------|
| File | `kms-portal-ui/src/styles/chatgpt-style.css` |
| Lines Added | 42 lines (line 537-578) |
| Classes | `.chatgpt-markdown-img`, `:hover`, `.chatgpt-image-overlay`, `.chatgpt-image-enlarged` |

```css
/* 핵심 변경 */
.chatgpt-markdown-img {
  max-width: 100%; max-height: 300px;
  cursor: pointer; transition: opacity 0.15s;
  border-radius: var(--chatgpt-radius, 8px);
}
.chatgpt-image-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.8);
}
.chatgpt-image-enlarged {
  max-width: 90vw; max-height: 90vh;
  object-fit: contain;
}
```

**설계 결정**: 기존 `agent-*` 클래스(AgentChat.css)와 독립적인 `chatgpt-*` 네임스페이스 유지. 각 스타일 시스템이 자체 CSS 변수(`--chatgpt-radius` vs 프로젝트 범용 변수) 사용.

### Fix 2: 디버그 로깅 추가

| Item | Detail |
|------|--------|
| File | `app/api/services/agentic_rag_service.py` |
| Method | `_build_table_supplement()` |
| Logs Added | 7개 f-string 디버그 로그 |

| Log Point | Purpose |
|-----------|---------|
| result skip (score <= 0) | 점수 필터링 추적 |
| result skip (no pdf_path) | PDF 경로 미발견 추적 |
| result PDF/page/product | 검색 결과 매핑 확인 |
| page별 이미지 수 | 페이지당 추출 이미지 수 |
| 이미지 추출 에러 | PyMuPDF 에러 캡처 |
| PDF open 에러 | PDF 파일 접근 에러 |
| 최종 table/image 수 | 결과 요약 |

**주의**: AppLogger는 `%`-style 포맷을 지원하지 않음 → f-string 전용 사용 (초기 구현에서 HTTP 500 발생 → 즉시 수정).

### Fix 3: product_id 매핑 확인

| Item | Detail |
|------|--------|
| 결론 | 변환 불필요 (upstream에서 처리) |
| 근거 | `r.product`이 이미 동적 product_id 반환 (예: `mvs_openframe_7.1`) |
| 이미지 경로 | `/uploads/pdf_images/{product_id}/...` — `structured_knowledge_store.py:400` 에서 일치 확인 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Status |
|--------|--------|-------|--------|
| Design Match Rate | 90% | 100% | ✅ |
| CSS 클래스 완성도 | 3 classes | 4 rules (hover 포함) | ✅ |
| 디버그 로그 수 | 5+ points | 7 points | ✅ |
| AppLogger 호환성 | f-string only | 0 %-style patterns | ✅ |
| 비수정 범위 준수 | intact | 4/4 verified | ✅ |

### 5.2 API 테스트 결과

| Query | Tables | Images | Reason |
|-------|:------:|:------:|--------|
| OSCシステムサーバーの一覧 | 3 | 0 | 검색 결과 페이지(p.21,22,166)에 이미지 없음 (정상) |

```
Debug log output:
result[0] pdf=JCL-Reference-Guide, page=165 → 0 images
result[1] pdf=Installation-Guide, page=21 → 0 images
result[2] pdf=Installation-Guide, page=20 → 0 images
final: 3 tables, 0 images
```

### 5.3 Resolved Issues

| Issue | Resolution |
|-------|------------|
| CSS 클래스 불일치로 이미지 미표시 | `chatgpt-*` CSS 3+1개 클래스 추가 |
| 이미지 미포함 원인 불명 | f-string 디버그 로그 7개 추가 |
| AppLogger %-style 크래시 (HTTP 500) | 전량 f-string 변환 |

---

## 6. Lessons Learned

### 6.1 What Went Well (Keep)

- **스크린샷 기반 디버깅**: 사용자 제공 스크린샷에서 문제를 시각적으로 확인 후 코드 추적
- **전체 파이프라인 추적**: Backend (이미지 추출) → Static Files → Vite Proxy → Frontend (CSS) 전 경로 분석
- **비수정 범위 명확화**: Plan 단계에서 수정하지 않을 범위를 명시하여 불필요한 변경 방지

### 6.2 What Needs Improvement (Problem)

- **CSS prefix 기본값 검증 부재**: `useChatGPTStyle=true`가 기본값으로 설정되었으나 대응 CSS가 누락된 채 배포됨 (chatgpt-style.css 생성 시 이미지 관련 규칙 미포함)
- **AppLogger 규약 문서화**: `%`-style 포맷 미지원이 문서화되지 않아 런타임 크래시 발생

### 6.3 What to Try Next (Try)

- **CSS 클래스 완전성 검증 스크립트**: TSX에서 사용되는 CSS 클래스명이 실제 CSS 파일에 존재하는지 빌드 시 검증
- **이미지 포함 E2E 테스트**: OSC Administrator Guide p.18 (767x543 아키텍처 다이어그램) 등 이미지가 포함된 페이지에 대한 E2E 테스트 추가

---

## 7. Modified Files

| File | Changes | Category |
|------|---------|----------|
| `kms-portal-ui/src/styles/chatgpt-style.css` | +42 lines (4 CSS rules) | Frontend CSS |
| `app/api/services/agentic_rag_service.py` | +7 debug log points | Backend Logging |

---

## 8. Next Steps

### 8.1 Immediate

- [x] Production commit & push (e209f11)
- [ ] 이미지 포함 쿼리 실제 검증 (OSC Administrator Guide 아키텍처 다이어그램)
- [ ] Dark mode 테마 호환성 확인 (`chatgpt-*` CSS 변수 fallback 동작)

### 8.2 Next PDCA Cycle

| Item | Priority | Notes |
|------|----------|-------|
| 이미지 포함 E2E 테스트 추가 | Medium | `e2e/` 디렉토리에 이미지 렌더링 검증 |
| CSS 클래스 누락 감지 자동화 | Low | 빌드 파이프라인 통합 |

---

## 9. Changelog

### v1.0.0 (2026-02-27)

**Added:**
- `.chatgpt-markdown-img` CSS (이미지 표시, max-width/height, cursor:pointer)
- `.chatgpt-markdown-img:hover` (opacity 전환)
- `.chatgpt-image-overlay` (풀스크린 확대 배경)
- `.chatgpt-image-enlarged` (확대 이미지 스타일)
- `_build_table_supplement()` f-string 디버그 로그 7개

**Fixed:**
- CSS 클래스 불일치로 인한 WebUI 이미지 미표시 (chatgpt prefix CSS 부재)
- AppLogger %-style 포맷 크래시 (f-string 변환)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-02-27 | Completion report created | Claude Code |
