# Plan: RAG Context Injection - Neo4j 문서 검색으로 할루시네이션 방지

## 1. Problem Statement

현재 local-coder의 vLLM(Qwen3-32b)은 OpenFrame 제품에 대한 질문에 답변할 때 컴파일 옵션, 설정값, 명령어 파라미터 등 세부 사항에서 할루시네이션이 발생한다.

**근본 원인**: `tool_search_webdoc`이 ofcode-server의 웹문서 인덱스(TF-IDF 기반, 887건)만 검색하며, 원격 서버(192.168.8.11)의 Neo4j에 이미 임베딩된 **전체 OpenFrame 매뉴얼**(bge-m3 1024차원 벡터)을 활용하지 않고 있다.

**기존 인프라 현황**:
- Neo4j (`bolt://192.168.8.11:7687`): `:Document → :Chunk` 구조, `chunk_embedding` 벡터 인덱스 (1024d, cosine)
- bge-m3 (`http://192.168.8.11:12801`): Dense(1024d) + Sparse + Hybrid 임베딩 서비스
- PostgreSQL (`192.168.8.11:5432`): `text_chunks` 테이블, pgvector 4096d

## 2. Goal

LLM에게 질문 관련 **정확한 문서 컨텍스트**를 Neo4j 벡터 검색으로 가져와 전달하여 할루시네이션을 제거한다.

**성공 기준**:
- 컴파일 옵션 질문 시 실제 매뉴얼 내용 기반 답변 생성
- 검색 결과에 출처(문서명, 페이지) 포함
- 기존 E2E 테스트 87/87 PASS 유지
- 응답 지연 1초 미만 (벡터 검색 추가분)

## 3. Approach

`tool_search_webdoc`의 4단계 검색에 **Neo4j 벡터 검색을 Step 0 (최우선)**으로 추가한다.

### 검색 순서 (5단계 Combined Results)

```
Step 0: Neo4j 벡터 검색 (bge-m3 임베딩, 가장 정확)  ← NEW
Step 1: Web docs — product-filtered (기존)
Step 2: Web docs — all products (기존)
Step 3: of7 source code — product module (기존)
Step 4: of7 source code — all modules (기존)
```

### 아키텍처

```
User Query
    ↓
tool_search_webdoc(query, product)
    ↓
┌─── Step 0: Neo4j RAG ───────────────────────┐
│  1. bge-m3 /v1/embeddings → query vector    │
│  2. Neo4j vector search (chunk_embedding)    │
│  3. Product filtering by filename pattern    │
│  4. Top-3 chunks with content + metadata     │
└──────────────────────────────────────────────┘
    ↓
Steps 1-4: 기존 webdoc + of7 검색 (변경 없음)
    ↓
Combined Results → LLM
```

## 4. Implementation Plan

### 4.1 ofcode-server에 Neo4j RAG 엔드포인트 추가

**File**: `server/ofcode_server.py`

새 API 엔드포인트:
- `POST /api/rag/search` — Neo4j 벡터 검색
  - Input: `{"query": str, "product": str, "top_k": int}`
  - Process:
    1. bge-m3 `/v1/embeddings`로 query 벡터 생성
    2. Neo4j `db.index.vector.queryNodes('chunk_embedding', k, embedding)` 실행
    3. Product별 filename 패턴으로 필터링
  - Output: `{"results": [{"content", "doc_name", "page_number", "score"}]}`

**File**: `server/rag_service.py` (NEW)

Neo4j + bge-m3 연동 서비스:
```python
class RAGService:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password, bge_m3_url):
        ...

    async def vector_search(self, query, product="", top_k=3):
        # 1. Get embedding from bge-m3
        # 2. Query Neo4j vector index
        # 3. Filter by product
        # 4. Return chunks with metadata
```

### 4.2 Product → Filename 패턴 매핑

KMS의 기존 매핑을 참조하여 ofcode-server에 포함:

```python
PRODUCT_FILE_PATTERNS = {
    "OFASM": ["ofasm"],
    "OSC": ["osc", "cics"],
    "BATCH": ["batch", "tjes"],
    "IMS": ["ims"],
    "BASE": ["of_base", "openframe"],
    "OFCOBOL": ["ofcobol", "cobol"],
    "JEUS": ["jeus"],
    "TIBERO": ["tibero"],
    "PROSORT": ["prosort"],
    # IBM 매뉴얼
    "IBM": ["asmr1022", "hlasm"],
}
```

### 4.3 tool_search_webdoc에 Neo4j 검색 통합

**File**: `openframe_code/core.py`

`tool_search_webdoc()` 수정:
```python
def tool_search_webdoc(query, product=""):
    lines = []

    # Step 0: Neo4j RAG (most accurate, from full manuals)
    rag_result = _ofcode_api("/api/rag/search", {
        "query": query, "product": product, "top_k": 3
    })
    if not isinstance(rag_result, str):
        entries = rag_result.get("results", [])
        if entries:
            lines.append("── Manual (Neo4j RAG) ──")
            lines.extend(_format_rag_entries(entries))

    # Steps 1-4: existing webdoc + of7 search (unchanged)
    ...
```

### 4.4 Docker 환경 설정

`docker-compose.yml`의 ofcode-server에 환경변수 추가:
```yaml
ofcode-server:
  environment:
    NEO4J_URI: bolt://192.168.8.11:7687
    NEO4J_USER: neo4j
    NEO4J_PASSWORD: graphrag2024
    BGE_M3_URL: http://192.168.8.11:12801
```

### 4.5 E2E 테스트 추가

**File**: `test_webdoc_e2e.py`

새 테스트:
- `test_rag_search_api()`: `/api/rag/search` 직접 호출 테스트
- `test_rag_in_combined_results()`: `tool_search_webdoc` 반환에 Neo4j 결과 포함 확인
- `test_rag_reduces_hallucination()`: 컴파일 옵션 질문 시 매뉴얼 기반 답변 확인

## 5. Files to Modify

| File | Action | Changes |
|------|--------|---------|
| `server/rag_service.py` | NEW | Neo4j + bge-m3 벡터 검색 서비스 |
| `server/ofcode_server.py` | MODIFY | `/api/rag/search` 엔드포인트 추가, startup에서 RAGService 초기화 |
| `openframe_code/core.py` | MODIFY | `tool_search_webdoc`에 Step 0 추가, `_format_rag_entries` 함수 |
| `server/requirements.txt` or Dockerfile | MODIFY | `neo4j` Python driver 의존성 추가 |
| `docker-compose.yml` | MODIFY | NEO4J/BGE_M3 환경변수 추가 |
| `test_webdoc_e2e.py` | MODIFY | RAG 검색 테스트 추가 |

## 6. Implementation Order

1. `server/rag_service.py` — Neo4j driver + bge-m3 클라이언트 구현
2. `server/ofcode_server.py` — `/api/rag/search` 엔드포인트 + startup 초기화
3. Docker 설정 — neo4j 드라이버 설치, 환경변수 추가
4. 서버 배포 + API 테스트 (`curl /api/rag/search`)
5. `openframe_code/core.py` — `tool_search_webdoc` Step 0 통합
6. `test_webdoc_e2e.py` — RAG 테스트 추가
7. 배포 + 전체 E2E 테스트
8. LLM 실제 테스트 — 컴파일 옵션 질문으로 할루시네이션 감소 확인

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Neo4j 연결 실패 | RAG 실패 시 기존 4단계 검색으로 graceful fallback |
| bge-m3 임베딩 지연 | 타임아웃 3초 설정, 실패 시 skip |
| Neo4j에 해당 제품 문서 없음 | 빈 결과 시 자동 스킵, 다음 단계로 |
| 컨텍스트 길이 초과 | RAG 결과를 top_k=3, 각 chunk 500자 제한 |
| Docker 네트워크 접근 | ofcode-server → Neo4j/bge-m3 같은 호스트(192.168.8.11) 내부 통신 |

## 8. Dependencies

- 원격 서버 Neo4j 정상 가동 (`bolt://192.168.8.11:7687`)
- bge-m3 서비스 정상 가동 (`http://192.168.8.11:12801`)
- Python `neo4j` 드라이버 패키지
- OpenFrame 매뉴얼이 Neo4j에 임베딩 완료 상태
