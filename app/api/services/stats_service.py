"""
Stats Service - System statistics and monitoring
"""
import asyncio
from typing import Dict, Any, List
from datetime import datetime, timedelta
from functools import lru_cache
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from .rag_service import get_rag_service


class StatsService:
    """
    Service for retrieving system statistics

    Provides:
    - Database statistics (documents, chunks, entities)
    - Embedding coverage statistics
    - Query statistics and timeline
    - Storage usage
    """

    def __init__(self):
        self._rag_service = None

    @property
    def rag_service(self):
        if self._rag_service is None:
            self._rag_service = get_rag_service()
        return self._rag_service

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        Get complete system statistics

        Returns:
            Dictionary with database, embeddings, queries, and storage stats
        """
        # Get RAG stats
        rag_stats = await self.rag_service.get_stats()

        return {
            "database": {
                "documents_count": rag_stats.get("documents", 0),
                "chunks_count": rag_stats.get("chunks", 0),
                "entities_count": rag_stats.get("entities", 0),
                "relationships_count": rag_stats.get("relationships", 0)
            },
            "embeddings": {
                "total_chunks": rag_stats.get("chunks", 0),
                "with_embedding": rag_stats.get("embeddings", 0),
                "without_embedding": rag_stats.get("chunks", 0) - rag_stats.get("embeddings", 0),
                "coverage_percent": float(rag_stats.get("embedding_coverage", "0%").replace("%", "")),
                "dimension": 4096
            },
            "queries": {
                "total_queries": 0,  # TODO: Implement query logging
                "today_queries": 0,
                "avg_response_time_ms": 0,
                "strategy_distribution": {
                    "vector": 0,
                    "graph": 0,
                    "hybrid": 0,
                    "code": 0
                }
            },
            "storage": {
                "neo4j_size_mb": 0,  # TODO: Implement storage monitoring
                "documents_size_mb": 0
            }
        }

    async def get_query_stats(
        self,
        period: str = "7d",
        granularity: str = "day"
    ) -> Dict[str, Any]:
        """
        Get detailed query statistics for a time period

        Args:
            period: Time period (1d, 7d, 30d, 90d)
            granularity: Aggregation granularity (hour, day, week)

        Returns:
            Query statistics with timeline and top queries
        """
        # Parse period to days
        period_days = {
            "1d": 1,
            "7d": 7,
            "30d": 30,
            "90d": 90
        }.get(period, 7)

        # Generate empty timeline (TODO: Implement actual query logging)
        timeline = []
        end_date = datetime.utcnow()

        for i in range(period_days):
            date = end_date - timedelta(days=i)
            timeline.append({
                "date": date.strftime("%Y-%m-%d"),
                "queries_count": 0,
                "avg_response_time_ms": 0,
                "by_strategy": {
                    "vector": 0,
                    "graph": 0,
                    "hybrid": 0,
                    "code": 0
                }
            })

        timeline.reverse()

        return {
            "period": period,
            "total_queries": 0,
            "avg_response_time_ms": 0,
            "timeline": timeline,
            "top_queries": []
        }

    async def get_document_stats(self) -> Dict[str, Any]:
        """
        Get document statistics

        Returns:
            Document counts by status and language
        """
        rag_stats = await self.rag_service.get_stats()

        return {
            "total_documents": rag_stats.get("documents", 0),
            "by_status": {
                "ready": rag_stats.get("documents", 0),
                "processing": 0,
                "error": 0
            },
            "by_language": {
                "ko": 0,  # TODO: Implement language tracking
                "ja": 0,
                "en": 0
            },
            "total_pages": 0,
            "total_chunks": rag_stats.get("chunks", 0),
            "avg_chunks_per_document": (
                rag_stats.get("chunks", 0) / max(rag_stats.get("documents", 1), 1)
            )
        }


@lru_cache()
def get_stats_service() -> StatsService:
    """Get cached stats service instance"""
    return StatsService()
