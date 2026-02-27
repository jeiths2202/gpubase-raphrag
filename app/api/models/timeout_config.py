"""
Timeout Configuration Model

Centralized timeout settings for all services.
Environment variable prefix: TIMEOUT_

Usage:
    from app.api.services.configuration_service import get_timeout_config
    config = get_timeout_config()
    timeout = config.llm_default
"""

from pydantic import BaseModel, Field


class TimeoutConfig(BaseModel):
    """
    서비스별 타임아웃 설정.

    모든 값은 초(seconds) 단위입니다.
    환경변수로 오버라이드 가능하며, 기본값이 제공됩니다.
    """

    # ─────────────────────────────────────────────────────────────────
    # LLM Timeouts
    # ─────────────────────────────────────────────────────────────────
    llm_default: float = Field(
        default=120.0,
        ge=1.0,
        le=600.0,
        description="Default LLM request timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_LLM_DEFAULT",
            "effect": "Longer timeout allows slower models to complete",
            "trade_off": "Too long may cause poor UX on failures",
            "category": "llm"
        }
    )
    llm_streaming: float = Field(
        default=180.0,
        ge=1.0,
        le=600.0,
        description="LLM streaming request timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_LLM_STREAMING",
            "category": "llm"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Embedding Timeouts
    # ─────────────────────────────────────────────────────────────────
    embedding: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="Embedding API timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_EMBEDDING",
            "category": "embedding"
        }
    )
    embedding_batch: float = Field(
        default=120.0,
        ge=1.0,
        le=600.0,
        description="Batch embedding timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_EMBEDDING_BATCH",
            "category": "embedding"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Vision LLM Timeouts
    # ─────────────────────────────────────────────────────────────────
    vision: float = Field(
        default=180.0,
        ge=1.0,
        le=600.0,
        description="Vision LLM timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_VISION",
            "effect": "Vision models process images which takes longer",
            "category": "vision"
        }
    )
    vision_batch: float = Field(
        default=300.0,
        ge=1.0,
        le=900.0,
        description="Batch vision processing timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_VISION_BATCH",
            "category": "vision"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # HTTP/General Timeouts
    # ─────────────────────────────────────────────────────────────────
    http_default: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Default HTTP request timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_HTTP_DEFAULT",
            "category": "http"
        }
    )
    http_upload: float = Field(
        default=300.0,
        ge=1.0,
        le=600.0,
        description="File upload timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_HTTP_UPLOAD",
            "effect": "Large file uploads need more time",
            "category": "http"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # Circuit Breaker Timeouts
    # ─────────────────────────────────────────────────────────────────
    circuit_breaker_reset: float = Field(
        default=30.0,
        ge=5.0,
        le=300.0,
        description="Circuit breaker reset timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_CIRCUIT_BREAKER_RESET",
            "effect": "Time to wait before attempting recovery",
            "category": "circuit_breaker"
        }
    )
    circuit_breaker_half_open: float = Field(
        default=60.0,
        ge=10.0,
        le=300.0,
        description="Circuit breaker half-open timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_CIRCUIT_BREAKER_HALF_OPEN",
            "effect": "Time in half-open state before full recovery",
            "category": "circuit_breaker"
        }
    )

    # ─────────────────────────────────────────────────────────────────
    # CLI/Long-running Operation Timeouts
    # ─────────────────────────────────────────────────────────────────
    cli_default: float = Field(
        default=3600.0,  # 1 hour
        ge=60.0,
        le=36000.0,
        description="CLI operation timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_CLI_DEFAULT",
            "effect": "CLI tools may run long batch operations",
            "category": "cli"
        }
    )
    document_processing: float = Field(
        default=600.0,  # 10 minutes
        ge=60.0,
        le=3600.0,
        description="Document processing timeout (seconds)",
        json_schema_extra={
            "env_var": "TIMEOUT_DOCUMENT_PROCESSING",
            "effect": "Large PDF processing can take time",
            "category": "cli"
        }
    )

    model_config = {
        "json_schema_extra": {
            "description": "Centralized timeout configuration for all services"
        }
    }
