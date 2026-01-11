"""
API Key Pydantic models for public/anonymous RAG access
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class ApiKeyCreate(BaseModel):
    """Request to create a new API key"""
    name: str = Field(..., min_length=1, max_length=255, description="Descriptive name for the API key")
    description: Optional[str] = Field(None, max_length=1000, description="Optional description")
    allowed_endpoints: List[str] = Field(
        default=["query", "agents"],
        description="Allowed endpoint prefixes"
    )
    allowed_agent_types: List[str] = Field(
        default=["auto", "rag"],
        description="Allowed agent types (auto, rag, ims, vision, code, planner)"
    )
    rate_limit_per_minute: int = Field(default=10, ge=1, le=1000, description="Requests per minute")
    rate_limit_per_hour: int = Field(default=100, ge=1, le=10000, description="Requests per hour")
    rate_limit_per_day: int = Field(default=1000, ge=1, le=100000, description="Requests per day")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Days until expiration (None = never)")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Public Website Widget",
                "description": "API key for embedded RAG widget on public website",
                "allowed_endpoints": ["query", "agents"],
                "allowed_agent_types": ["auto", "rag"],
                "rate_limit_per_minute": 10,
                "rate_limit_per_hour": 100,
                "rate_limit_per_day": 1000,
                "expires_in_days": 90
            }
        }


class ApiKeyUpdate(BaseModel):
    """Request to update an API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    allowed_endpoints: Optional[List[str]] = None
    allowed_agent_types: Optional[List[str]] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=1000)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=10000)
    rate_limit_per_day: Optional[int] = Field(None, ge=1, le=100000)
    is_active: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    """API key information (without the actual key)"""
    id: UUID
    name: str
    description: Optional[str]
    key_prefix: str  # First 8 chars for identification
    owner_id: Optional[UUID]
    allowed_endpoints: List[str]
    allowed_agent_types: List[str]
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    rate_limit_per_day: int
    total_requests: int
    total_tokens_used: int
    last_used_at: Optional[datetime]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ApiKeyCreatedResponse(BaseModel):
    """Response when creating a new API key (includes the full key - shown only once)"""
    id: UUID
    name: str
    key: str  # Full API key - ONLY shown at creation time
    key_prefix: str
    message: str = "Save this API key securely. It will not be shown again."

    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Public Website Widget",
                "key": "kms_abc12345xyz67890abcdef1234567890",
                "key_prefix": "kms_abc1",
                "message": "Save this API key securely. It will not be shown again."
            }
        }


class ApiKeyListResponse(BaseModel):
    """List of API keys"""
    items: List[ApiKeyResponse]
    total: int
    page: int
    page_size: int


class ApiKeyUsageStats(BaseModel):
    """Usage statistics for an API key"""
    api_key_id: UUID
    period: str  # "hour", "day", "week", "month"
    total_requests: int
    total_tokens: int
    avg_response_time_ms: float
    error_count: int
    endpoints_breakdown: dict  # endpoint -> count
    agent_types_breakdown: dict  # agent_type -> count


class ApiKeyValidationResult(BaseModel):
    """Result of API key validation (internal use)"""
    is_valid: bool
    api_key_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    allowed_endpoints: List[str] = []
    allowed_agent_types: List[str] = []
    rate_limit_per_minute: int = 0
    rate_limit_per_hour: int = 0
    rate_limit_per_day: int = 0
    error: Optional[str] = None


class RateLimitStatus(BaseModel):
    """Current rate limit status"""
    minute_remaining: int
    minute_reset_at: datetime
    hour_remaining: int
    hour_reset_at: datetime
    day_remaining: int
    day_reset_at: datetime
