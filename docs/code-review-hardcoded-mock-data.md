# 하드코딩 및 Mock 데이터 코드 리뷰 결과

**리뷰 일자**: 2026-01-14
**리뷰 범위**: 전체 소스코드 (Backend + Frontend)

## 1. 보안 관련 하드코딩 (주의 필요)

### 1.1 고정 관리자 계정

**위치**: `app/api/services/auth_service.py:24-26`

```python
FIXED_ADMIN_ID = "admin"
FIXED_ADMIN_PASSWORD = "SecureAdm1nP@ss2024!"
FIXED_ADMIN_EMAIL = "admin@example.com"
```

| 항목 | 내용 |
|------|------|
| 상태 | 의도적 설계 (시스템 요구사항) |
| 위험도 | 중간 |
| 권고 | 프로덕션 배포 시 환경변수 `ADMIN_INITIAL_PASSWORD` 사용 권장 |

### 1.2 API Key 플레이스홀더

여러 파일에서 `api_key="not-needed"` 사용:

| 파일 | 용도 |
|------|------|
| `app/api/services/vector_rag.py` | Vector RAG 서비스 |
| `app/api/services/hybrid_rag.py` | Hybrid RAG 서비스 |
| `app/api/services/graphrag.py` | Graph RAG 서비스 |
| `app/api/services/query_router.py` | 쿼리 라우터 |
| `app/api/services/batch_upload.py` | 배치 업로드 |
| `app/api/services/mindmap_service.py` | 마인드맵 서비스 |

| 항목 | 내용 |
|------|------|
| 상태 | 로컬 LLM 사용 시 API 키 불필요하므로 의도적 |
| 위험도 | 낮음 (외부 API 호출이 아닌 내부 NIM 컨테이너용) |

## 2. 개발용 기본값 (localhost URLs)

환경변수 폴백으로 localhost 사용 - 정상적인 개발 패턴:

| 환경변수 | 기본값 |
|----------|--------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `NEO4J_URI` | `bolt://localhost:7687` |
| `POSTGRES_HOST` | `localhost` |
| `NEMOTRON_BASE_URL` | `http://localhost:12800` |
| `EMBEDDING_BASE_URL` | `http://localhost:12801` |
| `MISTRAL_CODE_BASE_URL` | `http://localhost:12802` |

| 항목 | 내용 |
|------|------|
| 상태 | 정상 (환경변수로 오버라이드 가능) |
| 위험도 | 낮음 |
| 권고 | 프로덕션 `.env` 파일에서 적절히 설정 |

## 3. 프론트엔드 Mock 데이터 (테스트용)

### 3.1 MSW (Mock Service Worker) 핸들러

**위치**: `kms-portal-ui/src/mocks/handlers/`

| 파일 | Mock 데이터 | 용도 |
|------|-------------|------|
| `auth.ts` | MOCK_USERS, MOCK_TOKENS | 인증 테스트 |
| `ims.ts` | MOCK_JOBS, MOCK_STATS, MOCK_LOGS | IMS 페이지 테스트 |
| `chat.ts` | MOCK_RESPONSES, MOCK_SOURCES | 채팅 기능 테스트 |
| `knowledge.ts` | MOCK_ARTICLES, MOCK_CATEGORIES | 지식베이스 테스트 |

| 항목 | 내용 |
|------|------|
| 상태 | 테스트 전용 (프로덕션 빌드에 포함 안 됨) |
| 위험도 | 없음 |

### 3.2 페이지 내 Mock 데이터

| 파일 | 내용 |
|------|------|
| `AIStudioPage.tsx` | 샘플 프롬프트 템플릿 |
| `HomePage.tsx` | 대시보드 통계 예시 |
| `FAQPage.tsx` | FAQ 데이터 |
| `SettingsPage.tsx` | 설정 옵션 |

| 항목 | 내용 |
|------|------|
| 상태 | UI 렌더링용 초기 데이터 |
| 위험도 | 낮음 |
| 권고 | 실제 API 연동 확인 필요 |

## 4. 기타 발견 사항

### 4.1 마이그레이션 스크립트 기본값

**위치**: `scripts/migration/*.sh`

```bash
PG_PASSWORD="${POSTGRES_PASSWORD:-ragpassword}"
```

| 항목 | 내용 |
|------|------|
| 상태 | 폴백 값으로 적절 |
| 위험도 | 낮음 |
| 권고 | 프로덕션 배포 전 반드시 변경 |

## 5. 요약

| 분류 | 개수 | 위험도 | 조치 필요 |
|------|------|--------|-----------|
| 고정 관리자 계정 | 1곳 | 중간 | 환경변수 사용 권장 |
| API Key 플레이스홀더 | 6곳 | 낮음 | 의도적 설계 |
| localhost 기본값 | 다수 | 낮음 | 환경변수로 오버라이드 |
| 테스트 Mock 데이터 | 4파일 | 없음 | 테스트 전용 |
| 페이지 Mock 데이터 | 4파일 | 낮음 | API 연동 확인 |

## 6. 결론

심각한 보안 문제는 없습니다. 발견된 하드코딩은 대부분 의도적 설계이거나 테스트 목적입니다.

### 프로덕션 배포 체크리스트

- [ ] `.env` 파일에서 `ADMIN_INITIAL_PASSWORD` 설정
- [ ] `.env` 파일에서 `JWT_SECRET_KEY` 새로 생성
- [ ] `.env` 파일에서 `ENCRYPTION_MASTER_KEY` 새로 생성
- [ ] `.env` 파일에서 `ENCRYPTION_SALT` 새로 생성
- [ ] `.env` 파일에서 `NEO4J_PASSWORD` 설정
- [ ] `.env` 파일에서 `POSTGRES_PASSWORD` 설정
- [ ] 모든 localhost URL을 실제 서비스 URL로 변경
