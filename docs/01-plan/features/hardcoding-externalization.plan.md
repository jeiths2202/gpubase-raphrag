# PDCA Plan: Hardcoding Externalization

> **Feature**: hardcoding-externalization
> **Created**: 2026-01-31
> **Status**: Plan Phase
> **Priority**: High (Security & Maintainability)

---

## 1. Executive Summary

KMS 프로젝트 전체에서 발견된 하드코딩 값들을 외부 설정으로 분리하여 유지보수성, 보안성, 환경 간 이식성을 향상시킵니다.

### 발견된 하드코딩 총계

| 카테고리 | 항목 수 | 심각도 |
|---------|--------|-------|
| 보안 자격증명 | 12+ | 🔴 Critical |
| API 엔드포인트/포트 | 15+ | 🟠 High |
| 모델명/컨테이너명 | 10+ | 🟡 Medium |
| 타임아웃/제한값 | 20+ | 🟡 Medium |
| 스코어링 가중치 | 15+ | 🟡 Medium |
| 파일 경로 | 8+ | 🟢 Low |

---

## 2. Problem Statement

### 2.1 현재 문제점

1. **보안 위험**: OAuth 자격증명, JWT 시크릿, DB 패스워드가 `.env.local`에 직접 커밋됨
2. **환경 이식성 부족**: `192.168.8.11`, `localhost` 등 특정 IP가 하드코딩되어 환경 전환 시 수정 필요
3. **유지보수 어려움**: 스코어링 가중치, 타임아웃 값이 코드에 분산되어 튜닝 시 여러 파일 수정 필요
4. **테스트 어려움**: Magic number가 코드에 흩어져 있어 테스트 커버리지 확보 어려움

### 2.2 영향 범위

```
프로젝트 구조:
├── app/api/                 # 백엔드 Python (325 파일)
│   ├── core/config.py       # 일부 외부화됨
│   ├── services/            # 하드코딩 다수 발견
│   └── agents/              # 스코어링 가중치 하드코딩
├── kms-portal-ui/           # 프론트엔드 TypeScript
│   └── src/config/          # constants.ts 존재
├── cli/                     # CLI 도구
├── scripts/                 # 유틸리티 스크립트
└── docker/                  # Docker 설정
```

---

## 3. Detailed Analysis

### 3.1 Category A: 보안 자격증명 (🔴 Critical)

| 파일 | 라인 | 하드코딩 값 | 해결 방안 |
|-----|-----|-----------|---------|
| `.env.local:51` | NEO4J_PASSWORD | `graphrag2024` | 환경변수 + 시크릿 매니저 |
| `.env.local:58` | POSTGRES_PASSWORD | `ragpassword123` | 환경변수 + 시크릿 매니저 |
| `.env.local:39` | JWT_SECRET_KEY | 실제 키 노출 | 환경변수 필수 |
| `.env.local:131-140` | OAUTH 자격증명 | 전체 노출 | 시크릿 매니저 필수 |

**해결 전략**:
1. `.env.example` 파일에 플레이스홀더만 유지
2. `.env.local`은 `.gitignore`에 추가 (현재 누락됨)
3. 프로덕션은 Kubernetes Secrets 또는 HashiCorp Vault 사용

### 3.2 Category B: API 엔드포인트/포트 (🟠 High)

| 서비스 | 현재 하드코딩 | 파일 위치 |
|-------|-------------|---------|
| Text LLM | `http://192.168.8.11:12800` | `.env.local`, `app/src/config.py` |
| Embeddings | `http://192.168.8.11:12801` | `.env.local`, 여러 서비스 |
| Code LLM | `http://192.168.8.11:12802` | `.env.local` |
| Vision LLM | `http://192.168.8.11:12803` | `.env.local` |
| Neo4j | `bolt://192.168.8.11:7687` | `.env.local`, `app/api/core/settings.py` |
| PostgreSQL | `192.168.8.11:5432` | `.env.local` |

**해결 전략**:
1. `app/api/core/config.py`의 `Settings` 클래스에 모든 URL 통합
2. Docker Compose에서 서비스명 기반 DNS 사용 (`llm:12800`)
3. 환경별 `.env` 파일 분리 (`.env.dev`, `.env.prod`, `.env.docker`)

### 3.3 Category C: 모델명 (🟡 Medium)

| 모델 유형 | 하드코딩 값 | 파일 위치 |
|---------|-----------|---------|
| Text LLM | `Qwen/Qwen2.5-7B-Instruct` | `app/src/config.py:15` |
| Code LLM | `mistralai/Mistral-Nemo-Instruct-2407` | `.env.local:77` |
| Vision LLM | `openbmb/MiniCPM-V-2_6` | `app/api/services/vision_llm_factory.py:43` |
| Embedding | `nvidia/nv-embedqa-mistral-7b-v2` | `app/api/core/config.py:138` |

**해결 전략**:
1. `ModelRegistry` 클래스 생성하여 모델 설정 중앙화
2. 환경변수에서 모델명 동적 로드
3. 모델별 설정 (temperature, max_tokens) 함께 관리

### 3.4 Category D: 타임아웃/제한값 (🟡 Medium)

| 설정 | 현재 값 | 파일 위치 | 권장 값 |
|-----|--------|---------|--------|
| CLI 타임아웃 | 36000s (10h) | `cli/config.py:16` | 환경변수화 |
| HTTP 타임아웃 | 30s, 60s, 120s | `cli/auth.py` 여러 곳 | 통일 및 외부화 |
| Circuit Breaker Reset | 30s, 60s | `circuit_breaker.py` | 서비스별 분리 |
| Embedding 타임아웃 | 60s | `scripts/cli_document_processor.py` | 환경변수화 |
| Vision 타임아웃 | 180s | `scripts/cli_document_processor.py` | 환경변수화 |

**해결 전략**:
1. `TimeoutConfig` 데이터클래스 생성
2. 서비스 유형별 기본값 정의 (LLM: 120s, Embedding: 60s, Vision: 180s)
3. 환경변수로 오버라이드 가능하게 설계

### 3.5 Category E: 스코어링 가중치 (🟡 Medium)

| 스코어 유형 | 현재 값 | 파일 위치 |
|-----------|--------|---------|
| BM25 가중치 | 0.3 | `ai-driven-rag/tools/rerank.py:89` |
| Semantic 가중치 | 0.5 | `ai-driven-rag/tools/rerank.py:89` |
| Source Boost | 0.2 | `ai-driven-rag/tools/rerank.py:90` |
| High Confidence | 0.7 | `test_summary_bm25_service.py:32` |
| Medium Confidence | 0.4 | `test_summary_bm25_service.py:33` |
| Entity Confidence | 0.70 | `scripts/graph_db_quality_test.py:86` |

**해결 전략**:
1. `ScoringConfigService` 활용 (이미 구현됨 - Admin Scoring 탭)
2. DB 기반 동적 설정 로드
3. A/B 테스트 지원을 위한 프로파일 시스템

### 3.6 Category F: 벡터/임베딩 파라미터 (🟡 Medium)

| 파라미터 | 현재 값 | 파일 위치 |
|---------|--------|---------|
| Embedding Dimension | 4096 | 여러 파일에 중복 |
| Top-K Results | 5 | `app/src/config.py`, `.env.local` |
| Chunk Size | 350~1000 | 파일마다 다름 |
| Chunk Overlap | 200 | `.env.local` |
| Min Similarity | 0.3 | `vector_search.py:80` |

**해결 전략**:
1. `VectorSearchConfig` 클래스에 통합
2. 모델별 dimension 자동 매핑 (registry 패턴)
3. 환경변수 기반 오버라이드

### 3.7 Category G: 파일 경로 (🟢 Low)

| 경로 | 사용처 |
|-----|-------|
| `/opt/kms/uploads` | 업로드 저장소 |
| `/opt/kms/uploads/summaries` | BM25 요약본 |
| `/opt/kms/models/qlora_adapters` | LoRA 어댑터 |
| `/opt/kms/data/training` | 학습 데이터 |

**해결 전략**:
1. `PathConfig` 클래스에서 기본 경로 정의
2. `KMS_DATA_ROOT` 환경변수로 루트 경로 지정
3. 상대 경로로 하위 디렉토리 자동 생성

---

## 4. Solution Architecture

### 4.1 설정 계층 구조

```
┌─────────────────────────────────────────────────────┐
│                  Application Code                    │
├─────────────────────────────────────────────────────┤
│              Configuration Service                   │
│  ┌───────────┐ ┌───────────┐ ┌───────────────────┐  │
│  │ Settings  │ │ Scoring   │ │ Prompt            │  │
│  │ (Pydantic)│ │ Config    │ │ Config (Already)  │  │
│  └───────────┘ └───────────┘ └───────────────────┘  │
├─────────────────────────────────────────────────────┤
│                  Data Sources                        │
│  ┌─────────┐ ┌───────────┐ ┌─────────────────────┐  │
│  │ .env    │ │ Database  │ │ Secret Manager      │  │
│  │ Files   │ │ (Postgres)│ │ (Vault/K8s Secrets) │  │
│  └─────────┘ └───────────┘ └─────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 4.2 새로운 설정 클래스 구조

```python
# app/api/core/config.py 확장

class TimeoutSettings(BaseSettings):
    llm_timeout: int = 120
    embedding_timeout: int = 60
    vision_timeout: int = 180
    http_default: int = 30

class ModelSettings(BaseSettings):
    text_llm_model: str = "Qwen/Qwen2.5-7B-Instruct"
    code_llm_model: str = "mistralai/Mistral-Nemo-Instruct-2407"
    vision_llm_model: str = "openbmb/MiniCPM-V-2_6"
    embedding_model: str = "nvidia/nv-embedqa-mistral-7b-v2"

class VectorSettings(BaseSettings):
    embedding_dimension: int = 4096
    top_k_results: int = 5
    chunk_size: int = 500
    chunk_overlap: int = 100
    min_similarity: float = 0.3

class PathSettings(BaseSettings):
    data_root: str = "/opt/kms"
    uploads_dir: str = "uploads"
    summaries_dir: str = "uploads/summaries"
    models_dir: str = "models"
```

### 4.3 마이그레이션 전략

```
Phase 1: 보안 자격증명 분리 (즉시)
  └─ .gitignore 업데이트
  └─ .env.example 생성
  └─ 기존 .env.local에서 시크릿 제거

Phase 2: 설정 클래스 확장 (1주)
  └─ TimeoutSettings, ModelSettings 등 추가
  └─ 기존 하드코딩 값을 Settings 참조로 변경
  └─ 단위 테스트 추가

Phase 3: DB 기반 동적 설정 (2주)
  └─ ScoringConfigService 패턴 확장
  └─ Admin UI에 설정 관리 탭 추가
  └─ 런타임 변경 지원

Phase 4: 프로덕션 준비 (3주)
  └─ Kubernetes Secrets 연동
  └─ 환경별 설정 분리
  └─ 모니터링 및 알림
```

---

## 5. Task Breakdown

### Phase 1: 보안 긴급 조치 (Priority: P0)

- [ ] `.gitignore`에 `.env.local` 추가
- [ ] `.env.example` 생성 (플레이스홀더만)
- [ ] OAuth 자격증명 분리
- [ ] JWT/암호화 키 환경변수화

### Phase 2: 설정 클래스 통합 (Priority: P1)

- [ ] `TimeoutSettings` 클래스 생성
- [ ] `ModelSettings` 클래스 생성
- [ ] `VectorSettings` 클래스 생성
- [ ] `PathSettings` 클래스 생성
- [ ] 기존 하드코딩 값 마이그레이션

### Phase 3: 서비스 레이어 수정 (Priority: P1)

- [ ] `circuit_breaker.py` 타임아웃 외부화
- [ ] `cli/config.py` 통합
- [ ] `vision_llm_factory.py` 모델명 외부화
- [ ] Reranking 가중치 DB 연동

### Phase 4: 테스트 및 문서화 (Priority: P2)

- [ ] 설정 클래스 단위 테스트
- [ ] 환경변수 목록 문서화
- [ ] 마이그레이션 가이드 작성

---

## 6. Success Metrics

| 지표 | 현재 | 목표 |
|-----|-----|-----|
| 하드코딩된 자격증명 | 12+ | 0 |
| 코드 내 Magic Number | 80+ | <10 |
| 환경변수 문서화 | 없음 | 100% |
| 설정 변경 시 재시작 필요 | Yes | No (동적 로드) |

---

## 7. Risks & Mitigations

| 리스크 | 영향 | 완화 방안 |
|-------|-----|---------|
| 환경변수 누락으로 서비스 시작 실패 | High | 필수값 검증 + 기본값 제공 |
| 설정 변경 후 예상치 못한 동작 | Medium | 변경 로깅 + 롤백 기능 |
| 마이그레이션 중 다운타임 | Low | 점진적 배포 + Feature Flag |

---

## 8. References

- [Python Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [12-Factor App Config](https://12factor.net/config)
- [HashiCorp Vault](https://www.vaultproject.io/)
- 기존 구현: `ScoringConfigService`, `PromptConfigService`

---

## Next Steps

1. **즉시**: Phase 1 보안 조치 실행
2. **이번 주**: Phase 2 설정 클래스 설계 및 구현
3. **다음 주**: Phase 3 서비스 수정 및 테스트
4. **검토**: `/pdca design hardcoding-externalization`으로 상세 설계

