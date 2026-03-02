# Agentic RAG 처리 파이프라인 상세 설계서

> **작성일**: 2026-02-08
> **대상 시스템**: KMS (Knowledge Management System) - Agentic RAG 모듈
> **범위**: 사용자 프롬프트 입력부터 화면 렌더링까지 전체 흐름

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [전체 파이프라인 플로우](#2-전체-파이프라인-플로우)
3. [Phase 1: 프론트엔드 입력 처리](#3-phase-1-프론트엔드-입력-처리)
4. [Phase 2: API 요청 전송 (SSE)](#4-phase-2-api-요청-전송-sse)
5. [Phase 3: 백엔드 라우터 수신](#5-phase-3-백엔드-라우터-수신)
6. [Phase 4: 제품 라우팅 (Product Resolution)](#6-phase-4-제품-라우팅-product-resolution)
7. [Phase 5: Web Doc Fast Path](#7-phase-5-web-doc-fast-path)
8. [Phase 6: 질문 유형 분류 (Query Type Classification)](#8-phase-6-질문-유형-분류-query-type-classification)
9. [Phase 7: 다중 제품 검색 (Multi-Product Search)](#9-phase-7-다중-제품-검색-multi-product-search)
10. [Phase 8: 응답 생성 (Response Generation)](#10-phase-8-응답-생성-response-generation)
11. [Phase 9: 사후 검증 (Post-Verification)](#11-phase-9-사후-검증-post-verification)
12. [Phase 10: SSE 스트리밍 전송](#12-phase-10-sse-스트리밍-전송)
13. [Phase 11: 프론트엔드 렌더링](#13-phase-11-프론트엔드-렌더링)
14. [SSE 이벤트 타입 정의](#14-sse-이벤트-타입-정의)
15. [파일 맵](#15-파일-맵)

---

## 1. 시스템 개요

Agentic RAG는 제품별 Agent 기반 RAG(Retrieval-Augmented Generation) 시스템으로, 다음 특성을 갖습니다:

- **19개 제품** 동적 발견 (uploads/manuals/ 디렉토리 스캔)
- **LLM-free 검색**: 키워드 + BM25 기반 결정론적 검색 (환각 0%)
- **2-Track 응답**: 정형 질문(~70-80%) → 템플릿 응답 / 비정형 질문 → LLM 생성 + 사후 검증
- **Web Doc Fast Path**: docs.tmaxsoft.com 실시간 검색으로 PDF 검색 우회
- **Long-term Memory**: 사용자별 제품 라우팅 컨텍스트 영속

### 핵심 설계 원칙

| 원칙 | 내용 |
|------|------|
| **Zero-Hallucination First** | 정형 질문은 100% 소스 기반 템플릿 (LLM 미사용) |
| **LLM Constrained** | 비정형 질문도 검색 결과 컨텍스트 내에서만 생성 |
| **Deterministic Search** | 검색 단계는 LLM 없이 키워드/BM25로 결정론적 수행 |
| **Post-Verification** | LLM 출력은 문장별 소스 대조 검증 (🟢🟡🔴) |

---

## 2. 전체 파이프라인 플로우

```
사용자 입력 (AgenticRAGPage.tsx)
    │
    ▼
[Phase 1] 입력 처리 + AgenticRAGRequest 구성
    │
    ▼
[Phase 2] fetch() → POST /api/v1/agentic-rag/stream (SSE)
    │
    ▼
[Phase 3] FastAPI Router (agentic_rag.py) → 인증 → user_id 주입
    │
    ▼
[Phase 4] 제품 라우팅 (_resolve_search_products)
    │     ├─ Case 1-3: 명시적 제품 → CONFIRMED
    │     └─ Case 4: Auto → QueryRouter.classify()
    │          ├─ CONFIRMED → 진행
    │          ├─ CLARIFICATION_NEEDED → SSE clarification_needed 이벤트 → 종료
    │          └─ NO_MATCH → all_scores fallback → Memory fallback
    │
    ▼
[Phase 5] Web Doc Fast Path (score >= 0.9?)
    │     ├─ Yes → httpx fetch → LLM 생성 → SSE 스트리밍 → 종료
    │     └─ No → 다음 단계
    │
    ▼
[Phase 6] 질문 유형 분류 (QueryTypeClassifier)
    │     → ERROR_CODE / COMMAND / PARAMETER / CONFIG / FREEFORM
    │
    ▼
[Phase 7] 다중 제품 검색 (_multi_product_search)
    │     ├─ Agent별 병렬 검색 (asyncio.gather)
    │     ├─ Intent 기반 재순위 (rerank_by_intent)
    │     └─ Fingerprint 중복 제거
    │
    ▼
[Phase 8] 응답 생성
    │     ├─ 정형 (COMMAND/ERROR_CODE/PARAMETER/CONFIG)
    │     │     └─ TemplateResponseBuilder.build() → template_response 이벤트
    │     └─ 비정형 (FREEFORM) 또는 템플릿 실패
    │           ├─ LLM 스트리밍 생성 → llm_token 이벤트
    │           └─ 테이블/이미지 보충 (_build_table_supplement)
    │
    ▼
[Phase 9] 사후 검증 (ResponseVerifier.verify)
    │     → 문장별 VERIFIED(🟢) / INFERRED(🟡) / UNVERIFIED(🔴)
    │
    ▼
[Phase 10] SSE 이벤트 전송 (sources → done)
    │
    ▼
[Phase 11] 프론트엔드 렌더링
      ├─ SSE 이벤트 파싱 (ReadableStream)
      ├─ React State 업데이트 (messages)
      └─ MessageContent 컴포넌트 (Markdown + 코드 하이라이팅)
```

---

## 3. Phase 1: 프론트엔드 입력 처리

### 파일 위치
- `kms-portal-ui/src/pages/AgenticRAGPage.tsx`

### 처리 순서

#### 3.1 사용자 입력

```
<textarea> → onKeyDown (Enter) / onClick (Send 버튼)
    │
    ▼
handleSubmit(e) → sendMessage(input)    [line 442-444]
```

- Enter 키(Shift 없이) 또는 Send 버튼으로 전송
- `handleKeyDown` (line 448-453): Shift+Enter는 줄바꿈, Enter만은 전송

#### 3.2 AgenticRAGRequest 구성

`sendMessage` 함수 (line 217-431)에서 요청 객체를 구성합니다:

```typescript
const request: AgenticRAGRequest = {
  message: text,                          // 사용자 입력 텍스트
  product: isAutoMode ? 'auto' : selectedProducts[0],  // Auto 또는 선택된 제품
  products: selectedProducts || undefined, // 다중 제품 선택 시
  selected_product: overrideProduct,       // 되묻기 후 사용자가 선택한 제품
  language: 'ja',                          // 고정: 일본어
  history: messages                        // 최근 10개 대화 이력
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .slice(-10)
    .map(m => ({ role: m.role, content: m.content, product: m.product })),
};
```

#### 3.3 제품 선택 모드

| 모드 | 조건 | 동작 |
|------|------|------|
| **Auto** | `isAutoMode === true` | `product: "auto"`, 서버가 자동 판별 |
| **단일 선택** | 트리 드롭다운에서 1개 | `product: "mvs_openframe_7.1"` |
| **다중 선택** | 체크박스로 N개 | `products: ["mvs_openframe_7.1", "openframe_hidb_7"]` |
| **되묻기 응답** | 서버 clarification 후 클릭 | `selected_product: "tibero_7fixset01"` |

#### 3.4 UI State 관리

```typescript
const [messages, setMessages] = useState<ChatMessage[]>([]);  // 채팅 메시지
const [isStreaming, setIsStreaming] = useState(false);          // 스트리밍 중
const [input, setInput] = useState('');                         // 입력 텍스트
const [isAutoMode, setIsAutoMode] = useState(true);            // Auto 모드
const [selectedProducts, setSelectedProducts] = useState<string[]>([]); // 선택 제품
```

---

## 4. Phase 2: API 요청 전송 (SSE)

### 파일 위치
- `kms-portal-ui/src/pages/AgenticRAGPage.tsx` (line 248-414)
- `kms-portal-ui/src/api/agentic-rag.api.ts` (line 74-116)

### SSE 연결 방식

```typescript
// fetch API로 SSE 스트림 연결
const response = await fetch('/api/v1/agentic-rag/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  },
  body: JSON.stringify(request),
  credentials: 'include',
  signal: abortControllerRef.current.signal,  // 취소 지원
});

// ReadableStream으로 SSE 파싱
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const chunks = buffer.split('\n\n');      // SSE 이벤트 구분자
  buffer = chunks.pop() || '';               // 미완성 청크는 버퍼에 보관

  for (const chunk of chunks) {
    const trimmed = chunk.trim();
    if (!trimmed.startsWith('data: ')) continue;
    const event = JSON.parse(trimmed.slice(6));  // "data: " 제거 후 파싱
    // → 이벤트 타입별 처리 (Phase 11에서 상세 설명)
  }
}
```

### 주요 특성

| 항목 | 값 |
|------|-----|
| HTTP Method | POST |
| Content-Type | application/json (요청) / text/event-stream (응답) |
| 인증 | Bearer JWT Token |
| 취소 | AbortController.signal |
| 이벤트 구분자 | `\n\n` (SSE 표준) |
| 데이터 접두사 | `data: ` |

---

## 5. Phase 3: 백엔드 라우터 수신

### 파일 위치
- `app/api/routers/agentic_rag.py` (line 162-194)
- `app/api/core/deps.py` (`get_current_user`)

### 라우터 등록

```python
# app/api/main.py에서 등록
from .routers import agentic_rag
app.include_router(agentic_rag.router, prefix=API_PREFIX)
# → /api/v1/agentic-rag/*
```

### 스트리밍 엔드포인트

```python
@router.post("/stream")
async def stream_chat(
    request: AgenticRAGRequest,           # Pydantic 자동 파싱
    current_user: dict = Depends(get_current_user),  # JWT 인증
):
    # user_id 주입 (Long-term Memory용)
    request.user_id = current_user.get("user_id", "anonymous")

    async def generate():
        service = get_agentic_rag_service()  # 싱글턴 서비스
        async for event in service.stream_chat(request):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화
        },
    )
```

### 인증 처리 (`get_current_user`)

```
Authorization: Bearer <JWT> → deps.py:get_current_user()
    ├─ JWT 디코딩 (JWT_SECRET_KEY)
    ├─ 만료 검사 (exp claim)
    ├─ user_id, username, role 추출
    └─ 실패 시 HTTP 401 Unauthorized
```

### 요청 모델 (AgenticRAGRequest)

```python
class AgenticRAGRequest(BaseModel):
    message: str                          # 사용자 질문 (필수)
    product: str = "auto"                 # 제품 ID 또는 "auto"
    products: Optional[List[str]] = None  # 다중 제품 선택
    selected_product: Optional[str] = None  # 되묻기 후 확정 제품
    history: Optional[List[dict]] = None  # 대화 이력
    file_content: Optional[str] = None    # 첨부 파일 텍스트
    language: str = "ja"                  # 언어 (ja/ko/en)
    user_id: Optional[str] = None         # 서버에서 주입
```

---

## 6. Phase 4: 제품 라우팅 (Product Resolution)

### 파일 위치
- `app/api/services/agentic_rag_service.py` → `_resolve_search_products()` (line 192-282)
- `app/api/services/query_router_service.py` → `QueryRouter.classify()` (line 127-200)
- `app/api/services/product_router_service.py` → `ProductRouterService.classify()`

### 처리 순서

```
_resolve_search_products(request)
    │
    ├─ Case 1: selected_product 존재 → [selected_product], CONFIRMED
    ├─ Case 2: products 리스트 존재 → products, CONFIRMED
    ├─ Case 3: product != "auto" → [product], CONFIRMED
    │
    └─ Case 4: Auto 모드 (product == "auto")
         │
         ▼
    QueryRouter.classify(query, language, history)
         │
         ▼
    ProductRouterService.classify(query)
         │  ├─ 키워드 매칭 (keyword weight: 0.15)
         │  └─ 패턴 매칭 (pattern weight: 0.3)
         │  → 각 제품별 점수 계산 (max_score=1.5 정규화)
         │
         ▼
    다단계 판정
         ├─ top >= 0.8 AND gap >= 0.3 → CONFIRMED
         ├─ 0.5 <= top < 0.8 → CLARIFICATION_NEEDED
         │     └─ 자동 확정 조건: 후보 1개 + conf >= 0.6 → CONFIRMED
         └─ top < 0.5 → NO_MATCH
              ├─ all_scores 중 점수 > 0인 상위 5개 → fallback 검색
              └─ 점수 없음 → Long-term Memory 조회
                   ├─ session_product (현재 세션)
                   └─ recent_product (전역)
```

### 점수 계산 상세

| 매칭 방식 | Weight | 예시 |
|-----------|--------|------|
| 키워드 정확 매칭 | 0.15 × 키워드 가중치 | "tjesmgr" → openframe_mvs (+0.15 × 2.0) |
| 패턴 매칭 (정규식) | 0.3 × 패턴 가중치 | `/tjes\w*/i` → openframe_mvs (+0.3 × 1.5) |
| 정규화 | ÷ 1.5 (max_score) | 최종 점수: 0.0 ~ 1.0 |

### SSE 이벤트 출력

```python
# 분류 결과 전송 (항상)
yield {"type": "classification", "product": primary_product, "products": product_ids,
       "decision": "CONFIRMED", "confidence": 0.85}

# 되묻기 필요 시 (CLARIFICATION_NEEDED + 자동확정 불가)
yield {"type": "clarification_needed",
       "candidates": [{"product": "mvs_openframe_7.1", "confidence": 0.65, ...}, ...],
       "message": "どの製品に関する質問ですか？"}
# → 스트림 종료
```

### Long-term Memory

```
ProductContextMemory (LangGraph InMemoryStore)
    ├─ save_product_context(user_id, session_id, product_id, query, confidence)
    │     → 라우팅 성공 시 저장
    ├─ get_session_product(user_id, session_id)
    │     → 현재 세션의 최근 제품
    └─ get_recent_product(user_id)
          → 전역 최근 제품
```

---

## 7. Phase 5: Web Doc Fast Path

### 파일 위치
- `app/api/services/agentic_rag_service.py` → `_search_web_doc()` (line 938-973), `stream_chat()` (line 649-704)
- `app/api/services/web_doc_search_service.py` → `WebDocSearchService`

### 처리 순서

```
_search_web_doc(query, language, product_ids)
    │
    ├─ product_id 매핑 (라우터ID → web doc ID)
    │     예: "openframe_mvs" → ["mvs_openframe_7.1", "openframe_hidb_7", ...]
    │
    ├─ WebDocSearchService.search(query, language, product_ids, top_k=1)
    │     ├─ 인메모리 keyword + IDF 검색 (<10ms)
    │     └─ uploads/web_doc_index/index.json (643 pages, 14 components)
    │
    └─ normalized_score >= 0.9 (WEB_DOC_THRESHOLD)?
         ├─ Yes → Fast Path 진입
         │     ├─ SSE: web_doc_match 이벤트
         │     ├─ httpx.get(url, verify=False) → HTML fetch
         │     ├─ <article> 태그 추출 → 텍스트 변환
         │     ├─ LLM 스트리밍 생성 (web content를 context로)
         │     ├─ SSE: llm_token 이벤트 (토큰별)
         │     ├─ SSE: sources 이벤트 (domain: "web_doc")
         │     └─ SSE: done 이벤트 → 종료
         └─ No → PDF RAG 파이프라인 계속
```

### 주요 매핑 테이블 (`_LEGACY_TO_WEB_DOC_PIDS`)

| 라우터 Product ID | Web Doc Product IDs |
|-------------------|---------------------|
| `openframe_mvs` | `mvs_openframe_7.1`, `openframe_hidb_7`, `openframe_ndb_7`, `openframe_tacf_7`, `openframe_aim_7` |
| `tibero7` | `tibero_7fixset01` |
| `tmax` | `tmax_6.0` |
| (등 9개 매핑) | |

---

## 8. Phase 6: 질문 유형 분류 (Query Type Classification)

### 파일 위치
- `app/api/services/query_type_classifier.py` → `QueryTypeClassifier.classify()` (line 98+)

### 분류 우선순위 (Regex 기반, LLM 없음)

```
classify(query)
    │
    ├─ 1순위: ERROR_CODE
    │     패턴: -\d{4,5}, ABEND S\d{3}, エラーコード, error code
    │     예: "에러 -5212" → ERROR_CODE
    │
    ├─ 2순위: COMMAND
    │     패턴: tjesmgr \w+, tacfmgr \w+, oscmgr \w+, コマンド, 使い方
    │     예: "tjesmgr BOOTの使い方" → COMMAND
    │
    ├─ 3순위: PARAMETER
    │     패턴: LRECL, RECFM, BLKSIZE, パラメータ
    │     예: "LRECLの設定" → PARAMETER
    │
    ├─ 4순위: CONFIG
    │     패턴: .conf, 設定ファイル, 설정
    │     예: "tjes.confの設定" → CONFIG
    │
    └─ 5순위: FREEFORM (위 어디에도 매칭 안 됨)
          예: "OpenFrameの概要" → FREEFORM
```

### QueryType → 검색 도메인 매핑

| QueryType | 우선 검색 도메인 |
|-----------|-----------------|
| ERROR_CODE | `error_codes`, `error-codes` |
| COMMAND | `commands`, `pdf_manuals` |
| PARAMETER | `configs`, `pdf_manuals` |
| CONFIG | `configs`, `pdf_manuals` |
| FREEFORM | 전체 도메인 |

---

## 9. Phase 7: 다중 제품 검색 (Multi-Product Search)

### 파일 위치
- `app/api/services/agentic_rag_service.py` → `_multi_product_search()` (line 368-437)
- `app/api/services/product_agent_service.py` → `BaseProductAgent.search()` (line 52-70)
- `app/api/services/structured_knowledge_store.py` → `StructuredKnowledgeStore.search()` (line 50+)

### 처리 순서

```
_multi_product_search(query, product_ids, query_type)
    │
    ├─ 1. per-product top_k 자동 조절
    │     ├─ 제품 1~2개: top_k = 5
    │     ├─ 제품 3~5개: top_k = 3
    │     └─ 제품 6개+: top_k = 2
    │
    ├─ 2. Agent별 병렬 검색
    │     ├─ get_product_agent(pid) → BaseProductAgent
    │     ├─ asyncio.Semaphore(5) → 동시 5개 제한
    │     └─ asyncio.gather(*tasks) → 병렬 실행
    │
    │     각 Agent 내부:
    │     BaseProductAgent.search(query, query_type, top_k)
    │         └─ StructuredKnowledgeStore.search(query, domains, top_k)
    │              ├─ _ensure_loaded() → 캐시 로딩 (초회만, 이후 <10ms)
    │              │     ├─ Markdown 파일 파싱 (섹션 단위)
    │              │     ├─ JSON 파일 파싱 (에러코드 등)
    │              │     └─ PDF 파싱 (TOC 기반 or 헤딩 기반)
    │              │           └─ _extract_page_text_with_codeblocks()
    │              │                ├─ _get_shaded_rects(page) → 음영 영역 감지
    │              │                └─ 음영 내 텍스트 → ``` 코드블록 래핑
    │              │
    │              ├─ O(1) 직접 조회 (에러코드, 명령어, 용어)
    │              │     패턴: -5212 → error_codes에서 직접 매칭
    │              │
    │              └─ BM25 키워드 검색
    │                    ├─ CJK 토큰화 (일본어/한국어/중국어)
    │                    ├─ 불용어 필터링 (えてください 등)
    │                    └─ 도메인별 가중치
    │                         ├─ pdf_manuals: 1.5x
    │                         ├─ glossary: 0.6x
    │                         └─ learning_qa: 0.4x
    │
    ├─ 3. 결과 병합 + 정렬 (relevance_score 내림차순)
    │
    ├─ 4. Intent 기반 재순위 (_rerank_by_intent)
    │     ├─ 쿼리 토큰 분리:
    │     │     context: 제품명 (tjes, tibero, ...)
    │     │     generic: 수식어 (機能, 設定, エラー, ...)
    │     │     intent: 핵심 의도 (나머지)
    │     ├─ intent 토큰이 제목에 있으면 +5.0 보너스
    │     ├─ intent 토큰이 본문 200자 내 있으면 +1.0 보너스
    │     └─ 概要/overview 섹션이면 × 0.7 페널티
    │
    └─ 5. Fingerprint 중복 제거
          ├─ 각 결과의 content[:120]로 fingerprint 생성
          ├─ 영숫자 + CJK만 추출하여 비교
          └─ max_total=8개까지 유지
```

### 검색 데이터 소스

| 소스 | 도메인 | 데이터 형태 | 검색 방식 |
|------|--------|------------|----------|
| PDF 매뉴얼 | `pdf_manuals` | TOC/헤딩 기반 섹션 | BM25 + 키워드 |
| 명령어 요약본 | `commands` | Markdown 섹션 | O(1) + BM25 |
| 에러코드 사전 | `error_codes` | Markdown/JSON | O(1) 직접 조회 |
| 설정 요약본 | `configs` | Markdown 섹션 | BM25 |
| 용어 사전 | `glossary` | Markdown (A-Z 파일) | O(1) + BM25 |
| 학습 데이터 | `learning_qa` | JSON Q&A | BM25 |

### SearchResult 구조

```python
@dataclass
class SearchResult:
    title: str            # 섹션 제목
    content: str          # 섹션 본문 (코드블록 포함)
    source_file: str      # 출처 파일명
    source_page: str      # 출처 페이지
    relevance_score: float  # BM25 + 보너스 점수
    domain: str           # 데이터 소스 도메인
    product: str          # 제품 ID
    source_path: str      # PDF 전체 경로 (테이블/이미지 추출용)
```

---

## 10. Phase 8: 응답 생성 (Response Generation)

### 파일 위치
- `app/api/services/agentic_rag_service.py` → `stream_chat()` (line 736-812)
- `app/api/services/template_response_builder.py` → `TemplateResponseBuilder.build()`
- `app/api/services/learning_llm_service.py` → `LearningLLMService.generate_stream()`

### 분기 로직

```
query_type != FREEFORM AND search_context.structured_results?
    │
    ├─ Yes → 정형 응답 (Template Path)
    │     │
    │     ▼
    │     TemplateResponseBuilder.build(query, query_type, results, language)
    │         ├─ _clean_inline_metadata() → 메타데이터 행 제거
    │         ├─ enrich_content_with_tables() → PDF 테이블 보충
    │         ├─ format_as_markdown() → 마크다운 변환
    │         │     ├─ 코드블록(```) 내부 보존
    │         │     ├─ ● ■ ▶ → "- " (불릿)
    │         │     ├─ "1.3. 제목" → "#### 1.3. 제목" (헤딩)
    │         │     └─ 일본어 문장 종결(。) 후 줄바꿈
    │         └─ 참고 테이블 추가 (최상위 결과)
    │     │
    │     ▼
    │     SSE: {"type": "template_response", "content": "...", "query_type": "command"}
    │     SSE: {"type": "sources", ...}
    │     SSE: {"type": "done", ...}
    │     → 종료 (LLM 미사용, 환각 0%)
    │
    └─ No → 비정형 응답 (LLM Path)
          │
          ▼
          _build_llm_context(results, history)
              ├─ PDF 우선: pdf_manuals 결과 >= 1개면 요약본 제외
              ├─ 상위 5개 중 top_score × 0.5 이상인 결과만
              ├─ per_result_limit = 4000 / 결과 수
              ├─ enrich_content_with_tables() → 테이블 보충
              └─ 대화 이력 포맷 (최근 3턴, 800자 제한)
          │
          ▼
          LearningLLMService.generate_stream(
              question=query,
              context=context,           # 최대 4000자
              max_tokens=2048,
              temperature=0.3,
              product=adapter_product,    # 동적 → 어댑터 매핑
          )
              ├─ VLLMAdapter → POST /v1/chat/completions (stream=true)
              │     ├─ model: "learning" (LoRA 어댑터)
              │     ├─ GPU: NVIDIA A100 (vLLM 컨테이너)
              │     └─ 토큰 단위 스트리밍
              └─ LLM 불가 시 fallback:
                    _fallback_from_structured(results)
                    → 검색 결과를 마크다운으로 직접 포맷
          │
          ▼
          SSE: {"type": "llm_token", "token": "OpenFrame"}
          SSE: {"type": "llm_token", "token": "の"}
          SSE: {"type": "llm_token", "token": "概要..."}
          ... (토큰별 스트리밍)
          │
          ▼
          _build_table_supplement(results)
              ├─ 최상위 결과 1개만 (relevance_score >= 10.0)
              ├─ PyMuPDF → page.find_tables()
              ├─ _table_to_markdown(data) → 마크다운 테이블
              └─ _extract_page_images() → base64 이미지
          │
          ▼
          SSE: {"type": "llm_token", "token": "\n\n**참고テーブル:**\n\n| ... |"}
```

### 제품 ID → LLM 어댑터 매핑

```python
_DYNAMIC_TO_ADAPTER_MAP = {
    "mvs_openframe_7.1": "openframe_base",
    "tibero_7fixset01": "tibero7",
    "tmax_6.0": "tmax",
    "jeus_8.5": "jeus",
    ... (19개 매핑)
}
```

---

## 11. Phase 9: 사후 검증 (Post-Verification)

### 파일 위치
- `app/api/services/response_verifier.py` → `ResponseVerifier.verify()` (line 31-80)

### 처리 순서

```
ResponseVerifier.verify(response_text, source_results)
    │
    ├─ 1. 문장 분할 (_split_sentences)
    │     ├─ 일본어: "。" 기준 분할
    │     ├─ 한국어: "." + 줄바꿈 기준
    │     └─ 영어: "." 기준
    │     → 5자 미만 문장 스킵
    │
    ├─ 2. 소스 텍스트 결합
    │     source_texts = [r.content for r in source_results]
    │
    └─ 3. 문장별 검증
          for sentence in sentences:
              ├─ 각 소스 청크와 단어 겹침(word overlap) 계산
              ├─ best_similarity = max(overlaps)
              │
              └─ 등급 판정:
                   ├─ similarity >= 0.7 → VERIFIED (🟢)
                   ├─ 0.4 <= similarity < 0.7 → INFERRED (🟡)
                   └─ similarity < 0.4 → UNVERIFIED (🔴)
```

### SSE 이벤트 출력

```python
yield {
    "type": "verification",
    "sentences": [
        {
            "text": "tjesmgrはTJESのメイン管理ツールです。",
            "level": "verified",      # 🟢
            "similarity": 0.85,
            "source_chunk": "tjesmgr...",
            "source_doc": "OF_TJES_MVS.pdf"
        },
        {
            "text": "バッチジョブの管理に使用されます。",
            "level": "inferred",      # 🟡
            "similarity": 0.55,
            ...
        }
    ]
}
```

### 종합 신뢰도 계산

```python
def _calculate_confidence(verification):
    if not verification:
        return ConfidenceLevel.MEDIUM
    verified_count = sum(1 for v in verification if v.level == VerificationLevel.VERIFIED)
    ratio = verified_count / len(verification)
    if ratio >= 0.7:
        return ConfidenceLevel.HIGH
    elif ratio >= 0.4:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW
```

---

## 12. Phase 10: SSE 스트리밍 전송

### 파일 위치
- `app/api/routers/agentic_rag.py` → `stream_chat()` (line 162-194)

### 전송 형식

```python
async def generate():
    async for event in service.stream_chat(request):
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
```

### 이벤트 순서 (정상 흐름)

#### Template Path (정형 질문)
```
1. classification       → 제품 확정
2. search_progress(0.3) → 검색 시작
3. search_progress(0.6) → 검색 완료
4. template_response    → 전체 응답 (한 번에)
5. sources              → 검색 소스 목록
6. done                 → 완료
```

#### LLM Path (비정형 질문)
```
1. classification       → 제품 확정
2. search_progress(0.3) → 검색 시작
3. search_progress(0.6) → 검색 완료
4. search_progress(0.7) → 생성 시작
5. llm_token × N        → 토큰 스트리밍 (50~200개)
6. llm_token (table)    → 테이블 보충 (있는 경우)
7. verification         → 문장별 검증 결과
8. sources              → 검색 소스 목록
9. done                 → 완료
```

#### Web Doc Fast Path
```
1. classification       → 제품 확정
2. search_progress(0.3) → 검색 시작
3. web_doc_match        → URL/제목 정보
4. search_progress(0.6) → Web doc 생성 중
5. llm_token × N        → 토큰 스트리밍
6. sources              → 소스 (domain: web_doc)
7. done                 → 완료 (web_doc_url 포함)
```

#### 되묻기 (Clarification)
```
1. classification        → 제품 미확정
2. clarification_needed  → 후보 목록 + 메시지
→ 종료 (사용자 선택 대기)
```

### StreamingResponse 헤더

| 헤더 | 값 | 용도 |
|------|-----|------|
| Content-Type | text/event-stream | SSE 표준 |
| Cache-Control | no-cache | 캐시 비활성화 |
| Connection | keep-alive | 연결 유지 |
| X-Accel-Buffering | no | Nginx 프록시 버퍼링 비활성화 |

---

## 13. Phase 11: 프론트엔드 렌더링

### 파일 위치
- `kms-portal-ui/src/pages/AgenticRAGPage.tsx` (line 290-411)
- `kms-portal-ui/src/components/AgentChat/MessageContent.tsx`
- `kms-portal-ui/src/styles/chatgpt-style.css`

### SSE 이벤트 → React State 매핑

| SSE Event | 처리 | React State 변경 |
|-----------|------|------------------|
| `classification` | 제품 ID 저장 | `currentProduct = event.product` |
| `clarification_needed` | 되묻기 카드 표시 | `messages += clarification message` → 스트림 종료 |
| `low_relevance_warning` | 경고 메시지 표시 | `messages += warning message` |
| `search_progress` | (현재 무시) | - |
| `template_response` | 전체 응답 한 번에 | `messages[assistantId].content = event.content` |
| `llm_token` | 토큰 누적 (실시간) | `currentContent += token` → `messages` 업데이트 |
| `web_doc_match` | (현재 무시) | - |
| `verification` | 검증 결과 첨부 | `messages[assistantId].verification = sentences` |
| `sources` | 소스 정보 첨부 | `messages[assistantId].sources = event` |
| `done` | 최종 메타데이터 | `messages[assistantId].queryType = ...` |
| `error` | 에러 메시지 표시 | `messages[assistantId].content = error` |

### llm_token 실시간 업데이트

```typescript
case 'llm_token':
  currentContent += event.token;
  setMessages(prev => {
    const existing = prev.find(m => m.id === assistantId);
    if (existing) {
      return prev.map(m =>
        m.id === assistantId ? { ...m, content: currentContent } : m
      );
    }
    return [...prev, { id: assistantId, role: 'assistant', content: currentContent, ... }];
  });
```

### MessageContent 렌더링 파이프라인

```
msg.content (Markdown 텍스트)
    │
    ▼
<MessageContent content={msg.content} />
    │
    ▼
ReactMarkdown
    ├─ remarkGfm          → GFM 지원 (테이블, 취소선, etc.)
    ├─ rehypeHighlight     → 코드 구문 하이라이팅 (190+ 언어)
    │
    └─ Custom Components:
         ├─ code ({ className, children })
         │     ├─ 인라인 코드: <code class="chatgpt-inline-code">
         │     └─ 코드블록: <div class="chatgpt-code-block">
         │          ├─ 언어 라벨 표시
         │          ├─ CopyButton (복사 + "Copied!" 피드백)
         │          └─ <pre><code> (syntax highlighted)
         │
         ├─ table → <div class="chatgpt-table-wrapper"><table>
         ├─ img → <img loading="lazy">
         ├─ a → sanitizeUrl(href) → XSS 차단 (javascript:, vbscript:)
         └─ p → <p class="chatgpt-paragraph">
```

### CSS 스타일링 (`chatgpt-style.css`)

| 요소 | CSS 클래스 | 효과 |
|------|-----------|------|
| 코드 블록 | `.chatgpt-code-block` | 다크 배경(#1e1e1e), 둥근 모서리, 언어 표시 |
| Copy 버튼 | `.chatgpt-code-copy` | 우상단, 호버 표시 |
| 인라인 코드 | `.chatgpt-inline-code` | 회색 배경 + 모노스페이스 |
| 테이블 | `.chatgpt-table-wrapper` | 가로 스크롤 + 줄 교대 색상 |
| 헤더 | `.chatgpt-markdown h1-h4` | 크기 계층 + 하단 보더 |
| 리스트 | `.chatgpt-markdown ul/ol` | disc/decimal + 중첩 |
| 인용문 | `.chatgpt-markdown blockquote` | 좌측 초록 보더 |
| 링크 | `.chatgpt-markdown-link` | 밑줄 + XSS 보호 |

### 검증 결과 표시

```
메시지 하단에 "信頼度検証" 섹션:
┌─────────────────────────────────────────┐
│ 🔍 信頼度検証                            │
├─────────────────────────────────────────┤
│ 🟢 "tjesmgrはTJESの管理ツールです。"     │
│    similarity: 0.85 | source: TJES.pdf   │
│ 🟡 "バッチ処理に使用されます。"          │
│    similarity: 0.55 | source: TJES.pdf   │
│ 🔴 "高速な処理が可能です。"              │
│    similarity: 0.25 | source: -           │
└─────────────────────────────────────────┘
```

### 소스 정보 표시

```
메시지 하단에 Sources 섹션:
┌─────────────────────────────────────────┐
│ 📄 Sources                               │
├─────────────────────────────────────────┤
│ [1] OF_TJES_MVS.pdf (p.45)              │
│     score: 15.2 | domain: pdf_manuals    │
│ [2] commands/OpenFrame_TJES_MVS.md       │
│     score: 8.7 | domain: commands        │
└─────────────────────────────────────────┘

또는 Web Doc 소스:
┌─────────────────────────────────────────┐
│ 🌐 Web Documentation                     │
│ https://docs.tmaxsoft.com/openframe/... │
└─────────────────────────────────────────┘
```

---

## 14. SSE 이벤트 타입 정의

| 이벤트 타입 | 발생 시점 | 주요 필드 |
|------------|----------|----------|
| `classification` | 항상 (첫 이벤트) | `product`, `products`, `decision`, `confidence` |
| `clarification_needed` | 제품 미확정 시 | `candidates[]`, `message` |
| `search_progress` | 검색/생성 진행 시 | `step`, `progress` (0.0~1.0) |
| `web_doc_match` | Web Doc 매칭 시 | `url`, `title`, `component`, `score` |
| `low_relevance_warning` | best_score < 0.3 | `message`, `best_score`, `searched_products` |
| `template_response` | 정형 응답 시 | `content`, `query_type` |
| `llm_token` | LLM 토큰 생성 시 | `token` |
| `verification` | LLM 검증 완료 시 | `sentences[]` |
| `sources` | 소스 정보 전송 시 | `results[]`, `total` |
| `done` | 항상 (마지막) | `processing_time_ms`, `product`, `query_type` |
| `error` | 에러 발생 시 | `message` |

---

## 15. 파일 맵

### Frontend

| 파일 | 역할 | 핵심 라인 |
|------|------|----------|
| `kms-portal-ui/src/pages/AgenticRAGPage.tsx` | 메인 UI + SSE 처리 | 217-431 (sendMessage) |
| `kms-portal-ui/src/api/agentic-rag.api.ts` | API 클라이언트 + 타입 정의 | 74-116 (streamChat) |
| `kms-portal-ui/src/components/AgentChat/MessageContent.tsx` | Markdown 렌더러 | 전체 (ChatGPT 스타일) |
| `kms-portal-ui/src/styles/chatgpt-style.css` | ChatGPT 스타일 CSS | 전체 (535 lines) |

### Backend - Router

| 파일 | 역할 | 핵심 라인 |
|------|------|----------|
| `app/api/routers/agentic_rag.py` | API 엔드포인트 | 162-194 (stream) |
| `app/api/core/deps.py` | JWT 인증 | get_current_user |

### Backend - Services

| 파일 | 역할 | 핵심 라인 |
|------|------|----------|
| `app/api/services/agentic_rag_service.py` | 오케스트레이터 | 582-812 (stream_chat) |
| `app/api/services/query_router_service.py` | 다단계 확인 라우터 | 127-200 (classify) |
| `app/api/services/product_router_service.py` | 키워드/패턴 점수 계산 | classify() |
| `app/api/services/product_agent_service.py` | 제품별 Agent | 52-70 (search) |
| `app/api/services/structured_knowledge_store.py` | 구조화 검색 엔진 | search(), _extract_page_text_with_codeblocks() |
| `app/api/services/query_type_classifier.py` | 질문 유형 분류 | 98+ (classify) |
| `app/api/services/template_response_builder.py` | 정형 응답 생성 | build(), format_as_markdown() |
| `app/api/services/learning_llm_service.py` | LLM 추론 서비스 | generate_stream() |
| `app/api/services/response_verifier.py` | 사후 검증 | verify() |
| `app/api/services/web_doc_search_service.py` | Web Doc 검색 | search() |
| `app/api/services/web_doc_crawler_service.py` | Web Doc 크롤러 | crawl() |
| `app/api/services/product_context_memory.py` | Long-term Memory | save/get_product_context() |
| `app/api/services/manual_registry_service.py` | 동적 제품 발견 | get_all_products() |
| `app/api/services/summary_bm25_service.py` | BM25 검색 | search() |

### Backend - Models

| 파일 | 역할 |
|------|------|
| `app/api/models/agentic_rag.py` | AgenticRAGRequest/Response, QueryType, RouterResult, VerifiedSentence |
| `app/api/models/openframe_rag.py` | ProductSources, ConfidenceLevel, VectorSource |
| `app/api/models/web_doc.py` | WebDocSource |

---

## 부록 A: 할루시네이션 검출과 유사도 점수의 구조적 한계

### 현상

LLM 응답에 할루시네이션(사실과 다른 내용)이 포함되어 있음에도 `ResponseVerifier`의 유사도 점수가 높게 측정되는 경우가 있습니다.

### 원인 분석

#### 1. 동일 소스 순환 참조 (Context = Verification Source)

현재 파이프라인에서 LLM 생성과 사후 검증은 **같은 검색 결과**를 사용합니다:

```
검색 결과 (structured_results)
    │
    ├──→ _build_llm_context(results)    → LLM에 컨텍스트로 전달
    │                                       ↓
    │                                   LLM 응답 생성
    │                                       ↓
    └──→ verifier.verify(response, results) → 검증 소스로 사용
```

LLM은 주어진 컨텍스트의 단어/표현을 그대로 활용하여 응답을 생성합니다.
검증기는 그 응답을 같은 소스와 비교하므로, **LLM이 소스 단어를 잘못된 맥락으로 조합하더라도 단어 겹침은 높게 나옵니다.**

#### 2. Word Overlap 방식의 구조적 맹점

`ResponseVerifier._calculate_word_overlap()` (line 97-110)의 측정 방식:

```python
sentence_set = set(sentence_tokens)
source_set = set(source_tokens)
overlap = sentence_set & source_set
return len(overlap) / len(sentence_set)  # 문장 토큰 커버리지
```

이 방식은 **"응답 문장의 단어가 소스에 존재하는가?"** 만 측정합니다.

| 측정하는 것 | 측정하지 못하는 것 |
|------------|-------------------|
| 단어 수준 겹침 | 문장 수준 의미 일치 |
| 소스 어휘 재활용 여부 | 사실관계의 정확성 |
| 토큰 커버리지 비율 | 속성-대상 연결의 정확성 |

**할루시네이션이 높은 유사도를 받는 예시:**

```
소스 A: "tjesmgrはTJESノードの起動、停止、状態確認を行うツールです。"
소스 B: "oscmgrはOSCリージョンの管理ツールです。リージョンの起動、停止を行います。"

할루시네이션 응답: "oscmgrはTJESノードの起動を行うツールです。"
                   → ソースA의 단어(TJES, ノード, 起動, ツール) + ソースB의 단어(oscmgr)
                   → word overlap ≈ 0.8 (높음) ← 사실은 완전히 틀린 문장
```

#### 3. 코드블록/테이블 보충에 의한 점수 부풀림

최근 추가된 두 가지 기능이 유사도를 구조적으로 높입니다:

**a) PDF 음영 영역 코드블록 추출 (`_extract_page_text_with_codeblocks`)**

```
이전: 코드 예시가 일반 텍스트로 추출 → 줄바꿈 소실, 단어 경계 훼손
현재: 코드 예시가 ``` 코드블록으로 정확히 보존 → 소스에 완전한 코드 텍스트 존재
```

코드 블록 내 텍스트(명령어, 옵션, 출력 예시)는 소스와 응답에서 **동일한 형태로 존재**하므로 word overlap이 대폭 상승합니다.

**b) 테이블 보충 (`_build_table_supplement`)**

```python
# agentic_rag_service.py line 777-782
if search_context.structured_results:
    table_supplement = self._build_table_supplement(search_context.structured_results)
    if table_supplement:
        yield {"type": "llm_token", "token": table_supplement}
        full_response += table_supplement  # ← 응답 텍스트에 포함

# 이후 검증:
verification = self.response_verifier.verify(full_response, search_context.structured_results)
```

테이블은 PDF에서 직접 추출한 원문이므로 소스와 100% 일치합니다.
이 테이블이 `full_response`에 포함된 채 검증되면, 테이블 부분의 높은 유사도가 전체 검증 결과를 끌어올립니다.

#### 4. PDF 우선 정책에 의한 어휘 집중

```python
# _build_llm_context() line 1152
results = _select_tiered_results(results, min_primary=1)
# PDF 결과가 1개 이상이면 요약본/학습데이터 제외 → PDF만 사용
```

PDF 매뉴얼은 전문 용어가 고밀도로 집중되어 있어, LLM이 같은 전문 용어를 재사용할 확률이 높습니다. 검증 소스도 같은 PDF이므로 어휘 겹침이 자연적으로 높아집니다.

#### 5. 소스 텍스트 크기에 따른 확률적 겹침

```python
# response_verifier.py line 63-64
for i, source_text in enumerate(source_texts):
    sim = self._calculate_word_overlap(sentence, source_text)
```

각 `source_text`는 `r.content` 전체 (최대 `_MAX_SECTION_CHARS`)입니다.
수천 자의 소스 텍스트에는 다양한 단어가 포함되어 있으므로, 짧은 응답 문장의 단어가 우연히 겹칠 확률이 높아집니다.

| 소스 크기 | 응답 문장 10 토큰 중 겹침 기대치 |
|-----------|-------------------------------|
| 100 토큰 | ~30% (0.3) |
| 500 토큰 | ~50% (0.5) |
| 2000 토큰 | ~70-80% (0.7+) → VERIFIED |

### 영향도 요약

```
유사도 점수 = f(단어 겹침)

높은 유사도 ≠ 정확한 응답

실제 정확성에 영향을 미치는 요소:
  ① 사실관계 정확성 (속성-대상 매핑)  → 미측정
  ② 인과관계 정확성 (원인-결과)        → 미측정
  ③ 수치/코드 정확성                   → 부분 측정 (동일 토큰이면 겹침)
  ④ 소스 어휘 재활용                   → 측정됨 (현재 방식)
```

### 개선 방향 (향후)

| 방안 | 효과 | 복잡도 |
|------|------|--------|
| **N-gram overlap** (bigram/trigram) | 단어 순서 고려 → 조합 오류 감지 | 낮음 |
| **테이블 보충 분리 검증** | 테이블을 제외한 텍스트만 검증 | 낮음 |
| **Embedding 기반 유사도** | 의미 수준 비교 (word2vec, sentence-BERT) | 중간 |
| **NLI (Natural Language Inference)** | 소스와 응답의 논리적 함의 관계 판정 | 높음 |
| **Fact extraction + matching** | 주어-술어-목적어 트리플 추출 비교 | 높음 |

---

## 부록 B: 성능 특성

| 단계 | 소요 시간 | LLM 사용 |
|------|----------|----------|
| JWT 인증 | <1ms | No |
| 제품 라우팅 | <5ms | No |
| Web Doc 검색 | <10ms | No |
| 질문 유형 분류 | <1ms | No |
| 구조화 검색 (캐시 후) | <10ms/제품 | No |
| 템플릿 응답 생성 | <5ms | No |
| LLM 생성 (스트리밍) | 2~10s | **Yes** |
| 사후 검증 | <50ms | No |
| **총 (Template Path)** | **<50ms** | **No** |
| **총 (LLM Path)** | **2~10s** | **Yes** |

---

## 부록 C: Web Document 검색 추가 후 답변 정확도 향상 원인 분석

### 현상

Web Doc Fast Path(Phase 5) 추가 이후, 동일한 질문에 대해 답변 정확도가 체감적으로 상승했습니다. 이 섹션에서는 소스 코드 레벨에서 그 구조적 원인을 분석합니다.

### 원인 1: 단일 페이지 전체 컨텍스트 vs 파편화된 PDF 조각

**PDF RAG 경로** (`_build_llm_context()`, line 1141-1181):

```
검색 결과 최대 5개 → relevance_score × 0.5 필터
→ 각 결과를 per_result_limit(~800자)로 잘라서 이어붙임
→ 총 예산: _MAX_LLM_CONTEXT_CHARS = 4000자
```

- PDF에서 추출한 텍스트는 TOC 기반 섹션 분할 → BM25 매칭 → top-k 수집
- 관련 있는 여러 섹션의 **조각들**이 `---`로 연결됨
- LLM은 불완전한 단편들을 보고 추론 → 빈 부분을 자체 지식으로 메움 → **할루시네이션 발생**

**Web Doc Fast Path** (`stream_chat()`, line 672-674):

```python
web_context = f"[Web Documentation: {title}]\nURL: {url}\n\n{web_content}"
# 단일 페이지의 전체 내용이 하나의 컨텍스트로 제공
```

- `_fetch_web_doc_content()`가 `<article>` 태그 내 전체 본문을 추출 (line 993-998)
- **하나의 완전한 문서 페이지**가 통째로 LLM 컨텍스트가 됨
- LLM이 추론/보간할 필요 없이 있는 그대로 정리만 하면 됨

| 항목 | PDF RAG | Web Doc Fast Path |
|------|---------|-------------------|
| 컨텍스트 구성 | 5개 조각 × ~800자 (파편) | 1개 페이지 전체 (완결) |
| LLM 역할 | 단편 조합 + 추론 보간 | 원문 정리 + 요약 |
| 할루시네이션 리스크 | 빈 부분을 메우면서 발생 | 원문이 완전하므로 낮음 |

### 원인 2: 매우 높은 진입 임계값 (score >= 0.9)

```python
# web_doc_search_service.py line 64
WEB_DOC_THRESHOLD = 0.9
```

Web Doc Fast Path는 정규화 점수 0.9 이상일 때만 활성화됩니다.

**스코어링 구조** (`WebDocSearchService`, line 94-218):

```
TITLE_WEIGHT = 3.0    # 타이틀 매칭 가중치
CONTENT_WEIGHT = 1.0  # 본문 매칭 가중치

normalized = raw_score / max_possible
max_possible = sum(idf[t] × TITLE_WEIGHT)  # 모든 토큰이 타이틀 매칭 시
coverage_factor = 0.5 + 0.5 × (matched_tokens / total_tokens)
```

점수 0.9 이상이 되려면 쿼리 토큰 대부분이 **페이지 타이틀에서** 매칭되어야 합니다:
- 예: `"dbdcpybkgen"` → 타이틀이 정확히 `"dbdcpybkgen"` 인 페이지만 매칭
- **오탐(false positive)이 구조적으로 거의 불가능**

반면 PDF RAG 경로의 `StructuredKnowledgeStore.search()`는 BM25 상대 점수 기반 top-k 반환이므로, 관련성이 낮은 섹션도 상위에 올 수 있습니다.

### 원인 3: 구조화된 HTML vs 비구조화된 PDF 텍스트

**Web Doc 소스** (docs.tmaxsoft.com, Antora 3.1.12):

```
<article>
  <h1>dbdcpybkgen</h1>
  <p>メインフレームIMS/DBの特定のDBDから...</p>
  <h2>使用方法</h2>
  <pre><code>$ dbdcpybkgen EXHIDAM</code></pre>
  <table>...</table>
</article>
```

- 의미적으로 구분된 HTML 태그 (`<h1>`, `<p>`, `<code>`, `<table>`)
- `<article>` 추출 시 네비게이션/사이드바/헤더/푸터 자동 제외
- 깔끔한 줄바꿈과 단락 구분

**PDF 텍스트** (`_extract_page_text_with_codeblocks()`):

```
page.get_text("text") → 헤더/푸터/페이지번호 포함
표 내용이 줄 단위로 풀려서 의미 구분 어려움
코드 블록은 shaded rect 감지로 보정하지만 표/리스트 구조는 손실
```

| 요소 | PDF 추출 | HTML 추출 |
|------|---------|----------|
| 코드 블록 | 음영 감지 후 래핑 (간접) | `<pre><code>` 직접 인식 |
| 테이블 | `find_tables()` 별도 추출 | `<table>` 태그 보존 |
| 헤더/푸터 | 본문에 혼입 | `<article>` 외부 → 자동 제외 |
| 리스트 구조 | 줄바꿈으로 평탄화 | `<ul>/<ol>` 계층 보존 |

### 원인 4: 파이프라인 단축 → 오류 누적 제거

**PDF RAG 경로 (7단계)**:

```
질문 → Product Router → Query Type → Agent Search(BM25+keyword)
  → _select_tiered_results → _build_llm_context(4000자 예산배분)
  → LLM 생성 → Post-Verification
```

각 단계에서 정보 손실/오류가 누적됩니다:
- Product Router가 잘못된 제품 선택 → 검색 범위 자체가 틀림
- BM25 검색에서 관련 섹션 누락 가능
- 4000자 예산 배분 과정에서 핵심 내용 잘릴 수 있음

**Web Doc Fast Path (3단계)** (line 649-704):

```
질문 → Web Doc Search(IDF+title) → fetch HTML → LLM 생성
```

- Product Router 이후 **즉시** web doc 검색 수행
- 매칭되면 Query Type 분류, Agent Search, 예산 배분 등 **전부 스킵**
- 오류 누적 지점 자체가 절반으로 줄어듦

```
PDF 경로:  7단계 → 오류 확률 = 1 - (1-p)^7 ≈ 높음
Web 경로:  3단계 → 오류 확률 = 1 - (1-p)^3 ≈ 낮음
```

### 원인 5: 온라인 문서의 원문 충실도

Web Doc 인덱스는 docs.tmaxsoft.com에서 크롤링한 **최신 온라인 매뉴얼**:
- `WebDocCrawlerService`: 643 페이지, 14 컴포넌트 (`web_doc_crawler_service.py`)
- HTML 원문이므로 텍스트 추출 과정의 품질 저하가 없음
- 같은 내용이라도 PDF `get_text()`보다 깔끔한 텍스트

### 원인 6: LLM에 URL 출처 명시 → 응답 품질 향상

Web doc 컨텍스트는 URL을 포함합니다:

```python
web_context = f"[Web Documentation: {title}]\nURL: {url}\n\n{web_content}"
```

LLM이 정확한 출처를 인식하고, 해당 문서의 구조를 존중하여 응답을 생성합니다. PDF 경로에서는 `[参考資料 1: セクション名 (出典: filename.pdf)]` 형식으로 파일명만 제공됩니다.

### 종합 비교

| 요인 | PDF RAG 경로 | Web Doc Fast Path | 정확도 영향 |
|------|-------------|-------------------|------------|
| 컨텍스트 완결성 | 5개 조각 × ~800자 | 1개 페이지 전체 | **가장 큰 차이** |
| 진입 임계값 | BM25 top-k (상대 순위) | normalized >= 0.9 (절대 기준) | 오탐 제거 |
| 텍스트 품질 | PDF `get_text()` + 후처리 | HTML `<article>` 추출 | 구조 보존 |
| 파이프라인 깊이 | 7단계 (오류 누적) | 3단계 (빠른 종료) | 오류 경로 축소 |
| 콘텐츠 최신성 | 정적 PDF | docs.tmaxsoft.com (최신) | 정보 정확성 |
| 출처 명시 | 파일명만 | URL + 타이틀 | LLM 응답 품질 |

### 핵심 결론

Web Doc Fast Path의 정확도 우위는 "더 좋은 검색 알고리즘" 때문이 아니라, 다음 두 가지 구조적 설계에서 나옵니다:

1. **높은 확신(0.9)일 때만 발동** → 오탐이 거의 없음
2. **완전한 단일 페이지를 통째로 LLM에 제공** → 추론/보간 불필요

PDF RAG가 여러 조각을 조합해서 4000자 예산 안에 우겨넣는 것과 근본적으로 다릅니다. 이는 곧 PDF RAG 경로의 개선 방향도 시사합니다: **검색 결과의 완결성을 높이는 것**이 검색 알고리즘 자체를 개선하는 것보다 효과적일 수 있습니다.
