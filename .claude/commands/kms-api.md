---
description: KMS API 테스트를 수행합니다. 인증, RAG 쿼리, OpenFrame RAG 등 주요 API 엔드포인트를 테스트합니다.
---

# KMS API Test Skill

KMS API 엔드포인트를 테스트하는 스킬입니다.

## 사용법

```
/kms-api login         # 로그인 테스트
/kms-api query <질문>  # RAG 쿼리 테스트
/kms-api products      # 제품 목록 조회
/kms-api classify <질문>  # 제품 분류 테스트
```

## 인증

### 로그인 (토큰 획득)
```bash
TOKEN=$(curl -s -X POST http://localhost:9000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d @scripts/login.json | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

echo $TOKEN
```

### 로그인 정보
| 항목 | 값 |
|------|-----|
| API URL | `http://localhost:9000` |
| 인증 파일 | `scripts/login.json` |
| Admin 계정 | `admin` / `SecureAdm1nP@ss2024!` |

## 주요 API 엔드포인트

### 1. RAG 쿼리 (일반)
```bash
curl -s -X POST http://localhost:9000/api/v1/agents/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"task": "tjesmgr 기능 설명", "agent_type": "rag"}'
```

### 2. OpenFrame RAG - 제품 목록
```bash
curl -s http://localhost:9000/api/v1/openframe-rag/products \
  -H "Authorization: Bearer $TOKEN" | jq
```

### 3. OpenFrame RAG - 제품 분류
```bash
curl -s -X POST http://localhost:9000/api/v1/openframe-rag/classify \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "tjesmgr BOOT 명령어"}'
```

### 4. OpenFrame RAG - 쿼리 (스트리밍)
```bash
curl -s -X POST http://localhost:9000/api/v1/openframe-rag/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "에러 -5212 해결법", "product_id": "openframe_mvs"}'
```

### 5. DeepSeek 통합 검색
```bash
curl -s -X POST http://localhost:9000/api/v1/openframe-rag/deep-seek/stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "VSAM 파일 처리"}'
```

## 테스트 스크립트 사용

### 간편 테스트
```bash
./scripts/api_test.sh "tjesmgr 기능"
./scripts/api_test.sh "에러코드 -5212" rag
```

## API 문서

Swagger UI: http://localhost:9000/docs

## 응답 형식

### 성공 응답
```json
{
  "success": true,
  "data": { ... },
  "message": null
}
```

### 에러 응답
```json
{
  "success": false,
  "data": null,
  "message": "Error description"
}
```

## SSE 스트리밍 이벤트

| 이벤트 | 설명 |
|--------|------|
| `classification` | 제품 분류 결과 |
| `token` | 응답 토큰 |
| `sources` | 출처 정보 |
| `done` | 완료 |
| `error` | 에러 |

## 주요 엔드포인트 목록

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/v1/auth/login` | 로그인 |
| GET | `/api/v1/openframe-rag/health` | 헬스체크 |
| GET | `/api/v1/openframe-rag/products` | 제품 목록 |
| POST | `/api/v1/openframe-rag/classify` | 제품 분류 |
| POST | `/api/v1/openframe-rag/stream` | RAG 스트리밍 |
| POST | `/api/v1/openframe-rag/deep-seek/stream` | DeepSeek |
| POST | `/api/v1/agents/stream` | 일반 Agent |
