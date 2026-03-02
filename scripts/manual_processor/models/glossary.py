"""용어 사전 모델"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class GlossaryTerm:
    """용어 정의"""
    term: str  # TJES
    full_name: str = ""  # Tmax Job Entry Subsystem
    product: str = ""  # OpenFrame Batch
    description: str = ""  # 説明
    features: List[str] = field(default_factory=list)  # 주요 기능
    related_terms: List[str] = field(default_factory=list)  # 관련 용어
    source_files: List[str] = field(default_factory=list)  # 참조 매뉴얼
    components: List[str] = field(default_factory=list)  # 하위 컴포넌트

    @property
    def first_letter(self) -> str:
        """첫 글자 (파일 분류용)"""
        if self.term:
            return self.term[0].upper()
        return "OTHER"

    @property
    def search_keys(self) -> List[str]:
        """검색 키워드 목록"""
        keys = [self.term, self.term.lower(), self.term.upper()]
        if self.full_name:
            keys.append(self.full_name)
            # 약어 생성 (Tmax Job Entry Subsystem -> TJES)
            words = self.full_name.split()
            if len(words) > 1:
                abbr = "".join(w[0].upper() for w in words if w[0].isupper() or w[0].isalpha())
                if abbr and abbr not in keys:
                    keys.append(abbr)
        return keys

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "term": self.term,
            "full_name": self.full_name,
            "product": self.product,
            "description": self.description,
            "features": self.features,
            "related_terms": self.related_terms,
            "components": self.components,
        }

    def to_markdown(self) -> str:
        """마크다운 형식으로 변환"""
        lines = [f"## {self.term}"]

        if self.full_name:
            lines.append(f"- **정식명칭**: {self.full_name}")
        if self.product:
            lines.append(f"- **제품군**: {self.product}")
        if self.description:
            lines.append(f"- **설명**: {self.description}")

        if self.features:
            lines.append("- **주요기능**:")
            for feat in self.features:
                lines.append(f"  - {feat}")

        if self.components:
            lines.append("- **컴포넌트**:")
            for comp in self.components:
                lines.append(f"  - {comp}")

        if self.related_terms:
            lines.append(f"- **관련용어**: {', '.join(self.related_terms)}")

        if self.source_files:
            lines.append(f"- **참조매뉴얼**: {', '.join(self.source_files)}")

        lines.append("")
        return "\n".join(lines)


@dataclass
class GlossarySection:
    """용어 섹션 (첫 글자별)"""
    letter: str  # A, B, C, ...
    terms: List[GlossaryTerm] = field(default_factory=list)
    language: str = "ja"

    @property
    def filename(self) -> str:
        """출력 파일명"""
        return f"{self.letter}.md"

    def add_term(self, term: GlossaryTerm) -> None:
        """용어 추가"""
        # 중복 체크
        existing = [t for t in self.terms if t.term.upper() == term.term.upper()]
        if existing:
            # 기존 항목에 정보 병합
            self._merge_term(existing[0], term)
        else:
            self.terms.append(term)
            # 알파벳 순 정렬
            self.terms.sort(key=lambda t: t.term.upper())

    def _merge_term(self, existing: GlossaryTerm, new: GlossaryTerm) -> None:
        """용어 정보 병합"""
        if not existing.full_name and new.full_name:
            existing.full_name = new.full_name
        if not existing.description and new.description:
            existing.description = new.description

        # 리스트 병합 (중복 제거)
        existing.features = list(set(existing.features + new.features))
        existing.related_terms = list(set(existing.related_terms + new.related_terms))
        existing.source_files = list(set(existing.source_files + new.source_files))
        existing.components = list(set(existing.components + new.components))

    def to_markdown(self) -> str:
        """마크다운 파일 생성"""
        from datetime import datetime

        lines = [
            "---",
            "type: glossary",
            f"letter: {self.letter}",
            f"language: {self.language}",
            f"generated: {datetime.now().isoformat()}",
            f"term_count: {len(self.terms)}",
            "---",
            "",
            f"# {self.letter}",
            "",
        ]

        for term in self.terms:
            lines.append(term.to_markdown())

        return "\n".join(lines)
