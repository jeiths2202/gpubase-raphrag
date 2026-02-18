"""
JCL AST Parser - Column-based line parser for MVS JCL + JES2/JES3.

Feature extraction categories:
- JOB_CARD, EXEC_STEP, DD_STATEMENT, DATASET, PROCEDURE,
  UTILITY, JES_CONTROL, CONDITIONAL, GDG, VSAM
"""

import re
from typing import List, Optional

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

# JCL 컬럼 레이아웃
CONTINUATION_COLUMN = 72
OPERAND_START_COLUMN = 16

# 패턴
_JOB_RE = re.compile(r"^//(\w+)\s+JOB\s+(.*)$", re.IGNORECASE)
_EXEC_RE = re.compile(r"^//(\w*)\s+EXEC\s+(.*)$", re.IGNORECASE)
_DD_RE = re.compile(r"^//(\w+)\s+DD\s+(.*)$", re.IGNORECASE)
_PROC_RE = re.compile(r"^//(\w*)\s+PROC\b", re.IGNORECASE)
_PEND_RE = re.compile(r"^//\s+PEND\b", re.IGNORECASE)
_IF_RE = re.compile(r"^//\s+IF\s+", re.IGNORECASE)
_JES_RE = re.compile(r"^/\*(\w+)\s+(.*)$")
_COMMENT_RE = re.compile(r"^//\*")
_DSN_RE = re.compile(r"DSN=([^\s,]+)", re.IGNORECASE)
_PGM_RE = re.compile(r"PGM=(\w+)", re.IGNORECASE)
_PROC_CALL_RE = re.compile(r"EXEC\s+(\w+)", re.IGNORECASE)
_GDG_RE = re.compile(r"\([+-]\d+\)")

# 유틸리티 프로그램 목록
UTILITY_PROGRAMS = {
    "IDCAMS", "IEBGENER", "IEBCOPY", "IEFBR14", "DFSORT", "SORT",
    "ICETOOL", "IKJEFT01", "IRXJCL", "IEFPROC", "ADRDSSU",
    "DSMIGIN", "DSMIGOUT",
}


class JCLParser(BaseParser):
    """Deterministic JCL parser with column-based line parsing."""

    async def parse(self, source: str, file_path: str) -> ParserResult:
        lines = self._preprocess_continuation(source)
        ast = self._build_ast(lines, file_path)
        features = self._extract_features(lines, file_path)
        evidence = self._build_trace_evidence(features, source, file_path)
        dialect = await self.detect_dialect(source)
        stats = self._compute_stats(source.splitlines(), features, dialect)

        return ParserResult(
            asset_type=AssetType.JCL,
            dialect=dialect,
            ast=ast,
            features=features,
            trace_evidence=evidence,
            stats=stats,
        )

    def _preprocess_continuation(self, source: str) -> List[tuple[int, str]]:
        """Join continuation lines. Returns (original_line_no, joined_line)."""
        raw_lines = source.splitlines()
        result: List[tuple[int, str]] = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            start_line = i + 1
            # 계속 행 처리: 72열 넘는 줄이면 다음 줄의 16열부터 이어붙임
            while (
                len(line) > CONTINUATION_COLUMN
                and i + 1 < len(raw_lines)
                and raw_lines[i + 1].startswith("//")
                and len(raw_lines[i + 1]) > OPERAND_START_COLUMN
                and not _COMMENT_RE.match(raw_lines[i + 1])
            ):
                i += 1
                continuation = raw_lines[i][OPERAND_START_COLUMN - 1 :].strip()
                line = line[:CONTINUATION_COLUMN].rstrip() + continuation
            result.append((start_line, line))
            i += 1
        return result

    def _build_ast(
        self, lines: List[tuple[int, str]], file_path: str
    ) -> ASTNode:
        children: List[ASTNode] = []
        current_job: Optional[ASTNode] = None

        for line_no, line in lines:
            if _JOB_RE.match(line):
                m = _JOB_RE.match(line)
                current_job = ASTNode(
                    node_type="JOB", name=m.group(1),
                    source_line=line_no, source_end_line=line_no,
                )
                children.append(current_job)
            elif _EXEC_RE.match(line):
                m = _EXEC_RE.match(line)
                step = ASTNode(
                    node_type="EXEC_STEP", name=m.group(1) or None,
                    source_line=line_no, source_end_line=line_no,
                    properties={"operand": m.group(2).strip()},
                )
                if current_job:
                    current_job.children.append(step)
                else:
                    children.append(step)
            elif _DD_RE.match(line):
                m = _DD_RE.match(line)
                dd = ASTNode(
                    node_type="DD_STATEMENT", name=m.group(1),
                    source_line=line_no, source_end_line=line_no,
                    properties={"operand": m.group(2).strip()},
                )
                if current_job and current_job.children:
                    current_job.children[-1].children.append(dd)
                elif current_job:
                    current_job.children.append(dd)
                else:
                    children.append(dd)

        return ASTNode(
            node_type="JCL_FILE", name=file_path,
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
            # JOB card
            if _JOB_RE.match(line):
                counter += 1
                m = _JOB_RE.match(line)
                features.append(NormalizedFeature(
                    feature_id=f"JCL-JOB-{counter:03d}",
                    category=FeatureCategory.JOB_CARD,
                    subcategory="JOB",
                    name=f"JOB {m.group(1)}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

            # EXEC step
            if _EXEC_RE.match(line):
                counter += 1
                operand = _EXEC_RE.match(line).group(2).strip()
                pgm_match = _PGM_RE.search(operand)
                if pgm_match:
                    pgm = pgm_match.group(1).upper()
                    cat = FeatureCategory.UTILITY if pgm in UTILITY_PROGRAMS else FeatureCategory.EXEC_STEP
                    features.append(NormalizedFeature(
                        feature_id=f"JCL-EXEC-{counter:03d}",
                        category=cat,
                        subcategory="PGM",
                        name=f"PGM={pgm}",
                        source_reference=SourceReference(
                            file_path=file_path, line_start=line_no, line_end=line_no
                        ),
                        complexity=ComplexityLevel.LOW if pgm in UTILITY_PROGRAMS else ComplexityLevel.MEDIUM,
                    ))
                else:
                    # PROC call
                    proc_m = _PROC_CALL_RE.search(operand)
                    if proc_m:
                        features.append(NormalizedFeature(
                            feature_id=f"JCL-PROC-{counter:03d}",
                            category=FeatureCategory.PROCEDURE,
                            subcategory="EXEC_PROC",
                            name=f"EXEC {proc_m.group(1)}",
                            source_reference=SourceReference(
                                file_path=file_path, line_start=line_no, line_end=line_no
                            ),
                            complexity=ComplexityLevel.MEDIUM,
                        ))

            # DD statement
            if _DD_RE.match(line):
                counter += 1
                m = _DD_RE.match(line)
                operand = m.group(2).strip()
                dsn_match = _DSN_RE.search(operand)
                subcategory = "DD"
                complexity = ComplexityLevel.LOW
                cat = FeatureCategory.DD_STATEMENT

                if dsn_match:
                    dsn = dsn_match.group(1)
                    if _GDG_RE.search(dsn):
                        cat = FeatureCategory.GDG
                        subcategory = "GDG"
                        complexity = ComplexityLevel.MEDIUM
                    cat = FeatureCategory.DATASET if cat == FeatureCategory.DD_STATEMENT else cat

                features.append(NormalizedFeature(
                    feature_id=f"JCL-DD-{counter:03d}",
                    category=cat,
                    subcategory=subcategory,
                    name=f"DD {m.group(1)}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=complexity,
                ))

            # JES control
            if _JES_RE.match(line):
                counter += 1
                m = _JES_RE.match(line)
                features.append(NormalizedFeature(
                    feature_id=f"JCL-JES-{counter:03d}",
                    category=FeatureCategory.JES_CONTROL,
                    subcategory=m.group(1).upper(),
                    name=f"/*{m.group(1).upper()}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

            # IF/THEN/ELSE
            if _IF_RE.match(line):
                counter += 1
                features.append(NormalizedFeature(
                    feature_id=f"JCL-IF-{counter:03d}",
                    category=FeatureCategory.CONDITIONAL,
                    subcategory="IF",
                    name="IF condition",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.MEDIUM,
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
                ast_node_path=f"/JCL/{feat.category.value}/{feat.feature_id}",
                source_file=file_path,
                source_lines=(feat.source_reference.line_start, feat.source_reference.line_end),
                raw_source=raw.rstrip(),
                confidence=0.95,
            ))
        return evidence

    def _compute_stats(
        self, lines: List[str], features: List[NormalizedFeature], dialect: Optional[str]
    ) -> ParseStats:
        total = len(lines)
        comment = sum(1 for l in lines if _COMMENT_RE.match(l))
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
        if "/*JOBPARM" in source or "/*ROUTE" in source:
            return "jes2"
        if "//*MAIN" in source or "//*FORMAT" in source:
            return "jes3"
        return "mvs"

    def get_supported_dialects(self) -> List[str]:
        return ["mvs", "jes2", "jes3"]
