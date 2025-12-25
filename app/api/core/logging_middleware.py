"""
Logging Middleware for FastAPI
Request/Response logging with mode-aware behavior
"""
import time
import uuid
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .app_mode import get_app_mode_manager
from .logging_framework import (
    AppLogger, RequestContext, LogCategory, get_logger
)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive request/response logging.
    Behavior adapts based on application mode.
    """

    # Paths to skip logging (health checks, static files, etc.)
    SKIP_PATHS = {
        "/health",
        "/api/v1/health",
        "/metrics",
        "/favicon.ico",
        "/docs",
        "/redoc",
        "/openapi.json"
    }

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._logger = get_logger("kms.http")
        self._mode_manager = get_app_mode_manager()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response]
    ) -> Response:
        # Skip logging for certain paths
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Generate request ID
        request_id = request.headers.get(
            "X-Request-ID",
            f"req_{uuid.uuid4().hex[:12]}"
        )

        # Extract session and user info from headers/state
        session_id = request.headers.get("X-Session-ID")
        user_id = None
        if hasattr(request.state, "user"):
            user_id = getattr(request.state.user, "id", None)

        # Create request context
        context = RequestContext(
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            endpoint=str(request.url.path),
            method=request.method,
            ip_address=self._get_client_ip(request),
            user_agent=request.headers.get("User-Agent", "")[:200]
        )

        # Set context for logging
        AppLogger.set_request_context(context)

        # Store in request state for later access
        request.state.request_id = request_id
        request.state.session_id = session_id

        # Log request start (develop mode only)
        if self._mode_manager.is_develop:
            self._log_request_start(request, context)

        # Process request
        start_time = time.time()

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = str(int(duration_ms))

            # Log request completion
            self._log_request_complete(
                request, response, duration_ms, context
            )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            self._logger.error(
                f"Request failed: {request.method} {request.url.path}",
                category=LogCategory.REQUEST,
                extra_data={
                    "duration_ms": int(duration_ms),
                    "error": str(e)
                },
                exc_info=True
            )

            raise

        finally:
            # Clear context
            AppLogger.clear_request_context()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"

    def _log_request_start(self, request: Request, context: RequestContext):
        """Log request start (develop mode)"""
        # Build query params summary
        query_params = dict(request.query_params)
        query_str = ""
        if query_params:
            query_str = f"?{len(query_params)} params"

        self._logger.debug(
            f"→ {request.method} {request.url.path}{query_str}",
            category=LogCategory.REQUEST,
            extra_data={
                "query_params": query_params if len(str(query_params)) < 200 else "...",
                "content_type": request.headers.get("Content-Type"),
                "content_length": request.headers.get("Content-Length")
            }
        )

    def _log_request_complete(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
        context: RequestContext
    ):
        """Log request completion"""
        self._logger.log_request(
            method=request.method,
            path=str(request.url.path),
            status_code=response.status_code,
            duration_ms=duration_ms,
            extra_data={
                "content_type": response.headers.get("Content-Type"),
                "content_length": response.headers.get("Content-Length")
            }
        )


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware for detailed performance tracking.
    Logs slow requests and performance metrics.
    """

    def __init__(self, app: ASGIApp, slow_threshold_ms: int = 1000):
        super().__init__(app)
        self._logger = get_logger("kms.performance")
        self._mode_manager = get_app_mode_manager()
        self._slow_threshold = slow_threshold_ms

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response]
    ) -> Response:
        if not self._mode_manager.config.enable_performance_tracking:
            return await call_next(request)

        start_time = time.time()
        start_memory = self._get_memory_usage()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000
        end_memory = self._get_memory_usage()

        # Log slow requests
        threshold = self._mode_manager.config.slow_request_threshold_ms
        if duration_ms > threshold:
            self._logger.warning(
                f"SLOW REQUEST: {request.method} {request.url.path} took {duration_ms:.0f}ms",
                category=LogCategory.PERFORMANCE,
                duration_ms=duration_ms,
                extra_data={
                    "threshold_ms": threshold,
                    "memory_delta_mb": end_memory - start_memory
                }
            )

        return response

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0


class TracingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for distributed tracing.
    Compatible with OpenTelemetry and other APM tools.
    """

    def __init__(self, app: ASGIApp, service_name: str = "kms-api"):
        super().__init__(app)
        self._service_name = service_name
        self._mode_manager = get_app_mode_manager()
        self._tracer = self._init_tracer()

    def _init_tracer(self):
        """Initialize tracer (OpenTelemetry compatible)"""
        if not self._mode_manager.config.enable_tracing:
            return None

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider = TracerProvider()
            trace.set_tracer_provider(provider)

            # Add OTLP exporter if configured
            import os
            otlp_endpoint = os.environ.get("OTLP_ENDPOINT")
            if otlp_endpoint:
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(SimpleSpanProcessor(exporter))

            return trace.get_tracer(self._service_name)
        except ImportError:
            return None

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Response]
    ) -> Response:
        if not self._tracer:
            return await call_next(request)

        # Extract trace context from headers
        trace_id = request.headers.get("X-Trace-ID")
        span_id = request.headers.get("X-Span-ID")

        with self._tracer.start_as_current_span(
            f"{request.method} {request.url.path}",
            attributes={
                "http.method": request.method,
                "http.url": str(request.url),
                "http.user_agent": request.headers.get("User-Agent", ""),
                "service.name": self._service_name
            }
        ) as span:
            response = await call_next(request)

            span.set_attribute("http.status_code", response.status_code)

            # Propagate trace context
            if hasattr(span, "get_span_context"):
                ctx = span.get_span_context()
                response.headers["X-Trace-ID"] = format(ctx.trace_id, "032x")
                response.headers["X-Span-ID"] = format(ctx.span_id, "016x")

            return response


def setup_logging_middleware(app):
    """
    Configure all logging middleware for the application.

    Usage:
        from fastapi import FastAPI
        from app.api.core.logging_middleware import setup_logging_middleware

        app = FastAPI()
        setup_logging_middleware(app)
    """
    mode_manager = get_app_mode_manager()

    # Add middlewares in reverse order (last added = first executed)
    app.add_middleware(LoggingMiddleware)

    if mode_manager.config.enable_performance_tracking:
        app.add_middleware(
            PerformanceMiddleware,
            slow_threshold_ms=mode_manager.config.slow_request_threshold_ms
        )

    if mode_manager.config.enable_tracing:
        app.add_middleware(TracingMiddleware)
