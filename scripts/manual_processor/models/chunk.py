"""
청크 데이터 모델

Semantic Multimodal Chunking을 위한 향상된 청크 모델입니다.
기존 RecursiveCharacterTextSplitter의 고정 크기 청킹을 대체합니다.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
import hashlib


class ChunkType(Enum):
    """청크 유형"""
    TEXT = "text"           # 일반 텍스트
    TABLE = "table"         # 테이블 (GFM Markdown)
    IMAGE = "image"         # 이미지 설명
    MIXED = "mixed"         # 텍스트 + 테이블/이미지


class TableType(Enum):
    """테이블 유형"""
    ERROR_TABLE = "error"           # 에러코드 테이블
    PARAMETER_TABLE = "parameter"   # 설정 파라미터
    COMMAND_TABLE = "command"       # 명령어 옵션
    DATA_TABLE = "data"             # 일반 데이터


class ImageType(Enum):
    """이미지 유형"""
    DIAGRAM = "diagram"         # 아키텍처/구성 다이어그램
    FLOWCHART = "flowchart"     # 플로우차트
    SCREENSHOT = "screenshot"   # 스크린샷/UI
    TABLE_IMAGE = "table_image" # 이미지로 된 테이블
    CHART = "chart"             # 차트/그래프
    OTHER = "other"


@dataclass
class ImageChunk:
    """이미지 청크"""
    image_id: str                   # 고유 ID (hash)
    image_type: ImageType           # 이미지 유형
    description: str                # Vision LLM 생성 설명
    caption: str = ""               # 원본 캡션 (있으면)
    page_number: int = 0            # 출처 페이지
    ref_id: str = ""                # 원본 참조 (図 1.1)
    base64_data: Optional[str] = None  # 이미지 데이터 (캐싱용)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "image_type": self.image_type.value,
            "description": self.description,
            "caption": self.caption,
            "page_number": self.page_number,
            "ref_id": self.ref_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImageChunk":
        return cls(
            image_id=data.get("image_id", ""),
            image_type=ImageType(data.get("image_type", "other")),
            description=data.get("description", ""),
            caption=data.get("caption", ""),
            page_number=data.get("page_number", 0),
            ref_id=data.get("ref_id", ""),
            base64_data=data.get("base64_data"),
        )


@dataclass
class TableChunk:
    """테이블 청크"""
    table_id: str                   # 고유 ID
    table_type: TableType           # 테이블 유형
    markdown: str                   # GFM Markdown 형식
    title: str = ""                 # 테이블 제목
    row_count: int = 0              # 행 수
    col_count: int = 0              # 열 수
    page_number: int = 0            # 출처 페이지

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "table_type": self.table_type.value,
            "markdown": self.markdown,
            "title": self.title,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "page_number": self.page_number,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TableChunk":
        return cls(
            table_id=data.get("table_id", ""),
            table_type=TableType(data.get("table_type", "data")),
            markdown=data.get("markdown", ""),
            title=data.get("title", ""),
            row_count=data.get("row_count", 0),
            col_count=data.get("col_count", 0),
            page_number=data.get("page_number", 0),
        )


@dataclass
class EnhancedChunk:
    """향상된 청크 모델

    기존 고정 크기 청킹을 대체하는 의미 기반 청크입니다.
    섹션/단락 경계를 존중하고 멀티모달 컨텐츠를 지원합니다.
    """
    chunk_id: str                           # 고유 ID
    content: str                            # 청크 내용 (텍스트/마크다운)
    chunk_type: ChunkType                   # 청크 유형

    # 메타데이터
    section_title: str = ""                 # 섹션 제목
    section_level: int = 0                  # 섹션 레벨 (1-4)
    page_range: Tuple[int, int] = (0, 0)    # 페이지 범위
    char_count: int = 0                     # 문자 수

    # 관계
    parent_concept_id: str = ""             # 부모 Concept ID
    document_id: str = ""                   # 출처 Document ID
    previous_chunk_id: Optional[str] = None # 이전 청크 ID (연속성)
    next_chunk_id: Optional[str] = None     # 다음 청크 ID

    # 멀티모달 컨텐츠
    images: List[ImageChunk] = field(default_factory=list)
    tables: List[TableChunk] = field(default_factory=list)

    # 검색 메타데이터
    keywords: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)  # 추출된 엔티티

    def __post_init__(self):
        if not self.char_count:
            self.char_count = len(self.content)

    @property
    def has_images(self) -> bool:
        return len(self.images) > 0

    @property
    def has_tables(self) -> bool:
        return len(self.tables) > 0

    @property
    def is_multimodal(self) -> bool:
        return self.has_images or self.has_tables

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "chunk_type": self.chunk_type.value,
            "section_title": self.section_title,
            "section_level": self.section_level,
            "page_range": list(self.page_range),
            "char_count": self.char_count,
            "parent_concept_id": self.parent_concept_id,
            "document_id": self.document_id,
            "previous_chunk_id": self.previous_chunk_id,
            "next_chunk_id": self.next_chunk_id,
            "has_images": self.has_images,
            "has_tables": self.has_tables,
            "images": [img.to_dict() for img in self.images],
            "tables": [tbl.to_dict() for tbl in self.tables],
            "keywords": self.keywords,
            "entities": self.entities,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnhancedChunk":
        return cls(
            chunk_id=data.get("chunk_id", ""),
            content=data.get("content", ""),
            chunk_type=ChunkType(data.get("chunk_type", "text")),
            section_title=data.get("section_title", ""),
            section_level=data.get("section_level", 0),
            page_range=tuple(data.get("page_range", (0, 0))),
            char_count=data.get("char_count", 0),
            parent_concept_id=data.get("parent_concept_id", ""),
            document_id=data.get("document_id", ""),
            previous_chunk_id=data.get("previous_chunk_id"),
            next_chunk_id=data.get("next_chunk_id"),
            images=[ImageChunk.from_dict(img) for img in data.get("images", [])],
            tables=[TableChunk.from_dict(tbl) for tbl in data.get("tables", [])],
            keywords=data.get("keywords", []),
            entities=data.get("entities", []),
        )

    @staticmethod
    def generate_id(content: str, section_title: str = "", index: int = 0) -> str:
        """청크 ID 생성"""
        data = f"{section_title}:{content[:100]}:{index}"
        return hashlib.md5(data.encode()).hexdigest()[:12]


@dataclass
class ExtractedImage:
    """PDF에서 추출된 이미지 정보"""
    page_number: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    image_data: bytes                        # PNG/JPEG 바이너리
    image_hash: str                          # MD5 해시
    width: int
    height: int
    ref_id: str = ""                         # 원본 참조 (図 1.1)
    caption: str = ""                        # 캡션 (있으면)

    @staticmethod
    def compute_hash(image_data: bytes) -> str:
        """이미지 해시 계산"""
        return hashlib.md5(image_data).hexdigest()


@dataclass
class ExtractedTable:
    """PDF에서 추출된 테이블 정보"""
    page_number: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    data: List[List[str]]                    # 2D 테이블 데이터
    headers: List[str]                       # 헤더 행
    row_count: int
    col_count: int
    title: str = ""                          # 테이블 제목 (추출된 경우)
