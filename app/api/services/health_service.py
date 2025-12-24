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
    - Nemotron LLM
    - NeMo Embedding service
    - Mistral Code LLM
    """

    def __init__(self):
        self._start_time = time.time()

    @property
    def uptime_seconds(self) -> int:
        return int(time.time() - self._start_time)

    async def check_neo4j(self) -> Dict[str, Any]:
        """Check Neo4j database health"""
        start = time.time()
        try:
            from langchain_neo4j import Neo4jGraph
            graph = Neo4jGraph(
                url=config.neo4j.uri,
                username=config.neo4j.user,
                password=config.neo4j.password
            )
            graph.query("RETURN 1")
            response_time = int((time.time() - start) * 1000)

            return {
                "status": "healthy",
                "response_time_ms": response_time
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def check_llm(self) -> Dict[str, Any]:
        """Check Nemotron LLM health"""
        start = time.time()
        try:
            # Extract base URL (remove /chat/completions)
            base_url = config.llm.api_url.replace("/chat/completions", "")
            health_url = f"{base_url}/health/ready"

            async with httpx.AsyncClient(timeout=10.0) as client:
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

    async def check_embedding(self) -> Dict[str, Any]:
        """Check embedding service health"""
        start = time.time()
        try:
            health_url = f"{config.embedding.api_url}/health/ready"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 4,5"
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

    async def check_mistral(self) -> Dict[str, Any]:
        """Check Mistral Code LLM health"""
        start = time.time()
        try:
            # vLLM uses /health endpoint
            base_url = config.code_llm.api_url.replace("/chat/completions", "")
            health_url = f"{base_url}/health"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)
                response_time = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "gpu": "GPU 0"
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

    async def check_all(self) -> Dict[str, Any]:
        """
        Check all services health

        Returns:
            Complete health status for all services
        """
        # Run all health checks in parallel
        neo4j, llm, embedding, mistral = await asyncio.gather(
            self.check_neo4j(),
            self.check_llm(),
            self.check_embedding(),
            self.check_mistral()
        )

        services = {
            "api": {
                "status": "healthy",
                "uptime_seconds": self.uptime_seconds
            },
            "neo4j": neo4j,
            "nemotron_llm": llm,
            "embedding": embedding,
            "mistral_code": mistral
        }

        # Determine overall status
        external_services = [neo4j, llm, embedding, mistral]
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

        return {
            "status": overall_status,
            "services": services
        }


@lru_cache()
def get_health_service() -> HealthService:
    """Get cached health service instance"""
    return HealthService()
