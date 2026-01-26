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

    Checks health of:
    - Neo4j database
    - Qwen LLM (Text, GPU 4, port 12800)
    - NeMo Embedding service (GPU 5, port 12801)
    - CodeQwen (Code, GPU 7, port 12802)
    - Vision LLM (GPU 6, port 12803)
    - Learning LLM (GPU 7, port 12804)
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
        """Check Qwen Text LLM health (GPU 4, port 12800)"""
        start = time.time()
        try:
            # vLLM uses /health endpoint at root (not /v1/health)
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
        """Check CodeQwen Code LLM health (GPU 7, port 12802)"""
        start = time.time()
        try:
            # vLLM uses /health endpoint at root (not /v1/health)
            base_url = config.code_llm.api_url.replace("/v1/chat/completions", "")
            health_url = f"{base_url}/health"

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 7"
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

    async def check_vision_llm(self) -> Dict[str, Any]:
        """Check Vision LLM health (GPU 6, port 12803)"""
        start = time.time()
        try:
            # NIM uses /v1/health/ready endpoint
            base_url = config.vision_llm.api_url.replace("/chat/completions", "")
            health_url = f"{base_url}/health/ready"

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 6"
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

    async def check_learning_llm(self) -> Dict[str, Any]:
        """Check Learning LLM health (GPU 7, port 12804)"""
        start = time.time()
        try:
            # vLLM uses /health endpoint at root (not /v1/health)
            base_url = config.learning_llm.api_url.replace("/v1/chat/completions", "")
            health_url = f"{base_url}/health"

            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 7"
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

        services = {
            "api": {
                "status": "healthy",
                "uptime_seconds": self.uptime_seconds
            },
            "neo4j": neo4j,
            "qwen_llm": llm,
            "embedding": embedding,
            "codeqwen": code_llm,
            "vision_llm": vision_llm,
            "learning_llm": learning_llm
        }

        # Determine overall status (core services only: neo4j, llm, embedding)
        # Vision and Learning LLM are optional services
        core_services = [neo4j, llm, embedding]
        external_services = [neo4j, llm, embedding, code_llm, vision_llm, learning_llm]
        unhealthy_count = sum(
            1 for s in external_services
            if s.get("status") == "unhealthy"
        )

        if unhealthy_count == 0:
            overall_status = "healthy"
        elif unhealthy_count < len(external_services):
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
