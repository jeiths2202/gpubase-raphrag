"""품질 검사 데이터 모델

Summary Quality Improvement 기능을 위한 데이터 구조 정의.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
import json


class QualityIssueType(Enum):
    """품질 이슈 타입"""
    INCOMPLETE_DESCRIPTION = "incomplete_description"
    DUPLICATE_ENTRY = "duplicate_entry"
    TYPE_MISCLASSIFICATION = "type_misclassification"


@dataclass
class IncompleteItem:
    """불완전한 설명 항목"""
    name: str
    description: str           # 현재 (불완전한) 설명
    source_file: str           # 원본 마크다운 파일
    item_type: str             # command, concept, config 등
    pdf_source: Optional[str] = None  # 원본 PDF
    page: Optional[int] = None        # PDF 페이지
    suggested_fix: str = ""    # 보완 제안
    pattern_matched: str = ""  # 매칭된 불완전 패턴

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "source_file": self.source_file,
            "item_type": self.item_type,
            "pdf_source": self.pdf_source,
            "page": self.page,
            "suggested_fix": self.suggested_fix,
            "pattern_matched": self.pattern_matched,
        }


@dataclass
class DuplicateGroup:
    """중복 항목 그룹"""
    name: str
    items: List[dict] = field(default_factory=list)  # 중복된 항목들
    best_item: Optional[dict] = None  # 가장 완전한 항목
    merge_strategy: str = "keep_best"  # "keep_best" | "merge_all"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "count": len(self.items),
            "items": self.items,
            "best_item": self.best_item,
            "merge_strategy": self.merge_strategy,
        }


@dataclass
class MisclassifiedItem:
    """분류 오류 항목"""
    name: str
    current_type: str          # 현재 타입 (잘못된)
    suggested_type: str        # 제안 타입
    pattern_matched: str       # 매칭된 패턴
    confidence: float = 1.0    # 신뢰도 (0-1)
    source_file: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "current_type": self.current_type,
            "suggested_type": self.suggested_type,
            "pattern_matched": self.pattern_matched,
            "confidence": self.confidence,
            "source_file": self.source_file,
        }


@dataclass
class QualityReport:
    """품질 검사 리포트"""
    total_items: int
    incomplete_items: List[IncompleteItem] = field(default_factory=list)
    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)
    misclassified_items: List[MisclassifiedItem] = field(default_factory=list)
    scan_timestamp: str = ""
    summaries_dir: str = ""

    @property
    def incomplete_count(self) -> int:
        return len(self.incomplete_items)

    @property
    def duplicate_count(self) -> int:
        """중복 항목 수 (원본 제외)"""
        return sum(len(g.items) - 1 for g in self.duplicate_groups)

    @property
    def misclassified_count(self) -> int:
        return len(self.misclassified_items)

    @property
    def total_issues(self) -> int:
        return self.incomplete_count + self.duplicate_count + self.misclassified_count

    @property
    def quality_score(self) -> float:
        """품질 점수 (0-100)"""
        if self.total_items == 0:
            return 100.0
        issues = self.total_issues
        return max(0, (1 - issues / self.total_items) * 100)

    def to_dict(self) -> dict:
        """JSON 직렬화"""
        return {
            "summary": {
                "total_items": self.total_items,
                "incomplete_count": self.incomplete_count,
                "duplicate_count": self.duplicate_count,
                "misclassified_count": self.misclassified_count,
                "total_issues": self.total_issues,
                "quality_score": round(self.quality_score, 2),
            },
            "scan_timestamp": self.scan_timestamp,
            "summaries_dir": self.summaries_dir,
            "incomplete_items": [item.to_dict() for item in self.incomplete_items],
            "duplicate_groups": [group.to_dict() for group in self.duplicate_groups],
            "misclassified_items": [item.to_dict() for item in self.misclassified_items],
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 문자열로 변환"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str) -> None:
        """파일로 저장"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, data: dict) -> "QualityReport":
        """dict에서 생성"""
        summary = data.get("summary", {})
        report = cls(
            total_items=summary.get("total_items", 0),
            scan_timestamp=data.get("scan_timestamp", ""),
            summaries_dir=data.get("summaries_dir", ""),
        )

        # IncompleteItem 복원
        for item_data in data.get("incomplete_items", []):
            report.incomplete_items.append(IncompleteItem(
                name=item_data["name"],
                description=item_data["description"],
                source_file=item_data["source_file"],
                item_type=item_data.get("item_type", ""),
                pdf_source=item_data.get("pdf_source"),
                page=item_data.get("page"),
                suggested_fix=item_data.get("suggested_fix", ""),
                pattern_matched=item_data.get("pattern_matched", ""),
            ))

        # DuplicateGroup 복원
        for group_data in data.get("duplicate_groups", []):
            report.duplicate_groups.append(DuplicateGroup(
                name=group_data["name"],
                items=group_data.get("items", []),
                best_item=group_data.get("best_item"),
                merge_strategy=group_data.get("merge_strategy", "keep_best"),
            ))

        # MisclassifiedItem 복원
        for item_data in data.get("misclassified_items", []):
            report.misclassified_items.append(MisclassifiedItem(
                name=item_data["name"],
                current_type=item_data["current_type"],
                suggested_type=item_data["suggested_type"],
                pattern_matched=item_data["pattern_matched"],
                confidence=item_data.get("confidence", 1.0),
                source_file=item_data.get("source_file", ""),
            ))

        return report

    @classmethod
    def load(cls, path: str) -> "QualityReport":
        """파일에서 로드"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class EnhancementResult:
    """품질 개선 결과"""
    fixed_incomplete: int = 0
    merged_duplicates: int = 0
    reclassified_items: int = 0
    failed_items: List[str] = field(default_factory=list)
    updated_files: List[str] = field(default_factory=list)

    @property
    def total_fixed(self) -> int:
        return self.fixed_incomplete + self.merged_duplicates + self.reclassified_items

    def to_dict(self) -> dict:
        return {
            "fixed_incomplete": self.fixed_incomplete,
            "merged_duplicates": self.merged_duplicates,
            "reclassified_items": self.reclassified_items,
            "total_fixed": self.total_fixed,
            "failed_items": self.failed_items,
            "updated_files": self.updated_files,
        }
