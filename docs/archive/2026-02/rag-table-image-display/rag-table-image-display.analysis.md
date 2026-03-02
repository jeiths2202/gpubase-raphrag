# Gap Analysis: rag-table-image-display

## 분석 일시
2026-02-27

## Plan 문서
`docs/01-plan/features/rag-table-image-display.plan.md`

## 분석 결과

### Overall Match Rate: 95% (Gap 수정 후)

| Category | Score | Status | 비고 |
|----------|:-----:|:------:|------|
| Backend - Score 완화 (3.0→0) | 100% | ✅ | `relevance_score <= 0` 으로 변경 |
| Backend - Top-3 확대 | 100% | ✅ | `results[:3]` |
| Backend - Table Enrichment | 100% | ✅ | `enrich_content_with_tables()` 기존 동작 유지 |
| Backend - Image Extraction | 100% | ✅ | `_extract_page_images()` 기존 동작 유지 |
| Safeguard - 테이블 20행 제한 | 100% | ✅ | `MAX_TABLE_ROWS = 20` |
| Safeguard - 이미지 2개 제한 | 100% | ✅ | `MAX_IMAGES = 2` |
| Safeguard - 키워드 매칭 검증 | 100% | ✅ | 쿼리 키워드 ∩ 테이블 내용 검증 추가 |
| Frontend - 테이블 렌더링 | 100% | ✅ | react-markdown + remark-gfm 기존 동작 |
| Frontend - 이미지 CSS | 100% | ✅ | `.agent-markdown-img` 기존 CSS 존재 |
| Frontend - 이미지 클릭 확대 | 100% | ✅ | `enlargedImg` state + overlay modal 추가 |
| 비수정 범위 준수 | 100% | ✅ | BlockRenderer, useStreamingChat 미수정 |

### 1차 분석 (수정 전): 85%

3개 Gap 발견:
1. **키워드 매칭 검증 미구현** — 무관한 테이블 포함 가능성
2. **이미지 클릭 확대 미구현** — Plan 목표 3번 미충족
3. **이미지 CSS prefix 확인** — `agent-markdown-img` 존재 확인

### 수정 내역

#### Fix 1: 키워드 매칭 검증 (`agentic_rag_service.py`)
- `_build_table_supplement(results, query)` 시그니처 변경
- 쿼리 토큰 추출 → 테이블 내용과 교차 검증
- 4개 호출 사이트 모두 `query=request.message` 전달

#### Fix 2: 이미지 클릭 확대 (`MessageContent.tsx`)
- `enlargedImg` state 추가
- `img` handler에 `onClick` → `setEnlargedImg(src)` 추가
- Overlay modal: fixed position, zoom-out cursor, 90vw/90vh 제한

#### Fix 3: 이미지 hover/overlay CSS (`AgentChat.css`)
- `.agent-markdown-img:hover { opacity: 0.85 }` 추가
- `.agent-image-overlay` 풀스크린 backdrop 추가
- `.agent-image-enlarged` max-width/height 제한

## 테스트 결과

| 쿼리 | 테이블 포함 | 이미지 포함 | 라우팅 |
|------|:-----------:|:-----------:|--------|
| OSCシステムサーバーの一覧 | ✅ (7 tables) | - (해당 페이지에 이미지 없음) | openframe_mvs |
| osctdlrmに대해서 알려줘 | - (해당 페이지에 테이블 없음) | - | openframe_mvs |

## 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `app/api/services/agentic_rag_service.py` | score 완화, top-3, 행 제한, 이미지 제한, 키워드 검증 |
| `kms-portal-ui/src/components/AgentChat/MessageContent.tsx` | 이미지 클릭 확대 기능 |
| `kms-portal-ui/src/components/AgentChat.css` | 이미지 hover + overlay CSS |
