"""
IMS Semantic Search Models

자연어 질의 기반 IMS 시맨틱 검색 및 채팅 서비스용 Pydantic 모델.
BGE-M3 IR 모델을 통한 임베딩 검색 전용.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ============================================================================
# Issue Content (텍스트 파일 파싱 결과)
# ============================================================================

class IssueMetadata(BaseModel):
    """IMS 이슈 메타데이터 (텍스트 파일 헤더)"""
    ims_id: str = Field(..., description="IMS 이슈 번호", examples=["341013"])
    product: str = Field("", description="제품명")
    version: str = Field("", description="버전")
    module: str = Field("", description="모듈")
    category: str = Field("", description="카테고리")
    subject: str = Field("", description="제목")
    customer: str = Field("", description="고객사")
    status: str = Field("", description="상태")
    date: str = Field("", description="등록일")


class ActionLogEntry(BaseModel):
    """조치 이력 항목"""
    index: int = Field(..., description="순번 (1부터)")
    content: str = Field(..., description="조치 내용")


class IssueContent(BaseModel):
    """완전한 IMS 이슈 내용 (텍스트 파일 파싱 결과)"""
    metadata: IssueMetadata
    description: str = Field("", description="상세 내용")
    action_log: List[ActionLogEntry] = Field(default_factory=list)
    raw_text: str = Field("", description="원본 텍스트 전문")
    referenced_ims_ids: List[str] = Field(default_factory=list, description="참조된 IMS 이슈 번호")
    referenced_urls: List[str] = Field(default_factory=list, description="참조된 URL")
    has_attachment_references: bool = Field(False, description="첨부파일 참조 여부")


# ============================================================================
# Search
# ============================================================================

class IMSSearchRequest(BaseModel):
    """시맨틱 검색 요청"""
    query: str = Field(..., min_length=2, description="자연어 검색 쿼리")
    limit: int = Field(10, ge=1, le=50, description="최대 결과 수")
    product_filter: Optional[str] = Field(None, description="제품 필터 (optional)")


class IMSSearchResult(BaseModel):
    """검색 결과 단건"""
    ims_id: str
    score: float = Field(..., description="유사도 점수")
    subject: str = Field("")
    product: str = Field("")
    status: str = Field("")
    date: str = Field("")
    snippet: str = Field("", description="매칭 스니펫")


class IMSSearchResponse(BaseModel):
    """검색 응답"""
    query: str
    results: List[IMSSearchResult]
    total: int
    search_time_ms: float


# ============================================================================
# Related Issues
# ============================================================================

class RelatedIssue(BaseModel):
    """관련 이슈"""
    ims_id: str
    relation_type: str = Field(..., description="관계 유형: ims_reference, url_reference, action_reference")
    subject: str = Field("")
    product: str = Field("")
    status: str = Field("")
    context: str = Field("", description="참조 컨텍스트")


class RelatedIssuesResponse(BaseModel):
    """관련 이슈 응답"""
    ims_id: str
    related_issues: List[RelatedIssue]
    total: int


# ============================================================================
# Semantic Chat
# ============================================================================

class IMSSemanticChatRequest(BaseModel):
    """시맨틱 검색 기반 채팅 요청 (issue_ids 불필요)"""
    query: str = Field(..., min_length=2, description="자연어 질문")
    conversation_id: Optional[str] = Field(None, description="기존 대화 ID")
    search_limit: int = Field(5, ge=1, le=20, description="검색할 이슈 수")
    include_related: bool = Field(True, description="관련 이슈 자동 포함")
    language: str = Field("auto", description="응답 언어: auto, ko, ja, en")


# ============================================================================
# Summary
# ============================================================================

class IMSSummaryRequest(BaseModel):
    """이슈 요약 요청"""
    ims_id: str = Field(..., description="이슈 번호")
    language: str = Field("auto", description="요약 언어")
    include_action_log: bool = Field(True, description="조치 이력 포함 여부")


class IMSSummaryResponse(BaseModel):
    """이슈 요약 응답"""
    ims_id: str
    subject: str
    summary: str
    key_points: List[str] = Field(default_factory=list)
    resolution: Optional[str] = None
    related_ims_ids: List[str] = Field(default_factory=list)


# ============================================================================
# Knowledge Creation
# ============================================================================

class IMSKnowledgeCreateRequest(BaseModel):
    """이슈 기반 지식 생성 요청"""
    ims_ids: List[str] = Field(..., min_length=1, description="소스 이슈 번호 목록")
    title: str = Field(..., min_length=5, description="지식 문서 제목")
    language: str = Field("auto", description="생성 언어")


class IMSKnowledgeCreateResponse(BaseModel):
    """지식 생성 응답"""
    title: str
    content: str = Field(..., description="생성된 지식 문서 (Markdown)")
    source_issues: List[str]
    created_at: datetime
