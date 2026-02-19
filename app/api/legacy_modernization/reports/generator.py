"""ReportGenerator — produces 9 report types from SharedWorkspaceState.

P0 reports (always generated):
  - TECHNICAL_FINDINGS, EXECUTIVE_SUMMARY, REVIEW_REPORT,
    QA_VALIDATION, CONFIDENCE_INDEX

P1 reports (conditional on workspace data):
  - E2E_TEST, MIGRATION_COST, VENDOR_COMPARISON, RISK_HEATMAP
"""

import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import uuid4

from ..core.shared_state import SharedWorkspaceState
from ..models.enums import Severity
from ..models.reports import Report, ReportType

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates all report types from a completed workspace."""

    async def generate_all(
        self,
        workspace: SharedWorkspaceState,
    ) -> Dict[ReportType, Report]:
        """Generate all applicable reports for the workspace."""
        reports: Dict[ReportType, Report] = {}

        # P0 — always generated
        reports[ReportType.TECHNICAL_FINDINGS] = await self._gen_technical(workspace)
        reports[ReportType.EXECUTIVE_SUMMARY] = await self._gen_executive(workspace)
        reports[ReportType.REVIEW_REPORT] = await self._gen_review(workspace)
        reports[ReportType.QA_VALIDATION] = await self._gen_qa(workspace)
        reports[ReportType.CONFIDENCE_INDEX] = await self._gen_confidence(workspace)

        # P1 — conditional
        if workspace.e2e_results:
            reports[ReportType.E2E_TEST] = await self._gen_e2e(workspace)
        if workspace.migration_cost:
            reports[ReportType.MIGRATION_COST] = await self._gen_cost(workspace)
        if workspace.vendor_comparison:
            reports[ReportType.VENDOR_COMPARISON] = await self._gen_vendor(workspace)
        if workspace.risk_scores:
            reports[ReportType.RISK_HEATMAP] = await self._gen_heatmap(workspace)

        logger.info(
            "Generated %d reports for asset %s",
            len(reports), workspace.asset_id,
        )
        return reports

    async def generate_single(
        self,
        workspace: SharedWorkspaceState,
        report_type: ReportType,
    ) -> Optional[Report]:
        """Generate a single report type."""
        generators = {
            ReportType.TECHNICAL_FINDINGS: self._gen_technical,
            ReportType.EXECUTIVE_SUMMARY: self._gen_executive,
            ReportType.REVIEW_REPORT: self._gen_review,
            ReportType.QA_VALIDATION: self._gen_qa,
            ReportType.CONFIDENCE_INDEX: self._gen_confidence,
            ReportType.E2E_TEST: self._gen_e2e,
            ReportType.MIGRATION_COST: self._gen_cost,
            ReportType.VENDOR_COMPARISON: self._gen_vendor,
            ReportType.RISK_HEATMAP: self._gen_heatmap,
        }
        gen_fn = generators.get(report_type)
        if gen_fn is None:
            return None
        return await gen_fn(workspace)

    # ------------------------------------------------------------------
    # P0 report generators
    # ------------------------------------------------------------------

    async def _gen_technical(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-A: Technical Findings — all features and compatibility findings."""
        # Severity breakdown
        severity_counts: dict[str, int] = {}
        for f in ws.compatibility_findings:
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Category breakdown
        category_counts: dict[str, int] = {}
        for feat in ws.features:
            cat = feat.get("category", "unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        content = {
            "asset_type": ws.asset_type.value,
            "loc_count": ws.loc_count,
            "dialect": ws.dialect,
            "total_features": len(ws.features),
            "total_findings": len(ws.compatibility_findings),
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "features": ws.features[:100],  # Cap at 100 for report size
            "findings": ws.compatibility_findings[:100],
            "parse_errors": ws.parse_errors,
        }

        return self._build_report(
            ReportType.TECHNICAL_FINDINGS,
            f"Technical Findings — {ws.file_name}",
            content, ws,
        )

    async def _gen_executive(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-B: Executive Summary — high-level overview for stakeholders."""
        # Count critical/error findings
        critical = sum(
            1 for f in ws.compatibility_findings
            if f.get("severity") == Severity.CRITICAL.value
        )
        errors = sum(
            1 for f in ws.compatibility_findings
            if f.get("severity") == Severity.ERROR.value
        )
        warnings = sum(
            1 for f in ws.compatibility_findings
            if f.get("severity") == Severity.WARNING.value
        )

        # Migration readiness score (inverse of risk)
        overall_risk = 0.0
        if ws.risk_scores:
            overall_risk = ws.risk_scores.get("overall_risk", 0.0)
        readiness = round((1.0 - overall_risk) * 100, 1)

        # Cost summary
        total_days = 0.0
        if ws.migration_cost:
            total_days = ws.migration_cost.get("total_person_days", 0.0)

        content = {
            "asset_name": ws.file_name,
            "asset_type": ws.asset_type.value,
            "loc_count": ws.loc_count,
            "migration_readiness_percent": readiness,
            "critical_issues": critical,
            "error_issues": errors,
            "warning_issues": warnings,
            "total_features_analyzed": len(ws.features),
            "estimated_person_days": total_days,
            "qa_passed": ws.qa_passed,
            "recommended_vendor": self._extract_recommended_vendor(ws),
            "key_risks": self._extract_key_risks(ws),
        }

        return self._build_report(
            ReportType.EXECUTIVE_SUMMARY,
            f"Executive Summary — {ws.file_name}",
            content, ws,
        )

    async def _gen_review(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-C: Review Report — reviewer notes and reanalysis history."""
        # Count by type
        note_types: dict[str, int] = {}
        for note in ws.review_notes:
            ntype = note.get("type", "unknown")
            note_types[ntype] = note_types.get(ntype, 0) + 1

        content = {
            "total_review_notes": len(ws.review_notes),
            "note_type_breakdown": note_types,
            "review_notes": ws.review_notes,
            "reanalysis_triggered": any(
                n.get("type") == "reanalysis_requested" for n in ws.review_notes
            ),
        }

        return self._build_report(
            ReportType.REVIEW_REPORT,
            f"Review Report — {ws.file_name}",
            content, ws,
        )

    async def _gen_qa(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-D: QA Validation — rule engine results and flags."""
        # Severity breakdown of QA flags
        flag_severities: dict[str, int] = {}
        for flag in ws.qa_flags:
            sev = flag.get("severity", "info")
            flag_severities[sev] = flag_severities.get(sev, 0) + 1

        rules_checked = set()
        for flag in ws.qa_flags:
            rules_checked.add(flag.get("rule_id", "unknown"))

        content = {
            "qa_passed": ws.qa_passed,
            "total_flags": len(ws.qa_flags),
            "flag_severity_breakdown": flag_severities,
            "rules_evaluated": sorted(rules_checked),
            "flags": ws.qa_flags,
            "veto_issued": any(
                f.get("severity") == Severity.CRITICAL.value for f in ws.qa_flags
            ) and not ws.qa_passed,
        }

        return self._build_report(
            ReportType.QA_VALIDATION,
            f"QA Validation — {ws.file_name}",
            content, ws,
        )

    async def _gen_confidence(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-I: Confidence Index — per-finding and overall confidence."""
        confidences = [
            f.get("confidence", 0.0) for f in ws.compatibility_findings
        ]
        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )
        low_confidence = [
            {
                "finding_id": f.get("finding_id"),
                "confidence": f.get("confidence", 0.0),
                "feature_name": f.get("feature", {}).get("name", ""),
            }
            for f in ws.compatibility_findings
            if f.get("confidence", 0.0) < 0.6
        ]

        content = {
            "parser_confidence": ws.confidence,
            "average_finding_confidence": round(avg_confidence, 3),
            "total_findings": len(ws.compatibility_findings),
            "low_confidence_count": len(low_confidence),
            "low_confidence_findings": low_confidence[:20],
            "confidence_distribution": self._confidence_distribution(confidences),
        }

        return self._build_report(
            ReportType.CONFIDENCE_INDEX,
            f"Confidence Index — {ws.file_name}",
            content, ws,
        )

    # ------------------------------------------------------------------
    # P1 report generators (conditional)
    # ------------------------------------------------------------------

    async def _gen_e2e(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-E: E2E Test results."""
        e2e = ws.e2e_results or {}
        content = {
            "total": e2e.get("total", 0),
            "passed": e2e.get("passed", 0),
            "failed": e2e.get("failed", 0),
            "regression_detected": e2e.get("failed", 0) > 0,
            "test_cases": e2e.get("test_cases", []),
        }

        return self._build_report(
            ReportType.E2E_TEST,
            f"E2E Test Report — {ws.file_name}",
            content, ws,
        )

    async def _gen_cost(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-F: Migration Cost estimate."""
        cost = ws.migration_cost or {}
        content = {
            "total_person_days": cost.get("total_person_days", 0.0),
            "breakdown": cost.get("breakdown", {}),
            "confidence": cost.get("confidence", 0.0),
            "assumptions": cost.get("assumptions", []),
            "risk_factors": cost.get("risk_factors", []),
        }

        return self._build_report(
            ReportType.MIGRATION_COST,
            f"Migration Cost Estimate — {ws.file_name}",
            content, ws,
        )

    async def _gen_vendor(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-G: Vendor Comparison matrix."""
        vc_list = ws.vendor_comparison or []
        vc = vc_list[0] if vc_list else {}
        content = {
            "vendors": vc.get("vendors", []),
            "matrix": vc.get("matrix", []),
            "summary": vc.get("summary", {}),
            "recommended_vendor": (
                vc.get("summary", {}).get("recommended_vendor", "unknown")
            ),
        }

        return self._build_report(
            ReportType.VENDOR_COMPARISON,
            f"Vendor Comparison — {ws.file_name}",
            content, ws,
        )

    async def _gen_heatmap(self, ws: SharedWorkspaceState) -> Report:
        """FR-04-H: Risk Heatmap (JSON)."""
        risk = ws.risk_scores or {}
        content = {
            "overall_risk": risk.get("overall_risk", 0.0),
            "complexity_score": risk.get("complexity_score", 0.0),
            "effort_score": risk.get("effort_score", 0.0),
            "compatibility_score": risk.get("compatibility_score", 0.0),
            "category_risks": risk.get("category_risks", {}),
        }

        return self._build_report(
            ReportType.RISK_HEATMAP,
            f"Risk Heatmap — {ws.file_name}",
            content, ws,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_report(
        report_type: ReportType,
        title: str,
        content: dict,
        ws: SharedWorkspaceState,
    ) -> Report:
        return Report(
            report_id=str(uuid4()),
            report_type=report_type,
            title=title,
            content=content,
            asset_id=ws.asset_id,
            tenant_id=ws.tenant_id,
        )

    @staticmethod
    def _extract_recommended_vendor(ws: SharedWorkspaceState) -> str:
        if ws.vendor_comparison:
            vc = ws.vendor_comparison[0] if isinstance(ws.vendor_comparison, list) else ws.vendor_comparison
            return vc.get(
                "summary", {},
            ).get("recommended_vendor", "unknown")
        return "openframe"  # Default

    @staticmethod
    def _extract_key_risks(ws: SharedWorkspaceState) -> list[str]:
        risks: list[str] = []
        if ws.migration_cost:
            for rf in ws.migration_cost.get("risk_factors", []):
                risks.append(rf)
        critical_count = sum(
            1 for f in ws.compatibility_findings
            if f.get("severity") == Severity.CRITICAL.value
        )
        if critical_count > 0:
            risks.append(f"{critical_count} critical compatibility findings")
        return risks[:5]

    @staticmethod
    def _confidence_distribution(
        confidences: list[float],
    ) -> dict[str, int]:
        """Bucket confidences into ranges."""
        buckets = {"0.0-0.3": 0, "0.3-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for c in confidences:
            if c < 0.3:
                buckets["0.0-0.3"] += 1
            elif c < 0.6:
                buckets["0.3-0.6"] += 1
            elif c < 0.8:
                buckets["0.6-0.8"] += 1
            else:
                buckets["0.8-1.0"] += 1
        return buckets
