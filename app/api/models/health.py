"""
Health check Pydantic models
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status types"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


class ServiceHealth(BaseModel):
    """Individual service health"""
    status: HealthStatus
    response_time_ms: Optional[int] = None
    error: Optional[str] = None
    gpu: Optional[str] = None
    uptime_seconds: Optional[int] = None


class ServicesHealth(BaseModel):
    """All services health status

    Active GPU Allocation:
    - GPU 4-7: multi_lora_dpo (Qwen2.5-72B + 15 DPO adapters, 4x A100-40GB, port 12810)
    - GPU 5: embedding (NeMo Embedding, port 12801)

    Disabled:
    - qwen_llm (port 12800) - ENABLE_QWEN_LLM=false
    - codeqwen (port 12802) - not deployed
    - vision_llm (port 12803) - not deployed
    """
    api: ServiceHealth
    neo4j: ServiceHealth
    multi_lora_dpo: ServiceHealth
    embedding: ServiceHealth
    qwen_llm: Optional[ServiceHealth] = None
    codeqwen: Optional[ServiceHealth] = None
    vision_llm: Optional[ServiceHealth] = None


class PreloadStatus(BaseModel):
    """PDF knowledge store preload progress"""
    total: int = Field(description="Total products to preload")
    loaded: int = Field(description="Products loaded so far")
    current_product: str = Field(default="", description="Currently loading product")
    is_running: bool = Field(description="Whether preloading is in progress")
    is_done: bool = Field(description="Whether preloading completed")
    elapsed_seconds: float = Field(description="Time elapsed in seconds")
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: HealthStatus
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    services: ServicesHealth
    preload: Optional[PreloadStatus] = None
