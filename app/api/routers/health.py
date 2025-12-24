"""
Health API Router
시스템 상태 확인 API (인증 불필요)
"""
import time
from datetime import datetime
from fastapi import APIRouter, Response

from ..models.health import (
    HealthResponse,
    HealthStatus,
    ServiceHealth,
    ServicesHealth,
)
from ..core.config import api_settings

router = APIRouter(prefix="/health", tags=["Health"])

# Track server start time
_server_start_time = time.time()


async def check_neo4j_health() -> ServiceHealth:
    """Check Neo4j database health"""
    try:
        # TODO: Implement actual Neo4j health check
        # from ..services.database import check_neo4j_connection
        # response_time, is_healthy = await check_neo4j_connection()
        return ServiceHealth(
            status=HealthStatus.HEALTHY,
            response_time_ms=15
        )
    except Exception as e:
        return ServiceHealth(
            status=HealthStatus.UNHEALTHY,
            error=str(e)
        )


async def check_llm_health() -> ServiceHealth:
    """Check Nemotron LLM health"""
    try:
        # TODO: Implement actual LLM health check
        return ServiceHealth(
            status=HealthStatus.HEALTHY,
            response_time_ms=120,
            gpu="GPU 7"
        )
    except Exception as e:
        return ServiceHealth(
            status=HealthStatus.UNHEALTHY,
            error=str(e)
        )


async def check_embedding_health() -> ServiceHealth:
    """Check embedding service health"""
    try:
        # TODO: Implement actual embedding health check
        return ServiceHealth(
            status=HealthStatus.HEALTHY,
            response_time_ms=85,
            gpu="GPU 4,5"
        )
    except Exception as e:
        return ServiceHealth(
            status=HealthStatus.UNHEALTHY,
            error=str(e)
        )


async def check_mistral_health() -> ServiceHealth:
    """Check Mistral Code LLM health"""
    try:
        # TODO: Implement actual Mistral health check
        return ServiceHealth(
            status=HealthStatus.HEALTHY,
            response_time_ms=95,
            gpu="GPU 0"
        )
    except Exception as e:
        return ServiceHealth(
            status=HealthStatus.UNHEALTHY,
            error=str(e)
        )


@router.get(
    "",
    response_model=HealthResponse,
    summary="시스템 상태 조회",
    description="전체 시스템 및 개별 서비스 상태를 조회합니다."
)
async def health_check(response: Response):
    """Comprehensive health check for all services"""
    uptime = int(time.time() - _server_start_time)

    # Check all services
    neo4j = await check_neo4j_health()
    llm = await check_llm_health()
    embedding = await check_embedding_health()
    mistral = await check_mistral_health()

    services = ServicesHealth(
        api=ServiceHealth(
            status=HealthStatus.HEALTHY,
            uptime_seconds=uptime
        ),
        neo4j=neo4j,
        nemotron_llm=llm,
        embedding=embedding,
        mistral_code=mistral
    )

    # Determine overall status
    all_services = [neo4j, llm, embedding, mistral]
    unhealthy_count = sum(1 for s in all_services if s.status == HealthStatus.UNHEALTHY)

    if unhealthy_count == 0:
        overall_status = HealthStatus.HEALTHY
    elif unhealthy_count < len(all_services):
        overall_status = HealthStatus.DEGRADED
        response.status_code = 503
    else:
        overall_status = HealthStatus.UNHEALTHY
        response.status_code = 503

    return HealthResponse(
        status=overall_status,
        version=api_settings.APP_VERSION,
        timestamp=datetime.utcnow(),
        services=services
    )


@router.get(
    "/ready",
    summary="Readiness 체크",
    description="서비스 준비 상태를 확인합니다 (Kubernetes Readiness Probe용)."
)
async def readiness_check(response: Response):
    """Kubernetes readiness probe"""
    # Check critical services only
    neo4j = await check_neo4j_health()
    llm = await check_llm_health()

    if neo4j.status == HealthStatus.HEALTHY and llm.status == HealthStatus.HEALTHY:
        return {"status": "ready"}
    else:
        response.status_code = 503
        return {"status": "not ready"}


@router.get(
    "/live",
    summary="Liveness 체크",
    description="서비스 생존 상태를 확인합니다 (Kubernetes Liveness Probe용)."
)
async def liveness_check():
    """Kubernetes liveness probe"""
    return {"status": "alive"}
