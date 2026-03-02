"""
Pydantic models for metadata configuration.
Used for API request/response validation.
"""
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


# ==================== Domain Glossary ====================

class GlossaryTermBase(BaseModel):
    """Base model for glossary term."""
    term: str = Field(..., min_length=1, max_length=100,
                      description="용어 (대문자로 저장)", example="TJES")
    full_name: str = Field(..., min_length=1, max_length=255,
                          description="전체 명칭", example="Tmax Job Entry Subsystem")
    description: Optional[str] = Field(None, description="설명")
    category: str = Field("system", description="카테고리",
                         example="system")
    translations: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="다국어 번역 (ko, ja, en)",
        example={"ko": "배치 작업 관리", "ja": "バッチジョブ管理"}
    )
    equivalent_to: Optional[str] = Field(
        None,
        description="IBM/메인프레임 동등 용어",
        example="JES2/JES3"
    )


class GlossaryTermCreate(GlossaryTermBase):
    """Request model for creating glossary term."""
    pass


class GlossaryTermUpdate(BaseModel):
    """Request model for updating glossary term."""
    full_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    translations: Optional[Dict[str, str]] = None
    equivalent_to: Optional[str] = None
    active: Optional[bool] = None


class GlossaryTermResponse(GlossaryTermBase):
    """Response model for glossary term."""
    id: UUID
    active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Document Mappings ====================

class DocumentMappingBase(BaseModel):
    """Base model for document mapping."""
    keyword: str = Field(..., min_length=1, max_length=100,
                        description="검색 키워드", example="ADRDSSU")
    document_pattern: str = Field(..., min_length=1, max_length=255,
                                  description="문서 파일명 패턴", example="Utility")
    category: str = Field("product", description="카테고리",
                         example="utility")
    priority: int = Field(100, ge=1, le=1000,
                         description="매칭 우선순위 (낮을수록 우선)")


class DocumentMappingCreate(DocumentMappingBase):
    """Request model for creating document mapping."""
    pass


class DocumentMappingResponse(DocumentMappingBase):
    """Response model for document mapping."""
    id: UUID
    active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Error Code Ranges ====================

class ErrorCodeRangeBase(BaseModel):
    """Base model for error code range."""
    module: str = Field(..., min_length=1, max_length=50,
                       description="모듈명", example="BASE")
    range_start: int = Field(..., ge=0,
                            description="범위 시작", example=5000)
    range_end: int = Field(..., ge=0,
                          description="범위 끝", example=5999)
    file_path: str = Field(..., min_length=1, max_length=255,
                          description="요약본 파일 경로", example="BASE-5000.md")
    category: Optional[str] = Field(None, description="에러 카테고리",
                                   example="allocation")
    description: Optional[str] = Field(None, description="범위 설명")


class ErrorCodeRangeCreate(ErrorCodeRangeBase):
    """Request model for creating error code range."""
    pass


class ErrorCodeRangeResponse(ErrorCodeRangeBase):
    """Response model for error code range."""
    id: UUID
    active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== Synonyms ====================

class SynonymBase(BaseModel):
    """Base model for synonym."""
    base_term: str = Field(..., min_length=1, max_length=255,
                          description="기본 용어", example="DATASET")
    synonym: str = Field(..., min_length=1, max_length=255,
                        description="동의어", example="データセット")
    language: str = Field(..., min_length=2, max_length=10,
                         description="언어 코드", example="ja")
    domain: str = Field("general", description="도메인",
                       example="technical")
    confidence: float = Field(1.0, ge=0.0, le=1.0,
                             description="신뢰도 (0.0-1.0)")


class SynonymCreate(SynonymBase):
    """Request model for creating synonym."""
    pass


class SynonymResponse(SynonymBase):
    """Response model for synonym."""
    id: UUID
    active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Visual Keywords ====================

class VisualKeywordBase(BaseModel):
    """Base model for visual keyword."""
    keyword: str = Field(..., min_length=1, max_length=100,
                        description="시각 키워드", example="プロセス図")
    language: str = Field(..., min_length=2, max_length=10,
                         description="언어 코드", example="ja")
    category: str = Field("diagram", description="카테고리",
                         example="diagram")
    weight: float = Field(1.0, ge=0.0, le=2.0,
                         description="가중치 (Vision LLM 라우팅용)")


class VisualKeywordCreate(VisualKeywordBase):
    """Request model for creating visual keyword."""
    pass


class VisualKeywordResponse(VisualKeywordBase):
    """Response model for visual keyword."""
    id: UUID
    active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Bulk Operations ====================

class BulkGlossaryRequest(BaseModel):
    """Request model for bulk glossary insert."""
    terms: List[GlossaryTermCreate]


class BulkMappingsRequest(BaseModel):
    """Request model for bulk mappings insert."""
    mappings: List[DocumentMappingCreate]


class BulkErrorRangesRequest(BaseModel):
    """Request model for bulk error ranges insert."""
    ranges: List[ErrorCodeRangeCreate]


class BulkSynonymsRequest(BaseModel):
    """Request model for bulk synonyms insert."""
    synonyms: List[SynonymCreate]


class BulkVisualKeywordsRequest(BaseModel):
    """Request model for bulk visual keywords insert."""
    keywords: List[VisualKeywordCreate]


class BulkInsertResponse(BaseModel):
    """Response model for bulk insert operations."""
    inserted_count: int
    message: str


# ==================== Cache Stats ====================

class CacheStatsResponse(BaseModel):
    """Response model for cache statistics."""
    cached_keys: List[str]
    cache_sizes: Dict[str, int]
    cache_ages_seconds: Dict[str, int]
    ttl_seconds: int
