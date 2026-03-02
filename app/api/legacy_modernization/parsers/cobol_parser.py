"""
COBOL AST Parser - Tree-sitter based deterministic parsing.

Supported dialects:
- Enterprise COBOL 6.x (z/OS)
- VS COBOL II
- Micro Focus COBOL
- GnuCOBOL

Feature extraction categories:
- FILE_IO, CICS, DB2, IMS, STRING_OP, ARITHMETIC, FLOW_CONTROL, COPYBOOK, SPECIAL
"""

import re
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from ..models.enums import AssetType, ComplexityLevel, FeatureCategory
from .base import (
    ASTNode,
    BaseParser,
    NormalizedFeature,
    ParseError,
    ParseStats,
    ParserResult,
    SourceReference,
    TraceEvidence,
)

# Tree-sitter grammar path (compiled .so/.dll)
_GRAMMAR_PATH = Path(__file__).parent / "grammars" / "cobol.so"

# COBOL 방언 마커
DIALECT_MARKERS = {
    "enterprise_cobol_6": ["JSON GENERATE", "JSON PARSE", "UTF-8", "FUNCTION RANDOM"],
    "vs_cobol_ii": ["EVALUATE TRUE", "SET ADDRESS", "REFERENCE"],
    "micro_focus": ["$SET", "SCREEN SECTION", "ACCEPT FROM"],
    "gnucobol": [">>SOURCE", ">>DEFINE", "FUNCTION-ID"],
}

# Feature 추출 패턴 (정규식 기반 폴백, Tree-sitter 없을 때)
_EXEC_CICS_RE = re.compile(
    r"EXEC\s+CICS\s+(\w+)", re.IGNORECASE | re.MULTILINE
)
_EXEC_SQL_RE = re.compile(
    r"EXEC\s+SQL\s+(\w+)", re.IGNORECASE | re.MULTILINE
)
_EXEC_DLI_RE = re.compile(
    r"EXEC\s+DLI\s+(\w+)", re.IGNORECASE | re.MULTILINE
)
_FILE_IO_RE = re.compile(
    r"\b(OPEN|CLOSE|READ|WRITE|REWRITE|DELETE|START)\b", re.IGNORECASE
)
_COPY_RE = re.compile(r"\bCOPY\s+([\w-]+)", re.IGNORECASE)
_PERFORM_RE = re.compile(r"\bPERFORM\s+([\w-]+)", re.IGNORECASE)
_CALL_RE = re.compile(r"\bCALL\s+['\"]?([\w-]+)", re.IGNORECASE)
_COMPUTE_RE = re.compile(r"\bCOMPUTE\b", re.IGNORECASE)
_STRING_OP_RE = re.compile(
    r"\b(STRING|UNSTRING|INSPECT)\b", re.IGNORECASE
)
_SORT_RE = re.compile(r"\bSORT\b", re.IGNORECASE)


class COBOLParser(BaseParser):
    """Deterministic COBOL parser with Tree-sitter AST (with regex fallback)."""

    def __init__(self) -> None:
        self._tree_sitter_available = False
        self._ts_parser = None
        self._ts_language = None
        self._try_load_tree_sitter()

    def _try_load_tree_sitter(self) -> None:
        """Attempt to load Tree-sitter COBOL grammar."""
        try:
            import tree_sitter  # noqa: F401

            if _GRAMMAR_PATH.exists():
                # tree_sitter.Language(_GRAMMAR_PATH, "cobol")
                # self._ts_language = lang
                # self._ts_parser = tree_sitter.Parser()
                # self._ts_parser.set_language(lang)
                # self._tree_sitter_available = True
                pass  # Grammar .so 빌드 후 활성화
        except ImportError:
            pass

    async def parse(self, source: str, file_path: str) -> ParserResult:
        dialect = await self.detect_dialect(source)
        if self._tree_sitter_available:
            return await self._parse_tree_sitter(source, file_path, dialect)
        return await self._parse_regex_fallback(source, file_path, dialect)

    async def _parse_tree_sitter(
        self, source: str, file_path: str, dialect: Optional[str]
    ) -> ParserResult:
        """Full Tree-sitter based parsing (requires compiled grammar)."""
        # TODO: Tree-sitter grammar .so 빌드 후 활성화
        return await self._parse_regex_fallback(source, file_path, dialect)

    async def _parse_regex_fallback(
        self, source: str, file_path: str, dialect: Optional[str]
    ) -> ParserResult:
        """Regex-based feature extraction fallback."""
        lines = source.splitlines()
        ast = self._build_basic_ast(lines, file_path)
        features: List[NormalizedFeature] = []
        evidence: List[TraceEvidence] = []
        errors: List[ParseError] = []
        counter = 0

        # EXEC CICS
        for m in _EXEC_CICS_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            feat = NormalizedFeature(
                feature_id=f"COBOL-CICS-{m.group(1).upper()}-{counter:03d}",
                category=FeatureCategory.CICS,
                subcategory=m.group(1).upper(),
                name=f"EXEC CICS {m.group(1).upper()}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.MEDIUM,
            )
            features.append(feat)
            evidence.append(TraceEvidence(
                ast_node_path=f"/PROGRAM/CICS/{m.group(1).upper()}[{counter}]",
                source_file=file_path,
                source_lines=(line_no, line_no),
                raw_source=m.group(0).strip(),
                confidence=0.95,
            ))

        # EXEC SQL
        for m in _EXEC_SQL_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-DB2-{m.group(1).upper()}-{counter:03d}",
                category=FeatureCategory.DB2,
                subcategory=m.group(1).upper(),
                name=f"EXEC SQL {m.group(1).upper()}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.MEDIUM,
            ))
            evidence.append(TraceEvidence(
                ast_node_path=f"/PROGRAM/SQL/{m.group(1).upper()}[{counter}]",
                source_file=file_path,
                source_lines=(line_no, line_no),
                raw_source=m.group(0).strip(),
                confidence=0.95,
            ))

        # EXEC DLI (IMS)
        for m in _EXEC_DLI_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-IMS-{m.group(1).upper()}-{counter:03d}",
                category=FeatureCategory.IMS,
                subcategory=m.group(1).upper(),
                name=f"EXEC DLI {m.group(1).upper()}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.HIGH,
            ))
            evidence.append(TraceEvidence(
                ast_node_path=f"/PROGRAM/IMS/{m.group(1).upper()}[{counter}]",
                source_file=file_path,
                source_lines=(line_no, line_no),
                raw_source=m.group(0).strip(),
                confidence=0.90,
            ))

        # FILE I/O
        for m in _FILE_IO_RE.finditer(source):
            line_no = source[:m.start()].count("\n") + 1
            # 인라인 코멘트 안의 매칭 스킵
            line_text = lines[line_no - 1] if line_no <= len(lines) else ""
            if len(line_text) >= 7 and line_text[6] == "*":
                continue
            counter += 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-IO-{m.group(1).upper()}-{counter:03d}",
                category=FeatureCategory.FILE_IO,
                subcategory=m.group(1).upper(),
                name=m.group(1).upper(),
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.LOW,
            ))

        # COPY (copybook)
        for m in _COPY_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-COPY-{counter:03d}",
                category=FeatureCategory.COPYBOOK,
                subcategory="COPY",
                name=f"COPY {m.group(1)}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.LOW,
            ))

        # CALL (external)
        for m in _CALL_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-CALL-{counter:03d}",
                category=FeatureCategory.SPECIAL,
                subcategory="CALL",
                name=f"CALL {m.group(1)}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.MEDIUM,
            ))

        # STRING/UNSTRING/INSPECT
        for m in _STRING_OP_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-STR-{counter:03d}",
                category=FeatureCategory.STRING_OP,
                subcategory=m.group(1).upper(),
                name=m.group(1).upper(),
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.LOW,
            ))

        # SORT
        for m in _SORT_RE.finditer(source):
            counter += 1
            line_no = source[:m.start()].count("\n") + 1
            features.append(NormalizedFeature(
                feature_id=f"COBOL-SORT-{counter:03d}",
                category=FeatureCategory.SPECIAL,
                subcategory="SORT",
                name="SORT",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.MEDIUM,
            ))

        stats = self._compute_stats(lines, features, dialect)
        return ParserResult(
            asset_type=AssetType.COBOL,
            dialect=dialect,
            ast=ast,
            features=features,
            trace_evidence=evidence,
            parse_errors=errors,
            stats=stats,
        )

    def _build_basic_ast(self, lines: List[str], file_path: str) -> ASTNode:
        """Build a basic AST from COBOL source lines."""
        children: List[ASTNode] = []
        current_division = None

        for i, line in enumerate(lines, 1):
            upper = line.upper().strip()
            if "IDENTIFICATION DIVISION" in upper:
                current_division = "IDENTIFICATION"
                children.append(ASTNode(
                    node_type="DIVISION", name="IDENTIFICATION",
                    source_line=i, source_end_line=i,
                ))
            elif "ENVIRONMENT DIVISION" in upper:
                current_division = "ENVIRONMENT"
                children.append(ASTNode(
                    node_type="DIVISION", name="ENVIRONMENT",
                    source_line=i, source_end_line=i,
                ))
            elif "DATA DIVISION" in upper:
                current_division = "DATA"
                children.append(ASTNode(
                    node_type="DIVISION", name="DATA",
                    source_line=i, source_end_line=i,
                ))
            elif "PROCEDURE DIVISION" in upper:
                current_division = "PROCEDURE"
                children.append(ASTNode(
                    node_type="DIVISION", name="PROCEDURE",
                    source_line=i, source_end_line=i,
                ))

        return ASTNode(
            node_type="PROGRAM",
            name=file_path,
            source_line=1,
            source_end_line=len(lines),
            children=children,
        )

    def _compute_stats(
        self, lines: List[str], features: List[NormalizedFeature], dialect: Optional[str]
    ) -> ParseStats:
        total = len(lines)
        comment = 0
        blank = 0
        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                blank += 1
            elif len(stripped) >= 7 and stripped[6] == "*":
                comment += 1
        return ParseStats(
            total_lines=total,
            code_lines=total - comment - blank,
            comment_lines=comment,
            blank_lines=blank,
            feature_count=len(features),
            dialect=dialect,
        )

    async def detect_dialect(self, source: str) -> Optional[str]:
        upper = source.upper()
        for dialect, markers in DIALECT_MARKERS.items():
            if any(m in upper for m in markers):
                return dialect
        return "enterprise_cobol_6"  # default

    def get_supported_dialects(self) -> List[str]:
        return list(DIALECT_MARKERS.keys())
