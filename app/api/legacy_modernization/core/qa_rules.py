"""QA Rule Engine - 7 validation rules for quality control.

RULE-01: TraceEvidence — every finding must have trace evidence
RULE-02: NonZeroConfidence — no finding with 0.0 confidence
RULE-03: NoDuplicateFindings — no duplicate feature+vendor combinations
RULE-04: SeverityConsistency — severity must match support_level
RULE-05: SourceLineMatch — trace evidence source lines within LOC range
RULE-06: HallucinationGuard — LLM annotations must not contain hallucination patterns
RULE-07: SchemaValidation — all required fields present in workspace
"""

import re
from abc import ABC, abstractmethod
from typing import ClassVar, List

from pydantic import BaseModel, Field

from ..core.shared_state import SharedWorkspaceState
from ..models.enums import Severity, SupportLevel


class QARuleResult(BaseModel):
    """Result of a single QA rule evaluation."""

    rule_id: str
    passed: bool
    severity: Severity
    message: str
    affected_findings: List[str] = Field(default_factory=list)


class QARule(ABC):
    """Abstract QA rule interface."""

    rule_id: ClassVar[str]
    description: ClassVar[str]
    severity: ClassVar[Severity]

    @abstractmethod
    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        ...


class TraceEvidenceRule(QARule):
    """RULE-01: Every finding must have trace_evidence with source references."""

    rule_id = "RULE-01"
    description = "Every finding must have trace evidence with source line reference"
    severity = Severity.CRITICAL

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        missing: List[str] = []
        for finding in workspace.compatibility_findings:
            te = finding.get("trace_evidence")
            if not te:
                missing.append(finding.get("finding_id", "unknown"))
            elif isinstance(te, dict) and not te.get("source_lines"):
                missing.append(finding.get("finding_id", "unknown"))
        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(missing) == 0,
            severity=self.severity,
            message=(
                f"{len(missing)} findings missing trace evidence"
                if missing
                else "All findings have trace evidence"
            ),
            affected_findings=missing,
        )


class NonZeroConfidenceRule(QARule):
    """RULE-02: No finding with confidence == 0.0."""

    rule_id = "RULE-02"
    description = "No finding should have zero confidence"
    severity = Severity.CRITICAL

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        zero_conf: List[str] = []
        for finding in workspace.compatibility_findings:
            if finding.get("confidence", 0.0) == 0.0:
                zero_conf.append(finding.get("finding_id", "unknown"))
        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(zero_conf) == 0,
            severity=self.severity,
            message=(
                f"{len(zero_conf)} findings have zero confidence"
                if zero_conf
                else "All findings have non-zero confidence"
            ),
            affected_findings=zero_conf,
        )


class NoDuplicateFindingsRule(QARule):
    """RULE-03: No duplicate feature+vendor findings."""

    rule_id = "RULE-03"
    description = "No duplicate findings for the same feature and vendor"
    severity = Severity.ERROR

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        duplicates: List[str] = []
        seen: set[str] = set()
        for finding in workspace.compatibility_findings:
            feat = finding.get("feature", {})
            fid = feat.get("feature_id", "")
            vendor = finding.get("vendor", "")
            key = f"{fid}:{vendor}"
            if key in seen:
                duplicates.append(finding.get("finding_id", "unknown"))
            else:
                seen.add(key)
        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(duplicates) == 0,
            severity=self.severity,
            message=(
                f"{len(duplicates)} duplicate findings detected"
                if duplicates
                else "No duplicate findings"
            ),
            affected_findings=duplicates,
        )


class SeverityConsistencyRule(QARule):
    """RULE-04: Severity must be consistent with support_level."""

    rule_id = "RULE-04"
    description = "Severity must be consistent with support level"
    severity = Severity.ERROR

    EXPECTED_SEVERITY: ClassVar[dict[str, str]] = {
        SupportLevel.FULL.value: Severity.INFO.value,
        SupportLevel.PARTIAL.value: Severity.WARNING.value,
        SupportLevel.WORKAROUND.value: Severity.WARNING.value,
        SupportLevel.UNSUPPORTED.value: Severity.ERROR.value,
    }

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        inconsistent: List[str] = []
        for finding in workspace.compatibility_findings:
            sl = finding.get("support_level", "")
            sev = finding.get("severity", "")
            expected = self.EXPECTED_SEVERITY.get(sl)
            if expected and sev != expected:
                # CRITICAL is manually set and always allowed
                if sev != Severity.CRITICAL.value:
                    inconsistent.append(finding.get("finding_id", "unknown"))
        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(inconsistent) == 0,
            severity=self.severity,
            message=(
                f"{len(inconsistent)} findings have inconsistent severity"
                if inconsistent
                else "Severity consistent with support levels"
            ),
            affected_findings=inconsistent,
        )


class SourceLineMatchRule(QARule):
    """RULE-05: Trace evidence source lines must be within LOC range."""

    rule_id = "RULE-05"
    description = "Source line references must be within the file's LOC range"
    severity = Severity.ERROR

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        out_of_range: List[str] = []
        loc = workspace.loc_count
        if loc == 0:
            # Cannot validate without LOC count
            return QARuleResult(
                rule_id=self.rule_id,
                passed=True,
                severity=self.severity,
                message="LOC count is 0, skipping source line validation",
            )

        for finding in workspace.compatibility_findings:
            te = finding.get("trace_evidence")
            if not te or not isinstance(te, dict):
                continue
            for sl in te.get("source_lines", []):
                if isinstance(sl, dict):
                    line = sl.get("line_number", 0)
                elif isinstance(sl, int):
                    line = sl
                else:
                    continue
                if line > loc or line < 1:
                    out_of_range.append(finding.get("finding_id", "unknown"))
                    break

        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(out_of_range) == 0,
            severity=self.severity,
            message=(
                f"{len(out_of_range)} findings have out-of-range source lines"
                if out_of_range
                else "All source line references within LOC range"
            ),
            affected_findings=out_of_range,
        )


class HallucinationGuardRule(QARule):
    """RULE-06: LLM-generated annotations must not contain hallucination patterns."""

    rule_id = "RULE-06"
    description = "LLM-generated text must not contain hallucination patterns"
    severity = Severity.CRITICAL

    # Hallucination patterns identified from KMS E2E testing
    HALLUCINATION_PATTERNS: ClassVar[list[str]] = [
        r"OpenFrame version \d+\.\d+ supports",  # Non-existent version references
        r"according to the official documentation",  # Unsubstantiated claims
        r"it is well known that",  # Ungrounded generalizations
        r"as stated in the manual",  # Phantom manual references
        r"the specification clearly states",  # Phantom spec references
    ]

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        flagged: List[str] = []
        for annotation in workspace.annotations:
            source = annotation.get("source", "")
            text = annotation.get("text", "")
            ann_id = annotation.get("annotation_id", "unknown")
            if source == "llm":
                for pattern in self.HALLUCINATION_PATTERNS:
                    if re.search(pattern, text, re.IGNORECASE):
                        flagged.append(ann_id)
                        break
        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(flagged) == 0,
            severity=self.severity,
            message=(
                f"{len(flagged)} hallucination patterns detected in LLM annotations"
                if flagged
                else "No hallucination patterns detected"
            ),
            affected_findings=flagged,
        )


class SchemaValidationRule(QARule):
    """RULE-07: All required workspace fields are populated."""

    rule_id = "RULE-07"
    description = "Workspace must have all required fields populated"
    severity = Severity.ERROR

    REQUIRED_FIELDS: ClassVar[list[str]] = [
        "asset_id", "tenant_id", "asset_type",
        "file_path", "file_name",
        "features", "confidence",
    ]

    async def validate(self, workspace: SharedWorkspaceState) -> QARuleResult:
        missing: List[str] = []
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(workspace, field_name, None)
            if value is None or value == "" or value == []:
                missing.append(field_name)

        return QARuleResult(
            rule_id=self.rule_id,
            passed=len(missing) == 0,
            severity=self.severity,
            message=(
                f"Missing required fields: {', '.join(missing)}"
                if missing
                else "All required fields populated"
            ),
            affected_findings=missing,
        )


def get_all_rules() -> List[QARule]:
    """Return all 7 QA rules in order."""
    return [
        TraceEvidenceRule(),        # RULE-01
        NonZeroConfidenceRule(),     # RULE-02
        NoDuplicateFindingsRule(),   # RULE-03
        SeverityConsistencyRule(),   # RULE-04
        SourceLineMatchRule(),       # RULE-05
        HallucinationGuardRule(),    # RULE-06
        SchemaValidationRule(),      # RULE-07
    ]
