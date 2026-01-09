"""
KMS API Main Application
GPU Hybrid RAG based Knowledge Management System
"""
import sys
import asyncio

# Windows asyncio fix: Enable subprocess support for Playwright
# SelectorEventLoop (default on Windows) doesn't support subprocesses
# ProactorEventLoop is required for asyncio.create_subprocess_exec()
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import time
import uuid
import argparse
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from .core.config import api_settings
from .core.app_mode import get_app_mode_manager, AppMode
from .core.logging_framework import get_logger, get_token_logger, LogCategory
from .core.logging_middleware import setup_logging_middleware
from .core.error_handling import (
    get_error_handler,
    AppException,
    ValidationException
)
from .core.exceptions import (
    APIException,
    api_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)

# Import routers
from .routers import query, documents, history, stats, health, settings, auth, mindmap, admin, content, notes, projects, knowledge_graph, knowledge_article, notification, web_source, session_document, external_connection, enterprise, system, preferences, vision, conversations, workspace, admin_traces, system_metrics, db_stats, ims_chat
from .ims_crawler.presentation import credentials_router, search_router, jobs_router, reports_router, dashboard_router, cache_router, tasks_router


# Initialize mode manager and logger
mode_manager = get_app_mode_manager()
logger = get_logger("kms.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # ==================== Secrets Validation ====================
    # SECURITY: Validate all required secrets FIRST before anything else
    # This ensures the application fails fast if secrets are missing or insecure
    from .core.secrets_manager import validate_secrets_on_startup, SecretValidationError
    try:
        validate_secrets_on_startup()
        logger.info(
            "All required secrets validated successfully",
            category=LogCategory.BUSINESS
        )

        # DEBUG: Log CORP_EMAIL_DOMAINS configuration to file
        with open('startup_debug.log', 'w') as f:
            f.write(f"{'='*60}\n")
            f.write(f"[STARTUP DEBUG] CORP_EMAIL_DOMAINS configuration:\n")
            f.write(f"  Raw value: '{api_settings.CORP_EMAIL_DOMAINS}'\n")
            f.write(f"  Parsed list: {api_settings.get_corp_domains_list()}\n")
            f.write(f"  Test email: ijshin@tmaxsoft.co.jp\n")
            f.write(f"  is_corp_email: {api_settings.is_corp_email('ijshin@tmaxsoft.co.jp')}\n")
            f.write(f"{'='*60}\n")

    except SecretValidationError as e:
        logger.error(
            f"FATAL: Secrets validation failed: {e}",
            category=LogCategory.BUSINESS
        )
        raise  # Application should not start without valid secrets

    # ==================== PostgreSQL Auth Service Initialization ====================
    # Initialize PostgreSQL-backed authentication service
    from .services.auth_service import initialize_auth_service
    try:
        dsn = api_settings.get_postgres_dsn()
        auth_service = await initialize_auth_service(dsn)
        logger.info(
            "[OK] PostgreSQL-backed authentication initialized",
            category=LogCategory.BUSINESS,
            extra_data={
                "admin_email": "admin@localhost",
                "fixed_admin_id": "admin"
            }
        )
    except Exception as e:
        logger.error(
            f"FATAL: Auth service initialization failed: {e}",
            category=LogCategory.BUSINESS
        )
        raise  # Application should not start without authentication

    # ==================== Database Pool Initialization ====================
    # Initialize PostgreSQL connection pool for conversation repository
    import asyncpg
    from .infrastructure.postgres.conversation_repository import PostgresConversationRepository
    from .core.container import Container

    db_pool = None
    conversation_repo = None
    try:
        dsn = api_settings.get_postgres_dsn()
        db_pool = await asyncpg.create_pool(
            dsn,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info(
            "[OK] PostgreSQL connection pool created",
            category=LogCategory.BUSINESS,
            extra_data={
                "min_size": 5,
                "max_size": 20
            }
        )

        # Create conversation repository with the pool
        conversation_repo = PostgresConversationRepository(db_pool)

        # Register repository in container
        container = Container.get_instance()
        container.register_singleton("conversation_repository", conversation_repo)

        # Initialize conversation service with PostgreSQL repository
        from .services.conversation_service import ConversationService, set_conversation_service
        postgres_conversation_service = ConversationService(repository=conversation_repo)
        set_conversation_service(postgres_conversation_service)

        logger.info(
            "[OK] Conversation repository and service initialized with PostgreSQL",
            category=LogCategory.BUSINESS
        )

        # ==================== Trace System Initialization ====================
        # Initialize trace repository and writer for E2E message tracing
        from .infrastructure.postgres.trace_repository import TraceRepository
        from .infrastructure.services.trace_writer import initialize_trace_writer

        trace_repo = TraceRepository(db_pool)
        trace_writer = initialize_trace_writer(trace_repo)
        await trace_writer.start()

        # Register in container
        container.register_singleton("trace_repository", trace_repo)
        container.register_singleton("trace_writer", trace_writer)

        logger.info(
            "[OK] Trace system initialized (E2E message tracing enabled)",
            category=LogCategory.BUSINESS,
            extra_data={
                "batch_size": trace_writer.batch_size,
                "batch_timeout_seconds": trace_writer.batch_timeout
            }
        )

    except Exception as e:
        logger.warning(
            f"PostgreSQL pool initialization failed, using in-memory storage: {e}",
            category=LogCategory.BUSINESS
        )
        # Continue without PostgreSQL - will fall back to in-memory storage
        trace_writer = None

    # ==================== Background Task Queue Initialization ====================
    from .ims_crawler.infrastructure.services import get_task_queue
    try:
        task_queue = get_task_queue(max_concurrent=3)
        await task_queue.start()
        logger.info(
            "[OK] Background task queue initialized",
            category=LogCategory.BUSINESS,
            extra_data={"max_concurrent_tasks": 3}
        )
    except Exception as e:
        logger.warning(
            f"Background task queue initialization failed: {e}",
            category=LogCategory.BUSINESS
        )
        task_queue = None

    # ==================== Application Startup ====================
    logger.info(
        f"Starting {api_settings.APP_NAME} v{api_settings.APP_VERSION}",
        category=LogCategory.BUSINESS,
        extra_data={
            "mode": mode_manager.mode.value,
            "log_level": mode_manager.get_log_level(),
            "token_logging": mode_manager.should_log_tokens(),
            "performance_tracking": mode_manager.config.enable_performance_tracking
        }
    )

    if mode_manager.is_develop:
        logger.debug(
            "Running in DEVELOP mode - detailed logging enabled",
            category=LogCategory.BUSINESS
        )
    else:
        logger.info(
            "Running in PRODUCT mode - optimized for performance",
            category=LogCategory.BUSINESS
        )

    yield

    # ==================== Application Shutdown ====================
    logger.info("Shutting down application", category=LogCategory.BUSINESS)

    # Stop trace writer (flush remaining traces)
    if trace_writer is not None:
        try:
            await trace_writer.stop()
            logger.info("Trace writer stopped and flushed", category=LogCategory.BUSINESS)
        except Exception as e:
            logger.warning(f"Error stopping trace writer: {e}", category=LogCategory.BUSINESS)

    # Stop background task queue
    if task_queue is not None:
        try:
            await task_queue.stop()
            logger.info("Background task queue stopped", category=LogCategory.BUSINESS)
        except Exception as e:
            logger.warning(f"Error stopping task queue: {e}", category=LogCategory.BUSINESS)

    # Close database pool
    if db_pool is not None:
        await db_pool.close()
        logger.info("Database pool closed", category=LogCategory.BUSINESS)


# Create FastAPI application
app = FastAPI(
    title=api_settings.APP_NAME,
    description="""
## GPU Hybrid RAG 기반 Knowledge Management System API

이 API는 NVIDIA GPU 기반의 Hybrid RAG 시스템을 통해 지식 관리 기능을 제공합니다.

### 주요 기능
- **Query API**: RAG 질의 및 답변 생성
- **Documents API**: 문서 업로드 및 관리
- **History API**: 질의 히스토리 관리
- **Stats API**: 시스템 통계 조회
- **Health API**: 시스템 상태 확인
- **Mindmap API**: 문서 기반 마인드맵 자동 생성 및 관리
- **Admin API**: 관리자 대시보드 및 사용자 관리
- **Content API**: AI 기반 콘텐츠 생성 (요약, FAQ, 학습가이드, 브리핑, 타임라인, 목차)
- **Notes API**: 노트 및 메모 관리
- **Projects API**: 프로젝트/노트북 관리 및 공유
- **Knowledge Graph API**: 쿼리 기반 지식 그래프 생성 및 탐색
- **Knowledge Article API**: 지식 등록, 검수, 게시 워크플로우
- **Notification API**: 인앱 알림 및 메시지 관리
- **Web Source API**: URL 기반 웹 콘텐츠 RAG 처리
- **Session Document API**: 채팅 세션별 문서 업로드 및 우선순위 RAG
- **External Connection API**: 외부 리소스 연동 (OneNote, GitHub, Google Drive, Notion, Confluence)
- **Enterprise API**: 엔터프라이즈 기능 (MFA, 감사 로그, 문서 버전 관리, 협업)
- **System API**: 시스템 상태 모니터링 (GPU, AI 모델, 인덱스, Neo4j)
- **Vision API**: Vision LLM 기반 시각적 문서 분석 및 질의 (차트, 다이어그램, 이미지 인식)
- **Workspace API**: 멀티메뉴 작업공간 상태 영구 저장 및 복원 (채팅, 문서, 마인드맵, 지식그래프 등)

### 기술 스택
- **LLM**: Nemotron Nano 9B, Mistral NeMo 12B
- **Embedding**: NV-EmbedQA-Mistral 7B v2
- **Database**: Neo4j (Graph + Vector Index)
    """,
    version=api_settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Setup logging middleware (mode-aware)
setup_logging_middleware(app)

# ==================== Security Middleware Stack ====================
# SECURITY: Order matters - Security headers should wrap CORS
from .core.security_middleware import SecurityHeadersMiddleware, get_cors_config

# Add security headers middleware (outermost - applied to all responses)
app.add_middleware(
    SecurityHeadersMiddleware,
    environment=api_settings.APP_ENV
)

# CORS middleware with hardened settings
# SECURITY: Explicit methods and headers instead of wildcards
cors_config = get_cors_config(api_settings.APP_ENV, api_settings.CORS_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config["allow_origins"],
    allow_credentials=cors_config["allow_credentials"],
    allow_methods=cors_config["allow_methods"],
    allow_headers=cors_config["allow_headers"],
    expose_headers=cors_config["expose_headers"],
    max_age=cors_config["max_age"],
)


# Mode-aware exception handlers
error_handler = get_error_handler()


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle application exceptions with mode awareness"""
    return await error_handler.handle_app_exception(request, exc)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return await error_handler.handle_http_exception(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler_new(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    validation_exc = ValidationException(
        message="Request validation failed",
        details={"errors": exc.errors()}
    )
    return await error_handler.handle_app_exception(request, validation_exc)


@app.exception_handler(Exception)
async def generic_exception_handler_new(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    return await error_handler.handle_generic_exception(request, exc)


# Legacy exception handlers (for backward compatibility)
app.add_exception_handler(APIException, api_exception_handler)


# Include routers with /api/v1 prefix
API_PREFIX = "/api/v1"

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(admin_traces.router, prefix=API_PREFIX)  # E2E trace query API (admin only)
app.include_router(query.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(history.router, prefix=API_PREFIX)
app.include_router(conversations.router, prefix=API_PREFIX)  # Comprehensive conversations management
app.include_router(stats.router, prefix=API_PREFIX)
app.include_router(health.router, prefix=API_PREFIX)
app.include_router(settings.router, prefix=API_PREFIX)
app.include_router(mindmap.router, prefix=API_PREFIX)
app.include_router(content.router, prefix=API_PREFIX)
app.include_router(notes.router, prefix=API_PREFIX)
app.include_router(projects.router, prefix=API_PREFIX)
app.include_router(knowledge_graph.router, prefix=API_PREFIX)
app.include_router(knowledge_article.router, prefix=API_PREFIX)
app.include_router(notification.router, prefix=API_PREFIX)
app.include_router(web_source.router, prefix=API_PREFIX)
app.include_router(session_document.router, prefix=API_PREFIX)
app.include_router(external_connection.router, prefix=API_PREFIX)
app.include_router(enterprise.router, prefix=API_PREFIX)
app.include_router(system.router, prefix=API_PREFIX)
app.include_router(preferences.router, prefix=API_PREFIX)
app.include_router(vision.router, prefix=API_PREFIX)
app.include_router(workspace.router, prefix=API_PREFIX)  # Persistent workspace state management
app.include_router(system_metrics.router, prefix=API_PREFIX)  # System resource monitoring
app.include_router(db_stats.router, prefix=API_PREFIX)  # PostgreSQL database monitoring

# IMS Crawler routers
app.include_router(credentials_router, prefix=API_PREFIX)  # IMS credentials management
app.include_router(search_router, prefix=API_PREFIX)  # IMS natural language search
app.include_router(jobs_router, prefix=API_PREFIX)  # IMS crawl jobs with SSE streaming
app.include_router(reports_router, prefix=API_PREFIX)  # IMS markdown report generation
app.include_router(dashboard_router, prefix=API_PREFIX)  # IMS dashboard statistics
app.include_router(cache_router, prefix=API_PREFIX)  # IMS cache management
app.include_router(tasks_router, prefix=API_PREFIX)  # IMS background task queue management
app.include_router(ims_chat.router, prefix=API_PREFIX)  # IMS AI chat (limited to searched issues)


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "name": api_settings.APP_NAME,
        "version": api_settings.APP_VERSION,
        "mode": mode_manager.mode.value,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# Mode status endpoint
@app.get("/mode", tags=["System"])
async def get_mode():
    """Get current application mode and configuration"""
    config = mode_manager.config

    # Only expose configuration details in develop mode
    if mode_manager.is_develop:
        return {
            "mode": mode_manager.mode.value,
            "config": {
                "log_level": config.log_level,
                "enable_token_logging": config.enable_token_logging,
                "enable_debug_logs": config.enable_debug_logs,
                "enable_stack_trace": config.enable_stack_trace,
                "enable_performance_tracking": config.enable_performance_tracking,
                "slow_request_threshold_ms": config.slow_request_threshold_ms,
                "enable_tracing": config.enable_tracing
            }
        }

    return {
        "mode": mode_manager.mode.value
    }


# For running directly with: python -m app.api.main
if __name__ == "__main__":
    import uvicorn

    # Parse CLI arguments for mode
    parser = argparse.ArgumentParser(description="KMS API Server")
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["develop", "product", "dev", "prod"],
        default=None,
        help="Application mode (develop/product)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=api_settings.HOST,
        help="Host to bind"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=api_settings.PORT,
        help="Port to bind"
    )

    args = parser.parse_args()

    # Apply CLI mode if specified
    if args.mode:
        mode_manager.set_mode(AppMode.from_string(args.mode))

    # Configure uvicorn based on mode
    # Windows: Disable reload to ensure ProactorEventLoop is used for Playwright
    # uvicorn reload spawns a subprocess that doesn't inherit the event loop policy,
    # causing Playwright to fail with NotImplementedError on Windows
    if sys.platform == 'win32':
        reload = False
        workers = 1
        if mode_manager.is_develop:
            print("[Windows] Auto-reload disabled for Playwright compatibility")
            print("[Windows] Restart manually after code changes")
    else:
        reload = mode_manager.is_develop
        workers = 1 if mode_manager.is_develop else api_settings.WORKERS
    log_level = mode_manager.get_log_level().lower()

    # Windows asyncio fix for uvicorn subprocess
    # When using reload=True, uvicorn spawns a new process that needs the event loop policy
    uvicorn_config = {
        "app": "app.api.main:app",
        "host": args.host,
        "port": args.port,
        "reload": reload,
        "workers": workers,
        "log_level": log_level,
    }

    # On Windows, use asyncio event loop to ensure ProactorEventLoop is used
    if sys.platform == 'win32':
        uvicorn_config["loop"] = "asyncio"

    uvicorn.run(**uvicorn_config)
