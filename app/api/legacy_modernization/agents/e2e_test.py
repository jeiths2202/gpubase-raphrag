"""E2E Test Agent - Synthetic asset pipeline simulation.

Runs synthetic test assets through the analysis pipeline and compares
actual results against expected outputs to detect regressions.

Test suites contain:
- Synthetic COBOL/JCL/MAP/ASM source code with known features
- Expected feature extraction results
- Expected compatibility findings
"""

import logging
from typing import Any, ClassVar, Dict, List, Optional

from ..core.event_bus import EventBus
from ..core.protocol import (
    AgentId,
    AgentMessage,
    AgentResult,
    AgentTask,
    ChangeRequest,
    ChangeRequestResponse,
)
from ..core.shared_state import SharedStateStore
from ..models.enums import AgentRole, AgentStatus, AssetType, MessageType
from ..parsers.base import BaseParser
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class E2ETestCase:
    """A single E2E test case with synthetic asset and expected results."""

    def __init__(
        self,
        name: str,
        asset_type: AssetType,
        source_code: str,
        expected_features: List[str],
        expected_categories: List[str],
        min_confidence: float = 0.5,
    ) -> None:
        self.name = name
        self.asset_type = asset_type
        self.source_code = source_code
        self.expected_features = expected_features
        self.expected_categories = expected_categories
        self.min_confidence = min_confidence


# Built-in test suites for each asset type
_BUILTIN_SUITES: List[E2ETestCase] = [
    E2ETestCase(
        name="cobol_basic_file_io",
        asset_type=AssetType.COBOL,
        source_code=(
            "       IDENTIFICATION DIVISION.\n"
            "       PROGRAM-ID. TESTPGM.\n"
            "       ENVIRONMENT DIVISION.\n"
            "       INPUT-OUTPUT SECTION.\n"
            "       FILE-CONTROL.\n"
            "           SELECT INFILE ASSIGN TO 'INPUT.DAT'.\n"
            "       DATA DIVISION.\n"
            "       FILE SECTION.\n"
            "       FD INFILE.\n"
            "       01 IN-REC PIC X(80).\n"
            "       PROCEDURE DIVISION.\n"
            "           OPEN INPUT INFILE.\n"
            "           READ INFILE INTO IN-REC.\n"
            "           CLOSE INFILE.\n"
            "           STOP RUN.\n"
        ),
        expected_features=["OPEN", "READ", "CLOSE"],
        expected_categories=["file_io", "flow_control"],
    ),
    E2ETestCase(
        name="jcl_basic_job",
        asset_type=AssetType.JCL,
        source_code=(
            "//TESTJOB  JOB (ACCT),'TEST',CLASS=A,MSGCLASS=X\n"
            "//STEP1    EXEC PGM=IEFBR14\n"
            "//OUTDD    DD DSN=TEST.OUTPUT,DISP=(NEW,CATLG),\n"
            "//         SPACE=(CYL,(10,5)),DCB=(RECFM=FB,LRECL=80)\n"
        ),
        expected_features=["JOB", "EXEC", "DD"],
        expected_categories=["job_card", "exec_step", "dd_statement"],
    ),
    E2ETestCase(
        name="bms_basic_map",
        asset_type=AssetType.MAP,
        source_code=(
            "TESTSET  DFHMSD TYPE=MAP,LANG=COBOL,MODE=INOUT\n"
            "TESTMAP  DFHMDI SIZE=(24,80)\n"
            "FIELD1   DFHMDF POS=(3,10),LENGTH=20,ATTRB=(ASKIP,BRT)\n"
            "         DFHMSD TYPE=FINAL\n"
        ),
        expected_features=["DFHMSD", "DFHMDI", "DFHMDF"],
        expected_categories=["mapset_structure", "screen_layout", "field_definition"],
    ),
    E2ETestCase(
        name="asm_basic_csect",
        asset_type=AssetType.ASSEMBLER,
        source_code=(
            "TESTPGM  CSECT\n"
            "         USING *,R15\n"
            "         LA    R1,PARMLIST\n"
            "         L     R15,=V(SUBPGM)\n"
            "         BALR  R14,R15\n"
            "         SR    R15,R15\n"
            "         BR    R14\n"
            "PARMLIST DS    F\n"
            "         END   TESTPGM\n"
        ),
        expected_features=["CSECT", "USING", "LA", "BALR"],
        expected_categories=["addressing", "register_usage", "branch"],
    ),
]


class E2ETestAgent(BaseAgent):
    """Synthetic asset pipeline simulation for regression detection."""

    def __init__(
        self,
        event_bus: EventBus,
        shared_state: SharedStateStore,
        parsers: Optional[Dict[AssetType, BaseParser]] = None,
    ) -> None:
        super().__init__(AgentId(role=AgentRole.E2E_TEST), event_bus)
        self.shared_state = shared_state
        self._parsers = parsers or {}

    async def execute(self, task: AgentTask) -> AgentResult:
        workspace = await self.shared_state.get_workspace(task.asset_id)

        # Load test suites (built-in + any from task metadata)
        suites = list(_BUILTIN_SUITES)
        test_results: List[dict] = []

        for suite in suites:
            result = await self._run_test_case(suite)
            test_results.append(result)

        # Aggregate results
        passed = sum(1 for r in test_results if r["passed"])
        failed = len(test_results) - passed

        e2e_results = {
            "total": len(test_results),
            "passed": passed,
            "failed": failed,
            "test_cases": test_results,
        }

        # Write results
        workspace.e2e_results = e2e_results
        await self.shared_state.save_workspace(
            workspace, AgentRole.E2E_TEST,
            changed_fields={"e2e_results"},
        )

        # Publish result
        status = AgentStatus.COMPLETED if failed == 0 else AgentStatus.ERROR
        await self.publish(AgentMessage(
            sender=self.agent_id,
            recipient=AgentId(role=AgentRole.ORCHESTRATOR),
            message_type=MessageType.RESULT,
            payload={
                "asset_id": task.asset_id,
                "total": len(test_results),
                "passed": passed,
                "failed": failed,
                "regression_detected": failed > 0,
            },
            correlation_id=task.correlation_id,
        ))

        return AgentResult(
            agent_id=self.agent_id,
            status=status,
            workspace_id=task.asset_id,
            metadata=e2e_results,
        )

    async def handle_change_request(self, cr: ChangeRequest) -> ChangeRequestResponse:
        """E2E Test agent can only modify e2e_results."""
        if cr.target_field.startswith("e2e_results"):
            return ChangeRequestResponse(
                request_id=cr.request_id,
                approved=True,
                reason="E2E Test owns e2e_results",
                agent_id=self.agent_id,
            )
        return ChangeRequestResponse(
            request_id=cr.request_id,
            approved=False,
            reason="E2E Test can only modify e2e_results",
            agent_id=self.agent_id,
        )

    async def _run_test_case(self, suite: E2ETestCase) -> dict:
        """Run a single test case against the parser."""
        result: dict = {
            "suite_name": suite.name,
            "asset_type": suite.asset_type.value,
            "passed": False,
            "expected_features": suite.expected_features,
            "actual_features": [],
            "missing_features": [],
            "extra_features": [],
            "expected_categories": suite.expected_categories,
            "actual_categories": [],
            "confidence": 0.0,
            "error": None,
        }

        parser = self._parsers.get(suite.asset_type)
        if not parser:
            result["error"] = f"No parser available for {suite.asset_type.value}"
            return result

        try:
            parse_result = await parser.parse(suite.source_code, f"e2e_test/{suite.name}")
            actual_names = {f.name.upper() for f in parse_result.features}
            actual_categories = {f.category.value for f in parse_result.features}
            expected_names = {n.upper() for n in suite.expected_features}
            expected_cats = set(suite.expected_categories)

            missing = expected_names - actual_names
            extra = actual_names - expected_names
            missing_cats = expected_cats - actual_categories

            confidence = 1.0 - (len(parse_result.parse_errors) / max(len(parse_result.features), 1))

            result["actual_features"] = sorted(actual_names)
            result["actual_categories"] = sorted(actual_categories)
            result["missing_features"] = sorted(missing)
            result["extra_features"] = sorted(extra)
            result["confidence"] = round(max(0.0, confidence), 3)

            # Pass condition: no missing features AND confidence >= threshold
            result["passed"] = (
                len(missing) == 0
                and len(missing_cats) == 0
                and confidence >= suite.min_confidence
            )

        except Exception as exc:
            result["error"] = str(exc)
            logger.error("E2E test '%s' failed: %s", suite.name, exc)

        return result
