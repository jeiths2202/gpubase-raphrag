"""
JCL AST Parser - Column-based line parser for MVS/XSP JCL + JES2/JES3.

Feature extraction categories:
- JOB_CARD, EXEC_STEP, DD_STATEMENT, DATASET, PROCEDURE,
  UTILITY, JES_CONTROL, CONDITIONAL, GDG, VSAM

Supported dialects:
- mvs: Standard MVS JCL (//-prefixed statements)
- jes2: JES2 extensions (/*JOBPARM, /*ROUTE)
- jes3: JES3 extensions (//*MAIN, //*FORMAT)
- xsp: Fujitsu OSIV/XSP JCL (\\ JOB, \\ EX, \\ FD, /EXPAN, / SET)
      → C 파서 가용 시 OF7 xspjcl C 파서에 위임 (모든 기능 완전 지원)
"""

import logging
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
from .xspjcl import XSPParserAdapter

logger = logging.getLogger(__name__)

# JCL 컬럼 레이아웃
CONTINUATION_COLUMN = 72
OPERAND_START_COLUMN = 16

# --- MVS JCL patterns (// prefix) ---
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

# --- Fujitsu XSP JCL patterns (\ prefix) ---
# XSP uses "\ " (backslash-space) as statement prefix instead of "//"
# Statements: \ JOB, \ EX (EXEC), \ FD (DD), \ JEND, / SET, /EXPAN, / DEFEND, / MSG
_XSP_JOB_RE = re.compile(r"^\\\s+JOB\s+(.*)$", re.IGNORECASE)
_XSP_EXEC_RE = re.compile(r"^\\\s+EX\s+(.*)$", re.IGNORECASE)
_XSP_FD_RE = re.compile(r"^\\\s+FD\s+(.*)$", re.IGNORECASE)
_XSP_JEND_RE = re.compile(r"^\\\s+JEND\b", re.IGNORECASE)
_XSP_SET_RE = re.compile(r"^/\s+SET\s+(.*)$", re.IGNORECASE)
_XSP_EXPAN_RE = re.compile(r"^/EXPAN\s+(.*)$", re.IGNORECASE)
_XSP_MSG_RE = re.compile(r"^\\\s+MSG\s+(.*)$", re.IGNORECASE)
_XSP_DEFEND_RE = re.compile(r"^/\s+DEFEND\b", re.IGNORECASE)
_XSP_COMMENT_RE = re.compile(r"^\\\s*\*")
# XSP statement detector (any \ or / prefix used in XSP)
_XSP_DETECT_PATTERNS = {"\ JOB", "\ EX ", "\ FD ", "\ JEND", "/EXPAN", "/ SET", "/ DEFEND"}

# 유틸리티 프로그램 목록
UTILITY_PROGRAMS = {
    "IDCAMS", "IEBGENER", "IEBCOPY", "IEFBR14", "DFSORT", "SORT",
    "ICETOOL", "IKJEFT01", "IRXJCL", "IEFPROC", "ADRDSSU",
    "DSMIGIN", "DSMIGOUT",
}


class JCLParser(BaseParser):
    """Deterministic JCL parser with column-based line parsing.

    XSP 방언 감지 시 OF7 C 파서에 위임하여 모든 기능을 완전 지원:
      - 43개 statement 타입 파싱
      - 매크로 확장 (/DEFINE, /SET, SCF 변수)
      - SYSIN 파일 포함
      - Instream 데이터 (FD *, FDDS~FDDE, DATA~END)
      - Relational expression (SW/IF 조건식)
      - 21개 에러 타입 감지
      - Stream 관리 (원본 소스 라인 + 에러 주석)
    C 파서 불가 시 기존 Python regex 폴백.
    """

    def __init__(self) -> None:
        super().__init__()
        self._xsp_adapter = XSPParserAdapter()

    async def parse(self, source: str, file_path: str) -> ParserResult:
        dialect = await self.detect_dialect(source)

        # XSP 방언: C 파서에 위임 (가용 시)
        if dialect == "xsp":
            c_result = await self._xsp_adapter.parse(source, file_path)
            if c_result is not None:
                logger.info(
                    "XSP JCL parsed by C parser: %d features, %d errors",
                    c_result.stats.feature_count,
                    c_result.stats.error_count,
                )
                return c_result
            logger.debug("C parser unavailable, falling back to Python regex")

        # MVS/JES2/JES3 또는 C 파서 불가 시 Python 폴백
        lines = self._preprocess_continuation(source)
        ast = self._build_ast(lines, file_path)
        features = self._extract_features(lines, file_path)
        evidence = self._build_trace_evidence(features, source, file_path)
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
            # MVS 계속 행: 72열 넘으면 다음 //행의 16열부터 이어붙임
            while (
                len(line) > CONTINUATION_COLUMN
                and i + 1 < len(raw_lines)
                and (
                    (raw_lines[i + 1].startswith("//") and not _COMMENT_RE.match(raw_lines[i + 1]))
                    or (raw_lines[i + 1].startswith("\\") and not _XSP_COMMENT_RE.match(raw_lines[i + 1]))
                )
                and len(raw_lines[i + 1]) > OPERAND_START_COLUMN
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
            # MVS JOB or XSP JOB
            m_job = _JOB_RE.match(line) or _XSP_JOB_RE.match(line)
            m_exec = None if m_job else (_EXEC_RE.match(line) or _XSP_EXEC_RE.match(line))
            m_dd = None if (m_job or m_exec) else (_DD_RE.match(line) or _XSP_FD_RE.match(line))

            if m_job:
                # MVS: group(1)=name, XSP: group(1)=operand (first word = jobname)
                is_xsp = _XSP_JOB_RE.match(line) is not None
                if is_xsp:
                    job_name = m_job.group(1).split()[0] if m_job.group(1).strip() else "UNNAMED"
                else:
                    job_name = m_job.group(1)
                current_job = ASTNode(
                    node_type="JOB", name=job_name,
                    source_line=line_no, source_end_line=line_no,
                )
                children.append(current_job)
            elif m_exec:
                is_xsp = _XSP_EXEC_RE.match(line) is not None
                if is_xsp:
                    operand = m_exec.group(1).strip()
                    step_name = None
                else:
                    step_name = m_exec.group(1) or None
                    operand = m_exec.group(2).strip()
                step = ASTNode(
                    node_type="EXEC_STEP", name=step_name,
                    source_line=line_no, source_end_line=line_no,
                    properties={"operand": operand},
                )
                if current_job:
                    current_job.children.append(step)
                else:
                    children.append(step)
            elif m_dd:
                is_xsp = _XSP_FD_RE.match(line) is not None
                if is_xsp:
                    # XSP FD: operand like "DDNAME=DISP,..." — extract ddname
                    operand = m_dd.group(1).strip()
                    dd_name = operand.split("=")[0].strip() if "=" in operand else operand.split()[0]
                else:
                    dd_name = m_dd.group(1)
                    operand = m_dd.group(2).strip()
                dd = ASTNode(
                    node_type="DD_STATEMENT", name=dd_name,
                    source_line=line_no, source_end_line=line_no,
                    properties={"operand": operand},
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
            # JOB card (MVS or XSP)
            m_mvs_job = _JOB_RE.match(line)
            m_xsp_job = _XSP_JOB_RE.match(line) if not m_mvs_job else None
            if m_mvs_job or m_xsp_job:
                counter += 1
                if m_mvs_job:
                    job_name = m_mvs_job.group(1)
                else:
                    operand = m_xsp_job.group(1).strip()
                    job_name = operand.split()[0] if operand else "UNNAMED"
                features.append(NormalizedFeature(
                    feature_id=f"JCL-JOB-{counter:03d}",
                    category=FeatureCategory.JOB_CARD,
                    subcategory="JOB",
                    name=f"JOB {job_name}",
                    source_reference=SourceReference(
                        file_path=file_path, line_start=line_no, line_end=line_no
                    ),
                    complexity=ComplexityLevel.LOW,
                ))

            # EXEC step (MVS or XSP EX)
            m_mvs_exec = _EXEC_RE.match(line)
            m_xsp_exec = _XSP_EXEC_RE.match(line) if not m_mvs_exec else None
            if m_mvs_exec or m_xsp_exec:
                counter += 1
                if m_mvs_exec:
                    operand = m_mvs_exec.group(2).strip()
                else:
                    operand = m_xsp_exec.group(1).strip()
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
                    # XSP EX: first word is program name directly (e.g. "\ EX KEQEFT01")
                    # MVS: PROC call (e.g. "EXEC MYPROC")
                    pgm_or_proc = operand.split()[0] if operand else ""
                    if m_xsp_exec and pgm_or_proc:
                        pgm = pgm_or_proc.upper()
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

            # DD statement (MVS or XSP FD)
            m_mvs_dd = _DD_RE.match(line)
            m_xsp_fd = _XSP_FD_RE.match(line) if not m_mvs_dd else None
            if m_mvs_dd or m_xsp_fd:
                counter += 1
                if m_mvs_dd:
                    dd_name = m_mvs_dd.group(1)
                    operand = m_mvs_dd.group(2).strip()
                else:
                    operand = m_xsp_fd.group(1).strip()
                    dd_name = operand.split("=")[0].strip() if "=" in operand else operand.split()[0]
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
                    name=f"DD {dd_name}",
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

            # IF/THEN/ELSE (MVS only)
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

            # XSP control statements (/EXPAN, / SET, / DEFEND, \ JEND, \ MSG)
            m_xsp_ctl = (
                _XSP_EXPAN_RE.match(line)
                or _XSP_SET_RE.match(line)
                or _XSP_DEFEND_RE.match(line)
                or _XSP_JEND_RE.match(line)
                or _XSP_MSG_RE.match(line)
            )
            if m_xsp_ctl:
                counter += 1
                # Determine subcategory from the matched pattern
                if _XSP_EXPAN_RE.match(line):
                    sub, name = "EXPAN", f"/EXPAN {m_xsp_ctl.group(1).strip()}" if m_xsp_ctl.lastindex else "/EXPAN"
                elif _XSP_SET_RE.match(line):
                    sub, name = "SET", f"/ SET {m_xsp_ctl.group(1).strip()}" if m_xsp_ctl.lastindex else "/ SET"
                elif _XSP_DEFEND_RE.match(line):
                    sub, name = "DEFEND", "/ DEFEND"
                elif _XSP_JEND_RE.match(line):
                    sub, name = "JEND", "\\ JEND"
                else:
                    sub, name = "MSG", f"\\ MSG {m_xsp_ctl.group(1).strip()}" if m_xsp_ctl.lastindex else "\\ MSG"
                features.append(NormalizedFeature(
                    feature_id=f"JCL-XSP-{counter:03d}",
                    category=FeatureCategory.XSP_CONTROL,
                    subcategory=sub,
                    name=name,
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
        comment = sum(1 for l in lines if _COMMENT_RE.match(l) or _XSP_COMMENT_RE.match(l))
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
        upper = source[:1000].upper()
        # XSP JCL: Fujitsu OSIV/XSP dialect (\ JOB, \ EX, \ FD, /EXPAN)
        if any(pat in upper for pat in _XSP_DETECT_PATTERNS):
            return "xsp"
        if "/*JOBPARM" in source or "/*ROUTE" in source:
            return "jes2"
        if "//*MAIN" in source or "//*FORMAT" in source:
            return "jes3"
        return "mvs"

    def get_supported_dialects(self) -> List[str]:
        return ["mvs", "jes2", "jes3", "xsp"]
