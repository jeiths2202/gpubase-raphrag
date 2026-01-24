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

    GPU Allocation:
    - GPU 4: qwen_llm (Qwen2.5-7B-Instruct)
    - GPU 5: embedding (NeMo Embedding)
    - GPU 6: vision_llm (LLaMA-3.1-Nemotron-Nano-VL)
    - GPU 7: codeqwen (Qwen2.5-Coder-3B) + learning_llm (Qwen2.5-7B-AWQ)
    """
    api: ServiceHealth
    neo4j: ServiceHealth
    qwen_llm: ServiceHealth
    embedding: ServiceHealth
    codeqwen: ServiceHealth
    vision_llm: ServiceHealth
    learning_llm: ServiceHealth


class HealthResponse(BaseModel):
    """Health check response"""
    status: HealthStatus
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    services: ServicesHealth
