"""
MAP Parser - BMS (CICS) and MFS (IMS) screen definition parser.

Regex-based macro parsing for DFHMSD/DFHMDI/DFHMDF (BMS) and FORMAT/MSG/SEG (MFS).
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

# BMS 매크로 패턴
BMS_PATTERNS = {
    "DFHMSD": re.compile(
        r"^(\w+)\s+DFHMSD\s+(.*)", re.IGNORECASE | re.MULTILINE
    ),
    "DFHMDI": re.compile(
        r"^(\w+)\s+DFHMDI\s+(.*)", re.IGNORECASE | re.MULTILINE
    ),
    "DFHMDF": re.compile(
        r"^(\w+)\s+DFHMDF\s+(.*)", re.IGNORECASE | re.MULTILINE
    ),
}

# MFS 패턴
MFS_PATTERNS = {
    "FMT": re.compile(r"^(\w+)\s+FMT\s+(.*)", re.IGNORECASE | re.MULTILINE),
    "MSG": re.compile(r"^(\w+)\s+MSG\s+(.*)", re.IGNORECASE | re.MULTILINE),
    "SEG": re.compile(r"^(\w+)\s+SEG\s+(.*)", re.IGNORECASE | re.MULTILINE),
    "LPAGE": re.compile(r"^(\w+)\s+LPAGE\s+(.*)", re.IGNORECASE | re.MULTILINE),
}

# Attribute extraction helpers
_TYPE_RE = re.compile(r"TYPE=(\w+)", re.IGNORECASE)
_SIZE_RE = re.compile(r"SIZE=\((\d+),(\d+)\)", re.IGNORECASE)
_POS_RE = re.compile(r"POS=\((\d+),(\d+)\)", re.IGNORECASE)
_ATTRB_RE = re.compile(r"ATTRB=\(([^)]+)\)", re.IGNORECASE)
_LENGTH_RE = re.compile(r"LENGTH=(\d+)", re.IGNORECASE)
_COLOR_RE = re.compile(r"COLOR=(\w+)", re.IGNORECASE)
_INITIAL_RE = re.compile(r"INITIAL='([^']*)'", re.IGNORECASE)


class MAPParser(BaseParser):
    """Deterministic MAP parser for BMS/MFS screen definitions."""

    async def parse(self, source: str, file_path: str) -> ParserResult:
        dialect = await self.detect_dialect(source)
        if dialect == "mfs":
            return await self._parse_mfs(source, file_path)
        return await self._parse_bms(source, file_path)

    async def _parse_bms(self, source: str, file_path: str) -> ParserResult:
        """Parse CICS BMS mapset definitions."""
        features: List[NormalizedFeature] = []
        evidence: List[TraceEvidence] = []
        children: List[ASTNode] = []
        counter = 0

        # DFHMSD (mapset level)
        for m in BMS_PATTERNS["DFHMSD"].finditer(source):
            counter += 1
            line_no = source[: m.start()].count("\n") + 1
            name = m.group(1)
            operand = m.group(2)
            type_m = _TYPE_RE.search(operand)
            mapset_type = type_m.group(1) if type_m else "MAP"

            mapset_node = ASTNode(
                node_type="MAPSET", name=name,
                source_line=line_no, source_end_line=line_no,
                properties={"type": mapset_type},
            )
            children.append(mapset_node)

            features.append(NormalizedFeature(
                feature_id=f"MAP-MAPSET-{counter:03d}",
                category=FeatureCategory.MAPSET_STRUCTURE,
                subcategory="DFHMSD",
                name=f"MAPSET {name} TYPE={mapset_type}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.MEDIUM,
            ))
            evidence.append(TraceEvidence(
                ast_node_path=f"/MAPSET/{name}",
                source_file=file_path,
                source_lines=(line_no, line_no),
                raw_source=m.group(0).strip(),
                confidence=0.98,
            ))

        # DFHMDI (map level)
        for m in BMS_PATTERNS["DFHMDI"].finditer(source):
            counter += 1
            line_no = source[: m.start()].count("\n") + 1
            name = m.group(1)
            operand = m.group(2)
            size_m = _SIZE_RE.search(operand)
            rows = int(size_m.group(1)) if size_m else 24
            cols = int(size_m.group(2)) if size_m else 80

            map_node = ASTNode(
                node_type="MAP", name=name,
                source_line=line_no, source_end_line=line_no,
                properties={"rows": rows, "cols": cols},
            )
            if children:
                children[-1].children.append(map_node)
            else:
                children.append(map_node)

            features.append(NormalizedFeature(
                feature_id=f"MAP-SCREEN-{counter:03d}",
                category=FeatureCategory.SCREEN_LAYOUT,
                subcategory="DFHMDI",
                name=f"MAP {name} SIZE=({rows},{cols})",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.MEDIUM,
            ))
            evidence.append(TraceEvidence(
                ast_node_path=f"/MAPSET/MAP/{name}",
                source_file=file_path,
                source_lines=(line_no, line_no),
                raw_source=m.group(0).strip(),
                confidence=0.98,
            ))

        # DFHMDF (field level)
        for m in BMS_PATTERNS["DFHMDF"].finditer(source):
            counter += 1
            line_no = source[: m.start()].count("\n") + 1
            name = m.group(1)
            operand = m.group(2)
            pos_m = _POS_RE.search(operand)
            row = int(pos_m.group(1)) if pos_m else 0
            col = int(pos_m.group(2)) if pos_m else 0
            length_m = _LENGTH_RE.search(operand)
            length = int(length_m.group(1)) if length_m else 0
            attrb_m = _ATTRB_RE.search(operand)
            attrb = attrb_m.group(1) if attrb_m else ""

            features.append(NormalizedFeature(
                feature_id=f"MAP-FIELD-{counter:03d}",
                category=FeatureCategory.FIELD_DEFINITION,
                subcategory="DFHMDF",
                name=f"FIELD {name} POS=({row},{col}) LEN={length}",
                source_reference=SourceReference(
                    file_path=file_path, line_start=line_no, line_end=line_no
                ),
                complexity=ComplexityLevel.LOW,
                metadata={"attrb": attrb, "row": row, "col": col, "length": length},
            ))

            # Attribute features
            color_m = _COLOR_RE.search(operand)
            if color_m or "IC" in attrb.upper():
                features.append(NormalizedFeature(
                    feature_id=f"MAP-ATTR-{counter:03d}",
                    category=FeatureCategory.ATTRIBUTE,
                    subcategory="COLOR" if color_m else "CURSOR",
                    name=f"ATTRB({attrb})" if not color_m else f"COLOR={color_m.group(1)}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

        ast = ASTNode(
            node_type="BMS_FILE", name=file_path,
            source_line=1,
            source_end_line=source.count("\n") + 1,
            children=children,
        )
        stats = self._compute_stats(source, features, "bms")
        return ParserResult(
            asset_type=AssetType.MAP, dialect="bms",
            ast=ast, features=features, trace_evidence=evidence,
            stats=stats,
        )

    async def _parse_mfs(self, source: str, file_path: str) -> ParserResult:
        """Parse IMS MFS format definitions."""
        features: List[NormalizedFeature] = []
        evidence: List[TraceEvidence] = []
        children: List[ASTNode] = []
        counter = 0

        for macro_name, pattern in MFS_PATTERNS.items():
            for m in pattern.finditer(source):
                counter += 1
                line_no = source[: m.start()].count("\n") + 1
                name = m.group(1)
                operand = m.group(2)

                node = ASTNode(
                    node_type=macro_name, name=name,
                    source_line=line_no, source_end_line=line_no,
                    properties={"operand": operand.strip()},
                )
                children.append(node)

                cat = FeatureCategory.SCREEN_LAYOUT if macro_name == "FMT" else FeatureCategory.FIELD_DEFINITION
                features.append(NormalizedFeature(
                    feature_id=f"MFS-{macro_name}-{counter:03d}",
                    category=cat,
                    subcategory=macro_name,
                    name=f"{macro_name} {name}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.MEDIUM,
                ))
                evidence.append(TraceEvidence(
                    ast_node_path=f"/MFS/{macro_name}/{name}",
                    source_file=file_path,
                    source_lines=(line_no, line_no),
                    raw_source=m.group(0).strip(),
                    confidence=0.90,
                ))

        ast = ASTNode(
            node_type="MFS_FILE", name=file_path,
            source_line=1,
            source_end_line=source.count("\n") + 1,
            children=children,
        )
        stats = self._compute_stats(source, features, "mfs")
        return ParserResult(
            asset_type=AssetType.MAP, dialect="mfs",
            ast=ast, features=features, trace_evidence=evidence,
            stats=stats,
        )

    def _compute_stats(
        self, source: str, features: List[NormalizedFeature], dialect: Optional[str]
    ) -> ParseStats:
        lines = source.splitlines()
        total = len(lines)
        comment = sum(1 for l in lines if l.strip().startswith("*"))
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
        if "DFHMSD" in source.upper() or "DFHMDI" in source.upper():
            return "bms"
        if "FMT" in source.upper() and "MSG" in source.upper():
            return "mfs"
        return None

    def get_supported_dialects(self) -> List[str]:
        return ["bms", "mfs"]
