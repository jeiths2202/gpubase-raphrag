# PDCA Plan: 검색 결과 이미지/표 출력 기능

## 1. 기능 개요

### 1.1 현재 상황
- RAG 검색 결과에서 "포함된 이미지/표:" 섹션에 `[figure] 1.1: マッピング・サポートの基本構造` 같은 텍스트 참조만 표시됨
- 실제 이미지 데이터는 표시되지 않음
- `FigureImageService`가 이미 존재하며 figure reference 감지 및 이미지 조회 기능이 구현되어 있음

### 1.2 목표
- 검색 결과에서 figure 참조가 있을 때 실제 이미지를 인라인으로 표시
- 사용자가 관련 다이어그램/차트/표를 즉시 확인 가능하도록 함

## 2. 기존 인프라 분석

### 2.1 백엔드 - 이미지 서비스 (이미 구현됨)

**`app/api/services/figure_image_service.py`**
```python
class FigureImageService:
    async def get_images_for_response(self, response_text, document_ids, include_data=True)
    async def get_images_for_sources(self, sources, include_data=True)
    async def get_images_for_pages(self, document_id, page_numbers, include_data=True)
```

**출력 형식:**
```json
{
  "id": "image_uuid",
  "document_id": "doc_uuid",
  "page_number": 15,
  "figure_reference": "fig_1_1",
  "figure_caption": "マッピング・サポートの基本構造",
  "description": "...",
  "width": 800,
  "height": 600,
  "mime_type": "image/png",
  "data": "data:image/png;base64,..."  // include_data=true일 때
}
```

### 2.2 프론트엔드 - 현재 구조

**`kms-portal-ui/src/pages/OpenAgentPage.tsx`**
- `Message` 인터페이스에 `images?: ImageContent[]` 필드 존재
- `ImageContent` 타입:
```typescript
interface ImageContent {
  chunk_id?: string;
  content: string;
  page_start?: number;
  page_end?: number;
  doc_filename?: string;
  image_url?: string;  // 이미지 URL (현재 미사용)
}
```

### 2.3 검색 도구 - 이미지/표 처리

**`app/api/agents/tools/unified_search.py`**
- `include_images=true` 파라미터 지원
- CLIP 기반 text-to-image 검색 지원
- 현재 이미지 참조만 반환, 실제 base64 데이터는 미포함

## 3. Gap 분석

### 3.1 누락된 연결 포인트

| 위치 | 현재 상태 | 필요한 상태 |
|------|----------|------------|
| RAG Agent 실행 후 | 응답 텍스트만 전달 | 응답 + 관련 이미지 데이터 |
| SSE 스트리밍 | sources 청크만 전송 | sources + images 청크 추가 |
| 프론트엔드 | ImageContent에 image_url만 | data:base64 형식 지원 |
| 메시지 렌더링 | 이미지 참조 텍스트 표시 | 실제 이미지 인라인 렌더링 |

### 3.2 수정 대상 파일

1. **`app/api/agents/executor.py`** - Agent 실행 후 이미지 조회 로직 추가
2. **`app/api/agents/orchestrator.py`** - 스트리밍 응답에 images 청크 추가
3. **`kms-portal-ui/src/pages/OpenAgentPage.tsx`** - 이미지 렌더링 컴포넌트 추가
4. **`kms-portal-ui/src/components/AgentChat/hooks/useStreamingChat.ts`** - images 청크 처리

## 4. 구현 계획

### Phase 1: 백엔드 이미지 데이터 통합

**Step 1.1: Agent Executor 수정**
- `executor.py`에서 RAG 응답 완료 후 FigureImageService 호출
- sources에서 document_id, page_number 추출
- 관련 이미지 조회 및 base64 인코딩

**Step 1.2: SSE 스트림에 images 청크 추가**
- 새로운 chunk_type: "images" 정의
- 이미지 데이터를 별도 청크로 전송 (텍스트 스트리밍과 분리)

### Phase 2: 프론트엔드 이미지 렌더링

**Step 2.1: ImageContent 타입 확장**
```typescript
interface ImageContent {
  id?: string;
  content: string;  // figure_caption
  figure_reference?: string;
  data?: string;  // base64 data URL
  width?: number;
  height?: number;
  page_number?: number;
  doc_filename?: string;
}
```

**Step 2.2: 이미지 렌더링 컴포넌트**
- 검색 결과 하단에 이미지 갤러리 형태로 표시
- 클릭 시 확대 보기 (모달)
- 이미지 캡션 표시

### Phase 3: OpenFrameRAGPage 통합

- 동일한 이미지 렌더링 컴포넌트 재사용
- 제품별 이미지 필터링 지원

## 5. 성공 기준

| 기준 | 측정 방법 |
|------|----------|
| 이미지 표시 동작 | "マッピング・サポートの基本構造" 쿼리 시 관련 이미지 표시 |
| 성능 | 이미지 포함 시 응답 지연 < 2초 추가 |
| UX | 이미지 로딩 중 스켈레톤 UI 표시 |
| 에러 처리 | 이미지 없는 경우 graceful 처리 |

## 6. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 큰 이미지로 인한 성능 저하 | SSE 스트림 지연 | 이미지 크기 제한 (max 500KB), 썸네일 생성 |
| 다수 이미지 | 메모리 사용량 증가 | 페이지당 최대 5개 이미지 제한 |
| DB 조회 실패 | 이미지 미표시 | 텍스트 참조는 유지, 에러 로깅 |

## 7. 예상 작업량

| 단계 | 예상 파일 수 | 복잡도 |
|------|-------------|--------|
| Phase 1 | 3개 | 중 |
| Phase 2 | 3개 | 중 |
| Phase 3 | 1개 | 저 |
| 테스트 | 2개 | 저 |

## 8. 다음 단계

1. Design 문서 작성 (`/pdca design search-result-image-display`)
2. Phase 1 구현 (백엔드)
3. Phase 2 구현 (프론트엔드)
4. E2E 테스트
5. Gap 분석 및 검증
