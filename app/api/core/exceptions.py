"""
Custom Exception Handlers
"""
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from datetime import datetime, timezone
import uuid


class APIException(Exception):
    """Base API Exception"""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict = None
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class DocumentNotFoundException(APIException):
    def __init__(self, document_id: str):
        super().__init__(
            code="DOCUMENT_NOT_FOUND",
            message="문서를 찾을 수 없습니다.",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"document_id": document_id}
        )


class DocumentTooLargeException(APIException):
    def __init__(self, max_size_mb: int, actual_size_mb: float):
        super().__init__(
            code="DOCUMENT_TOO_LARGE",
            message=f"파일 크기가 제한을 초과했습니다. (최대: {max_size_mb}MB)",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"max_size_mb": max_size_mb, "actual_size_mb": actual_size_mb}
        )


class ServiceUnavailableException(APIException):
    def __init__(self, service_name: str, error: str = None):
        super().__init__(
            code=f"SERVICE_{service_name.upper()}_UNAVAILABLE",
            message=f"{service_name} 서비스를 사용할 수 없습니다.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"service": service_name, "error": error}
        )


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            },
            "meta": {
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors"""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력 데이터 유효성 검증에 실패했습니다.",
                "details": {"errors": errors}
            },
            "meta": {
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }
        }
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "서버 내부 오류가 발생했습니다.",
                "details": None
            },
            "meta": {
                "request_id": f"req_{uuid.uuid4().hex[:12]}",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
            }
        }
    )
