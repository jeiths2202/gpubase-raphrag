"""
Base models and common schemas
"""
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class MetaInfo(BaseModel):
    """Response metadata"""
    request_id: str = Field(..., description="Unique request identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    processing_time_ms: Optional[int] = None


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int = Field(ge=1, description="Current page number")
    limit: int = Field(ge=1, le=100, description="Items per page")
    total_items: int = Field(ge=0, description="Total number of items")
    total_pages: int = Field(ge=0, description="Total number of pages")
    has_next: bool = False
    has_prev: bool = False


class ErrorDetail(BaseModel):
    """Error details"""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict[str, Any]] = None


class SuccessResponse(BaseModel, Generic[DataT]):
    """Standard success response wrapper"""
    success: bool = True
    data: DataT
    meta: Optional[MetaInfo] = None


class ErrorResponse(BaseModel):
    """Standard error response wrapper"""
    success: bool = False
    error: ErrorDetail
    meta: Optional[MetaInfo] = None


class PaginatedResponse(BaseModel, Generic[DataT]):
    """Paginated response wrapper"""
    success: bool = True
    data: DataT
    meta: Optional[MetaInfo] = None
    pagination: Optional[PaginationMeta] = None
