"""
Dependency Injection - FastAPI Dependencies for IMS Crawler

Provides singleton instances of repositories, services, and use cases.
"""

import asyncpg
import redis.asyncio as redis
from functools import lru_cache
from typing import AsyncGenerator, Optional
from datetime import timedelta

from pathlib import Path

from ..application.use_cases import ManageCredentialsUseCase, SearchIssuesUseCase, CrawlJobsUseCase, GenerateReportUseCase, GetDashboardStatisticsUseCase
from ..infrastructure.adapters import (
    PostgreSQLCredentialsRepository,
    PostgreSQLIssueRepository,
    PostgreSQLDashboardRepository,
    NvidiaNIMParser,
    NvEmbedQAService,
    PlaywrightCrawler
)
from ..infrastructure.services import (
    CredentialEncryptionService,
    get_encryption_service,
    AttachmentProcessor,
    get_attachment_processor,
    MarkdownReportGenerator,
    RedisCacheService,
    InMemoryCacheService,
    CachedSearchService,
    CachedDashboardService
)
from ..domain.ports.cache_port import CachePort
from ...core.config import api_settings
from ...core.container import get_container
from ...ports.llm_port import LLMPort
from ...ports.embedding_port import EmbeddingPort


# Global connection pools (singletons)
_db_pool: asyncpg.Pool | None = None
_redis_client: Optional[redis.Redis] = None
_cache_service: Optional[CachePort] = None
_crawl_jobs_use_case: Optional[CrawlJobsUseCase] = None


async def get_db_pool() -> asyncpg.Pool:
    """
    Get or create database connection pool.

    Returns:
        asyncpg connection pool
    """
    global _db_pool

    if _db_pool is None:
        settings = api_settings
        _db_pool = await asyncpg.create_pool(
            settings.get_postgres_dsn(),
            min_size=2,
            max_size=10,
            command_timeout=60
        )

    return _db_pool


async def get_credentials_repository() -> PostgreSQLCredentialsRepository:
    """
    Get credentials repository instance.

    Dependency for FastAPI endpoints.
    """
    pool = await get_db_pool()
    return PostgreSQLCredentialsRepository(pool)


def get_credential_encryption_service() -> CredentialEncryptionService:
    """
    Get encryption service instance.

    Dependency for FastAPI endpoints.
    """
    return get_encryption_service()


async def get_manage_credentials_use_case() -> ManageCredentialsUseCase:
    """
    Get ManageCredentials use case instance.

    Dependency for FastAPI endpoints.
    """
    repository = await get_credentials_repository()
    encryption = get_credential_encryption_service()

    return ManageCredentialsUseCase(repository, encryption)


async def get_issue_repository() -> PostgreSQLIssueRepository:
    """
    Get issue repository instance.

    Dependency for FastAPI endpoints.
    """
    pool = await get_db_pool()
    return PostgreSQLIssueRepository(pool)


def get_nvidia_nim_parser() -> NvidiaNIMParser:
    """
    Get NVIDIA NIM parser instance.

    Dependency for FastAPI endpoints.
    """
    container = get_container()
    llm = container.llm
    return NvidiaNIMParser(llm)


def get_nv_embedqa_service() -> NvEmbedQAService:
    """
    Get NV-EmbedQA embedding service instance.

    Dependency for FastAPI endpoints.
    """
    container = get_container()
    embedding = container.embedding
    return NvEmbedQAService(embedding)


async def get_search_issues_use_case() -> SearchIssuesUseCase:
    """
    Get SearchIssues use case instance.

    Dependency for FastAPI endpoints.
    """
    parser = get_nvidia_nim_parser()
    repository = await get_issue_repository()
    embedding = get_nv_embedqa_service()

    return SearchIssuesUseCase(parser, repository, embedding)


def get_playwright_crawler() -> PlaywrightCrawler:
    """
    Get Playwright crawler instance.

    Dependency for FastAPI endpoints.
    """
    settings = api_settings
    encryption = get_encryption_service()
    attachments_dir = Path(settings.UPLOAD_DIR) / "ims_attachments"

    return PlaywrightCrawler(
        encryption_service=encryption,
        attachments_dir=attachments_dir,
        headless=True
    )


async def get_crawl_jobs_use_case() -> CrawlJobsUseCase:
    """
    Get CrawlJobs use case instance (singleton).

    Dependency for FastAPI endpoints.

    IMPORTANT: Returns singleton instance to maintain in-memory job state
    across multiple HTTP requests.
    """
    global _crawl_jobs_use_case

    if _crawl_jobs_use_case is None:
        crawler = get_playwright_crawler()
        credentials_repo = await get_credentials_repository()
        issue_repo = await get_issue_repository()
        embedding = get_nv_embedqa_service()
        attachment_processor = get_attachment_processor()

        _crawl_jobs_use_case = CrawlJobsUseCase(
            crawler=crawler,
            credentials_repository=credentials_repo,
            issue_repository=issue_repo,
            embedding_service=embedding,
            attachment_processor=attachment_processor
        )
        print("[OK] CrawlJobsUseCase singleton initialized")

    return _crawl_jobs_use_case


def get_markdown_report_generator() -> MarkdownReportGenerator:
    """
    Get Markdown report generator instance.

    Dependency for FastAPI endpoints.
    """
    return MarkdownReportGenerator()


async def get_report_generator_use_case() -> GenerateReportUseCase:
    """
    Get GenerateReport use case instance.

    Dependency for FastAPI endpoints.
    """
    issue_repo = await get_issue_repository()
    report_generator = get_markdown_report_generator()

    return GenerateReportUseCase(
        issue_repository=issue_repo,
        report_generator=report_generator
    )


async def get_dashboard_repository() -> PostgreSQLDashboardRepository:
    """
    Get dashboard repository instance.

    Dependency for FastAPI endpoints.
    """
    pool = await get_db_pool()
    return PostgreSQLDashboardRepository(pool)


async def get_dashboard_statistics_use_case() -> GetDashboardStatisticsUseCase:
    """
    Get GetDashboardStatistics use case instance.

    Dependency for FastAPI endpoints.
    """
    dashboard_repo = await get_dashboard_repository()

    return GetDashboardStatisticsUseCase(
        dashboard_repository=dashboard_repo
    )


async def get_redis_client() -> redis.Redis:
    """
    Get or create Redis client.

    Returns:
        Redis async client
    """
    global _redis_client

    if _redis_client is None:
        settings = api_settings
        redis_url = getattr(settings, 'REDIS_URL', None) or "redis://localhost:6379/0"

        _redis_client = await redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=False,
            max_connections=10
        )

    return _redis_client


async def get_cache_service() -> CachePort:
    """
    Get cache service (Redis or InMemory fallback).

    Dependency for FastAPI endpoints.
    """
    global _cache_service

    if _cache_service is None:
        try:
            # Try Redis first
            redis_client = await get_redis_client()
            await redis_client.ping()  # Test connection

            _cache_service = RedisCacheService(
                redis_client=redis_client,
                key_prefix="ims:",
                default_ttl=timedelta(minutes=15)
            )
            print("[OK] Redis cache service initialized")

        except Exception as e:
            # Fallback to in-memory cache
            print(f"[WARN] Redis unavailable ({e}), using in-memory cache")
            _cache_service = InMemoryCacheService(
                default_ttl=timedelta(minutes=15)
            )

    return _cache_service


async def get_cached_search_service() -> CachedSearchService:
    """
    Get cached search service.

    Dependency for FastAPI endpoints.
    """
    search_use_case = await get_search_issues_use_case()
    cache = await get_cache_service()

    return CachedSearchService(
        search_use_case=search_use_case,
        cache=cache,
        cache_ttl=timedelta(minutes=15)
    )


async def get_cached_dashboard_service() -> CachedDashboardService:
    """
    Get cached dashboard service.

    Dependency for FastAPI endpoints.
    """
    dashboard_use_case = await get_dashboard_statistics_use_case()
    cache = await get_cache_service()

    return CachedDashboardService(
        dashboard_use_case=dashboard_use_case,
        cache=cache,
        cache_ttl=timedelta(minutes=5)
    )
