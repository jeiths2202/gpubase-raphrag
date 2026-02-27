"""
Health API Router
시스템 상태 확인 API (인증 불필요)
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Response, Depends

from ..models.health import (
    HealthResponse,
    HealthStatus,
    ServiceHealth,
    ServicesHealth,
    PreloadStatus,
)
from ..core.preload_state import get_preload_state
from ..core.config import api_settings
from ..core.deps import get_health_service

router = APIRouter(prefix="/health", tags=["Health"])


def _convert_health_result(result: dict) -> ServiceHealth:
    """Convert health check result to ServiceHealth model"""
    raw_status = result.get("status", "unhealthy")
    if raw_status == "healthy":
        status = HealthStatus.HEALTHY
    elif raw_status == "disabled":
        status = HealthStatus.UNHEALTHY  # disabled → unhealthy for display
    else:
        status = HealthStatus.UNHEALTHY
    return ServiceHealth(
        status=status,
        response_time_ms=result.get("response_time_ms"),
        gpu=result.get("gpu"),
        error=result.get("error") or result.get("reason")
    )


@router.get(
    "",
    response_model=HealthResponse,
    summary="시스템 상태 조회",
    description="전체 시스템 및 개별 서비스 상태를 조회합니다."
)
async def health_check(
    response: Response,
    health_service = Depends(get_health_service)
):
    """Comprehensive health check for all services"""
    # Check all services using real health service
    result = await health_service.check_all()

    services_data = result.get("services", {})

    # Convert API service health
    api_data = services_data.get("api", {})
    api_health = ServiceHealth(
        status=HealthStatus.HEALTHY,
        uptime_seconds=api_data.get("uptime_seconds", 0)
    )

    # Convert other service health results
    neo4j = _convert_health_result(services_data.get("neo4j", {}))
    multi_lora_dpo = _convert_health_result(services_data.get("multi_lora_dpo", {}))
    embedding = _convert_health_result(services_data.get("embedding", {}))

    # Optional disabled services
    qwen_llm_data = services_data.get("qwen_llm")
    codeqwen_data = services_data.get("code_llm") or services_data.get("codeqwen")
    vision_llm_data = services_data.get("vision_llm")

    services = ServicesHealth(
        api=api_health,
        neo4j=neo4j,
        multi_lora_dpo=multi_lora_dpo,
        embedding=embedding,
        qwen_llm=_convert_health_result(qwen_llm_data) if qwen_llm_data else None,
        codeqwen=_convert_health_result(codeqwen_data) if codeqwen_data else None,
        vision_llm=_convert_health_result(vision_llm_data) if vision_llm_data else None,
    )

    # Determine overall status from result
    overall = result.get("status", "unhealthy")
    if overall == "healthy":
        overall_status = HealthStatus.HEALTHY
    elif overall == "degraded":
        overall_status = HealthStatus.DEGRADED
        response.status_code = 503
    else:
        overall_status = HealthStatus.UNHEALTHY
        response.status_code = 503

    # PDF preload progress
    preload_state = get_preload_state()
    preload = PreloadStatus(**preload_state.to_dict()) if preload_state.started_at else None

    return HealthResponse(
        status=overall_status,
        version=api_settings.APP_VERSION,
        timestamp=datetime.now(timezone.utc),
        services=services,
        preload=preload,
    )


@router.get(
    "/ready",
    summary="Readiness 체크",
    description="서비스 준비 상태를 확인합니다 (Kubernetes Readiness Probe용)."
)
async def readiness_check(
    response: Response,
    health_service = Depends(get_health_service)
):
    """Kubernetes readiness probe"""
    # Check critical services: Neo4j + active LLM (Multi-LoRA DPO)
    neo4j = await health_service.check_neo4j()
    llm = await health_service.check_learning_llm()

    if neo4j.get("status") == "healthy" and llm.get("status") == "healthy":
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
