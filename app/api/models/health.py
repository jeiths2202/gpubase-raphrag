"""
Health check Pydantic models
"""
from datetime import datetime
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
    """All services health status"""
    api: ServiceHealth
    neo4j: ServiceHealth
    nemotron_llm: ServiceHealth
    embedding: ServiceHealth
    mistral_code: ServiceHealth


class HealthResponse(BaseModel):
    """Health check response"""
    status: HealthStatus
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: ServicesHealth
