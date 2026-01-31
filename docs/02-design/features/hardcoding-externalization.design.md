# PDCA Design: Hardcoding Externalization

> **Feature**: hardcoding-externalization
> **Created**: 2026-01-31
> **Status**: Design Phase
> **Based on**: [Plan Document](../../01-plan/features/hardcoding-externalization.plan.md)
> **Design Version**: v1.0

---

## 1. Design Overview

### 1.1 설계 목표

기존 `ScoringConfigService` 및 `APISettings` 패턴을 확장하여 하드코딩된 값들을 체계적으로 외부화합니다.

### 1.2 설계 원칙

1. **점진적 마이그레이션**: 기존 코드 변경 최소화
2. **하위 호환성**: 환경변수 없으면 기본값 사용
3. **패턴 일관성**: 기존 `ScoringConfigService` 패턴 재사용
4. **테스트 가능성**: 설정 주입으로 단위 테스트 용이

---

## 2. Architecture Design

### 2.1 설정 계층 구조

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Application Code                               │
├─────────────────────────────────────────────────────────────────────┤
│                     Configuration Layer                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐│
│  │ APISettings  │ │TimeoutConfig │ │ ModelConfig  │ │ PathConfig  ││
│  │ (Existing)   │ │ (New)        │ │ (New)        │ │ (New)       ││
│  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘│
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────────┐│
│  │ScoringConfig │ │ HybridConfig │ │ VectorSearchConfig (New)    ││
│  │ (Existing)   │ │ (Existing)   │ │                              ││
│  └──────────────┘ └──────────────┘ └──────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────┤
│                     Data Sources (Priority Order)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐ │
│  │ 1. Runtime  │  │ 2. Database │  │ 3. Environment Variables    │ │
│  │    Override │  │    (Postgres)│  │    (.env files)            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────────┘ │
│                                    ┌─────────────────────────────┐ │
│                                    │ 4. Pydantic Defaults        │ │
│                                    │    (Code fallback)          │ │
│                                    └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 신규 Config 클래스 설계

#### 2.2.1 TimeoutConfig

```python
# app/api/models/timeout_config.py

from pydantic import BaseModel, Field
from typing import Optional

class TimeoutConfig(BaseModel):
    """
    서비스별 타임아웃 설정.

    환경변수 접두사: TIMEOUT_
    """

    # LLM 관련
    llm_default: float = Field(
        default=120.0,
        ge=1.0, le=600.0,
        description="Default LLM request timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_LLM_DEFAULT",
            "effect": "Longer timeout allows slower models to complete",
            "trade_off": "Too long may cause poor UX on failures"
        }
    )
    llm_streaming: float = Field(
        default=180.0,
        ge=1.0, le=600.0,
        description="LLM streaming request timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_LLM_STREAMING"}
    )

    # Embedding
    embedding: float = Field(
        default=60.0,
        ge=1.0, le=300.0,
        description="Embedding API timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_EMBEDDING"}
    )
    embedding_batch: float = Field(
        default=120.0,
        ge=1.0, le=600.0,
        description="Batch embedding timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_EMBEDDING_BATCH"}
    )

    # Vision
    vision: float = Field(
        default=180.0,
        ge=1.0, le=600.0,
        description="Vision LLM timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_VISION"}
    )
    vision_batch: float = Field(
        default=300.0,
        ge=1.0, le=900.0,
        description="Batch vision processing timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_VISION_BATCH"}
    )

    # HTTP/General
    http_default: float = Field(
        default=30.0,
        ge=1.0, le=120.0,
        description="Default HTTP request timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_HTTP_DEFAULT"}
    )
    http_upload: float = Field(
        default=300.0,
        ge=1.0, le=600.0,
        description="File upload timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_HTTP_UPLOAD"}
    )

    # Circuit Breaker
    circuit_breaker_reset: float = Field(
        default=30.0,
        ge=5.0, le=300.0,
        description="Circuit breaker reset timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_CIRCUIT_BREAKER_RESET"}
    )
    circuit_breaker_half_open: float = Field(
        default=60.0,
        ge=10.0, le=300.0,
        description="Circuit breaker half-open timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_CIRCUIT_BREAKER_HALF_OPEN"}
    )

    # CLI/Long-running
    cli_default: float = Field(
        default=3600.0,  # 1 hour
        ge=60.0, le=36000.0,
        description="CLI operation timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_CLI_DEFAULT"}
    )
    document_processing: float = Field(
        default=600.0,  # 10 minutes
        ge=60.0, le=3600.0,
        description="Document processing timeout (seconds)",
        json_schema_extra={"env_var": "TIMEOUT_DOCUMENT_PROCESSING"}
    )
```

#### 2.2.2 ModelConfig

```python
# app/api/models/model_config.py

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class LLMModelConfig(BaseModel):
    """
    LLM 모델 설정.

    환경변수 접두사: MODEL_
    """

    # Text LLM
    text_model_name: str = Field(
        default="Qwen/Qwen2.5-7B-Instruct",
        description="Text generation LLM model name",
        json_schema_extra={"env_var": "MODEL_TEXT_NAME"}
    )
    text_model_url: str = Field(
        default="http://localhost:12800/v1",
        description="Text LLM API base URL",
        json_schema_extra={"env_var": "MODEL_TEXT_URL"}
    )
    text_temperature: float = Field(
        default=0.7,
        ge=0.0, le=2.0,
        description="Text LLM default temperature",
        json_schema_extra={"env_var": "MODEL_TEXT_TEMPERATURE"}
    )
    text_max_tokens: int = Field(
        default=2048,
        ge=100, le=16384,
        description="Text LLM max output tokens",
        json_schema_extra={"env_var": "MODEL_TEXT_MAX_TOKENS"}
    )

    # Code LLM
    code_model_name: str = Field(
        default="mistralai/Mistral-Nemo-Instruct-2407",
        description="Code generation LLM model name",
        json_schema_extra={"env_var": "MODEL_CODE_NAME"}
    )
    code_model_url: str = Field(
        default="http://localhost:12802/v1",
        description="Code LLM API base URL",
        json_schema_extra={"env_var": "MODEL_CODE_URL"}
    )
    code_temperature: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Code LLM temperature (lower for determinism)",
        json_schema_extra={"env_var": "MODEL_CODE_TEMPERATURE"}
    )
    code_max_tokens: int = Field(
        default=4096,
        ge=100, le=16384,
        description="Code LLM max output tokens",
        json_schema_extra={"env_var": "MODEL_CODE_MAX_TOKENS"}
    )

    # Vision LLM
    vision_model_name: str = Field(
        default="openbmb/MiniCPM-V-2_6",
        description="Vision LLM model name",
        json_schema_extra={"env_var": "MODEL_VISION_NAME"}
    )
    vision_model_url: str = Field(
        default="http://localhost:12803/v1",
        description="Vision LLM API base URL",
        json_schema_extra={"env_var": "MODEL_VISION_URL"}
    )
    vision_provider: str = Field(
        default="minicpm",
        description="Vision LLM provider (minicpm, openai, anthropic)",
        json_schema_extra={"env_var": "MODEL_VISION_PROVIDER"}
    )
    vision_max_tokens: int = Field(
        default=2048,
        ge=100, le=8192,
        description="Vision LLM max output tokens",
        json_schema_extra={"env_var": "MODEL_VISION_MAX_TOKENS"}
    )


class EmbeddingModelConfig(BaseModel):
    """
    임베딩 모델 설정.
    """

    model_name: str = Field(
        default="nvidia/nv-embedqa-mistral-7b-v2",
        description="Embedding model name",
        json_schema_extra={"env_var": "EMBEDDING_MODEL_NAME"}
    )
    model_url: str = Field(
        default="http://localhost:12801/v1",
        description="Embedding API base URL",
        json_schema_extra={"env_var": "EMBEDDING_URL"}
    )
    dimension: int = Field(
        default=4096,
        ge=128, le=8192,
        description="Embedding vector dimension",
        json_schema_extra={"env_var": "EMBEDDING_DIMENSION"}
    )
    batch_size: int = Field(
        default=32,
        ge=1, le=128,
        description="Batch size for embedding operations",
        json_schema_extra={"env_var": "EMBEDDING_BATCH_SIZE"}
    )
    max_text_length: int = Field(
        default=8192,
        ge=512, le=32768,
        description="Maximum input text length",
        json_schema_extra={"env_var": "EMBEDDING_MAX_TEXT_LENGTH"}
    )


class ModelRegistry(BaseModel):
    """
    전체 모델 레지스트리.

    모든 모델 설정을 통합 관리.
    """

    llm: LLMModelConfig = Field(default_factory=LLMModelConfig)
    embedding: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)

    # Model-specific dimension mappings (read-only reference)
    _dimension_map: Dict[str, int] = {
        "nvidia/nv-embedqa-mistral-7b-v2": 4096,
        "sentence-transformers/all-MiniLM-L6-v2": 384,
        "openai/text-embedding-ada-002": 1536,
        "openai/text-embedding-3-small": 1536,
        "openai/text-embedding-3-large": 3072,
    }

    def get_dimension_for_model(self, model_name: str) -> int:
        """모델명으로 dimension 자동 조회"""
        return self._dimension_map.get(model_name, self.embedding.dimension)
```

#### 2.2.3 PathConfig

```python
# app/api/models/path_config.py

from pydantic import BaseModel, Field
from pathlib import Path

class PathConfig(BaseModel):
    """
    파일 시스템 경로 설정.

    환경변수 접두사: PATH_
    """

    # Root directories
    data_root: str = Field(
        default="/opt/kms",
        description="KMS data root directory",
        json_schema_extra={"env_var": "KMS_DATA_ROOT"}
    )

    # Relative paths (auto-joined with data_root)
    uploads_dir: str = Field(
        default="uploads",
        description="Upload storage directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_UPLOADS"}
    )
    summaries_dir: str = Field(
        default="uploads/summaries",
        description="Summary files directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_SUMMARIES"}
    )
    models_dir: str = Field(
        default="models",
        description="ML models directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_MODELS"}
    )
    qlora_adapters_dir: str = Field(
        default="models/qlora_adapters",
        description="QLoRA adapters directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_QLORA_ADAPTERS"}
    )
    training_data_dir: str = Field(
        default="data/training",
        description="Training data directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_TRAINING_DATA"}
    )
    logs_dir: str = Field(
        default="logs",
        description="Log files directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_LOGS"}
    )
    temp_dir: str = Field(
        default="temp",
        description="Temporary files directory (relative to data_root)",
        json_schema_extra={"env_var": "PATH_TEMP"}
    )

    def get_absolute_path(self, relative_attr: str) -> Path:
        """상대 경로를 절대 경로로 변환"""
        relative = getattr(self, relative_attr)
        return Path(self.data_root) / relative

    def ensure_directories(self) -> None:
        """필요한 디렉토리 자동 생성"""
        dirs = [
            'uploads_dir', 'summaries_dir', 'models_dir',
            'qlora_adapters_dir', 'training_data_dir', 'logs_dir', 'temp_dir'
        ]
        for dir_attr in dirs:
            path = self.get_absolute_path(dir_attr)
            path.mkdir(parents=True, exist_ok=True)
```

#### 2.2.4 VectorSearchConfig

```python
# app/api/models/vector_search_config.py

from pydantic import BaseModel, Field

class VectorSearchConfig(BaseModel):
    """
    벡터 검색 설정.

    환경변수 접두사: VECTOR_
    """

    # Result limits
    default_top_k: int = Field(
        default=5,
        ge=1, le=100,
        description="Default number of search results",
        json_schema_extra={"env_var": "VECTOR_DEFAULT_TOP_K"}
    )
    max_top_k: int = Field(
        default=20,
        ge=1, le=200,
        description="Maximum allowed search results",
        json_schema_extra={"env_var": "VECTOR_MAX_TOP_K"}
    )

    # Similarity thresholds
    min_similarity: float = Field(
        default=0.3,
        ge=0.0, le=1.0,
        description="Minimum similarity score for results",
        json_schema_extra={"env_var": "VECTOR_MIN_SIMILARITY"}
    )
    high_similarity: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="High similarity threshold for boost",
        json_schema_extra={"env_var": "VECTOR_HIGH_SIMILARITY"}
    )

    # Chunking
    chunk_size: int = Field(
        default=500,
        ge=100, le=4000,
        description="Default chunk size for text splitting",
        json_schema_extra={"env_var": "VECTOR_CHUNK_SIZE"}
    )
    chunk_overlap: int = Field(
        default=100,
        ge=0, le=500,
        description="Overlap between chunks",
        json_schema_extra={"env_var": "VECTOR_CHUNK_OVERLAP"}
    )

    # Index settings
    index_ef_construction: int = Field(
        default=128,
        ge=16, le=512,
        description="HNSW index ef_construction parameter",
        json_schema_extra={"env_var": "VECTOR_EF_CONSTRUCTION"}
    )
    index_ef_search: int = Field(
        default=64,
        ge=16, le=256,
        description="HNSW index ef_search parameter",
        json_schema_extra={"env_var": "VECTOR_EF_SEARCH"}
    )
    index_m: int = Field(
        default=16,
        ge=4, le=64,
        description="HNSW index M parameter",
        json_schema_extra={"env_var": "VECTOR_INDEX_M"}
    )
```

---

## 3. Service Layer Design

### 3.1 ConfigurationService (통합 서비스)

```python
# app/api/services/configuration_service.py

import os
import logging
from typing import Optional, TypeVar, Type
from pydantic import BaseModel
from functools import lru_cache

from ..models.timeout_config import TimeoutConfig
from ..models.model_config import ModelRegistry, LLMModelConfig, EmbeddingModelConfig
from ..models.path_config import PathConfig
from ..models.vector_search_config import VectorSearchConfig

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


class ConfigurationService:
    """
    통합 설정 서비스.

    모든 설정 클래스를 중앙에서 관리하고,
    환경변수 로딩 및 런타임 오버라이드를 제공합니다.

    사용법:
        config_service = get_configuration_service()
        timeout = config_service.timeout.llm_default
        model = config_service.models.llm.text_model_name
    """

    def __init__(
        self,
        db_pool=None,
        cache=None,
        timeout_config: Optional[TimeoutConfig] = None,
        model_registry: Optional[ModelRegistry] = None,
        path_config: Optional[PathConfig] = None,
        vector_config: Optional[VectorSearchConfig] = None,
    ):
        self._db_pool = db_pool
        self._cache = cache

        # Load configs from environment if not provided
        self._timeout = timeout_config or self._load_from_env(TimeoutConfig)
        self._models = model_registry or self._load_model_registry_from_env()
        self._paths = path_config or self._load_from_env(PathConfig)
        self._vector = vector_config or self._load_from_env(VectorSearchConfig)

        logger.info("ConfigurationService initialized")

    def _load_from_env(self, config_class: Type[T]) -> T:
        """환경변수에서 설정 로드"""
        env_values = {}

        for field_name, field_info in config_class.model_fields.items():
            extra = field_info.json_schema_extra or {}
            env_var = extra.get('env_var')

            if env_var and env_var in os.environ:
                raw_value = os.environ[env_var]

                # Type conversion based on annotation
                annotation = field_info.annotation
                if annotation == float:
                    env_values[field_name] = float(raw_value)
                elif annotation == int:
                    env_values[field_name] = int(raw_value)
                elif annotation == bool:
                    env_values[field_name] = raw_value.lower() in ('true', '1', 'yes')
                else:
                    env_values[field_name] = raw_value

        return config_class(**env_values)

    def _load_model_registry_from_env(self) -> ModelRegistry:
        """모델 레지스트리 환경변수 로드"""
        llm = self._load_from_env(LLMModelConfig)
        embedding = self._load_from_env(EmbeddingModelConfig)
        return ModelRegistry(llm=llm, embedding=embedding)

    @property
    def timeout(self) -> TimeoutConfig:
        """타임아웃 설정"""
        return self._timeout

    @property
    def models(self) -> ModelRegistry:
        """모델 레지스트리"""
        return self._models

    @property
    def paths(self) -> PathConfig:
        """경로 설정"""
        return self._paths

    @property
    def vector(self) -> VectorSearchConfig:
        """벡터 검색 설정"""
        return self._vector

    def update_timeout(self, updates: dict) -> TimeoutConfig:
        """런타임 타임아웃 업데이트"""
        current = self._timeout.model_dump()
        current.update(updates)
        self._timeout = TimeoutConfig(**current)
        logger.info(f"Timeout config updated: {list(updates.keys())}")
        return self._timeout

    def reload_from_env(self) -> None:
        """환경변수에서 전체 재로드"""
        self._timeout = self._load_from_env(TimeoutConfig)
        self._models = self._load_model_registry_from_env()
        self._paths = self._load_from_env(PathConfig)
        self._vector = self._load_from_env(VectorSearchConfig)
        logger.info("Configuration reloaded from environment")


# Singleton instance
_configuration_service: Optional[ConfigurationService] = None


@lru_cache(maxsize=1)
def get_configuration_service() -> ConfigurationService:
    """Get or create the configuration service singleton."""
    global _configuration_service

    if _configuration_service is None:
        _configuration_service = ConfigurationService()

    return _configuration_service


# Convenience functions
def get_timeout_config() -> TimeoutConfig:
    """Get timeout configuration."""
    return get_configuration_service().timeout


def get_model_registry() -> ModelRegistry:
    """Get model registry."""
    return get_configuration_service().models


def get_path_config() -> PathConfig:
    """Get path configuration."""
    return get_configuration_service().paths


def get_vector_config() -> VectorSearchConfig:
    """Get vector search configuration."""
    return get_configuration_service().vector
```

---

## 4. Migration Mapping

### 4.1 파일별 마이그레이션 체크리스트

| 파일 | 현재 하드코딩 | 대상 Config | 환경변수 |
|------|-------------|------------|---------|
| `cli/config.py:16` | `36000` (timeout) | `TimeoutConfig.cli_default` | `TIMEOUT_CLI_DEFAULT` |
| `cli/auth.py:*` | `30`, `60`, `120` | `TimeoutConfig.http_default` | `TIMEOUT_HTTP_DEFAULT` |
| `circuit_breaker.py:*` | `30`, `60` | `TimeoutConfig.circuit_breaker_*` | `TIMEOUT_CIRCUIT_BREAKER_*` |
| `vision_llm_factory.py:43` | `openbmb/MiniCPM-V-2_6` | `ModelRegistry.llm.vision_model_name` | `MODEL_VISION_NAME` |
| `app/src/config.py:15` | `Qwen/Qwen2.5-7B-Instruct` | `ModelRegistry.llm.text_model_name` | `MODEL_TEXT_NAME` |
| `vector_search.py:80` | `0.3` | `VectorSearchConfig.min_similarity` | `VECTOR_MIN_SIMILARITY` |

### 4.2 코드 변경 예시

#### Before (하드코딩)

```python
# cli/config.py
class CLIConfig:
    timeout = 36000  # 10 hours hard-coded

# circuit_breaker.py
class CircuitBreaker:
    reset_timeout = 30  # hard-coded

# vision_llm_factory.py
def create_vision_client():
    model = "openbmb/MiniCPM-V-2_6"  # hard-coded
```

#### After (외부화)

```python
# cli/config.py
from app.api.services.configuration_service import get_timeout_config

class CLIConfig:
    @property
    def timeout(self) -> float:
        return get_timeout_config().cli_default

# circuit_breaker.py
from app.api.services.configuration_service import get_timeout_config

class CircuitBreaker:
    @property
    def reset_timeout(self) -> float:
        return get_timeout_config().circuit_breaker_reset

# vision_llm_factory.py
from app.api.services.configuration_service import get_model_registry

def create_vision_client():
    model = get_model_registry().llm.vision_model_name
```

---

## 5. Environment Variables Reference

### 5.1 신규 환경변수 목록

```bash
# ═══════════════════════════════════════════════════════════════════
# Timeout Configuration
# ═══════════════════════════════════════════════════════════════════
TIMEOUT_LLM_DEFAULT=120.0          # LLM 기본 타임아웃 (초)
TIMEOUT_LLM_STREAMING=180.0        # LLM 스트리밍 타임아웃 (초)
TIMEOUT_EMBEDDING=60.0             # 임베딩 API 타임아웃 (초)
TIMEOUT_EMBEDDING_BATCH=120.0      # 배치 임베딩 타임아웃 (초)
TIMEOUT_VISION=180.0               # Vision LLM 타임아웃 (초)
TIMEOUT_VISION_BATCH=300.0         # 배치 Vision 타임아웃 (초)
TIMEOUT_HTTP_DEFAULT=30.0          # HTTP 기본 타임아웃 (초)
TIMEOUT_HTTP_UPLOAD=300.0          # 파일 업로드 타임아웃 (초)
TIMEOUT_CIRCUIT_BREAKER_RESET=30.0 # Circuit Breaker 리셋 (초)
TIMEOUT_CIRCUIT_BREAKER_HALF_OPEN=60.0
TIMEOUT_CLI_DEFAULT=3600.0         # CLI 작업 타임아웃 (초)
TIMEOUT_DOCUMENT_PROCESSING=600.0  # 문서 처리 타임아웃 (초)

# ═══════════════════════════════════════════════════════════════════
# Model Configuration
# ═══════════════════════════════════════════════════════════════════
MODEL_TEXT_NAME=Qwen/Qwen2.5-7B-Instruct
MODEL_TEXT_URL=http://localhost:12800/v1
MODEL_TEXT_TEMPERATURE=0.7
MODEL_TEXT_MAX_TOKENS=2048

MODEL_CODE_NAME=mistralai/Mistral-Nemo-Instruct-2407
MODEL_CODE_URL=http://localhost:12802/v1
MODEL_CODE_TEMPERATURE=0.3
MODEL_CODE_MAX_TOKENS=4096

MODEL_VISION_NAME=openbmb/MiniCPM-V-2_6
MODEL_VISION_URL=http://localhost:12803/v1
MODEL_VISION_PROVIDER=minicpm
MODEL_VISION_MAX_TOKENS=2048

EMBEDDING_MODEL_NAME=nvidia/nv-embedqa-mistral-7b-v2
EMBEDDING_URL=http://localhost:12801/v1
EMBEDDING_DIMENSION=4096
EMBEDDING_BATCH_SIZE=32
EMBEDDING_MAX_TEXT_LENGTH=8192

# ═══════════════════════════════════════════════════════════════════
# Path Configuration
# ═══════════════════════════════════════════════════════════════════
KMS_DATA_ROOT=/opt/kms
PATH_UPLOADS=uploads
PATH_SUMMARIES=uploads/summaries
PATH_MODELS=models
PATH_QLORA_ADAPTERS=models/qlora_adapters
PATH_TRAINING_DATA=data/training
PATH_LOGS=logs
PATH_TEMP=temp

# ═══════════════════════════════════════════════════════════════════
# Vector Search Configuration
# ═══════════════════════════════════════════════════════════════════
VECTOR_DEFAULT_TOP_K=5
VECTOR_MAX_TOP_K=20
VECTOR_MIN_SIMILARITY=0.3
VECTOR_HIGH_SIMILARITY=0.8
VECTOR_CHUNK_SIZE=500
VECTOR_CHUNK_OVERLAP=100
VECTOR_EF_CONSTRUCTION=128
VECTOR_EF_SEARCH=64
VECTOR_INDEX_M=16
```

### 5.2 .env.example 템플릿

```bash
# ═══════════════════════════════════════════════════════════════════
# KMS Configuration Template
# ═══════════════════════════════════════════════════════════════════
# Copy this file to .env and fill in your values
# NEVER commit .env to version control!
# ═══════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────
# REQUIRED: Security Credentials (NO DEFAULTS)
# ─────────────────────────────────────────────────────────────────
JWT_SECRET_KEY=                    # min 32 chars, generate: openssl rand -base64 32
ENCRYPTION_MASTER_KEY=             # min 32 chars, for OAuth token encryption
ENCRYPTION_SALT=                   # min 16 chars, for key derivation

# Database
POSTGRES_PASSWORD=                 # PostgreSQL password
NEO4J_PASSWORD=                    # Neo4j password

# ─────────────────────────────────────────────────────────────────
# OPTIONAL: OAuth Providers (leave empty if not using)
# ─────────────────────────────────────────────────────────────────
NOTION_CLIENT_ID=
NOTION_CLIENT_SECRET=
GOOGLE_DRIVE_CLIENT_ID=
GOOGLE_DRIVE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
ATLASSIAN_CLIENT_ID=
ATLASSIAN_CLIENT_SECRET=
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=

# ─────────────────────────────────────────────────────────────────
# OPTIONAL: Infrastructure (defaults shown)
# ─────────────────────────────────────────────────────────────────
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# NEO4J_URI=bolt://localhost:7687

# ─────────────────────────────────────────────────────────────────
# OPTIONAL: Model URLs (defaults shown)
# ─────────────────────────────────────────────────────────────────
# MODEL_TEXT_URL=http://localhost:12800/v1
# MODEL_CODE_URL=http://localhost:12802/v1
# MODEL_VISION_URL=http://localhost:12803/v1
# EMBEDDING_URL=http://localhost:12801/v1

# ─────────────────────────────────────────────────────────────────
# OPTIONAL: Timeouts (defaults shown, in seconds)
# ─────────────────────────────────────────────────────────────────
# TIMEOUT_LLM_DEFAULT=120.0
# TIMEOUT_VISION=180.0
# TIMEOUT_EMBEDDING=60.0
```

---

## 6. Implementation Checklist

### Phase 1: 보안 긴급 조치 (P0) - 즉시

- [ ] `.gitignore` 업데이트 (`.env.local`, `.env` 추가)
- [ ] `.env.example` 파일 생성
- [ ] OAuth 자격증명 `.env`로 이동
- [ ] 기존 `.env.local` 커밋에서 시크릿 제거

### Phase 2: Config 모델 구현 (P1) - 1주

- [ ] `app/api/models/timeout_config.py` 생성
- [ ] `app/api/models/model_config.py` 생성
- [ ] `app/api/models/path_config.py` 생성
- [ ] `app/api/models/vector_search_config.py` 생성
- [ ] `app/api/services/configuration_service.py` 생성
- [ ] 단위 테스트 작성

### Phase 3: 서비스 마이그레이션 (P1) - 2주

- [ ] `circuit_breaker.py` 타임아웃 외부화
- [ ] `cli/config.py` 통합
- [ ] `vision_llm_factory.py` 모델명 외부화
- [ ] `vector_search.py` 설정 외부화
- [ ] 기존 하드코딩 값 제거

### Phase 4: 테스트 및 문서화 (P2)

- [ ] 통합 테스트 작성
- [ ] 환경변수 목록 문서화 (README)
- [ ] 마이그레이션 가이드 작성

---

## 7. Testing Strategy

### 7.1 단위 테스트

```python
# tests/unit/test_configuration_service.py

import pytest
import os
from app.api.models.timeout_config import TimeoutConfig
from app.api.services.configuration_service import ConfigurationService

class TestTimeoutConfig:
    def test_default_values(self):
        config = TimeoutConfig()
        assert config.llm_default == 120.0
        assert config.embedding == 60.0
        assert config.vision == 180.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("TIMEOUT_LLM_DEFAULT", "200.0")
        monkeypatch.setenv("TIMEOUT_EMBEDDING", "90.0")

        # Reload config
        service = ConfigurationService()
        assert service.timeout.llm_default == 200.0
        assert service.timeout.embedding == 90.0

    def test_validation_min_max(self):
        with pytest.raises(ValueError):
            TimeoutConfig(llm_default=0.5)  # below ge=1.0

        with pytest.raises(ValueError):
            TimeoutConfig(llm_default=700.0)  # above le=600.0


class TestModelRegistry:
    def test_dimension_lookup(self):
        from app.api.models.model_config import ModelRegistry

        registry = ModelRegistry()
        assert registry.get_dimension_for_model("nvidia/nv-embedqa-mistral-7b-v2") == 4096
        assert registry.get_dimension_for_model("openai/text-embedding-ada-002") == 1536
        assert registry.get_dimension_for_model("unknown/model") == registry.embedding.dimension
```

### 7.2 통합 테스트

```python
# tests/integration/test_config_integration.py

import pytest
from app.api.services.configuration_service import get_configuration_service

@pytest.mark.integration
class TestConfigIntegration:
    def test_service_singleton(self):
        svc1 = get_configuration_service()
        svc2 = get_configuration_service()
        assert svc1 is svc2

    def test_runtime_update(self):
        svc = get_configuration_service()
        original = svc.timeout.llm_default

        svc.update_timeout({"llm_default": 200.0})
        assert svc.timeout.llm_default == 200.0

        # Cleanup
        svc.update_timeout({"llm_default": original})
```

---

## 8. Rollback Plan

### 8.1 문제 발생 시 롤백 절차

1. **환경변수 제거**: 새로 추가한 환경변수 제거
2. **기본값 복원**: Pydantic 기본값으로 자동 폴백
3. **Git Revert**: 필요시 커밋 롤백

### 8.2 호환성 보장

```python
# 기존 코드와 호환성 유지 예시
def get_timeout() -> float:
    """
    기존 함수 시그니처 유지.
    내부적으로 새 ConfigurationService 사용.
    """
    try:
        return get_timeout_config().llm_default
    except Exception:
        return 120.0  # Fallback to original default
```

---

## 9. Success Criteria

| 지표 | 현재 | 목표 | 측정 방법 |
|-----|-----|-----|---------|
| 코드 내 하드코딩 타임아웃 | 20+ | 0 | Grep 검색 |
| 코드 내 하드코딩 모델명 | 10+ | 0 | Grep 검색 |
| 코드 내 하드코딩 경로 | 8+ | 0 | Grep 검색 |
| 환경변수 문서화율 | 0% | 100% | .env.example 커버리지 |
| 설정 변경 시 재시작 필요 | Yes | No | reload_from_env() 테스트 |

---

## 10. Next Steps

1. **Phase 1 실행**: 보안 긴급 조치 (`.gitignore`, `.env.example`)
2. **Phase 2 구현**: Config 모델 파일 생성
3. **Phase 3 마이그레이션**: 서비스 레이어 수정
4. **Gap 분석**: `/pdca analyze hardcoding-externalization`

---

**Created by**: PDCA Design Agent
**Design Version**: v1.0
**Last Updated**: 2026-01-31
