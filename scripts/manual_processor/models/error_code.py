"""에러 코드 모델"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ErrorCode:
    """개별 에러 코드"""
    code: int  # -5212
    name: str  # DSALC_ERR_ALREADY_CATALOGED
    description: str  # 説明
    solution: str  # 対処方法
    reference: str = ""  # 参考
    module: str = ""  # DSALC
    source_file: str = ""  # 원본 파일명

    @property
    def code_str(self) -> str:
        """에러 코드 문자열 (음수 포함)"""
        return str(-abs(self.code))

    @property
    def search_keys(self) -> List[str]:
        """검색 키워드 목록"""
        keys = [
            self.code_str,
            str(abs(self.code)),
            self.name,
            self.name.replace("_", " "),
        ]
        # 에러명에서 주요 키워드 추출
        if "_ERR_" in self.name:
            parts = self.name.split("_ERR_")
            if len(parts) > 1:
                keys.append(parts[1].replace("_", " "))
        return keys

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "solution": self.solution,
            "reference": self.reference,
            "module": self.module,
        }

    def to_markdown(self) -> str:
        """마크다운 형식으로 변환"""
        lines = [
            f"### {self.name} ({self.code_str})",
            f"- **설명**: {self.description}",
            f"- **대처방법**: {self.solution}",
        ]
        if self.reference:
            lines.append(f"- **참고**: {self.reference}")
        lines.append("")
        return "\n".join(lines)


@dataclass
class ErrorCodeModule:
    """에러 코드 모듈 (범위 단위)"""
    module_name: str  # DSALC
    range_start: int  # 5000
    range_end: int  # 5999
    description: str  # モジュール説明
    prefix: str = "BASE"  # 제품 프리픽스
    errors: List[ErrorCode] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)

    @property
    def range_str(self) -> str:
        """범위 문자열"""
        return f"-{self.range_start} ~ -{self.range_end}"

    @property
    def filename(self) -> str:
        """출력 파일명"""
        return f"{self.prefix}-{self.range_start}.md"

    def add_error(self, error: ErrorCode) -> None:
        """에러 코드 추가"""
        error.module = self.module_name
        self.errors.append(error)
        # 코드 순서로 정렬
        self.errors.sort(key=lambda e: abs(e.code))

    def find_error(self, code: int) -> Optional[ErrorCode]:
        """에러 코드로 검색"""
        code = abs(code)
        for error in self.errors:
            if abs(error.code) == code:
                return error
        return None

    def to_markdown(self, language: str = "ja") -> str:
        """마크다운 파일 생성"""
        from datetime import datetime

        lines = [
            "---",
            "type: error-codes",
            f"module: {self.module_name}",
            f"range: {self.range_str}",
            f"language: {language}",
            f"generated: {datetime.now().isoformat()}",
            "source_files:",
        ]
        for src in self.source_files:
            lines.append(f"  - {src}")
        lines.extend([
            "---",
            "",
            f"# {self.module_name} 에러 코드 (-{self.range_start})",
            "",
            "## 모듈 개요",
            self.description,
            "",
            "## 에러 목록",
            "",
        ])

        for error in self.errors:
            lines.append(error.to_markdown())

        return "\n".join(lines)
