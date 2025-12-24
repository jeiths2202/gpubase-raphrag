# KMS API 설계 문서
## GPU Hybrid RAG 기반 Knowledge Management System REST API

**버전**: 1.0.0
**Base URL**: `http://{server}:8000/api/v1`
**작성일**: 2025-12-24

---

## 목차

1. [API 개요](#1-api-개요)
2. [인증](#2-인증)
3. [공통 사항](#3-공통-사항)
4. [Query API](#4-query-api)
5. [Documents API](#5-documents-api)
6. [History API](#6-history-api)
7. [Stats API](#7-stats-api)
8. [Health API](#8-health-api)
9. [Settings API](#9-settings-api)
10. [에러 코드](#10-에러-코드)
11. [WebSocket API](#11-websocket-api)

---

## 1. API 개요

### 1.1 시스템 구성

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React/Streamlit)              │
│                              │                              │
│                              ▼                              │
│                    ┌─────────────────┐                      │
│                    │  Nginx Proxy    │                      │
│                    │  (Port 80)      │                      │
│                    └────────┬────────┘                      │
│                              │                              │
│              ┌───────────────┴───────────────┐              │
│              ▼                               ▼              │
│    ┌─────────────────┐             ┌─────────────────┐      │
│    │  FastAPI        │             │  Static Files   │      │
│    │  (Port 8000)    │             │  (Frontend)     │      │
│    └────────┬────────┘             └─────────────────┘      │
│              │                                              │
│              ▼                                              │
│    ┌─────────────────────────────────────────────────┐      │
│    │              Backend Services                    │      │
│    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────┐ │      │
│    │  │Nemotron │ │Embedding│ │ Mistral │ │ Neo4j │ │      │
│    │  │ :12800  │ │ :12801  │ │ :12802  │ │ :7687 │ │      │
│    │  └─────────┘ └─────────┘ └─────────┘ └───────┘ │      │
│    └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 기술 스택

| 구성 요소 | 기술 |
|----------|------|
| API Framework | FastAPI 0.104+ |
| 문서화 | OpenAPI 3.0 (Swagger) |
| 인증 | JWT (JSON Web Token) |
| 직렬화 | Pydantic v2 |
| 비동기 | asyncio, httpx |

---

## 2. 인증

### 2.1 인증 방식

JWT (JSON Web Token) 기반 Bearer 인증

```http
Authorization: Bearer <access_token>
```

### 2.2 인증 엔드포인트

#### POST /api/v1/auth/login

사용자 로그인 및 토큰 발급

**Request Body**:
```json
{
  "username": "string",
  "password": "string"
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600,
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
}
```

#### POST /api/v1/auth/refresh

토큰 갱신

**Request Body**:
```json
{
  "refresh_token": "string"
}
```

#### POST /api/v1/auth/logout

로그아웃 (토큰 무효화)

**Headers**: `Authorization: Bearer <access_token>`

---

## 3. 공통 사항

### 3.1 요청 헤더

| Header | 필수 | 설명 |
|--------|------|------|
| `Authorization` | 조건부 | Bearer 토큰 (인증 필요 API) |
| `Content-Type` | Yes | `application/json` |
| `Accept-Language` | No | 응답 언어 (ko, ja, en) |
| `X-Request-ID` | No | 요청 추적 ID |

### 3.2 공통 응답 형식

**성공 응답**:
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-12-24T10:30:00Z",
    "processing_time_ms": 1234
  }
}
```

**에러 응답**:
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": { ... }
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-12-24T10:30:00Z"
  }
}
```

### 3.3 페이지네이션

**Request Parameters**:
| Parameter | Type | Default | 설명 |
|-----------|------|---------|------|
| `page` | int | 1 | 페이지 번호 |
| `limit` | int | 20 | 페이지당 항목 수 (max: 100) |
| `sort` | string | - | 정렬 필드 |
| `order` | string | desc | 정렬 방향 (asc, desc) |

**Response Meta**:
```json
{
  "pagination": {
    "page": 1,
    "limit": 20,
    "total_items": 150,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

---

## 4. Query API

RAG 시스템 질의 관련 API

### 4.1 POST /api/v1/query

RAG 질의 실행

**인증**: 필요

**Request Body**:
```json
{
  "question": "OpenFrame 설치 방법을 알려주세요",
  "strategy": "auto",
  "language": "auto",
  "options": {
    "top_k": 5,
    "include_sources": true,
    "conversation_id": "conv_abc123"
  }
}
```

**Request Parameters**:

| Field | Type | Required | Default | 설명 |
|-------|------|----------|---------|------|
| `question` | string | Yes | - | 질문 텍스트 (max: 2000자) |
| `strategy` | string | No | "auto" | 검색 전략 |
| `language` | string | No | "auto" | 응답 언어 |
| `options.top_k` | int | No | 5 | 검색 결과 수 (1-20) |
| `options.include_sources` | bool | No | true | 소스 포함 여부 |
| `options.conversation_id` | string | No | - | 대화 세션 ID |

**Strategy 옵션**:
| Value | 설명 |
|-------|------|
| `auto` | 자동 라우팅 (기본값) |
| `vector` | 벡터 유사도 검색 |
| `graph` | 그래프 관계 탐색 |
| `hybrid` | Vector + Graph 통합 |
| `code` | 코드 생성 (Mistral NeMo) |

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "answer": "OpenFrame을 설치하려면 다음 단계를 따르세요...",
    "strategy": "vector",
    "language": "ko",
    "confidence": 0.92,
    "sources": [
      {
        "doc_id": "doc_12345",
        "doc_name": "OpenFrame_Installation_Guide.pdf",
        "chunk_id": "chunk_001",
        "chunk_index": 5,
        "content": "OpenFrame 설치 전 요구사항...",
        "score": 0.89,
        "source_type": "vector",
        "entities": ["OpenFrame", "Installation", "Linux"]
      }
    ],
    "query_analysis": {
      "detected_language": "ko",
      "query_type": "vector",
      "is_comprehensive": false,
      "is_deep_analysis": false,
      "has_error_code": false
    }
  },
  "meta": {
    "request_id": "req_xyz789",
    "timestamp": "2025-12-24T10:30:00Z",
    "processing_time_ms": 2340
  }
}
```

### 4.2 POST /api/v1/query/stream

스트리밍 응답 질의 (SSE)

**인증**: 필요

**Request Body**: `/api/v1/query`와 동일

**Response**: Server-Sent Events

```
event: start
data: {"query_id": "q_abc123", "strategy": "hybrid"}

event: chunk
data: {"text": "OpenFrame을 "}

event: chunk
data: {"text": "설치하려면 "}

event: sources
data: {"sources": [...]}

event: done
data: {"processing_time_ms": 2340}
```

### 4.3 GET /api/v1/query/classify

질문 분류만 수행 (검색 없이)

**인증**: 필요

**Query Parameters**:
| Parameter | Type | Required | 설명 |
|-----------|------|----------|------|
| `question` | string | Yes | 분류할 질문 |

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "question": "NVSM_ERR_SYSTEM_FWRITE 에러 해결 방법",
    "classification": {
      "strategy": "hybrid",
      "confidence": 0.95,
      "probabilities": {
        "vector": 0.15,
        "graph": 0.20,
        "hybrid": 0.65
      }
    },
    "features": {
      "language": "ko",
      "has_error_code": true,
      "is_comprehensive": false,
      "is_code_query": false
    }
  }
}
```

---

## 5. Documents API

문서 관리 API

### 5.1 GET /api/v1/documents

문서 목록 조회

**인증**: 필요

**Query Parameters**:
| Parameter | Type | Default | 설명 |
|-----------|------|---------|------|
| `page` | int | 1 | 페이지 번호 |
| `limit` | int | 20 | 페이지당 항목 수 |
| `search` | string | - | 문서명 검색 |
| `status` | string | - | 상태 필터 (processing, ready, error) |

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "documents": [
      {
        "id": "doc_12345",
        "filename": "OpenFrame_Guide_v7.pdf",
        "original_name": "OpenFrame_Installation_Guide.pdf",
        "file_size": 2456789,
        "mime_type": "application/pdf",
        "status": "ready",
        "chunks_count": 45,
        "entities_count": 128,
        "embedding_status": "completed",
        "language": "ko",
        "created_at": "2025-12-20T09:00:00Z",
        "updated_at": "2025-12-20T09:15:00Z"
      }
    ]
  },
  "meta": {
    "pagination": {
      "page": 1,
      "limit": 20,
      "total_items": 35,
      "total_pages": 2
    }
  }
}
```

### 5.2 POST /api/v1/documents

문서 업로드

**인증**: 필요

**Content-Type**: `multipart/form-data`

**Request Body**:
| Field | Type | Required | 설명 |
|-------|------|----------|------|
| `file` | file | Yes | PDF 파일 (max: 50MB) |
| `name` | string | No | 문서 표시명 |
| `language` | string | No | 문서 언어 (auto, ko, ja, en) |
| `tags` | string[] | No | 태그 목록 |

**Response** `202 Accepted`:
```json
{
  "success": true,
  "data": {
    "document_id": "doc_67890",
    "filename": "uploaded_file.pdf",
    "status": "processing",
    "message": "문서 업로드가 시작되었습니다. 처리 완료까지 약 2-5분 소요됩니다.",
    "task_id": "task_abc123"
  }
}
```

### 5.3 GET /api/v1/documents/{document_id}

문서 상세 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "id": "doc_12345",
    "filename": "OpenFrame_Guide_v7.pdf",
    "original_name": "OpenFrame_Installation_Guide.pdf",
    "file_size": 2456789,
    "mime_type": "application/pdf",
    "status": "ready",
    "language": "ko",
    "tags": ["installation", "openframe"],
    "stats": {
      "pages": 120,
      "chunks_count": 45,
      "entities_count": 128,
      "avg_chunk_size": 850,
      "embedding_dimension": 4096
    },
    "processing_info": {
      "started_at": "2025-12-20T09:00:00Z",
      "completed_at": "2025-12-20T09:15:00Z",
      "processing_time_seconds": 900
    },
    "created_at": "2025-12-20T09:00:00Z",
    "updated_at": "2025-12-20T09:15:00Z"
  }
}
```

### 5.4 DELETE /api/v1/documents/{document_id}

문서 삭제

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "document_id": "doc_12345",
    "message": "문서가 성공적으로 삭제되었습니다.",
    "deleted_chunks": 45,
    "deleted_entities": 128
  }
}
```

### 5.5 GET /api/v1/documents/{document_id}/chunks

문서의 청크 목록 조회

**인증**: 필요

**Query Parameters**:
| Parameter | Type | Default | 설명 |
|-----------|------|---------|------|
| `page` | int | 1 | 페이지 번호 |
| `limit` | int | 20 | 페이지당 항목 수 |

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "chunks": [
      {
        "id": "chunk_001",
        "index": 0,
        "content": "OpenFrame 설치 가이드 1장...",
        "content_length": 856,
        "has_embedding": true,
        "entities": ["OpenFrame", "Installation"]
      }
    ]
  }
}
```

### 5.6 GET /api/v1/documents/upload-status/{task_id}

업로드 작업 상태 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "task_id": "task_abc123",
    "document_id": "doc_67890",
    "status": "processing",
    "progress": {
      "current_step": "embedding",
      "steps": [
        {"name": "upload", "status": "completed"},
        {"name": "parsing", "status": "completed"},
        {"name": "chunking", "status": "completed"},
        {"name": "embedding", "status": "in_progress", "progress": 65},
        {"name": "indexing", "status": "pending"}
      ],
      "overall_progress": 72
    },
    "started_at": "2025-12-20T09:00:00Z",
    "estimated_completion": "2025-12-20T09:05:00Z"
  }
}
```

---

## 6. History API

질의 히스토리 관리 API

### 6.1 GET /api/v1/history

질의 히스토리 목록 조회

**인증**: 필요

**Query Parameters**:
| Parameter | Type | Default | 설명 |
|-----------|------|---------|------|
| `page` | int | 1 | 페이지 번호 |
| `limit` | int | 20 | 페이지당 항목 수 |
| `conversation_id` | string | - | 대화 세션 필터 |
| `strategy` | string | - | 전략 필터 |
| `from_date` | string | - | 시작 날짜 (ISO 8601) |
| `to_date` | string | - | 종료 날짜 (ISO 8601) |

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "history": [
      {
        "id": "query_abc123",
        "conversation_id": "conv_xyz",
        "question": "OpenFrame 설치 방법",
        "answer_preview": "OpenFrame을 설치하려면...",
        "strategy": "vector",
        "language": "ko",
        "sources_count": 5,
        "processing_time_ms": 2340,
        "created_at": "2025-12-24T10:30:00Z"
      }
    ]
  }
}
```

### 6.2 GET /api/v1/history/{query_id}

질의 상세 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "id": "query_abc123",
    "conversation_id": "conv_xyz",
    "question": "OpenFrame 설치 방법을 알려주세요",
    "answer": "OpenFrame을 설치하려면 다음 단계를 따르세요...",
    "strategy": "vector",
    "language": "ko",
    "sources": [...],
    "query_analysis": {...},
    "processing_time_ms": 2340,
    "created_at": "2025-12-24T10:30:00Z"
  }
}
```

### 6.3 DELETE /api/v1/history/{query_id}

질의 히스토리 삭제

**인증**: 필요

### 6.4 GET /api/v1/conversations

대화 세션 목록 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "conversations": [
      {
        "id": "conv_xyz",
        "title": "OpenFrame 설치 관련 질문",
        "queries_count": 5,
        "last_query_at": "2025-12-24T10:30:00Z",
        "created_at": "2025-12-24T10:00:00Z"
      }
    ]
  }
}
```

### 6.5 POST /api/v1/conversations

새 대화 세션 생성

**인증**: 필요

**Request Body**:
```json
{
  "title": "OpenFrame 설치 질문"
}
```

### 6.6 DELETE /api/v1/conversations/{conversation_id}

대화 세션 삭제 (포함된 모든 히스토리 삭제)

**인증**: 필요

---

## 7. Stats API

시스템 통계 API

### 7.1 GET /api/v1/stats

시스템 전체 통계 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "database": {
      "documents_count": 35,
      "chunks_count": 1250,
      "entities_count": 3400,
      "relationships_count": 5600
    },
    "embeddings": {
      "total_chunks": 1250,
      "with_embedding": 1250,
      "without_embedding": 0,
      "coverage_percent": 100.0,
      "dimension": 4096
    },
    "queries": {
      "total_queries": 5420,
      "today_queries": 45,
      "avg_response_time_ms": 2800,
      "strategy_distribution": {
        "vector": 2100,
        "graph": 1200,
        "hybrid": 1800,
        "code": 320
      }
    },
    "storage": {
      "neo4j_size_mb": 1250,
      "documents_size_mb": 890
    }
  }
}
```

### 7.2 GET /api/v1/stats/queries

질의 통계 상세 조회

**인증**: 필요

**Query Parameters**:
| Parameter | Type | Default | 설명 |
|-----------|------|---------|------|
| `period` | string | "7d" | 기간 (1d, 7d, 30d, 90d) |
| `granularity` | string | "day" | 집계 단위 (hour, day, week) |

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "period": "7d",
    "total_queries": 320,
    "avg_response_time_ms": 2650,
    "timeline": [
      {
        "date": "2025-12-24",
        "queries_count": 45,
        "avg_response_time_ms": 2800,
        "by_strategy": {
          "vector": 18,
          "graph": 12,
          "hybrid": 13,
          "code": 2
        }
      }
    ],
    "top_queries": [
      {
        "question": "OpenFrame 설치 방법",
        "count": 12
      }
    ]
  }
}
```

### 7.3 GET /api/v1/stats/documents

문서 통계 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "total_documents": 35,
    "by_status": {
      "ready": 32,
      "processing": 2,
      "error": 1
    },
    "by_language": {
      "ko": 20,
      "ja": 10,
      "en": 5
    },
    "total_pages": 4200,
    "total_chunks": 1250,
    "avg_chunks_per_document": 36
  }
}
```

---

## 8. Health API

시스템 상태 확인 API (인증 불필요)

### 8.1 GET /api/v1/health

전체 시스템 상태 조회

**인증**: 불필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "timestamp": "2025-12-24T10:30:00Z",
    "services": {
      "api": {
        "status": "healthy",
        "uptime_seconds": 86400
      },
      "neo4j": {
        "status": "healthy",
        "response_time_ms": 15
      },
      "nemotron_llm": {
        "status": "healthy",
        "response_time_ms": 120,
        "gpu": "GPU 6,7"
      },
      "embedding": {
        "status": "healthy",
        "response_time_ms": 85,
        "gpu": "GPU 4,5"
      },
      "mistral_code": {
        "status": "healthy",
        "response_time_ms": 95,
        "gpu": "GPU 0"
      }
    }
  }
}
```

**Response** `503 Service Unavailable`:
```json
{
  "success": false,
  "data": {
    "status": "unhealthy",
    "services": {
      "neo4j": {
        "status": "unhealthy",
        "error": "Connection refused"
      }
    }
  }
}
```

### 8.2 GET /api/v1/health/ready

Readiness 체크 (Kubernetes용)

**Response** `200 OK` or `503 Service Unavailable`

### 8.3 GET /api/v1/health/live

Liveness 체크 (Kubernetes용)

**Response** `200 OK`

---

## 9. Settings API

설정 관리 API

### 9.1 GET /api/v1/settings

현재 설정 조회

**인증**: 필요

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "rag": {
      "default_strategy": "auto",
      "top_k": 5,
      "vector_weight": 0.5,
      "chunk_size": 1000,
      "chunk_overlap": 200
    },
    "llm": {
      "temperature": 0.1,
      "max_tokens": 2048
    },
    "ui": {
      "language": "auto",
      "theme": "dark",
      "show_sources": true
    }
  }
}
```

### 9.2 PATCH /api/v1/settings

설정 업데이트

**인증**: 필요 (Admin)

**Request Body**:
```json
{
  "rag": {
    "top_k": 10
  },
  "ui": {
    "theme": "light"
  }
}
```

**Response** `200 OK`:
```json
{
  "success": true,
  "data": {
    "message": "설정이 업데이트되었습니다.",
    "updated_fields": ["rag.top_k", "ui.theme"]
  }
}
```

---

## 10. 에러 코드

### 10.1 HTTP 상태 코드

| 코드 | 설명 |
|------|------|
| `200` | 성공 |
| `201` | 생성 성공 |
| `202` | 요청 수락 (비동기 처리) |
| `400` | 잘못된 요청 |
| `401` | 인증 필요 |
| `403` | 권한 없음 |
| `404` | 리소스 없음 |
| `422` | 유효성 검증 실패 |
| `429` | 요청 제한 초과 |
| `500` | 서버 오류 |
| `503` | 서비스 불가 |

### 10.2 애플리케이션 에러 코드

| 코드 | HTTP | 설명 |
|------|------|------|
| `AUTH_INVALID_TOKEN` | 401 | 유효하지 않은 토큰 |
| `AUTH_TOKEN_EXPIRED` | 401 | 토큰 만료 |
| `AUTH_INSUFFICIENT_PERMISSION` | 403 | 권한 부족 |
| `QUERY_TOO_LONG` | 400 | 질문이 너무 김 (max: 2000자) |
| `QUERY_EMPTY` | 400 | 빈 질문 |
| `DOCUMENT_NOT_FOUND` | 404 | 문서 없음 |
| `DOCUMENT_TOO_LARGE` | 400 | 파일 크기 초과 (max: 50MB) |
| `DOCUMENT_INVALID_FORMAT` | 400 | 지원하지 않는 파일 형식 |
| `DOCUMENT_PROCESSING_FAILED` | 500 | 문서 처리 실패 |
| `SERVICE_NEO4J_UNAVAILABLE` | 503 | Neo4j 서비스 불가 |
| `SERVICE_LLM_UNAVAILABLE` | 503 | LLM 서비스 불가 |
| `SERVICE_EMBEDDING_UNAVAILABLE` | 503 | 임베딩 서비스 불가 |
| `RATE_LIMIT_EXCEEDED` | 429 | 요청 제한 초과 |

### 10.3 에러 응답 예시

```json
{
  "success": false,
  "error": {
    "code": "DOCUMENT_TOO_LARGE",
    "message": "파일 크기가 제한을 초과했습니다.",
    "details": {
      "max_size_mb": 50,
      "actual_size_mb": 75,
      "filename": "large_document.pdf"
    }
  },
  "meta": {
    "request_id": "req_error123",
    "timestamp": "2025-12-24T10:30:00Z"
  }
}
```

---

## 11. WebSocket API

실시간 업데이트를 위한 WebSocket API

### 11.1 연결

**URL**: `ws://{server}:8000/api/v1/ws`

**Query Parameters**:
| Parameter | Type | Required | 설명 |
|-----------|------|----------|------|
| `token` | string | Yes | JWT 토큰 |

### 11.2 메시지 형식

**Client → Server**:
```json
{
  "type": "subscribe",
  "channel": "document_status",
  "payload": {
    "document_id": "doc_12345"
  }
}
```

**Server → Client**:
```json
{
  "type": "document_status",
  "payload": {
    "document_id": "doc_12345",
    "status": "processing",
    "progress": 65
  },
  "timestamp": "2025-12-24T10:30:00Z"
}
```

### 11.3 채널 목록

| Channel | 설명 |
|---------|------|
| `document_status` | 문서 처리 상태 업데이트 |
| `system_health` | 시스템 상태 변경 알림 |
| `query_stream` | 질의 응답 스트리밍 |

---

## 부록

### A. 데이터 모델

#### Document
```typescript
interface Document {
  id: string;
  filename: string;
  original_name: string;
  file_size: number;
  mime_type: string;
  status: 'processing' | 'ready' | 'error';
  language: 'ko' | 'ja' | 'en' | 'auto';
  tags: string[];
  chunks_count: number;
  entities_count: number;
  created_at: string;
  updated_at: string;
}
```

#### Query
```typescript
interface Query {
  id: string;
  conversation_id?: string;
  question: string;
  answer: string;
  strategy: 'vector' | 'graph' | 'hybrid' | 'code';
  language: 'ko' | 'ja' | 'en';
  sources: Source[];
  processing_time_ms: number;
  created_at: string;
}
```

#### Source
```typescript
interface Source {
  doc_id: string;
  doc_name: string;
  chunk_id: string;
  chunk_index: number;
  content: string;
  score: number;
  source_type: 'vector' | 'graph' | 'hybrid' | 'topic_density';
  entities: string[];
}
```

### B. Rate Limiting

| 엔드포인트 | 제한 |
|------------|------|
| `/api/v1/query` | 60 requests/minute |
| `/api/v1/documents` (POST) | 10 requests/minute |
| 기타 | 120 requests/minute |

### C. Swagger UI 접속

개발 환경에서 Swagger UI를 통해 API를 테스트할 수 있습니다:

- **Swagger UI**: `http://{server}:8000/docs`
- **ReDoc**: `http://{server}:8000/redoc`
- **OpenAPI JSON**: `http://{server}:8000/openapi.json`

---

**문서 버전**: 1.0.0
**최종 수정일**: 2025-12-24
**작성자**: YiJae Shin
