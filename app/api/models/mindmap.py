"""
Mindmap Models - Pydantic schemas for mindmap functionality
마인드맵 데이터 구조 정의
"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """마인드맵 노드 유형"""
    ROOT = "root"           # 중심 개념
    CONCEPT = "concept"     # 일반 개념
    ENTITY = "entity"       # 엔티티 (사람, 조직 등)
    TOPIC = "topic"         # 주제
    KEYWORD = "keyword"     # 키워드


class RelationType(str, Enum):
    """노드 간 관계 유형"""
    RELATES_TO = "relates_to"       # 일반적인 관련
    CONTAINS = "contains"           # 포함 관계
    CAUSES = "causes"               # 인과 관계
    DEPENDS_ON = "depends_on"       # 의존 관계
    SIMILAR_TO = "similar_to"       # 유사 관계
    OPPOSES = "opposes"             # 대립 관계
    PART_OF = "part_of"             # 부분 관계
    EXAMPLE_OF = "example_of"       # 예시 관계


class MindmapNode(BaseModel):
    """마인드맵 노드"""
    id: str = Field(..., description="노드 고유 ID")
    label: str = Field(..., description="노드 레이블 (표시 텍스트)")
    type: NodeType = Field(default=NodeType.CONCEPT, description="노드 유형")
    description: Optional[str] = Field(None, description="노드 설명")
    importance: float = Field(default=0.5, ge=0, le=1, description="중요도 (0-1)")
    source_chunks: List[str] = Field(default=[], description="관련 문서 청크 ID 목록")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="추가 메타데이터")

    # 시각화 관련 속성
    x: Optional[float] = Field(None, description="X 좌표 (시각화용)")
    y: Optional[float] = Field(None, description="Y 좌표 (시각화용)")
    color: Optional[str] = Field(None, description="노드 색상")
    size: Optional[float] = Field(None, description="노드 크기")


class MindmapEdge(BaseModel):
    """마인드맵 엣지 (관계)"""
    id: str = Field(..., description="엣지 고유 ID")
    source: str = Field(..., description="시작 노드 ID")
    target: str = Field(..., description="대상 노드 ID")
    relation: RelationType = Field(default=RelationType.RELATES_TO, description="관계 유형")
    label: Optional[str] = Field(None, description="관계 레이블")
    strength: float = Field(default=0.5, ge=0, le=1, description="관계 강도 (0-1)")
    bidirectional: bool = Field(default=False, description="양방향 관계 여부")


class MindmapData(BaseModel):
    """마인드맵 전체 데이터"""
    nodes: List[MindmapNode] = Field(default=[], description="노드 목록")
    edges: List[MindmapEdge] = Field(default=[], description="엣지 목록")
    root_id: Optional[str] = Field(None, description="루트 노드 ID")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="마인드맵 메타데이터")


class MindmapInfo(BaseModel):
    """마인드맵 정보"""
    id: str = Field(..., description="마인드맵 ID")
    title: str = Field(..., description="마인드맵 제목")
    description: Optional[str] = Field(None, description="마인드맵 설명")
    document_ids: List[str] = Field(default=[], description="관련 문서 ID 목록")
    node_count: int = Field(default=0, description="노드 수")
    edge_count: int = Field(default=0, description="엣지 수")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MindmapFull(MindmapInfo):
    """마인드맵 전체 데이터 (상세 조회용)"""
    data: MindmapData = Field(..., description="마인드맵 그래프 데이터")


# === Request Models ===

class GenerateMindmapRequest(BaseModel):
    """마인드맵 생성 요청"""
    document_ids: List[str] = Field(
        default=[],
        description="마인드맵을 생성할 문서 ID 목록 (빈 배열이면 전체 문서 사용)"
    )
    title: Optional[str] = Field(None, description="마인드맵 제목 (없으면 자동 생성)")
    max_nodes: int = Field(default=50, ge=5, le=200, description="최대 노드 수")
    depth: int = Field(default=3, ge=1, le=5, description="탐색 깊이")
    focus_topic: Optional[str] = Field(None, description="집중할 주제 (선택)")
    language: str = Field(default="auto", description="언어 설정 (auto, ko, en, ja)")


class ExpandNodeRequest(BaseModel):
    """노드 확장 요청"""
    node_id: str = Field(..., description="확장할 노드 ID")
    depth: int = Field(default=1, ge=1, le=3, description="확장 깊이")
    max_children: int = Field(default=10, ge=1, le=20, description="최대 하위 노드 수")


class QueryNodeRequest(BaseModel):
    """노드 관련 RAG 질의 요청"""
    node_id: str = Field(..., description="질의할 노드 ID")
    question: Optional[str] = Field(None, description="추가 질문 (없으면 노드 요약)")


# === Response Models ===

class GenerateMindmapResponse(BaseModel):
    """마인드맵 생성 응답"""
    mindmap: MindmapFull
    message: str = Field(default="Mindmap generated successfully")


class ExpandNodeResponse(BaseModel):
    """노드 확장 응답"""
    new_nodes: List[MindmapNode] = Field(default=[], description="새로 추가된 노드")
    new_edges: List[MindmapEdge] = Field(default=[], description="새로 추가된 엣지")
    expanded_from: str = Field(..., description="확장 시작 노드 ID")


class QueryNodeResponse(BaseModel):
    """노드 질의 응답"""
    node_id: str
    node_label: str
    answer: str = Field(..., description="RAG 답변")
    related_concepts: List[str] = Field(default=[], description="관련 개념 목록")
    sources: List[Dict[str, Any]] = Field(default=[], description="참조 소스")


class NodeDetailResponse(BaseModel):
    """노드 상세 정보 응답"""
    node: MindmapNode
    connected_nodes: List[MindmapNode] = Field(default=[], description="연결된 노드들")
    edges: List[MindmapEdge] = Field(default=[], description="관련 엣지들")
    source_content: List[Dict[str, Any]] = Field(default=[], description="원본 문서 내용")


class MindmapListResponse(BaseModel):
    """마인드맵 목록 응답"""
    mindmaps: List[MindmapInfo]
    total: int
