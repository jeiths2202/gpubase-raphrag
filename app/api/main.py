"""
KMS API Main Application
GPU Hybrid RAG based Knowledge Management System
"""
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
from .routers import query, documents, history, stats, health, settings, auth, mindmap, admin, content, notes, projects, knowledge_graph, knowledge_article, notification, web_source, session_document, external_connection, enterprise


# Initialize mode manager and logger
mode_manager = get_app_mode_manager()
logger = get_logger("kms.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
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

    # TODO: Initialize database connections, load models, etc.
    yield

    # Shutdown
    logger.info("Shutting down application", category=LogCategory.BUSINESS)
    # TODO: Cleanup resources


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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(query.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(history.router, prefix=API_PREFIX)
app.include_router(history.conversations_router, prefix=API_PREFIX)
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
    reload = mode_manager.is_develop
    workers = 1 if mode_manager.is_develop else api_settings.WORKERS
    log_level = mode_manager.get_log_level().lower()

    uvicorn.run(
        "app.api.main:app",
        host=args.host,
        port=args.port,
        reload=reload,
        workers=workers,
        log_level=log_level
    )
