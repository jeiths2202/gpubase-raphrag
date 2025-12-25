"""
Application Exception Hierarchy
Consistent exception handling across the application.
Extends existing exceptions with comprehensive error handling.
"""
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from fastapi import status
import traceback
import uuid


class ErrorCode(str, Enum):
    """Standardized error codes"""
    # General errors (1xxx)
    INTERNAL_ERROR = "ERR_1000"
    VALIDATION_ERROR = "ERR_1001"
    NOT_FOUND = "ERR_1002"
    CONFLICT = "ERR_1003"
    RATE_LIMITED = "ERR_1004"
    SERVICE_UNAVAILABLE = "ERR_1005"

    # Authentication errors (2xxx)
    UNAUTHORIZED = "ERR_2000"
    INVALID_TOKEN = "ERR_2001"
    TOKEN_EXPIRED = "ERR_2002"
    INVALID_CREDENTIALS = "ERR_2003"
    MFA_REQUIRED = "ERR_2004"
    MFA_INVALID = "ERR_2005"
    ACCOUNT_LOCKED = "ERR_2006"
    EMAIL_NOT_VERIFIED = "ERR_2007"

    # Authorization errors (3xxx)
    FORBIDDEN = "ERR_3000"
    INSUFFICIENT_PERMISSIONS = "ERR_3001"
    RESOURCE_ACCESS_DENIED = "ERR_3002"

    # Resource errors (4xxx)
    DOCUMENT_NOT_FOUND = "ERR_4000"
    PROJECT_NOT_FOUND = "ERR_4001"
    USER_NOT_FOUND = "ERR_4002"
    NOTE_NOT_FOUND = "ERR_4003"
    CHUNK_NOT_FOUND = "ERR_4004"

    # Processing errors (5xxx)
    PROCESSING_FAILED = "ERR_5000"
    UPLOAD_FAILED = "ERR_5001"
    EMBEDDING_FAILED = "ERR_5002"
    INDEXING_FAILED = "ERR_5003"
    LLM_ERROR = "ERR_5004"
    CHUNKING_FAILED = "ERR_5005"

    # External service errors (6xxx)
    EXTERNAL_SERVICE_ERROR = "ERR_6000"
    OPENAI_ERROR = "ERR_6001"
    NEO4J_ERROR = "ERR_6002"
    VECTOR_STORE_ERROR = "ERR_6003"
    OAUTH_ERROR = "ERR_6004"

    # Data errors (7xxx)
    INVALID_DATA = "ERR_7000"
    DUPLICATE_ENTRY = "ERR_7001"
    DATA_INTEGRITY_ERROR = "ERR_7002"
    SERIALIZATION_ERROR = "ERR_7003"


@dataclass
class ErrorContext:
    """Additional context for errors"""
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    path: Optional[str] = None
    method: Optional[str] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class AppError(Exception):
    """
    Base application exception.

    All custom exceptions should inherit from this class.
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
        context: Optional[ErrorContext] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        self.cause = cause
        self.context = context or ErrorContext()

        # Capture stack trace
        self._stack_trace = traceback.format_exc() if cause else None

    def to_dict(self, include_trace: bool = False) -> Dict[str, Any]:
        """Convert exception to dictionary for API response"""
        result = {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details
            },
            "meta": {
                "request_id": self.context.request_id,
                "timestamp": self.context.timestamp.isoformat() + "Z"
            }
        }

        if include_trace and self._stack_trace:
            result["error"]["trace"] = self._stack_trace

        return result

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


# ==================== Authentication Errors ====================

class AuthenticationError(AppError):
    """Base authentication exception"""

    def __init__(
        self,
        message: str = "Authentication required",
        code: ErrorCode = ErrorCode.UNAUTHORIZED,
        **kwargs
    ):
        super().__init__(message, code, status_code=status.HTTP_401_UNAUTHORIZED, **kwargs)


class InvalidCredentialsError(AuthenticationError):
    """Invalid login credentials"""

    def __init__(self, message: str = "Invalid email or password", **kwargs):
        super().__init__(message, ErrorCode.INVALID_CREDENTIALS, **kwargs)


class TokenExpiredError(AuthenticationError):
    """JWT token has expired"""

    def __init__(self, message: str = "Token has expired", **kwargs):
        super().__init__(message, ErrorCode.TOKEN_EXPIRED, **kwargs)


class InvalidTokenError(AuthenticationError):
    """Invalid JWT token"""

    def __init__(self, message: str = "Invalid token", **kwargs):
        super().__init__(message, ErrorCode.INVALID_TOKEN, **kwargs)


class MFARequiredError(AuthenticationError):
    """MFA verification required"""

    def __init__(self, message: str = "MFA verification required", **kwargs):
        super().__init__(message, ErrorCode.MFA_REQUIRED, **kwargs)


class AccountLockedError(AuthenticationError):
    """Account is locked"""

    def __init__(
        self,
        message: str = "Account is locked",
        locked_until: Optional[datetime] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if locked_until:
            details["locked_until"] = locked_until.isoformat()
        super().__init__(message, ErrorCode.ACCOUNT_LOCKED, details=details, **kwargs)


# ==================== Authorization Errors ====================

class AuthorizationError(AppError):
    """Base authorization exception"""

    def __init__(
        self,
        message: str = "Access denied",
        code: ErrorCode = ErrorCode.FORBIDDEN,
        **kwargs
    ):
        super().__init__(message, code, status_code=status.HTTP_403_FORBIDDEN, **kwargs)


class InsufficientPermissionsError(AuthorizationError):
    """User lacks required permissions"""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        required_permissions: Optional[List[str]] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if required_permissions:
            details["required_permissions"] = required_permissions
        super().__init__(
            message, ErrorCode.INSUFFICIENT_PERMISSIONS, details=details, **kwargs
        )


# ==================== Resource Errors ====================

class NotFoundError(AppError):
    """Resource not found"""

    def __init__(
        self,
        resource_type: str,
        resource_id: Optional[str] = None,
        message: Optional[str] = None,
        code: ErrorCode = ErrorCode.NOT_FOUND,
        **kwargs
    ):
        if message is None:
            message = f"{resource_type} not found"
            if resource_id:
                message = f"{resource_type} '{resource_id}' not found"

        details = kwargs.pop("details", {})
        details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(message, code, status_code=status.HTTP_404_NOT_FOUND, details=details, **kwargs)


class DocumentNotFoundError(NotFoundError):
    """Document not found"""

    def __init__(self, document_id: Optional[str] = None, **kwargs):
        super().__init__(
            "Document", document_id, code=ErrorCode.DOCUMENT_NOT_FOUND, **kwargs
        )


class ProjectNotFoundError(NotFoundError):
    """Project not found"""

    def __init__(self, project_id: Optional[str] = None, **kwargs):
        super().__init__(
            "Project", project_id, code=ErrorCode.PROJECT_NOT_FOUND, **kwargs
        )


class UserNotFoundError(NotFoundError):
    """User not found"""

    def __init__(self, user_id: Optional[str] = None, **kwargs):
        super().__init__(
            "User", user_id, code=ErrorCode.USER_NOT_FOUND, **kwargs
        )


# ==================== Validation Errors ====================

class ValidationError(AppError):
    """Validation error"""

    def __init__(
        self,
        message: str = "Validation error",
        errors: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if errors:
            details["validation_errors"] = errors

        super().__init__(
            message, ErrorCode.VALIDATION_ERROR, status_code=status.HTTP_400_BAD_REQUEST, details=details, **kwargs
        )


class DuplicateEntryError(AppError):
    """Duplicate entry error"""

    def __init__(
        self,
        field: str,
        value: Optional[str] = None,
        message: Optional[str] = None,
        **kwargs
    ):
        if message is None:
            message = f"Duplicate entry for {field}"

        details = kwargs.pop("details", {})
        details["field"] = field
        if value:
            details["value"] = value

        super().__init__(
            message, ErrorCode.DUPLICATE_ENTRY, status_code=status.HTTP_409_CONFLICT, details=details, **kwargs
        )


# ==================== Processing Errors ====================

class ProcessingError(AppError):
    """Processing error"""

    def __init__(
        self,
        message: str = "Processing failed",
        code: ErrorCode = ErrorCode.PROCESSING_FAILED,
        **kwargs
    ):
        super().__init__(message, code, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, **kwargs)


class LLMError(ProcessingError):
    """LLM operation error"""

    def __init__(
        self,
        message: str = "LLM operation failed",
        model: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if model:
            details["model"] = model

        super().__init__(message, ErrorCode.LLM_ERROR, details=details, **kwargs)


class EmbeddingError(ProcessingError):
    """Embedding generation error"""

    def __init__(self, message: str = "Embedding generation failed", **kwargs):
        super().__init__(message, ErrorCode.EMBEDDING_FAILED, **kwargs)


class IndexingError(ProcessingError):
    """Indexing error"""

    def __init__(self, message: str = "Indexing failed", **kwargs):
        super().__init__(message, ErrorCode.INDEXING_FAILED, **kwargs)


# ==================== External Service Errors ====================

class ExternalServiceError(AppError):
    """External service error"""

    def __init__(
        self,
        service: str,
        message: Optional[str] = None,
        code: ErrorCode = ErrorCode.EXTERNAL_SERVICE_ERROR,
        **kwargs
    ):
        if message is None:
            message = f"External service error: {service}"

        details = kwargs.pop("details", {})
        details["service"] = service

        super().__init__(message, code, status_code=status.HTTP_502_BAD_GATEWAY, details=details, **kwargs)


class RateLimitedError(AppError):
    """Rate limit exceeded"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message, ErrorCode.RATE_LIMITED, status_code=status.HTTP_429_TOO_MANY_REQUESTS, details=details, **kwargs
        )


class ServiceUnavailableError(AppError):
    """Service temporarily unavailable"""

    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        retry_after: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            message, ErrorCode.SERVICE_UNAVAILABLE, status_code=status.HTTP_503_SERVICE_UNAVAILABLE, details=details, **kwargs
        )
