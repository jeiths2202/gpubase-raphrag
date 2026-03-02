"""
PDF 문서 계층 구조 데이터 모델

Two-Stage Retrieval을 위한 계층적 구조 데이터를 표현합니다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any


class NodeType(Enum):
    """계층 노드 타입"""
    CHAPTER = "chapter"       # Level 1: 第1章, Chapter
    SECTION = "section"       # Level 2: 1.1., A.1.
    SUBSECTION = "subsection" # Level 3: 1.1.1.
    PARAGRAPH = "paragraph"   # Level 4: 본문/글머리
    APPENDIX = "appendix"     # 付録, Appendix


@dataclass
class ImageReference:
    """이미지/테이블 참조 정보"""
    ref_type: str           # "figure" | "table"
    ref_id: str             # "図 1.1", "表 A.1"
    caption: str            # 캡션 텍스트
    page_number: int        # 페이지 번호
    context: str = ""       # 주변 문맥 (100자 내외)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "caption": self.caption,
            "page_number": self.page_number,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImageReference":
        """딕셔너리에서 생성"""
        return cls(
            ref_type=data.get("ref_type", ""),
            ref_id=data.get("ref_id", ""),
            caption=data.get("caption", ""),
            page_number=data.get("page_number", 0),
            context=data.get("context", ""),
        )


@dataclass
class HierarchyNode:
    """계층 구조 노드"""
    id: str                              # 고유 ID (예: "ch1", "ch1.s2", "ch1.s2.ss3")
    level: int                           # 계층 레벨 (1-4)
    node_type: NodeType                  # 노드 타입
    title: str                           # 제목
    page_start: int                      # 시작 페이지
    page_end: int = 0                    # 종료 페이지 (계산 후 설정)
    summary: str = ""                    # 요약 (100-300자)
    keywords: List[str] = field(default_factory=list)  # 키워드 (3-7개)
    has_images: bool = False             # 이미지 포함 여부
    images: List[ImageReference] = field(default_factory=list)  # 이미지 참조 목록
    parent_id: Optional[str] = None      # 부모 노드 ID
    children: List["HierarchyNode"] = field(default_factory=list)  # 자식 노드
    raw_text: str = ""                   # 원문 텍스트 (요약 생성용)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (재귀적)"""
        return {
            "id": self.id,
            "level": self.level,
            "node_type": self.node_type.value,
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "summary": self.summary,
            "keywords": self.keywords,
            "has_images": self.has_images,
            "images": [img.to_dict() for img in self.images],
            "parent_id": self.parent_id,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HierarchyNode":
        """딕셔너리에서 생성 (재귀적)"""
        return cls(
            id=data.get("id", ""),
            level=data.get("level", 1),
            node_type=NodeType(data.get("node_type", "chapter")),
            title=data.get("title", ""),
            page_start=data.get("page_start", 0),
            page_end=data.get("page_end", 0),
            summary=data.get("summary", ""),
            keywords=data.get("keywords", []),
            has_images=data.get("has_images", False),
            images=[ImageReference.from_dict(img) for img in data.get("images", [])],
            parent_id=data.get("parent_id"),
            children=[cls.from_dict(child) for child in data.get("children", [])],
        )

    def count_nodes(self) -> int:
        """노드 및 자식 노드 수 계산"""
        count = 1
        for child in self.children:
            count += child.count_nodes()
        return count

    def find_by_id(self, node_id: str) -> Optional["HierarchyNode"]:
        """ID로 노드 검색 (재귀적)"""
        if self.id == node_id:
            return self
        for child in self.children:
            found = child.find_by_id(node_id)
            if found:
                return found
        return None


@dataclass
class DocumentStructure:
    """문서 전체 구조"""
    # 메타데이터
    title: str                           # 문서 제목
    file_name: str                       # 원본 파일명
    file_path: Optional[Path] = None     # 원본 파일 경로
    version: str = ""                    # 문서 버전
    total_pages: int = 0                 # 총 페이지 수
    language: str = "ja"                 # 언어 (ja, en, ko)

    # 계층 구조
    hierarchy: List[HierarchyNode] = field(default_factory=list)  # 최상위 노드 목록

    # 이미지 인덱스 (모든 이미지 참조의 플랫 리스트)
    images_index: List[ImageReference] = field(default_factory=list)

    # 처리 로그
    processing_log: Dict[str, Any] = field(default_factory=dict)

    # 검증 결과
    validation: Dict[str, Any] = field(default_factory=dict)

    # 생성 정보
    generated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "title": self.title,
            "file_name": self.file_name,
            "file_path": str(self.file_path) if self.file_path else None,
            "version": self.version,
            "total_pages": self.total_pages,
            "language": self.language,
            "hierarchy": [node.to_dict() for node in self.hierarchy],
            "images_index": [img.to_dict() for img in self.images_index],
            "processing_log": self.processing_log,
            "validation": self.validation,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentStructure":
        """딕셔너리에서 생성"""
        generated_at = None
        if data.get("generated_at"):
            try:
                generated_at = datetime.fromisoformat(data["generated_at"])
            except (ValueError, TypeError):
                pass

        return cls(
            title=data.get("title", ""),
            file_name=data.get("file_name", ""),
            file_path=Path(data["file_path"]) if data.get("file_path") else None,
            version=data.get("version", ""),
            total_pages=data.get("total_pages", 0),
            language=data.get("language", "ja"),
            hierarchy=[HierarchyNode.from_dict(node) for node in data.get("hierarchy", [])],
            images_index=[ImageReference.from_dict(img) for img in data.get("images_index", [])],
            processing_log=data.get("processing_log", {}),
            validation=data.get("validation", {}),
            generated_at=generated_at,
        )

    def count_all_nodes(self) -> int:
        """전체 노드 수 계산"""
        count = 0
        for node in self.hierarchy:
            count += node.count_nodes()
        return count

    def find_node_by_id(self, node_id: str) -> Optional[HierarchyNode]:
        """ID로 노드 검색"""
        for node in self.hierarchy:
            found = node.find_by_id(node_id)
            if found:
                return found
        return None

    def find_node_by_title(self, title: str, exact: bool = False) -> Optional[HierarchyNode]:
        """제목으로 노드 검색"""
        def search_recursive(nodes: List[HierarchyNode]) -> Optional[HierarchyNode]:
            for node in nodes:
                if exact:
                    if node.title == title:
                        return node
                else:
                    if title.lower() in node.title.lower():
                        return node
                found = search_recursive(node.children)
                if found:
                    return found
            return None

        return search_recursive(self.hierarchy)

    def get_nodes_at_level(self, level: int) -> List[HierarchyNode]:
        """특정 레벨의 모든 노드 반환"""
        results = []

        def collect_recursive(nodes: List[HierarchyNode]):
            for node in nodes:
                if node.level == level:
                    results.append(node)
                collect_recursive(node.children)

        collect_recursive(self.hierarchy)
        return results

    def get_images_for_page(self, page: int) -> List[ImageReference]:
        """특정 페이지의 이미지 참조 반환"""
        return [img for img in self.images_index if img.page_number == page]

    def get_images_for_range(self, start_page: int, end_page: int) -> List[ImageReference]:
        """페이지 범위의 이미지 참조 반환"""
        return [
            img for img in self.images_index
            if start_page <= img.page_number <= end_page
        ]

    def get_all_keywords(self) -> List[str]:
        """모든 노드의 키워드 수집"""
        keywords = set()

        def collect_recursive(nodes: List[HierarchyNode]):
            for node in nodes:
                keywords.update(node.keywords)
                collect_recursive(node.children)

        collect_recursive(self.hierarchy)
        return sorted(keywords)

    def is_valid(self) -> bool:
        """검증 결과 확인"""
        return self.validation.get("valid", False)

    def get_coverage_ratio(self) -> float:
        """TOC 커버리지 비율 반환"""
        return self.validation.get("coverage_ratio", 0.0)
