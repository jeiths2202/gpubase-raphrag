"""
Prompt Configuration Models

Pydantic models for prompt management system.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class PromptCategory(str, Enum):
    """Prompt categories"""
    AGENT = "agent"
    MIDDLEWARE = "middleware"
    SYSTEM = "system"
    PERSONA = "persona"
    DOMAIN = "domain"


class PromptLanguage(str, Enum):
    """Supported languages"""
    EN = "en"
    KO = "ko"
    JA = "ja"


class PromptSummary(BaseModel):
    """Prompt list item for UI display"""
    prompt_id: str
    name: str
    category: PromptCategory
    language: PromptLanguage = PromptLanguage.EN
    is_readonly: bool = False
    updated_at: Optional[datetime] = None
    content_preview: str = Field(
        default="",
        description="First 100 chars of content"
    )


class PromptDetail(BaseModel):
    """Full prompt detail including content"""
    id: UUID
    prompt_id: str
    name: str
    description: Optional[str] = None
    category: PromptCategory
    language: PromptLanguage = PromptLanguage.EN
    content: str
    is_readonly: bool = False
    source_file: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[UUID] = None
    version_count: int = 0


class PromptUpdateRequest(BaseModel):
    """Request to update prompt content"""
    content: str = Field(..., min_length=1, max_length=50000)
    reason: Optional[str] = Field(None, max_length=500)


class PromptHistory(BaseModel):
    """Version history item"""
    id: UUID
    version_number: int
    content: str
    change_reason: Optional[str] = None
    changed_at: datetime
    changed_by: Optional[UUID] = None


class PromptTestRequest(BaseModel):
    """Request to test prompt rendering"""
    test_query: str = Field(..., min_length=1, max_length=1000)
    variables: dict = Field(default_factory=dict)


class PromptTestResult(BaseModel):
    """Test result with rendered prompt"""
    success: bool
    rendered_prompt: str
    token_count: int
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class SyncResult(BaseModel):
    """File sync result"""
    synced: int
    skipped: int
    errors: List[str] = Field(default_factory=list)


# Database model (internal use)
class PromptConfigDB(BaseModel):
    """Database row representation"""
    id: UUID
    prompt_id: str
    language: str = "en"
    category: str
    name: str
    description: Optional[str] = None
    content: str
    is_readonly: bool = False
    source_file: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[UUID] = None

    class Config:
        from_attributes = True


class PromptHistoryDB(BaseModel):
    """Database row for history"""
    id: UUID
    prompt_id: str
    language: str = "en"
    version_number: int
    content: str
    change_reason: Optional[str] = None
    changed_at: datetime
    changed_by: Optional[UUID] = None

    class Config:
        from_attributes = True
