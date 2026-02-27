# PDCA Report: Hardcoding Externalization

> **Feature**: hardcoding-externalization
> **Report Date**: 2026-01-31
> **Status**: ✅ Phase 1-2 Complete, Phase 3-4 Pending
> **Match Rate**: 98%
> **Design Version**: v1.0

---

## 1. Executive Summary

### 1.1 개요

하드코딩된 설정값(타임아웃, 모델명, 경로, 벡터검색 파라미터)을 중앙화된 Pydantic Config 모델로 외부화하여 유지보수성과 배포 유연성을 향상시켰습니다.

### 1.2 핵심 성과

| 지표 | 목표 | 달성 | 상태 |
|------|------|------|------|
| Config 모델 구현 | 4개 | 4개 | ✅ 완료 |
| 설정 필드 정의 | 46개 | 46개 | ✅ 완료 |
| 환경변수 문서화 | 42개 | 42개 | ✅ 완료 |
| Design Match Rate | ≥90% | 98% | ✅ PASS |
| Service Migration | 4개 파일 | 0개 | ⏳ Phase 3 대기 |

---

## 2. Plan Summary

### 2.1 문제 정의

기존 코드베이스에서 80개 이상의 하드코딩된 값이 발견됨:
- **Timeout Values**: 20개 (LLM, Embedding, Vision, HTTP 등)
- **Model Names/URLs**: 15개 (Text LLM, Code LLM, Vision, Embedding)
- **File Paths**: 10개 (uploads, summaries, models 등)
- **Vector Search**: 10개 (top_k, similarity thresholds, chunk settings)
- **Scoring Weights**: 10개+ (이미 외부화됨)
- **Magic Numbers**: 15개+ (retry counts, buffer sizes 등)

### 2.2 설계 원칙

1. **점진적 마이그레이션**: 기존 코드 변경 최소화
2. **하위 호환성**: 환경변수 없으면 기본값 사용
3. **패턴 일관성**: 기존 `ScoringConfigService` 패턴 재사용
4. **테스트 가능성**: 설정 주입으로 단위 테스트 용이

---

## 3. Design Summary

### 3.1 아키텍처

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Application Code                               │
├─────────────────────────────────────────────────────────────────────┤
│                     Configuration Layer                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐│
│  │TimeoutConfig │ │ ModelConfig  │ │ PathConfig   │ │VectorSearch ││
│  │ (12 fields)  │ │ (17 fields)  │ │ (8 fields)   │ │ (9 fields)  ││
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘│
│  ┌──────────────────────────────────────────────────────────────────┐│
│  │                    ConfigurationService                          ││
│  │  - Environment variable loading                                  ││
│  │  - Runtime override support                                      ││
│  │  - Singleton pattern                                             ││
│  └──────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────┤
│                     Data Sources (Priority Order)                    │
│  1. Runtime Override → 2. Environment Variables → 3. Pydantic Default│
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Config 모델 설계

| 모델 | 필드 수 | 환경변수 접두사 | 역할 |
|------|--------|----------------|------|
| TimeoutConfig | 12 | `TIMEOUT_` | 서비스별 타임아웃 설정 |
| LLMModelConfig | 12 | `MODEL_` | Text/Code/Vision LLM 설정 |
| EmbeddingModelConfig | 5 | `EMBEDDING_` | 임베딩 모델 설정 |
| PathConfig | 8 | `PATH_`, `KMS_DATA_ROOT` | 파일 시스템 경로 |
| VectorSearchConfig | 9 | `VECTOR_` | 검색 파라미터 설정 |

---

## 4. Implementation Summary

### 4.1 생성된 파일

| 파일 | 라인 수 | 역할 |
|------|--------|------|
| `app/api/models/timeout_config.py` | ~120 | 타임아웃 설정 모델 |
| `app/api/models/model_config.py` | ~170 | LLM/Embedding 모델 설정 |
| `app/api/models/path_config.py` | ~160 | 경로 설정 모델 |
| `app/api/models/vector_search_config.py` | ~190 | 벡터 검색 설정 |
| `app/api/services/configuration_service.py` | ~406 | 통합 설정 서비스 |
| `.env.example` (업데이트) | +60 | 환경변수 템플릿 |

### 4.2 구현된 기능

#### TimeoutConfig (12 fields)
- `llm_default`, `llm_streaming` - LLM 타임아웃
- `embedding`, `embedding_batch` - 임베딩 타임아웃
- `vision`, `vision_batch` - Vision LLM 타임아웃
- `http_default`, `http_upload` - HTTP 타임아웃
- `circuit_breaker_reset`, `circuit_breaker_half_open` - Circuit Breaker
- `cli_default`, `document_processing` - CLI/문서 처리

#### ModelRegistry (17 fields)
- Text LLM: `text_model_name`, `text_model_url`, `text_temperature`, `text_max_tokens`
- Code LLM: `code_model_name`, `code_model_url`, `code_temperature`, `code_max_tokens`
- Vision LLM: `vision_model_name`, `vision_model_url`, `vision_provider`, `vision_max_tokens`
- Embedding: `model_name`, `model_url`, `dimension`, `batch_size`, `max_text_length`
- Utility: `get_dimension_for_model()` - 모델별 dimension 자동 조회

#### PathConfig (8 fields)
- `data_root` - KMS 루트 디렉토리
- `uploads_dir`, `summaries_dir` - 스토리지 경로
- `models_dir`, `qlora_adapters_dir` - 모델 경로
- `training_data_dir`, `logs_dir`, `temp_dir` - 기타 경로
- Utility: `get_absolute_path()`, `ensure_directories()`

#### VectorSearchConfig (9 fields)
- `default_top_k`, `max_top_k` - 결과 수 제한
- `min_similarity`, `high_similarity` - 유사도 임계값
- `chunk_size`, `chunk_overlap` - 청킹 설정
- `index_ef_construction`, `index_ef_search`, `index_m` - HNSW 인덱스
- Validation: `validate_chunk_settings()`, `get_warnings()`

#### ConfigurationService
- 싱글톤 패턴으로 중앙 설정 관리
- 환경변수 자동 로딩 (`_load_from_env`)
- 런타임 오버라이드 (`update_timeout`, `update_models`, `update_paths`, `update_vector`)
- 편의 함수 12개 (`get_llm_timeout`, `get_text_model_name`, etc.)

### 4.3 환경변수 (42개)

```bash
# Timeout (12)
TIMEOUT_LLM_DEFAULT, TIMEOUT_LLM_STREAMING, TIMEOUT_EMBEDDING,
TIMEOUT_EMBEDDING_BATCH, TIMEOUT_VISION, TIMEOUT_VISION_BATCH,
TIMEOUT_HTTP_DEFAULT, TIMEOUT_HTTP_UPLOAD, TIMEOUT_CIRCUIT_BREAKER_RESET,
TIMEOUT_CIRCUIT_BREAKER_HALF_OPEN, TIMEOUT_CLI_DEFAULT, TIMEOUT_DOCUMENT_PROCESSING

# Model (13)
MODEL_TEXT_NAME, MODEL_TEXT_URL, MODEL_TEXT_TEMPERATURE, MODEL_TEXT_MAX_TOKENS,
MODEL_CODE_NAME, MODEL_CODE_URL, MODEL_CODE_TEMPERATURE, MODEL_CODE_MAX_TOKENS,
MODEL_VISION_NAME, MODEL_VISION_URL, MODEL_VISION_PROVIDER, MODEL_VISION_MAX_TOKENS,
EMBEDDING_MODEL_NAME, EMBEDDING_URL, EMBEDDING_DIMENSION,
EMBEDDING_BATCH_SIZE, EMBEDDING_MAX_TEXT_LENGTH

# Path (8)
KMS_DATA_ROOT, PATH_UPLOADS, PATH_SUMMARIES, PATH_MODELS,
PATH_QLORA_ADAPTERS, PATH_TRAINING_DATA, PATH_LOGS, PATH_TEMP

# Vector (9)
VECTOR_DEFAULT_TOP_K, VECTOR_MAX_TOP_K, VECTOR_MIN_SIMILARITY,
VECTOR_HIGH_SIMILARITY, VECTOR_CHUNK_SIZE, VECTOR_CHUNK_OVERLAP,
VECTOR_EF_CONSTRUCTION, VECTOR_EF_SEARCH, VECTOR_INDEX_M
```

---

## 5. Gap Analysis Results

### 5.1 카테고리별 점수

| Category | Score | Status |
|----------|:-----:|:------:|
| TimeoutConfig Model | 100% | ✅ PASS |
| ModelConfig Model | 100% | ✅ PASS |
| PathConfig Model | 100% | ✅ PASS |
| VectorSearchConfig Model | 100% | ✅ PASS |
| ConfigurationService | 95% | ✅ PASS |
| .env.example Coverage | 100% | ✅ PASS |

### 5.2 Design 초과 구현

Design에 명시되지 않았지만 추가 구현된 유용한 기능들:

| Feature | Location | Description |
|---------|----------|-------------|
| Quick Access Functions | configuration_service.py | 12개 편의 함수 |
| `update_models()` | ConfigurationService | 런타임 모델 설정 업데이트 |
| `update_paths()` | ConfigurationService | 런타임 경로 설정 업데이트 |
| `update_vector()` | ConfigurationService | 런타임 벡터 설정 업데이트 |
| `reset_configuration_service()` | configuration_service.py | 테스트용 리셋 함수 |
| `to_dict()` | ConfigurationService | 전체 설정 딕셔너리 반환 |
| `get_all_warnings()` | ConfigurationService | 설정 검증 경고 수집 |
| `get_*_path()` methods | PathConfig | 경로 편의 메서드 4개 |
| Validation methods | VectorSearchConfig | 설정 유효성 검증 |
| Extended dimension map | ModelRegistry | 더 많은 임베딩 모델 지원 |
| `force_reload` param | get_configuration_service() | 서비스 강제 재생성 |

### 5.3 Minor Gaps (수용 가능)

| Item | Design | Implementation | Impact |
|------|--------|----------------|--------|
| Singleton pattern | `@lru_cache` | Manual singleton + `force_reload` | Low |
| `_dimension_map` type | Instance `Dict` | `ClassVar[Dict]` | Low (더 나은 패턴) |

---

## 6. Phase Status

| Phase | Description | Status | Progress |
|-------|-------------|--------|----------|
| Phase 1 | Security (`.env.example`, `.gitignore`) | ✅ Complete | 100% |
| Phase 2 | Config Models Implementation | ✅ Complete | 100% |
| Phase 3 | Service Migration | ⏳ Pending | 0% |
| Phase 4 | Testing | ⏳ Pending | 0% |

### 6.1 Phase 3 남은 작업

점진적 마이그레이션으로 기존 서비스에서 새 Config 모델을 사용하도록 전환:

| 파일 | 현재 하드코딩 | 대상 Config | 우선순위 |
|------|-------------|-------------|----------|
| `circuit_breaker.py` | `30`, `60` 타임아웃 | `TimeoutConfig.circuit_breaker_*` | P1 |
| `cli/config.py` | `36000` 타임아웃 | `TimeoutConfig.cli_default` | P2 |
| `vision_llm_factory.py` | 모델명 하드코딩 | `ModelRegistry.llm.vision_*` | P1 |
| `vector_search.py` | `0.3` similarity | `VectorSearchConfig.min_similarity` | P2 |

### 6.2 Phase 4 테스트 계획

```python
# 단위 테스트 (우선)
tests/unit/test_timeout_config.py
tests/unit/test_model_config.py
tests/unit/test_path_config.py
tests/unit/test_vector_search_config.py
tests/unit/test_configuration_service.py

# 통합 테스트
tests/integration/test_config_integration.py
```

---

## 7. Usage Guide

### 7.1 기본 사용법

```python
from app.api.services.configuration_service import (
    get_configuration_service,
    get_timeout_config,
    get_model_registry,
    get_path_config,
    get_vector_config,
)

# 전체 서비스 접근
config = get_configuration_service()
timeout = config.timeout.llm_default
model = config.models.llm.text_model_name

# 편의 함수 사용
timeout = get_timeout_config().llm_default
model = get_model_registry().llm.text_model_name
path = get_path_config().get_uploads_path()
top_k = get_vector_config().default_top_k
```

### 7.2 Quick Access 함수

```python
from app.api.services.configuration_service import (
    get_llm_timeout,        # LLM 기본 타임아웃
    get_embedding_timeout,  # 임베딩 타임아웃
    get_vision_timeout,     # Vision LLM 타임아웃
    get_http_timeout,       # HTTP 타임아웃
    get_text_model_name,    # Text LLM 모델명
    get_text_model_url,     # Text LLM URL
    get_vision_model_name,  # Vision LLM 모델명
    get_embedding_model_name,  # 임베딩 모델명
    get_embedding_dimension,   # 임베딩 차원
    get_default_top_k,      # 기본 top_k
    get_min_similarity,     # 최소 유사도
)
```

### 7.3 런타임 오버라이드

```python
config = get_configuration_service()

# 타임아웃 업데이트
config.update_timeout({"llm_default": 180.0})

# 모델 설정 업데이트
config.update_models({"llm.text_temperature": 0.5})

# 환경변수에서 전체 재로드
config.reload_from_env()
```

---

## 8. Key Deliverables

| 항목 | 수량 | 설명 |
|------|------|------|
| Config 모델 | 5개 | TimeoutConfig, LLMModelConfig, EmbeddingModelConfig, PathConfig, VectorSearchConfig |
| 설정 필드 | 46개 | 모든 하드코딩 대상 외부화 |
| 환경변수 | 42개 | .env.example에 문서화 |
| 편의 함수 | 16개 | ConfigurationService + Quick Access |
| 검증 메서드 | 4개 | VectorSearchConfig 유효성 검사 |

---

## 9. Recommendations

### 9.1 즉시 조치 사항

1. **`.gitignore` 확인**: `.env` 파일이 버전 관리에서 제외되는지 확인
2. **기존 `.env.local` 검토**: 커밋된 시크릿이 있으면 히스토리에서 제거

### 9.2 Phase 3 마이그레이션 권장 순서

1. `circuit_breaker.py` - 타임아웃 외부화 (가장 자주 조정 필요)
2. `vision_llm_factory.py` - 모델명 외부화 (배포 환경별 차이)
3. `vector_search.py` - 검색 파라미터 외부화
4. `cli/config.py` - CLI 타임아웃 외부화

### 9.3 향후 개선 방향

- **DB 기반 설정**: PostgreSQL에서 설정 로드 기능 추가
- **설정 UI**: Admin 페이지에서 런타임 설정 변경 UI
- **설정 히스토리**: 설정 변경 이력 추적

---

## 10. Conclusion

**Match Rate: 98% ✅ PASS**

Phase 1-2가 성공적으로 완료되었으며, Design 문서를 충실히 구현하였습니다.

**핵심 성과**:
- ✅ 4개 Config 모델 모두 Design과 일치
- ✅ ConfigurationService 핵심 기능 모두 구현
- ✅ 42개 환경변수 모두 `.env.example`에 문서화
- ✅ Design 초과 구현 (12개 편의 함수, 추가 유틸리티 메서드)

**다음 단계**:
- Phase 3: 기존 서비스 마이그레이션 (점진적 진행)
- Phase 4: 단위 테스트 및 통합 테스트 작성

---

**Generated by**: PDCA Report Generator
**Report Version**: v1.0
**Last Updated**: 2026-01-31
