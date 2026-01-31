"""
Configuration Service

Unified configuration management service that centralizes all configuration
classes and provides environment variable loading, runtime override, and
convenient accessor functions.

Usage:
    from app.api.services.configuration_service import (
        get_configuration_service,
        get_timeout_config,
        get_model_registry,
        get_path_config,
        get_vector_config,
    )

    # Full service access
    config_service = get_configuration_service()
    timeout = config_service.timeout.llm_default

    # Convenience functions
    timeout = get_timeout_config().llm_default
    model = get_model_registry().llm.text_model_name
    path = get_path_config().get_uploads_path()
    top_k = get_vector_config().default_top_k
"""

import os
import logging
from typing import Optional, TypeVar, Type, Dict, Any
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

    Configuration Priority (low to high):
    1. Pydantic defaults
    2. Environment variables
    3. Runtime override

    Attributes:
        timeout: TimeoutConfig instance
        models: ModelRegistry instance
        paths: PathConfig instance
        vector: VectorSearchConfig instance
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
        """
        Initialize configuration service.

        Args:
            db_pool: Database connection pool (for future DB-based config)
            cache: Cache instance (for future caching)
            timeout_config: Pre-configured TimeoutConfig (optional)
            model_registry: Pre-configured ModelRegistry (optional)
            path_config: Pre-configured PathConfig (optional)
            vector_config: Pre-configured VectorSearchConfig (optional)
        """
        self._db_pool = db_pool
        self._cache = cache

        # Load configs from environment if not provided
        self._timeout = timeout_config or self._load_from_env(TimeoutConfig)
        self._models = model_registry or self._load_model_registry_from_env()
        self._paths = path_config or self._load_from_env(PathConfig)
        self._vector = vector_config or self._load_from_env(VectorSearchConfig)

        logger.info("ConfigurationService initialized")

    def _load_from_env(self, config_class: Type[T]) -> T:
        """
        환경변수에서 설정 로드.

        Pydantic 모델의 json_schema_extra에 정의된 env_var를 사용하여
        환경변수에서 값을 읽어옵니다.

        Args:
            config_class: Pydantic BaseModel 클래스

        Returns:
            설정 인스턴스
        """
        env_values: Dict[str, Any] = {}

        for field_name, field_info in config_class.model_fields.items():
            extra = field_info.json_schema_extra or {}
            env_var = extra.get('env_var')

            if env_var and env_var in os.environ:
                raw_value = os.environ[env_var]

                # Type conversion based on annotation
                annotation = field_info.annotation
                try:
                    if annotation == float:
                        env_values[field_name] = float(raw_value)
                    elif annotation == int:
                        env_values[field_name] = int(raw_value)
                    elif annotation == bool:
                        env_values[field_name] = raw_value.lower() in ('true', '1', 'yes')
                    else:
                        env_values[field_name] = raw_value
                except ValueError as e:
                    logger.warning(
                        f"Failed to parse env var {env_var}={raw_value}: {e}. "
                        f"Using default value for {field_name}."
                    )

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

    def update_timeout(self, updates: Dict[str, Any]) -> TimeoutConfig:
        """
        런타임 타임아웃 업데이트.

        Args:
            updates: 업데이트할 필드와 값

        Returns:
            업데이트된 TimeoutConfig
        """
        current = self._timeout.model_dump()
        current.update(updates)
        self._timeout = TimeoutConfig(**current)
        logger.info(f"Timeout config updated: {list(updates.keys())}")
        return self._timeout

    def update_models(self, updates: Dict[str, Any]) -> ModelRegistry:
        """
        런타임 모델 설정 업데이트.

        Args:
            updates: 업데이트할 필드와 값 (llm.*, embedding.*)

        Returns:
            업데이트된 ModelRegistry
        """
        current = self._models.model_dump()

        for key, value in updates.items():
            if '.' in key:
                # Handle nested updates like 'llm.text_model_name'
                parts = key.split('.')
                target = current
                for part in parts[:-1]:
                    target = target[part]
                target[parts[-1]] = value
            else:
                current[key] = value

        self._models = ModelRegistry(**current)
        logger.info(f"Model config updated: {list(updates.keys())}")
        return self._models

    def update_paths(self, updates: Dict[str, Any]) -> PathConfig:
        """런타임 경로 설정 업데이트"""
        current = self._paths.model_dump()
        current.update(updates)
        self._paths = PathConfig(**current)
        logger.info(f"Path config updated: {list(updates.keys())}")
        return self._paths

    def update_vector(self, updates: Dict[str, Any]) -> VectorSearchConfig:
        """런타임 벡터 검색 설정 업데이트"""
        current = self._vector.model_dump()
        current.update(updates)
        self._vector = VectorSearchConfig(**current)
        logger.info(f"Vector config updated: {list(updates.keys())}")
        return self._vector

    def reload_from_env(self) -> None:
        """
        환경변수에서 전체 재로드.

        모든 설정을 환경변수에서 다시 읽어옵니다.
        런타임 오버라이드는 무시됩니다.
        """
        self._timeout = self._load_from_env(TimeoutConfig)
        self._models = self._load_model_registry_from_env()
        self._paths = self._load_from_env(PathConfig)
        self._vector = self._load_from_env(VectorSearchConfig)
        logger.info("Configuration reloaded from environment")

    def get_all_warnings(self) -> Dict[str, list]:
        """
        모든 설정의 경고 메시지 수집.

        Returns:
            카테고리별 경고 메시지 딕셔너리
        """
        warnings = {}

        # Vector config warnings
        vector_warnings = self._vector.get_warnings()
        if vector_warnings:
            warnings['vector'] = vector_warnings

        return warnings

    def to_dict(self) -> Dict[str, Any]:
        """모든 설정을 딕셔너리로 반환"""
        return {
            'timeout': self._timeout.model_dump(),
            'models': self._models.model_dump(),
            'paths': self._paths.model_dump(),
            'vector': self._vector.model_dump(),
        }


# Singleton instance
_configuration_service: Optional[ConfigurationService] = None


def get_configuration_service(
    db_pool=None,
    cache=None,
    force_reload: bool = False
) -> ConfigurationService:
    """
    Get or create the configuration service singleton.

    Args:
        db_pool: Database connection pool (optional)
        cache: Cache instance (optional)
        force_reload: If True, recreate the service

    Returns:
        ConfigurationService singleton instance
    """
    global _configuration_service

    if _configuration_service is None or force_reload:
        _configuration_service = ConfigurationService(db_pool, cache)

    return _configuration_service


def reset_configuration_service() -> None:
    """
    Reset the configuration service singleton.

    주로 테스트에서 사용됩니다.
    """
    global _configuration_service
    _configuration_service = None
    # Clear lru_cache as well
    get_configuration_service.cache_clear() if hasattr(get_configuration_service, 'cache_clear') else None


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════════

def get_timeout_config() -> TimeoutConfig:
    """
    Get timeout configuration.

    Usage:
        timeout = get_timeout_config().llm_default
    """
    return get_configuration_service().timeout


def get_model_registry() -> ModelRegistry:
    """
    Get model registry.

    Usage:
        model = get_model_registry().llm.text_model_name
        dimension = get_model_registry().get_dimension_for_model("nvidia/nv-embedqa-mistral-7b-v2")
    """
    return get_configuration_service().models


def get_path_config() -> PathConfig:
    """
    Get path configuration.

    Usage:
        uploads = get_path_config().get_uploads_path()
    """
    return get_configuration_service().paths


def get_vector_config() -> VectorSearchConfig:
    """
    Get vector search configuration.

    Usage:
        top_k = get_vector_config().default_top_k
    """
    return get_configuration_service().vector


# ═══════════════════════════════════════════════════════════════════════════════
# Quick Access Functions (for common use cases)
# ═══════════════════════════════════════════════════════════════════════════════

def get_llm_timeout() -> float:
    """Get default LLM timeout in seconds"""
    return get_timeout_config().llm_default


def get_embedding_timeout() -> float:
    """Get embedding timeout in seconds"""
    return get_timeout_config().embedding


def get_vision_timeout() -> float:
    """Get vision LLM timeout in seconds"""
    return get_timeout_config().vision


def get_http_timeout() -> float:
    """Get default HTTP timeout in seconds"""
    return get_timeout_config().http_default


def get_text_model_name() -> str:
    """Get text LLM model name"""
    return get_model_registry().llm.text_model_name


def get_text_model_url() -> str:
    """Get text LLM API URL"""
    return get_model_registry().llm.text_model_url


def get_vision_model_name() -> str:
    """Get vision LLM model name"""
    return get_model_registry().llm.vision_model_name


def get_vision_model_url() -> str:
    """Get vision LLM API URL"""
    return get_model_registry().llm.vision_model_url


def get_embedding_model_name() -> str:
    """Get embedding model name"""
    return get_model_registry().embedding.model_name


def get_embedding_dimension() -> int:
    """Get embedding dimension"""
    return get_model_registry().embedding.dimension


def get_default_top_k() -> int:
    """Get default top_k for vector search"""
    return get_vector_config().default_top_k


def get_min_similarity() -> float:
    """Get minimum similarity threshold"""
    return get_vector_config().min_similarity
