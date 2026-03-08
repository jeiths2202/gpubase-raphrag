# Plan: IMS Semantic Search & Chat Service

> Feature: `ims-semantic-search`
> Created: 2026-03-07
> Status: Plan Phase
> Author: Claude Code

---

## 1. Background & Motivation

### Current State
- IMS(Issue Management System) 이슈 **21,215건**이 텍스트 파일로 보관 (`uploads/ims_issues/`)
- BGE-M3 IR 모델을 통해 이미 **임베딩 완료** (서버 192.168.8.11:12801)
- 기존 IMS 시스템 존재:
  - `ims_chat.py` 라우터 (issue_ids 기반 채팅 - 사용자가 이슈 ID를 알아야 함)
  - `ims_search.py` 도구 (PostgreSQL keyword 검색 + IMS 크롤러)
  - `ims_crawler/` 패키지 (웹 크롤링 기반 이슈 수집)
  - `bge_m3_ir_service.py` (BGE-M3 dense/sparse/hybrid 검색)

### Problem
1. **검색 진입장벽**: 현재 IMS 검색은 issue_id를 미리 알거나 정확한 키워드가 필요
2. **시맨틱 검색 부재**: 21,215건의 임베딩된 IMS 데이터를 자연어로 검색하는 기능 없음
3. **관계 탐색 불가**: 이슈 내 참조된 다른 이슈(IMS#341031 등)나 URL 링크 추적 불가
4. **첨부파일 접근 불가**: 이슈에 언급된 첨부파일 다운로드/분석 기능 없음
5. **지식 재활용 불가**: 이슈 해결 과정의 노하우가 개별 이슈에 묻혀 있음

### Goal
자연어 질의만으로 BGE-M3 임베딩 기반 시맨틱 검색을 수행하고, 검색된 IMS 이슈 내용을 중심으로 심층 대화가 가능한 채팅 서비스를 구축한다.

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | 요구사항 | 우선순위 | 비고 |
|----|----------|----------|------|
| FR-01 | **자연어 시맨틱 검색**: 사용자 질문 → BGE-M3 임베딩 → 유사 IMS 이슈 검색 | P0 (Must) | 기존 `bge_m3_ir_service.py` 활용 |
| FR-02 | **검색 결과 기반 채팅**: 검색된 이슈들을 컨텍스트로 LLM과 심층 대화 | P0 (Must) | 기존 `ims_chat` 패턴 확장 |
| FR-03 | **이슈 요약**: 검색된 이슈 내용을 간결하게 요약 | P0 (Must) | LLM 활용 |
| FR-04 | **관련 이슈 링크 추적**: 이슈 본문 내 `IMS#XXXXXX` 패턴 자동 감지 → 관련 이슈 로드 | P1 (Should) | 정규식: `IMS#(\d{6})` |
| FR-05 | **URL 링크 추적**: 이슈 내 외부 URL 감지 → 메타정보 표시 | P2 (Could) | 보안 필터링 필요 |
| FR-06 | **첨부파일 다운로드 & 분석**: 이슈 첨부파일 접근 및 코드/로그 분석 | P1 (Should) | 기존 Vision/Code LLM 활용 |
| FR-07 | **지식 생성**: 이슈 해결 내용 기반 Knowledge Article 생성 | P2 (Could) | Verified Knowledge 연동 |
| FR-08 | **CLI 인터페이스**: Python 커맨드라인 도구 (`ofims/`) | P0 (Must) | Phase 1 |
| FR-09 | **WebUI 인터페이스**: 프론트엔드 채팅 UI 통합 | P1 (Should) | Phase 2 |

### 2.2 Non-Functional Requirements

| ID | 요구사항 | 목표값 |
|----|----------|--------|
| NFR-01 | 검색 응답 시간 | < 3초 (BGE-M3 encoding + Neo4j search) |
| NFR-02 | 동시 사용자 | 10명 이상 |
| NFR-03 | 검색 정확도 | Top-5 관련도 70% 이상 |
| NFR-04 | 임베딩 데이터 소스 | IMS 이슈 전용 (일반 매뉴얼 RAG와 분리) |

---

## 3. Architecture Overview

### 3.1 System Flow

```
[User Query: "OSC에서 EIBAID 값이 비어있는 문제"]
    |
    v
[Phase 1: CLI (ofims/)]          [Phase 2: WebUI]
    |                                  |
    v                                  v
[API Server (localhost:9000)]
    |
    v
[BGE-M3 IR Service] ── encode_dense() ──> [1024-dim vector]
    |
    v
[Neo4j Vector Search] ── cosine similarity ──> [Top-K IMS Issues]
    |                                              |
    v                                              v
[Issue Content Loader]                    [Related Issue Resolver]
  - uploads/ims_issues/{id}.txt             - IMS#XXXXXX 패턴 추출
  - Server: /raid/.../ims_issues/           - 재귀적 관련이슈 로드
    |                                              |
    v                                              v
[Context Builder] ─── issue_contents + related_issues ───>
    |
    v
[LLM (Qwen 32B / Learning LLM)] ── streaming response ──>
    |
    v
[User: 이슈 기반 답변 + 출처 + 관련이슈 링크]
```

### 3.2 Data Flow

```
IMS Issue Text Files (21,215건)
    |
    |── [이미 완료] BGE-M3 Dense Embedding → Neo4j chunk_embedding index
    |
    |── [신규] 자연어 검색 쿼리 → BGE-M3 encode → Neo4j vector search
    |       |
    |       └── 검색 결과: [{ims_id, score, content_snippet}, ...]
    |
    |── [신규] Issue Content Loading
    |       |── Local: uploads/ims_issues/{ims_id}.txt
    |       └── Remote: /raid/users/ofuser/work/of7/ims_issues_20260302/{ims_id}.txt
    |
    |── [신규] Related Issue Graph
    |       |── IMS#XXXXXX 참조 추출
    |       └── 1-depth 관련이슈 자동 로드
    |
    └── [신규] Knowledge Creation
            └── Issue 해결 내용 → Knowledge Article 변환
```

### 3.3 Key Integration Points

| Component | 기존 코드 | 활용 방식 |
|-----------|----------|----------|
| BGE-M3 IR | `bge_m3_ir_service.py` | `encode_dense()`, `neo4j_vector_search()` 직접 활용 |
| IMS Chat | `ims_chat.py` | 라우터 패턴 참조, 신규 엔드포인트 추가 |
| IMS RAG Integration | `ims_rag_integration.py` | 채팅 서비스 패턴 확장 |
| Learning LLM | `learning_llm_service.py` | `stream_generate()` for 응답 생성 |
| Vision LLM | `vision` 서비스 | 첨부파일 이미지 분석 |
| Legacy Analyze | `legacy-analyze` 스킬 | COBOL/JCL/ASM 코드 분석 |
| Knowledge Article | `knowledge_article.py` | 지식 생성 API |

---

## 4. Implementation Phases

### Phase 1: CLI Tool (ofims/) - P0

**목표**: Python 커맨드라인에서 IMS 시맨틱 검색 + 대화 기능 동작 확인

```
ofims/
├── __init__.py
├── __main__.py           # CLI entry point
├── cli.py                # argparse/click CLI
├── client.py             # API client (requests)
├── config.py             # 설정 (API URL, auth)
├── display.py            # 터미널 출력 포맷팅
└── utils.py              # 유틸리티
```

**CLI Commands**:
```bash
# 시맨틱 검색
python -m ofims search "OSC EIBAID 값이 비어있는 문제"
python -m ofims search "dsmigin 변환 오류" --limit 10

# 이슈 상세 조회
python -m ofims detail 341013

# 검색 + 대화
python -m ofims chat "tjesmgr BOOT 에러 원인과 해결방법"

# 이슈 요약
python -m ofims summarize 341013

# 관련 이슈 탐색
python -m ofims related 341013

# 지식 생성
python -m ofims create-knowledge 341013 --title "OSC EIBAID 처리 가이드"
```

### Phase 2: Backend API - P0/P1

**신규/확장 API 엔드포인트**:

| Endpoint | Method | Description | Priority |
|----------|--------|-------------|----------|
| `POST /api/v1/ims/search` | POST | BGE-M3 시맨틱 검색 | P0 |
| `POST /api/v1/ims/chat/semantic` | POST | 시맨틱 검색 기반 채팅 (SSE) | P0 |
| `GET /api/v1/ims/issues/{ims_id}` | GET | 이슈 상세 (텍스트파일 기반) | P0 |
| `GET /api/v1/ims/issues/{ims_id}/summary` | GET | 이슈 요약 | P0 |
| `GET /api/v1/ims/issues/{ims_id}/related` | GET | 관련 이슈 목록 | P1 |
| `GET /api/v1/ims/issues/{ims_id}/attachments` | GET | 첨부파일 목록 | P1 |
| `GET /api/v1/ims/attachments/{att_id}/download` | GET | 첨부파일 다운로드 | P1 |
| `POST /api/v1/ims/attachments/{att_id}/analyze` | POST | 첨부파일 분석 | P1 |
| `POST /api/v1/ims/knowledge/create` | POST | 이슈 기반 지식 생성 | P2 |

### Phase 3: WebUI Integration - P1

- 기존 KMS Portal UI에 IMS 검색 전용 탭/페이지 추가
- 검색 → 이슈 목록 → 이슈 상세 → 채팅 플로우
- 관련 이슈 그래프 시각화 (optional)

---

## 5. Data Sources & Storage

### 5.1 IMS Issue Text Files

| 위치 | 경로 | 용도 |
|------|------|------|
| Local (개발) | `uploads/ims_issues/{ims_id}.txt` | 개발/테스트용 로컬 복사본 |
| Server (운영) | `/raid/users/ofuser/work/of7/ims_issues_20260302/{ims_id}.txt` | 원본 (21,215건) |

**파일 포맷** (예: `100012.txt`):
```
=== IMS Issue {ims_id} ===
Product: {product_name}
Version: {version}
Module: {module}
Category: {category}
Subject: {title}
Customer: {customer}
Status: {status}
Date: {date}

## 상세 내용
{issue_description}

## 조치 이력
{action_log_entries separated by ---}
```

### 5.2 임베딩 저장소

- **Neo4j Vector Index**: `chunk_embedding` (기존 BGE-M3 1024-dim)
- IMS 이슈 Chunk 노드: `(:Chunk {content, id, page_number})` ← `(:Document {filename})`
- 검색 시 `filename` 필터로 IMS 이슈 문서만 대상

### 5.3 이슈 내 참조 패턴

| 패턴 | 정규식 | 예시 |
|------|--------|------|
| IMS 이슈 번호 | `IMS#(\d{5,6})` | `IMS#341031`, `IMS#344158` |
| Action 번호 | `Action No\.(\d{7})` | `Action No.2209990` |
| HTTP URL | `https?://[^\s<>"]+` | `https://dbpms.tibero.com:7000/...` |
| 첨부파일 참조 | `첨부.*파일\|attachment` | "첨부파일을 확인 부탁드립니다" |

---

## 6. Key Design Decisions

### 6.1 BGE-M3 전용 검색 (일반 RAG와 분리)

**결정**: IMS 시맨틱 검색은 BGE-M3 임베딩 데이터만 사용. 일반 매뉴얼 RAG와 완전 분리.

**근거**:
- IMS 이슈는 도메인 특화 지식 (고객 대응, 버그 해결, 패치 이력)
- 매뉴얼 문서와 혼합 시 노이즈 증가
- Neo4j에서 `Document.filename` 필터로 IMS 이슈 문서만 검색

### 6.2 CLI-First 접근

**결정**: `ofims/` CLI 도구를 먼저 구현, 검증 후 WebUI 적용.

**근거**:
- API 동작 검증이 빠름
- E2E 테스트 자동화 용이
- WebUI 없이도 운용 가능

### 6.3 기존 API 서버 확장

**결정**: 별도 서비스가 아닌 기존 FastAPI 서버에 라우터/서비스 추가.

**근거**:
- BGE-M3 IR Service, Neo4j 연결, LLM 서비스 등 기존 인프라 재사용
- 인증/권한 체계 통합
- 배포 복잡도 최소화

### 6.4 이슈 컨텐츠 로딩 전략

**결정**: 검색은 Neo4j 벡터 검색, 상세 내용은 텍스트 파일에서 직접 로드.

**근거**:
- 임베딩된 Chunk는 요약/분할된 상태 → 전체 이슈 내용이 필요한 채팅에 부적합
- 원본 텍스트 파일(21,215건)에서 전체 이슈 로드가 정확
- 파일 I/O가 DB 쿼리보다 빠름 (< 1ms per file)

### 6.5 관련 이슈 탐색 깊이

**결정**: 1-depth만 자동 로드. 사용자 요청 시 추가 depth.

**근거**:
- 이슈당 평균 2-3개 관련 이슈 참조
- 2-depth 이상은 컨텍스트 폭발 (O(n^depth))
- LLM 컨텍스트 윈도우 제한 (32K tokens)

---

## 7. Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Neo4j에 IMS 이슈 임베딩이 별도 인덱스 없음 | High | Medium | Document filename 필터 or 별도 벡터 인덱스 생성 |
| IMS 이슈 텍스트 파일 인코딩 이슈 (한글/일본어) | Medium | Low | UTF-8 강제, fallback encoding 처리 |
| 대량 검색 결과의 LLM 컨텍스트 초과 | High | Medium | Top-5 제한, 요약 후 삽입 전략 |
| 첨부파일 서버 접근 권한 이슈 | Medium | High | SSH/API 프록시, 권한 확인 로직 |
| 관련 이슈 순환 참조 (A→B→A) | Low | Medium | visited set으로 방문 추적 |

---

## 8. Success Criteria

| Criteria | Metric | Target |
|----------|--------|--------|
| 시맨틱 검색 동작 | CLI에서 자연어 검색 성공 | 100% |
| 검색 품질 | Top-5 관련도 (수동 평가) | >= 70% |
| 채팅 응답 품질 | IMS 이슈 기반 답변 (환각 없음) | >= 90% |
| 관련 이슈 추적 | IMS# 참조 자동 해석 | 100% |
| 이슈 요약 품질 | 핵심 내용 포함 여부 | >= 85% |
| API 응답 시간 | 검색 + 스트리밍 시작 | < 3초 |

---

## 9. Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| BGE-M3 서버 (192.168.8.11:12801) | Running | Dense/Sparse/Hybrid 인코딩 |
| Neo4j (IMS 이슈 임베딩 데이터) | Running | chunk_embedding 인덱스 확인 필요 |
| LLM 서버 (Qwen 32B, port 12810) | Running | 응답 생성용 |
| IMS 이슈 텍스트 파일 | Available | 21,215건, uploads/ims_issues/ |
| FastAPI 서버 | Running | 기존 API 서버 확장 |
| PostgreSQL | Running | IMS 이슈 메타데이터 (기존 ims_crawler) |

---

## 10. Estimated Scope

### Phase 1 (CLI + Core API): ~5 files new, ~3 files modified
- `ofims/` CLI 패키지 (5 files)
- `app/api/services/ims_semantic_search_service.py` (신규)
- `app/api/routers/ims_chat.py` (확장: semantic search endpoint)
- `app/api/core/config.py` (IMS 설정 추가)

### Phase 2 (Advanced Features): ~3 files new, ~2 files modified
- 관련 이슈 resolver, 첨부파일 다운로드, 지식 생성
- `app/api/services/ims_issue_resolver_service.py` (신규)

### Phase 3 (WebUI): ~4 files new (frontend)
- IMS 검색 페이지 컴포넌트
- IMS 채팅 UI 통합

---

## 11. Open Questions

1. **Neo4j 내 IMS 이슈 Document 노드의 filename 패턴은?** → 확인 필요
2. **IMS 첨부파일 서버 접근 방식?** → SSH proxy vs HTTP API
3. **기존 PostgreSQL의 `ims_issues` 테이블과 텍스트 파일의 sync 상태?** → 크롤러 데이터 vs 텍스트 파일 매핑
4. **Knowledge Article 생성 시 승인 프로세스 필요?** → Admin approval flow

---

## Next Step

> `/pdca design ims-semantic-search` 로 Design 문서 작성 진행
