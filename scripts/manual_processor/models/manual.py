"""매뉴얼 메타데이터 모델"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class TOCItem:
    """목차 항목"""
    level: int
    title: str
    page: int


@dataclass
class ManualMetadata:
    """매뉴얼 메타데이터"""
    # 파일 정보
    file_path: Path
    file_name: str
    file_size: int

    # 파싱된 정보
    prefix: str = ""  # OF, OFManager, Tibero, Tmax
    component: str = ""  # Base, Batch, Common, TACF 등
    platform: Optional[str] = None  # XSP, MSP, MVS
    version: str = ""  # 7.3, 7.1 등
    guide_type: str = ""  # Error-Reference-Guide, TJES-Guide 등
    doc_version: str = ""  # v3.2.1
    language: str = ""  # ja, jp, en

    # PDF 메타데이터
    page_count: int = 0
    title: str = ""
    author: str = ""
    creation_date: Optional[datetime] = None

    # 목차
    toc: List[TOCItem] = field(default_factory=list)

    @property
    def product_key(self) -> str:
        """제품 키 반환 (예: openframe-batch-xsp)"""
        parts = [self.component.lower()]
        if self.platform:
            parts.append(self.platform.lower())
        return "-".join(parts)

    @property
    def is_error_guide(self) -> bool:
        """에러 참조 가이드 여부"""
        return "Error" in self.guide_type

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "file_path": str(self.file_path),
            "file_name": self.file_name,
            "prefix": self.prefix,
            "component": self.component,
            "platform": self.platform,
            "version": self.version,
            "guide_type": self.guide_type,
            "doc_version": self.doc_version,
            "language": self.language,
            "page_count": self.page_count,
            "title": self.title,
        }


@dataclass
class ManualContent:
    """매뉴얼 콘텐츠"""
    metadata: ManualMetadata
    pages: List[str] = field(default_factory=list)  # 페이지별 텍스트
    full_text: str = ""  # 전체 텍스트

    def get_page_range(self, start: int, end: int) -> str:
        """특정 페이지 범위의 텍스트 반환"""
        if not self.pages:
            return ""
        start_idx = max(0, start - 1)
        end_idx = min(len(self.pages), end)
        return "\n\n".join(self.pages[start_idx:end_idx])

    def get_section_by_toc(self, toc_item: TOCItem) -> str:
        """목차 항목에 해당하는 섹션 텍스트 반환"""
        toc = self.metadata.toc
        current_idx = toc.index(toc_item)

        # 다음 같은 레벨 또는 상위 레벨 항목 찾기
        end_page = self.metadata.page_count
        for i in range(current_idx + 1, len(toc)):
            if toc[i].level <= toc_item.level:
                end_page = toc[i].page - 1
                break

        return self.get_page_range(toc_item.page, end_page)
