"""
HLASM (High-Level Assembler) Parser - Column-based parsing.

Supports: z/OS HLASM, z/VSE Assembler, z/VM Assembler.
Feature categories: MACRO_USAGE, REGISTER_USAGE, SUPERVISOR_CALL,
                    DSECT_STRUCTURE, DATA_DEFINITION, SYSTEM_MACRO, ADDRESSING, BRANCH
"""

import re
from typing import List, Optional

from ..models.enums import AssetType, ComplexityLevel, FeatureCategory
from .base import (
    ASTNode,
    BaseParser,
    NormalizedFeature,
    ParseStats,
    ParserResult,
    SourceReference,
    TraceEvidence,
)

# HLASM 컬럼 레이아웃
LABEL_START = 0
LABEL_END = 8
OP_START = 9
OP_END = 14
OPERAND_START = 15
CONT_COL = 71

# 시스템 매크로 → FeatureCategory 매핑
SYSTEM_MACROS = {
    "GET": FeatureCategory.MACRO_USAGE,
    "PUT": FeatureCategory.MACRO_USAGE,
    "OPEN": FeatureCategory.MACRO_USAGE,
    "CLOSE": FeatureCategory.MACRO_USAGE,
    "GETMAIN": FeatureCategory.SYSTEM_MACRO,
    "FREEMAIN": FeatureCategory.SYSTEM_MACRO,
    "WTO": FeatureCategory.SYSTEM_MACRO,
    "ABEND": FeatureCategory.SYSTEM_MACRO,
    "CALL": FeatureCategory.MACRO_USAGE,
    "LINK": FeatureCategory.MACRO_USAGE,
    "XCTL": FeatureCategory.MACRO_USAGE,
    "LOAD": FeatureCategory.MACRO_USAGE,
    "DELETE": FeatureCategory.MACRO_USAGE,
    "ATTACH": FeatureCategory.SYSTEM_MACRO,
    "DETACH": FeatureCategory.SYSTEM_MACRO,
    "ENQ": FeatureCategory.SYSTEM_MACRO,
    "DEQ": FeatureCategory.SYSTEM_MACRO,
    "STIMER": FeatureCategory.SYSTEM_MACRO,
    "TTIMER": FeatureCategory.SYSTEM_MACRO,
}

# SVC 번호 → 서비스 매핑
SVC_TABLE = {
    1: "WAIT",
    2: "POST",
    3: "EXIT",
    4: "GETMAIN",
    5: "FREEMAIN",
    6: "LINK",
    7: "XCTL",
    10: "GETMAIN/FREEMAIN",
    13: "ABEND",
    19: "OPEN",
    20: "CLOSE",
    35: "WTO",
    42: "ATTACH",
    47: "STIMER",
    48: "DEQ",
    56: "ENQ",
}

# Addressing instructions
_ADDRESSING_OPS = {"LA", "L", "ST", "MVC", "MVI", "CLC", "CLI", "IC", "STC", "LR", "LH", "STH"}
# Branch instructions
_BRANCH_OPS = {"B", "BC", "BCR", "BAL", "BALR", "BAS", "BASR", "BXH", "BXLE"}
# Structure directives
_STRUCT_OPS = {"DSECT", "CSECT", "USING", "DROP", "ENTRY", "EXTRN"}
# Data definitions
_DATA_OPS = {"DC", "DS", "EQU", "ORG"}

_SVC_RE = re.compile(r"\bSVC\s+(\d+)", re.IGNORECASE)
_REGISTER_RE = re.compile(r"\bR(\d{1,2})\b")


class ASMParser(BaseParser):
    """Deterministic HLASM parser with column-based line parsing."""

    async def parse(self, source: str, file_path: str) -> ParserResult:
        lines = self._preprocess_continuation(source)
        ast = self._build_ast(lines, file_path)
        features = self._extract_features(lines, file_path)
        evidence = self._build_trace_evidence(features, source, file_path)
        dialect = await self.detect_dialect(source)
        stats = self._compute_stats(source.splitlines(), features, dialect)

        return ParserResult(
            asset_type=AssetType.ASSEMBLER,
            dialect=dialect,
            ast=ast,
            features=features,
            trace_evidence=evidence,
            stats=stats,
        )

    def _preprocess_continuation(self, source: str) -> List[tuple[int, str]]:
        """Join continuation lines (col 72 non-blank = continuation)."""
        raw_lines = source.splitlines()
        result: List[tuple[int, str]] = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            start_line = i + 1
            while (
                len(line) > CONT_COL
                and line[CONT_COL] not in (" ", "")
                and i + 1 < len(raw_lines)
            ):
                i += 1
                next_line = raw_lines[i]
                continuation = next_line[OPERAND_START:].strip() if len(next_line) > OPERAND_START else ""
                line = line[:CONT_COL].rstrip() + continuation
            result.append((start_line, line))
            i += 1
        return result

    def _parse_statement(self, line: str) -> tuple[str, str, str]:
        """Extract label, operation, operand from a line."""
        if not line or line[0] == "*":
            return ("", "", "")
        label = line[LABEL_START:LABEL_END].strip() if len(line) > LABEL_END else ""
        op = line[OP_START:OP_END + 1].strip() if len(line) > OP_START else ""
        operand = line[OPERAND_START:CONT_COL].strip() if len(line) > OPERAND_START else ""
        return (label, op.upper(), operand)

    def _build_ast(
        self, lines: List[tuple[int, str]], file_path: str
    ) -> ASTNode:
        children: List[ASTNode] = []
        current_section: Optional[ASTNode] = None

        for line_no, line in lines:
            label, op, operand = self._parse_statement(line)
            if op in ("CSECT", "DSECT"):
                current_section = ASTNode(
                    node_type=op, name=label or f"UNNAMED_{line_no}",
                    source_line=line_no, source_end_line=line_no,
                )
                children.append(current_section)
            elif op and current_section is not None:
                stmt = ASTNode(
                    node_type="STATEMENT", name=label or None,
                    source_line=line_no, source_end_line=line_no,
                    properties={"op": op, "operand": operand},
                )
                current_section.children.append(stmt)

        return ASTNode(
            node_type="ASM_FILE", name=file_path,
            source_line=1,
            source_end_line=lines[-1][0] if lines else 1,
            children=children,
        )

    def _extract_features(
        self, lines: List[tuple[int, str]], file_path: str
    ) -> List[NormalizedFeature]:
        features: List[NormalizedFeature] = []
        counter = 0

        for line_no, line in lines:
            label, op, operand = self._parse_statement(line)
            if not op:
                continue

            # System macros
            if op in SYSTEM_MACROS:
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"ASM-MACRO-{op}-{counter:03d}",
                    category=SYSTEM_MACROS[op],
                    subcategory=op,
                    name=f"{op} {operand[:30]}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.MEDIUM,
                ))

            # SVC calls
            svc_m = _SVC_RE.search(line)
            if svc_m:
                svc_num = int(svc_m.group(1))
                svc_name = SVC_TABLE.get(svc_num, f"SVC_{svc_num}")
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"ASM-SVC-{svc_num}-{counter:03d}",
                    category=FeatureCategory.SUPERVISOR_CALL,
                    subcategory=f"SVC_{svc_num}",
                    name=f"SVC {svc_num} ({svc_name})",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.HIGH,
                ))

            # Addressing instructions
            if op in _ADDRESSING_OPS:
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"ASM-ADDR-{counter:03d}",
                    category=FeatureCategory.ADDRESSING,
                    subcategory=op,
                    name=f"{op} {operand[:30]}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

            # Branch instructions
            if op in _BRANCH_OPS:
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"ASM-BRANCH-{counter:03d}",
                    category=FeatureCategory.BRANCH,
                    subcategory=op,
                    name=f"{op} {operand[:30]}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

            # Structure directives (DSECT, CSECT, USING, DROP)
            if op in _STRUCT_OPS:
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"ASM-STRUCT-{counter:03d}",
                    category=FeatureCategory.DSECT_STRUCTURE,
                    subcategory=op,
                    name=f"{op} {label or operand[:30]}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.MEDIUM,
                ))

            # Data definitions (DC, DS)
            if op in _DATA_OPS:
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"ASM-DATA-{counter:03d}",
                    category=FeatureCategory.DATA_DEFINITION,
                    subcategory=op,
                    name=f"{op} {label or ''} {operand[:20]}".strip(),
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

        return features

    def _build_trace_evidence(
        self,
        features: List[NormalizedFeature],
        source: str,
        file_path: str,
    ) -> List[TraceEvidence]:
        lines = source.splitlines()
        evidence: List[TraceEvidence] = []
        for feat in features:
            line_idx = feat.source_reference.line_start - 1
            raw = lines[line_idx] if 0 <= line_idx < len(lines) else ""
            evidence.append(TraceEvidence(
                ast_node_path=f"/ASM/{feat.category.value}/{feat.feature_id}",
                source_file=file_path,
                source_lines=(feat.source_reference.line_start, feat.source_reference.line_end),
                raw_source=raw.rstrip(),
                confidence=0.90,
            ))
        return evidence

    def _compute_stats(
        self, lines: List[str], features: List[NormalizedFeature], dialect: Optional[str]
    ) -> ParseStats:
        total = len(lines)
        comment = sum(1 for l in lines if l and l[0] == "*")
        blank = sum(1 for l in lines if not l.strip())
        return ParseStats(
            total_lines=total,
            code_lines=total - comment - blank,
            comment_lines=comment,
            blank_lines=blank,
            feature_count=len(features),
            dialect=dialect,
        )

    async def detect_dialect(self, source: str) -> Optional[str]:
        if "SYSSTATE ARCHLVL" in source.upper():
            return "hlasm_zos"
        return "hlasm"

    def get_supported_dialects(self) -> List[str]:
        return ["hlasm", "hlasm_zos", "hlasm_zvse"]
