"""
Web Document RAG Models

docs.tmaxsoft.com 검색 결과용 Pydantic 모델
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class WebDocSource(BaseModel):
    """Web document source for RAG responses."""
    url: str = Field(..., description="docs.tmaxsoft.com 페이지 URL")
    title: str = Field(default="", description="페이지 제목")
    component: str = Field(default="", description="Antora 컴포넌트명")
    product_id: str = Field(default="", description="내부 product_id")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="정규화 유사도 (0-1)")
    content_preview: str = Field(default="", description="페이지 내용 미리보기 (200자)")
    headings: List[str] = Field(default_factory=list, description="매칭된 섹션 제목")
