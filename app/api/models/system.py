"""
System Status Models
시스템 상태 정보 모델
"""
from datetime import datetime, timezone
from typing import Optional, Literal
from pydantic import BaseModel, Field


class GPUStatus(BaseModel):
    """GPU 상태 정보"""
    name: str = Field(..., description="GPU 모델명")
    memory_used: float = Field(..., description="사용 중인 메모리 (GB)")
    memory_total: float = Field(..., description="전체 메모리 (GB)")
    utilization: int = Field(..., ge=0, le=100, description="GPU 사용률 (%)")
    temperature: int = Field(..., description="GPU 온도 (°C)")
    status: Literal["online", "offline", "warning"] = Field(..., description="GPU 상태")


class ModelStatus(BaseModel):
    """AI 모델 상태 정보"""
    name: str = Field(..., description="모델명")
    version: str = Field(..., description="모델 버전")
    status: Literal["loaded", "loading", "error"] = Field(..., description="모델 상태")
    inference_time_ms: float = Field(..., description="평균 추론 시간 (ms)")


class IndexStatus(BaseModel):
    """벡터 인덱스 상태 정보"""
    total_documents: int = Field(..., ge=0, description="전체 문서 수")
    total_chunks: int = Field(..., ge=0, description="전체 청크 수")
    last_updated: datetime = Field(..., description="마지막 업데이트 시간")
    status: Literal["ready", "indexing", "error"] = Field(..., description="인덱스 상태")


class Neo4jStatus(BaseModel):
    """Neo4j 그래프 DB 상태 정보"""
    status: Literal["connected", "disconnected"] = Field(..., description="연결 상태")
    node_count: int = Field(..., ge=0, description="노드 수")
    relationship_count: int = Field(..., ge=0, description="관계 수")


class SystemStatusResponse(BaseModel):
    """시스템 전체 상태 응답"""
    gpu: GPUStatus
    model: ModelStatus
    index: IndexStatus
    neo4j: Neo4jStatus
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="조회 시간")


class KnowledgeSource(BaseModel):
    """지식 소스 정보"""
    id: str = Field(..., description="소스 ID")
    name: str = Field(..., description="소스 이름")
    type: Literal["pdf", "docx", "web", "api", "database"] = Field(..., description="소스 유형")
    document_count: int = Field(..., ge=0, description="문서 수")
    last_sync: str = Field(..., description="마지막 동기화 시간")
    status: Literal["active", "syncing", "error"] = Field(..., description="소스 상태")


class KnowledgeSourcesResponse(BaseModel):
    """지식 소스 목록 응답"""
    sources: list[KnowledgeSource]
    total: int = Field(..., ge=0, description="전체 소스 수")
