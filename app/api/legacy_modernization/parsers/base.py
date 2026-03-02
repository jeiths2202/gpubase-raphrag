"""Base parser interface and shared data models for all language parsers."""

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel, Field

from ..models.enums import AssetType, ComplexityLevel, FeatureCategory


class SourceReference(BaseModel):
    """Source code location reference."""

    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0


class ASTNode(BaseModel):
    """Abstract Syntax Tree node."""

    node_type: str = Field(
        ..., description="노드 타입 (e.g., PROGRAM, PARAGRAPH, DD_STATEMENT)"
    )
    name: Optional[str] = Field(None, description="노드 이름")
    source_line: int = Field(..., description="소스 라인 번호 (1-based)")
    source_column: int = Field(0, description="소스 컬럼")
    source_end_line: int = Field(..., description="종료 라인")
    children: List["ASTNode"] = Field(default_factory=list)
    properties: dict = Field(default_factory=dict, description="노드별 속성")


class NormalizedFeature(BaseModel):
    """Normalized feature extracted from source code (language-agnostic output)."""

    feature_id: str = Field(
        ..., description="고유 ID (e.g., COBOL-CICS-EXEC-001)"
    )
    category: FeatureCategory
    subcategory: str = Field(..., description="세부 분류")
    name: str = Field(..., description="Feature 이름")
    source_reference: SourceReference
    complexity: ComplexityLevel
    dialect_specific: bool = Field(False, description="방언 고유 기능 여부")
    metadata: dict = Field(default_factory=dict)


class TraceEvidence(BaseModel):
    """Trace evidence linking every finding back to source lines."""

    ast_node_path: str = Field(
        ..., description="AST 노드 경로 (e.g., /PROGRAM/PROCEDURE/PARAGRAPH[3])"
    )
    source_file: str
    source_lines: tuple[int, int] = Field(
        ..., description="(start_line, end_line)"
    )
    raw_source: str = Field(..., description="원문 소스 코드")
    confidence: float = Field(..., ge=0.0, le=1.0)


class ParseError(BaseModel):
    """Parse error encountered during parsing."""

    line: int
    column: int
    message: str
    severity: str = "error"


class ParseStats(BaseModel):
    """Statistics about a parse operation."""

    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    feature_count: int = 0
    error_count: int = 0
    dialect: Optional[str] = None


class ParserResult(BaseModel):
    """Final output of any parser."""

    asset_type: AssetType
    dialect: Optional[str] = None
    ast: ASTNode
    features: List[NormalizedFeature] = Field(default_factory=list)
    trace_evidence: List[TraceEvidence] = Field(default_factory=list)
    parse_errors: List[ParseError] = Field(default_factory=list)
    stats: ParseStats = Field(default_factory=ParseStats)


class BaseParser(ABC):
    """Abstract base class for all deterministic parsers."""

    @abstractmethod
    async def parse(self, source: str, file_path: str) -> ParserResult:
        """Parse source code and return AST + features."""
        ...

    @abstractmethod
    async def detect_dialect(self, source: str) -> Optional[str]:
        """Auto-detect the dialect of the source code."""
        ...

    @abstractmethod
    def get_supported_dialects(self) -> List[str]:
        """Return list of supported dialects."""
        ...

    def _count_lines(self, source: str) -> ParseStats:
        """Count line types in source."""
        lines = source.splitlines()
        total = len(lines)
        blank = sum(1 for l in lines if not l.strip())
        return ParseStats(
            total_lines=total,
            blank_lines=blank,
            code_lines=total - blank,
        )
