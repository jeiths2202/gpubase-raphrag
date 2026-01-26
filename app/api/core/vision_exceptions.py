"""
Vision Service Exceptions

Comprehensive exception handling for Vision LLM services.
Provides structured error responses and recovery suggestions.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VisionErrorCode(str, Enum):
    """Vision-specific error codes"""
    # API Errors (1xxx)
    API_KEY_MISSING = "VISION_1001"
    API_KEY_INVALID = "VISION_1002"
    API_RATE_LIMITED = "VISION_1003"
    API_QUOTA_EXCEEDED = "VISION_1004"
    API_TIMEOUT = "VISION_1005"
    API_UNAVAILABLE = "VISION_1006"
    API_RESPONSE_INVALID = "VISION_1007"

    # Image Errors (2xxx)
    IMAGE_TOO_LARGE = "VISION_2001"
    IMAGE_FORMAT_UNSUPPORTED = "VISION_2002"
    IMAGE_CORRUPTED = "VISION_2003"
    IMAGE_PROCESSING_FAILED = "VISION_2004"
    IMAGE_COUNT_EXCEEDED = "VISION_2005"
    IMAGE_RESOLUTION_EXCEEDED = "VISION_2006"

    # Document Errors (3xxx)
    DOCUMENT_NOT_FOUND = "VISION_3001"
    DOCUMENT_ACCESS_DENIED = "VISION_3002"
    DOCUMENT_TOO_LARGE = "VISION_3003"
    DOCUMENT_TYPE_UNSUPPORTED = "VISION_3004"
    DOCUMENT_PROCESSING_FAILED = "VISION_3005"
    DOCUMENT_NO_VISUAL_CONTENT = "VISION_3006"

    # Routing Errors (4xxx)
    ROUTING_FAILED = "VISION_4001"
    NO_SUITABLE_MODEL = "VISION_4002"
    MODEL_UNAVAILABLE = "VISION_4003"
    FALLBACK_EXHAUSTED = "VISION_4004"

    # Budget/Limit Errors (5xxx)
    BUDGET_EXCEEDED = "VISION_5001"
    RATE_LIMIT_EXCEEDED = "VISION_5002"
    TOKEN_LIMIT_EXCEEDED = "VISION_5003"
    COST_LIMIT_EXCEEDED = "VISION_5004"

    # Internal Errors (9xxx)
    INTERNAL_ERROR = "VISION_9001"
    CONFIGURATION_ERROR = "VISION_9002"
    CACHE_ERROR = "VISION_9003"
    SERIALIZATION_ERROR = "VISION_9004"


@dataclass
class VisionErrorDetail:
    """Detailed error information"""
    code: VisionErrorCode
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    suggestions: List[str] = field(default_factory=list)
    retry_after: Optional[int] = None  # seconds
    recoverable: bool = True


class VisionException(Exception):
    """Base exception for Vision services"""

    def __init__(
        self,
        code: VisionErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        retry_after: Optional[int] = None,
        recoverable: bool = True,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.suggestions = suggestions or []
        self.retry_after = retry_after
        self.recoverable = recoverable
        self.cause = cause

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
                "suggestions": self.suggestions,
                "retry_after": self.retry_after,
                "recoverable": self.recoverable,
            }
        }

    def to_error_detail(self) -> VisionErrorDetail:
        """Convert to VisionErrorDetail"""
        return VisionErrorDetail(
            code=self.code,
            message=self.message,
            details=self.details,
            suggestions=self.suggestions,
            retry_after=self.retry_after,
            recoverable=self.recoverable,
        )


# ==================== API Exceptions ====================

class VisionAPIException(VisionException):
    """Base exception for Vision API errors"""
    pass


class APIKeyMissingError(VisionAPIException):
    """API key not configured"""

    def __init__(self, provider: str):
        super().__init__(
            code=VisionErrorCode.API_KEY_MISSING,
            message=f"{provider} API key is not configured",
            details={"provider": provider},
            suggestions=[
                f"Configure {provider.upper()}_API_KEY in environment variables",
                "Check settings.vision.api_key configuration",
            ],
            recoverable=False,
        )


class APIKeyInvalidError(VisionAPIException):
    """API key is invalid"""

    def __init__(self, provider: str, reason: str = ""):
        super().__init__(
            code=VisionErrorCode.API_KEY_INVALID,
            message=f"{provider} API key is invalid: {reason}",
            details={"provider": provider, "reason": reason},
            suggestions=[
                f"Verify the {provider} API key is correct",
                "Check if the API key has been revoked",
                "Generate a new API key from the provider dashboard",
            ],
            recoverable=False,
        )


class APIRateLimitedError(VisionAPIException):
    """API rate limit exceeded"""

    def __init__(
        self,
        provider: str,
        retry_after: int = 60,
        limit_type: str = "requests",
    ):
        super().__init__(
            code=VisionErrorCode.API_RATE_LIMITED,
            message=f"{provider} API rate limit exceeded ({limit_type})",
            details={"provider": provider, "limit_type": limit_type},
            suggestions=[
                f"Wait {retry_after} seconds before retrying",
                "Consider upgrading to a higher tier plan",
                "Implement request queuing or batching",
            ],
            retry_after=retry_after,
            recoverable=True,
        )


class APIQuotaExceededError(VisionAPIException):
    """API quota exceeded"""

    def __init__(self, provider: str, quota_type: str = "monthly"):
        super().__init__(
            code=VisionErrorCode.API_QUOTA_EXCEEDED,
            message=f"{provider} {quota_type} quota exceeded",
            details={"provider": provider, "quota_type": quota_type},
            suggestions=[
                "Check your billing and usage dashboard",
                "Upgrade your subscription plan",
                "Wait for quota reset",
            ],
            recoverable=False,
        )


class APITimeoutError(VisionAPIException):
    """API request timeout"""

    def __init__(self, provider: str, timeout_seconds: int):
        super().__init__(
            code=VisionErrorCode.API_TIMEOUT,
            message=f"{provider} API request timed out after {timeout_seconds}s",
            details={"provider": provider, "timeout": timeout_seconds},
            suggestions=[
                "Reduce image size or count",
                "Simplify the prompt",
                "Retry the request",
            ],
            retry_after=5,
            recoverable=True,
        )


class APIUnavailableError(VisionAPIException):
    """API service unavailable"""

    def __init__(self, provider: str, reason: str = ""):
        super().__init__(
            code=VisionErrorCode.API_UNAVAILABLE,
            message=f"{provider} API is currently unavailable: {reason}",
            details={"provider": provider, "reason": reason},
            suggestions=[
                "Check provider status page",
                "Try fallback provider",
                "Retry after a few minutes",
            ],
            retry_after=60,
            recoverable=True,
        )


# ==================== Image Exceptions ====================

class VisionImageException(VisionException):
    """Base exception for image-related errors"""
    pass


class ImageTooLargeError(VisionImageException):
    """Image exceeds size limit"""

    def __init__(self, size_bytes: int, max_bytes: int, filename: str = ""):
        size_mb = size_bytes / (1024 * 1024)
        max_mb = max_bytes / (1024 * 1024)
        super().__init__(
            code=VisionErrorCode.IMAGE_TOO_LARGE,
            message=f"Image too large: {size_mb:.1f}MB (max {max_mb:.1f}MB)",
            details={
                "size_bytes": size_bytes,
                "max_bytes": max_bytes,
                "filename": filename,
            },
            suggestions=[
                f"Resize image to under {max_mb:.0f}MB",
                "Compress the image",
                "Use a lower resolution version",
            ],
            recoverable=True,
        )


class ImageFormatUnsupportedError(VisionImageException):
    """Image format not supported"""

    def __init__(self, format: str, supported_formats: List[str]):
        super().__init__(
            code=VisionErrorCode.IMAGE_FORMAT_UNSUPPORTED,
            message=f"Image format '{format}' is not supported",
            details={
                "format": format,
                "supported_formats": supported_formats,
            },
            suggestions=[
                f"Convert image to one of: {', '.join(supported_formats)}",
                "Use PNG or JPEG for best compatibility",
            ],
            recoverable=True,
        )


class ImageCorruptedError(VisionImageException):
    """Image file is corrupted"""

    def __init__(self, filename: str = "", reason: str = ""):
        super().__init__(
            code=VisionErrorCode.IMAGE_CORRUPTED,
            message=f"Image file is corrupted or unreadable: {reason}",
            details={"filename": filename, "reason": reason},
            suggestions=[
                "Re-download or re-export the image",
                "Check if the file was fully uploaded",
                "Try a different image file",
            ],
            recoverable=False,
        )


class ImageCountExceededError(VisionImageException):
    """Too many images in request"""

    def __init__(self, count: int, max_count: int):
        super().__init__(
            code=VisionErrorCode.IMAGE_COUNT_EXCEEDED,
            message=f"Too many images: {count} (max {max_count})",
            details={"count": count, "max_count": max_count},
            suggestions=[
                f"Reduce to {max_count} or fewer images",
                "Split into multiple requests",
                "Combine images into a single collage",
            ],
            recoverable=True,
        )


# ==================== Document Exceptions ====================

class VisionDocumentException(VisionException):
    """Base exception for document-related errors"""
    pass


class DocumentNotFoundError(VisionDocumentException):
    """Document not found"""

    def __init__(self, document_id: str):
        super().__init__(
            code=VisionErrorCode.DOCUMENT_NOT_FOUND,
            message=f"Document not found: {document_id}",
            details={"document_id": document_id},
            suggestions=[
                "Verify the document ID is correct",
                "Check if the document was deleted",
                "Re-upload the document",
            ],
            recoverable=False,
        )


class DocumentAccessDeniedError(VisionDocumentException):
    """Access to document denied"""

    def __init__(self, document_id: str, reason: str = ""):
        super().__init__(
            code=VisionErrorCode.DOCUMENT_ACCESS_DENIED,
            message=f"Access denied to document: {document_id}",
            details={"document_id": document_id, "reason": reason},
            suggestions=[
                "Check document permissions",
                "Request access from document owner",
            ],
            recoverable=False,
        )


class DocumentTypeUnsupportedError(VisionDocumentException):
    """Document type not supported for vision processing"""

    def __init__(self, doc_type: str, supported_types: List[str]):
        super().__init__(
            code=VisionErrorCode.DOCUMENT_TYPE_UNSUPPORTED,
            message=f"Document type '{doc_type}' not supported for vision processing",
            details={
                "document_type": doc_type,
                "supported_types": supported_types,
            },
            suggestions=[
                f"Convert to: {', '.join(supported_types)}",
                "Export as PDF or images",
            ],
            recoverable=True,
        )


class DocumentNoVisualContentError(VisionDocumentException):
    """Document has no visual content"""

    def __init__(self, document_id: str):
        super().__init__(
            code=VisionErrorCode.DOCUMENT_NO_VISUAL_CONTENT,
            message=f"Document has no visual content to process",
            details={"document_id": document_id},
            suggestions=[
                "Use text-based query for this document",
                "The document may be text-only",
            ],
            recoverable=True,
        )


# ==================== Routing Exceptions ====================

class VisionRoutingException(VisionException):
    """Base exception for routing errors"""
    pass


class RoutingFailedError(VisionRoutingException):
    """Routing decision failed"""

    def __init__(self, reason: str):
        super().__init__(
            code=VisionErrorCode.ROUTING_FAILED,
            message=f"Failed to route query: {reason}",
            details={"reason": reason},
            suggestions=[
                "Try with force_text=True or force_vision=True",
                "Simplify the query",
            ],
            recoverable=True,
        )


class NoSuitableModelError(VisionRoutingException):
    """No suitable model available"""

    def __init__(self, requirements: Dict[str, Any]):
        super().__init__(
            code=VisionErrorCode.NO_SUITABLE_MODEL,
            message="No suitable vision model available for the request",
            details={"requirements": requirements},
            suggestions=[
                "Configure additional vision providers",
                "Check API key configurations",
            ],
            recoverable=False,
        )


class FallbackExhaustedError(VisionRoutingException):
    """All fallback options exhausted"""

    def __init__(self, tried_providers: List[str], errors: List[str]):
        super().__init__(
            code=VisionErrorCode.FALLBACK_EXHAUSTED,
            message="All vision providers failed",
            details={
                "tried_providers": tried_providers,
                "errors": errors,
            },
            suggestions=[
                "Check all provider configurations",
                "Verify API keys are valid",
                "Try again later",
            ],
            retry_after=60,
            recoverable=True,
        )


# ==================== Budget/Limit Exceptions ====================

class VisionBudgetException(VisionException):
    """Base exception for budget-related errors"""
    pass


class BudgetExceededError(VisionBudgetException):
    """Budget limit exceeded"""

    def __init__(
        self,
        budget_type: str,
        current: float,
        limit: float,
        reset_time: Optional[str] = None,
    ):
        super().__init__(
            code=VisionErrorCode.BUDGET_EXCEEDED,
            message=f"{budget_type} budget exceeded: ${current:.2f}/${limit:.2f}",
            details={
                "budget_type": budget_type,
                "current": current,
                "limit": limit,
                "reset_time": reset_time,
            },
            suggestions=[
                "Wait for budget reset",
                "Request budget increase",
                "Use text-only queries",
            ],
            recoverable=False,
        )


class RateLimitExceededError(VisionBudgetException):
    """Rate limit exceeded"""

    def __init__(self, limit_type: str, current: int, limit: int, retry_after: int):
        super().__init__(
            code=VisionErrorCode.RATE_LIMIT_EXCEEDED,
            message=f"{limit_type} rate limit exceeded: {current}/{limit}",
            details={
                "limit_type": limit_type,
                "current": current,
                "limit": limit,
            },
            suggestions=[
                f"Wait {retry_after} seconds",
                "Reduce request frequency",
            ],
            retry_after=retry_after,
            recoverable=True,
        )


# ==================== Exception Handler ====================

class VisionExceptionHandler:
    """
    Handler for Vision exceptions.

    Provides consistent error handling, logging, and response formatting.
    """

    @staticmethod
    def handle(exception: Exception) -> VisionErrorDetail:
        """Convert any exception to VisionErrorDetail."""
        if isinstance(exception, VisionException):
            logger.warning(
                f"Vision error: {exception.code.value} - {exception.message}",
                extra={"details": exception.details},
            )
            return exception.to_error_detail()

        # Handle unknown exceptions
        logger.error(f"Unexpected vision error: {exception}", exc_info=True)
        return VisionErrorDetail(
            code=VisionErrorCode.INTERNAL_ERROR,
            message=str(exception),
            suggestions=["Contact support if the issue persists"],
            recoverable=False,
        )

    @staticmethod
    def from_api_error(
        provider: str,
        status_code: int,
        error_message: str,
    ) -> VisionException:
        """Create appropriate exception from API error."""
        if status_code == 401:
            return APIKeyInvalidError(provider, error_message)
        elif status_code == 429:
            return APIRateLimitedError(provider)
        elif status_code == 402:
            return APIQuotaExceededError(provider)
        elif status_code == 408:
            return APITimeoutError(provider, 60)
        elif status_code >= 500:
            return APIUnavailableError(provider, error_message)
        else:
            return VisionAPIException(
                code=VisionErrorCode.API_RESPONSE_INVALID,
                message=f"{provider} API error: {error_message}",
                details={"status_code": status_code},
            )
