"""
Health Service - System health monitoring
"""
import asyncio
import time
import httpx
from typing import Dict, Any, Optional
from functools import lru_cache
from datetime import datetime
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from config import config


class HealthService:
    """
    Service for monitoring system health

    Active services:
    - Neo4j database (bolt://192.168.8.11:7687)
    - Multi-LoRA DPO vLLM (Qwen2.5-72B + 15 DPO adapters, GPU 4-7, port 12810)
    - NeMo Embedding service (GPU 5, port 12801)

    Disabled services:
    - Qwen LLM (port 12800) - ENABLE_QWEN_LLM=false
    - CodeQwen (port 12802) - not deployed
    - Vision LLM (port 12803) - not deployed
    """

    # Cache TTL in seconds
    CACHE_TTL = 30

    def __init__(self):
        self._start_time = time.time()
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: float = 0

    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self._start_time)

    async def check_neo4j(self) -> Dict[str, Any]:
        """Check Neo4j database health"""
        start = time.time()
        try:
            # Run synchronous Neo4j query in thread pool to avoid blocking event loop
            import concurrent.futures
            loop = asyncio.get_event_loop()

            def _check():
                from langchain_neo4j import Neo4jGraph
                graph = Neo4jGraph(
                    url=config.neo4j.uri,
                    username=config.neo4j.user,
                    password=config.neo4j.password
                )
                graph.query("RETURN 1")
                return True

            with concurrent.futures.ThreadPoolExecutor() as executor:
                await asyncio.wait_for(
                    loop.run_in_executor(executor, _check),
                    timeout=2.0  # 2 second timeout
                )

            response_time = int((time.time() - start) * 1000)
            return {
                "status": "healthy",
                "response_time_ms": response_time
            }
        except asyncio.TimeoutError:
            return {
                "status": "unhealthy",
                "error": "Timeout (2s)"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_llm(self) -> Dict[str, Any]:
        """Check Qwen Text LLM health (port 12800) - disabled if ENABLE_QWEN_LLM=false"""
        enable = os.getenv("ENABLE_QWEN_LLM", "false").lower()
        if enable not in ("true", "1", "yes"):
            return {"status": "disabled", "reason": "ENABLE_QWEN_LLM=false"}

        start = time.time()
        try:
            base_url = config.llm.api_url.replace("/v1/chat/completions", "")
            health_url = f"{base_url}/health"

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 4"
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_embedding(self) -> Dict[str, Any]:
        """Check NeMo Embedding service health (GPU 5, port 12801)"""
        start = time.time()
        try:
            health_url = f"{config.embedding.api_url}/health/ready"

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 5"
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_code_llm(self) -> Dict[str, Any]:
        """Check Code LLM health (port 12802) - not deployed"""
        return {"status": "disabled", "reason": "Service not deployed"}

    async def check_vision_llm(self) -> Dict[str, Any]:
        """Check Vision LLM health (port 12803) - not deployed"""
        return {"status": "disabled", "reason": "Service not deployed"}

    async def check_learning_llm(self) -> Dict[str, Any]:
        """Check Multi-LoRA DPO vLLM health (Qwen2.5-72B + 15 DPO adapters, GPU 4-7, port 12810)"""
        start = time.time()
        try:
            base_url = config.learning_llm.api_url.replace("/v1/chat/completions", "")
            health_url = f"{base_url}/health"

            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    result = {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 4-7 (4x A100-40GB)",
                    }
                    # Fetch model/adapter info from vLLM
                    try:
                        models_resp = await client.get(f"{base_url}/v1/models")
                        if models_resp.status_code == 200:
                            models_data = models_resp.json()
                            models = models_data.get("data", [])
                            if models:
                                result["model"] = models[0].get("id", "unknown")
                                result["total_models"] = len(models)
                    except Exception:
                        pass
                    return result
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_all(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Check all services health

        Args:
            use_cache: If True, return cached result if available and not expired

        Returns:
            Complete health status for all services
        """
        # Return cached result if valid
        if use_cache and self._cache is not None:
            cache_age = time.time() - self._cache_time
            if cache_age < self.CACHE_TTL:
                # Update uptime in cached result
                self._cache["services"]["api"]["uptime_seconds"] = self.uptime_seconds
                return self._cache

        # Run all health checks in parallel
        neo4j, llm, embedding, code_llm, vision_llm, learning_llm = await asyncio.gather(
            self.check_neo4j(),
            self.check_llm(),
            self.check_embedding(),
            self.check_code_llm(),
            self.check_vision_llm(),
            self.check_learning_llm()
        )

        # Only include active services (skip disabled ones)
        services = {
            "api": {
                "status": "healthy",
                "uptime_seconds": self.uptime_seconds
            },
            "neo4j": neo4j,
            "multi_lora_dpo": learning_llm,
            "embedding": embedding,
        }

        # Include non-disabled services
        if llm.get("status") != "disabled":
            services["qwen_llm"] = llm
        if code_llm.get("status") != "disabled":
            services["code_llm"] = code_llm
        if vision_llm.get("status") != "disabled":
            services["vision_llm"] = vision_llm

        # Determine overall status from active external services only
        active_external = [
            s for key, s in services.items()
            if key != "api" and s.get("status") != "disabled"
        ]
        unhealthy_count = sum(
            1 for s in active_external
            if s.get("status") == "unhealthy"
        )

        if unhealthy_count == 0:
            overall_status = "healthy"
        elif unhealthy_count < len(active_external):
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        result = {
            "status": overall_status,
            "services": services
        }

        # Cache the result
        self._cache = result
        self._cache_time = time.time()

        return result


@lru_cache()
def get_health_service() -> HealthService:
    """Get cached health service instance"""
    return HealthService()
