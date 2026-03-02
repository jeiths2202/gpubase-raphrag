# Plan: RAG 응답 테이블/이미지 WebUI 출력

## 배경

현재 Agentic RAG 페이지에서 LLM 응답이 텍스트로만 출력되며, PDF에서 추출된 테이블이나 이미지가 표시되지 않는 문제가 있다.

### 현상

- 스크린샷: "OSCシステムの構造" 다이어그램 참조가 텍스트(`図 1.1을 참조하시기 바랍니다`)로만 표시
- PDF 내 표/이미지가 존재해도 WebUI에 렌더링되지 않음

### 원인 분석 (Gap)

| 기능 | 백엔드 | AgenticRAGPage | Gap |
|------|--------|----------------|-----|
| GFM 테이블 (llm_token) | `_build_table_supplement()` 으로 마크다운 주입 | react-markdown + remark-gfm 렌더링 가능 | score >= 3.0 제한으로 대부분 스킵됨 |
| PDF 이미지 (마크다운 URL) | `_extract_page_images()` → `/uploads/pdf_images/` 저장 + 마크다운 참조 | react-markdown img 핸들러 렌더링 가능 | 이미지 추출 조건이 제한적 |
| `sources` SSE 이벤트 | source 목록 전송 | 출처 표시만 함 | 관련 테이블/이미지를 sources와 함께 표시 안함 |

## 목표

1. RAG 검색 결과에 관련 **테이블**이 있으면 응답에 GFM 마크다운으로 포함
2. RAG 검색 결과에 관련 **이미지**(다이어그램, 차트)가 있으면 응답에 이미지 URL로 포함
3. 프론트엔드에서 테이블은 styled table, 이미지는 클릭 확대 가능하게 렌더링

## 수정 범위

### Backend (2개 파일)

#### 1. `app/api/services/agentic_rag_service.py`

- `_build_table_supplement()`: **score >= 3.0 제한 완화** → score > 0 이면 보충 테이블 생성
- 검색 결과 상위 N개에 대해 테이블/이미지 보충 (현재 top-1만)

#### 2. `app/api/services/structured_knowledge_store.py`

- `enrich_content_with_tables()`: 검색 결과 content에 테이블+이미지 인라인 주입 범위 확대
- `_extract_page_images()`: 이미지 추출 조건 확인 및 필요시 완화

### Frontend (1개 파일)

#### 3. `kms-portal-ui/src/pages/AgenticRAGPage.tsx`

- `sources` 이벤트 처리 시 관련 이미지를 함께 표시하는 UI 추가 (별도 SSE 이벤트 불필요 — llm_token에 이미 마크다운으로 포함)

## 비수정 범위

- `BlockRenderer` / `answer_block` 시스템 (AgentPage 전용 — 별도 아키텍처)
- `useStreamingChat` 훅 (AgenticRAGPage는 별도 SSE 처리)
- `search_result` 이벤트 (agent executor 경로 전용)

## 구현 순서

1. **Backend**: `_build_table_supplement()` score 제한 완화 + 상위 3개 결과 대상 확대
2. **Backend**: `enrich_content_with_tables()` 호출 조건 확인
3. **테스트**: mscasmc, osctdlrm 등 명령어 쿼리로 테이블/이미지 포함 여부 확인
4. **Frontend**: 필요시 이미지 스타일링 보정 (이미 react-markdown이 렌더링함)

## 리스크

- 테이블이 너무 길면 응답이 비대해짐 → 테이블 행 수 제한 (max 20행)
- 이미지가 많으면 로딩 느림 → 페이지당 최대 2개 이미지 제한
- score 제한 완화로 무관한 테이블이 포함될 수 있음 → 키워드 매칭 검증 추가
