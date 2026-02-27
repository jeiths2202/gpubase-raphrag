# Plan: WebUI 이미지 미출력 수정

## 배경

Agentic RAG 페이지에서 PDF에서 추출된 이미지가 WebUI에 표시되지 않는 문제.
`rag-table-image-display` 기능으로 백엔드 이미지 추출 파이프라인은 구현 완료되었으나, 프론트엔드에서 이미지가 렌더링되지 않음.

### 현상

- 스크린샷: OSC 아키텍처 관련 질문에서 텍스트만 출력, 이미지 미표시
- `図 1.1을 참조하시기 바랍니다` 같은 텍스트 참조만 표시됨
- 테이블은 정상 출력됨

## 근본 원인 분석

### Root Cause 1: CSS 클래스 불일치 (CRITICAL)

`MessageContent.tsx`의 CSS 클래스 생성 로직:

```tsx
// MessageContent.tsx:88 - 기본값이 true
useChatGPTStyle = true

// MessageContent.tsx:95 - prefix 결정
const prefix = useChatGPTStyle ? 'chatgpt' : 'agent';

// MessageContent.tsx:184 - 이미지에 적용되는 클래스
className={`${prefix}-markdown-img`}
// → 실제 생성: "chatgpt-markdown-img"
```

**문제**: `chatgpt-markdown-img` CSS 클래스가 프로젝트 전체에 존재하지 않음

| CSS 클래스 | 존재 여부 | 파일 |
|-----------|:---------:|------|
| `.agent-markdown-img` | ✅ 있음 | `AgentChat.css:2110` |
| `.agent-image-overlay` | ✅ 있음 | `AgentChat.css:2129` |
| `.agent-image-enlarged` | ✅ 있음 | `AgentChat.css:2139` |
| `.chatgpt-markdown-img` | ❌ **없음** | 어디에도 없음 |
| `.chatgpt-image-overlay` | ❌ **없음** | 어디에도 없음 |
| `.chatgpt-image-enlarged` | ❌ **없음** | 어디에도 없음 |

**호출처 분석**: `MessageContent`를 사용하는 모든 컴포넌트가 `useChatGPTStyle`을 명시적으로 전달하지 않음 → 기본값 `true` → `chatgpt-*` prefix 사용

| 호출처 | useChatGPTStyle 전달 | 실제 prefix |
|--------|:-------------------:|:-----------:|
| `AgenticRAGPage.tsx:1029,1058` | 미전달 (=true) | `chatgpt` |
| `OpenFrameRAGPage.tsx:866` | 미전달 (=true) | `chatgpt` |
| `MessageBubble.tsx:455` | 미전달 (=true) | `chatgpt` |
| `ExpandableSearchResultCard.tsx:120` | 미전달 (=true) | `chatgpt` |
| `DirectModeFloatingPanel.tsx:259` | 미전달 (=true) | `chatgpt` |

**결과**: 이미지가 스타일 없이 렌더링 → 브라우저 기본 동작으로 표시 (크기 제한 없음, 오버레이 불동작)

### Root Cause 2: 이미지 URL 경로 불일치 가능성

백엔드 `_extract_page_images()`가 생성하는 이미지 경로:
```
/uploads/pdf_images/{product_id}/{pdf_stem}/p{page}_img{idx}.png
```

실제 디스크 파일:
```
uploads/pdf_images/mvs_openframe_7.1/OF_OSC_7.1_CTG-User-Guide_v3.1.2_jp/p13_img0.png
uploads/pdf_images/mvs_openframe_7.1/p100_img0.png  (pdf_stem 없는 경우도 있음)
```

잠재적 불일치:
- 검색 결과의 `r.product`이 `openframe_mvs`인데 디스크 경로는 `mvs_openframe_7.1`
- `_resolve_pdf_path_and_page()`가 Summary 결과에서 PDF 경로를 추출 실패할 수 있음

### Root Cause 3: 이미지가 응답에 미포함 가능성

`_build_table_supplement()`의 이미지 포함 조건:
1. `results[:3]` — 상위 3개 결과만 대상
2. `relevance_score > 0` — 점수 필터
3. `_resolve_pdf_path_and_page()` 성공 — PDF 경로 확인
4. 해당 페이지에 이미지 존재 — `page.get_images()` 비어있으면 스킵
5. 이미지 크기 >= 50x50 — 소형 이미지 필터
6. `MAX_IMAGES = 2` — 최대 2개 제한

→ 검색 결과 페이지에 실제 이미지가 없으면 `**参考図:**` 섹션 자체가 미생성

## 수정 범위

### Fix 1: CSS 클래스 추가 (Frontend) — **핵심 수정**

**파일**: `kms-portal-ui/src/styles/chatgpt-style.css`

`chatgpt-markdown-img`, `chatgpt-image-overlay`, `chatgpt-image-enlarged` CSS 규칙 추가.
기존 `AgentChat.css`의 `.agent-*` 규칙과 동일한 스타일 적용.

### Fix 2: 이미지 추출 디버그 로깅 (Backend)

**파일**: `app/api/services/agentic_rag_service.py`

`_build_table_supplement()`에 이미지 추출 과정 디버그 로그 추가:
- PDF 경로 해석 결과
- 페이지별 이미지 개수
- 스킵 사유 (경로 미발견, 이미지 없음, 크기 미달 등)

### Fix 3: product_id 매핑 확인 (Backend)

**파일**: `app/api/services/structured_knowledge_store.py`

`_extract_page_images()` 내 `product_id` 사용 시 Legacy→Dynamic 매핑 확인:
- `openframe_mvs` → `mvs_openframe_7.1` 변환 필요 여부

## 비수정 범위

- `_build_table_supplement()` 로직 (이미 `rag-table-image-display`에서 구현 완료)
- Vite proxy 설정 (이미 `/uploads` → `localhost:9000` 프록시 설정됨)
- `StaticFiles` 마운트 (`main.py:870-877` 이미 정상)
- Backend 이미지 추출 파이프라인 (568개 이미지 정상 생성됨)

## 구현 순서

1. **Fix 1**: `chatgpt-style.css`에 이미지 관련 CSS 3개 클래스 추가
2. **검증**: 브라우저에서 이미지 렌더링 확인
3. **Fix 2**: 백엔드 디버그 로깅 추가 (이미지 미포함 시 원인 추적용)
4. **Fix 3**: product_id 매핑 불일치 확인 및 수정 (필요시)
5. **테스트**: OSC 관련 질문으로 이미지 포함 여부 API 테스트

## 리스크

| 리스크 | 대응 |
|--------|------|
| `chatgpt-style.css`가 다른 페이지에도 영향 | `.chatgpt-markdown-img`는 `MessageContent` 전용이므로 영향 범위 제한적 |
| 이미지가 아예 응답에 미포함 | Fix 2 디버그 로깅으로 원인 추적 |
| product_id 불일치로 잘못된 경로 생성 | Fix 3에서 매핑 테이블 확인 |
