# Gap Analysis: webui-image-display-fix

## 분석 일시
2026-02-27

## Plan 문서
`docs/01-plan/features/webui-image-display-fix.plan.md`

## 분석 결과

### Overall Match Rate: 100%

| Category | Score | Status | 비고 |
|----------|:-----:|:------:|------|
| Fix 1: CSS 클래스 추가 | 100% | PASS | `.chatgpt-markdown-img/overlay/enlarged` 3개 클래스 추가 완료 |
| Fix 2: 디버그 로깅 | 100% | PASS | f-string 포맷 6개 로그 추가, %-style 0개 |
| Fix 3: product_id 매핑 | 100% | PASS | 변환 불필요 확인 (upstream에서 처리) |
| 비수정 범위 준수 | 100% | PASS | core 로직, Vite proxy, StaticFiles, agent-* CSS 모두 intact |

## Fix 1: CSS 클래스 추가 (CRITICAL)

**파일**: `kms-portal-ui/src/styles/chatgpt-style.css`

| CSS 클래스 | 필수 속성 | 구현 위치 | Status |
|-----------|----------|----------|:------:|
| `.chatgpt-markdown-img` | max-width, max-height, cursor:pointer, transition | line 541-554 | PASS |
| `.chatgpt-markdown-img:hover` | opacity:0.85 | line 555-557 | PASS |
| `.chatgpt-image-overlay` | position:fixed, inset:0, z-index:9999, rgba backdrop | line 560-569 | PASS |
| `.chatgpt-image-enlarged` | max-width:90vw, max-height:90vh, object-fit:contain | line 570-576 | PASS |

**CSS 변수 사용**: chatgpt 전용 변수 (`--chatgpt-radius`, `--chatgpt-border`) + fallback 값 적용. 기존 `agent-*` 클래스는 프로젝트 범용 변수 사용. 각 스타일 시스템이 자체 네임스페이스 유지.

## Fix 2: 디버그 로깅

**파일**: `app/api/services/agentic_rag_service.py`

| 로그 포인트 | 형식 | 위치 | Status |
|-----------|------|------|:------:|
| result skip (score <= 0) | f-string | line 2221 | PASS |
| result skip (no pdf_path) | f-string | line 2225 | PASS |
| result PDF/page/product | f-string | line 2227 | PASS |
| page별 이미지 수 | f-string | line 2258 | PASS |
| 이미지 추출 에러 | f-string | line 2264 | PASS (bonus) |
| PDF open 에러 | f-string | line 2267 | PASS (bonus) |
| 최종 table/image 수 | f-string | line 2269 | PASS |

**검증**: `_build_table_supplement` 메서드 내 `%s`, `%d` 패턴 0개 확인. AppLogger 호환 완료.

## Fix 3: product_id 매핑

| 확인 항목 | 기대값 | 실제값 | Status |
|----------|-------|-------|:------:|
| product_id 소스 | `r.product` (동적 ID) | `r.product or "unknown"` (line 2231) | PASS |
| 이미지 경로 템플릿 | `/uploads/pdf_images/{product_id}/...` | 일치 (structured_knowledge_store.py:400) | PASS |
| Legacy 매핑 필요 여부 | 이 레이어에서 불필요 | 미적용 (정상) | PASS |

## 비수정 범위 검증

| 항목 | 파일:위치 | Status |
|------|----------|:------:|
| `_build_table_supplement` core 로직 | `results[:3]`, `MAX_TABLE_ROWS=20`, `MAX_IMAGES=2` 유지 | PASS |
| Vite proxy `/uploads` | `vite.config.ts:30-34` intact | PASS |
| StaticFiles mount | `main.py:877` intact | PASS |
| `.agent-markdown-img` CSS | `AgentChat.css:2110-2145` intact | PASS |

## API 테스트 결과

| 쿼리 | テーブル | 이미지 | 이유 |
|------|:--------:|:-----:|------|
| OSCシステムサーバーの一覧 | YES (3 tables) | NO | 검색 결과 페이지(p.21,22,166)에 이미지 없음 (정상) |

디버그 로그 확인:
```
result[0] pdf=JCL-Reference-Guide, page=165 → page 165: 0 images, page 166: 0 images
result[1] pdf=Installation-Guide, page=21 → page 21: 0 images, page 22: 0 images
result[2] pdf=Installation-Guide, page=20 → page 20: 0 images, page 21: 0 images
final: 3 tables, 0 images
```

## 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `kms-portal-ui/src/styles/chatgpt-style.css` | `.chatgpt-markdown-img`, `hover`, `overlay`, `enlarged` CSS 추가 |
| `app/api/services/agentic_rag_service.py` | `_build_table_supplement()` f-string 디버그 로그 7개 추가 |
