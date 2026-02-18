"""Chat API request/response schemas for Legacy Modernization AI Assistant."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SystemType(str, Enum):
    """Target system for chat routing."""
    HOST = "host"
    OPENFRAME = "openframe"
    ALL = "all"


class AnalysisContext(BaseModel):
    """Optional context from an active analysis session."""
    analysis_id: Optional[str] = Field(None, description="Active analysis session ID")
    file_name: Optional[str] = Field(None, description="Source file name")
    asset_type: Optional[str] = Field(None, description="Asset type: cobol, jcl, map, asm")
    source_code_snippet: Optional[str] = Field(
        None, max_length=2000, description="First 2000 chars of source code",
    )
    target_product: Optional[str] = Field(None, description="Target OpenFrame product")


class ModernizationChatRequest(BaseModel):
    """Request body for modernization chat endpoint."""
    message: str = Field(..., min_length=1, max_length=8000, description="User message")
    system_type: SystemType = Field(default=SystemType.HOST, description="Target system")
    language: str = Field(default="ja", description="Response language (ja, en, ko)")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for history")
    analysis_context: Optional[AnalysisContext] = Field(
        None, description="Context from active analysis session",
    )
