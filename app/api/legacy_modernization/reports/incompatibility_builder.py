"""IncompatibilityReportBuilder — 7-section incompatibility report from workspace state.

Builds a structured report using Capability DB lookups and parser verification
results from the SharedWorkspaceState.

Sections:
  1. file_overview       — basic file metadata
  2. parser_verification — OF7 token-level verification
  3. line_analysis        — per-line verdict (OK/WARNING/INCOMPATIBLE/SYNTAX_ERROR)
  4. capability_lookup    — Capability DB match results
  5. incompatible_items   — aggregated incompatibilities with risk + mitigation
  6. recommendations      — ordered list of migration actions
  7. summary              — numeric totals + support rate
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IncompatibilityReportBuilder:
    """Assemble a 7-section incompatibility report from workspace state."""

    def __init__(self) -> None:
        from ..capabilities.registry import get_product_registry
        self._registry = get_product_registry()

    async def build(self, workspace_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Build the report from a workspace dict (model_dump() output).

        Args:
            workspace_dict: SharedWorkspaceState.model_dump() output.

        Returns:
            7-section report dict.
        """
        features = workspace_dict.get("features", [])
        findings = workspace_dict.get("compatibility_findings", [])
        parse_errors = workspace_dict.get("parse_errors", [])

        # Section 1: File Overview
        file_overview = self._build_file_overview(workspace_dict)

        # Section 2: Parser Verification
        parser_verification = self._build_parser_verification(features)

        # Section 3: Line Analysis
        line_analysis = self._build_line_analysis(
            workspace_dict, findings, parse_errors,
        )

        # Section 4: Capability Lookup
        capability_lookup = self._build_capability_lookup(
            features,
            workspace_dict.get("target_product"),
            workspace_dict.get("target_version"),
        )

        # Section 5: Incompatible Items
        incompatible_items = self._build_incompatible_items(findings)

        # Section 6: Recommendations
        recommendations = self._generate_recommendations(findings)

        # Section 7: Summary
        incompatible_count = len(findings)
        supported_count = max(len(features) - incompatible_count, 0)
        total = max(len(features), 1)
        rate = round((supported_count / total) * 100, 1)

        risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for f in findings:
            sev = f.get("severity", "info").upper()
            if sev in risk_counts:
                risk_counts[sev] += 1

        summary = {
            "total_features": len(features),
            "supported": supported_count,
            "incompatible": incompatible_count,
            "support_rate": rate,
            "risk_high": risk_counts["HIGH"],
            "risk_medium": risk_counts["MEDIUM"],
            "risk_low": risk_counts["LOW"],
        }

        return {
            "file_overview": file_overview,
            "parser_verification": parser_verification,
            "line_analysis": line_analysis,
            "capability_lookup": capability_lookup,
            "incompatible_items": incompatible_items,
            "recommendations": recommendations,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Section builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_file_overview(ws: Dict[str, Any]) -> Dict[str, Any]:
        asset_type = ws.get("asset_type", "")
        if isinstance(asset_type, dict):
            asset_type = asset_type.get("value", asset_type)

        # Try to extract program name from features
        program = ""
        for feat in ws.get("features", []):
            if isinstance(feat, dict):
                name = feat.get("name", "")
                cat = feat.get("category", "")
                if cat in ("program", "PGM") or "PGM=" in name:
                    program = name.replace("PGM=", "")
                    break

        return {
            "file_name": ws.get("file_name", ""),
            "format": str(asset_type).upper(),
            "purpose": _infer_purpose(ws),
            "program": program,
            "total_lines": ws.get("loc_count", 0),
        }

    @staticmethod
    def _build_parser_verification(features: List[dict]) -> List[Dict[str, Any]]:
        results = []
        for feat in features:
            if not isinstance(feat, dict):
                continue
            name = feat.get("name", "")
            metadata = feat.get("metadata", {}) or {}
            results.append({
                "statement": name,
                "of7_token": metadata.get("of7_token", ""),
                "stmt_type": metadata.get("stmt_type", ""),
                "support": metadata.get("support", "SUPPORTED"),
            })
        return results

    @staticmethod
    def _build_line_analysis(
        ws: Dict[str, Any],
        findings: List[dict],
        parse_errors: List[dict],
    ) -> List[Dict[str, Any]]:
        # Build lookup of problematic lines
        problem_lines: Dict[int, str] = {}
        for f in findings:
            line = 0
            feat = f.get("feature", {}) or {}
            if isinstance(feat, dict):
                line = feat.get("line", 0)
            if line > 0:
                sev = f.get("severity", "info").upper()
                if sev == "HIGH":
                    problem_lines[line] = "INCOMPATIBLE"
                elif sev in ("MEDIUM", "WARNING"):
                    problem_lines[line] = "WARNING"
                else:
                    problem_lines[line] = "WARNING"

        for err in parse_errors:
            line = err.get("line", 0)
            if line > 0:
                problem_lines[line] = "SYNTAX_ERROR"

        # Build line entries from AST if available
        ast = ws.get("ast", [])
        results = []
        if ast:
            for node in ast:
                if not isinstance(node, dict):
                    continue
                line = node.get("line", 0)
                source = node.get("source", node.get("raw", ""))
                syntax_type = node.get("type", node.get("syntax_type", ""))
                verdict = problem_lines.get(line, "OK")
                results.append({
                    "line": line,
                    "source": source[:120],
                    "syntax_type": syntax_type,
                    "verdict": verdict,
                })
        return results

    def _build_capability_lookup(
        self,
        features: List[dict],
        product: Optional[str],
        version: Optional[str],
    ) -> List[Dict[str, Any]]:
        results = []

        can_lookup = bool(product and version)
        if can_lookup:
            try:
                self._registry.resolve_capabilities(product, version)
            except Exception:
                logger.debug("Could not resolve capabilities for %s/%s", product, version)
                can_lookup = False

        for feat in features:
            if not isinstance(feat, dict):
                continue
            name = feat.get("name", "")
            category = feat.get("category", "")
            cap_key = f"{category}.{name}".lower().replace(" ", "_")

            status = "UNKNOWN"
            notes = ""
            if can_lookup:
                # Strategy 1: Direct lookup (exact, prefix, utility, param-level)
                cap = self._registry.lookup_capability(product, version, name)

                # Strategy 2: Utility program match via metadata
                if cap is None:
                    metadata = feat.get("metadata", {}) or {}
                    pgm = metadata.get("pgm") or metadata.get("program")
                    if pgm:
                        cap = self._registry.lookup_capability(
                            product, version, f"PGM={pgm.upper()}",
                        )

                # Strategy 3: Subcategory-based pattern (e.g. "DD SYSUT1" → "DD DSN")
                if cap is None:
                    subcategory = feat.get("subcategory", "")
                    if subcategory:
                        cap = self._registry.lookup_capability(
                            product, version, subcategory,
                        )

                if cap:
                    status = cap.support.upper()
                    notes = cap.notes or ""

            results.append({
                "feature": name,
                "capability_key": cap_key,
                "status": status,
                "notes": notes,
            })
        return results

    @staticmethod
    def _build_incompatible_items(findings: List[dict]) -> List[Dict[str, Any]]:
        items = []
        for idx, f in enumerate(findings, 1):
            feat = f.get("feature", {}) or {}
            feat_name = feat.get("name", "unknown") if isinstance(feat, dict) else str(feat)
            items.append({
                "id": idx,
                "item": feat_name,
                "risk": f.get("severity", "info").upper(),
                "description": f.get("description", ""),
                "mitigation": f.get("mitigation", f.get("recommendation", "")),
            })
        # Sort by risk priority
        risk_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        items.sort(key=lambda x: risk_order.get(x["risk"], 3))
        return items

    @staticmethod
    def _generate_recommendations(findings: List[dict]) -> List[str]:
        recs = []
        seen = set()
        for f in findings:
            rec = f.get("recommendation", f.get("mitigation", ""))
            if rec and rec not in seen:
                recs.append(f"{len(recs) + 1}. {rec}")
                seen.add(rec)
        return recs


def _infer_purpose(ws: Dict[str, Any]) -> str:
    """Infer file purpose from features and annotations."""
    annotations = ws.get("annotations", [])
    for ann in annotations:
        if isinstance(ann, dict):
            purpose = ann.get("purpose", "")
            if purpose:
                return purpose

    # Fallback: infer from program name or asset type
    asset_type = ws.get("asset_type", "")
    if isinstance(asset_type, dict):
        asset_type = asset_type.get("value", "")
    return f"{str(asset_type).upper()} source file"


# Singleton
_builder_instance: Optional[IncompatibilityReportBuilder] = None


def get_incompatibility_builder() -> IncompatibilityReportBuilder:
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = IncompatibilityReportBuilder()
    return _builder_instance
