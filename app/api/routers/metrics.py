"""
Metrics Router
Prometheus-compatible metrics endpoint.
"""
from fastapi import APIRouter, Response
from typing import Dict, Any

from ..core.metrics import get_metrics_registry
from ..core.circuit_breaker import get_circuit_breaker_registry
from ..core.cache import get_cache_registry
from ..core.safe_stores import get_session_vector_store, get_user_vector_store

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("")
@router.get("/")
async def get_metrics():
    """
    Get metrics in Prometheus text format.

    This endpoint is designed to be scraped by Prometheus.
    """
    registry = get_metrics_registry()
    prometheus_text = registry.export_prometheus()

    return Response(
        content=prometheus_text,
        media_type="text/plain; charset=utf-8"
    )


@router.get("/json")
async def get_metrics_json() -> Dict[str, Any]:
    """
    Get metrics in JSON format.

    Useful for debugging and non-Prometheus consumers.
    """
    registry = get_metrics_registry()
    return {
        "metrics": registry.collect_all()
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check with component status.

    Returns detailed status of all components.
    """
    circuit_registry = get_circuit_breaker_registry()
    cache_registry = get_cache_registry()

    # Get circuit breaker states
    open_circuits = circuit_registry.get_open_circuits()
    circuit_stats = circuit_registry.get_all_stats()

    # Get cache stats
    cache_stats = cache_registry.get_all_stats()

    # Get store stats
    try:
        session_store_stats = get_session_vector_store().get_stats()
    except Exception:
        session_store_stats = {"error": "not initialized"}

    try:
        user_store_stats = get_user_vector_store().get_stats()
    except Exception:
        user_store_stats = {"error": "not initialized"}

    # Determine overall health
    is_healthy = len(open_circuits) == 0

    return {
        "status": "healthy" if is_healthy else "degraded",
        "components": {
            "circuit_breakers": {
                "status": "healthy" if not open_circuits else "degraded",
                "open_circuits": open_circuits,
                "stats": circuit_stats
            },
            "caches": {
                "status": "healthy",
                "stats": cache_stats
            },
            "stores": {
                "session_store": session_store_stats,
                "user_store": user_store_stats
            }
        }
    }


@router.get("/circuit-breakers")
async def get_circuit_breakers() -> Dict[str, Any]:
    """
    Get circuit breaker status.

    Shows state and statistics for all circuit breakers.
    """
    registry = get_circuit_breaker_registry()

    return {
        "open_circuits": registry.get_open_circuits(),
        "breakers": registry.get_all_stats()
    }


@router.post("/circuit-breakers/{name}/reset")
async def reset_circuit_breaker(name: str) -> Dict[str, Any]:
    """
    Reset a specific circuit breaker.

    Use with caution - only reset if you're sure the service has recovered.
    """
    registry = get_circuit_breaker_registry()
    breaker = registry.get(name)

    if breaker is None:
        return {
            "success": False,
            "error": f"Circuit breaker '{name}' not found"
        }

    await breaker.reset()

    return {
        "success": True,
        "message": f"Circuit breaker '{name}' reset to CLOSED state"
    }


@router.get("/caches")
async def get_caches() -> Dict[str, Any]:
    """
    Get cache statistics.

    Shows hit rates, sizes, and eviction counts for all caches.
    """
    registry = get_cache_registry()

    return {
        "caches": registry.get_all_stats()
    }


@router.post("/caches/cleanup")
async def cleanup_caches() -> Dict[str, Any]:
    """
    Trigger cache cleanup.

    Removes expired entries from all caches.
    """
    registry = get_cache_registry()
    results = registry.cleanup_all()

    return {
        "success": True,
        "cleaned": results
    }


@router.get("/stores")
async def get_stores() -> Dict[str, Any]:
    """
    Get vector store statistics.

    Shows entry counts, memory usage, and performance metrics.
    """
    try:
        session_stats = get_session_vector_store().get_stats()
    except Exception as e:
        session_stats = {"error": str(e)}

    try:
        user_stats = get_user_vector_store().get_stats()
    except Exception as e:
        user_stats = {"error": str(e)}

    return {
        "session_store": session_stats,
        "user_store": user_stats
    }


@router.post("/stores/cleanup")
async def cleanup_stores() -> Dict[str, Any]:
    """
    Trigger store cleanup.

    Removes expired entries from all vector stores.
    """
    results = {}

    try:
        session_removed = await get_session_vector_store().cleanup_expired()
        results["session_store"] = {"removed": session_removed}
    except Exception as e:
        results["session_store"] = {"error": str(e)}

    try:
        user_removed = await get_user_vector_store().cleanup_expired()
        results["user_store"] = {"removed": user_removed}
    except Exception as e:
        results["user_store"] = {"error": str(e)}

    return {
        "success": True,
        "results": results
    }
