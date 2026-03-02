"""
Vector Search Configuration Model

Centralized vector search and indexing settings.
Environment variable prefix: VECTOR_

Usage:
    from app.api.services.configuration_service import get_vector_config
    config = get_vector_config()
    top_k = config.default_top_k
    min_sim = config.min_similarity
"""

from pydantic import BaseModel, Field


class VectorSearchConfig(BaseModel):
    """
    벡터 검색 설정.

    검색 결과 수, 유사도 임계값, 청킹 설정,
    HNSW 인덱스 파라미터 등을 관리합니다.
    """

    # ─────────────────────────────────────────────────────────────────
    # Result Limits
    # ─────────────────────────────────────────────────────────────────
    default_top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Default number of search results",
        json_schema_extra={
            "env_var": "VECTOR_DEFAULT_TOP_K",
            "effect": "Number of results returned by default",
            "category": "results"
        }
    )
    max_top_k: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum allowed search results",
        json_schema_extra={
            "env_var": "VECTOR_MAX_TOP_K",
            "effect": "Upper limit for user-requested top_k",
            "category": "results"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Similarity Thresholds
    # ─────────────────────────────────────────────────────────────────
    min_similarity: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score for results",
        json_schema_extra={
            "env_var": "VECTOR_MIN_SIMILARITY",
            "effect": "Results below this threshold are filtered out",
            "trade_off": "Too high = fewer results, too low = noisy results",
            "category": "thresholds"
        }
    )
    high_similarity: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="High similarity threshold for boost",
        json_schema_extra={
            "env_var": "VECTOR_HIGH_SIMILARITY",
            "effect": "Results above this get priority boost",
            "category": "thresholds"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Chunking Settings
    # ─────────────────────────────────────────────────────────────────
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=4000,
        description="Default chunk size for text splitting",
        json_schema_extra={
            "env_var": "VECTOR_CHUNK_SIZE",
            "effect": "Smaller chunks = more precise, larger = more context",
            "trade_off": "Balance between precision and context",
            "category": "chunking"
        }
    )
    chunk_overlap: int = Field(
        default=100,
        ge=0,
        le=500,
        description="Overlap between chunks",
        json_schema_extra={
            "env_var": "VECTOR_CHUNK_OVERLAP",
            "effect": "Overlap helps maintain context across chunk boundaries",
            "category": "chunking"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # HNSW Index Settings
    # ─────────────────────────────────────────────────────────────────
    index_ef_construction: int = Field(
        default=128,
        ge=16,
        le=512,
        description="HNSW index ef_construction parameter",
        json_schema_extra={
            "env_var": "VECTOR_EF_CONSTRUCTION",
            "effect": "Higher = better index quality, slower build",
            "trade_off": "Index build time vs search quality",
            "category": "index"
        }
    )
    index_ef_search: int = Field(
        default=64,
        ge=16,
        le=256,
        description="HNSW index ef_search parameter",
        json_schema_extra={
            "env_var": "VECTOR_EF_SEARCH",
            "effect": "Higher = better recall, slower search",
            "trade_off": "Search speed vs accuracy",
            "category": "index"
        }
    )
    index_m: int = Field(
        default=16,
        ge=4,
        le=64,
        description="HNSW index M parameter",
        json_schema_extra={
            "env_var": "VECTOR_INDEX_M",
            "effect": "Number of connections per node",
            "trade_off": "Memory usage vs search quality",
            "category": "index"
        }
    )

    def validate_chunk_settings(self) -> bool:
        """청킹 설정 유효성 검증"""
        if self.chunk_overlap >= self.chunk_size:
            return False
        return True

    def validate_similarity_thresholds(self) -> bool:
        """유사도 임계값 유효성 검증"""
        if self.min_similarity >= self.high_similarity:
            return False
        return True

    def get_warnings(self) -> list[str]:
        """설정 경고 메시지 반환"""
        warnings = []

        if not self.validate_chunk_settings():
            warnings.append(
                f"chunk_overlap ({self.chunk_overlap}) should be less than "
                f"chunk_size ({self.chunk_size})"
            )

        if not self.validate_similarity_thresholds():
            warnings.append(
                f"min_similarity ({self.min_similarity}) should be less than "
                f"high_similarity ({self.high_similarity})"
            )

        if self.min_similarity > 0.5:
            warnings.append(
                f"High min_similarity ({self.min_similarity}) may filter too many results"
            )

        if self.index_ef_search > self.index_ef_construction:
            warnings.append(
                "ef_search should typically be <= ef_construction for optimal performance"
            )

        return warnings

    model_config = {
        "json_schema_extra": {
            "description": "Vector search and indexing configuration"
        }
    }
