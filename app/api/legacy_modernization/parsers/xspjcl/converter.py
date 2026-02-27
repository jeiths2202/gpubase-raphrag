"""XSP JCL C 파서 결과 → NormalizedFeature 변환기.

C 파서의 XSPParseResult를 base.py의 ParserResult로 변환.
모든 statement/param/subparam/instream/relex/error를 NormalizedFeature + ASTNode로 매핑.
"""

import logging
from typing import Dict, List, Optional, Tuple

from ..base import (
    ASTNode,
    NormalizedFeature,
    ParseError,
    ParseStats,
    ParserResult,
    SourceReference,
    TraceEvidence,
)
from ...models.enums import AssetType, ComplexityLevel, FeatureCategory
from .models import (
    STMT_TYPE_DISPLAY,
    XSPParam,
    XSPParseResult,
    XSPStatement,
)

logger = logging.getLogger(__name__)

# Statement 타입 → FeatureCategory 매핑
_STMT_TO_CATEGORY: Dict[str, FeatureCategory] = {
    # Job 관리
    "STMT_JOBG": FeatureCategory.JOB_CARD,
    "STMT_CODE": FeatureCategory.JOB_CARD,
    "STMT_JOB": FeatureCategory.JOB_CARD,
    "STMT_JEND": FeatureCategory.JOB_CARD,
    "STMT_JGEND": FeatureCategory.JOB_CARD,
    "STMT_FIN": FeatureCategory.JOB_CARD,
    # 실행
    "STMT_EX": FeatureCategory.EXEC_STEP,
    "STMT_EX_MACRO": FeatureCategory.EXEC_STEP,
    "STMT_PARA": FeatureCategory.EXEC_STEP,
    # 파일
    "STMT_FD": FeatureCategory.DD_STATEMENT,
    "STMT_FDR": FeatureCategory.DD_STATEMENT,
    "STMT_FDDS": FeatureCategory.DD_STATEMENT,
    "STMT_FDDE": FeatureCategory.DD_STATEMENT,
    "STMT_SYSIN": FeatureCategory.DD_STATEMENT,
    # 데이터
    "STMT_DATA": FeatureCategory.DATASET,
    "STMT_END": FeatureCategory.DATASET,
    "STMT_CAT": FeatureCategory.DATASET,
    "STMT_UNCAT": FeatureCategory.DATASET,
    "STMT_STACK": FeatureCategory.DATASET,
    # 제어
    "STMT_SW": FeatureCategory.CONDITIONAL,
    "STMT_SCAN": FeatureCategory.XSP_CONTROL,
    "STMT_SCEND": FeatureCategory.XSP_CONTROL,
    "STMT_USER": FeatureCategory.XSP_CONTROL,
    "STMT_UEND": FeatureCategory.XSP_CONTROL,
    "STMT_NOP": FeatureCategory.XSP_CONTROL,
    "STMT_COMMAND": FeatureCategory.XSP_CONTROL,
    "STMT_PAUSE": FeatureCategory.XSP_CONTROL,
    "STMT_MSG": FeatureCategory.XSP_CONTROL,
    "STMT_NOTE": FeatureCategory.XSP_CONTROL,
    "STMT_CHAM": FeatureCategory.XSP_CONTROL,
    # 매크로
    "STMT_MACRO": FeatureCategory.PROCEDURE,
    "STMT_MEND": FeatureCategory.PROCEDURE,
    # JCM 매크로 문
    "MSTMT_DEFINE": FeatureCategory.XSP_CONTROL,
    "MSTMT_SKIP": FeatureCategory.CONDITIONAL,
    "MSTMT_IF": FeatureCategory.CONDITIONAL,
    "MSTMT_IFN": FeatureCategory.CONDITIONAL,
    "MSTMT_SET": FeatureCategory.XSP_CONTROL,
    "MSTMT_MSG": FeatureCategory.XSP_CONTROL,
    "MSTMT_WTO": FeatureCategory.XSP_CONTROL,
    "MSTMT_WTOR": FeatureCategory.XSP_CONTROL,
    "MSTMT_NOP": FeatureCategory.XSP_CONTROL,
    "MSTMT_DEXIT": FeatureCategory.XSP_CONTROL,
    "MSTMT_DEFEND": FeatureCategory.XSP_CONTROL,
    # 에러
    "STMT_ERROR": FeatureCategory.XSP_CONTROL,
    "STMT_OTHER": FeatureCategory.XSP_CONTROL,
}

# Complexity 결정 기준
_HIGH_COMPLEXITY_STMTS = {
    "STMT_SW", "MSTMT_IF", "MSTMT_IFN", "STMT_SCAN",
    "STMT_EX_MACRO", "MSTMT_DEFINE",
}
_MEDIUM_COMPLEXITY_STMTS = {
    "STMT_JOBG", "STMT_JOB", "STMT_EX", "STMT_FD",
    "STMT_MACRO", "MSTMT_SET", "STMT_FDDS", "STMT_SYSIN",
    "STMT_COMMAND", "STMT_CHAM",
}


class XSPResultConverter:
    """XSPParseResult → ParserResult 변환기.

    C 파서 출력의 모든 구조를 ASTNode + NormalizedFeature로 변환.
    """

    def __init__(self, file_path: str = "<string>"):
        self._file_path = file_path
        self._feature_counter: Dict[str, int] = {}
        self._features: List[NormalizedFeature] = []
        self._traces: List[TraceEvidence] = []
        self._errors: List[ParseError] = []

    def convert(self, result: XSPParseResult, source: str = "") -> ParserResult:
        """XSPParseResult → ParserResult 변환."""
        self._features = []
        self._traces = []
        self._errors = []
        self._feature_counter = {}

        # AST 루트 구축
        root_children = []
        for stmt in result.statements:
            ast_node = self._stmt_to_ast(stmt, "/")
            root_children.append(ast_node)
            self._extract_features_recursive(stmt, "/")

        root = ASTNode(
            node_type="XSP_JCL_PROGRAM",
            name=self._file_path,
            source_line=1,
            source_end_line=result.total_lines or len(source.splitlines()),
            children=root_children,
            properties={
                "parser": "OF7_xspjcl_c",
                "parser_version": result.parser_version,
                "macro_expanded": (
                    result.macro_info.expanded if result.macro_info else False
                ),
            },
        )

        # 에러 변환
        for err in result.errors:
            self._errors.append(ParseError(
                line=err.lineno,
                column=0,
                message=f"[{err.error_name}] {err.message}",
                severity="error",
            ))

        # 통계
        source_lines = source.splitlines() if source else []
        stats = ParseStats(
            total_lines=result.total_lines or len(source_lines),
            code_lines=result.stmt_count,
            error_count=result.error_count,
            feature_count=len(self._features),
            dialect="xsp",
        )

        return ParserResult(
            asset_type=AssetType.JCL,
            dialect="xsp",
            ast=root,
            features=self._features,
            trace_evidence=self._traces,
            parse_errors=self._errors,
            stats=stats,
        )

    def _stmt_to_ast(self, stmt: XSPStatement, parent_path: str) -> ASTNode:
        """XSPStatement → ASTNode 재귀 변환."""
        node_path = f"{parent_path}{stmt.type}"
        line_start = stmt.lineno
        line_end = stmt.lineno

        # line_range가 있으면 사용
        if stmt.line_range and len(stmt.line_range) == 2:
            line_start = stmt.line_range[0]
            line_end = stmt.line_range[1]

        # 파라미터 속성 추출
        properties: dict = {}
        if stmt.type_str:
            properties["type_str"] = stmt.type_str
        if stmt.lineno_str:
            properties["lineno_str"] = stmt.lineno_str

        # 파라미터 직렬화
        param_props = self._params_to_dict(stmt.params)
        if param_props:
            properties["params"] = param_props

        # 자식 노드 재귀
        children = []
        for child in stmt.children:
            children.append(self._stmt_to_ast(child, f"{node_path}/"))

        return ASTNode(
            node_type=stmt.type,
            name=stmt.name,
            source_line=line_start,
            source_end_line=line_end,
            children=children,
            properties=properties,
        )

    def _params_to_dict(self, params: List[XSPParam]) -> List[dict]:
        """파라미터 리스트를 딕셔너리로 변환."""
        result = []
        for p in params:
            # !!RANGE!! 내부 파라미터는 건너뜀 (이미 line_range로 처리)
            if p.keyword == "!!RANGE!!":
                continue

            entry: dict = {"type": p.type, "position": p.position}
            if p.keyword:
                entry["keyword"] = p.keyword

            if p.subparam:
                sp = p.subparam
                entry["val_type"] = sp.val_type
                if sp.str_val is not None:
                    entry["value"] = sp.str_val
                if sp.sub_params:
                    entry["sub_params"] = self._params_to_dict(sp.sub_params)
                if sp.instream_data:
                    entry["instream_data"] = {
                        "count": sp.instream_data.count,
                        "lines": sp.instream_data.lines,
                    }
                if sp.relex:
                    entry["relex"] = {
                        "type": sp.relex.type,
                    }

            result.append(entry)
        return result

    def _extract_features_recursive(
        self, stmt: XSPStatement, parent_path: str
    ) -> None:
        """Statement에서 NormalizedFeature 추출 (재귀)."""
        # STMT_NULL, STMT_OTHER 건너뜀
        if stmt.type in ("STMT_NULL", "STMT_OTHER"):
            for child in stmt.children:
                self._extract_features_recursive(child, parent_path)
            return

        category = _STMT_TO_CATEGORY.get(stmt.type, FeatureCategory.XSP_CONTROL)
        complexity = self._determine_complexity(stmt)

        feature_id = self._next_feature_id(stmt.type)
        subcategory = self._determine_subcategory(stmt)

        line_start = stmt.lineno
        line_end = stmt.lineno
        if stmt.line_range and len(stmt.line_range) == 2:
            line_start = stmt.line_range[0]
            line_end = stmt.line_range[1]

        # 메타데이터: 파라미터 요약
        metadata: dict = {}
        if stmt.name:
            metadata["name"] = stmt.name
        if stmt.type_str:
            metadata["display"] = stmt.type_str
        if stmt.lineno_str:
            metadata["macro_line"] = stmt.lineno_str

        # 주요 키워드 파라미터 추출
        for p in stmt.params:
            if p.keyword and p.keyword != "!!RANGE!!" and p.subparam:
                if p.subparam.str_val:
                    metadata[p.keyword] = p.subparam.str_val

        # Instream 데이터 존재 여부
        has_instream = any(
            p.subparam and p.subparam.instream_data
            for p in stmt.params
            if p.subparam
        )
        if has_instream:
            metadata["has_instream_data"] = True

        # Relex 존재 여부 (SW/IF 문)
        has_relex = any(
            p.subparam and p.subparam.relex
            for p in stmt.params
            if p.subparam
        )
        if has_relex:
            metadata["has_relational_expression"] = True

        feature = NormalizedFeature(
            feature_id=feature_id,
            category=category,
            subcategory=subcategory,
            name=f"{stmt.type_str or stmt.type}" + (f" {stmt.name}" if stmt.name else ""),
            source_reference=SourceReference(
                file_path=self._file_path,
                line_start=line_start,
                line_end=line_end,
            ),
            complexity=complexity,
            dialect_specific=True,
            metadata=metadata,
        )
        self._features.append(feature)

        # Trace evidence
        display = stmt.type_str or STMT_TYPE_DISPLAY.get(stmt.type, stmt.type)
        self._traces.append(TraceEvidence(
            ast_node_path=f"{parent_path}{stmt.type}",
            source_file=self._file_path,
            source_lines=(line_start, line_end),
            raw_source=f"{display} {stmt.name or ''}".strip(),
            confidence=1.0,
        ))

        # 자식 재귀
        for child in stmt.children:
            self._extract_features_recursive(
                child, f"{parent_path}{stmt.type}/"
            )

    def _determine_complexity(self, stmt: XSPStatement) -> ComplexityLevel:
        """Statement의 복잡도 결정."""
        if stmt.type == "STMT_ERROR":
            return ComplexityLevel.CRITICAL
        if stmt.type in _HIGH_COMPLEXITY_STMTS:
            return ComplexityLevel.HIGH
        if stmt.type in _MEDIUM_COMPLEXITY_STMTS:
            return ComplexityLevel.MEDIUM
        return ComplexityLevel.LOW

    def _determine_subcategory(self, stmt: XSPStatement) -> str:
        """Statement의 세부 분류 결정."""
        type_str = stmt.type

        # JCM 매크로 문
        if type_str.startswith("MSTMT_"):
            return "jcm_macro"

        # 에러
        if type_str == "STMT_ERROR":
            return "parse_error"

        # Statement 타입별 세부 분류
        subcategory_map = {
            "STMT_JOBG": "job_group",
            "STMT_CODE": "return_code",
            "STMT_JOB": "job_definition",
            "STMT_EX": "program_execution",
            "STMT_EX_MACRO": "macro_execution",
            "STMT_PARA": "parameter_override",
            "STMT_FD": "file_definition",
            "STMT_FDR": "file_definition_relative",
            "STMT_FDDS": "file_definition_ds_start",
            "STMT_FDDE": "file_definition_ds_end",
            "STMT_SW": "switch_condition",
            "STMT_PAUSE": "execution_pause",
            "STMT_MSG": "message_output",
            "STMT_NOTE": "comment",
            "STMT_JEND": "job_end",
            "STMT_JGEND": "job_group_end",
            "STMT_FIN": "jcl_finish",
            "STMT_SYSIN": "sysin_include",
            "STMT_CHAM": "channel_message",
            "STMT_MACRO": "macro_definition",
            "STMT_MEND": "macro_end",
            "STMT_STACK": "stack_operation",
            "STMT_CAT": "catalog_operation",
            "STMT_UNCAT": "uncatalog_operation",
            "STMT_DATA": "instream_data_start",
            "STMT_END": "instream_data_end",
            "STMT_SCAN": "scan_start",
            "STMT_SCEND": "scan_end",
            "STMT_USER": "user_start",
            "STMT_UEND": "user_end",
            "STMT_NOP": "no_operation",
            "STMT_COMMAND": "system_command",
        }
        return subcategory_map.get(type_str, "unknown")

    def _next_feature_id(self, stmt_type: str) -> str:
        """Feature ID 생성."""
        count = self._feature_counter.get(stmt_type, 0) + 1
        self._feature_counter[stmt_type] = count
        return f"XSP-{stmt_type}-{count:03d}"
