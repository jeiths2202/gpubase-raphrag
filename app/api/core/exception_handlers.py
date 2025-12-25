"""
FastAPI Exception Handlers
Global exception handling for consistent error responses.
"""
from typing import Union
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

from .exceptions import (
    AppException,
    ErrorCode,
    ErrorContext,
    ValidationException
)
from .settings import get_settings

logger = logging.getLogger(__name__)


def configure_exception_handlers(app: FastAPI) -> None:
    """Configure global exception handlers for the FastAPI app"""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request,
        exc: AppException
    ) -> JSONResponse:
        """Handle application exceptions"""
        settings = get_settings()

        # Add request context
        exc.context.path = str(request.url.path)
        exc.context.method = request.method

        # Log error
        log_exception(exc, request)

        # Build response
        include_trace = settings.debug
        response_data = exc.to_dict(include_trace=include_trace)

        return JSONResponse(
            status_code=exc.status_code,
            content=response_data
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors"""
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"]
            })

        validation_exc = ValidationException(
            message="Request validation failed",
            errors=errors
        )
        validation_exc.context.path = str(request.url.path)
        validation_exc.context.method = request.method

        log_exception(validation_exc, request)

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=validation_exc.to_dict()
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle Starlette HTTP exceptions"""
        # Map to appropriate error code
        code_map = {
            400: ErrorCode.VALIDATION_ERROR,
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
            409: ErrorCode.CONFLICT,
            429: ErrorCode.RATE_LIMITED,
            500: ErrorCode.INTERNAL_ERROR,
            502: ErrorCode.EXTERNAL_SERVICE_ERROR,
            503: ErrorCode.SERVICE_UNAVAILABLE,
        }

        error_code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        context = ErrorContext(
            path=str(request.url.path),
            method=request.method
        )

        response_data = {
            "error": {
                "code": error_code.value,
                "message": exc.detail or "An error occurred",
                "details": {},
                "request_id": context.request_id,
                "timestamp": context.timestamp.isoformat()
            }
        }

        logger.warning(
            f"HTTP {exc.status_code}: {exc.detail}",
            extra={
                "status_code": exc.status_code,
                "path": request.url.path,
                "method": request.method,
                "request_id": context.request_id
            }
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=response_data
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle unhandled exceptions"""
        settings = get_settings()
        context = ErrorContext(
            path=str(request.url.path),
            method=request.method
        )

        # Log full error
        logger.exception(
            f"Unhandled exception: {exc}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "request_id": context.request_id,
                "exception_type": type(exc).__name__
            }
        )

        # Build response
        response_data = {
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An unexpected error occurred",
                "details": {},
                "request_id": context.request_id,
                "timestamp": context.timestamp.isoformat()
            }
        }

        # Include error details in debug mode
        if settings.debug:
            response_data["error"]["details"] = {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)
            }

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_data
        )


def log_exception(exc: AppException, request: Request) -> None:
    """Log exception with appropriate level"""
    extra = {
        "error_code": exc.code.value,
        "status_code": exc.status_code,
        "path": request.url.path,
        "method": request.method,
        "request_id": exc.context.request_id,
        "details": exc.details
    }

    if exc.context.user_id:
        extra["user_id"] = exc.context.user_id

    if exc.status_code >= 500:
        logger.error(f"{exc.code.value}: {exc.message}", extra=extra)
        if exc.cause:
            logger.exception("Caused by", exc_info=exc.cause)
    elif exc.status_code >= 400:
        logger.warning(f"{exc.code.value}: {exc.message}", extra=extra)
    else:
        logger.info(f"{exc.code.value}: {exc.message}", extra=extra)
