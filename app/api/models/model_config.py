"""
Model Configuration

Centralized LLM and Embedding model settings.
Environment variable prefix: MODEL_, EMBEDDING_

Usage:
    from app.api.services.configuration_service import get_model_registry
    registry = get_model_registry()
    model = registry.llm.text_model_name
    dimension = registry.embedding.dimension
"""

from typing import Dict, ClassVar
from pydantic import BaseModel, Field


class LLMModelConfig(BaseModel):
    """
    LLM 모델 설정.

    Text, Code, Vision LLM 설정을 통합 관리합니다.
    """

    # ─────────────────────────────────────────────────────────────────
    # Text LLM
    # ─────────────────────────────────────────────────────────────────
    text_model_name: str = Field(
        default="Qwen/Qwen2.5-7B-Instruct",
        description="Text generation LLM model name",
        json_schema_extra={
            "env_var": "MODEL_TEXT_NAME",
            "category": "text_llm"
        }
    )
    text_model_url: str = Field(
        default="http://localhost:12800/v1",
        description="Text LLM API base URL",
        json_schema_extra={
            "env_var": "MODEL_TEXT_URL",
            "category": "text_llm"
        }
    )
    text_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Text LLM default temperature",
        json_schema_extra={
            "env_var": "MODEL_TEXT_TEMPERATURE",
            "effect": "Higher = more creative, lower = more deterministic",
            "category": "text_llm"
        }
    )
    text_max_tokens: int = Field(
        default=2048,
        ge=100,
        le=16384,
        description="Text LLM max output tokens",
        json_schema_extra={
            "env_var": "MODEL_TEXT_MAX_TOKENS",
            "category": "text_llm"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Code LLM
    # ─────────────────────────────────────────────────────────────────
    code_model_name: str = Field(
        default="mistralai/Mistral-Nemo-Instruct-2407",
        description="Code generation LLM model name",
        json_schema_extra={
            "env_var": "MODEL_CODE_NAME",
            "category": "code_llm"
        }
    )
    code_model_url: str = Field(
        default="http://localhost:12802/v1",
        description="Code LLM API base URL",
        json_schema_extra={
            "env_var": "MODEL_CODE_URL",
            "category": "code_llm"
        }
    )
    code_temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Code LLM temperature (lower for determinism)",
        json_schema_extra={
            "env_var": "MODEL_CODE_TEMPERATURE",
            "effect": "Lower temperature for more consistent code generation",
            "category": "code_llm"
        }
    )
    code_max_tokens: int = Field(
        default=4096,
        ge=100,
        le=16384,
        description="Code LLM max output tokens",
        json_schema_extra={
            "env_var": "MODEL_CODE_MAX_TOKENS",
            "category": "code_llm"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Vision LLM
    # ─────────────────────────────────────────────────────────────────
    vision_model_name: str = Field(
        default="openbmb/MiniCPM-V-2_6",
        description="Vision LLM model name",
        json_schema_extra={
            "env_var": "MODEL_VISION_NAME",
            "category": "vision_llm"
        }
    )
    vision_model_url: str = Field(
        default="http://localhost:12803/v1",
        description="Vision LLM API base URL",
        json_schema_extra={
            "env_var": "MODEL_VISION_URL",
            "category": "vision_llm"
        }
    )
    vision_provider: str = Field(
        default="minicpm",
        description="Vision LLM provider (minicpm, openai, anthropic)",
        json_schema_extra={
            "env_var": "MODEL_VISION_PROVIDER",
            "effect": "Determines API format and capabilities",
            "category": "vision_llm"
        }
    )
    vision_max_tokens: int = Field(
        default=2048,
        ge=100,
        le=8192,
        description="Vision LLM max output tokens",
        json_schema_extra={
            "env_var": "MODEL_VISION_MAX_TOKENS",
            "category": "vision_llm"
        }
    )


class EmbeddingModelConfig(BaseModel):
    """
    임베딩 모델 설정.

    벡터 임베딩 모델의 URL, 차원, 배치 크기 등을 관리합니다.
    """

    model_name: str = Field(
        default="nvidia/nv-embedqa-mistral-7b-v2",
        description="Embedding model name",
        json_schema_extra={
            "env_var": "EMBEDDING_MODEL_NAME",
            "category": "embedding"
        }
    )
    model_url: str = Field(
        default="http://localhost:12801/v1",
        description="Embedding API base URL",
        json_schema_extra={
            "env_var": "EMBEDDING_URL",
            "category": "embedding"
        }
    )
    dimension: int = Field(
        default=4096,
        ge=128,
        le=8192,
        description="Embedding vector dimension",
        json_schema_extra={
            "env_var": "EMBEDDING_DIMENSION",
            "effect": "Must match the model's output dimension",
            "category": "embedding"
        }
    )
    batch_size: int = Field(
        default=32,
        ge=1,
        le=128,
        description="Batch size for embedding operations",
        json_schema_extra={
            "env_var": "EMBEDDING_BATCH_SIZE",
            "effect": "Larger batches = faster but more memory",
            "category": "embedding"
        }
    )
    max_text_length: int = Field(
        default=8192,
        ge=512,
        le=32768,
        description="Maximum input text length",
        json_schema_extra={
            "env_var": "EMBEDDING_MAX_TEXT_LENGTH",
            "effect": "Text exceeding this will be truncated",
            "category": "embedding"
        }
    )


class ModelRegistry(BaseModel):
    """
    전체 모델 레지스트리.

    모든 모델 설정을 통합 관리하고, 모델명으로 차원을 조회하는
    편의 기능을 제공합니다.

    Usage:
        registry = ModelRegistry()
        dim = registry.get_dimension_for_model("nvidia/nv-embedqa-mistral-7b-v2")
    """

    llm: LLMModelConfig = Field(default_factory=LLMModelConfig)
    embedding: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)

    # Model-specific dimension mappings (class variable, not a field)
    _dimension_map: ClassVar[Dict[str, int]] = {
        # NVIDIA
        "nvidia/nv-embedqa-mistral-7b-v2": 4096,
        "nvidia/nv-embed-v2": 4096,
        # OpenAI
        "openai/text-embedding-ada-002": 1536,
        "openai/text-embedding-3-small": 1536,
        "openai/text-embedding-3-large": 3072,
        # Sentence Transformers
        "sentence-transformers/all-MiniLM-L6-v2": 384,
        "sentence-transformers/all-mpnet-base-v2": 768,
        # Cohere
        "cohere/embed-english-v3.0": 1024,
        "cohere/embed-multilingual-v3.0": 1024,
    }

    def get_dimension_for_model(self, model_name: str) -> int:
        """
        모델명으로 임베딩 차원 조회.

        알려진 모델이면 매핑된 차원을 반환하고,
        알 수 없는 모델이면 현재 설정된 기본 차원을 반환합니다.

        Args:
            model_name: 모델 이름 (예: "nvidia/nv-embedqa-mistral-7b-v2")

        Returns:
            임베딩 벡터 차원
        """
        return self._dimension_map.get(model_name, self.embedding.dimension)

    def get_known_models(self) -> Dict[str, int]:
        """알려진 모델과 차원 목록 반환"""
        return dict(self._dimension_map)

    model_config = {
        "json_schema_extra": {
            "description": "Unified model registry for LLM and embedding models"
        }
    }
