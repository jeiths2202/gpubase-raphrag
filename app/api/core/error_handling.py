"""
Mode-Aware Error Handling
Production-safe error responses with detailed develop mode debugging
"""
import sys
import traceback
from typing import Optional, Dict, Any, Type, List
from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .app_mode import get_app_mode_manager, AppMode
from .logging_framework import AppLogger, LogCategory, get_logger


class ErrorCode:
    """Standardized error codes"""
    # General errors (1xxx)
    INTERNAL_ERROR = "E1000"
    VALIDATION_ERROR = "E1001"
    NOT_FOUND = "E1002"
    PERMISSION_DENIED = "E1003"
    RATE_LIMITED = "E1004"

    # Authentication errors (2xxx)
    UNAUTHORIZED = "E2000"
    TOKEN_EXPIRED = "E2001"
    TOKEN_INVALID = "E2002"
    MFA_REQUIRED = "E2003"

    # Business logic errors (3xxx)
    BUSINESS_ERROR = "E3000"
    INVALID_STATE = "E3001"
    RESOURCE_CONFLICT = "E3002"
    QUOTA_EXCEEDED = "E3003"

    # External service errors (4xxx)
    LLM_ERROR = "E4000"
    EMBEDDING_ERROR = "E4001"
    DATABASE_ERROR = "E4002"
    EXTERNAL_API_ERROR = "E4003"


@dataclass
class ErrorContext:
    """Context information for errors"""
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None


class ErrorResponse(BaseModel):
    """Standard error response model"""
    success: bool = False
    error: Dict[str, Any]
    request_id: Optional[str] = None
    timestamp: str


class DevelopErrorDetail(BaseModel):
    """Detailed error info for develop mode"""
    type: str
    message: str
    code: str
    location: Dict[str, Any]
    stack_trace: List[str]
    context: Dict[str, Any]
    suggestions: List[str]


class ProductErrorDetail(BaseModel):
    """Minimal error info for product mode"""
    message: str
    code: str
    reference_id: str


class AppException(Exception):
    """
    Base application exception with mode-aware handling.
    """

    def __init__(
        self,
        message: str,
        code: str = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None,
        suggestions: Optional[List[str]] = None,
        log_level: str = "error"
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.user_message = user_message or self._get_user_message()
        self.suggestions = suggestions or []
        self.log_level = log_level
        self.context: Optional[ErrorContext] = None
        self.exc_info = sys.exc_info()

    def _get_user_message(self) -> str:
        """Get user-friendly message for product mode"""
        messages = {
            ErrorCode.INTERNAL_ERROR: "An internal error occurred. Please try again later.",
            ErrorCode.VALIDATION_ERROR: "The request contains invalid data.",
            ErrorCode.NOT_FOUND: "The requested resource was not found.",
            ErrorCode.PERMISSION_DENIED: "You do not have permission to perform this action.",
            ErrorCode.RATE_LIMITED: "Too many requests. Please wait and try again.",
            ErrorCode.UNAUTHORIZED: "Authentication required.",
            ErrorCode.TOKEN_EXPIRED: "Your session has expired. Please log in again.",
            ErrorCode.TOKEN_INVALID: "Invalid authentication token.",
            ErrorCode.MFA_REQUIRED: "Multi-factor authentication is required.",
            ErrorCode.LLM_ERROR: "AI service is temporarily unavailable.",
            ErrorCode.EMBEDDING_ERROR: "Text processing service is unavailable.",
            ErrorCode.DATABASE_ERROR: "Database service is temporarily unavailable.",
            ErrorCode.EXTERNAL_API_ERROR: "External service is unavailable.",
        }
        return messages.get(self.code, "An error occurred. Please try again.")

    def set_context(self, context: ErrorContext):
        """Set error context"""
        self.context = context

    def to_response(self, request_id: Optional[str] = None) -> Dict[str, Any]:
        """Convert to response based on current mode"""
        mode_manager = get_app_mode_manager()

        if mode_manager.is_develop:
            return self._to_develop_response(request_id)
        return self._to_product_response(request_id)

    def _to_develop_response(self, request_id: Optional[str]) -> Dict[str, Any]:
        """Detailed response for develop mode"""
        # Get stack trace
        stack_trace = []
        if self.exc_info[2]:
            stack_trace = traceback.format_tb(self.exc_info[2])

        location = {}
        if self.context:
            location = {
                "module": self.context.module,
                "function": self.context.function,
                "line": self.context.line,
                "endpoint": self.context.endpoint
            }

        return {
            "success": False,
            "error": {
                "type": self.__class__.__name__,
                "message": self.message,
                "code": self.code,
                "status_code": self.status_code,
                "location": location,
                "stack_trace": stack_trace,
                "details": self.details,
                "suggestions": self.suggestions,
                "context": {
                    "request_id": self.context.request_id if self.context else request_id,
                    "session_id": self.context.session_id if self.context else None,
                    "user_id": self.context.user_id if self.context else None
                }
            },
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }

    def _to_product_response(self, request_id: Optional[str]) -> Dict[str, Any]:
        """Minimal response for product mode"""
        return {
            "success": False,
            "error": {
                "message": self.user_message,
                "code": self.code,
                "reference_id": request_id or "unknown"
            },
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        }


# Specific exception classes
class ValidationException(AppException):
    """Validation error"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
            details=details,
            suggestions=["Check the request format", "Review the API documentation"]
        )


class NotFoundException(AppException):
    """Resource not found"""
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code=ErrorCode.NOT_FOUND,
            status_code=404,
            details={"resource": resource, "identifier": str(identifier)},
            user_message=f"The requested {resource.lower()} was not found."
        )


class AuthenticationException(AppException):
    """Authentication error"""
    def __init__(self, message: str = "Authentication required", code: str = ErrorCode.UNAUTHORIZED):
        super().__init__(
            message=message,
            code=code,
            status_code=401,
            suggestions=["Check your credentials", "Ensure your token is valid"]
        )


class PermissionException(AppException):
    """Permission denied"""
    def __init__(self, action: str, resource: Optional[str] = None):
        msg = f"Permission denied: {action}"
        if resource:
            msg += f" on {resource}"
        super().__init__(
            message=msg,
            code=ErrorCode.PERMISSION_DENIED,
            status_code=403,
            details={"action": action, "resource": resource}
        )


class RateLimitException(AppException):
    """Rate limit exceeded"""
    def __init__(self, limit: int, window_seconds: int, retry_after: int):
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            code=ErrorCode.RATE_LIMITED,
            status_code=429,
            details={
                "limit": limit,
                "window_seconds": window_seconds,
                "retry_after": retry_after
            },
            user_message=f"Too many requests. Please wait {retry_after} seconds."
        )


class LLMException(AppException):
    """LLM service error"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code=ErrorCode.LLM_ERROR,
            status_code=503,
            details=details,
            suggestions=["Retry the request", "Check LLM service status"]
        )


class EmbeddingException(AppException):
    """Embedding service error"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code=ErrorCode.EMBEDDING_ERROR,
            status_code=503,
            details=details
        )


class DatabaseException(AppException):
    """Database error"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code=ErrorCode.DATABASE_ERROR,
            status_code=503,
            details=details
        )


class ExternalAPIException(AppException):
    """External API error"""
    def __init__(self, service: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"{service}: {message}",
            code=ErrorCode.EXTERNAL_API_ERROR,
            status_code=502,
            details={"service": service, **(details or {})}
        )


class ErrorHandler:
    """
    Centralized error handler for FastAPI.
    Provides mode-aware error processing and logging.
    """

    def __init__(self):
        self._logger = get_logger("kms.error")
        self._mode_manager = get_app_mode_manager()

    def _extract_context(self, request: Request, exc: Exception) -> ErrorContext:
        """Extract error context from request and exception"""
        # Get location from traceback
        module, function, line = None, None, None
        tb = sys.exc_info()[2]
        if tb:
            while tb.tb_next:
                tb = tb.tb_next
            frame = tb.tb_frame
            module = frame.f_globals.get("__name__")
            function = frame.f_code.co_name
            line = tb.tb_lineno

        return ErrorContext(
            request_id=getattr(request.state, "request_id", None),
            session_id=getattr(request.state, "session_id", None),
            user_id=getattr(request.state, "user_id", None),
            endpoint=str(request.url.path),
            method=request.method,
            module=module,
            function=function,
            line=line
        )

    async def handle_app_exception(
        self,
        request: Request,
        exc: AppException
    ) -> JSONResponse:
        """Handle AppException"""
        context = self._extract_context(request, exc)
        exc.set_context(context)

        # Log the error
        log_method = getattr(self._logger, exc.log_level, self._logger.error)
        log_method(
            f"[{exc.code}] {exc.message}",
            category=LogCategory.ERROR,
            extra_data={
                "error_code": exc.code,
                "location": f"{context.module}.{context.function}:{context.line}",
                "details": exc.details
            },
            exc_info=self._mode_manager.is_develop
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response(context.request_id)
        )

    async def handle_http_exception(
        self,
        request: Request,
        exc: HTTPException
    ) -> JSONResponse:
        """Handle FastAPI HTTPException"""
        context = self._extract_context(request, exc)

        # Extract message and code from detail if it's a dict
        message = str(exc.detail)
        code = f"HTTP_{exc.status_code}"

        if isinstance(exc.detail, dict):
            message = exc.detail.get("message", message)
            code = exc.detail.get("code", code)

        self._logger.warning(
            f"HTTP {exc.status_code}: {message}",
            category=LogCategory.ERROR,
            extra_data={"status_code": exc.status_code, "code": code}
        )

        if self._mode_manager.is_develop:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "success": False,
                    "error": {
                        "type": "HTTPException",
                        "message": message,
                        "code": code,
                        "status_code": exc.status_code
                    },
                    "request_id": context.request_id,
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
                }
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": {
                    "message": message,
                    "code": code,
                    "reference_id": context.request_id or "unknown"
                },
                "request_id": context.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }
        )

    async def handle_generic_exception(
        self,
        request: Request,
        exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions"""
        context = self._extract_context(request, exc)

        self._logger.critical(
            f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
            category=LogCategory.ERROR,
            extra_data={
                "exception_type": type(exc).__name__,
                "location": f"{context.module}.{context.function}:{context.line}"
            },
            exc_info=True
        )

        if self._mode_manager.is_develop:
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "code": ErrorCode.INTERNAL_ERROR,
                        "location": {
                            "module": context.module,
                            "function": context.function,
                            "line": context.line
                        },
                        "stack_trace": traceback.format_exc().split("\n")
                    },
                    "request_id": context.request_id,
                    "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
                }
            )

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "message": "An internal error occurred. Please try again later.",
                    "code": ErrorCode.INTERNAL_ERROR,
                    "reference_id": context.request_id or "unknown"
                },
                "request_id": context.request_id,
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }
        )


# Singleton error handler
_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get error handler singleton"""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler
