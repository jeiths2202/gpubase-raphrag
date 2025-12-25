"""
KMS API Main Application
GPU Hybrid RAG based Knowledge Management System
"""
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from .core.config import api_settings
from .core.exceptions import (
    APIException,
    api_exception_handler,
    validation_exception_handler,
    generic_exception_handler
)

# Import routers
from .routers import query, documents, history, stats, health, settings, auth, mindmap, admin, content, notes, projects, knowledge_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print(f"🚀 Starting {api_settings.APP_NAME} v{api_settings.APP_VERSION}")
    print(f"📊 Debug mode: {api_settings.DEBUG}")
    # TODO: Initialize database connections, load models, etc.
    yield
    # Shutdown
    print("👋 Shutting down...")
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=api_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    """Add request timing and request ID to responses"""
    request_id = request.headers.get("X-Request-ID", f"req_{uuid.uuid4().hex[:12]}")
    start_time = time.time()

    response = await call_next(request)

    process_time = int((time.time() - start_time) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(process_time)

    return response


# Exception handlers
app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

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


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "name": api_settings.APP_NAME,
        "version": api_settings.APP_VERSION,
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# For running directly with: python -m app.api.main
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.api.main:app",
        host=api_settings.HOST,
        port=api_settings.PORT,
        reload=api_settings.DEBUG,
        workers=1 if api_settings.DEBUG else api_settings.WORKERS
    )
