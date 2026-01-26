"""
Settings Pydantic models
"""
from typing import Optional
from pydantic import BaseModel, Field


class RAGSettings(BaseModel):
    """RAG system settings"""
    default_strategy: str = "auto"
    top_k: int = Field(default=5, ge=1, le=20)
    vector_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    chunk_size: int = Field(default=1000, ge=100, le=5000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)


class LLMSettings(BaseModel):
    """LLM settings"""
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=100, le=8192)


class UISettings(BaseModel):
    """UI settings"""
    language: str = "auto"
    theme: str = "dark"
    show_sources: bool = True


class SystemSettings(BaseModel):
    """Complete system settings"""
    rag: RAGSettings = Field(default_factory=RAGSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    ui: UISettings = Field(default_factory=UISettings)


class SettingsUpdate(BaseModel):
    """Settings update request (partial)"""
    rag: Optional[RAGSettings] = None
    llm: Optional[LLMSettings] = None
    ui: Optional[UISettings] = None


class SettingsUpdateResponse(BaseModel):
    """Settings update response"""
    message: str
    updated_fields: list[str] = Field(default_factory=list)
